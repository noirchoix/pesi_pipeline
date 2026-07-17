from __future__ import annotations

from pesi.api.config import ApiSettings
from pesi.api.services.report_interpreter import ReportInterpreter


def _evidence(target: str, *, shared: bool = False) -> dict:
    food_source = {
        "food_name": "Olive",
        "food_group": "Fruits",
        "source_confidence": 0.96,
        "evidence_class": "fooddb_reported_occurrence_evidence",
    }
    return {
        "path": [
            {
                "entity_type": "target_enzyme",
                "label": target,
                "source": "weed_assignment",
                "evidence_tier": "mixed_evidence",
            },
            {
                "entity_type": "pathway",
                "label": "shikimate aromatic amino acid biosynthesis",
                "source": "PESI herbicide target atlas",
                "evidence_tier": "curated_rule_or_direct",
            },
        ],
        "enzyme_state_reasoning": {
            "growth_stage": "seedling_emergence",
            "target_class": "curated_family_function",
            "evidence_signals": {
                "pathway_essentiality": 0.9,
                "kinetic_evidence": 0.62,
                "structure_evidence": 0.55,
                "plant_context": 0.8,
                "uncertainty_penalty": 0.31,
            },
        },
        "scenario_selectivity": {
            "stage_relevance": "seedling_emergence",
            "weed_vulnerability": 0.7,
            "crop_vulnerability": 0.25,
            "selectivity_margin": 0.45,
        },
        "synergy_reasoning": {
            "functional_signals": ["active site compatibility", "transition state mimicry"],
        },
        "pathway_context": [
            {
                "pathway": "shikimate_aromatic_amino_acid_biosynthesis",
                "site_of_action": "5-enolpyruvylshikimate-3-phosphate synthase",
                "source": "PESI herbicide target atlas",
                "evidence_class": "curated_literature_rule",
            }
        ],
        "assay_prioritization": {
            "status": "available",
            "relative_input_band": [0.4, 1.0],
            "simulated_max_inhibition": 0.82,
            "model": "relative response simulation",
            "interpretation": "Relative assay design context only.",
        },
        "natural_source_context": {
            "shared_sources": [food_source] if shared else [],
            "compound_a_sources": [food_source],
            "compound_b_sources": [food_source],
        },
        "confidence_and_limitations": {
            "direct_evidence": ["FoodDB compound and food occurrence records", "weed_assignment"],
            "model_inference": ["compound-pair optimization"],
            "proxy_assumptions": ["crop-impact proxy"],
            "weak_or_unsupported_assumptions": ["Crop-weed selectivity exists for every pair"],
        },
        "source_artifacts": [
            "aim4_optimized_interventions.csv",
            "scenario_selectivity.csv",
            "compound_food_sources.csv",
        ],
    }


def test_report_groups_pairs_and_exposes_food_provenance_and_appendix() -> None:
    settings = ApiSettings(project_root=".", ai_enabled=False)
    interpreter = ReportInterpreter(settings)
    recommendations = [
        {
            "id": "r1",
            "compound_a": "Compound A",
            "compound_b": "Compound B",
            "target": "EPSP synthase",
            "target_family": "EPSPS",
            "stage": "Seedling emergence",
            "evidence_strength": "Strong review lead",
            "chemical_class": "phosphonate + phenolic",
            "validation_note": "Confirm target engagement.",
            "raw_scores": {"review_fit": 0.61},
        },
        {
            "id": "r2",
            "compound_a": "Compound B",
            "compound_b": "Compound A",
            "target": "acetolactate synthase",
            "target_family": "ALS/AHAS",
            "stage": "Seedling emergence",
            "evidence_strength": "Strong review lead",
            "chemical_class": "phosphonate + phenolic",
            "validation_note": "Confirm target engagement.",
            "raw_scores": {"review_fit": 0.60},
        },
    ]
    pair_key = "compound a||compound b"
    pair_food = {
        pair_key: {
            "status": "ok",
            "context": {
                "shared_food_count": 1,
                "shared_source_confidence": 0.96,
                "shared_sources": [{"food_name": "Olive", "food_group": "Fruits", "source_confidence": 0.96}],
                "caveat": "Occurrence context only.",
            },
            "compound_a_detail": {
                "status": "ok",
                "match": {"fooddb_compound_name": "Compound A", "match_method": "exact_normalized_name", "match_confidence": 1.0},
                "sources": [{"food_name": "Olive", "food_group": "Fruits", "source_confidence": 0.96}],
            },
            "compound_b_detail": {
                "status": "ok",
                "match": {"fooddb_compound_name": "Compound B", "match_method": "exact_synonym", "match_confidence": 0.92},
                "sources": [{"food_name": "Olive", "food_group": "Fruits", "source_confidence": 0.96}],
            },
        }
    }
    report = interpreter.aggregate(
        scenario={"crop": "Zea mays", "weed": "Amaranthus palmeri", "growth_stage": "seedling_emergence"},
        recommendations=recommendations,
        targets=[],
        evidence_by_recommendation={"r1": _evidence("EPSP synthase", shared=True), "r2": _evidence("acetolactate synthase", shared=True)},
        target_reasoning=[],
        pair_food_details=pair_food,
        report_type="summary",
        caveats=["Computational screening candidate only."],
        food_mapping={"status": "completed"},
    )

    assert len(report["pair_groups"]) == 1
    group = report["pair_groups"][0]
    assert group["target_count"] == 2
    assert {item["target"] for item in group["targets"]} == {"EPSP synthase", "acetolactate synthase"}
    assert group["natural_source_context"]["shared_source_names"] == ["Olive"]
    assert group["natural_source_context"]["compound_a"]["match_method"] == "exact normalized name"
    assert group["assay_prioritization"]["overall_priority"] == "High relative assay priority"
    assert "PESI crop/weed assignment evidence" in group["confidence"]["direct_evidence"]
    assert report["interpretation_mode"]["label"] == "Deterministic artifact-grounded synthesis"
    assert report["technical_appendix"]["pair_count"] == 1
    assert "Executive synthesis" in [section["title"] for section in report["sections"]]

    rendered = interpreter.render_html(report)
    assert "Olive" in rendered
    assert "EPSP synthase" in rendered
    assert "acetolactate synthase" in rendered
    assert "Technical appendix" in rendered
    assert "exact normalized name" in rendered
