from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from pesi.etl.fooddb_loader import (
    FOOD_SOURCE_CAVEAT,
    FoodDBMapper,
    augment_kg_with_food_sources,
    discover_food_chemistry,
)


def test_food_chemistry_bundle_is_discovered() -> None:
    paths = discover_food_chemistry("raw")
    assert paths.available
    assert paths.duckdb_path is not None
    assert paths.duckdb_path.name == "fooddb.duckdb"
    assert paths.curated_dir is not None
    assert (paths.curated_dir / "food_compound_edges.parquet").exists()


def test_fooddb_identifier_mapping_and_occurrence_sources() -> None:
    mapper = FoodDBMapper("raw")
    pool = pd.DataFrame([
        {
            "compound_name": "3,4-dihydroxybenzoate",
            "compound_name_canonical": "3 4-dihydroxybenzoate",
            "smiles": "OC=1C=C(C(=O)[O-])C=CC1O",
        }
    ])
    matches = mapper.match_compounds(pool)
    assert len(matches) == 1
    row = matches.iloc[0]
    assert row["match_status"] == "matched"
    assert row["fooddb_compound_name"] == "protocatechuate"
    assert float(row["match_confidence"]) >= 0.9

    sources = mapper.food_sources(matches, top_n_per_compound=10)
    assert not sources.empty
    assert set(sources["pesi_compound_name"]) == {"3,4-dihydroxybenzoate"}
    assert sources["food_name"].notna().all()
    assert sources["source_confidence"].between(0, 1).all()
    assert set(sources["mapping_caveat"]) == {FOOD_SOURCE_CAVEAT}


def test_food_kg_augmentation_is_idempotent(tmp_path: Path) -> None:
    kg_path = tmp_path / "pesi_kg.sqlite"
    with sqlite3.connect(kg_path) as con:
        pd.DataFrame([
            {
                "node_id": "Compound:seed",
                "node_type": "Compound",
                "label": "seed",
                "source_resource": "fixture",
                "evidence_class": "real_evidence",
            }
        ]).to_sql("kg_nodes", con, index=False)
        pd.DataFrame([
            {
                "src": "Compound:seed",
                "dst": "Compound:seed",
                "rel": "self",
                "source_resource": "fixture",
                "evidence_class": "real_evidence",
            }
        ]).to_sql("kg_edges", con, index=False)

    matches = pd.DataFrame([
        {
            "pesi_compound_name": "protocatechuate",
            "fooddb_compound_id": 31298,
            "fooddb_public_id": "FDB031135",
            "fooddb_compound_name": "protocatechuate",
            "evidence_class": "direct_structure_identifier_match",
        }
    ])
    sources = pd.DataFrame([
        {
            "fooddb_compound_id": 31298,
            "fooddb_public_id": "FDB031135",
            "food_id": 6,
            "food_public_id": "FOOD00006",
            "food_name": "Garden onion",
            "evidence_class": "fooddb_reported_occurrence_evidence",
        }
    ])
    pair_context = pd.DataFrame([
        {
            "pair_key": "a||b",
            "compound_a": "a",
            "compound_b": "b",
            "shared_food_count": 0,
        }
    ])

    first = augment_kg_with_food_sources(kg_path, matches, sources, pair_context)
    second = augment_kg_with_food_sources(kg_path, matches, sources, pair_context)
    assert first == {"nodes_added": 3, "nodes_removed": 0, "edges_added": 2, "edges_removed": 0}
    assert second == {"nodes_added": 0, "nodes_removed": 0, "edges_added": 0, "edges_removed": 0}

    with sqlite3.connect(kg_path) as con:
        node_count = con.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0]
        edge_count = con.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0]
    assert node_count == 4
    assert edge_count == 3
