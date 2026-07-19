from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pesi.api.config import ApiSettings
from pesi.api.schemas import RunRequest, ScenarioPayload
from pesi.api.services.artifact_reader import ArtifactReader
from pesi.api.services.evidence_path_service import EvidencePathService
from pesi.api.services.job_runner import JobStore, get_job_runner, get_job_store
from pesi.api.services.llm_client import DeepSeekClient
from pesi.api.services.report_interpreter import ReportInterpreter
from pesi.api.services.json_safe import to_json_safe
from pesi.domain.compound_rules import canonicalize_compound_pair, canonicalize_text_key
from pesi.domain.enzyme_identity import resolve_enzyme_identity
from pesi.domain.compound_identity import canonical_compound_identity, canonical_compound_pair_key
from pesi.domain.herbicide_targets import match_herbicide_targets

CAVEATS = [
    "Computational screening candidate only.",
    "Not validated for field use.",
    "Not a formulation, dose, safety, or application recommendation.",
    "Requires enzyme assays, crop/weed response testing, toxicity review, and environmental validation.",
]

GROWTH_STAGES = [
    {"value": "germination", "label": "Germination"},
    {"value": "seedling_emergence", "label": "Seedling emergence"},
    {"value": "early_vegetative", "label": "Early vegetative growth"},
    {"value": "vegetative_expansion", "label": "Vegetative expansion"},
    {"value": "specialized_metabolism", "label": "Specialized metabolism"},
    {"value": "stress_response", "label": "Stress response"},
]

ANALYSIS_GOALS = [
    {"value": "candidate_pairs", "label": "Find candidate compound pairs", "description": "Prioritize enzyme targets and compound pairs for research review."},
    {"value": "target_review", "label": "Review enzyme targets", "description": "Focus on target enzymes and biological rationale first."},
    {"value": "scenario_report", "label": "Prepare report", "description": "Build a readable research summary from the latest outputs."},
]

EXAMPLE_SCENARIOS = [
    {"crop": "Zea mays", "weed": "Amaranthus palmeri", "stage": "seedling_emergence"},
    {"crop": "Oryza sativa", "weed": "Echinochloa crus-galli", "stage": "early_vegetative"},
    {"crop": "Glycine max", "weed": "Ambrosia artemisiifolia", "stage": "germination"},
]

CLASS_LABELS = {
    "organophosphonate_transition_state_mimic": "phosphonate-like transition-state mimic",
    "phenolic_acid_or_benzoate": "phenolic acid / benzoate-like compound",
    "organosulfur_sulfonate": "organosulfur / sulfonate-like compound",
    "flavonoid_polyphenol": "flavonoid / polyphenol-like compound",
    "quinone_redox_candidate": "quinone-like redox-active compound",
    "terpenoid_lipophilic": "terpenoid / lipophilic compound",
    "alkaloid_nitrogenous": "alkaloid / nitrogen-containing compound",
    "glycoside_or_sugar_conjugate": "glycoside / sugar-conjugate",
    "organic_acid_or_lactone": "organic acid / lactone-like compound",
    "unclassified_or_unknown": "unclassified screening compound",
}

TOKEN_LABELS = {
    "active_site_compatibility": "active-site fit",
    "functional_group_match": "functional-group match",
    "herbicide_target_atlas_match": "known target-class support",
    "known_inhibitor_class_similarity": "similarity to known inhibitor classes",
    "transition_state_mimicry": "transition-state mimic pattern",
    "known_inhibitor_like": "known-inhibitor-like signal",
    "transition_state_mimic_candidate": "transition-state mimic candidate",
    "phenolic_or_aromatic_hydroxyl": "phenolic/aromatic hydroxyl group",
    "transition_state_acidic_mimic": "acidic transition-state mimic group",
    "model_inference_with_real_compound_and_target_rule_evidence": "artifact-backed model inference",
    "real_evidence_plus_model_inference": "evidence-backed model inference",
    "contextual_model_inference_requires_crop_weed_assay_validation": "scenario model output requiring assay validation",
    "core_transition_anchor_plus_atlas_match": "growth-stage target evidence plus known target-class support",
    "not_high_confidence": "exploratory target signal",
}


def now_id(prefix: str = "analysis") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_text(value: Any, fallback: str = "Not listed") -> str:
    if value is None:
        return fallback
    try:
        if value != value:  # NaN
            return fallback
    except Exception:
        pass
    text = str(value).strip()
    return text if text else fallback


def score(value: Any, digits: int = 2) -> float | None:
    try:
        number = float(value)
        if not math.isfinite(number):
            return None
        return round(number, digits)
    except Exception:
        return None


def human_stage(value: Any) -> str:
    raw = safe_text(value, "Not listed")
    for stage in GROWTH_STAGES:
        if stage["value"] == raw:
            return stage["label"]
    return raw.replace("_", " ").title()


def readable_token(value: Any) -> str:
    raw = safe_text(value, "")
    if not raw:
        return "not listed"
    if raw in TOKEN_LABELS:
        return TOKEN_LABELS[raw]
    return re.sub(r"\s+", " ", raw.replace("||", " + ").replace(";", ", ").replace("_", " ")).strip()


def readable_list(value: Any, limit: int = 4) -> list[str]:
    if value is None:
        return []
    parts = [readable_token(p.strip()) for p in re.split(r"[;|]+", str(value)) if p.strip()]
    return [p for p in parts if p and p != "not listed"][:limit]


