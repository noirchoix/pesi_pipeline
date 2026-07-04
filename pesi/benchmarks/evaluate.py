from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pesi.domain.compound_rules import canonicalize_compound_pair, canonicalize_text_key


def _safe_read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        y = float(x)
        if math.isnan(y) or math.isinf(y):
            return default
        return y
    except Exception:
        return default


def enrichment_at_k(df: pd.DataFrame, score_col: str, label_col: str, k: int = 50) -> float | None:
    if df is None or not len(df) or score_col not in df.columns or label_col not in df.columns:
        return None
    top = df.sort_values(score_col, ascending=False).head(min(k, len(df)))
    base_rate = pd.to_numeric(df[label_col], errors="coerce").fillna(0).mean()
    top_rate = pd.to_numeric(top[label_col], errors="coerce").fillna(0).mean()
    if base_rate <= 0:
        return None
    return float(top_rate / base_rate)


def _normalized_entropy(series: pd.Series) -> float | None:
    if series is None or not len(series):
        return None
    counts = series.astype(str).value_counts()
    if len(counts) <= 1:
        return 0.0
    p = counts / counts.sum()
    entropy = float(-(p * np.log(p)).sum())
    return float(entropy / np.log(len(counts)))


def _max_share(series: pd.Series) -> float | None:
    if series is None or not len(series):
        return None
    counts = series.astype(str).value_counts()
    return float(counts.max() / max(1, counts.sum()))



def _class_key_series(df: pd.DataFrame, col: str, default: str = "unclassified_or_unknown") -> pd.Series:
    return df.get(col, pd.Series([default] * len(df))).fillna(default).astype(str).map(canonicalize_text_key)


