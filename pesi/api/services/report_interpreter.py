from __future__ import annotations

import html
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from pesi.api.config import ApiSettings
from pesi.api.services.llm_client import DeepSeekClient


FOOD_SOURCE_CAVEAT = (
    "Food/source occurrence is contextual evidence only. It does not establish extractability, useful concentration, "
    "efficacy, crop safety, formulation suitability, or field-use readiness."
)

ARTIFACT_LABELS = {
    "aim4_optimized_interventions.csv": "Optimized compound-pair ranking",
    "aim3_critical_transition_enzymes.csv": "Critical enzyme-target ranking",
    "enzyme_state_signatures.csv": "Enzyme-state signature model",
    "scenario_selectivity.csv": "Crop-versus-weed scenario selectivity model",
    "aim4_inhibit_synergy_groups.csv": "Typed compound-pairing evidence",
    "compound_pool.csv": "Compound screening and prioritization rules",
    "pseudo_lab_dose_response.csv": "Relative assay-prioritization simulation",
    "compound_fooddb_matches.csv": "PESI-to-FoodDB compound normalization",
    "compound_food_sources.csv": "FoodDB ingredient and food occurrence records",
    "pair_food_source_context.csv": "Pair-level shared-source context",
    "proxy_evidence_report.csv": "Proxy evidence register",
    "unsupported_assumptions.json": "Unsupported-assumption register",
}

SOURCE_LABELS = {
    "PESI herbicide target atlas": "Curated herbicide target atlas",
    "FoodDB compound and food occurrence records": "FoodDB compound and food occurrence records",
    "FoodDB-derived food chemistry bundle": "FoodDB-derived food chemistry bundle",
    "critical-transition ranking": "Critical enzyme-target ranking",
    "optimized intervention artifact": "Optimized compound-pair ranking",
    "curated family/target atlas": "Curated enzyme-family and target atlas",
    "stage model": "Enzyme-state signature model",
    "weed_assignment": "PESI crop/weed assignment evidence",
    "SKiD_substrates": "SKiD substrate evidence",
    "curated_family_function": "Curated enzyme-family function evidence",
    "carbon_concentration_anaplerotic": "Carbon-concentration and anaplerotic pathway evidence",
    "FoodDB": "FoodDB compound and food occurrence records",
}

EVIDENCE_TIER_LABELS = {
    "direct_or_curated": "direct or curated evidence",
    "direct_occurrence_or_unavailable": "direct occurrence evidence when available",
    "curated_rule_or_direct": "curated rule or direct pathway evidence",
    "curated_literature_rule": "curated literature-derived rule",
    "mixed_evidence": "mixed direct and inferred evidence",
    "model_inference": "model inference",
}

STRENGTH_RANK = {
    "Strong review lead": 3,
    "Moderate review lead": 2,
    "Exploratory lead": 1,
}


@dataclass(frozen=True)
class PairSelection:
    key: str
    compound_a: str
    compound_b: str


def _safe(value: Any, fallback: str = "Not available") -> str:
    if value is None:
        return fallback
    try:
        if value != value:  # NaN
            return fallback
    except Exception:
        pass
    text = str(value).strip()
    return text or fallback


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        if number != number:
            return None
        return round(number, 3)
    except Exception:
        return None


def _pair_key(compound_a: str, compound_b: str) -> str:
    values = [re.sub(r"\s+", " ", x.strip().casefold()) for x in (compound_a, compound_b)]
    return "||".join(sorted(values))


def _human_token(value: Any) -> str:
    raw = _safe(value, "")
    if not raw:
        return "not resolved"
    text = raw.replace("||", " + ").replace("_", " ").replace(";", ", ")
    return re.sub(r"\s+", " ", text).strip()


def _source_label(value: Any) -> str:
    raw = _safe(value, "")
    if not raw:
        return "not resolved"
    return SOURCE_LABELS.get(raw, _human_token(raw))


