from __future__ import annotations

from pesi.api.config import ApiSettings
from pesi.api.services.report_interpreter import ReportInterpreter
from pesi.domain.compound_identity import canonical_compound_identity, canonical_compound_pair_key


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
            "direct_occurrence_evidence": ["FoodDB compound and food occurrence records"],
            "curated_reference_evidence": ["PESI herbicide target atlas"],
            "scenario_context": ["User-provided crop, weed, and growth-stage scenario"],
            "model_inference": ["compound-pair optimization", "weed_assignment"],
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
    a_id = canonical_compound_identity(name="Compound A")["canonical_compound_id"]
    b_id = canonical_compound_identity(name="Compound B")["canonical_compound_id"]
    pair_key = canonical_compound_pair_key(a_id, b_id)
    recommendations = [
        {
            "id": "r1",
            "compound_a": "Compound A",
            "compound_b": "Compound B",
            "compound_a_canonical_id": a_id,
            "compound_b_canonical_id": b_id,
            "canonical_pair_key": pair_key,
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
            "compound_a_canonical_id": b_id,
            "compound_b_canonical_id": a_id,
            "canonical_pair_key": pair_key,
            "target": "acetolactate synthase",
            "target_family": "ALS/AHAS",
            "stage": "Seedling emergence",
            "evidence_strength": "Strong review lead",
            "chemical_class": "phosphonate + phenolic",
            "validation_note": "Confirm target engagement.",
            "raw_scores": {"review_fit": 0.60},
        },
    ]
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
                "canonical_compound_id": a_id,
                "match": {"fooddb_compound_id": 1, "fooddb_compound_name": "Compound A", "match_method": "exact_normalized_name", "match_confidence": 1.0},
                "sources": [{"pesi_compound_canonical_id": a_id, "food_name": "Olive", "food_group": "Fruits", "source_confidence": 0.96}],
            },
            "compound_b_detail": {
                "status": "ok",
                "canonical_compound_id": b_id,
                "match": {"fooddb_compound_id": 2, "fooddb_compound_name": "Compound B", "match_method": "exact_synonym", "match_confidence": 0.92},
                "sources": [{"pesi_compound_canonical_id": b_id, "food_name": "Olive", "food_group": "Fruits", "source_confidence": 0.96}],
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
    assert group["assay_prioritization"]["overall_priority"] == "Exploratory scientific validation priority"
    assert all(item["simulation_priority"] == "Simulation output available" for item in group["assay_prioritization"]["target_bands"])
    assert "FoodDB compound and food occurrence records" in group["confidence"]["direct_occurrence_evidence"]
    assert "Curated herbicide target atlas" in group["confidence"]["curated_reference_evidence"]
    assert "weed_assignment" in group["confidence"]["model_inference"]
    assert report["interpretation_mode"]["semantic_validation_status"] == "passed"
    assert report["technical_appendix"]["pair_count"] == 1
    assert "Executive synthesis" in [section["title"] for section in report["sections"]]

    rendered = interpreter.render_html(report)
    assert "Olive" in rendered
    assert "EPSP synthase" in rendered
    assert "acetolactate synthase" in rendered
    assert "Technical appendix" in rendered
    assert "exact normalized name" in rendered


def test_deepseek_synthesis_is_corrected_when_it_contradicts_structured_facts(monkeypatch) -> None:
    settings = ApiSettings(project_root=".", ai_enabled=True, ai_provider="deepseek", deepseek_api_key="test")
    interpreter = ReportInterpreter(settings)
    a_id = canonical_compound_identity(name="Compound A")["canonical_compound_id"]
    b_id = canonical_compound_identity(name="Compound B")["canonical_compound_id"]
    pair_key = canonical_compound_pair_key(a_id, b_id)

    def contradictory_response(*, system, user, fallback):
        return {
            "status": "ok",
            "executive_summary": (
                "No pair has a confirmed natural co-occurrence source; only Compound A + Compound B "
                "has shared food sources. All pairs are assigned high assay priority."
            ),
            "key_findings": ["All assays are available."],
            "scenario_interpretation": "The candidates are field-ready with confirmed efficacy.",
            "ai_source": "deepseek",
            "ai_status": "generated",
        }

    monkeypatch.setattr(interpreter.llm, "complete_json", contradictory_response)
    recommendations = [
        {
            "id": "r1",
            "compound_a": "Compound A",
            "compound_b": "Compound B",
            "compound_a_canonical_id": a_id,
            "compound_b_canonical_id": b_id,
            "canonical_pair_key": pair_key,
            "target": "EPSP synthase",
            "target_family": "EPSPS",
            "stage": "Seedling emergence",
            "evidence_strength": "Strong review lead",
            "validation_note": "Validate experimentally.",
        },
        {
            "id": "r2",
            "compound_a": "Compound B",
            "compound_b": "Compound A",
            "compound_a_canonical_id": b_id,
            "compound_b_canonical_id": a_id,
            "canonical_pair_key": pair_key,
            "target": "alpha-amylase",
            "target_family": "amylase",
            "stage": "Germination",
            "evidence_strength": "Exploratory lead",
            "validation_note": "Validate experimentally.",
        },
    ]
    e1 = _evidence("EPSP synthase", shared=True)
    e2 = _evidence("alpha-amylase", shared=True)
    e2["assay_prioritization"] = {"status": "not_available"}
    pair_food = {
        pair_key: {
            "context": {
                "shared_food_count": 1,
                "shared_sources": [{"food_name": "Olive", "source_confidence": 0.9}],
            },
            "compound_a_detail": {
                "canonical_compound_id": a_id,
                "match": {"match_status": "matched", "match_method": "inchikey_exact", "match_confidence": 1.0, "fooddb_compound_id": 1, "fooddb_compound_name": "Compound A"},
                "sources": [{"pesi_compound_canonical_id": a_id, "food_name": "Olive"}],
            },
            "compound_b_detail": {
                "canonical_compound_id": b_id,
                "match": {"match_status": "matched", "match_method": "exact_synonym", "match_confidence": 0.9, "fooddb_compound_id": 2, "fooddb_compound_name": "Compound B"},
                "sources": [{"pesi_compound_canonical_id": b_id, "food_name": "Olive"}],
            },
        }
    }
    report = interpreter.aggregate(
        scenario={"crop": "Zea mays", "weed": "Amaranthus palmeri", "growth_stage": "seedling_emergence"},
        recommendations=recommendations,
        targets=[],
        evidence_by_recommendation={"r1": e1, "r2": e2},
        target_reasoning=[],
        pair_food_details=pair_food,
        report_type="full",
        caveats=["Computational screening candidate only."],
        food_mapping={"status": "completed"},
    )
    assert report["semantic_validation"]["status"] == "corrected"
    assert "shared_food_occurrence_contradiction" in report["semantic_validation"]["corrections"]
    assert "assay_coverage_overstatement" in report["semantic_validation"]["corrections"]
    assert "food_source_usability_overstatement" in report["semantic_validation"]["corrections"]
    assert "practical_validation_overstatement" in report["semantic_validation"]["corrections"]
    assert "field-ready" not in report["executive_summary"]["scenario_interpretation"].casefold()
    assert report["interpretation_mode"]["source"] == "deepseek"
    assert "deterministically corrected" in report["interpretation_mode"]["label"]
