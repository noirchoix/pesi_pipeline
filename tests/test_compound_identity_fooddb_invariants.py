from __future__ import annotations

import json

import pandas as pd

from pesi.api.config import ApiSettings
from pesi.api.services.report_interpreter import ReportInterpreter
from pesi.domain.compound_identity import (
    canonical_compound_identity,
    canonical_compound_pair_key,
    structure_identifiers,
)
from pesi.domain.enzyme_identity import resolve_enzyme_identity
from pesi.domain.scientific_semantics import evidence_adjusted_assay_priority
from pesi.etl.fooddb_loader import FoodDBMapper, build_pair_source_context


def _minimal_evidence(target: str, *, assay_available: bool = True) -> dict:
    assay = (
        {
            "status": "available",
            "relative_input_band": [0.6, 1.5],
            "simulated_max_inhibition": 0.8,
            "scientific_priority": "Exploratory scientific validation priority",
            "scientific_priority_code": "exploratory",
            "scientific_priority_score": 0.4,
            "simulation_priority": "High simulation-derived response rank",
            "gating_reasons": ["Compound-target support is model-derived or unresolved."],
        }
        if assay_available
        else {"status": "not_available"}
    )
    return {
        "enzyme_state_reasoning": {
            "growth_stage": "seedling_emergence",
            "target_class": "screening context",
            "evidence_signals": {
                "kinetic_evidence": 0.0,
                "structure_evidence": 0.0,
                "plant_context": 0.0,
                "pathway_essentiality": 0.8,
                "uncertainty_penalty": 0.4,
            },
        },
        "scenario_selectivity": {
            "stage_relevance": "seedling_emergence",
            "weed_vulnerability": 0.6,
            "crop_vulnerability": 0.3,
            "selectivity_difference": 0.3,
            "selectivity_index": 0.8,
            "selectivity_scope": "scenario_level",
            "target_specific_evidence_present": False,
        },
        "target_atlas_validation": {"target_match_status": "unmapped"},
        "assay_prioritization": assay,
        "confidence_and_limitations": {
            "model_inference": ["compound-pair optimization"],
            "weak_or_unsupported_assumptions": ["requires validation"],
        },
        "path": [],
        "source_artifacts": [],
    }


def test_structure_backed_compound_ids_and_pair_keys_are_order_invariant() -> None:
    key = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
    ethanol = canonical_compound_identity(name="ethanol", inchikey=key)
    ethyl_alcohol = canonical_compound_identity(name="ethyl alcohol", inchikey=key)
    water = canonical_compound_identity(name="water", inchikey="XLYOFNOQVPJJNP-UHFFFAOYSA-N")

    assert ethanol["canonical_compound_id"] == ethyl_alcohol["canonical_compound_id"]
    assert ethanol["structure_backed_identity"] is True
    assert canonical_compound_pair_key(ethanol, water) == canonical_compound_pair_key(water, ethyl_alcohol)

    invalid = canonical_compound_identity(name="invalid", canonical_smiles="not-a-smiles")
    assert invalid["structure_backed_identity"] is False
    assert invalid["compound_identity_level"] == "normalized_name_fallback"


