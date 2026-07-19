from __future__ import annotations

import math
import re
from typing import Any


EVIDENCE_TIER_LABELS: dict[str, str] = {
    "direct_occurrence": "direct database occurrence evidence",
    "curated_reference": "curated reference evidence",
    "scenario_context": "user-provided scenario context",
    "model_inference": "model-derived inference",
    "proxy_estimate": "proxy estimate",
    "unresolved": "unresolved or unsupported evidence",
    "unmapped": "no validated target-specific mapping",
    "database_query_no_shared_occurrence": "database query returned no shared occurrence",
    "compound_unmatched": "compound could not be mapped to the queried database",
    "database_unavailable": "database evidence unavailable",
}


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_selectivity(
    *,
    weed_vulnerability: Any,
    crop_vulnerability: Any,
    reported_margin: Any = None,
    reported_index: Any = None,
) -> dict[str, Any]:
    """Return scientifically explicit selectivity semantics.

    `selectivity_difference` is weed vulnerability minus crop vulnerability and
    therefore ranges from -1 to +1. `selectivity_index` is the historical PESI
    centered index (difference + 0.5, clipped to 0..1) retained solely for
    backward-compatible ranking. The two values must never be described as the
    same quantity.
    """

    weed = finite_float(weed_vulnerability)
    crop = finite_float(crop_vulnerability)
    reported_margin_value = finite_float(reported_margin)
    reported_index_value = finite_float(reported_index)

    difference: float | None = None
    computed_index: float | None = None
    if weed is not None and crop is not None:
        difference = max(-1.0, min(1.0, weed - crop))
        computed_index = max(0.0, min(1.0, difference + 0.5))

    legacy_encoded = False
    if difference is not None and reported_margin_value is not None:
        legacy_expected = max(0.0, min(1.0, difference + 0.5))
        legacy_encoded = (
            abs(reported_margin_value - legacy_expected) <= 0.015
            and abs(reported_margin_value - difference) > 0.015
        )

    if reported_index_value is not None:
        selectivity_index = max(0.0, min(1.0, reported_index_value))
    elif legacy_encoded:
        selectivity_index = max(0.0, min(1.0, reported_margin_value))
    elif computed_index is not None:
        selectivity_index = computed_index
    else:
        selectivity_index = None

    if difference is None and reported_margin_value is not None and not legacy_encoded:
        difference = max(-1.0, min(1.0, reported_margin_value))

    if difference is None:
        direction = "unresolved"
    elif difference >= 0.25:
        direction = "materially_higher_modeled_weed_vulnerability"
    elif difference > 0.05:
        direction = "small_positive_modeled_separation"
    elif difference >= -0.05:
        direction = "no_material_modeled_separation"
    else:
        direction = "modeled_crop_vulnerability_concern"

    return {
        "weed_vulnerability": weed,
        "crop_vulnerability": crop,
        "selectivity_difference": round(difference, 6) if difference is not None else None,
        "selectivity_index": round(selectivity_index, 6) if selectivity_index is not None else None,
        "reported_selectivity_value": reported_margin_value,
        "legacy_centered_index_detected": legacy_encoded,
        "direction": direction,
        "difference_definition": "weed_vulnerability minus crop_vulnerability",
        "index_definition": "historical PESI ranking index: clip(selectivity_difference + 0.5, 0, 1)",
    }


def normalize_fooddb_match(detail: dict[str, Any] | None, *, source_count: int = 0) -> dict[str, Any]:
    detail = detail or {}
    match = detail.get("match") or {}
    raw_status = str(
        match.get("match_status")
        or detail.get("match_status")
        or detail.get("status")
        or ""
    ).strip().casefold()
    method = str(match.get("match_method") or "").strip()
    method_key = method.casefold()
    name = match.get("fooddb_compound_name")
    confidence = finite_float(match.get("match_confidence"))

    unmatched_tokens = {"unmatched", "not_matched", "missing", "not_available", "none"}
    ambiguous_tokens = {"ambiguous", "multiple_matches", "needs_review"}
    is_unmatched = raw_status in unmatched_tokens or method_key in unmatched_tokens or not match
    is_ambiguous = raw_status in ambiguous_tokens or method_key in ambiguous_tokens

    if is_ambiguous:
        status = "ambiguous"
        label = "Ambiguous FoodDB match"
        method_label = method.replace("_", " ") if method else "Review required"
        confidence_label = "Unresolved"
    elif is_unmatched:
        status = "unmatched"
        label = "No FoodDB compound match"
        method_label = "Not applicable"
        confidence_label = "Unresolved"
        confidence = None
        name = None
    else:
        status = "matched"
        label = "Matched to FoodDB"
        method_label = method.replace("_", " ") if method else "Validated identifier or exact-name match"
        if confidence is None:
            confidence_label = "Not quantified"
        elif confidence >= 0.85:
            confidence_label = "Strong"
        elif confidence >= 0.65:
            confidence_label = "Moderate"
        else:
            confidence_label = "Limited"

    occurrence_status = "reported_occurrences_found" if source_count > 0 else "no_occurrences_resolved"
    return {
        "status": status,
        "status_label": label,
        "fooddb_compound_name": name,
        "match_method": method_label,
        "match_confidence": confidence,
        "match_confidence_label": confidence_label,
        "occurrence_status": occurrence_status,
        "source_count": int(source_count),
    }


