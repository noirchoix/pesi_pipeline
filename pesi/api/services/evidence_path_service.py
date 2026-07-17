from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from pesi.api.config import ApiSettings
from pesi.api.services.artifact_reader import ArtifactReader
from pesi.domain.herbicide_targets import HERBICIDE_TARGET_RULES, match_herbicide_targets
from pesi.etl.fooddb_loader import FOOD_SOURCE_CAVEAT


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _safe(value: Any, fallback: str = "Not available") -> str:
    if value is None:
        return fallback
    try:
        if pd.isna(value):
            return fallback
    except Exception:
        pass
    text = str(value).strip()
    return text or fallback


def _num(value: Any, digits: int = 3) -> float | None:
    try:
        out = float(value)
        return None if pd.isna(out) else round(out, digits)
    except Exception:
        return None


def _split(value: Any) -> list[str]:
    if value is None:
        return []
    return [x.strip().replace("_", " ") for x in re.split(r"[;|]+", str(value)) if x.strip()]




def _nullable(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value

def _json_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return value
    if not value or (isinstance(value, float) and pd.isna(value)):
        return []
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


class EvidencePathService:
    """Builds recommendation-level provenance from PESI outputs without inventing missing links."""

    def __init__(self, settings: ApiSettings):
        self.settings = settings
        self.reader = ArtifactReader(settings)
        self._frame_cache: dict[str, pd.DataFrame] = {}
        self._json_cache: dict[str, Any] = {}

    def _df(self, key: str, out_dir: str | Path | None) -> pd.DataFrame:
        try:
            path = self.reader.csv_path(key, out_dir)
        except KeyError:
            return pd.DataFrame()
        cache_key = str(path.resolve())
        if cache_key in self._frame_cache:
            return self._frame_cache[cache_key]
        if not path.exists():
            frame = pd.DataFrame()
        else:
            try:
                frame = pd.read_csv(path)
            except Exception:
                frame = pd.DataFrame()
        self._frame_cache[cache_key] = frame
        return frame

    def _json(self, key: str, out_dir: str | Path | None) -> Any:
        try:
            path = self.reader.json_path(key, out_dir)
        except KeyError:
            return {}
        cache_key = str(path.resolve())
        if cache_key not in self._json_cache:
            try:
                self._json_cache[cache_key] = self.reader.read_json(key, out_dir)
            except Exception:
                self._json_cache[cache_key] = {}
        return self._json_cache[cache_key]

    def _find_recommendation_row(self, rec: dict[str, Any], out_dir: str | Path | None) -> dict[str, Any]:
        df = self._df("aim4", out_dir)
        if df.empty:
            return {}
        target = _norm(rec.get("target"))
        a = _norm(rec.get("compound_a"))
        b = _norm(rec.get("compound_b"))
        for row in df.to_dict("records"):
            pair = {_norm(row.get("compound_a")), _norm(row.get("compound_b"))}
            if _norm(row.get("target_enzyme")) == target and pair == {a, b}:
                return row
        return {}

    def _target_row(self, target: str, out_dir: str | Path | None) -> dict[str, Any]:
        df = self._df("aim3", out_dir)
        if df.empty:
            return {}
        key = _norm(target)
        exact = df[df.apply(lambda r: _norm(r.get("enzyme_name") or r.get("target_enzyme")) == key, axis=1)]
        if not exact.empty:
            return exact.iloc[0].to_dict()
        contains = df[df.apply(lambda r: key in _norm(r.get("enzyme_name") or r.get("target_enzyme")) or _norm(r.get("enzyme_name") or r.get("target_enzyme")) in key, axis=1)]
        return contains.iloc[0].to_dict() if not contains.empty else {}

    def _state_row(self, target: str, out_dir: str | Path | None) -> dict[str, Any]:
        df = self._df("aim2-signatures", out_dir)
        if df.empty:
            return {}
        key = _norm(target)
        exact = df[df.apply(lambda r: _norm(r.get("enzyme_name") or r.get("enzyme_key")) == key, axis=1)]
        if not exact.empty:
            return exact.sort_values("criticality_score_formula", ascending=False).iloc[0].to_dict()
        contains = df[df.apply(lambda r: key in _norm(r.get("enzyme_name") or r.get("enzyme_key")) or _norm(r.get("enzyme_name") or r.get("enzyme_key")) in key, axis=1)]
        return contains.sort_values("criticality_score_formula", ascending=False).iloc[0].to_dict() if not contains.empty else {}

    def _scenario_row(self, target: str, out_dir: str | Path | None) -> dict[str, Any]:
        df = self._df("scenario-selectivity", out_dir)
        if df.empty:
            return {}
        key = _norm(target)
        exact = df[df.apply(lambda r: _norm(r.get("enzyme_name")) == key, axis=1)]
        return exact.iloc[0].to_dict() if not exact.empty else {}

    def _synergy_row(self, target: str, compound_a: str, compound_b: str, out_dir: str | Path | None) -> dict[str, Any]:
        df = self._df("synergy", out_dir)
        if df.empty:
            return {}
        wanted = {_norm(compound_a), _norm(compound_b)}
        target_key = _norm(target)
        for row in df.to_dict("records"):
            members = {_norm(x) for x in str(row.get("members") or "").split(";") if str(x).strip()}
            if wanted == members and _norm(row.get("target_enzyme")) == target_key:
                return row
        return {}

    def _compound_row(self, compound: str, out_dir: str | Path | None) -> dict[str, Any]:
        df = self._df("compound-pool", out_dir)
        if df.empty:
            return {}
        key = _norm(compound)
        exact = df[df.apply(lambda r: key in {_norm(r.get("compound_name")), _norm(r.get("compound_name_canonical")), _norm(r.get("compound_id"))}, axis=1)]
        return exact.iloc[0].to_dict() if not exact.empty else {}

    def _food_context(self, a: str, b: str, out_dir: str | Path | None) -> dict[str, Any]:
        df = self._df("pair-food-context", out_dir)
        pair_key = "||".join(sorted([a, b]))
        if not df.empty and "pair_key" in df.columns:
            row = df[df["pair_key"].astype(str) == pair_key]
            if row.empty:
                wanted = {_norm(a), _norm(b)}
                row = df[df.apply(lambda r: {_norm(r.get("compound_a")), _norm(r.get("compound_b"))} == wanted, axis=1)]
            if not row.empty:
                item = row.iloc[0].to_dict()
                return {
                    "status": item.get("source_context_status"),
                    "shared_food_count": int(item.get("shared_food_count") or 0),
                    "shared_quantified_food_count": int(item.get("shared_quantified_food_count") or 0),
                    "shared_source_confidence": _num(item.get("shared_source_confidence")),
                    "shared_sources": _json_list(item.get("shared_foods_json")),
                    "compound_a_sources": _json_list(item.get("compound_a_sources_json")),
                    "compound_b_sources": _json_list(item.get("compound_b_sources_json")),
                    "evidence_class": item.get("evidence_class"),
                    "caveat": FOOD_SOURCE_CAVEAT,
                }
        return {
            "status": "not_available",
            "shared_food_count": 0,
            "shared_quantified_food_count": 0,
            "shared_source_confidence": None,
            "shared_sources": [],
            "compound_a_sources": [],
            "compound_b_sources": [],
            "evidence_class": "no_fooddb_source_context",
            "caveat": FOOD_SOURCE_CAVEAT,
        }

    def _assay_priority(self, target: str, a: str, b: str, out_dir: str | Path | None) -> dict[str, Any]:
        df = self._df("pseudo-lab", out_dir)
        if df.empty:
            return {"status": "not_available", "evidence_class": "pseudo_lab_model_inference"}
        wanted = {_norm(a), _norm(b)}
        target_key = _norm(target)
        subset = df[df.apply(
            lambda r: _norm(r.get("target_enzyme")) == target_key
            and {_norm(r.get("compound_a")), _norm(r.get("compound_b"))} == wanted,
            axis=1,
        )].copy()
        if subset.empty:
            return {"status": "not_available", "evidence_class": "pseudo_lab_model_inference"}
        subset["predicted_inhibition"] = pd.to_numeric(subset["predicted_inhibition"], errors="coerce")
        subset["dose_relative"] = pd.to_numeric(subset["dose_relative"], errors="coerce")
        subset = subset.dropna(subset=["predicted_inhibition", "dose_relative"]).sort_values("dose_relative")
        if subset.empty:
            return {"status": "not_available", "evidence_class": "pseudo_lab_model_inference"}
        max_effect = float(subset["predicted_inhibition"].max())
        threshold = max_effect * 0.5
        transition = subset[subset["predicted_inhibition"] >= threshold]
        center = float(transition["dose_relative"].iloc[0]) if not transition.empty else float(subset["dose_relative"].median())
        lower = max(0.0, center * 0.6)
        upper = min(float(subset["dose_relative"].max()), center * 1.5 if center > 0 else 0.1)
        return {
            "status": "available",
            "label": "Suggested assay-priority simulation band",
            "relative_input_band": [round(lower, 3), round(upper, 3)],
            "simulated_max_inhibition": round(max_effect, 3),
            "model": _safe(subset.iloc[0].get("model"), "PESI pseudo-lab response model"),
            "interpretation": "Use this relative range only to prioritize controlled assay design; it is not a dose, formulation, or field application rate.",
            "evidence_class": "pseudo_lab_model_inference",
        }

    def _pathway_context(self, row: dict[str, Any], target_row: dict[str, Any], state_row: dict[str, Any]) -> list[dict[str, Any]]:
        match = match_herbicide_targets(
            row.get("target_enzyme") or target_row.get("enzyme_name"),
            row.get("target_family") or target_row.get("enzyme_family"),
            row.get("stage") or target_row.get("stage_assigned"),
        )
        rule = next((r for r in HERBICIDE_TARGET_RULES if r.target_family == match.get("herbicide_target_family")), None)
        contexts: list[dict[str, Any]] = []
        if rule:
            contexts.append({
                "pathway": rule.pathway.replace("_", " "),
                "site_of_action": rule.site_of_action,
                "binding_logic": rule.binding_logic.replace("_", " "),
                "known_inhibitor_classes": list(rule.known_inhibitor_classes),
                "resistance_risks": list(rule.resistance_risks),
                "source": "PESI herbicide target atlas",
                "evidence_class": rule.evidence_class,
            })
        substrate = state_row.get("substrate")
        product = state_row.get("product")
        if substrate or product:
            contexts.append({
                "pathway": "reaction context",
                "substrate": None if pd.isna(substrate) else substrate,
                "product": None if pd.isna(product) else product,
                "source": state_row.get("source_evidence"),
                "evidence_class": state_row.get("evidence_class"),
            })
        return contexts

    def recommendation_path(
        self,
        recommendation: dict[str, Any],
        out_dir: str | Path | None = None,
        artifact_dir: str | Path | None = None,
        scenario: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rec_row = self._find_recommendation_row(recommendation, out_dir)
        target = recommendation.get("target") or rec_row.get("target_enzyme")
        a = recommendation.get("compound_a") or rec_row.get("compound_a")
        b = recommendation.get("compound_b") or rec_row.get("compound_b")
        target_row = self._target_row(str(target), out_dir)
        state_row = self._state_row(str(target), out_dir)
        scenario_row = self._scenario_row(str(target), out_dir)
        synergy_row = self._synergy_row(str(target), str(a), str(b), out_dir)
        compound_a = self._compound_row(str(a), out_dir)
        compound_b = self._compound_row(str(b), out_dir)
        food = self._food_context(str(a), str(b), out_dir)
        assay = self._assay_priority(str(target), str(a), str(b), out_dir)
        pathway_context = self._pathway_context(rec_row, target_row, state_row)

        direct: list[str] = []
        model: list[str] = []
        proxies: list[str] = []
        weak: list[str] = []
        for source in [target_row.get("source_evidence"), state_row.get("source_evidence"), rec_row.get("compound_a_source"), rec_row.get("compound_b_source")]:
            if source and str(source).lower() not in {"nan", "none"}:
                direct.append(str(source))
        if food.get("shared_sources") or food.get("compound_a_sources") or food.get("compound_b_sources"):
            direct.append("FoodDB compound and food occurrence records")
        model.extend([
            "critical-transition ranking",
            "compound-pair optimization",
            "typed pairing/synergy inference",
            "scenario selectivity inference",
        ])
        proxies.extend([
            "crop-impact proxy",
            "toxicity-hazard proxy",
            "environmental-persistence proxy",
            "pseudo-lab response simulation",
        ])
        unsupported = self._json("unsupported-assumptions", out_dir)
        assumptions = unsupported if isinstance(unsupported, list) else unsupported.get("value", []) if isinstance(unsupported, dict) else []
        for item in assumptions:
            if isinstance(item, dict) and item.get("status") not in {"supported", "validated"}:
                weak.append(_safe(item.get("assumption")))

        state_reasoning = {
            "target": target,
            "growth_stage": _safe(state_row.get("stage_assigned") or target_row.get("stage_assigned") or rec_row.get("stage")),
            "target_class": _safe(state_row.get("target_class") or target_row.get("target_class")),
            "why_state_matters": (
                f"The state signature links {target} to {_safe(state_row.get('stage_assigned') or rec_row.get('stage'), 'the selected growth stage')} "
                f"and {_safe(state_row.get('target_class'), 'a pathway function under review')}."
            ),
            "stage_signal": {
                "trajectory_peak": _num(state_row.get("trajectory_peak")),
                "trajectory_curvature": _num(state_row.get("trajectory_curvature_max")),
                "critical_transition_time": _num(state_row.get("trajectory_critical_t")),
            },
            "evidence_signals": {
                "kinetic_records": _num(state_row.get("kinetic_records"), 0),
                "kinetic_evidence": _num(state_row.get("kinetic_evidence_score")),
                "structure_evidence": _num(state_row.get("structure_score")),
                "plant_context": _num(state_row.get("plant_context_score")),
                "pathway_essentiality": _num(state_row.get("pathway_essentiality_score")),
                "uncertainty_penalty": _num(state_row.get("uncertainty_penalty")),
            },
            "source": state_row.get("source_evidence"),
            "evidence_class": state_row.get("evidence_class") or "model_inference",
            "limitation": "The enzyme-state trajectory is a computational representation and requires biological validation.",
        }

        scenario_selectivity = {
            "scenario": scenario or {},
            "why_context_changes_priority": (
                "The crop, weed, and growth-stage context changes the comparative vulnerability and crop-impact penalties used to order candidates."
            ),
            "weed_vulnerability": _num(scenario_row.get("weed_vulnerability_score") or rec_row.get("weed_vulnerability_score")),
            "crop_vulnerability": _num(scenario_row.get("crop_vulnerability_score") or rec_row.get("crop_vulnerability_score")),
            "selectivity_margin": _num(scenario_row.get("scenario_selectivity_margin") or rec_row.get("scenario_selectivity_margin")),
            "stage_relevance": _safe(scenario_row.get("stage_assigned") or rec_row.get("stage")),
            "evidence_class": scenario_row.get("selectivity_evidence_class") or "contextual_model_inference",
            "limitation": "These values are comparative screening proxies, not measured crop-safety or weed-control outcomes.",
        }

        synergy = {
            "why_paired": (
                "The pair was retained because the two compound records contributed complementary inhibition-related features "
                "for the same target context."
            ),
            "functional_signals": _split(synergy_row.get("match_schema") or rec_row.get("synergy_match_schema")),
            "same_target_class": _safe(synergy_row.get("target_family") or rec_row.get("target_family")),
            "pairing_support": _num(synergy_row.get("synergy_group_score") or rec_row.get("synergy_group_score")),
            "inferred_not_measured": True,
            "evidence_class": synergy_row.get("evidence_class") or rec_row.get("synergy_evidence_class") or "model_inference",
            "limitation": "The pairing signal is inferred from typed evidence and must not be described as measured synergy.",
        }

        def compound_intelligence(row: dict[str, Any], label: str) -> dict[str, Any]:
            exclusion = row.get("compound_exclusion_reason")
            return {
                "compound": label,
                "why_allowed": "No exclusion rule was triggered." if not exclusion or str(exclusion).lower() == "nan" else f"Review note: {exclusion}",
                "why_prioritized": _safe(row.get("compound_priority_class"), "screening candidate"),
                "phytochemical_class": _safe(row.get("phytochemical_class")),
                "functional_groups": _split(row.get("functional_group_hits")),
                "natural_product_evidence": _num(row.get("natural_product_evidence_score")),
                "availability_signal": _num(row.get("availability_score")),
                "hazard_proxy": _num(row.get("hazard_proxy")),
                "persistence_proxy": _num(row.get("persistence_proxy")),
                "intervention_suitability": _num(row.get("intervention_suitability_score")),
                "source": row.get("source_resource"),
                "evidence_class": row.get("compound_rule_evidence_class") or row.get("evidence_class"),
                "limitation": "Rule-based compound intelligence is a screening aid, not a safety determination.",
            }

        path = [
            {"order": 1, "entity_type": "compound_pair", "label": f"{a} + {b}", "relationship": "screened as a candidate pair", "source": "optimized intervention artifact", "evidence_tier": "model_inference"},
            {"order": 2, "entity_type": "target_enzyme", "label": target, "relationship": "prioritized for perturbation", "source": target_row.get("source_evidence") or "critical-transition ranking", "evidence_tier": "mixed_evidence"},
            {"order": 3, "entity_type": "enzyme_family", "label": rec_row.get("target_family") or target_row.get("enzyme_family"), "relationship": "classified within target family", "source": target_row.get("source_evidence") or "curated family/target atlas", "evidence_tier": "direct_or_curated"},
            {"order": 4, "entity_type": "pathway", "label": pathway_context[0].get("pathway") if pathway_context else "Pathway not directly resolved", "relationship": "acts within pathway context", "source": pathway_context[0].get("source") if pathway_context else None, "evidence_tier": "curated_rule_or_direct"},
            {"order": 5, "entity_type": "growth_stage", "label": state_reasoning["growth_stage"], "relationship": "linked to enzyme-state transition", "source": state_reasoning.get("source") or "stage model", "evidence_tier": "mixed_evidence"},
            {"order": 6, "entity_type": "known_inhibitor_class", "label": ", ".join(_split(rec_row.get("known_inhibitor_classes"))) or "No inhibitor class directly listed", "relationship": "provides target-class context", "source": "PESI herbicide target atlas", "evidence_tier": "curated_literature_rule"},
            {"order": 7, "entity_type": "natural_source_context", "label": f"{food.get('shared_food_count', 0)} shared food-source records", "relationship": "reported occurrence context", "source": "FoodDB-derived food chemistry bundle", "evidence_tier": "direct_occurrence_or_unavailable"},
        ]

        direct = sorted(set(direct))
        overall = "mixed evidence with direct source support" if direct else "model-led evidence with limited direct source support"
        return {
            "status": "ok",
            "recommendation_id": recommendation.get("id"),
            "summary": f"Evidence path for {a} + {b} against {target}.",
            "path": path,
            "enzyme_state_reasoning": state_reasoning,
            "scenario_selectivity": scenario_selectivity,
            "synergy_reasoning": synergy,
            "compound_intelligence": {
                "compound_a": compound_intelligence(compound_a, str(a)),
                "compound_b": compound_intelligence(compound_b, str(b)),
            },
            "natural_source_context": food,
            "assay_prioritization": assay,
            "pathway_context": pathway_context,
            "confidence_and_limitations": {
                "overall": overall,
                "direct_evidence": direct,
                "model_inference": sorted(set(model)),
                "proxy_assumptions": sorted(set(proxies)),
                "weak_or_unsupported_assumptions": sorted(set(weak)),
                "scientific_boundary": "The evidence path explains why a candidate was ranked; it does not validate efficacy, safety, or field use.",
            },
            "source_artifacts": [
                "aim4_optimized_interventions.csv",
                "aim3_critical_transition_enzymes.csv",
                "enzyme_state_signatures.csv",
                "scenario_selectivity.csv",
                "aim4_inhibit_synergy_groups.csv",
                "compound_pool.csv",
                "pseudo_lab_dose_response.csv",
                "compound_fooddb_matches.csv",
                "compound_food_sources.csv",
                "pair_food_source_context.csv",
                "proxy_evidence_report.csv",
                "unsupported_assumptions.json",
            ],
            "caveats": [
                "Computational screening candidate only.",
                "Pairing and selectivity are inferred, not experimentally measured.",
                FOOD_SOURCE_CAVEAT,
                "Requires enzyme assays, crop/weed response testing, toxicity review, and environmental validation.",
            ],
        }

    def compound_food_sources(self, compound: str, out_dir: str | Path | None = None, limit: int = 20) -> dict[str, Any]:
        matches = self._df("fooddb-matches", out_dir)
        sources = self._df("food-sources", out_dir)
        key = _norm(compound)
        match_row: dict[str, Any] = {}
        if not matches.empty:
            selected = matches[matches.apply(
                lambda r: key in {_norm(r.get("pesi_compound_name")), _norm(r.get("pesi_compound_name_canonical"))},
                axis=1,
            )]
            if not selected.empty:
                match_row = selected.iloc[0].to_dict()
        source_rows: list[dict[str, Any]] = []
        if not sources.empty:
            selected_sources = sources[sources["pesi_compound_name"].astype(str).map(_norm).eq(key)].head(max(1, min(limit, 100)))
            for row in selected_sources.to_dict("records"):
                source_rows.append({
                    "food_id": _nullable(row.get("food_id")),
                    "food_public_id": _nullable(row.get("food_public_id")),
                    "food_name": _nullable(row.get("food_name")),
                    "food_name_scientific": _nullable(row.get("food_name_scientific")),
                    "food_group": _nullable(row.get("food_group")),
                    "food_subgroup": _nullable(row.get("food_subgroup")),
                    "occurrence_evidence": _nullable(row.get("occurrence_evidence")),
                    "source_confidence": _num(row.get("source_confidence")),
                    "standard_content": _num(row.get("standard_content")),
                    "orig_content": _num(row.get("orig_content")),
                    "orig_unit": _nullable(row.get("orig_unit")),
                    "citation_type": _nullable(row.get("citation_type")),
                    "evidence_class": _nullable(row.get("evidence_class")),
                })
        return {
            "status": "ok" if match_row else "unmatched",
            "compound": compound,
            "match": {
                "fooddb_compound_id": _nullable(match_row.get("fooddb_compound_id")),
                "fooddb_public_id": _nullable(match_row.get("fooddb_public_id")),
                "fooddb_compound_name": _nullable(match_row.get("fooddb_compound_name")),
                "match_method": _nullable(match_row.get("match_method")),
                "match_confidence": _num(match_row.get("match_confidence")),
                "match_status": _nullable(match_row.get("match_status")),
                "evidence_class": _nullable(match_row.get("evidence_class")),
            } if match_row else None,
            "sources": source_rows,
            "source_count_returned": len(source_rows),
            "caveat": FOOD_SOURCE_CAVEAT,
        }

    def pair_food_context(self, compound_a: str, compound_b: str, out_dir: str | Path | None = None) -> dict[str, Any]:
        return {
            "status": "ok",
            "compound_a": compound_a,
            "compound_b": compound_b,
            "context": self._food_context(compound_a, compound_b, out_dir),
            "compound_a_detail": self.compound_food_sources(compound_a, out_dir, limit=10),
            "compound_b_detail": self.compound_food_sources(compound_b, out_dir, limit=10),
        }

    def target_state_reasoning(self, target: dict[str, Any], out_dir: str | Path | None = None) -> dict[str, Any]:
        target_name = target.get("name") or target.get("target")
        target_row = self._target_row(str(target_name), out_dir)
        state = self._state_row(str(target_name), out_dir)
        scenario = self._scenario_row(str(target_name), out_dir)
        contexts = self._pathway_context({}, target_row, state)
        return {
            "status": "ok" if target_row or state else "missing",
            "target": target_name,
            "family": target.get("family") or target_row.get("enzyme_family"),
            "growth_stage": _safe(state.get("stage_assigned") or target_row.get("stage_assigned")),
            "target_class": _safe(state.get("target_class") or target_row.get("target_class")),
            "why_state_matters": f"The target is linked to {_safe(state.get('target_class'), 'a biological function under review')} during {_safe(state.get('stage_assigned') or target_row.get('stage_assigned'), 'the assigned growth stage')}.",
            "trajectory": {
                "peak": _num(state.get("trajectory_peak")),
                "curvature": _num(state.get("trajectory_curvature_max")),
                "critical_transition_time": _num(state.get("trajectory_critical_t")),
            },
            "evidence_signals": {
                "kinetic_records": _num(state.get("kinetic_records"), 0),
                "kinetic_evidence": _num(state.get("kinetic_evidence_score")),
                "structure_evidence": _num(state.get("structure_score")),
                "plant_context": _num(state.get("plant_context_score")),
                "pathway_essentiality": _num(state.get("pathway_essentiality_score")),
                "uncertainty_penalty": _num(state.get("uncertainty_penalty")),
            },
            "scenario_selectivity": {
                "weed_vulnerability": _num(scenario.get("weed_vulnerability_score")),
                "crop_vulnerability": _num(scenario.get("crop_vulnerability_score")),
                "selectivity_margin": _num(scenario.get("scenario_selectivity_margin")),
                "evidence_class": scenario.get("selectivity_evidence_class"),
            },
            "pathway_context": contexts,
            "source": state.get("source_evidence") or target_row.get("source_evidence"),
            "evidence_class": state.get("evidence_class") or target_row.get("evidence_class"),
            "limitations": [
                "Enzyme-state trajectories and scenario selectivity are computational inference layers.",
                "Target-specific biochemical and comparative crop/weed assays are required.",
            ],
        }
