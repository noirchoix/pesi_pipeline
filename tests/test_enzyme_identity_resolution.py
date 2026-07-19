from __future__ import annotations

import pandas as pd

from pesi.domain.compound_rules import canonicalize_compound_pair
from pesi.domain.enzyme_identity import (
    canonicalize_enzyme_frame,
    consolidate_enzyme_records,
    resolve_enzyme_identity,
)
from pesi.domain.herbicide_targets import match_herbicide_targets
from pesi.domain.scientific_semantics import (
    classify_selectivity_scope,
    evidence_adjusted_assay_priority,
    fooddb_zero_result_semantics,
)


def test_hct_synonyms_resolve_to_one_canonical_identity() -> None:
    names = [
        "Hydroxycinnamoyl-coenzyme A:shikimate/quinate hydroxycinnamoyl transferase",
        "hydroxycinnamate-CoA shikimate transferase",
        "HCT",
    ]
    identities = [resolve_enzyme_identity(name, "BAHD acyltransferase") for name in names]
    assert {item["canonical_id"] for item in identities} == {"PESI:HCT"}
    assert {item["canonical_name"] for item in identities} == {"shikimate O-hydroxycinnamoyltransferase"}


def test_cse_family_conflict_is_corrected_not_silently_accepted() -> None:
    identity = resolve_enzyme_identity("caffeoylshikimate esterase", "BAHD acyltransferase")
    assert identity["canonical_id"] == "PESI:CSE"
    assert identity["canonical_family"] == "caffeoyl shikimate esterase"
    assert identity["family_validation_status"] == "conflict_corrected"
    assert identity["family_correction_applied"] is True
    assert "not used for canonical grouping" in identity["family_validation_reason"]


def test_plant_gh3_is_not_treated_as_bahd_or_cazy_gh3() -> None:
    identity = resolve_enzyme_identity("GH3 acyl adenylase-family enzyme", "BAHD acyltransferase")
    assert identity["canonical_id"] == "PESI:GH3_ACYL_ACID_AMIDO_SYNTHETASE"
    assert identity["canonical_family"] == "GH3 acyl acid amido synthetase"
    assert identity["family_validation_status"] == "conflict_corrected"
    assert not identity["canonical_id"].startswith("CAZY:")


def test_cazy_identifier_is_family_resolution_not_exact_target() -> None:
    identity = resolve_enzyme_identity("GH157", "GH")
    assert identity["canonical_id"] == "CAZY:GH157"
    assert identity["identity_resolution_level"] == "family"
    assert identity["family_validation_status"] == "refined"
    atlas = match_herbicide_targets("GH157", "GH", "germination")
    assert atlas["target_match_status"] == "family_context"
    assert atlas["known_inhibitor_classes"] == ""
    assert atlas["wssa_group"] == "unmapped"


def test_dynamic_cazy_canonical_labels_are_idempotent() -> None:
    first = resolve_enzyme_identity("GH13_11", "GH")
    second = resolve_enzyme_identity(first["canonical_name"], first["canonical_family"])
    assert first["canonical_id"] == "CAZY:GH13_11"
    assert second["canonical_id"] == first["canonical_id"]


def test_cellulase_is_broad_activity_not_exact_target_identity() -> None:
    identity = resolve_enzyme_identity("cellulase", "CAZy")
    assert identity["canonical_id"] == "PESI:ACTIVITY_CELLULASE"
    assert identity["identity_resolution_level"] == "functional_category"
    assert identity["family_validation_status"] == "compatible_broad"
    atlas = match_herbicide_targets("cellulase", "CAZy", "germination")
    assert atlas["target_match_status"] == "family_context"
    assert atlas["mapping_level"] == "family_or_process_context"
    assert atlas["known_inhibitor_classes"] == ""


def test_explicit_curated_identifier_overrides_unknown_name() -> None:
    identity = resolve_enzyme_identity("unknown label", ec_number="2.5.1.19")
    assert identity["canonical_id"] == "EC:2.5.1.19"
    assert identity["canonical_name"] == "EPSP synthase"
    assert identity["identity_match_basis"] == "explicit_curated_identifier"


def test_identifier_name_conflict_is_auditable() -> None:
    identity = resolve_enzyme_identity("EPSP synthase", "EPSPS", ec_number="2.2.1.6")
    assert identity["canonical_id"] == "EC:2.2.1.6"
    assert identity["identity_resolution_status"] == "resolved_with_warning"
    assert "identifier conflicts" in identity["identity_warning"]