def classify_evidence_source(
    source: Any,
    evidence_class: Any = None,
    *,
    has_occurrence_record: bool = False,
) -> str:
    """Conservatively classify evidence without upgrading inference to direct evidence."""

    text = f"{source or ''} {evidence_class or ''}".casefold()
    text = re.sub(r"\s+", " ", text)

    if "fooddb" in text:
        return "direct_occurrence" if has_occurrence_record else "unresolved"
    if any(token in text for token in ("unsupported", "unresolved", "unmapped", "not_available")):
        return "unresolved"
    if any(token in text for token in ("proxy", "pseudo_lab", "pseudo-lab", "simulation")):
        return "proxy_estimate"
    if any(token in text for token in (
        ".xlsx", "cazy", "skid", "curated", "literature_rule", "literature rule",
        "herbicide target atlas", "reference",
    )):
        return "curated_reference"
    if any(token in text for token in (
        "scenario context", "user-provided scenario", "field scenario",
    )):
        return "scenario_context"
    if any(token in text for token in (
        "weed_assignment", "crop/weed assignment", "critical-transition", "critical transition",
        "optimized", "ranking", "model", "inference", "synergy", "stage model",
    )):
        return "model_inference"
    if any(token in text for token in ("direct", "measured", "experimental")):
        # Unknown 'direct' claims are not promoted beyond curated-reference level
        # without an occurrence/measurement record in the payload.
        return "curated_reference"
    return "unresolved"


def evidence_tier_label(tier: str) -> str:
    return EVIDENCE_TIER_LABELS.get(tier, EVIDENCE_TIER_LABELS["unresolved"])



def classify_selectivity_scope(*payloads: dict[str, Any] | None) -> dict[str, Any]:
    """Label whether crop/weed selectivity is scenario-level or target-specific.

    A target-specific label requires paired crop-versus-weed evidence tied to the
    target itself. A target criticality score, growth-stage assignment, or a
    generic crop/weed scenario does not satisfy that requirement.
    """

    merged: dict[str, Any] = {}
    for payload in payloads:
        if isinstance(payload, dict):
            merged.update(payload)

    paired_fields = (
        ("weed_target_expression", "crop_target_expression"),
        ("weed_target_abundance", "crop_target_abundance"),
        ("weed_binding_score", "crop_binding_score"),
        ("weed_target_sensitivity", "crop_target_sensitivity"),
        ("weed_sequence_identity", "crop_sequence_identity"),
        ("weed_kinetic_sensitivity", "crop_kinetic_sensitivity"),
    )
    used: list[str] = []
    for weed_key, crop_key in paired_fields:
        if finite_float(merged.get(weed_key)) is not None and finite_float(merged.get(crop_key)) is not None:
            used.extend([weed_key, crop_key])

    explicit_scope = str(merged.get("selectivity_scope") or "").strip().casefold()
    if explicit_scope == "target_specific" and used:
        return {
            "selectivity_scope": "target_specific",
            "selectivity_scope_label": "Target-specific comparative model",
            "target_specific_evidence_present": True,
            "target_specific_inputs": used,
            "selectivity_scope_reason": "Paired crop-versus-weed target evidence was available.",
        }
    if used:
        return {
            "selectivity_scope": "target_specific",
            "selectivity_scope_label": "Target-specific comparative model",
            "target_specific_evidence_present": True,
            "target_specific_inputs": used,
            "selectivity_scope_reason": "Paired crop-versus-weed target evidence was detected.",
        }
    return {
        "selectivity_scope": "scenario_level",
        "selectivity_scope_label": "Scenario-level baseline applied to this target context",
        "target_specific_evidence_present": False,
        "target_specific_inputs": [],
        "selectivity_scope_reason": (
            "No paired crop-versus-weed sequence, expression, abundance, kinetic-sensitivity, or binding evidence was available for this target."
        ),
    }


