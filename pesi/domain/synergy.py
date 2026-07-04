from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from pesi.domain.compound_rules import canonicalize_compound_pair, canonicalize_text_key


@dataclass(frozen=True)
class InhibitionEvidenceEdge:
    target_enzyme: str
    target_family: str
    stage: str
    compound: str
    source: str
    p_score: float
    evidence_types: str
    evidence_class: str = "model_inference_with_real_evidence_inputs"

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InhibitSynergyGroup:
    group_id: str
    target_enzyme: str
    target_family: str
    stage: str
    members: str
    member_count: int
    source_score_list: str
    match_schema: str
    epsilon_threshold: float
    synergy_group_score: float
    evidence_class: str = "inhibit_synergy_model_inference"

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        x = float(value)
        if np.isnan(x) or np.isinf(x):
            return default
        return x
    except Exception:
        return default


def inhibition_edge_from_compound(target: pd.Series | dict[str, Any], compound: pd.Series | dict[str, Any]) -> InhibitionEvidenceEdge:
    tg = target.get if hasattr(target, "get") else dict(target).get
    cg = compound.get if hasattr(compound, "get") else dict(compound).get
    evidence_types: list[str] = []
    if _safe_float(cg("known_inhibitor_similarity_score")) >= 0.45:
        evidence_types.append("known_inhibitor_class_similarity")
    if _safe_float(cg("transition_state_mimic_score")) >= 0.45:
        evidence_types.append("transition_state_mimicry")
    if _safe_float(cg("active_site_compatibility_score")) >= 0.45:
        evidence_types.append("active_site_compatibility")
    if _safe_float(cg("functional_group_inhibition_score")) >= 0.45:
        evidence_types.append("functional_group_match")
    if _safe_float(cg("natural_product_evidence_score")) >= 0.55:
        evidence_types.append("natural_product_or_allelopathy_prior")
    if str(cg("functional_group_hits", "")).find("quinone_ros_redox") >= 0:
        evidence_types.append("ros_photosynthesis_disruption_prior")
    if _safe_float(tg("herbicide_target_score")) > 0:
        evidence_types.append("herbicide_target_atlas_match")

    p = (
        0.28 * _safe_float(cg("intervention_suitability_score"))
        + 0.18 * _safe_float(cg("active_site_compatibility_score"))
        + 0.16 * _safe_float(cg("known_inhibitor_similarity_score"))
        + 0.14 * _safe_float(cg("transition_state_mimic_score"))
        + 0.12 * _safe_float(cg("functional_group_inhibition_score"))
        + 0.12 * _safe_float(tg("herbicide_target_score"))
    )
    if cg("compound_exclusion_reason", ""):
        p *= 0.55
    p = float(np.clip(p, 0, 1))

    return InhibitionEvidenceEdge(
        target_enzyme=str(tg("enzyme_name", tg("target_enzyme", ""))),
        target_family=str(tg("enzyme_family", tg("target_family", ""))),
        stage=str(tg("stage_assigned", tg("stage", ""))),
        compound=str(cg("compound_name", cg("compound_id", ""))),
        source=str(cg("source_resource", "")),
        p_score=p,
        evidence_types=";".join(sorted(set(evidence_types))) if evidence_types else "descriptor_only_proxy",
    )


def score_pair_synergy(target: pd.Series | dict[str, Any], compound_a: pd.Series | dict[str, Any], compound_b: pd.Series | dict[str, Any], epsilon: float = 0.92) -> dict[str, Any]:
    edge_a = inhibition_edge_from_compound(target, compound_a)
    edge_b = inhibition_edge_from_compound(target, compound_b)
    evidence_schema = sorted(set(edge_a.evidence_types.split(";") + edge_b.evidence_types.split(";")))
    edge_sum = edge_a.p_score + edge_b.p_score
    schema_diversity = min(1.0, len([x for x in evidence_schema if x]) / 5.0)
    p_a = edge_a.p_score
    p_b = edge_b.p_score
    independence = 1.0 - abs(p_a - p_b)
    target_score = _safe_float(target.get("herbicide_target_score", 0.0) if hasattr(target, "get") else 0.0)
    suitability_mean = np.mean([
        _safe_float(compound_a.get("intervention_suitability_score", 0.0) if hasattr(compound_a, "get") else 0.0),
        _safe_float(compound_b.get("intervention_suitability_score", 0.0) if hasattr(compound_b, "get") else 0.0),
    ])
    synergy_score = float(np.clip(0.35 * min(1.0, edge_sum / max(epsilon, 1e-6)) + 0.20 * schema_diversity + 0.20 * independence + 0.15 * suitability_mean + 0.10 * target_score, 0, 1))
    inhibit_synergy = bool(edge_sum >= epsilon and len(evidence_schema) >= 2 and synergy_score >= 0.55)
    return {
        "inhibit_synergy": inhibit_synergy,
        "synergy_group_score": synergy_score,
        "synergy_edge_sum": float(edge_sum),
        "epsilon_threshold": float(epsilon),
        "synergy_match_schema": ";".join(evidence_schema),
        "compound_source_score_list": f"{edge_a.compound}:[{edge_a.source},{edge_a.p_score:.3f}]|{edge_b.compound}:[{edge_b.source},{edge_b.p_score:.3f}]",
        "compound_a_inhibition_edge_score": edge_a.p_score,
        "compound_b_inhibition_edge_score": edge_b.p_score,
        "compound_a_evidence_types": edge_a.evidence_types,
        "compound_b_evidence_types": edge_b.evidence_types,
    }


def build_synergy_groups(optimized: pd.DataFrame, epsilon: float = 0.92) -> pd.DataFrame:
    if optimized is None or not len(optimized):
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, r in optimized.iterrows():
        members = [str(r.get("compound_a", "")), str(r.get("compound_b", ""))]
        pair = canonicalize_compound_pair(members[0], members[1])
        key = "|".join([
            canonicalize_text_key(r.get("target_enzyme", "")),
            canonicalize_text_key(r.get("target_family", "")),
            canonicalize_text_key(r.get("stage", "")),
            pair[0],
            pair[1],
        ])
        gid = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        rows.append(InhibitSynergyGroup(
            group_id=gid,
            target_enzyme=str(r.get("target_enzyme", "")),
            target_family=str(r.get("target_family", "")),
            stage=str(r.get("stage", "")),
            members=";".join(sorted(members)),
            member_count=2,
            source_score_list=str(r.get("compound_source_score_list", "")),
            match_schema=str(r.get("synergy_match_schema", "")),
            epsilon_threshold=_safe_float(r.get("epsilon_threshold", epsilon), epsilon),
            synergy_group_score=_safe_float(r.get("synergy_group_score", 0.0)),
            evidence_class=str(r.get("synergy_evidence_class", "inhibit_synergy_model_inference")),
        ).asdict())
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("synergy_group_score", ascending=False).drop_duplicates("group_id", keep="first").reset_index(drop=True)
    return out