def test_pair_context_never_assigns_matched_partner_sources_to_unmatched_compound() -> None:
    a_id = canonical_compound_identity(name="matched-a", inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N")["canonical_compound_id"]
    b_id = canonical_compound_identity(name="unmatched-b", inchikey="XLYOFNOQVPJJNP-UHFFFAOYSA-N")["canonical_compound_id"]
    optimized = pd.DataFrame([
        {
            "compound_a": "matched-a",
            "compound_b": "unmatched-b",
            "compound_a_canonical_id": a_id,
            "compound_b_canonical_id": b_id,
        }
    ])
    # Include a deliberately contaminated source row for B. The match table is
    # authoritative and must suppress it because B is unmatched.
    sources = pd.DataFrame([
        {
            "pesi_compound_name": "matched-a",
            "pesi_compound_canonical_id": a_id,
            "compound_match_status": "matched",
            "food_id": 1,
            "food_name": "Olive",
            "occurrence_evidence": "reported_occurrence",
            "source_confidence": 0.9,
            "evidence_class": "fooddb_reported_occurrence_evidence",
        },
        {
            "pesi_compound_name": "unmatched-b",
            "pesi_compound_canonical_id": b_id,
            "compound_match_status": "matched",
            "food_id": 1,
            "food_name": "Olive",
            "occurrence_evidence": "reported_occurrence",
            "source_confidence": 0.9,
            "evidence_class": "contaminated_fixture",
        },
    ])
    matches = pd.DataFrame([
        {"pesi_compound_canonical_id": a_id, "match_status": "matched", "match_confidence": 1.0, "fooddb_compound_id": 11},
        {"pesi_compound_canonical_id": b_id, "match_status": "unmatched", "match_confidence": 0.0, "fooddb_compound_id": None},
    ])

    context, evidence = build_pair_source_context(optimized, sources, matches=matches)
    row = context.iloc[0]
    assert row["source_context_status"] == "compound_unmatched"
    assert json.loads(row["compound_b_sources_json"]) == []
    assert json.loads(row["shared_foods_json"]) == []
    assert row["shared_food_count"] == 0
    assert evidence.empty


def test_fooddb_mapper_emits_occurrences_only_for_the_owning_matched_identity(tmp_path) -> None:
    import duckdb

    staging = tmp_path / "food_chemistry" / "staging"
    staging.mkdir(parents=True)
    db_path = staging / "fooddb.duckdb"
    canonical, inchikey = structure_identifiers("OC=1C=C(C(=O)O)C=CC1O")
    assert canonical and inchikey
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            "CREATE TABLE curated_compound_lookup(compound_id BIGINT, public_id VARCHAR, name VARCHAR, cas_number VARCHAR, inchikey VARCHAR, inchi VARCHAR, kingdom VARCHAR, superklass VARCHAR, klass VARCHAR, subklass VARCHAR)"
        )
        con.execute(
            "INSERT INTO curated_compound_lookup VALUES (1, 'FDB0001', '3,4-dihydroxybenzoate', NULL, ?, NULL, 'Organic compounds', 'Benzenoids', 'Benzoic acids', 'Hydroxybenzoic acids')",
            [inchikey],
        )
        con.execute("CREATE TABLE compound_synonym(source_id VARCHAR, source_type VARCHAR, synonym VARCHAR)")
        con.execute("CREATE TABLE curated_food_lookup(food_id BIGINT, public_id VARCHAR, name VARCHAR, name_scientific VARCHAR, food_group VARCHAR, food_subgroup VARCHAR)")
        con.execute("INSERT INTO curated_food_lookup VALUES (10, 'FOOD10', 'Olive', 'Olea europaea', 'Fruits', 'Olives')")
        con.execute(
            "CREATE TABLE curated_food_compound_content(compound_id BIGINT, food_id BIGINT, standard_content DOUBLE, orig_content DOUBLE, orig_unit VARCHAR, preparation_type VARCHAR, citation VARCHAR, citation_type VARCHAR)"
        )
        con.execute("INSERT INTO curated_food_compound_content VALUES (1, 10, 2.5, 2.5, 'mg/100g', 'raw', 'fixture', 'DATABASE')")
    finally:
        con.close()

    mapper = FoodDBMapper(tmp_path)
    pool = pd.DataFrame([
        {"compound_id": "matched", "compound_name": "3,4-dihydroxybenzoate", "smiles": canonical, "source_resource": "fixture"},
        {"compound_id": "unmatched", "compound_name": "unresolved phosphonate", "smiles": "O=P(O)(O)CCO", "source_resource": "fixture"},
    ])
    matches = mapper.match_compounds(pool)
    sources = mapper.food_sources(matches)
    status_by_name = dict(zip(matches["pesi_compound_name"], matches["match_status"]))
    assert status_by_name["3,4-dihydroxybenzoate"] == "matched"
    assert status_by_name["unresolved phosphonate"] == "unmatched"
    matched_id = matches.loc[matches["pesi_compound_name"].eq("3,4-dihydroxybenzoate"), "pesi_compound_canonical_id"].iloc[0]
    unmatched_id = matches.loc[matches["pesi_compound_name"].eq("unresolved phosphonate"), "pesi_compound_canonical_id"].iloc[0]
    assert set(sources["pesi_compound_canonical_id"]) == {matched_id}
    assert unmatched_id not in set(sources["pesi_compound_canonical_id"])
    assert sources.iloc[0]["food_name"] == "Olive"


def test_report_row_validator_suppresses_legacy_unmatched_sources_and_shared_claims() -> None:
    a_id = canonical_compound_identity(name="Matched A")["canonical_compound_id"]
    b_id = canonical_compound_identity(name="Unmatched B")["canonical_compound_id"]
    pair_key = canonical_compound_pair_key(a_id, b_id)
    interpreter = ReportInterpreter(ApiSettings(project_root=".", ai_enabled=False))
    report = interpreter.aggregate(
        scenario={"crop": "Zea mays", "weed": "Amaranthus palmeri", "growth_stage": "seedling_emergence"},
        recommendations=[{
            "id": "r1",
            "compound_a": "Matched A",
            "compound_b": "Unmatched B",
            "compound_a_canonical_id": a_id,
            "compound_b_canonical_id": b_id,
            "canonical_pair_key": pair_key,
            "target": "alpha-amylase",
            "target_family": "alpha-amylase",
            "stage": "Germination",
            "evidence_strength": "Exploratory lead",
        }],
        targets=[],
        evidence_by_recommendation={"r1": _minimal_evidence("alpha-amylase")},
        target_reasoning=[],
        pair_food_details={
            pair_key: {
                "context": {
                    "status": "shared_sources_found",
                    "shared_food_count": 1,
                    "shared_sources": [{"food_name": "Olive"}],
                },
                "compound_a_detail": {
                    "canonical_compound_id": a_id,
                    "match_status": "matched",
                    "match": {"match_status": "matched", "fooddb_compound_id": 1, "fooddb_compound_name": "Matched A", "match_method": "inchikey_exact"},
                    "sources": [{"pesi_compound_canonical_id": a_id, "food_name": "Olive"}],
                },
                "compound_b_detail": {
                    "canonical_compound_id": b_id,
                    "match_status": "unmatched",
                    "match": None,
                    "sources": [{"pesi_compound_canonical_id": b_id, "food_name": "Olive"}],
                },
            }
        },
        report_type="full",
        caveats=["Computational screening candidate only."],
        food_mapping={"status": "completed"},
    )

    source = report["pair_groups"][0]["natural_source_context"]
    assert source["compound_b"]["match_status"] == "unmatched"
    assert source["compound_b"]["source_count"] == 0
    assert source["compound_b"]["top_source_names"] == []
    assert source["shared_source_count"] == 0
    assert source["shared_source_names"] == []
    assert "unmatched_compound_source_suppressed" in report["semantic_validation"]["corrections"]
    assert "invalid_shared_occurrence_suppressed" in report["semantic_validation"]["corrections"]