def chemical_class(value: Any) -> str:
    raw = safe_text(value, "")
    if not raw:
        return "chemical class not listed"
    return " + ".join(CLASS_LABELS.get(p, readable_token(p)) for p in raw.split("||") if p)


def evidence_strength(row: dict[str, Any]) -> str:
    obj = score(row.get("optimization_objective"), 3) or 0
    suitability = score(row.get("intervention_suitability_score"), 3) or 0
    synergy = score(row.get("synergy_group_score"), 3) or 0
    known = bool(row.get("known_inhibitor_classes")) or "known" in safe_text(row.get("compound_priority_class"), "").lower()
    if obj >= 0.59 and suitability >= 0.50 and synergy >= 0.88 and known:
        return "Strong review lead"
    if obj >= 0.54 and suitability >= 0.42:
        return "Moderate review lead"
    return "Exploratory lead"


def target_priority(row: dict[str, Any]) -> str:
    high = bool(row.get("high_confidence_known_target_label"))
    ct = score(row.get("critical_transition_score"), 3) or 0
    if high or ct >= 0.58:
        return "High interest"
    if ct >= 0.50:
        return "Medium interest"
    return "Exploratory"


def strip_internal(value: Any) -> str:
    text = safe_text(value, "")
    text = re.sub(r"Aim\s*\d+", "screening", text, flags=re.I)
    text = re.sub(r"\b\d+\s*/\s*\d+\s*gates?\b", "quality checks", text, flags=re.I)
    text = re.sub(r"Production gate status[^.]+\. ?", "", text, flags=re.I)
    text = re.sub(r"portfolio contains[^.]+\. ?", "", text, flags=re.I)
    text = text.replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


