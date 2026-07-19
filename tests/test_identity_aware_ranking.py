from __future__ import annotations

import pandas as pd

from pesi.domain.compound_identity import canonical_compound_identity, canonical_compound_pair_key
from pesi.etl.fooddb_loader import build_pair_source_context
from pesi.ml.pipeline import select_diverse_interventions


def test_diversity_selector_deduplicates_target_synonyms_by_canonical_id() -> None:
    scored = pd.DataFrame(
        [
            {
                "target_enzyme": "Hydroxycinnamoyl-coenzyme A:shikimate/quinate hydroxycinnamoyl transferase",
                "target_family": "BAHD acyltransferase",
                "target_canonical_id": "PESI:HCT",
                "target_family_canonical": "BAHD acyltransferase",
                "stage": "early_vegetative",
                "compound_a": "Compound A",
                "compound_b": "Compound B",
                "optimization_objective": 0.8,
            },
            {
                "target_enzyme": "hydroxycinnamate-CoA shikimate transferase",
                "target_family": "BAHD acyltransferase",
                "target_canonical_id": "PESI:HCT",
                "target_family_canonical": "BAHD acyltransferase",
                "stage": "early vegetative",
                "compound_a": "Compound B",
                "compound_b": "Compound A",
                "optimization_objective": 0.7,
            },
        ]
    )
    selected, report = select_diverse_interventions(scored, max_rows=10)
    assert len(selected) == 1
    assert selected.iloc[0]["optimization_objective"] == 0.8
    assert report["semantic_deduplication"] is True


def test_fooddb_pair_context_uses_order_invariant_canonical_provenance() -> None:
    a_id = canonical_compound_identity(name="Compound A")["canonical_compound_id"]
    b_id = canonical_compound_identity(name="Compound B")["canonical_compound_id"]
    optimized = pd.DataFrame(
        [
            {"compound_a": "Compound B", "compound_b": "Compound A", "compound_a_canonical_id": b_id, "compound_b_canonical_id": a_id},
            {"compound_a": "Compound A", "compound_b": "Compound B", "compound_a_canonical_id": a_id, "compound_b_canonical_id": b_id},
        ]
    )
    sources = pd.DataFrame(
        [
            {
                "pesi_compound_name": "Compound A",
                "pesi_compound_canonical_id": a_id,
                "compound_match_status": "matched",
                "food_id": 1,
                "food_name": "Olive",
                "occurrence_evidence": "reported_occurrence",
                "source_confidence": 0.9,
                "evidence_class": "fooddb_reported_occurrence_evidence",
            },
            {
                "pesi_compound_name": "Compound B",
                "pesi_compound_canonical_id": b_id,
                "compound_match_status": "matched",
                "food_id": 1,
                "food_name": "Olive",
                "occurrence_evidence": "reported_occurrence",
                "source_confidence": 0.8,
                "evidence_class": "fooddb_reported_occurrence_evidence",
            },
        ]
    )
    matches = pd.DataFrame([
        {"pesi_compound_canonical_id": a_id, "match_status": "matched", "match_confidence": 1.0, "fooddb_compound_id": 11},
        {"pesi_compound_canonical_id": b_id, "match_status": "matched", "match_confidence": 1.0, "fooddb_compound_id": 12},
    ])
    context, evidence = build_pair_source_context(optimized, sources, matches=matches)
    assert len(context) == 1
    assert context.iloc[0]["pair_key"] == canonical_compound_pair_key(a_id, b_id)
    assert {context.iloc[0]["compound_a"], context.iloc[0]["compound_b"]} == {"Compound A", "Compound B"}
    assert len(evidence) == 1
    assert evidence.iloc[0]["pair_key"] == context.iloc[0]["pair_key"]