def _dedupe_text(values: list[Any], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = _safe(value, "")
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if limit is not None and len(output) >= limit:
            break
    return output


def _score_label(value: Any, *, inverse: bool = False) -> str:
    number = _num(value)
    if number is None:
        return "not resolved"
    if inverse:
        if number <= 0.25:
            return "low"
        if number <= 0.50:
            return "moderate"
        return "high"
    if number >= 0.75:
        return "strong"
    if number >= 0.50:
        return "moderate"
    if number >= 0.25:
        return "limited"
    return "weak"


def _margin_interpretation(selectivity: dict[str, Any]) -> str:
    weed = _num(selectivity.get("weed_vulnerability"))
    crop = _num(selectivity.get("crop_vulnerability"))
    margin = _num(selectivity.get("selectivity_margin"))
    stage = _human_token(selectivity.get("stage_relevance"))
    if margin is None:
        return (
            f"No scenario-selectivity margin was resolved for {stage}. Treat the target order as general screening priority "
            "until crop-versus-weed assays are available."
        )
    if margin >= 0.25:
        direction = "a materially higher modeled weed-vulnerability signal than crop-vulnerability signal"
    elif margin > 0:
        direction = "a small positive modeled weed-versus-crop separation"
    elif margin == 0:
        direction = "no modeled weed-versus-crop separation"
    else:
        direction = "a modeled crop-impact concern that weakens selectivity confidence"
    values = []
    if weed is not None:
        values.append(f"weed signal {weed:.3f}")
    if crop is not None:
        values.append(f"crop signal {crop:.3f}")
    values.append(f"margin {margin:.3f}")
    return (
        f"At {stage}, the scenario layer shows {direction} ({', '.join(values)}). "
        "These values are comparative screening proxies, not measured crop safety or weed control."
    )


def _state_interpretation(state: dict[str, Any]) -> str:
    signals = state.get("evidence_signals") or {}
    stage = _human_token(state.get("growth_stage"))
    target_class = _human_token(state.get("target_class"))
    pathway = _score_label(signals.get("pathway_essentiality"))
    kinetic = _score_label(signals.get("kinetic_evidence"))
    structure = _score_label(signals.get("structure_evidence"))
    plant = _score_label(signals.get("plant_context"))
    uncertainty = _score_label(signals.get("uncertainty_penalty"), inverse=True)
    return (
        f"The enzyme-state model links this target to {target_class} during {stage}. "
        f"Support is {pathway} for pathway relevance, {kinetic} for kinetic evidence, {structure} for structural evidence, "
        f"and {plant} for plant-context evidence; modeled uncertainty is {uncertainty}."
    )


def _assay_band(assay: dict[str, Any]) -> dict[str, Any]:
    if assay.get("status") != "available":
        return {
            "status": "not_available",
            "priority": "Simulation unavailable",
            "relative_input_band": None,
            "simulated_max_inhibition": None,
            "interpretation": "No relative assay-prioritization simulation was available for this target-pair context.",
        }
    maximum = _num(assay.get("simulated_max_inhibition"))
    if maximum is None:
        priority = "Relative assay priority available"
    elif maximum >= 0.75:
        priority = "High relative assay priority"
    elif maximum >= 0.50:
        priority = "Moderate relative assay priority"
    else:
        priority = "Exploratory relative assay priority"
    band = assay.get("relative_input_band")
    return {
        "status": "available",
        "priority": priority,
        "relative_input_band": band,
        "simulated_max_inhibition": maximum,
        "model": assay.get("model"),
        "interpretation": assay.get("interpretation") or (
            "Use this relative band only to prioritize controlled assay design. It is not a dose, field rate, or formulation recommendation."
        ),
    }


def _food_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "food_name": record.get("food_name"),
        "food_name_scientific": record.get("food_name_scientific"),
        "food_group": record.get("food_group"),
        "food_subgroup": record.get("food_subgroup"),
        "occurrence_evidence": record.get("occurrence_evidence"),
        "source_confidence": _num(record.get("source_confidence") or record.get("shared_source_confidence")),
        "standard_content": _num(record.get("standard_content")),
        "orig_content": _num(record.get("orig_content")),
        "orig_unit": record.get("orig_unit"),
        "citation_type": record.get("citation_type"),
        "evidence_class": record.get("evidence_class"),
    }


def _source_names(records: list[dict[str, Any]], limit: int = 6) -> list[str]:
    return _dedupe_text([record.get("food_name") for record in records], limit=limit)