class InferenceAdapter:
    def __init__(self, settings: ApiSettings):
        self.settings = settings
        self.reader = ArtifactReader(settings)
        self.store: JobStore = get_job_store(settings)
        self.llm = DeepSeekClient(settings)
        self.evidence = EvidencePathService(settings)
        self.report_interpreter = ReportInterpreter(settings)

    def options(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "growth_stages": GROWTH_STAGES,
            "analysis_goals": ANALYSIS_GOALS,
            "example_scenarios": EXAMPLE_SCENARIOS,
            "defaults": {
                "crop": "Zea mays",
                "weed": "Amaranthus palmeri",
                "growth_stage": "seedling_emergence",
                "goal": "candidate_pairs",
                "profile": "audit",
            },
            "capabilities": {
                "food_source_context": self.reader.read_json("food-source-report").get("status") not in {"missing", "error"},
                "recommendation_evidence_paths": True,
                "enzyme_state_reasoning": True,
                "assay_prioritization_simulation": True,
                "ai_explanations": self.llm.enabled,
            },
            "ai_configuration": self.llm.configuration_status(),
        }

    def start_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        scenario = payload.get("scenario") or {}
        crop_taxa = scenario.get("crop_taxa") if isinstance(scenario.get("crop_taxa"), list) else []
        weed_taxa = scenario.get("weed_taxa") if isinstance(scenario.get("weed_taxa"), list) else []
        crop = safe_text(scenario.get("crop") or (crop_taxa[0] if crop_taxa else ""), "")
        weed = safe_text(scenario.get("weed") or (weed_taxa[0] if weed_taxa else ""), "")
        stage = safe_text(scenario.get("growth_stage"), "seedling_emergence")
        goal = safe_text(payload.get("analysis_goal"), "candidate_pairs")
        analysis_id = now_id()
        out_dir = f".pesi_runs/inference/{analysis_id}/outputs"
        artifact_dir = f".pesi_runs/inference/{analysis_id}/artifacts"
        run_request = RunRequest(
            profile=payload.get("profile", "audit"),
            sabio_mode=payload.get("sabio_mode", "cache"),
            raw_dir=payload.get("raw_dir", "raw"),
            out_dir=payload.get("out_dir") or out_dir,
            artifact_dir=payload.get("artifact_dir") or artifact_dir,
            scenario=ScenarioPayload(crop_taxa=[crop] if crop else [], weed_taxa=[weed] if weed else [], growth_stage=stage),
            run_benchmark=bool(payload.get("run_benchmark", True)),
        )
        record = get_job_runner(self.settings).launch(run_request)
        meta_path = self.settings.safe_path(self.settings.job_dir) / record.run_id / "analysis_meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps({"analysis_id": analysis_id, "analysis_goal": goal, "scenario": {"crop": crop, "weed": weed, "growth_stage": stage}}, indent=2), encoding="utf-8")
        return {
            "status": "accepted",
            "analysis_id": analysis_id,
            "run": record.model_dump(mode="json"),
            "progress_url": f"/api/v1/inference/analyses/{record.run_id}/progress",
            "results_url": f"/api/v1/inference/results?run_id={record.run_id}",
        }

    def _record_dirs(self, run_id: str | None) -> tuple[str | None, str | None, dict[str, Any] | None]:
        if not run_id:
            return None, None, None
        record = self.store.get(run_id)
        if not record:
            return None, None, None
        return record.output_dir, record.artifact_dir, record.model_dump(mode="json")

    def _run_meta(self, run_id: str | None) -> dict[str, Any]:
        if not run_id:
            return {}
        path = self.settings.safe_path(self.settings.job_dir) / run_id / "analysis_meta.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def progress(self, run_id: str) -> dict[str, Any]:
        record = self.store.get(run_id)
        if not record:
            return {"status": "missing", "message": "Analysis not found", "steps": []}
        log = self.store.read_log(run_id, tail=200)
        lines = "\n".join(log.get("lines", []))
        current = record.status
        step_defs = [
            ("queued", "Preparing analysis", "Checking the requested crop, weed, growth stage, and input folders."),
            ("evidence", "Reading evidence resources", "Loading plant-enzyme, compound, pathway, and reference evidence."),
            ("targets", "Finding enzyme targets", "Prioritizing enzymes that may matter in the selected biological context."),
            ("pairs", "Screening compound pairs", "Ranking candidate compound pairs for review."),
            ("quality", "Checking result quality", "Confirming that outputs are usable for interpretation."),
            ("ready", "Preparing results", "Packaging recommendations, target notes, and report inputs."),
        ]
        markers = {
            "evidence": ["loading resources", "resources loaded", "source tables"],
            "targets": ["critical transition", "ranking critical", "signatures"],
            "pairs": ["optimizing interventions", "optimization done"],
            "quality": ["benchmark", "gate", "PESI production run complete"],
            "ready": ["completed successfully", "PESI run"],
        }
        lower = lines.lower()
        steps = []
        for key, label, description in step_defs:
            if current == "succeeded":
                state = "complete"
            elif current == "failed":
                state = "error" if key in {"quality", "ready"} else "complete"
            elif key == "queued" and current in {"queued", "running"}:
                state = "complete" if current == "running" else "current"
            elif any(m in lower for m in markers.get(key, [])):
                state = "complete"
            else:
                previous_complete = bool(steps and steps[-1]["state"] == "complete")
                state = "current" if previous_complete and current == "running" and not any(s["state"] == "current" for s in steps) else "pending"
            steps.append({"key": key, "label": label, "description": description, "state": state})
        if current == "running" and not any(s["state"] == "current" for s in steps):
            for s in steps:
                if s["state"] == "pending":
                    s["state"] = "current"
                    break
        return {
            "status": current,
            "run_id": run_id,
            "message": self._friendly_status_message(current),
            "steps": steps,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "error": record.error,
            "technical_log_available": log.get("status") == "ok",
        }

    def _friendly_status_message(self, status: str) -> str:
        return {
            "queued": "The analysis is queued and will start shortly.",
            "running": "The analysis is running. Results will appear when screening finishes.",
            "succeeded": "Results are ready for review.",
            "failed": "The analysis stopped before results were ready. Check diagnostics for the technical error.",
            "cancelled": "The analysis was cancelled.",
        }.get(status, "Analysis status is unknown.")

    def _select_recommendation(self, results: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = results.get("recommendations", [])
        if payload.get("row_index") is not None:
            try:
                selected = next((r for r in rows if r.get("row_index") == int(payload["row_index"])), None)
                if selected:
                    return selected
            except (TypeError, ValueError):
                pass
        if payload.get("recommendation_id"):
            selected = next((r for r in rows if r.get("id") == payload.get("recommendation_id")), None)
            if selected:
                return selected
        return rows[0] if rows else None

    def _select_target(self, results: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = results.get("targets", [])
        if payload.get("row_index") is not None:
            try:
                selected = next((r for r in rows if r.get("row_index") == int(payload["row_index"])), None)
                if selected:
                    return selected
            except (TypeError, ValueError):
                pass
        if payload.get("target_id"):
            selected = next((r for r in rows if r.get("id") == payload.get("target_id")), None)
            if selected:
                return selected
        return rows[0] if rows else None

    @staticmethod
    def _food_summary(row: dict[str, Any]) -> dict[str, Any]:
        import json as _json

        def parse(value: Any) -> list[dict[str, Any]]:
            try:
                parsed = _json.loads(str(value)) if value not in {None, "", "nan"} else []
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []

        shared = parse(row.get("shared_foods_json"))
        a_sources = parse(row.get("compound_a_sources_json"))
        b_sources = parse(row.get("compound_b_sources_json"))
        return {
            "status": row.get("source_context_status") or "not_available",
            "shared_food_count": int(row.get("shared_food_count") or 0),
            "shared_quantified_food_count": int(row.get("shared_quantified_food_count") or 0),
            "shared_source_confidence": score(row.get("shared_source_confidence"), 3),
            "top_shared_sources": [safe_text(x.get("food_name")) for x in shared[:3] if x.get("food_name")],
            "compound_a_top_sources": [safe_text(x.get("food_name")) for x in a_sources[:3] if x.get("food_name")],
            "compound_b_top_sources": [safe_text(x.get("food_name")) for x in b_sources[:3] if x.get("food_name")],
            "evidence_class": row.get("evidence_class"),
            "caveat": row.get("mapping_caveat") or "Food occurrence is context only and does not establish extractability, dose, efficacy, or field-use suitability.",
        }

    def results(self, run_id: str | None = None, limit: int = 40) -> dict[str, Any]:
        out_dir, artifact_dir, run = self._record_dirs(run_id)
        meta = self._run_meta(run_id)
        aim4 = self.reader.read_table("aim4", out_dir, limit=limit, sort_by="optimization_objective")
        aim3 = self.reader.read_table("aim3", out_dir, limit=limit, sort_by="critical_transition_score")
        scenario = self.reader.read_table("scenario-selectivity", out_dir, limit=12, sort_by="scenario_selectivity_margin")
        synergy = self.reader.read_table("synergy", out_dir, limit=12, sort_by="synergy_group_score")
        food_context = self.reader.read_table("pair-food-context", out_dir, limit=1000)
        food_by_pair: dict[str, dict[str, Any]] = {}
        for row in food_context.get("rows", []):
            key = safe_text(row.get("pair_key"), "")
            if not key:
                key = canonical_compound_pair_key(
                    row.get("compound_a_canonical_id") or row.get("compound_a"),
                    row.get("compound_b_canonical_id") or row.get("compound_b"),
                    compound_a_name=row.get("compound_a"),
                    compound_b_name=row.get("compound_b"),
                )
            food_by_pair[key] = self._food_summary(row)
        recommendations = []
        for i, row in enumerate(aim4.get("rows", [])):
            card = self.recommendation_card(row, i)
            pair_key = card["canonical_pair_key"]
            card["natural_source_summary"] = food_by_pair.get(pair_key, {
                "status": "not_available", "shared_food_count": 0, "top_shared_sources": [],
                "compound_a_top_sources": [], "compound_b_top_sources": [],
                "caveat": "Food occurrence is context only and does not establish extractability, dose, efficacy, or field-use suitability.",
            })
            card["evidence_path_available"] = True
            recommendations.append(card)
        targets = []
        seen_target_contexts: set[tuple[str, str]] = set()
        for i, row in enumerate(aim3.get("rows", [])):
            card = self.target_card(row, i)
            key = (str(card.get("canonical_id")), str(card.get("stage")))
            if key in seen_target_contexts:
                continue
            seen_target_contexts.add(key)
            targets.append(card)
        for target in targets:
            target["state_reasoning_available"] = True
        scenario_notes = self.scenario_notes(meta.get("scenario") or {}, scenario.get("rows", []), recommendations, targets)
        food_report = self.reader.read_json("food-source-report", out_dir)
        return {
            "status": "ok" if recommendations or targets else "missing",
            "run": run,
            "scenario": meta.get("scenario") or {},
            "recommendations": recommendations,
            "targets": targets,
            "scenario_notes": scenario_notes,
            "synergy_notes": [self.synergy_note(r, i) for i, r in enumerate(synergy.get("rows", []))],
            "food_source_mapping": {
                "status": food_report.get("status", "missing"),
                "recommended_match_coverage": food_report.get("recommended_match_coverage"),
                "pairs_with_shared_sources": food_report.get("pairs_with_shared_sources", 0),
                "caveat": food_report.get("caveat"),
            },
            "filters": {
                "targets": sorted({r["target"] for r in recommendations if r.get("target")}),
                "target_families": sorted({r["target_family"] for r in recommendations if r.get("target_family")}),
                "stages": sorted({r["stage"] for r in recommendations if r.get("stage")}),
                "evidence_strength": sorted({r["evidence_strength"] for r in recommendations if r.get("evidence_strength")}),
                "chemical_classes": sorted({r["chemical_class"] for r in recommendations if r.get("chemical_class")}),
            },
            "caveats": CAVEATS,
        }

    def recommendation_card(self, row: dict[str, Any], index: int) -> dict[str, Any]:
        target_reported = safe_text(row.get("target_enzyme"), "Unlisted target")
        family_reported = safe_text(row.get("target_family"), "Family not listed")
        identity = resolve_enzyme_identity(target_reported, family_reported, source=row.get("source_evidence"))
        target = safe_text(identity.get("canonical_name"), target_reported)
        family = safe_text(identity.get("canonical_family"), family_reported)
        stage = human_stage(row.get("stage"))
        a_item = {
            "name": safe_text(row.get("compound_a"), "Compound A"),
            "canonical_id": safe_text(
                row.get("compound_a_canonical_id"),
                canonical_compound_identity(
                    name=row.get("compound_a"),
                    canonical_smiles=row.get("compound_a_canonical_smiles"),
                    inchikey=row.get("compound_a_inchikey"),
                    source_resource=row.get("compound_a_source"),
                )["canonical_compound_id"],
            ),
            "inchikey": row.get("compound_a_inchikey"),
            "canonical_smiles": row.get("compound_a_canonical_smiles"),
            "identity_level": row.get("compound_a_identity_level"),
            "structure_backed": row.get("compound_a_structure_backed"),
        }
        b_item = {
            "name": safe_text(row.get("compound_b"), "Compound B"),
            "canonical_id": safe_text(
                row.get("compound_b_canonical_id"),
                canonical_compound_identity(
                    name=row.get("compound_b"),
                    canonical_smiles=row.get("compound_b_canonical_smiles"),
                    inchikey=row.get("compound_b_inchikey"),
                    source_resource=row.get("compound_b_source"),
                )["canonical_compound_id"],
            ),
            "inchikey": row.get("compound_b_inchikey"),
            "canonical_smiles": row.get("compound_b_canonical_smiles"),
            "identity_level": row.get("compound_b_identity_level"),
            "structure_backed": row.get("compound_b_structure_backed"),
        }
        ordered = sorted([a_item, b_item], key=lambda item: str(item["canonical_id"]))
        a_item, b_item = ordered[0], ordered[1]
        a, b = a_item["name"], b_item["name"]
        pair_key = safe_text(
            row.get("canonical_pair_key"),
            canonical_compound_pair_key(a_item["canonical_id"], b_item["canonical_id"]),
        )
        features = readable_list(row.get("synergy_match_schema") or row.get("match_schema"), 4)
        atlas = match_herbicide_targets(target, family, row.get("stage"))
        known = readable_list(atlas.get("known_inhibitor_classes"), 3) if atlas.get("target_match_status") in {"validated", "validated_target"} else []
        strength = evidence_strength(row)
        selectivity_scope = safe_text(row.get("selectivity_scope"), "scenario_level")
        selectivity_scope_label = safe_text(
            row.get("selectivity_scope_label"),
            "Scenario-level baseline applied to this target context",
        )
        return {
            "row_index": index,
            "id": f"rec-{index}-{uuid.uuid5(uuid.NAMESPACE_URL, str(identity.get('canonical_id')) + pair_key + stage).hex[:10]}",
            "target": target,
            "target_reported": target_reported,
            "target_canonical_id": identity.get("canonical_id"),
            "target_family": family,
            "target_family_reported": family_reported,
            "enzyme_identity": identity,
            "target_atlas_validation": atlas,
            "stage": stage,
            "selectivity_scope": selectivity_scope,
            "selectivity_scope_label": selectivity_scope_label,
            "compound_a": a,
            "compound_b": b,
            "compound_a_canonical_id": a_item["canonical_id"],
            "compound_b_canonical_id": b_item["canonical_id"],
            "compound_a_inchikey": a_item.get("inchikey"),
            "compound_b_inchikey": b_item.get("inchikey"),
            "compound_a_canonical_smiles": a_item.get("canonical_smiles"),
            "compound_b_canonical_smiles": b_item.get("canonical_smiles"),
            "compound_a_identity_level": a_item.get("identity_level"),
            "compound_b_identity_level": b_item.get("identity_level"),
            "compound_a_structure_backed": a_item.get("structure_backed"),
            "compound_b_structure_backed": b_item.get("structure_backed"),
            "compound_pair": [a, b],
            "canonical_pair_key": pair_key,
            "canonical_pair_label": f"{a} + {b}",
            "chemical_class": chemical_class(row.get("phytochemical_class_pair")),
            "evidence_strength": strength,
            "short_reason": f"Review this pair as a candidate for {target} during {stage.lower()}.",
            "why_selected": f"PESI grouped this pair because it combines {chemical_class(row.get('phytochemical_class_pair'))} evidence with {', '.join(features) if features else 'screening support from the artifact set'}.",
            "biology_note": (
                f"Canonical target identity: {target} ({family}). "
                + (("Validated target-atlas inhibitor-class context includes " + ", ".join(known) + ".") if known else "No target-specific inhibitor-class claim is made for this context.")
            ),
            "pairing_note": f"The pairing is a computational hypothesis for follow-up screening; it is not measured wet-lab synergy.",
            "validation_note": "Confirm enzyme inhibition, crop/weed response, toxicity, and environmental behavior before any practical use.",
            "risk_level": "Validation required",
            "model_screening_rank": strength,
            "evidence_adjusted_priority": row.get("evidence_adjusted_priority") or "Not evaluated in this artifact",
            "evidence_adjusted_priority_code": row.get("evidence_adjusted_priority_code"),
            "evidence_adjusted_priority_score": score(row.get("evidence_adjusted_priority_score"), 3),
            "scientific_priority_gating_reasons": readable_list(row.get("scientific_priority_gating_reasons"), 8),
            "raw_scores": {
                "review_fit": score(row.get("optimization_objective"), 3),
                "candidate_fit": score(row.get("intervention_suitability_score"), 3),
                "pairing_support": score(row.get("synergy_group_score"), 3),
                "crop_impact_proxy": score(row.get("crop_impact_estimate"), 3),
                "toxicity_proxy": score(row.get("toxicity_hazard_proxy"), 3),
            },
        }

    def target_card(self, row: dict[str, Any], index: int) -> dict[str, Any]:
        target_reported = safe_text(row.get("enzyme_name_reported") or row.get("enzyme_name") or row.get("target_enzyme"), "Unlisted target")
        family_reported = safe_text(row.get("enzyme_family_reported") or row.get("enzyme_family") or row.get("target_family"), "Family not listed")
        identity = resolve_enzyme_identity(target_reported, family_reported, source=row.get("source_evidence"))
        target = safe_text(identity.get("canonical_name"), target_reported)
        family = safe_text(identity.get("canonical_family"), family_reported)
        stage = human_stage(row.get("stage_assigned") or row.get("stage"))
        atlas = match_herbicide_targets(target, family, row.get("stage_assigned") or row.get("stage"))
        known = readable_list(atlas.get("known_inhibitor_classes"), 3) if atlas.get("target_match_status") in {"validated", "validated_target"} else []
        selectivity_scope = safe_text(row.get("selectivity_scope"), "scenario_level")
        selectivity_scope_label = safe_text(
            row.get("selectivity_scope_label"),
            "Scenario-level baseline applied to this target context",
        )
        priority = target_priority(row)
        if atlas.get("target_match_status") in {"validated", "validated_target"}:
            biology_note = f"Validated target-specific site-of-action context: {atlas.get('herbicide_site_of_action')}."
        elif atlas.get("target_match_status") == "family_context":
            biology_note = "Broad family/process context only; no target-specific site-of-action claim is made."
        else:
            biology_note = "No target-specific target-atlas mapping was validated."
        return {
            "row_index": index,
            "id": f"target-{index}-{uuid.uuid5(uuid.NAMESPACE_URL, str(identity.get('canonical_id')) + stage).hex[:10]}",
            "name": target,
            "name_reported": target_reported,
            "canonical_id": identity.get("canonical_id"),
            "family": family,
            "family_reported": family_reported,
            "enzyme_identity": identity,
            "target_atlas_validation": atlas,
            "stage": stage,
            "selectivity_scope": selectivity_scope,
            "selectivity_scope_label": selectivity_scope_label,
            "priority": priority,
            "reason": f"This canonical target context appears in the computational review list for {stage.lower()}.",
            "biology_note": biology_note,
            "support_note": f"Validated inhibitor-class context: {', '.join(known)}." if known else "Treat as exploratory until target-specific validation is available.",
            "validation_note": "Validate target effect, crop tolerance, toxicity, and environmental behavior before any practical claim.",
            "raw_scores": {"target_priority": score(row.get("critical_transition_score"), 3)},
        }

    def scenario_notes(self, scenario: dict[str, Any], rows: list[dict[str, Any]], recommendations: list[dict[str, Any]], targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        crop = safe_text(scenario.get("crop"), "selected crop")
        weed = safe_text(scenario.get("weed"), "selected weed")
        stage = human_stage(scenario.get("growth_stage")) if scenario.get("growth_stage") else "selected growth stage"
        top = rows[0] if rows else {}
        top_name = safe_text(top.get("enzyme_name"), targets[0]["name"] if targets else "the leading target")
        return [
            {"title": "Scenario frame", "body": f"Interpret candidates as research hypotheses for {crop} versus {weed} at {stage.lower()}."},
            {"title": "Primary biological signal", "body": f"The current evidence places {top_name} near the front of the scenario review list."},
            {"title": "Candidate review", "body": f"{len(recommendations)} candidate pairs are available in this view. Start with the strongest leads, then compare target family, growth stage, and validation burden."},
            {"title": "Boundary", "body": "Scenario outputs guide screening priority only. Crop-safety and weed-response differences must be measured experimentally."},
        ]

    def synergy_note(self, row: dict[str, Any], index: int) -> dict[str, Any]:
        members = [safe_text(p) for p in str(row.get("members", "")).split(";") if p.strip()]
        return {
            "row_index": index,
            "target": safe_text(row.get("target_enzyme")),
            "stage": human_stage(row.get("stage")),
            "members": members,
            "evidence_strength": "Strong pairing signal" if (score(row.get("synergy_group_score"), 3) or 0) >= 0.9 else "Moderate pairing signal",
            "note": f"This group is based on {', '.join(readable_list(row.get('match_schema'), 4)) or 'typed inhibition evidence'} and requires assay validation.",
        }

    def recommendation_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = payload.get("run_id")
        out_dir, artifact_dir, _run = self._record_dirs(run_id)
        results = self.results(run_id=run_id, limit=200)
        chosen = self._select_recommendation(results, payload)
        if not chosen:
            return {"status": "missing", "message": "No recommendation was available.", "caveats": CAVEATS}
        return self.evidence.recommendation_path(
            chosen,
            out_dir=out_dir,
            artifact_dir=artifact_dir,
            scenario=results.get("scenario") or {},
        )

    def target_state_reasoning(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = payload.get("run_id")
        out_dir, _artifact_dir, _run = self._record_dirs(run_id)
        results = self.results(run_id=run_id, limit=200)
        chosen = self._select_target(results, payload)
        if not chosen:
            return {"status": "missing", "message": "No target was available.", "caveats": CAVEATS}
        return self.evidence.target_state_reasoning(chosen, out_dir=out_dir)

    def compound_food_sources(
        self,
        compound: str,
        run_id: str | None = None,
        limit: int = 20,
        canonical_compound_id: str | None = None,
    ) -> dict[str, Any]:
        out_dir, _artifact_dir, _run = self._record_dirs(run_id)
        return self.evidence.compound_food_sources(
            compound, out_dir=out_dir, limit=limit, canonical_compound_id=canonical_compound_id
        )

    def pair_food_context(
        self,
        compound_a: str,
        compound_b: str,
        run_id: str | None = None,
        compound_a_canonical_id: str | None = None,
        compound_b_canonical_id: str | None = None,
    ) -> dict[str, Any]:
        out_dir, _artifact_dir, _run = self._record_dirs(run_id)
        return self.evidence.pair_food_context(
            compound_a,
            compound_b,
            out_dir=out_dir,
            compound_a_canonical_id=compound_a_canonical_id,
            compound_b_canonical_id=compound_b_canonical_id,
        )

    def explain_recommendation(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = payload.get("run_id")
        results = self.results(run_id=run_id, limit=100)
        chosen = self._select_recommendation(results, payload)
        if not chosen:
            return {"status": "missing", "message": "No recommendation was available to explain.", "caveats": CAVEATS}
        evidence = self.recommendation_evidence({**payload, "recommendation_id": chosen.get("id")})
        fallback = self._recommendation_explanation(chosen, evidence, ai_source="deterministic_fallback")
        system = self._system_prompt()
        user = json.dumps(to_json_safe({
            "task": "Explain one PESI recommendation for a researcher without backend jargon.",
            "recommendation": chosen,
            "evidence_path": evidence,
            "scenario": results.get("scenario"),
            "required_caveats": CAVEATS,
        }), indent=2, allow_nan=False)
        response = self.llm.complete_json(system=system, user=user, fallback=fallback)
        if isinstance(response, dict):
            response["evidence_path"] = evidence
        return response

    def explain_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = payload.get("run_id")
        results = self.results(run_id=run_id, limit=100)
        chosen = self._select_target(results, payload)
        if not chosen:
            return {"status": "missing", "message": "No target was available to explain.", "caveats": CAVEATS}
        state_reasoning = self.target_state_reasoning({**payload, "target_id": chosen.get("id")})
        fallback = self._target_explanation(chosen, state_reasoning, ai_source="deterministic_fallback")
        system = self._system_prompt()
        user = json.dumps(to_json_safe({
            "task": "Explain one PESI target insight for a researcher without backend jargon.",
            "target": chosen,
            "enzyme_state_reasoning": state_reasoning,
            "scenario": results.get("scenario"),
            "required_caveats": CAVEATS,
        }), indent=2, allow_nan=False)
        response = self.llm.complete_json(system=system, user=user, fallback=fallback)
        if isinstance(response, dict):
            response["enzyme_state_reasoning"] = state_reasoning
        return response

    def _system_prompt(self) -> str:
        return (
            "You explain PESI computational plant-enzyme screening results. "
            "Use only the JSON artifact supplied by the user. Do not invent efficacy, dosage, formulation, field-use, safety, or regulatory claims. "
            "Return JSON with keys: status, title, lead, sections, caveats. sections must be a list of {title, body}. "
            "Explain target-state relevance, scenario selectivity, pairing logic, natural-source context, confidence limits, and validation needs when supplied. "
            "Never imply that food occurrence means the food is usable as a treatment or formulation. "
            "Avoid terms like Aim 3, Aim 4, gates, rows, benchmark, objective score, terminal log, and backend."
        )

    def _recommendation_explanation(self, rec: dict[str, Any], evidence: dict[str, Any], ai_source: str) -> dict[str, Any]:
        state = evidence.get("enzyme_state_reasoning", {})
        scenario = evidence.get("scenario_selectivity", {})
        synergy = evidence.get("synergy_reasoning", {})
        food = evidence.get("natural_source_context", {})
        confidence = evidence.get("confidence_and_limitations", {})
        assay = evidence.get("assay_prioritization", {})
        shared = [x.get("food_name") for x in food.get("shared_sources", [])[:3] if x.get("food_name")]
        individual_a = [x.get("food_name") for x in food.get("compound_a_sources", [])[:3] if x.get("food_name")]
        individual_b = [x.get("food_name") for x in food.get("compound_b_sources", [])[:3] if x.get("food_name")]
        if shared:
            food_body = f"Both mapped compounds are reported in {', '.join(shared)}. This is occurrence context only and does not establish extractability, useful concentration, efficacy, or safety."
        elif individual_a or individual_b:
            parts = []
            if individual_a:
                parts.append(f"{rec['compound_a']} is reported in {', '.join(individual_a)}")
            if individual_b:
                parts.append(f"{rec['compound_b']} is reported in {', '.join(individual_b)}")
            food_body = "; ".join(parts) + ". No shared source was established in the mapped records. Food occurrence is contextual evidence only."
        else:
            food_body = "No FoodDB source occurrence was resolved for this pair. Absence of a match does not prove absence from foods or plants."
        assay_body = assay.get("interpretation") if assay.get("status") == "available" else "No assay-priority simulation band was available for this pair."
        return {
            "status": "ok",
            "title": f"{rec['compound_a']} + {rec['compound_b']}",
            "lead": f"This pair is a {rec['evidence_strength'].lower()} for {rec['target']} during {rec['stage'].lower()}.",
            "sections": [
                {"title": "Why this enzyme state matters", "body": state.get("why_state_matters") or rec["biology_note"]},
                {"title": "Why the scenario changes priority", "body": scenario.get("why_context_changes_priority") or "The crop, weed, and growth-stage context changes comparative screening priority."},
                {"title": "Why these compounds were grouped", "body": synergy.get("why_paired") or rec["why_selected"]},
                {"title": "Natural source context", "body": food_body},
                {"title": "Evidence confidence", "body": f"{confidence.get('overall', 'Evidence combines model inference and source records')}. The ranking explains screening priority; it does not validate efficacy or safety."},
                {"title": "Assay-prioritization simulation", "body": assay_body},
                {"title": "What must be validated", "body": rec["validation_note"]},
            ],
            "caveats": evidence.get("caveats") or CAVEATS,
            "ai_source": ai_source,
            "ai_status": "generated" if ai_source == "deepseek" else "fallback",
        }

    def _target_explanation(self, target: dict[str, Any], state: dict[str, Any], ai_source: str) -> dict[str, Any]:
        trajectory = state.get("trajectory", {})
        signals = state.get("evidence_signals", {})
        selectivity = state.get("scenario_selectivity", {})
        trajectory_body = (
            f"The modeled transition signal has a relative peak of {trajectory.get('peak')}, curvature of {trajectory.get('curvature')}, "
            f"and transition position of {trajectory.get('critical_transition_time')}. These are comparative model features, not measured enzyme kinetics."
        )
        evidence_body = (
            f"Pathway essentiality: {signals.get('pathway_essentiality')}; kinetic evidence: {signals.get('kinetic_evidence')}; "
            f"structure evidence: {signals.get('structure_evidence')}; plant-context evidence: {signals.get('plant_context')}; "
            f"uncertainty penalty: {signals.get('uncertainty_penalty')}."
        )
        difference = selectivity.get("selectivity_difference")
        if difference is None:
            difference = selectivity.get("selectivity_margin")
        selectivity_body = (
            f"The scenario layer estimates weed vulnerability at {selectivity.get('weed_vulnerability')}, crop vulnerability at {selectivity.get('crop_vulnerability')}, "
            f"and a weed-minus-crop difference of {difference}. The centered ranking index is {selectivity.get('selectivity_index')}. "
            "These are screening proxies requiring comparative assays; the index is not a biological margin."
        )
        return {
            "status": "ok",
            "title": target["name"],
            "lead": f"This enzyme is a {target['priority'].lower()} target signal in the current screening context.",
            "sections": [
                {"title": "Why this enzyme state matters", "body": state.get("why_state_matters") or target["biology_note"]},
                {"title": "Growth-stage signal", "body": trajectory_body},
                {"title": "Evidence supporting the target", "body": evidence_body},
                {"title": "Scenario selectivity", "body": selectivity_body},
                {"title": "Pathway context", "body": target["biology_note"]},
                {"title": "What must be validated", "body": target["validation_note"]},
            ],
            "caveats": CAVEATS,
            "ai_source": ai_source,
            "ai_status": "generated" if ai_source == "deepseek" else "fallback",
        }

    @staticmethod
    def _report_pair_key(recommendation: dict[str, Any]) -> str:
        existing = safe_text(recommendation.get("canonical_pair_key"), "").strip()
        if existing:
            return existing
        return canonical_compound_pair_key(
            recommendation.get("compound_a_canonical_id") or recommendation.get("compound_a"),
            recommendation.get("compound_b_canonical_id") or recommendation.get("compound_b"),
            compound_a_name=recommendation.get("compound_a"),
            compound_b_name=recommendation.get("compound_b"),
        )

    def _report_scope(self, recommendations: list[dict[str, Any]], report_type: str) -> list[dict[str, Any]]:
        """Select top unique pairs, then retain all target contexts for those pairs."""
        pair_limit = 10 if report_type == "full" else 5
        selected_keys: list[str] = []
        for recommendation in recommendations:
            key = self._report_pair_key(recommendation)
            if key not in selected_keys:
                selected_keys.append(key)
            if len(selected_keys) >= pair_limit:
                break
        selected = [recommendation for recommendation in recommendations if self._report_pair_key(recommendation) in selected_keys]
        # Keep target-specific variants for the chosen pairs, but bound report size.
        max_target_variants = 5 if report_type == "full" else 3
        counts: dict[str, int] = {}
        seen_contexts: set[tuple[str, str, str]] = set()
        output: list[dict[str, Any]] = []
        for recommendation in selected:
            key = self._report_pair_key(recommendation)
            target_id = safe_text(
                recommendation.get("target_canonical_id"),
                resolve_enzyme_identity(recommendation.get("target"), recommendation.get("target_family")).get("canonical_id"),
            )
            stage_key = canonicalize_text_key(recommendation.get("stage"))
            context_key = (key, target_id, stage_key)
            if context_key in seen_contexts or counts.get(key, 0) >= max_target_variants:
                continue
            seen_contexts.add(context_key)
            counts[key] = counts.get(key, 0) + 1
            output.append(recommendation)
        return output

    def build_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = payload.get("run_id")
        report_type = payload.get("report_type", "summary")
        results = self.results(run_id=run_id, limit=200)
        scoped_recommendations = self._report_scope(results.get("recommendations", []), report_type)

        evidence_by_recommendation: dict[str, dict[str, Any]] = {}
        pair_food_details: dict[str, dict[str, Any]] = {}
        for recommendation in scoped_recommendations:
            recommendation_id = str(recommendation.get("id") or "")
            evidence_by_recommendation[recommendation_id] = self.recommendation_evidence({
                "run_id": run_id,
                "recommendation_id": recommendation_id,
                "row_index": recommendation.get("row_index"),
            })
            pair_key = self._report_pair_key(recommendation)
            if pair_key not in pair_food_details:
                pair_food_details[pair_key] = self.pair_food_context(
                    str(recommendation.get("compound_a") or ""),
                    str(recommendation.get("compound_b") or ""),
                    run_id=run_id,
                    compound_a_canonical_id=recommendation.get("compound_a_canonical_id"),
                    compound_b_canonical_id=recommendation.get("compound_b_canonical_id"),
                )

        unique_target_ids = {
            safe_text(
                recommendation.get("target_canonical_id"),
                resolve_enzyme_identity(recommendation.get("target"), recommendation.get("target_family")).get("canonical_id"),
            )
            for recommendation in scoped_recommendations
        }
        target_cards = [
            target for target in results.get("targets", [])
            if safe_text(
                target.get("canonical_id"),
                resolve_enzyme_identity(target.get("name"), target.get("family")).get("canonical_id"),
            ) in unique_target_ids
        ]
        if not target_cards:
            target_cards = results.get("targets", [])[: (8 if report_type == "full" else 5)]
        target_reasoning = [
            self.target_state_reasoning({"run_id": run_id, "target_id": target.get("id"), "row_index": target.get("row_index")})
            for target in target_cards
        ]

        scenario = results.get("scenario") or payload.get("scenario") or {}
        report = self.report_interpreter.aggregate(
            scenario=scenario,
            recommendations=scoped_recommendations,
            targets=target_cards,
            evidence_by_recommendation=evidence_by_recommendation,
            target_reasoning=target_reasoning,
            pair_food_details=pair_food_details,
            report_type=report_type,
            caveats=CAVEATS,
            food_mapping=results.get("food_source_mapping") or {},
        )
        return to_json_safe(report)

    def build_report_html(self, payload: dict[str, Any]) -> str:
        return self.report_interpreter.render_html(self.build_report(payload))

