from __future__ import annotations

from pesi.domain.scientific_semantics import (
    classify_evidence_source,
    normalize_fooddb_match,
    normalize_selectivity,
)


def test_legacy_centered_selectivity_is_separated_from_difference() -> None:
    semantics = normalize_selectivity(
        weed_vulnerability=0.632,
        crop_vulnerability=0.280,
        reported_margin=0.852,
    )
    assert semantics["selectivity_difference"] == 0.352
    assert semantics["selectivity_index"] == 0.852
    assert semantics["legacy_centered_index_detected"] is True


def test_fooddb_unmatched_status_never_renders_as_ok() -> None:
    normalized = normalize_fooddb_match(
        {
            "status": "ok",
            "match": {
                "match_status": "unmatched",
                "match_method": "unmatched",
                "match_confidence": 0.0,
            },
        },
        source_count=0,
    )
    assert normalized["status"] == "unmatched"
    assert normalized["status_label"] == "No FoodDB compound match"
    assert normalized["match_method"] == "Not applicable"
    assert normalized["match_confidence"] is None


def test_evidence_classification_is_conservative() -> None:
    assert classify_evidence_source("FoodDB compound and food occurrence records", has_occurrence_record=True) == "direct_occurrence"
    assert classify_evidence_source("BAHD_acyltransferase_Minimally_Curated_Set.xlsx") == "curated_reference"
    assert classify_evidence_source("weed_assignment") == "model_inference"
    assert classify_evidence_source("pseudo-lab response simulation") == "proxy_estimate"