def test_source_dataset_family_conflict_is_tracked_and_penalized() -> None:
    conflicting = resolve_enzyme_identity(
        "caffeoyl shikimate esterase",
        "BAHD acyltransferase",
        source="BAHD acyltransferase Minimally Curated Set.xlsx",
    )
    clean = resolve_enzyme_identity(
        "caffeoyl shikimate esterase",
        "caffeoyl shikimate esterase",
        source="independent curated enzyme registry",
    )
    assert conflicting["source_dataset_family_conflict"] is True
    assert conflicting["source_dataset_family_validation_status"] == "conflict"

    simulation = {"status": "available", "simulated_max_inhibition": 0.9}
    state = {"kinetic_evidence": 0.8, "structure_evidence": 0.8, "plant_context": 0.8, "uncertainty_penalty": 0.1}
    atlas = {"target_match_status": "validated_target"}
    conflicting_priority = evidence_adjusted_assay_priority(
        simulation=simulation,
        identity=conflicting,
        target_atlas=atlas,
        state_signals=state,
        compound_target_evidence_tier="curated_target_evidence",
    )
    clean_priority = evidence_adjusted_assay_priority(
        simulation=simulation,
        identity=clean,
        target_atlas=atlas,
        state_signals=state,
        compound_target_evidence_tier="curated_target_evidence",
    )
    assert conflicting_priority["scientific_priority_score"] < clean_priority["scientific_priority_score"]
    assert any("source dataset" in reason.casefold() for reason in conflicting_priority["gating_reasons"])


def test_executive_consistency_rejects_simulation_coverage_as_evidence_strength(monkeypatch) -> None:
    interpreter = ReportInterpreter(
        ApiSettings(project_root=".", ai_enabled=True, ai_provider="deepseek", deepseek_api_key="test")
    )

    def bad_synthesis(*, system, user, fallback):
        return {
            "status": "ok",
            "executive_summary": "The strongest scientific evidence comes from complete assay coverage. All target contexts are exploratory.",
            "key_findings": [],
            "scenario_interpretation": "All target contexts remain exploratory.",
            "ai_source": "deepseek",
            "ai_status": "generated",
        }

    monkeypatch.setattr(interpreter.llm, "complete_json", bad_synthesis)
    recommendations = [
        {
            "id": "r1",
            "compound_a": "A",
            "compound_b": "B",
            "target": "alpha-amylase",
            "target_family": "alpha-amylase",
            "stage": "Germination",
            "evidence_strength": "Exploratory lead",
        },
        {
            "id": "r2",
            "compound_a": "A",
            "compound_b": "B",
            "target": "EPSP synthase",
            "target_family": "EPSPS",
            "stage": "Early vegetative",
            "evidence_strength": "Exploratory lead",
        },
    ]
    report = interpreter.aggregate(
        scenario={"crop": "Zea mays", "weed": "Amaranthus palmeri", "growth_stage": "seedling_emergence"},
        recommendations=recommendations,
        targets=[],
        evidence_by_recommendation={
            "r1": _minimal_evidence("alpha-amylase", assay_available=False),
            "r2": _minimal_evidence("EPSP synthase", assay_available=True),
        },
        target_reasoning=[],
        pair_food_details={},
        report_type="full",
        caveats=["Computational screening candidate only."],
        food_mapping={},
    )
    corrections = report["semantic_validation"]["corrections"]
    assert "simulation_coverage_misrepresented_as_evidence_strength" in corrections
    assert "not_prioritizable_contexts_omitted" in corrections
    body = report["executive_summary"]["body"].casefold()
    assert "strongest scientific evidence comes from complete assay coverage" not in body
    assert "not prioritizable" in body
