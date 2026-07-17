from __future__ import annotations

from pesi.api.config import get_settings
from pesi.api.services.inference_adapter import InferenceAdapter
from pesi.etl.fooddb_loader import FOOD_SOURCE_CAVEAT


def test_recommendation_evidence_path_uses_multiple_artifact_layers() -> None:
    adapter = InferenceAdapter(get_settings())
    results = adapter.results(limit=10)
    assert results["status"] == "ok"
    recommendation = results["recommendations"][0]

    evidence = adapter.recommendation_evidence({"recommendation_id": recommendation["id"]})
    assert evidence["status"] == "ok"
    entity_types = [step["entity_type"] for step in evidence["path"]]
    assert entity_types == [
        "compound_pair",
        "target_enzyme",
        "enzyme_family",
        "pathway",
        "growth_stage",
        "known_inhibitor_class",
        "natural_source_context",
    ]
    assert "enzyme_state_reasoning" in evidence
    assert "scenario_selectivity" in evidence
    assert "synergy_reasoning" in evidence
    assert "compound_intelligence" in evidence
    assert "assay_prioritization" in evidence
    assert FOOD_SOURCE_CAVEAT in evidence["caveats"]
    assert evidence["confidence_and_limitations"]["proxy_assumptions"]


def test_target_state_reasoning_and_report_include_new_sections() -> None:
    adapter = InferenceAdapter(get_settings())
    results = adapter.results(limit=10)
    target = results["targets"][0]
    reasoning = adapter.target_state_reasoning({"target_id": target["id"]})
    assert reasoning["status"] in {"ok", "missing"}
    assert "evidence_signals" in reasoning
    assert "pathway_context" in reasoning

    report = adapter.build_report({"report_type": "summary", "format": "json"})
    section_titles = [section["title"] for section in report["sections"]]
    assert "Natural source context" in section_titles
    assert "Evidence confidence and limitations" in section_titles
    assert "Assay prioritization" in section_titles
    assert report["recommendation_evidence"]
