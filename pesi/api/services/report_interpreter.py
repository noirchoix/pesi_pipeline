from __future__ import annotations

import html
import json
import math
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from pesi.api.config import ApiSettings
from pesi.api.services.llm_client import DeepSeekClient
from pesi.api.services.json_safe import to_json_safe
from pesi.domain.compound_identity import canonical_compound_identity, canonical_compound_pair_key
from pesi.domain.compound_rules import canonicalize_compound_pair, canonicalize_text_key
from pesi.domain.enzyme_identity import resolve_enzyme_identity
from pesi.domain.scientific_semantics import evidence_tier_label, fooddb_zero_result_semantics, normalize_fooddb_match, normalize_selectivity


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
    "weed_assignment": "PESI model-derived crop/weed assignment",
    "SKiD_substrates": "SKiD substrate evidence",
    "curated_family_function": "Curated enzyme-family function evidence",
    "carbon_concentration_anaplerotic": "Carbon-concentration and anaplerotic pathway evidence",
    "FoodDB": "FoodDB compound and food occurrence records",
}

EVIDENCE_TIER_LABELS = {
    "direct_occurrence": "direct database occurrence evidence",
    "direct_occurrence_or_unavailable": "direct occurrence evidence when available",
    "curated_reference": "curated reference evidence",
    "direct_or_curated": "curated reference evidence",
    "curated_rule_or_direct": "curated target-rule evidence",
    "curated_literature_rule": "curated literature-derived rule",
    "scenario_context": "user-provided scenario context",
    "mixed_evidence": "mixed model and curated evidence",
    "model_inference": "model-derived inference",
    "proxy_estimate": "proxy estimate",
    "unresolved": "unresolved evidence",
    "unmapped": "no validated target-specific mapping",
    "database_query_no_shared_occurrence": "database query returned no shared occurrence",
    "compound_unmatched": "compound could not be mapped to FoodDB",
    "database_unavailable": "FoodDB evidence unavailable",
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
        if not math.isfinite(number):
            return None
        return round(number, 3)
    except Exception:
        return None


def _pair_key(compound_a: str, compound_b: str) -> str:
    left, right = canonicalize_compound_pair(compound_a, compound_b)
    return f"{left}||{right}"


def _canonical_pair_display(compound_a: str, compound_b: str) -> tuple[str, str, str]:
    ordered = sorted([str(compound_a).strip(), str(compound_b).strip()], key=canonicalize_text_key)
    return ordered[0], ordered[1], f"{ordered[0]} + {ordered[1]}"


def _canonical_pair_payload(recommendation: dict[str, Any]) -> dict[str, str]:
    """Resolve an unordered pair while preserving name-to-identity ownership.

    Pair grouping is identity-first. Display labels remain human-readable, but
    no report join is allowed to fall back to a display-name key when canonical
    compound identities are present.
    """

    raw_a = _safe(recommendation.get("compound_a"), "Compound A")
    raw_b = _safe(recommendation.get("compound_b"), "Compound B")

    identity_a = canonical_compound_identity(
        name=raw_a,
        canonical_smiles=recommendation.get("compound_a_canonical_smiles"),
        inchikey=recommendation.get("compound_a_inchikey"),
        source_id=recommendation.get("compound_a_source_id"),
        source_resource=recommendation.get("compound_a_source"),
    )
    identity_b = canonical_compound_identity(
        name=raw_b,
        canonical_smiles=recommendation.get("compound_b_canonical_smiles"),
        inchikey=recommendation.get("compound_b_inchikey"),
        source_id=recommendation.get("compound_b_source_id"),
        source_resource=recommendation.get("compound_b_source"),
    )
    id_a = str(recommendation.get("compound_a_canonical_id") or identity_a["canonical_compound_id"])
    id_b = str(recommendation.get("compound_b_canonical_id") or identity_b["canonical_compound_id"])

    ordered = sorted(
        [
            {"name": raw_a, "canonical_id": id_a},
            {"name": raw_b, "canonical_id": id_b},
        ],
        key=lambda item: (canonicalize_text_key(item["name"]), item["canonical_id"]),
    )
    pair_key = str(
        recommendation.get("canonical_pair_key")
        or canonical_compound_pair_key(
            id_a,
            id_b,
            compound_a_name=raw_a,
            compound_b_name=raw_b,
        )
    )
    return {
        "compound_a": ordered[0]["name"],
        "compound_b": ordered[1]["name"],
        "compound_a_canonical_id": ordered[0]["canonical_id"],
        "compound_b_canonical_id": ordered[1]["canonical_id"],
        "pair_key": pair_key,
        "pair_label": f"{ordered[0]['name']} + {ordered[1]['name']}",
    }


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


def _join_sentences(values: list[Any]) -> str:
    parts = [str(value).strip().rstrip(" .;") for value in values if str(value).strip()]
    return ". ".join(parts) + ("." if parts else "")


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
    semantics = normalize_selectivity(
        weed_vulnerability=selectivity.get("weed_vulnerability"),
        crop_vulnerability=selectivity.get("crop_vulnerability"),
        reported_margin=selectivity.get("selectivity_difference", selectivity.get("selectivity_margin")),
        reported_index=selectivity.get("selectivity_index"),
    )
    weed = _num(semantics.get("weed_vulnerability"))
    crop = _num(semantics.get("crop_vulnerability"))
    difference = _num(semantics.get("selectivity_difference"))
    index = _num(semantics.get("selectivity_index"))
    stage = _human_token(selectivity.get("stage_relevance"))
    if difference is None:
        return (
            f"No weed-minus-crop selectivity difference was resolved for {stage}. Treat the target order as general screening priority "
            "until comparative crop-versus-weed assays are available."
        )
    if difference >= 0.25:
        direction = "a materially higher modeled weed-vulnerability signal than crop-vulnerability signal"
    elif difference > 0.05:
        direction = "a small positive modeled weed-versus-crop separation"
    elif difference >= -0.05:
        direction = "no material modeled weed-versus-crop separation"
    else:
        direction = "a modeled crop-vulnerability concern that weakens selectivity confidence"
    values = []
    if weed is not None:
        values.append(f"weed signal {weed:.3f}")
    if crop is not None:
        values.append(f"crop signal {crop:.3f}")
    values.append(f"weed-minus-crop difference {difference:.3f}")
    if index is not None:
        values.append(f"centered ranking index {index:.3f}")
    scope = str(selectivity.get("selectivity_scope") or "scenario_level")
    if scope == "target_specific":
        scope_text = "This comparison uses paired target-specific crop-versus-weed inputs."
    else:
        scope_text = (
            "This is a scenario-level baseline applied to the target context; it is not a target-specific selectivity estimate because paired crop-versus-weed target evidence was unavailable."
        )
    return (
        f"At {stage}, the scenario layer shows {direction} ({', '.join(values)}). "
        "The difference is weed vulnerability minus crop vulnerability; the centered index is retained only for ranking. "
        f"{scope_text} Both values are comparative model proxies, not measured crop safety or weed control."
    )


def _state_interpretation(
    state: dict[str, Any],
    *,
    target_atlas: dict[str, Any] | None = None,
    identity: dict[str, Any] | None = None,
) -> str:
    signals = state.get("evidence_signals") or {}
    stage = _human_token(state.get("growth_stage"))
    target_class = _human_token(state.get("target_class"))
    kinetic = _score_label(signals.get("kinetic_evidence"))
    structure = _score_label(signals.get("structure_evidence"))
    plant = _score_label(signals.get("plant_context"))
    uncertainty = _score_label(signals.get("uncertainty_penalty"), inverse=True)
    pathway_signal = _score_label(signals.get("pathway_essentiality"))
    atlas_status = str((target_atlas or {}).get("target_match_status") or "unmapped")
    identity_level = str((identity or {}).get("identity_resolution_level") or "unresolved")
    if atlas_status in {"validated", "validated_target"}:
        pathway_text = f"a {pathway_signal} model-derived pathway-essentiality signal alongside a validated target-specific atlas mapping"
    elif atlas_status == "family_context":
        pathway_text = f"a {pathway_signal} model-derived pathway-essentiality signal, but only broad family/process atlas context"
    else:
        pathway_text = (
            f"a {pathway_signal} model-derived pathway-essentiality signal; no target-specific pathway identity was validated, so this is not confirmed pathway membership"
        )
    identity_text = f"Canonical identity resolution level: {identity_level.replace('_', ' ')}."
    return (
        f"The enzyme-state model links this target to {target_class} during {stage} and reports {pathway_text}. "
        f"Kinetic evidence is {kinetic}, structural evidence is {structure}, and plant-context evidence is {plant}; modeled uncertainty is {uncertainty}. "
        f"{identity_text}"
    )


def _assay_band(assay: dict[str, Any]) -> dict[str, Any]:
    if assay.get("status") != "available":
        return {
            "status": "not_available",
            "priority": "Not prioritizable",
            "scientific_priority": "Not prioritizable",
            "scientific_priority_code": "not_prioritizable",
            "scientific_priority_score": 0.0,
            "simulation_priority": "Simulation unavailable",
            "relative_input_band": None,
            "simulated_max_inhibition": None,
            "gating_reasons": ["No assay-prioritization simulation was available."],
            "interpretation": "No relative assay-prioritization simulation was available for this target-pair context.",
        }
    maximum = _num(assay.get("simulated_max_inhibition"))
    scientific = assay.get("scientific_priority") or "Exploratory scientific validation priority"
    return {
        "status": "available",
        "priority": scientific,
        "scientific_priority": scientific,
        "scientific_priority_code": assay.get("scientific_priority_code") or "exploratory",
        "scientific_priority_score": _num(assay.get("scientific_priority_score")),
        "simulation_priority": assay.get("simulation_priority") or "Simulation output available",
        "relative_input_band": assay.get("relative_input_band"),
        "units": assay.get("units") or "dimensionless_normalized_model_input",
        "units_label": assay.get("units_label") or "Dimensionless normalized model-input units",
        "simulated_max_inhibition": maximum,
        "model": assay.get("model"),
        "gating_reasons": assay.get("gating_reasons") or [],
        "supporting_factors": assay.get("supporting_factors") or [],
        "interpretation": assay.get("interpretation") or (
            "Use this dimensionless normalized model-input band only to prioritize controlled assay design. It is not a concentration, dose, field rate, or formulation recommendation."
        ),
    }


def _food_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "pesi_compound_canonical_id": record.get("pesi_compound_canonical_id"),
        "fooddb_compound_id": record.get("fooddb_compound_id"),
        "fooddb_public_id": record.get("fooddb_public_id"),
        "fooddb_compound_name": record.get("fooddb_compound_name"),
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
            pair = _canonical_pair_payload(recommendation)
            compound_a = pair["compound_a"]
            compound_b = pair["compound_b"]
            pair_label = pair["pair_label"]
            key = pair["pair_key"]
            evidence = evidence_by_recommendation.get(str(recommendation.get("id")), {})
            if key not in groups:
                groups[key] = {
                    "pair_id": str(recommendation.get("id") or key),
                    "compound_a": compound_a,
                    "compound_b": compound_b,
                    "compound_a_canonical_id": pair["compound_a_canonical_id"],
                    "compound_b_canonical_id": pair["compound_b_canonical_id"],
                    "pair_key": key,
                    "pair_label": pair_label,
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

            target_name_reported = _safe(recommendation.get("target"), "Unlisted target")
            identity = evidence.get("enzyme_identity") or (evidence.get("enzyme_state_reasoning") or {}).get("enzyme_identity") or resolve_enzyme_identity(
                target_name_reported, recommendation.get("target_family")
            )
            target_name = _safe(identity.get("canonical_name"), target_name_reported)
            target_id = _safe(identity.get("canonical_id"), target_name.casefold())
            target_stage_key = _human_token(recommendation.get("stage")).casefold()
            existing_target = next((item for item in group["targets"] if item.get("target_canonical_id") == target_id and _human_token(item.get("growth_stage")).casefold() == target_stage_key), None)
            state = evidence.get("enzyme_state_reasoning") or {}
            selectivity = evidence.get("scenario_selectivity") or {}
            pathway = evidence.get("pathway_context") or []
            synergy = evidence.get("synergy_reasoning") or {}
            assay = _assay_band(evidence.get("assay_prioritization") or {})
            confidence = evidence.get("confidence_and_limitations") or {}
            target_context = {
                "target": target_name,
                "target_reported": target_name_reported,
                "target_aliases": [target_name_reported],
                "target_canonical_id": target_id,
                "target_family": identity.get("canonical_family") or recommendation.get("target_family"),
                "target_family_reported": identity.get("family_reported") or recommendation.get("target_family"),
                "enzyme_identity": identity,
                "growth_stage": recommendation.get("stage"),
                "evidence_strength": recommendation.get("evidence_strength"),
                "enzyme_state_interpretation": _state_interpretation(
                    state, target_atlas=evidence.get("target_atlas_validation") or {}, identity=identity
                ),
                "scenario_selectivity_interpretation": _margin_interpretation(selectivity),
                "selectivity_scope": selectivity.get("selectivity_scope") or "scenario_level",
                "pathway_context": [
                    {
                        "pathway": _human_token(item.get("pathway")),
                        "site_of_action": _human_token(item.get("site_of_action")),
                        "source": _source_label(item.get("source")) if item.get("source") else None,
                        "evidence_class": _human_token(item.get("evidence_class")),
                        "target_match_status": item.get("target_match_status"),
                        "target_match_basis": item.get("target_match_basis"),
                        "target_match_confidence": _num(item.get("target_match_confidence")),
                    }
                    for item in pathway[:3]
                ],
                "target_atlas_validation": evidence.get("target_atlas_validation") or {},
                "pairing_interpretation": (
                    f"The compounds were grouped because the artifact set indicates {', '.join(_dedupe_text(synergy.get('functional_signals') or [], 4)) or 'complementary inhibition-related features'} "
                    f"within the {target_name} context. This is inferred pairing support, not measured synergy."
                ),
                "assay_priority": assay,
                "validation_required": recommendation.get("validation_note"),
            }
            if existing_target is None:
                group["targets"].append(target_context)
            else:
                aliases = existing_target.setdefault("target_aliases", [])
                if target_name_reported.casefold() not in {str(x).casefold() for x in aliases}:
                    aliases.append(target_name_reported)
                existing_target["consolidated_record_count"] = int(existing_target.get("consolidated_record_count") or 1) + 1
            assay_key = (target_id, target_stage_key)
            if not any((item.get("target_canonical_id"), item.get("stage_key")) == assay_key for item in group["assay_prioritization"]["target_bands"]):
                group["assay_prioritization"]["target_bands"].append({"target": target_name, "target_canonical_id": target_id, "stage_key": target_stage_key, **assay})
            group["technical"]["recommendations"].append({
                "recommendation_id": recommendation.get("id"),
                "canonical_pair_key": key,
                "compound_a": compound_a,
                "compound_b": compound_b,
                "compound_a_canonical_id": pair["compound_a_canonical_id"],
                "compound_b_canonical_id": pair["compound_b_canonical_id"],
                "target": target_name,
                "target_reported": target_name_reported,
                "target_canonical_id": target_id,
                "enzyme_identity": identity,
                "growth_stage": recommendation.get("stage"),
                "raw_scores": recommendation.get("raw_scores") or {},
                "state_signals": state.get("evidence_signals") or {},
                "scenario_selectivity": selectivity,
                "assay_prioritization": evidence.get("assay_prioritization") or {},
            })
            group["technical"]["evidence_paths"].append(evidence.get("path") or [])
            group["technical"]["source_artifacts"].extend(evidence.get("source_artifacts") or [])

            direct = confidence.get("direct_occurrence_evidence") or confidence.get("direct_evidence") or []
            curated = confidence.get("curated_reference_evidence") or []
            scenario_context = confidence.get("scenario_context") or []
            model = confidence.get("model_inference") or []
            proxies = confidence.get("proxy_assumptions") or []
            weak = confidence.get("weak_or_unsupported_assumptions") or []
            combined = group.get("_confidence_accumulator") or {
                "direct": [], "curated": [], "scenario": [], "model": [], "proxies": [], "weak": []
            }
            combined["direct"].extend(direct)
            combined["curated"].extend(curated)
            combined["scenario"].extend(scenario_context)
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
                        "evidence_tier": EVIDENCE_TIER_LABELS.get(
                            str(step.get("evidence_tier")),
                            evidence_tier_label(str(step.get("evidence_tier") or "unresolved")),
                        ),
                    })

        for key, group in groups.items():
            food_detail = pair_food_details.get(key) or {}
            if not food_detail:
                # Legacy report fixtures/artifacts may still use an unordered
                # normalized-name key. This fallback is read-only and cannot
                # create or merge compound occurrence claims.
                legacy_key = _pair_key(group["compound_a"], group["compound_b"])
                food_detail = pair_food_details.get(legacy_key) or {}
            group["natural_source_context"] = self._natural_source_context(group, food_detail)
            accumulator = group.pop("_confidence_accumulator", {
                "direct": [], "curated": [], "scenario": [], "model": [], "proxies": [], "weak": []
            })
            direct = _dedupe_text([_source_label(value) for value in accumulator["direct"]])
            curated = _dedupe_text([_source_label(value) for value in accumulator["curated"]])
            scenario_context = _dedupe_text(accumulator["scenario"])
            model = _dedupe_text(accumulator["model"])
            proxies = _dedupe_text(accumulator["proxies"])
            weak = _dedupe_text(accumulator["weak"])
            if direct:
                confidence_label = "Mixed evidence with direct occurrence records and additional curated/model support"
            elif curated:
                confidence_label = "Curated-reference and model-led evidence without direct occurrence support"
            else:
                confidence_label = "Model-led evidence with no direct occurrence support"
            if weak:
                confidence_label += "; unresolved assumptions remain"
            group["confidence"] = {
                "summary": confidence_label,
                "direct_evidence": direct,
                "direct_occurrence_evidence": direct,
                "curated_reference_evidence": curated,
                "scenario_context": scenario_context,
                "model_inference": model,
                "proxy_assumptions": proxies,
                "weak_or_unsupported_assumptions": weak,
                "scientific_boundary": "The ranking explains screening priority; it does not establish efficacy, safety, or field use.",
            }
            group["evidence_provenance"] = self._dedupe_provenance(group["evidence_provenance"], group["technical"]["source_artifacts"])
            group["technical"]["source_artifacts"] = _dedupe_text(group["technical"]["source_artifacts"])
            available_bands = [item for item in group["assay_prioritization"]["target_bands"] if item.get("status") == "available"]
            unavailable_bands = [item for item in group["assay_prioritization"]["target_bands"] if item.get("status") != "available"]
            group["assay_prioritization"]["available_target_count"] = len(available_bands)
            group["assay_prioritization"]["unavailable_target_count"] = len(unavailable_bands)
            group["assay_prioritization"]["coverage_status"] = (
                "complete" if available_bands and not unavailable_bands
                else "partial" if available_bands
                else "unavailable"
            )
            if available_bands:
                priority_order = {
                    "High scientific validation priority": 4,
                    "Moderate scientific validation priority": 3,
                    "Exploratory scientific validation priority": 2,
                    "Not prioritizable until target identity is resolved": 1,
                    "Not prioritizable": 0,
                }
                priority_values = [str(item.get("priority")) for item in available_bands]
                counts = {value: priority_values.count(value) for value in sorted(set(priority_values))}
                best = max(priority_values, key=lambda value: priority_order.get(value, 0))
                most_conservative = min(priority_values, key=lambda value: priority_order.get(value, 0))
                group["assay_prioritization"]["priority_distribution"] = counts
                group["assay_prioritization"]["best_supported_priority"] = best
                group["assay_prioritization"]["most_conservative_priority"] = most_conservative
                group["assay_prioritization"]["overall_priority"] = (
                    best if len(counts) == 1
                    else f"Mixed scientific priorities — best supported: {best}; conservative floor: {most_conservative}"
                )
            group["target_count"] = len(group["targets"])

        pair_groups = list(groups.values())
        row_validation = self._apply_row_semantic_invariants(pair_groups)
        unique_target_map: OrderedDict[str, str] = OrderedDict()
        for group in pair_groups:
            for target in group.get("targets", []):
                unique_target_map.setdefault(str(target.get("target_canonical_id") or target.get("target")), str(target.get("target")))
        unique_targets = list(unique_target_map.values())
        synthesis = self._synthesize(
            scenario=scenario,
            pair_groups=pair_groups,
            unique_targets=unique_targets,
            report_type=report_type,
            caveats=caveats,
            food_mapping=food_mapping or {},
        )
        synthesis_validation = synthesis.get("semantic_validation") or {"status": "not_run", "corrections": []}
        combined_corrections = list(dict.fromkeys(
            list(row_validation.get("corrections") or [])
            + list(synthesis_validation.get("corrections") or [])
        ))
        semantic_validation = {
            "status": "corrected" if combined_corrections else "passed",
            "corrections": combined_corrections,
            "facts": synthesis_validation.get("facts") or {},
            "row_invariants": row_validation,
            "synthesis_validation": synthesis_validation,
        }
        synthesis["semantic_validation"] = semantic_validation
        if synthesis.get("ai_source") == "deepseek":
            label = "DeepSeek artifact-grounded synthesis — deterministic scientific validation passed"
            if semantic_validation.get("status") == "corrected":
                label = "DeepSeek-assisted synthesis — deterministically corrected for scientific consistency"
        else:
            label = "Deterministic artifact-grounded synthesis — scientific validation passed"
        interpretation_mode = {
            "source": synthesis.get("ai_source", "deterministic_fallback"),
            "status": synthesis.get("ai_status", "fallback_validated"),
            "label": label,
            "model": self.settings.deepseek_model if synthesis.get("ai_source") == "deepseek" else None,
            "semantic_validation_status": semantic_validation.get("status"),
            "semantic_corrections": semantic_validation.get("corrections") or [],
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
            candidate = next(
                (
                    item for item in recommendations
                    if _canonical_pair_payload(item)["pair_key"] == group["pair_key"]
                ),
                None,
            )
            if candidate:
                representative_recommendations.append(candidate)
        unique_target_cards = []
        seen_targets: set[str] = set()
        for target in targets:
            identity = resolve_enzyme_identity(target.get("name"), target.get("family"))
            name = str(identity.get("canonical_id") or target.get("name") or "").casefold()
            if name and name not in seen_targets:
                seen_targets.add(name)
                unique_target_cards.append(target)

        crop = _safe(scenario.get("crop"), "selected crop")
        weed = _safe(scenario.get("weed"), "selected weed")
        stage = _human_token(scenario.get("growth_stage"))
        report = {
            "status": "ok",
            "report_type": report_type,
            "title": "PESI screening interpretation report",
            "intro": f"Artifact-grounded research summary for {crop} versus {weed} at {stage}.",
            "interpretation_mode": interpretation_mode,
            "semantic_validation": semantic_validation,
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
                "semantic_validation": semantic_validation,
            },
            "caveats": caveats + [FOOD_SOURCE_CAVEAT],
        }
        return to_json_safe(report)

    def _natural_source_context(self, group: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
        context = detail.get("context") or {}
        raw_details = [detail.get("compound_a_detail") or {}, detail.get("compound_b_detail") or {}]
        group_a_id = str(group.get("compound_a_canonical_id") or "").strip()
        group_b_id = str(group.get("compound_b_canonical_id") or "").strip()

        def detail_id(item: dict[str, Any]) -> str:
            return str(
                item.get("canonical_compound_id")
                or item.get("pesi_compound_canonical_id")
                or ""
            ).strip()

        def select_detail(canonical_id: str, fallback_index: int) -> dict[str, Any]:
            if canonical_id:
                found = next((item for item in raw_details if detail_id(item) == canonical_id), None)
                if found is not None:
                    return found
            return raw_details[fallback_index] if fallback_index < len(raw_details) else {}

        compound_a_detail = select_detail(group_a_id, 0)
        compound_b_detail = select_detail(group_b_id, 1)

        context_a_id = str(context.get("compound_a_canonical_id") or "").strip()
        context_b_id = str(context.get("compound_b_canonical_id") or "").strip()
        context_a_sources = context.get("compound_a_sources") or []
        context_b_sources = context.get("compound_b_sources") or []
        if group_a_id and group_a_id == context_b_id and group_b_id == context_a_id:
            context_a_sources, context_b_sources = context_b_sources, context_a_sources

        shared_records = [_food_record(item) for item in context.get("shared_sources") or []]
        a_records = [_food_record(item) for item in (compound_a_detail.get("sources") or context_a_sources or [])]
        b_records = [_food_record(item) for item in (compound_b_detail.get("sources") or context_b_sources or [])]

        def compound_summary(
            label: str,
            canonical_id: str,
            item: dict[str, Any],
            records: list[dict[str, Any]],
        ) -> dict[str, Any]:
            normalized = normalize_fooddb_match(item, source_count=len(records))
            matched = normalized["status"] == "matched"
            match = item.get("match") or {}
            fooddb_identifier = (
                match.get("fooddb_compound_id")
                or match.get("fooddb_public_id")
                or match.get("fooddb_compound_name")
            )
            # A matched label without a concrete FoodDB identity is not a valid
            # compound-specific occurrence join.
            if matched and not fooddb_identifier:
                matched = False
                normalized = normalize_fooddb_match({"match_status": "unmatched"}, source_count=0)
            owned_records = [
                record for record in records
                if canonical_id
                and str(record.get("pesi_compound_canonical_id") or "") == canonical_id
            ] if matched else []
            return {
                "compound": label,
                "canonical_compound_id": canonical_id or item.get("canonical_compound_id"),
                "compound_identity_level": item.get("compound_identity_level"),
                "structure_backed_identity": bool(item.get("structure_backed_identity")),
                "canonical_smiles": item.get("canonical_smiles"),
                "inchikey": item.get("inchikey"),
                "match_status": "matched" if matched else normalized["status"],
                "match_status_label": normalized["status_label"] if matched else "No FoodDB compound match",
                "fooddb_compound_id": match.get("fooddb_compound_id") if matched else None,
                "fooddb_public_id": match.get("fooddb_public_id") if matched else None,
                "fooddb_compound_name": normalized["fooddb_compound_name"] if matched else None,
                "match_method": normalized["match_method"] if matched else "Not applicable",
                "match_confidence": _num(normalized["match_confidence"]) if matched else None,
                "match_confidence_label": normalized["match_confidence_label"] if matched else "Unresolved",
                "occurrence_status": "reported_occurrences_found" if owned_records else "no_occurrences_resolved",
                "source_count": len(owned_records),
                "top_sources": owned_records[:6],
                "top_source_names": _source_names(owned_records),
                "source_suppressed": not matched and bool(records),
                "source_suppression_reason": (
                    "Food occurrence records require a unique compound-specific FoodDB match."
                    if not matched else None
                ),
            }

        a_summary = compound_summary(group["compound_a"], group_a_id, compound_a_detail, a_records)
        b_summary = compound_summary(group["compound_b"], group_b_id, compound_b_detail, b_records)
        invariant_corrections: list[dict[str, Any]] = []
        for summary in (a_summary, b_summary):
            if summary.get("source_suppressed"):
                invariant_corrections.append({
                    "code": "unmatched_compound_source_suppressed",
                    "compound": summary.get("compound"),
                })
        a_records = list(a_summary["top_sources"])
        b_records = list(b_summary["top_sources"])

        both_matched = a_summary["match_status"] == "matched" and b_summary["match_status"] == "matched"
        raw_shared_present = bool(shared_records)
        if not both_matched:
            shared_records = []
            if raw_shared_present:
                invariant_corrections.append({"code": "invalid_shared_occurrence_suppressed"})
        else:
            shared_records = [
                record for record in shared_records
                if record.get("fooddb_compound_id") is not None
                or record.get("fooddb_public_id") is not None
                or record.get("food_name")
            ]

        zero_semantics = fooddb_zero_result_semantics(
            query_available=bool(context) and context.get("status") != "not_available",
            compound_a_matched=a_summary["match_status"] == "matched",
            compound_b_matched=b_summary["match_status"] == "matched",
            shared_record_count=len(shared_records),
            individual_record_count=len(a_records) + len(b_records),
        )
        shared_status = "shared_sources_found" if shared_records else (
            "individual_sources_only" if a_records or b_records else "no_sources_resolved"
        )
        return {
            "status": shared_status,
            "canonical_pair_key": group.get("pair_key"),
            "shared_source_count": len(shared_records),
            "shared_source_confidence": _num(context.get("shared_source_confidence")) if shared_records else None,
            "shared_sources": shared_records[:8],
            "shared_source_names": _source_names(shared_records, limit=8),
            "compound_a": a_summary,
            "compound_b": b_summary,
            "pair_query_semantics": zero_semantics,
            "invariant_corrections": invariant_corrections,
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

    def _apply_row_semantic_invariants(self, pair_groups: list[dict[str, Any]]) -> dict[str, Any]:
        """Enforce scientific invariants on every emitted report row.

        The report interpreter is the final trust boundary. It therefore
        revalidates compound ownership, target-identity granularity,
        selectivity scope, and evidence-adjusted priority even when legacy or
        partially regenerated artifacts are supplied.
        """

        corrections: list[str] = []
        details: list[dict[str, Any]] = []
        checked = {
            "pair_rows": 0,
            "compound_rows": 0,
            "target_rows": 0,
            "selectivity_rows": 0,
            "assay_rows": 0,
        }

        def record(code: str, **payload: Any) -> None:
            corrections.append(code)
            details.append({"code": code, **payload})

        exact_identity_levels = {"exact_enzyme", "exact_target", "exact_identifier", "protein"}
        high_priority_codes = {"high", "moderate"}

        for group in pair_groups:
            checked["pair_rows"] += 1
            source = group.get("natural_source_context") or {}
            for prior in source.get("invariant_corrections") or []:
                record(
                    str(prior.get("code") or "row_invariant_corrected"),
                    pair=group.get("pair_label"),
                    compound=prior.get("compound"),
                )
            summaries = [source.get("compound_a") or {}, source.get("compound_b") or {}]
            for summary in summaries:
                checked["compound_rows"] += 1
                status = str(summary.get("match_status") or "unmatched").casefold()
                has_match_id = bool(
                    summary.get("fooddb_compound_id")
                    or summary.get("fooddb_public_id")
                    or summary.get("fooddb_compound_name")
                )
                has_sources = bool(
                    int(summary.get("source_count") or 0)
                    or summary.get("top_sources")
                    or summary.get("top_source_names")
                )
                if status == "matched" and not has_match_id:
                    status = "unmatched"
                    summary.update({
                        "match_status": "unmatched",
                        "match_status_label": "No FoodDB compound match",
                        "match_method": "Not applicable",
                        "match_confidence": None,
                        "match_confidence_label": "Unresolved",
                        "fooddb_compound_id": None,
                        "fooddb_public_id": None,
                        "fooddb_compound_name": None,
                    })
                    record(
                        "matched_compound_missing_fooddb_identity_downgraded",
                        pair=group.get("pair_label"),
                        compound=summary.get("compound"),
                    )
                if status != "matched" and has_sources:
                    summary.update({
                        "source_count": 0,
                        "top_sources": [],
                        "top_source_names": [],
                        "occurrence_status": "no_occurrences_resolved",
                        "source_suppressed": True,
                        "source_suppression_reason": "Food occurrence records require a unique compound-specific FoodDB match.",
                    })
                    record(
                        "unmatched_compound_source_suppressed",
                        pair=group.get("pair_label"),
                        compound=summary.get("compound"),
                    )

            both_matched = all(str(item.get("match_status") or "").casefold() == "matched" for item in summaries)
            if not both_matched and (
                source.get("shared_sources")
                or source.get("shared_source_names")
                or int(source.get("shared_source_count") or 0)
            ):
                source.update({
                    "shared_source_count": 0,
                    "shared_source_confidence": None,
                    "shared_sources": [],
                    "shared_source_names": [],
                })
                record("invalid_shared_occurrence_suppressed", pair=group.get("pair_label"))

            a_summary, b_summary = summaries
            a_records = list(a_summary.get("top_sources") or [])
            b_records = list(b_summary.get("top_sources") or [])
            shared_records = list(source.get("shared_sources") or [])
            source["status"] = "shared_sources_found" if shared_records else (
                "individual_sources_only" if a_records or b_records else "no_sources_resolved"
            )
            source["pair_query_semantics"] = fooddb_zero_result_semantics(
                query_available=True,
                compound_a_matched=str(a_summary.get("match_status") or "") == "matched",
                compound_b_matched=str(b_summary.get("match_status") or "") == "matched",
                shared_record_count=len(shared_records),
                individual_record_count=len(a_records) + len(b_records),
            )
            source["interpretation"] = self._food_interpretation(group, shared_records, a_records, b_records)

            technical_by_target: dict[tuple[str, str], dict[str, Any]] = {}
            for item in (group.get("technical") or {}).get("recommendations") or []:
                key = (
                    str(item.get("target_canonical_id") or ""),
                    _human_token(item.get("growth_stage")).casefold(),
                )
                technical_by_target[key] = item

            target_by_key: dict[tuple[str, str], dict[str, Any]] = {}
            for target in group.get("targets") or []:
                checked["target_rows"] += 1
                key = (
                    str(target.get("target_canonical_id") or ""),
                    _human_token(target.get("growth_stage")).casefold(),
                )
                target_by_key[key] = target
                identity = target.get("enzyme_identity") or {}
                atlas = target.get("target_atlas_validation") or {}
                identity_level = str(identity.get("identity_resolution_level") or "unresolved")
                if atlas.get("target_match_status") in {"validated", "validated_target"} and identity_level not in exact_identity_levels:
                    atlas.update({
                        "target_match_status": "family_context",
                        "target_match_basis": "identity_granularity_gate",
                        "target_match_confidence": min(float(atlas.get("target_match_confidence") or 0.5), 0.65),
                        "known_inhibitor_classes": [],
                        "known_inhibitor_class": None,
                    })
                    record(
                        "target_atlas_mapping_downgraded_for_identity_granularity",
                        pair=group.get("pair_label"),
                        target=target.get("target"),
                        identity_level=identity_level,
                    )
                if identity.get("source_dataset_family_conflict"):
                    target["source_dataset_family_conflict"] = True
                    record(
                        "source_dataset_family_conflict_tracked",
                        pair=group.get("pair_label"),
                        target=target.get("target"),
                        source=identity.get("source"),
                    )

                technical = technical_by_target.get(key) or {}
                selectivity = technical.get("scenario_selectivity") or {}
                checked["selectivity_rows"] += 1
                if (
                    str(selectivity.get("selectivity_scope") or "scenario_level") == "target_specific"
                    and not bool(selectivity.get("target_specific_evidence_present"))
                ):
                    selectivity.update({
                        "selectivity_scope": "scenario_level",
                        "selectivity_scope_label": "Scenario-level baseline applied to this target context",
                        "target_specific_evidence_present": False,
                        "target_specific_inputs": [],
                        "selectivity_scope_reason": (
                            "No paired crop-versus-weed sequence, expression, abundance, kinetic-sensitivity, or binding evidence was available for this target."
                        ),
                    })
                    target["selectivity_scope"] = "scenario_level"
                    target["scenario_selectivity_interpretation"] = _margin_interpretation(selectivity)
                    record(
                        "unsupported_target_specific_selectivity_downgraded",
                        pair=group.get("pair_label"),
                        target=target.get("target"),
                    )

            for band in (group.get("assay_prioritization") or {}).get("target_bands") or []:
                checked["assay_rows"] += 1
                key = (str(band.get("target_canonical_id") or ""), str(band.get("stage_key") or ""))
                target = target_by_key.get(key) or {}
                identity = target.get("enzyme_identity") or {}
                atlas = target.get("target_atlas_validation") or {}
                gating = _dedupe_text(list(band.get("gating_reasons") or []))
                source_conflict = bool(identity.get("source_dataset_family_conflict"))
                if source_conflict:
                    reason = "The source dataset family label conflicts with the canonical enzyme family and requires source-level review."
                    if reason not in gating:
                        gating.append(reason)
                model_only_support = any("model-derived or unresolved" in str(reason).casefold() for reason in gating)
                atlas_not_exact = atlas.get("target_match_status") not in {"validated", "validated_target"}
                code = str(band.get("scientific_priority_code") or "not_prioritizable")
                if code in high_priority_codes and (model_only_support or source_conflict or atlas_not_exact):
                    band.update({
                        "priority": "Exploratory scientific validation priority",
                        "scientific_priority": "Exploratory scientific validation priority",
                        "scientific_priority_code": "exploratory",
                        "scientific_priority_score": min(float(band.get("scientific_priority_score") or 0.49), 0.49),
                    })
                    record(
                        "scientific_priority_downgraded_by_evidence_gate",
                        pair=group.get("pair_label"),
                        target=band.get("target"),
                    )
                band["gating_reasons"] = gating

            bands = (group.get("assay_prioritization") or {}).get("target_bands") or []
            available_bands = [item for item in bands if item.get("status") == "available"]
            priority_order = {
                "High scientific validation priority": 4,
                "Moderate scientific validation priority": 3,
                "Exploratory scientific validation priority": 2,
                "Not prioritizable until target identity is resolved": 1,
                "Not prioritizable": 0,
            }
            if available_bands:
                values = [str(item.get("scientific_priority") or item.get("priority")) for item in available_bands]
                counts = {value: values.count(value) for value in sorted(set(values))}
                best = max(values, key=lambda value: priority_order.get(value, 0))
                floor = min(values, key=lambda value: priority_order.get(value, 0))
                group["assay_prioritization"].update({
                    "priority_distribution": counts,
                    "best_supported_priority": best,
                    "most_conservative_priority": floor,
                    "overall_priority": best if len(counts) == 1 else (
                        f"Mixed scientific priorities — best supported: {best}; conservative floor: {floor}"
                    ),
                })

        unique_corrections = list(dict.fromkeys(corrections))
        return {
            "status": "corrected" if unique_corrections else "passed",
            "corrections": unique_corrections,
            "correction_details": details,
            "checked_rows": checked,
            "policy": (
                "compound-specific FoodDB ownership, unique-match source suppression, identity-granularity target gating, "
                "selectivity-scope validation, and evidence-adjusted priority gating"
            ),
        }

    @staticmethod
    def _synthesis_facts(pair_groups: list[dict[str, Any]], unique_targets: list[str]) -> dict[str, Any]:
        shared_pairs = [
            group["pair_label"]
            for group in pair_groups
            if group.get("natural_source_context", {}).get("status") == "shared_sources_found"
        ]
        target_contexts = sum(len(group.get("targets", [])) for group in pair_groups)
        available_contexts = sum(
            int(group.get("assay_prioritization", {}).get("available_target_count") or 0)
            for group in pair_groups
        )
        unavailable_contexts = sum(
            int(group.get("assay_prioritization", {}).get("unavailable_target_count") or 0)
            for group in pair_groups
        )
        pairs_with_any_assay = sum(
            1 for group in pair_groups
            if int(group.get("assay_prioritization", {}).get("available_target_count") or 0) > 0
        )
        validated_atlas_contexts = sum(
            1
            for group in pair_groups
            for target in group.get("targets", [])
            if (target.get("target_atlas_validation") or {}).get("target_match_status") in {"validated", "validated_target"}
        )
        validated_target_ids = {
            str(target.get("target_canonical_id"))
            for group in pair_groups
            for target in group.get("targets", [])
            if (target.get("target_atlas_validation") or {}).get("target_match_status") in {"validated", "validated_target"}
        }
        family_context_count = sum(
            1 for group in pair_groups for target in group.get("targets", [])
            if (target.get("target_atlas_validation") or {}).get("target_match_status") == "family_context"
        )
        coverage_counts = {
            status: sum(
                1
                for group in pair_groups
                if str(group.get("assay_prioritization", {}).get("coverage_status") or "unavailable") == status
            )
            for status in ("complete", "partial", "unavailable")
        }
        priority_counts = {
            code: sum(
                1
                for group in pair_groups
                for item in group.get("assay_prioritization", {}).get("target_bands", [])
                if str(item.get("scientific_priority_code") or "not_prioritizable") == code
            )
            for code in ("high", "moderate", "exploratory", "not_prioritizable")
        }
        return {
            "pair_count": len(pair_groups),
            "unique_target_count": len(unique_targets),
            "target_context_count": target_contexts,
            "shared_food_occurrence_pair_count": len(shared_pairs),
            "shared_food_occurrence_pairs": shared_pairs,
            "assay_available_target_context_count": available_contexts,
            "assay_unavailable_target_context_count": unavailable_contexts,
            "pairs_with_any_assay_simulation": pairs_with_any_assay,
            "assay_pair_coverage_counts": coverage_counts,
            "scientific_priority_context_counts": priority_counts,
            "high_or_moderate_scientific_priority_context_count": priority_counts["high"] + priority_counts["moderate"],
            "exploratory_scientific_priority_context_count": priority_counts["exploratory"],
            "not_prioritizable_context_count": priority_counts["not_prioritizable"],
            "validated_target_atlas_context_count": validated_atlas_contexts,
            "unique_validated_target_identity_count": len(validated_target_ids),
            "family_process_context_count": family_context_count,
            "food_occurrence_boundary": (
                "Shared FoodDB occurrence is contextual database evidence only; it is not a validated, extractable, effective, or safe intervention source."
            ),
            "assay_boundary": (
                "Assay bands are dimensionless normalized model-input ranges and are not concentrations, doses, formulations, or field rates."
            ),
        }

    @staticmethod
    def _synthesis_violations(text: str, facts: dict[str, Any]) -> list[str]:
        """Detect model statements that conflict with deterministic report facts.

        This is intentionally conservative. Any ambiguous universal claim is
        rejected when the structured payload contains partial or missing coverage.
        """

        lowered = re.sub(r"\s+", " ", str(text or "").casefold()).strip()
        violations: list[str] = []
        shared_count = int(facts.get("shared_food_occurrence_pair_count") or 0)
        unavailable = int(facts.get("assay_unavailable_target_context_count") or 0)
        not_prioritizable = int(facts.get("not_prioritizable_context_count") or 0)
        high_or_moderate = int(facts.get("high_or_moderate_scientific_priority_context_count") or 0)

        denies_shared_occurrence = bool(
            re.search(
                r"(?:\bno pair\b|\bnone of (?:the )?pairs\b|\bno shared\b|\bwithout shared\b)"
                r"[^.]{0,180}(?:food|ingredient|source|occurr)",
                lowered,
            )
        )
        asserts_shared_occurrence = bool(
            re.search(
                r"(?:\bone pair\b|\bsome pairs?\b|\ba pair\b|\b[1-9][0-9]* pairs?\b)"
                r"[^.]{0,160}(?:shared|co-occurr)[^.]{0,120}(?:food|ingredient|source|occurr)",
                lowered,
            )
        )
        if shared_count > 0 and denies_shared_occurrence:
            violations.append("shared_food_occurrence_contradiction")
        if shared_count == 0 and asserts_shared_occurrence:
            violations.append("invented_shared_food_occurrence")

        universal_assay_claim = bool(
            re.search(
                r"(?:\ball (?:pairs?|targets?|candidates?|assays?)\b|\bevery (?:pair|target|candidate|assay)\b)"
                r"[^.]{0,160}(?:high(?: relative)? assay priority|assay priority|assays? (?:are|is) available|available assay)",
                lowered,
            )
            or re.search(r"\ball assays? (?:are|were|remain) available\b", lowered)
        )
        if unavailable > 0 and universal_assay_claim:
            violations.append("assay_coverage_overstatement")

        if re.search(
            r"\b(?:strongest|best|highest) (?:scientific )?evidence\b[^.]{0,140}"
            r"\b(?:complete|full) (?:assay|simulation) coverage\b",
            lowered,
        ):
            violations.append("simulation_coverage_misrepresented_as_evidence_strength")

        if not_prioritizable > 0 and re.search(
            r"\ball (?:targets?|contexts?|target-pair contexts?)\b[^.]{0,100}\bexploratory\b",
            lowered,
        ):
            violations.append("not_prioritizable_contexts_omitted")

        positive_high_or_moderate_claim = bool(
            re.search(
                r"\b(?:[1-9][0-9]*|some|several|multiple|one or more)\b[^.]{0,100}"
                r"\b(?:high|moderate) scientific (?:validation )?priorit(?:y|ies)\b",
                lowered,
            )
            or re.search(
                r"\b(?:reached|achieved|received|were assigned|are assigned)\b[^.]{0,80}"
                r"\b(?:high|moderate) scientific (?:validation )?priorit(?:y|ies)\b",
                lowered,
            )
        )
        if high_or_moderate == 0 and positive_high_or_moderate_claim and not re.search(
            r"\b(?:no|none|zero)\b[^.]{0,100}\b(?:high|moderate) scientific",
            lowered,
        ):
            violations.append("invented_high_or_moderate_scientific_priority")

        if re.search(
            r"\b(?:confirmed|validated|effective|safe)\b[^.]{0,80}"
            r"\b(?:natural source|food source|ingredient source|co-occurrence|intervention source)\b",
            lowered,
        ):
            violations.append("food_source_usability_overstatement")
        if re.search(
            r"\b(?:field[- ]ready|validated for field|proven efficacy|proven effective|proven safe|"
            r"confirmed efficacy|confirmed safety|safe for crops?|effective weed control)\b",
            lowered,
        ):
            violations.append("practical_validation_overstatement")

        # Preserve stable ordering and avoid duplicate correction codes.
        return list(dict.fromkeys(violations))

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
        facts = self._synthesis_facts(pair_groups, unique_targets)
        leading = pair_groups[0] if pair_groups else None
        shared_count = facts["shared_food_occurrence_pair_count"]
        available = facts["assay_available_target_context_count"]
        unavailable = facts["assay_unavailable_target_context_count"]
        total_contexts = available + unavailable
        priority_counts = facts["scientific_priority_context_counts"]
        exploratory = priority_counts["exploratory"]
        not_prioritizable = priority_counts["not_prioritizable"]
        high_or_moderate = facts["high_or_moderate_scientific_priority_context_count"]
        coverage = facts["assay_pair_coverage_counts"]

        if leading:
            priority_sentence = (
                f"Evidence-adjusted validation classified {exploratory} target-pair contexts as exploratory and "
                f"{not_prioritizable} as not prioritizable; no context reached high or moderate scientific priority."
                if high_or_moderate == 0
                else (
                    f"Evidence-adjusted validation classified {priority_counts['high']} contexts as high, "
                    f"{priority_counts['moderate']} as moderate, {exploratory} as exploratory, and "
                    f"{not_prioritizable} as not prioritizable."
                )
            )
            executive = (
                f"For {crop} versus {weed} at {stage}, PESI screened {facts['pair_count']} unique compound pairs across "
                f"{facts['unique_target_count']} canonical enzyme targets. The highest model-screening group, {leading['pair_label']}, "
                f"contains {len(leading.get('targets') or [])} retained target contexts, including "
                f"{', '.join(target['target'] for target in leading['targets'][:3])}. {priority_sentence} "
                f"FoodDB identified shared occurrence context for {shared_count} pair{'s' if shared_count != 1 else ''}; this does not establish a usable intervention source. "
                f"Relative assay simulations were available for {available} of {total_contexts} target-pair contexts, with {unavailable} unavailable; "
                f"{coverage['complete']} pairs had complete simulation coverage and {coverage['partial']} had partial coverage."
            )
        else:
            executive = f"No candidate pairs were available for {crop} versus {weed} at {stage}."

        canonical_findings = [
            f"{facts['pair_count']} unique compound pairs were retained after grouping repeated target-specific rows.",
            f"{facts['unique_target_count']} distinct enzyme targets are represented in {facts['target_context_count']} target-pair contexts.",
            f"{shared_count} pair{'s have' if shared_count != 1 else ' has'} shared FoodDB occurrence records; no food or ingredient is validated as an extractable, effective, or safe intervention source.",
            f"Assay simulations were available for {available} target-pair contexts and unavailable for {unavailable}; available bands use dimensionless normalized model-input units.",
            (
                f"Evidence-adjusted scientific priority: {priority_counts['high']} high, {priority_counts['moderate']} moderate, "
                f"{exploratory} exploratory, and {not_prioritizable} not prioritizable target-pair contexts. "
                "Simulation coverage is reported separately and is not treated as evidence strength."
            ),
            f"{facts['unique_validated_target_identity_count']} unique target identities ({facts['validated_target_atlas_context_count']} target-pair contexts) passed strict target-specific atlas validation; {facts['family_process_context_count']} contexts retained only broad family/process annotation.",
        ]
        fallback = {
            "status": "ok",
            "executive_summary": executive,
            "key_findings": canonical_findings,
            "scenario_interpretation": (
                f"The crop/weed frame is {crop} versus {weed} at {stage}. Current vulnerability values are labelled by scope. "
                "Where paired crop-versus-weed target evidence is absent, the values are scenario-level baselines applied to target contexts rather than target-specific selectivity estimates. "
                f"The centered selectivity index is retained only for ranking. Of {facts['target_context_count']} target-pair contexts, "
                f"{exploratory} are exploratory and {not_prioritizable} are not prioritizable under the current evidence gate. "
                "Complete simulation coverage does not imply stronger biological evidence."
            ),
            "ai_source": "deterministic_fallback",
            "ai_status": "fallback_validated",
            "semantic_validation": {"status": "passed", "corrections": [], "facts": facts},
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
                "assay_coverage_status": group.get("assay_prioritization", {}).get("coverage_status"),
                "assay_available_target_count": group.get("assay_prioritization", {}).get("available_target_count"),
                "assay_unavailable_target_count": group.get("assay_prioritization", {}).get("unavailable_target_count"),
                "scientific_priority_counts": {
                    code: sum(1 for item in group.get("assay_prioritization", {}).get("target_bands", []) if item.get("scientific_priority_code") == code)
                    for code in ("high", "moderate", "exploratory", "not_prioritizable")
                },
            })
        system = (
            "You produce a concise scientific executive synthesis for PESI computational plant-enzyme screening. "
            "Use only the supplied JSON and treat canonical_facts as immutable. Do not repeat rows. Group findings by unique compound pair. "
            "Distinguish direct occurrence evidence, curated reference evidence, user scenario context, model inference, proxies, and uncertainty. "
            "Never describe shared FoodDB occurrence as a confirmed, extractable, effective, or safe intervention source. "
            "Never say all assays are available or high priority when canonical_facts report unavailable contexts. Distinguish simulation-derived response rank from evidence-adjusted scientific validation priority. "
            "Never describe complete simulation coverage as stronger scientific evidence. Never say all targets or contexts are exploratory when canonical_facts include not-prioritizable contexts. "
            "State high, moderate, exploratory, and not-prioritizable context counts exactly as canonical_facts report them. "
            "Do not claim efficacy, concentration, dose, formulation, safety, field performance, or field readiness. "
            "Return JSON with keys: status, executive_summary, key_findings, scenario_interpretation. key_findings must be a short list."
        )
        user = json.dumps(to_json_safe({
            "report_type": report_type,
            "scenario": scenario,
            "canonical_facts": facts,
            "pair_groups": compact_pairs,
            "food_mapping": food_mapping,
            "required_caveats": caveats,
        }), indent=2, allow_nan=False)
        response = self.llm.complete_json(system=system, user=user, fallback=fallback)

        merged = dict(fallback)
        ai_source = response.get("ai_source") if isinstance(response, dict) else None
        if isinstance(response, dict):
            for key in ("executive_summary", "scenario_interpretation"):
                value = response.get(key)
                if isinstance(value, str) and value.strip():
                    merged[key] = value.strip()
        # Canonical findings are deterministic and cannot be replaced by model text.
        merged["key_findings"] = canonical_findings
        merged["ai_source"] = ai_source or "deterministic_fallback"

        combined_text = f"{merged.get('executive_summary', '')} {merged.get('scenario_interpretation', '')}"
        violations = self._synthesis_violations(combined_text, facts)
        if violations:
            merged["executive_summary"] = fallback["executive_summary"]
            merged["scenario_interpretation"] = fallback["scenario_interpretation"]
            merged["ai_status"] = "generated_corrected" if merged["ai_source"] == "deepseek" else "fallback_corrected"
            merged["semantic_validation"] = {
                "status": "corrected",
                "corrections": violations,
                "facts": facts,
            }
        else:
            merged["ai_status"] = "generated_validated" if merged["ai_source"] == "deepseek" else "fallback_validated"
            merged["semantic_validation"] = {
                "status": "passed",
                "corrections": [],
                "facts": facts,
            }
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
                    bands.append(f"{item.get('target')}: {item.get('scientific_priority')} [{item.get('simulation_priority')}] (dimensionless normalized model-input band {band})")
                else:
                    bands.append(f"{item.get('target')}: simulation unavailable")
            assay_lines.append(f"{index}. {group['pair_label']}: {'; '.join(bands) or 'simulation unavailable'}.")
        return [
            {"title": "Executive synthesis", "body": _safe(synthesis.get("executive_summary"))},
            {"title": "Scenario-specific interpretation", "body": f"{crop} versus {weed} at {stage}. {_safe(synthesis.get('scenario_interpretation'))}"},
            {"title": "Grouped candidate-pair findings", "body": "\n".join(pair_lines) or "No candidate pairs were available."},
            {"title": "Natural source context", "body": ("\n".join(source_lines) or "No FoodDB occurrence context was resolved.") + f"\n\n{FOOD_SOURCE_CAVEAT}"},
            {"title": "Named evidence provenance", "body": "\n".join(provenance_lines) or "No named provenance was resolved."},
            {"title": "Evidence confidence and limitations", "body": "Each grouped pair separates direct database occurrence evidence, curated reference evidence, user-provided scenario context, model inference, proxy estimates, and unresolved assumptions. The detailed classifications are shown in the grouped pair records and technical appendix."},
            {"title": "Assay prioritization", "body": "\n".join(assay_lines) or "No assay-prioritization simulation was available."},
            {"title": "Validation roadmap", "body": "Confirm target engagement, pair interaction, controlled dose-response behavior, comparative crop tolerance and weed response, toxicity, environmental persistence, and source extractability before any practical development decision."},
            {"title": "Interpretation method", "body": f"{interpretation_mode['label']}. The main report translates internal tokens and scores into scientific language. Raw scores, artifact names, and model fields are retained only in the technical appendix."},
        ]

    def render_html(self, report: dict[str, Any]) -> str:
        report = to_json_safe(report)

        def esc(value: Any) -> str:
            return html.escape(_safe(value, ""))

        interpretation = report.get("interpretation_mode") or {}
        summary = report.get("executive_summary") or {}
        key_findings = "".join(f"<li>{esc(item)}</li>" for item in summary.get("key_findings") or [])
        pair_html = "".join(self._pair_html(group, esc) for group in report.get("pair_groups") or [])
        caveats = "".join(f"<li>{esc(item)}</li>" for item in report.get("caveats") or [])
        appendix_json = esc(json.dumps(to_json_safe(report.get("technical_appendix") or {}), indent=2, default=str, allow_nan=False))
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
        target_rows: list[str] = []
        for item in group.get("targets") or []:
            atlas = item.get("target_atlas_validation") or {}
            if atlas.get("target_match_status") in {"validated", "validated_target"}:
                atlas_note = (
                    f"Validated target-atlas mapping: {atlas.get('herbicide_target_family')} "
                    f"({str(atlas.get('target_match_basis') or '').replace('_', ' ')}, confidence {atlas.get('target_match_confidence')})"
                )
            elif atlas.get("target_match_status") == "family_context":
                atlas_note = "Broad family/process context only; no target-specific inhibitor-class mapping"
            else:
                atlas_note = "No validated target-specific pathway or inhibitor-class mapping"
            target_rows.append(
                f"<tr><td><strong>{esc(item.get('target'))}</strong><br>{esc(item.get('target_family'))}<br><small>Canonical ID: {esc(item.get('target_canonical_id'))}; family validation: {esc((item.get('enzyme_identity') or {}).get('family_validation_status'))}</small><br><small>{esc(atlas_note)}</small></td>"
                f"<td>{esc(item.get('growth_stage'))}</td><td>{esc(item.get('enzyme_state_interpretation'))}</td>"
                f"<td>{esc(item.get('scenario_selectivity_interpretation'))}</td></tr>"
            )
        targets = "".join(target_rows)

        source = group.get("natural_source_context") or {}
        compound_a = source.get("compound_a") or {}
        compound_b = source.get("compound_b") or {}
        shared_pills = "".join(f"<span class='source-pill'>{esc(name)}</span>" for name in source.get("shared_source_names") or [])
        a_pills = "".join(f"<span class='source-pill'>{esc(name)}</span>" for name in compound_a.get("top_source_names") or [])
        b_pills = "".join(f"<span class='source-pill'>{esc(name)}</span>" for name in compound_b.get("top_source_names") or [])
        provenance = "".join(
            f"<li><strong>{esc(item.get('source'))}</strong> — {esc(item.get('supports'))} <em>({esc(item.get('evidence_tier'))})</em></li>"
            for item in (group.get("evidence_provenance") or [])[:16]
        )
        confidence = group.get("confidence") or {}
        assay_rows = "".join(
            f"<tr><td>{esc(item.get('target'))}</td><td>{esc(item.get('simulation_priority'))}</td><td>{esc(item.get('scientific_priority'))}<br><small>Evidence-adjusted score: {esc(item.get('scientific_priority_score'))}</small></td>"
            f"<td>{esc(item.get('relative_input_band') if item.get('status') == 'available' else 'Not available')}<br><small>{esc(item.get('units_label') if item.get('status') == 'available' else '')}</small></td>"
            f"<td>{esc(_join_sentences(item.get('gating_reasons') or []) or item.get('interpretation'))}</td></tr>"
            for item in group.get("assay_prioritization", {}).get("target_bands", [])
        )
        assay_summary = group.get("assay_prioritization", {})
        return f"""<article class="pair"><div class="pair-head"><div><h3>{esc(group.get('pair_label'))}</h3><p>{esc(group.get('target_count'))} target context(s) retained after grouping repeated rows.</p></div><span class="badge strength">Model screening rank: {esc(group.get('evidence_strength'))}</span></div>
<div class="panel"><h3>Target, enzyme-state, and scenario interpretation</h3><table><thead><tr><th>Target and atlas validation</th><th>Stage</th><th>Enzyme-state interpretation</th><th>Scenario selectivity</th></tr></thead><tbody>{targets}</tbody></table></div>
<div class="grid"><div class="subpanel"><h3>Natural source context</h3><p>{esc(source.get('interpretation'))}</p>
<p><strong>{esc(compound_a.get('compound'))}</strong><br>FoodDB status: {esc(compound_a.get('match_status_label'))}<br>Match method: {esc(compound_a.get('match_method'))}<br>Confidence: {esc(compound_a.get('match_confidence_label'))}<br>Resolved occurrence records: {esc(compound_a.get('source_count'))}</p><div class="source-list">{a_pills or '<span class="source-pill">No source names resolved</span>'}</div>
<p><strong>{esc(compound_b.get('compound'))}</strong><br>FoodDB status: {esc(compound_b.get('match_status_label'))}<br>Match method: {esc(compound_b.get('match_method'))}<br>Confidence: {esc(compound_b.get('match_confidence_label'))}<br>Resolved occurrence records: {esc(compound_b.get('source_count'))}</p><div class="source-list">{b_pills or '<span class="source-pill">No source names resolved</span>'}</div>
<p><strong>Pair-level FoodDB query:</strong> {esc((source.get('pair_query_semantics') or {}).get('label'))}</p><p>{esc((source.get('pair_query_semantics') or {}).get('interpretation'))}</p>
<p><strong>Shared FoodDB occurrence records</strong></p><div class="source-list">{shared_pills or '<span class="source-pill">No shared occurrence established</span>'}</div></div>
<div class="subpanel"><h3>Evidence confidence</h3><p>{esc(confidence.get('summary'))}</p>
<p><strong>Direct database occurrence:</strong> {esc(', '.join(confidence.get('direct_occurrence_evidence') or []) or 'None')}</p>
<p><strong>Curated reference evidence:</strong> {esc(', '.join(confidence.get('curated_reference_evidence') or []) or 'None')}</p>
<p><strong>User scenario context:</strong> {esc(', '.join(confidence.get('scenario_context') or []) or 'None')}</p>
<p><strong>Model inference:</strong> {esc(', '.join(confidence.get('model_inference') or []) or 'None')}</p>
<p><strong>Proxy estimates:</strong> {esc(', '.join(confidence.get('proxy_assumptions') or []) or 'None')}</p>
<p><strong>Unresolved assumptions:</strong> {esc(', '.join(confidence.get('weak_or_unsupported_assumptions') or []) or 'None identified')}</p></div></div>
<div class="panel"><h3>Named evidence provenance</h3><ul>{provenance or '<li>No named provenance was resolved.</li>'}</ul></div>
<div class="panel"><h3>Assay prioritization: simulation versus scientific evidence</h3><p><strong>{esc(assay_summary.get('overall_priority'))}</strong> — coverage: {esc(assay_summary.get('coverage_status'))}; available target contexts: {esc(assay_summary.get('available_target_count'))}; unavailable: {esc(assay_summary.get('unavailable_target_count'))}.</p><table><thead><tr><th>Target</th><th>Simulation-derived rank</th><th>Evidence-adjusted scientific priority</th><th>Dimensionless normalized model-input band</th><th>Scientific gating</th></tr></thead><tbody>{assay_rows}</tbody></table><p>Simulation rank does not establish scientific priority. Evidence-adjusted priority also requires canonical identity, family validation, target-specific evidence, and biological support.</p></div></article>"""