class ReportInterpreter:
    """Aggregates PESI artifacts into a non-repetitive, evidence-grounded research report."""

    def __init__(self, settings: ApiSettings):
        self.settings = settings
        self.llm = DeepSeekClient(settings)

    def aggregate(
        self,
        *,
        scenario: dict[str, Any],
        recommendations: list[dict[str, Any]],
        targets: list[dict[str, Any]],
        evidence_by_recommendation: dict[str, dict[str, Any]],
        target_reasoning: list[dict[str, Any]],
        pair_food_details: dict[str, dict[str, Any]],
        report_type: str,
        caveats: list[str],
        food_mapping: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
        for recommendation in recommendations:
            compound_a = _safe(recommendation.get("compound_a"), "Compound A")
            compound_b = _safe(recommendation.get("compound_b"), "Compound B")
            key = _pair_key(compound_a, compound_b)
            evidence = evidence_by_recommendation.get(str(recommendation.get("id")), {})
            if key not in groups:
                groups[key] = {
                    "pair_id": str(recommendation.get("id") or key),
                    "compound_a": compound_a,
                    "compound_b": compound_b,
                    "pair_label": f"{compound_a} + {compound_b}",
                    "evidence_strength": recommendation.get("evidence_strength") or "Exploratory lead",
                    "chemical_class": recommendation.get("chemical_class"),
                    "targets": [],
                    "natural_source_context": {},
                    "evidence_provenance": [],
                    "confidence": {},
                    "assay_prioritization": {"overall_priority": "Simulation unavailable", "target_bands": []},
                    "technical": {"recommendations": [], "source_artifacts": [], "evidence_paths": []},
                }
            group = groups[key]
            if STRENGTH_RANK.get(str(recommendation.get("evidence_strength")), 0) > STRENGTH_RANK.get(str(group.get("evidence_strength")), 0):
                group["evidence_strength"] = recommendation.get("evidence_strength")

            target_name = _safe(recommendation.get("target"), "Unlisted target")
            existing_target = next((item for item in group["targets"] if str(item.get("target")).casefold() == target_name.casefold()), None)
            state = evidence.get("enzyme_state_reasoning") or {}
            selectivity = evidence.get("scenario_selectivity") or {}
            pathway = evidence.get("pathway_context") or []
            synergy = evidence.get("synergy_reasoning") or {}
            assay = _assay_band(evidence.get("assay_prioritization") or {})
            confidence = evidence.get("confidence_and_limitations") or {}
            target_context = {
                "target": target_name,
                "target_family": recommendation.get("target_family"),
                "growth_stage": recommendation.get("stage"),
                "evidence_strength": recommendation.get("evidence_strength"),
                "enzyme_state_interpretation": _state_interpretation(state),
                "scenario_selectivity_interpretation": _margin_interpretation(selectivity),
                "pathway_context": [
                    {
                        "pathway": _human_token(item.get("pathway")),
                        "site_of_action": _human_token(item.get("site_of_action")),
                        "source": _source_label(item.get("source")) if item.get("source") else None,
                        "evidence_class": _human_token(item.get("evidence_class")),
                    }
                    for item in pathway[:3]
                ],
                "pairing_interpretation": (
                    f"The compounds were grouped because the artifact set indicates {', '.join(_dedupe_text(synergy.get('functional_signals') or [], 4)) or 'complementary inhibition-related features'} "
                    f"within the {target_name} context. This is inferred pairing support, not measured synergy."
                ),
                "assay_priority": assay,
                "validation_required": recommendation.get("validation_note"),
            }
            if existing_target is None:
                group["targets"].append(target_context)
            group["assay_prioritization"]["target_bands"].append({"target": target_name, **assay})
            group["technical"]["recommendations"].append({
                "recommendation_id": recommendation.get("id"),
                "target": target_name,
                "growth_stage": recommendation.get("stage"),
                "raw_scores": recommendation.get("raw_scores") or {},
                "state_signals": state.get("evidence_signals") or {},
                "scenario_selectivity": selectivity,
                "assay_prioritization": evidence.get("assay_prioritization") or {},
            })
            group["technical"]["evidence_paths"].append(evidence.get("path") or [])
            group["technical"]["source_artifacts"].extend(evidence.get("source_artifacts") or [])

            direct = confidence.get("direct_evidence") or []
            model = confidence.get("model_inference") or []
            proxies = confidence.get("proxy_assumptions") or []
            weak = confidence.get("weak_or_unsupported_assumptions") or []
            combined = group.get("_confidence_accumulator") or {"direct": [], "model": [], "proxies": [], "weak": []}
            combined["direct"].extend(direct)
            combined["model"].extend(model)
            combined["proxies"].extend(proxies)
            combined["weak"].extend(weak)
            group["_confidence_accumulator"] = combined

            for step in evidence.get("path") or []:
                source = _source_label(step.get("source")) if step.get("source") else None
                if source:
                    group["evidence_provenance"].append({
                        "source": source,
                        "supports": f"{_human_token(step.get('entity_type'))}: {_safe(step.get('label'))}",
                        "evidence_tier": EVIDENCE_TIER_LABELS.get(str(step.get("evidence_tier")), _human_token(step.get("evidence_tier"))),
                    })

        for key, group in groups.items():
            food_detail = pair_food_details.get(key) or {}
            group["natural_source_context"] = self._natural_source_context(group, food_detail)
            accumulator = group.pop("_confidence_accumulator", {"direct": [], "model": [], "proxies": [], "weak": []})
            direct = _dedupe_text([_source_label(value) for value in accumulator["direct"]])
            model = _dedupe_text(accumulator["model"])
            proxies = _dedupe_text(accumulator["proxies"])
            weak = _dedupe_text(accumulator["weak"])
            confidence_label = "Mixed evidence with named direct-source support" if direct else "Model-led evidence with limited direct-source support"
            if weak:
                confidence_label += "; unresolved assumptions remain"
            group["confidence"] = {
                "summary": confidence_label,
                "direct_evidence": direct,
                "model_inference": model,
                "proxy_assumptions": proxies,
                "weak_or_unsupported_assumptions": weak,
                "scientific_boundary": "The ranking explains screening priority; it does not establish efficacy, safety, or field use.",
            }
            group["evidence_provenance"] = self._dedupe_provenance(group["evidence_provenance"], group["technical"]["source_artifacts"])
            group["technical"]["source_artifacts"] = _dedupe_text(group["technical"]["source_artifacts"])
            available_bands = [item for item in group["assay_prioritization"]["target_bands"] if item.get("status") == "available"]
            if available_bands:
                priority_order = {"High relative assay priority": 3, "Moderate relative assay priority": 2, "Exploratory relative assay priority": 1}
                group["assay_prioritization"]["overall_priority"] = max(
                    (item.get("priority") for item in available_bands),
                    key=lambda value: priority_order.get(str(value), 0),
                )
            group["target_count"] = len(group["targets"])

        pair_groups = list(groups.values())
        unique_targets = _dedupe_text([target.get("target") for group in pair_groups for target in group.get("targets", [])])
        synthesis = self._synthesize(
            scenario=scenario,
            pair_groups=pair_groups,
            unique_targets=unique_targets,
            report_type=report_type,
            caveats=caveats,
            food_mapping=food_mapping or {},
        )
        interpretation_mode = {
            "source": synthesis.get("ai_source", "deterministic_fallback"),
            "status": synthesis.get("ai_status", "fallback"),
            "label": "DeepSeek artifact-grounded synthesis" if synthesis.get("ai_source") == "deepseek" else "Deterministic artifact-grounded synthesis",
            "model": self.settings.deepseek_model if synthesis.get("ai_source") == "deepseek" else None,
        }
        sections = self._sections(
            scenario=scenario,
            pair_groups=pair_groups,
            synthesis=synthesis,
            interpretation_mode=interpretation_mode,
            unique_targets=unique_targets,
        )
        representative_recommendations = []
        for group in pair_groups:
            candidate = next((item for item in recommendations if _pair_key(item.get("compound_a", ""), item.get("compound_b", "")) == _pair_key(group["compound_a"], group["compound_b"])), None)
            if candidate:
                representative_recommendations.append(candidate)
        unique_target_cards = []
        seen_targets: set[str] = set()
        for target in targets:
            name = str(target.get("name") or "").casefold()
            if name and name not in seen_targets:
                seen_targets.add(name)
                unique_target_cards.append(target)

        crop = _safe(scenario.get("crop"), "selected crop")
        weed = _safe(scenario.get("weed"), "selected weed")
        stage = _human_token(scenario.get("growth_stage"))
        return {
            "status": "ok",
            "report_type": report_type,
            "title": "PESI screening interpretation report",
            "intro": f"Artifact-grounded research summary for {crop} versus {weed} at {stage}.",
            "interpretation_mode": interpretation_mode,
            "executive_summary": {
                "body": synthesis.get("executive_summary"),
                "key_findings": synthesis.get("key_findings") or [],
                "scenario_interpretation": synthesis.get("scenario_interpretation"),
            },
            "sections": sections,
            "pair_groups": pair_groups,
            "recommendations": representative_recommendations,
            "targets": unique_target_cards,
            "recommendation_evidence": [
                evidence_by_recommendation[key]
                for key in evidence_by_recommendation
                if evidence_by_recommendation.get(key)
            ],
            "target_state_reasoning": target_reasoning,
            "food_source_mapping": food_mapping or {},
            "technical_appendix": {
                "scenario_raw": scenario,
                "pair_count": len(pair_groups),
                "unique_target_count": len(unique_targets),
                "pairs": [
                    {
                        "pair_label": group["pair_label"],
                        "technical": group["technical"],
                    }
                    for group in pair_groups
                ],
                "interpretation_source": interpretation_mode,
            },
            "caveats": caveats + [FOOD_SOURCE_CAVEAT],
        }

    def _natural_source_context(self, group: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
        context = detail.get("context") or {}
        compound_a_detail = detail.get("compound_a_detail") or {}
        compound_b_detail = detail.get("compound_b_detail") or {}
        shared_records = [_food_record(item) for item in context.get("shared_sources") or []]
        a_records = [_food_record(item) for item in (compound_a_detail.get("sources") or context.get("compound_a_sources") or [])]
        b_records = [_food_record(item) for item in (compound_b_detail.get("sources") or context.get("compound_b_sources") or [])]

        def compound_summary(label: str, item: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
            match = item.get("match") or {}
            status = item.get("status") or ("ok" if match else "unmatched")
            return {
                "compound": label,
                "match_status": status,
                "fooddb_compound_name": match.get("fooddb_compound_name"),
                "match_method": _human_token(match.get("match_method")) if match else "no exact FoodDB match resolved",
                "match_confidence": _num(match.get("match_confidence")) if match else None,
                "match_confidence_label": _score_label(match.get("match_confidence")) if match else "not resolved",
                "source_count": len(records),
                "top_sources": records[:6],
                "top_source_names": _source_names(records),
            }

        shared_status = "shared_sources_found" if shared_records else (
            "individual_sources_only" if a_records or b_records else "no_sources_resolved"
        )
        return {
            "status": shared_status,
            "shared_source_count": int(context.get("shared_food_count") or len(shared_records)),
            "shared_source_confidence": _num(context.get("shared_source_confidence")),
            "shared_sources": shared_records[:8],
            "shared_source_names": _source_names(shared_records, limit=8),
            "compound_a": compound_summary(group["compound_a"], compound_a_detail, a_records),
            "compound_b": compound_summary(group["compound_b"], compound_b_detail, b_records),
            "interpretation": self._food_interpretation(group, shared_records, a_records, b_records),
            "caveat": context.get("caveat") or FOOD_SOURCE_CAVEAT,
        }

    @staticmethod
    def _food_interpretation(group: dict[str, Any], shared: list[dict[str, Any]], a_records: list[dict[str, Any]], b_records: list[dict[str, Any]]) -> str:
        if shared:
            names = ", ".join(_source_names(shared, limit=5))
            return f"FoodDB reports both mapped compounds in {names}. This is shared occurrence context, not evidence that those foods provide an effective or safe intervention source."
        parts: list[str] = []
        if a_records:
            parts.append(f"{group['compound_a']} is reported in {', '.join(_source_names(a_records, limit=5))}")
        if b_records:
            parts.append(f"{group['compound_b']} is reported in {', '.join(_source_names(b_records, limit=5))}")
        if parts:
            return "; ".join(parts) + ". No shared food or ingredient source was established for the pair."
        return "No exact FoodDB occurrence source was resolved for either compound in this pair. An unmatched result does not prove absence from foods or plants."

    @staticmethod
    def _dedupe_provenance(items: list[dict[str, Any]], source_artifacts: list[str]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            source = _safe(item.get("source"), "")
            supports = _safe(item.get("supports"), "")
            key = (source.casefold(), supports.casefold())
            if not source or key in seen:
                continue
            seen.add(key)
            output.append(item)
        for artifact in _dedupe_text(source_artifacts):
            source = ARTIFACT_LABELS.get(artifact, artifact)
            key = (source.casefold(), "artifact provenance")
            if key in seen:
                continue
            seen.add(key)
            output.append({
                "source": source,
                "supports": "artifact provenance",
                "evidence_tier": "named generated artifact",
                "artifact": artifact,
            })
        return output

    def _synthesize(
        self,
        *,
        scenario: dict[str, Any],
        pair_groups: list[dict[str, Any]],
        unique_targets: list[str],
        report_type: str,
        caveats: list[str],
        food_mapping: dict[str, Any],
    ) -> dict[str, Any]:
        crop = _safe(scenario.get("crop"), "the selected crop")
        weed = _safe(scenario.get("weed"), "the selected weed")
        stage = _human_token(scenario.get("growth_stage"))
        leading = pair_groups[0] if pair_groups else None
        shared_count = sum(1 for group in pair_groups if group.get("natural_source_context", {}).get("status") == "shared_sources_found")
        if leading:
            executive = (
                f"For {crop} versus {weed} at {stage}, PESI prioritized {len(pair_groups)} unique compound pairs across "
                f"{len(unique_targets)} enzyme targets. The leading pair, {leading['pair_label']}, is associated with "
                f"{', '.join(target['target'] for target in leading['targets'][:3])}. The report separates direct occurrence and curated evidence "
                "from model inference, proxy assumptions, and unresolved limitations."
            )
        else:
            executive = f"No candidate pairs were available for {crop} versus {weed} at {stage}."
        fallback = {
            "status": "ok",
            "executive_summary": executive,
            "key_findings": [
                f"{len(pair_groups)} unique compound pairs were retained after grouping repeated target-specific rows.",
                f"{len(unique_targets)} distinct enzyme targets are represented in the selected report scope.",
                f"{shared_count} pair{'s' if shared_count != 1 else ''} have a shared FoodDB food or ingredient occurrence context.",
                "Scenario selectivity, pairing support, hazard, persistence, and assay-priority bands remain computational or proxy-based until experimentally validated.",
            ],
            "scenario_interpretation": (
                f"The crop/weed frame is {crop} versus {weed} at {stage}. Target-specific sections explain whether the model estimates a positive weed-versus-crop margin, "
                "a weak separation, or a crop-impact concern."
            ),
            "ai_source": "deterministic_fallback",
            "ai_status": "fallback",
        }
        compact_pairs = []
        for group in pair_groups[:10]:
            compact_pairs.append({
                "pair": group["pair_label"],
                "targets": [item["target"] for item in group.get("targets", [])],
                "evidence_strength": group.get("evidence_strength"),
                "natural_source_status": group.get("natural_source_context", {}).get("status"),
                "shared_sources": group.get("natural_source_context", {}).get("shared_source_names", [])[:5],
                "confidence": group.get("confidence", {}).get("summary"),
                "assay_priority": group.get("assay_prioritization", {}).get("overall_priority"),
            })
        system = (
            "You produce a concise scientific executive synthesis for PESI computational plant-enzyme screening. "
            "Use only the supplied JSON. Do not repeat rows. Group findings by unique compound pair. Distinguish direct evidence, model inference, proxies, and uncertainty. "
            "Do not claim efficacy, dose, formulation, safety, field performance, or that a reported food source is directly usable. "
            "Return JSON with keys: status, executive_summary, key_findings, scenario_interpretation. key_findings must be a short list."
        )
        user = json.dumps({
            "report_type": report_type,
            "scenario": scenario,
            "pair_groups": compact_pairs,
            "food_mapping": food_mapping,
            "required_caveats": caveats,
        }, indent=2)
        response = self.llm.complete_json(system=system, user=user, fallback=fallback)
        merged = dict(fallback)
        if isinstance(response, dict):
            for key in ("status", "executive_summary", "key_findings", "scenario_interpretation", "ai_source", "ai_status"):
                value = response.get(key)
                if value is not None and value != "":
                    merged[key] = value
        if not isinstance(merged.get("key_findings"), list):
            merged["key_findings"] = fallback["key_findings"]
        return merged

    @staticmethod
    def _sections(
        *,
        scenario: dict[str, Any],
        pair_groups: list[dict[str, Any]],
        synthesis: dict[str, Any],
        interpretation_mode: dict[str, Any],
        unique_targets: list[str],
    ) -> list[dict[str, str]]:
        crop = _safe(scenario.get("crop"), "selected crop")
        weed = _safe(scenario.get("weed"), "selected weed")
        stage = _human_token(scenario.get("growth_stage"))
        pair_lines = []
        source_lines = []
        provenance_lines = []
        assay_lines = []
        for index, group in enumerate(pair_groups, 1):
            targets = ", ".join(item["target"] for item in group.get("targets", [])) or "no target resolved"
            pair_lines.append(f"{index}. {group['pair_label']} — targets: {targets}; {str(group.get('evidence_strength', '')).lower()}.")
            source_lines.append(f"{index}. {group['pair_label']}: {group['natural_source_context']['interpretation']}")
            named_sources = _dedupe_text([item.get("source") for item in group.get("evidence_provenance", [])], limit=6)
            provenance_lines.append(f"{index}. {group['pair_label']}: {', '.join(named_sources) or 'No named provenance resolved'}. Confidence: {group['confidence']['summary']}.")
            bands = []
            for item in group.get("assay_prioritization", {}).get("target_bands", []):
                if item.get("status") == "available":
                    band = item.get("relative_input_band")
                    bands.append(f"{item.get('target')}: {item.get('priority')} (relative band {band})")
                else:
                    bands.append(f"{item.get('target')}: simulation unavailable")
            assay_lines.append(f"{index}. {group['pair_label']}: {'; '.join(bands) or 'simulation unavailable'}.")
        return [
            {"title": "Executive synthesis", "body": _safe(synthesis.get("executive_summary"))},
            {"title": "Scenario-specific interpretation", "body": f"{crop} versus {weed} at {stage}. {_safe(synthesis.get('scenario_interpretation'))}"},
            {"title": "Grouped candidate-pair findings", "body": "\n".join(pair_lines) or "No candidate pairs were available."},
            {"title": "Natural source context", "body": ("\n".join(source_lines) or "No FoodDB occurrence context was resolved.") + f"\n\n{FOOD_SOURCE_CAVEAT}"},
            {"title": "Named evidence provenance", "body": "\n".join(provenance_lines) or "No named provenance was resolved."},
            {"title": "Evidence confidence and limitations", "body": "Each grouped pair separates named direct evidence, model-inference layers, proxy assumptions, and unresolved assumptions. The detailed classifications are shown in the grouped pair records and technical appendix."},
            {"title": "Assay prioritization", "body": "\n".join(assay_lines) or "No assay-prioritization simulation was available."},
            {"title": "Validation roadmap", "body": "Confirm target engagement, pair interaction, controlled dose-response behavior, comparative crop tolerance and weed response, toxicity, environmental persistence, and source extractability before any practical development decision."},
            {"title": "Interpretation method", "body": f"{interpretation_mode['label']}. The main report translates internal tokens and scores into scientific language. Raw scores, artifact names, and model fields are retained only in the technical appendix."},
        ]

    def render_html(self, report: dict[str, Any]) -> str:
        def esc(value: Any) -> str:
            return html.escape(_safe(value, ""))

        interpretation = report.get("interpretation_mode") or {}
        summary = report.get("executive_summary") or {}
        key_findings = "".join(f"<li>{esc(item)}</li>" for item in summary.get("key_findings") or [])
        pair_html = "".join(self._pair_html(group, esc) for group in report.get("pair_groups") or [])
        caveats = "".join(f"<li>{esc(item)}</li>" for item in report.get("caveats") or [])
        appendix_json = esc(json.dumps(report.get("technical_appendix") or {}, indent=2, default=str))
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(report.get('title'))}</title>
<style>
:root{{--ink:#17211b;--muted:#59665e;--line:#dce5dd;--paper:#f5f7f3;--panel:#fff;--accent:#0b6b50;--soft:#eaf4ef;--warn:#8a4a12;--warn-soft:#fff8e8}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;line-height:1.58}}
main{{max-width:1080px;margin:0 auto;padding:42px 22px 72px}}h1{{font-size:clamp(2rem,4vw,3.5rem);line-height:1.02;letter-spacing:-.04em;margin:.35rem 0 1rem}}h2{{margin:0 0 .8rem}}h3{{margin:.1rem 0 .45rem}}p{{color:var(--muted)}}
.badge{{display:inline-flex;align-items:center;border:1px solid #b8d4c8;background:var(--soft);color:#07513d;border-radius:999px;padding:.4rem .7rem;font-size:.82rem;font-weight:750}}
.meta{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.8rem;margin:1.2rem 0 1.6rem}}.meta div,.panel,.pair{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:1rem}}
.meta small{{display:block;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.06em}}.meta strong{{display:block;margin-top:.25rem}}
.panel{{margin:1rem 0}}.pair{{margin:1rem 0;padding:1.2rem}}.pair-head{{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}}.strength{{white-space:nowrap}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.8rem}}.subpanel{{border:1px solid var(--line);border-radius:12px;padding:.85rem;background:#fbfcfa}}
ul{{padding-left:1.25rem}}table{{width:100%;border-collapse:collapse;font-size:.92rem}}th,td{{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:.6rem}}th{{color:var(--muted)}}
.source-list{{display:flex;flex-wrap:wrap;gap:.35rem}}.source-pill{{border:1px solid var(--line);border-radius:999px;padding:.25rem .55rem;background:#fbfcfa;font-size:.84rem}}
.notice{{background:var(--warn-soft);border-color:#edd09a}}details{{margin-top:1rem}}pre{{overflow:auto;max-height:520px;background:#111713;color:#dfe9e2;border-radius:12px;padding:1rem;font-size:.78rem}}
@media(max-width:800px){{.meta,.grid{{grid-template-columns:1fr}}.pair-head{{display:block}}}}
</style></head><body><main>
<span class="badge">PESI research-use report</span>
<h1>{esc(report.get('title'))}</h1><p>{esc(report.get('intro'))}</p>
<div class="meta"><div><small>Interpretation</small><strong>{esc(interpretation.get('label'))}</strong></div><div><small>Unique pairs</small><strong>{len(report.get('pair_groups') or [])}</strong></div><div><small>Unique targets</small><strong>{esc((report.get('technical_appendix') or {}).get('unique_target_count'))}</strong></div><div><small>Report depth</small><strong>{esc(report.get('report_type'))}</strong></div></div>
<section class="panel"><h2>Executive synthesis</h2><p>{esc(summary.get('body'))}</p><ul>{key_findings}</ul><p><strong>Scenario interpretation:</strong> {esc(summary.get('scenario_interpretation'))}</p></section>
<section><h2>Grouped candidate-pair findings</h2>{pair_html or '<p>No candidate pairs were available.</p>'}</section>
<section class="panel notice"><h2>Required validation and research boundaries</h2><ul>{caveats}</ul></section>
<details class="panel"><summary><strong>Technical appendix: raw scores, internal fields, and artifact names</strong></summary><p>These fields support auditability and are intentionally separated from the main interpretation.</p><pre>{appendix_json}</pre></details>
</main></body></html>"""

    def _pair_html(self, group: dict[str, Any], esc) -> str:
        targets = "".join(
            f"<tr><td><strong>{esc(item.get('target'))}</strong><br>{esc(item.get('target_family'))}</td><td>{esc(item.get('growth_stage'))}</td><td>{esc(item.get('enzyme_state_interpretation'))}</td><td>{esc(item.get('scenario_selectivity_interpretation'))}</td></tr>"
            for item in group.get("targets") or []
        )
        source = group.get("natural_source_context") or {}
        compound_a = source.get("compound_a") or {}
        compound_b = source.get("compound_b") or {}
        shared_pills = "".join(f"<span class='source-pill'>{esc(name)}</span>" for name in source.get("shared_source_names") or [])
        a_pills = "".join(f"<span class='source-pill'>{esc(name)}</span>" for name in compound_a.get("top_source_names") or [])
        b_pills = "".join(f"<span class='source-pill'>{esc(name)}</span>" for name in compound_b.get("top_source_names") or [])
        provenance = "".join(
            f"<li><strong>{esc(item.get('source'))}</strong> — {esc(item.get('supports'))} <em>({esc(item.get('evidence_tier'))})</em></li>"
            for item in (group.get("evidence_provenance") or [])[:12]
        )
        confidence = group.get("confidence") or {}
        assay_rows = "".join(
            f"<tr><td>{esc(item.get('target'))}</td><td>{esc(item.get('priority'))}</td><td>{esc(item.get('relative_input_band'))}</td><td>{esc(item.get('interpretation'))}</td></tr>"
            for item in group.get("assay_prioritization", {}).get("target_bands", [])
        )
        return f"""<article class="pair"><div class="pair-head"><div><h3>{esc(group.get('pair_label'))}</h3><p>{esc(group.get('target_count'))} target context(s) retained after grouping repeated rows.</p></div><span class="badge strength">{esc(group.get('evidence_strength'))}</span></div>
<div class="panel"><h3>Target, enzyme-state, and scenario interpretation</h3><table><thead><tr><th>Target</th><th>Stage</th><th>Enzyme-state interpretation</th><th>Scenario selectivity</th></tr></thead><tbody>{targets}</tbody></table></div>
<div class="grid"><div class="subpanel"><h3>Natural source context</h3><p>{esc(source.get('interpretation'))}</p><p><strong>{esc(compound_a.get('compound'))}</strong> — {esc(compound_a.get('match_status'))}; match: {esc(compound_a.get('match_method'))}; confidence: {esc(compound_a.get('match_confidence_label'))}.</p><div class="source-list">{a_pills or '<span class="source-pill">No source names resolved</span>'}</div><p><strong>{esc(compound_b.get('compound'))}</strong> — {esc(compound_b.get('match_status'))}; match: {esc(compound_b.get('match_method'))}; confidence: {esc(compound_b.get('match_confidence_label'))}.</p><div class="source-list">{b_pills or '<span class="source-pill">No source names resolved</span>'}</div><p><strong>Shared sources</strong></p><div class="source-list">{shared_pills or '<span class="source-pill">No shared source established</span>'}</div></div>
<div class="subpanel"><h3>Evidence confidence</h3><p>{esc(confidence.get('summary'))}</p><p><strong>Direct evidence:</strong> {esc(', '.join(confidence.get('direct_evidence') or []) or 'None named')}</p><p><strong>Model inference:</strong> {esc(', '.join(confidence.get('model_inference') or []) or 'None')}</p><p><strong>Proxy assumptions:</strong> {esc(', '.join(confidence.get('proxy_assumptions') or []) or 'None')}</p><p><strong>Unresolved assumptions:</strong> {esc(', '.join(confidence.get('weak_or_unsupported_assumptions') or []) or 'None identified')}</p></div></div>
<div class="panel"><h3>Named evidence provenance</h3><ul>{provenance or '<li>No named provenance was resolved.</li>'}</ul></div>
<div class="panel"><h3>Assay-prioritization simulation</h3><p><strong>{esc(group.get('assay_prioritization', {}).get('overall_priority'))}</strong></p><table><thead><tr><th>Target</th><th>Priority</th><th>Relative simulation band</th><th>Interpretation</th></tr></thead><tbody>{assay_rows}</tbody></table><p>This is relative experimental prioritization only; it is not a dose or field rate.</p></div></article>"""