def fooddb_zero_result_semantics(
    *,
    query_available: bool,
    compound_a_matched: bool,
    compound_b_matched: bool,
    shared_record_count: int,
    individual_record_count: int = 0,
) -> dict[str, Any]:
    """Distinguish occurrence, zero-result, unmatched, and unavailable states."""

    shared_record_count = max(0, int(shared_record_count or 0))
    individual_record_count = max(0, int(individual_record_count or 0))
    if not query_available:
        return {
            "status": "database_unavailable",
            "evidence_tier": "database_unavailable",
            "label": "FoodDB evidence unavailable",
            "interpretation": "The FoodDB query artifact was unavailable; no occurrence conclusion can be drawn.",
        }
    if shared_record_count > 0:
        return {
            "status": "shared_occurrence_found",
            "evidence_tier": "direct_occurrence",
            "label": f"{shared_record_count} shared FoodDB occurrence record(s)",
            "interpretation": "Direct database occurrence records were resolved for both mapped compounds.",
        }
    if not compound_a_matched or not compound_b_matched:
        return {
            "status": "compound_unmatched",
            "evidence_tier": "compound_unmatched",
            "label": "No shared occurrence resolved because one or both compounds were unmatched",
            "interpretation": (
                "The available mapping could not resolve both compounds in FoodDB. This is not evidence that shared biological occurrence is absent."
            ),
        }
    return {
        "status": "database_query_no_shared_occurrence",
        "evidence_tier": "database_query_no_shared_occurrence",
        "label": "FoodDB query returned no shared occurrence",
        "interpretation": (
            "Both compounds were mapped, but the available FoodDB query returned no shared occurrence record. This is a database zero-result, not proof of biological absence."
        ),
        "individual_record_count": individual_record_count,
    }