def test_frame_canonicalization_preserves_reported_values() -> None:
    frame = pd.DataFrame(
        [
            {"enzyme_name": "caffeoylshikimate esterase", "enzyme_family": "BAHD acyltransferase"},
            {"enzyme_name": "hydroxycinnamate-CoA shikimate transferase", "enzyme_family": "BAHD acyltransferase"},
        ]
    )
    out = canonicalize_enzyme_frame(frame)
    assert out.loc[0, "enzyme_name_reported"] == "caffeoylshikimate esterase"
    assert out.loc[0, "enzyme_name"] == "caffeoyl shikimate esterase"
    assert out.loc[0, "enzyme_family"] == "caffeoyl shikimate esterase"
    assert out.loc[1, "enzyme_canonical_id"] == "PESI:HCT"


def test_synonymous_target_rows_are_consolidated_by_canonical_id_and_stage() -> None:
    records = [
        {
            "target": "Hydroxycinnamoyl-coenzyme A:shikimate/quinate hydroxycinnamoyl transferase",
            "target_family": "BAHD acyltransferase",
            "stage": "early_vegetative",
            "review_fit": 0.6,
        },
        {
            "target": "hydroxycinnamate-CoA shikimate transferase",
            "target_family": "BAHD acyltransferase",
            "stage": "early vegetative",
            "review_fit": 0.8,
        },
    ]
    consolidated = consolidate_enzyme_records(records)
    assert len(consolidated) == 1
    assert consolidated[0]["target"] == "shikimate O-hydroxycinnamoyltransferase"
    assert consolidated[0]["consolidated_record_count"] == 2
    assert len(consolidated[0]["target_aliases"]) == 2
    assert consolidated[0]["review_fit"] == 0.8


def test_selectivity_scope_requires_paired_target_specific_inputs() -> None:
    baseline = classify_selectivity_scope({"weed_vulnerability": 0.7, "crop_vulnerability": 0.2})
    assert baseline["selectivity_scope"] == "scenario_level"
    specific = classify_selectivity_scope(
        {"weed_target_expression": 1.8, "crop_target_expression": 0.7}
    )
    assert specific["selectivity_scope"] == "target_specific"
    assert specific["target_specific_evidence_present"] is True


def test_evidence_adjusted_priority_does_not_promote_simulation_alone() -> None:
    result = evidence_adjusted_assay_priority(
        simulation={"status": "available", "simulated_max_inhibition": 0.95},
        identity={"identity_resolution_level": "exact_enzyme", "family_validation_status": "validated"},
        target_atlas={"target_match_status": "validated"},
        state_signals={
            "kinetic_evidence": 0.0,
            "structure_evidence": 0.0,
            "plant_context": 0.0,
            "uncertainty_penalty": 0.4,
        },
        compound_target_evidence_tier="model_inference",
    )
    assert result["simulation_priority"] == "High simulation-derived response rank"
    assert result["scientific_priority_code"] == "exploratory"
    assert any("Compound-target support" in reason for reason in result["gating_reasons"])


def test_high_scientific_priority_requires_identity_biology_and_target_evidence() -> None:
    result = evidence_adjusted_assay_priority(
        simulation={"status": "available", "simulated_max_inhibition": 0.9},
        identity={"identity_resolution_level": "exact_enzyme", "family_validation_status": "validated"},
        target_atlas={"target_match_status": "validated"},
        state_signals={
            "kinetic_evidence": 0.9,
            "structure_evidence": 0.8,
            "plant_context": 0.8,
            "uncertainty_penalty": 0.05,
        },
        compound_target_evidence_tier="direct_measurement",
    )
    assert result["scientific_priority_code"] == "high"
    assert result["scientific_priority"] == "High scientific validation priority"


def test_fooddb_zero_result_semantics_are_distinct() -> None:
    direct = fooddb_zero_result_semantics(
        query_available=True,
        compound_a_matched=True,
        compound_b_matched=True,
        shared_record_count=2,
    )
    zero = fooddb_zero_result_semantics(
        query_available=True,
        compound_a_matched=True,
        compound_b_matched=True,
        shared_record_count=0,
    )
    unmatched = fooddb_zero_result_semantics(
        query_available=True,
        compound_a_matched=True,
        compound_b_matched=False,
        shared_record_count=0,
    )
    unavailable = fooddb_zero_result_semantics(
        query_available=False,
        compound_a_matched=False,
        compound_b_matched=False,
        shared_record_count=0,
    )
    assert direct["evidence_tier"] == "direct_occurrence"
    assert zero["evidence_tier"] == "database_query_no_shared_occurrence"
    assert unmatched["evidence_tier"] == "compound_unmatched"
    assert unavailable["evidence_tier"] == "database_unavailable"


def test_compound_pair_key_is_order_invariant() -> None:
    assert canonicalize_compound_pair("Compound B", "Compound A") == canonicalize_compound_pair(
        "Compound A", "Compound B"
    )