def evaluate_outputs(out_dir: str | Path = "outputs", artifact_dir: str | Path = "artifacts") -> dict[str, Any]:
    out_path = Path(out_dir)
    artifact_path = Path(artifact_dir)
    critical = _safe_read_csv(out_path / "aim3_critical_transition_enzymes.csv")
    optimized = _safe_read_csv(out_path / "aim4_optimized_interventions.csv")
    signatures = _safe_read_csv(out_path / "enzyme_state_signatures.csv")
    compound_pool = _safe_read_csv(out_path / "compound_pool.csv")
    synergy = _safe_read_csv(out_path / "aim4_inhibit_synergy_groups.csv")

    report: dict[str, Any] = {
        "status": "evaluated",
        "out_dir": str(out_path),
        "artifact_dir": str(artifact_path),
        "benchmarks": {},
        "evidence_class": "benchmark_model_evaluation_and_ablation",
    }

    leaderboard: list[dict[str, Any]] = []

    if len(signatures):
        if "enzyme_state_cluster" in signatures.columns and "enzyme_family" in signatures.columns:
            family_diversity = signatures.groupby("enzyme_state_cluster")["enzyme_family"].nunique().mean()
            leaderboard.append({
                "benchmark": "enzyme_state_signatures_vs_enzyme_family",
                "metric": "mean_family_diversity_per_cluster",
                "value": float(family_diversity),
                "interpretation": "higher means state clusters are not mere family labels",
            })
        if "enzyme_state_cluster" in signatures.columns and "target_class" in signatures.columns:
            target_diversity = signatures.groupby("enzyme_state_cluster")["target_class"].nunique().mean()
            leaderboard.append({
                "benchmark": "enzyme_state_signatures_vs_target_class",
                "metric": "mean_target_class_diversity_per_cluster",
                "value": float(target_diversity),
                "interpretation": "higher means state clusters cut across broad target classes",
            })

    if len(critical):
        crit = critical.copy()
        if "known_target_label" in crit.columns:
            crit["known_herbicide_or_anchor"] = pd.to_numeric(crit["known_target_label"], errors="coerce").fillna(0).astype(int)
        elif "herbicide_target_match" in crit.columns:
            crit["known_herbicide_or_anchor"] = pd.to_numeric(crit["herbicide_target_match"], errors="coerce").fillna(0).astype(int)
        elif "herbicide_target_score" in crit.columns:
            crit["known_herbicide_or_anchor"] = (pd.to_numeric(crit["herbicide_target_score"], errors="coerce").fillna(0) >= 0.35).astype(int)
        else:
            crit["known_herbicide_or_anchor"] = crit.get("target_class", pd.Series([""] * len(crit))).astype(str).str.contains("herbicide|anchor|target", case=False, na=False).astype(int)

        enr = enrichment_at_k(crit, "critical_transition_score", "known_herbicide_or_anchor", k=50)
        leaderboard.append({
            "benchmark": "criticality_model_vs_random_baseline",
            "metric": "known_target_enrichment_at_50",
            "value": enr,
            "interpretation": "compares top-ranked critical enzymes with random prevalence of anchor/herbicide labels",
        })
        leaderboard.append({
            "benchmark": "criticality_model_known_target_prevalence",
            "metric": "known_target_base_rate",
            "value": float(pd.to_numeric(crit["known_herbicide_or_anchor"], errors="coerce").fillna(0).mean()),
            "interpretation": "prevalence of anchor/herbicide atlas matches used by the enrichment baseline",
        })

        if "high_confidence_known_target_label" in crit.columns:
            crit["high_confidence_known_target"] = pd.to_numeric(
                crit["high_confidence_known_target_label"], errors="coerce"
            ).fillna(0).astype(int)
        else:
            score = pd.to_numeric(crit.get("herbicide_target_score", pd.Series([0] * len(crit))), errors="coerce").fillna(0)
            family = crit.get("herbicide_target_family", pd.Series(["unmapped"] * len(crit))).astype(str).str.lower()
            wssa = crit.get("wssa_group", pd.Series(["unmapped"] * len(crit))).astype(str).str.lower()
            primary_site = family.ne("unmapped") & ~family.str.contains("detoxification|oxidative stress", na=False) & ~wssa.str.contains("modifier|unmapped", na=False)
            anchor = pd.to_numeric(crit.get("anchor_score", pd.Series([0] * len(crit))), errors="coerce").fillna(0) > 0
            crit["high_confidence_known_target"] = ((anchor & (score >= 0.35)) | (primary_site & (score >= 0.75))).astype(int)

        high_enr = enrichment_at_k(crit, "critical_transition_score", "high_confidence_known_target", k=50)
        leaderboard.append({
            "benchmark": "criticality_model_vs_strict_known_target_baseline",
            "metric": "high_confidence_known_target_enrichment_at_50",
            "value": high_enr,
            "interpretation": "uses stricter positive labels: core anchors or strong primary site-of-action atlas matches",
        })
        leaderboard.append({
            "benchmark": "criticality_model_high_confidence_prevalence",
            "metric": "high_confidence_known_target_base_rate",
            "value": float(pd.to_numeric(crit["high_confidence_known_target"], errors="coerce").fillna(0).mean()),
            "interpretation": "stricter prevalence used by the high-confidence enrichment baseline",
        })
        top50 = crit.sort_values("critical_transition_score", ascending=False).head(min(50, len(crit)))
        leaderboard.append({
            "benchmark": "criticality_model_high_confidence_topk",
            "metric": "high_confidence_known_target_top50_count",
            "value": int(pd.to_numeric(top50["high_confidence_known_target"], errors="coerce").fillna(0).sum()),
            "interpretation": "absolute strict known-target count among the top 50 critical transition candidates",
        })

        if "herbicide_target_family" in crit.columns:
            mapped = crit["herbicide_target_family"].astype(str).ne("unmapped").mean()
            leaderboard.append({
                "benchmark": "criticality_model_vs_herbicide_target_atlas",
                "metric": "mapped_target_fraction",
                "value": float(mapped),
                "interpretation": "fraction of ranked targets mapped to herbicide target atlas",
            })

    if len(optimized):
        opt = optimized.copy()
        opt["pair_key"] = opt.apply(lambda r: "||".join(canonicalize_compound_pair(r.get("compound_a"), r.get("compound_b"))), axis=1)
        opt["target_key"] = opt.get("target_enzyme", pd.Series([""] * len(opt))).map(canonicalize_text_key)
        opt["target_family_key"] = opt.get("target_family", pd.Series([""] * len(opt))).map(canonicalize_text_key)
        opt["stage_key"] = opt.get("stage", pd.Series([""] * len(opt))).map(canonicalize_text_key)
        opt["compound_a_key"] = opt.get("compound_a", pd.Series([""] * len(opt))).map(canonicalize_text_key)
        opt["compound_b_key"] = opt.get("compound_b", pd.Series([""] * len(opt))).map(canonicalize_text_key)
        all_compounds = pd.concat([opt["compound_a_key"], opt["compound_b_key"]], ignore_index=True)
        opt["compound_a_phytochemical_class_key"] = _class_key_series(opt, "compound_a_phytochemical_class")
        opt["compound_b_phytochemical_class_key"] = _class_key_series(opt, "compound_b_phytochemical_class")
        all_phytochemical_classes = pd.concat([
            opt["compound_a_phytochemical_class_key"],
            opt["compound_b_phytochemical_class_key"],
        ], ignore_index=True)
        opt["phytochemical_class_pair_key"] = opt.apply(
            lambda r: "||".join(sorted([
                str(r.get("compound_a_phytochemical_class_key", "unclassified_or_unknown")),
                str(r.get("compound_b_phytochemical_class_key", "unclassified_or_unknown")),
            ])),
            axis=1,
        )

        unique_pair_frac = opt["pair_key"].nunique() / max(1, len(opt))
        unique_target_frac = opt["target_key"].nunique() / max(1, len(opt))
        mean_suit = np.nanmean([
            pd.to_numeric(opt.get("compound_a_intervention_suitability_score", pd.Series([np.nan] * len(opt))), errors="coerce"),
            pd.to_numeric(opt.get("compound_b_intervention_suitability_score", pd.Series([np.nan] * len(opt))), errors="coerce"),
        ])
        mean_synergy = pd.to_numeric(opt.get("synergy_group_score", pd.Series([np.nan] * len(opt))), errors="coerce").mean()
        control_rate = (
            opt.get("compound_a_priority_class", pd.Series([""] * len(opt))).astype(str).str.contains("control|solvent|assay|aldehyde", case=False, na=False)
            | opt.get("compound_b_priority_class", pd.Series([""] * len(opt))).astype(str).str.contains("control|solvent|assay|aldehyde", case=False, na=False)
        ).mean()

        leaderboard.extend([
            {"benchmark": "compound_optimizer_vs_random_pairs", "metric": "unique_pair_fraction", "value": float(unique_pair_frac), "interpretation": "diversity sanity check"},
            {"benchmark": "compound_optimizer_pair_diversity", "metric": "unique_pair_count", "value": int(opt["pair_key"].nunique()), "interpretation": "absolute number of unordered compound pairs in final recommendations"},
            {"benchmark": "compound_optimizer_pair_concentration", "metric": "max_pair_share", "value": _max_share(opt["pair_key"]), "interpretation": "lower means no single compound pair dominates final recommendations"},
            {"benchmark": "compound_optimizer_compound_concentration", "metric": "max_individual_compound_share", "value": _max_share(all_compounds), "interpretation": "lower means no single compound dominates across pair members"},
            {"benchmark": "compound_optimizer_compound_diversity", "metric": "unique_compound_count", "value": int(all_compounds.nunique()), "interpretation": "absolute number of unique compounds represented in final pair recommendations"},
            {"benchmark": "compound_optimizer_phytochemical_class_diversity", "metric": "unique_phytochemical_class_count", "value": int(all_phytochemical_classes.nunique()), "interpretation": "absolute count of coarse phytochemical/chemical classes in final recommendations"},
            {"benchmark": "compound_optimizer_phytochemical_class_diversity", "metric": "phytochemical_class_entropy_normalized", "value": _normalized_entropy(all_phytochemical_classes), "interpretation": "0 to 1; higher means selected compounds span phytochemical/chemical classes more evenly"},
            {"benchmark": "compound_optimizer_phytochemical_pair_concentration", "metric": "max_phytochemical_pair_share", "value": _max_share(opt["phytochemical_class_pair_key"]), "interpretation": "lower means no single class-pair schema dominates recommendations"},
            {"benchmark": "compound_optimizer_vs_single_compound_baseline", "metric": "mean_pair_suitability_score", "value": float(mean_suit) if not np.isnan(mean_suit) else None, "interpretation": "mean suitability of selected pair members"},
            {"benchmark": "synergy_graph_vs_bliss_only", "metric": "mean_typed_synergy_score", "value": float(mean_synergy) if not np.isnan(mean_synergy) else None, "interpretation": "typed inhibition-synergy graph score"},
            {"benchmark": "compound_quality_filter", "metric": "control_or_low_priority_pair_rate", "value": float(control_rate), "interpretation": "lower is better for final candidate list; controls retained for audit"},
            {"benchmark": "target_diversity", "metric": "unique_target_fraction", "value": float(unique_target_frac), "interpretation": "guards against a single target dominating all interventions"},
            {"benchmark": "target_diversity", "metric": "unique_target_count", "value": int(opt["target_key"].nunique()), "interpretation": "absolute count of unique target enzymes in final recommendations"},
            {"benchmark": "target_concentration", "metric": "max_target_share", "value": _max_share(opt["target_key"]), "interpretation": "lower means no single target dominates final recommendations"},
            {"benchmark": "target_family_diversity", "metric": "target_family_entropy_normalized", "value": _normalized_entropy(opt["target_family_key"]), "interpretation": "0 to 1; higher means target families are more evenly represented"},
            {"benchmark": "stage_diversity", "metric": "stage_entropy_normalized", "value": _normalized_entropy(opt["stage_key"]), "interpretation": "0 to 1; higher means developmental stages are more evenly represented"},
        ])

        report["aim4_diversity_summary"] = {
            "rows": int(len(opt)),
            "unique_targets": int(opt["target_key"].nunique()),
            "unique_target_families": int(opt["target_family_key"].nunique()),
            "unique_pairs": int(opt["pair_key"].nunique()),
            "unique_compounds": int(all_compounds.nunique()),
            "unique_phytochemical_classes": int(all_phytochemical_classes.nunique()),
            "unique_phytochemical_class_pairs": int(opt["phytochemical_class_pair_key"].nunique()),
            "phytochemical_class_entropy_normalized": _normalized_entropy(all_phytochemical_classes),
            "max_target_share": _max_share(opt["target_key"]),
            "max_pair_share": _max_share(opt["pair_key"]),
            "max_individual_compound_share": _max_share(all_compounds),
            "max_phytochemical_pair_share": _max_share(opt["phytochemical_class_pair_key"]),
        }

    if len(compound_pool):
        priority_counts = compound_pool.get("compound_priority_class", pd.Series(["unknown"] * len(compound_pool))).value_counts().to_dict()
        report["compound_priority_distribution"] = {str(k): int(v) for k, v in priority_counts.items()}
        phyto_counts = compound_pool.get("phytochemical_class", pd.Series(["unclassified_or_unknown"] * len(compound_pool))).value_counts().to_dict()
        report["compound_phytochemical_class_distribution"] = {str(k): int(v) for k, v in phyto_counts.items()}

    if len(synergy):
        report["synergy_groups"] = {
            "rows": int(len(synergy)),
            "mean_score": float(pd.to_numeric(synergy.get("synergy_group_score"), errors="coerce").mean()),
            "unique_groups": int(synergy.get("group_id", pd.Series(range(len(synergy)))).nunique()),
        }


    # Production-readiness gates: explicit pass/fail summary for CI and release notes.
    metric_values: dict[str, Any] = {}
    for item in leaderboard:
        metric_values[str(item.get("metric"))] = item.get("value")

    def _metric(name: str) -> float | None:
        value = metric_values.get(name)
        try:
            if value is None:
                return None
            v = float(value)
            if math.isnan(v) or math.isinf(v):
                return None
            return v
        except Exception:
            return None

    gates = [
        {
            "gate": "strict_known_target_enrichment_available",
            "metric": "high_confidence_known_target_enrichment_at_50",
            "operator": ">=",
            "threshold": 1.0,
            "value": _metric("high_confidence_known_target_enrichment_at_50"),
            "rationale": "Top critical enzymes should enrich strict herbicide/transition target positives over base rate.",
        },
        {
            "gate": "compound_quality_controls_excluded_from_final_pairs",
            "metric": "control_or_low_priority_pair_rate",
            "operator": "<=",
            "threshold": 0.0,
            "value": _metric("control_or_low_priority_pair_rate"),
            "rationale": "Final recommendations should not include solvent/reagent/reactive-control pairs.",
        },
        {
            "gate": "target_family_balance",
            "metric": "target_family_entropy_normalized",
            "operator": ">=",
            "threshold": 0.70,
            "value": _metric("target_family_entropy_normalized"),
            "rationale": "Aim 4 should not over-concentrate in a small number of enzyme families.",
        },
        {
            "gate": "developmental_stage_balance",
            "metric": "stage_entropy_normalized",
            "operator": ">=",
            "threshold": 0.80,
            "value": _metric("stage_entropy_normalized"),
            "rationale": "Recommendations should preserve lifecycle/transition-stage coverage.",
        },
        {
            "gate": "individual_compound_concentration",
            "metric": "max_individual_compound_share",
            "operator": "<=",
            "threshold": 0.10,
            "value": _metric("max_individual_compound_share"),
            "rationale": "No single compound should dominate pair-member appearances.",
        },
        {
            "gate": "compound_portfolio_breadth",
            "metric": "unique_compound_count",
            "operator": ">=",
            "threshold": 50.0,
            "value": _metric("unique_compound_count"),
            "rationale": "Candidate list should preserve broad chemical exploration when candidate pool supports it.",
        },
        {
            "gate": "target_portfolio_breadth",
            "metric": "unique_target_count",
            "operator": ">=",
            "threshold": 35.0,
            "value": _metric("unique_target_count"),
            "rationale": "Candidate list should cover a broad target portfolio rather than only a few enzymes.",
        },
    ]

    for gate in gates:
        value = gate["value"]
        if value is None:
            gate["passed"] = False
            gate["status"] = "missing_metric"
        elif gate["operator"] == ">=":
            gate["passed"] = bool(value >= gate["threshold"])
            gate["status"] = "passed" if gate["passed"] else "failed"
        elif gate["operator"] == "<=":
            gate["passed"] = bool(value <= gate["threshold"])
            gate["status"] = "passed" if gate["passed"] else "failed"
        else:
            gate["passed"] = False
            gate["status"] = "unsupported_operator"

    passed = sum(1 for g in gates if g.get("passed"))
    report["production_gate_summary"] = {
        "status": "passed" if passed == len(gates) else "needs_attention",
        "passed_gates": int(passed),
        "total_gates": int(len(gates)),
        "failed_gates": [g["gate"] for g in gates if not g.get("passed")],
        "gates": gates,
    }

    lb = pd.DataFrame(leaderboard)
    out_path.mkdir(parents=True, exist_ok=True)
    lb.to_csv(out_path / "benchmark_leaderboard.csv", index=False)
    report["benchmarks"]["leaderboard_rows"] = int(len(lb))
    report["benchmarks"]["items"] = leaderboard
    (out_path / "benchmark_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report