def evidence_adjusted_assay_priority(
    *,
    simulation: dict[str, Any] | None,
    identity: dict[str, Any] | None,
    target_atlas: dict[str, Any] | None,
    state_signals: dict[str, Any] | None,
    compound_target_evidence_tier: str = "model_inference",
) -> dict[str, Any]:
    """Convert a simulation rank into a scientifically evidence-adjusted priority.

    A high simulated response is not sufficient for a high scientific priority.
    Identity quality, family validation, target-specific atlas mapping, direct or
    curated compound-target support, and biological evidence layers are required.
    """

    simulation = simulation or {}
    identity = identity or {}
    target_atlas = target_atlas or {}
    state_signals = state_signals or {}

    if simulation.get("status") != "available":
        return {
            "scientific_priority": "Not prioritizable",
            "scientific_priority_code": "not_prioritizable",
            "scientific_priority_score": 0.0,
            "simulation_priority": "Simulation unavailable",
            "gating_reasons": ["No assay-prioritization simulation was available."],
            "supporting_factors": [],
        }

    level = str(identity.get("identity_resolution_level") or "unresolved")
    identity_score = {
        "exact_enzyme": 0.22,
        "exact_target": 0.22,
        "identifier_only": 0.17,
        "subfamily": 0.14,
        "family": 0.11,
        "functional_category": 0.05,
    }.get(level, 0.0)
    family_status = str(identity.get("family_validation_status") or "unresolved")
    family_score = {
        "validated": 0.08,
        "refined": 0.07,
        "compatible_broad": 0.03,
        "missing": 0.02,
        "conflict_corrected": 0.03,
    }.get(family_status, 0.0)
    source_dataset_conflict = bool(identity.get("source_dataset_family_conflict"))
    source_dataset_penalty = 0.08 if source_dataset_conflict else 0.0

    atlas_status = str(target_atlas.get("target_match_status") or "unmapped")
    atlas_score = {
        "validated_target": 0.18,
        "validated": 0.18,  # backwards compatibility
        "family_context": 0.05,
        "unmapped": 0.0,
    }.get(atlas_status, 0.0)

    kinetic = max(0.0, min(1.0, finite_float(state_signals.get("kinetic_evidence")) or 0.0))
    structure = max(0.0, min(1.0, finite_float(state_signals.get("structure_evidence")) or 0.0))
    plant = max(0.0, min(1.0, finite_float(state_signals.get("plant_context")) or 0.0))
    uncertainty = max(0.0, min(1.0, finite_float(state_signals.get("uncertainty_penalty")) or 0.0))
    biological_score = 0.12 * kinetic + 0.10 * structure + 0.10 * plant

    tier_score = {
        "direct_occurrence": 0.0,  # occurrence does not prove target engagement
        "direct_measurement": 0.17,
        "curated_target_evidence": 0.12,
        "curated_reference": 0.08,
        "model_inference": 0.025,
        "proxy_estimate": 0.0,
        "unresolved": 0.0,
    }.get(str(compound_target_evidence_tier), 0.0)

    maximum = finite_float(simulation.get("simulated_max_inhibition"))
    simulation_score = 0.0 if maximum is None else 0.08 * max(0.0, min(1.0, maximum))
    score = max(0.0, min(1.0, identity_score + family_score + atlas_score + biological_score + tier_score + simulation_score - 0.12 * uncertainty - source_dataset_penalty))

    supporting: list[str] = []
    gating: list[str] = []
    if level in {"exact_enzyme", "exact_target"}:
        supporting.append("Exact canonical enzyme/target identity resolved.")
    elif level in {"family", "subfamily", "functional_category"}:
        gating.append("Only family-, subfamily-, or functional-category identity was resolved.")
    else:
        gating.append("Canonical enzyme identity is unresolved.")
    if family_status == "conflict_corrected":
        gating.append("The reported enzyme family conflicted with the canonical identity and required correction.")
    if source_dataset_conflict:
        gating.append("The source dataset's advertised enzyme family conflicts with the canonical identity; provenance was retained but evidence was down-weighted.")
    if atlas_status in {"validated", "validated_target"}:
        supporting.append("Target-specific herbicide-atlas identity was validated.")
    elif atlas_status == "family_context":
        gating.append("Only broad family/process context was available from the target atlas.")
    else:
        gating.append("No target-specific herbicide-atlas mapping was validated.")
    if max(kinetic, structure, plant) >= 0.25:
        supporting.append("At least one biological evidence layer was non-trivial.")
    else:
        gating.append("Kinetic, structural, and plant-context evidence are absent or weak.")
    if compound_target_evidence_tier in {"direct_measurement", "curated_target_evidence", "curated_reference"}:
        supporting.append("Direct or curated compound-target support was available.")
    else:
        gating.append("Compound-target support is model-derived or unresolved.")

    high_gate = (
        score >= 0.75
        and level in {"exact_enzyme", "exact_target"}
        and atlas_status in {"validated", "validated_target"}
        and max(kinetic, structure, plant) >= 0.25
        and compound_target_evidence_tier in {"direct_measurement", "curated_target_evidence"}
        and not source_dataset_conflict
    )
    moderate_gate = (
        score >= 0.50
        and level in {"exact_enzyme", "exact_target", "identifier_only", "subfamily", "family"}
        and (
            max(kinetic, structure, plant) >= 0.25
            or compound_target_evidence_tier in {"direct_measurement", "curated_target_evidence", "curated_reference"}
        )
        and not source_dataset_conflict
    )
    if high_gate:
        code, label = "high", "High scientific validation priority"
    elif moderate_gate:
        code, label = "moderate", "Moderate scientific validation priority"
    elif level == "unresolved":
        code, label = "not_prioritizable", "Not prioritizable until target identity is resolved"
    else:
        code, label = "exploratory", "Exploratory scientific validation priority"

    maximum_label = "Simulation output available"
    if maximum is not None:
        if maximum >= 0.75:
            maximum_label = "High simulation-derived response rank"
        elif maximum >= 0.50:
            maximum_label = "Moderate simulation-derived response rank"
        else:
            maximum_label = "Low simulation-derived response rank"
    return {
        "scientific_priority": label,
        "scientific_priority_code": code,
        "scientific_priority_score": round(score, 3),
        "simulation_priority": maximum_label,
        "gating_reasons": gating,
        "supporting_factors": supporting,
        "priority_definition": (
            "Evidence-adjusted priority integrates identity resolution, family validation, target-atlas specificity, biological evidence, compound-target support, simulation output, and uncertainty."
        ),
    }
