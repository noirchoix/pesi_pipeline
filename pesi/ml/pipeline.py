from __future__ import annotations

import itertools
import json
import math
import os
import random
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.feature_extraction.text import HashingVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import adjusted_rand_score, classification_report, ndcg_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from pesi.core.utils import ensure_dir, to_number, write_json
from pesi.etl.kg_builder import build_pesi_kg
from pesi.etl.fooddb_loader import build_food_source_artifacts
from pesi.domain.compound_rules import (
    annotate_compound_pool,
    canonicalize_compound_pair,
    canonicalize_text_key,
    pair_diversity_key,
    pair_phytochemical_class_key,
)
from pesi.domain.herbicide_targets import match_herbicide_targets
from pesi.domain.synergy import build_synergy_groups, score_pair_synergy
from pesi.domain.selectivity import estimate_contextual_selectivity, write_scenario_selectivity_report
from pesi.schemas.scenario import FieldScenario

STAGE_ORDER = ["germination", "seedling_emergence", "early_vegetative", "vegetative_expansion", "photosynthetic_establishment", "flowering_transition", "seed_formation", "stress_response", "specialized_metabolism", "cell_wall_secondary_growth"]


def _text(*vals: Any) -> str:
    return " ".join([str(v) for v in vals if v is not None and not (isinstance(v, float) and pd.isna(v))])[:5000]


def _stage_for_enzyme(name: str, family: str = "") -> str:
    s = (str(name) + " " + str(family)).lower()
    rules = [
        ("amylase|cellulase|glycoside hydrolase|gh", "germination"),
        ("acetolactate|ahas|als", "seedling_emergence"),
        ("epsp|shikimate", "early_vegetative"),
        ("photosystem|rubisco|ribulose|protoporphyrinogen|acetyl-coa carboxylase|pepc|phosphoenolpyruvate", "vegetative_expansion"),
        ("peroxidase|dioxygenase|oxidase", "stress_response"),
        ("p450|glycosyltransferase|methyltransferase|polyketide|bahd|acyltransferase", "specialized_metabolism"),
        ("gdsl|esterase|lipase|cazy", "cell_wall_secondary_growth"),
    ]
    for pat, stage in rules:
        if re.search(pat, s):
            return stage
    return "unassigned_stage"


def _life_curve(stage: str, activity: float, n: int = 12) -> dict[str, float]:
    # Smooth pseudo trajectory for curvature/change-point analysis.
    idx = STAGE_ORDER.index(stage) if stage in STAGE_ORDER else 3
    t = np.linspace(0, 1, n)
    center = (idx + 1) / max(1, len(STAGE_ORDER))
    width = 0.10 + 0.02 * (idx % 3)
    y = activity * np.exp(-((t - center) ** 2) / (2 * width ** 2))
    dy = np.gradient(y, t)
    ddy = np.gradient(dy, t)
    return {
        "trajectory_peak": float(np.max(y)),
        "trajectory_curvature_max": float(np.max(np.abs(ddy))),
        "trajectory_critical_t": float(t[int(np.argmax(np.abs(ddy)))]),
    }


def _make_enzyme_universe(data: dict[str, Any]) -> pd.DataFrame:
    rows = []
    anchors = data.get("stage_anchors", pd.DataFrame())
    for _, r in anchors.iterrows():
        rows.append({
            "enzyme_key": str(r.get("enzyme_name")),
            "enzyme_name": str(r.get("enzyme_name")),
            "enzyme_family": str(r.get("enzyme_family")),
            "stage": str(r.get("stage")),
            "target_class": str(r.get("target_class")),
            "anchor_hit": 1,
            "source_evidence": str(r.get("source")),
            "evidence_class": str(r.get("evidence_class")),
        })
    curated = data.get("curated_families", pd.DataFrame())
    if len(curated):
        for _, r in curated.head(2500).iterrows():
            name = r.get("enzyme_full_name") or r.get("enzyme_common_name") or r.get("curated_family")
            fam = r.get("curated_family")
            rows.append({
                "enzyme_key": str(name),
                "enzyme_name": str(name),
                "enzyme_family": str(fam),
                "stage": _stage_for_enzyme(name, fam),
                "target_class": "curated_family_function",
                "anchor_hit": int(str(r.get("flag", "")).lower() == "pass"),
                "species": r.get("species"),
                "substrate": r.get("substrate"),
                "product": r.get("product"),
                "source_evidence": r.get("source_resource"),
                "evidence_class": r.get("evidence_class", "real_evidence"),
            })
    skid = data.get("skid_kinetics", pd.DataFrame())
    if len(skid):
        g = skid.groupby(["ec_number", "substrate"], dropna=True).agg(
            kinetic_records=("entry_id", "count"),
            median_parameter=("parameter_value", "median"),
            pH_median=("ph", "median"),
            temp_median=("temperature_c", "median"),
            uniprot_count=("uniprot_id", "nunique"),
            organism_count=("organism_name", "nunique"),
            site_types=("site_type", lambda x: ";".join(sorted(set(map(str, x.dropna().head(6))))))
        ).reset_index()
        for _, r in g.head(2500).iterrows():
            name = f"EC {r.get('ec_number')}"
            rows.append({
                "enzyme_key": str(r.get("ec_number")),
                "enzyme_name": name,
                "enzyme_family": str(r.get("ec_number")).split(".")[0] if pd.notna(r.get("ec_number")) else "unknown_ec",
                "stage": _stage_for_enzyme(name, ""),
                "target_class": "kinetic_ec_record",
                "anchor_hit": 0,
                "substrate": r.get("substrate"),
                "kinetic_records": r.get("kinetic_records"),
                "median_parameter": r.get("median_parameter"),
                "pH_median": r.get("pH_median"),
                "temp_median": r.get("temp_median"),
                "uniprot_count": r.get("uniprot_count"),
                "organism_count": r.get("organism_count"),
                "site_types": r.get("site_types"),
                "source_evidence": "SKiD",
                "evidence_class": "real_evidence",
            })
    cazy = data.get("cazy", pd.DataFrame())
    if len(cazy):
        cg = cazy.groupby(["cazy_family", "cazy_class"], dropna=False).agg(
            organism_count=("organism", "nunique"),
            plant_like_records=("is_plant_like", "sum"),
            records=("accession", "count"),
        ).reset_index()
        for _, r in cg.head(800).iterrows():
            rows.append({
                "enzyme_key": str(r.get("cazy_family")),
                "enzyme_name": str(r.get("cazy_family")),
                "enzyme_family": str(r.get("cazy_class")),
                "stage": _stage_for_enzyme(str(r.get("cazy_family")), str(r.get("cazy_class"))),
                "target_class": "carbohydrate_active_enzyme",
                "anchor_hit": int(str(r.get("cazy_class")).upper() in {"GH", "GT", "CE", "PL"}),
                "organism_count": r.get("organism_count"),
                "plant_like_records": r.get("plant_like_records"),
                "kinetic_records": 0,
                "source_evidence": "CAZy",
                "evidence_class": "real_evidence",
            })
    df = pd.DataFrame(rows)
    if not len(df):
        return df
    # Aggregate duplicate enzyme keys, preserving evidence density.
    df["kinetic_records"] = pd.to_numeric(df.get("kinetic_records", 0), errors="coerce").fillna(0)
    df["organism_count"] = pd.to_numeric(df.get("organism_count", 0), errors="coerce").fillna(0)
    df["plant_like_records"] = pd.to_numeric(df.get("plant_like_records", 0), errors="coerce").fillna(0)
    df["anchor_hit"] = pd.to_numeric(df.get("anchor_hit", 0), errors="coerce").fillna(0)
    return df


def _build_features(df: pd.DataFrame, food: dict[str, Any] | None = None) -> pd.DataFrame:
    import time
    _bt=time.time(); print(f"[PESI] _build_features start rows={len(df)}", flush=True)
    out = df.copy()
    out["stage_assigned"] = out["stage"].fillna("unassigned_stage")
    out["stage_index"] = out["stage_assigned"].map({s: i for i, s in enumerate(STAGE_ORDER)}).fillna(3)
    out["kinetic_evidence_score"] = np.log1p(pd.to_numeric(out.get("kinetic_records", 0), errors="coerce").fillna(0))
    out["organism_evidence_score"] = np.log1p(pd.to_numeric(out.get("organism_count", 0), errors="coerce").fillna(0))
    out["plant_context_score"] = np.log1p(pd.to_numeric(out.get("plant_like_records", 0), errors="coerce").fillna(0))
    out["anchor_score"] = pd.to_numeric(out.get("anchor_hit", 0), errors="coerce").fillna(0)
    out["structure_score"] = out.get("site_types", pd.Series([""] * len(out))).fillna("").astype(str).str.contains("Substrate|Cofactor", case=False).astype(float)
    # Natural inhibitor/source availability from FoodDB compound-enzyme edges is only direct if matching text exists; otherwise proxy marked later.
    print(f"[PESI] _build_features base scores {time.time()-_bt:.1f}s", flush=True)
    natural_avail = np.zeros(len(out))
    if isinstance(food, dict):
        ce = food.get("compound_enzyme_edges", pd.DataFrame())
        if len(ce):
            print(f"[PESI] _build_features natural text source rows={len(ce)}", flush=True)
            text = " ".join(ce.astype(str).head(10000).apply(lambda r: " ".join(r), axis=1).tolist()).lower()[:2_000_000]
            print(f"[PESI] _build_features natural text ready {time.time()-_bt:.1f}s", flush=True)
            food_terms = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{3,}", text))
            def _term_hit(n: str) -> float:
                toks = re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{3,}", str(n).lower())[:8]
                return 1.0 if any(t in food_terms for t in toks) else 0.0
            natural_avail = out["enzyme_name"].fillna("").astype(str).map(_term_hit).to_numpy()
    out["natural_inhibitor_evidence_score"] = natural_avail
    # Selectivity proxy: high if plant evidence and target is not universally broad carbon/photosynthesis-only.
    broad = out["enzyme_name"].fillna("").astype(str).str.lower().str.contains("rubisco|photosystem|ribulose")
    out["crop_selectivity_margin"] = np.clip(0.65 + 0.08*out["anchor_score"] + 0.03*out["plant_context_score"] - 0.25*broad.astype(float), 0.05, 0.95)
    out["uncertainty_penalty"] = np.clip(0.45 - 0.06*out["kinetic_evidence_score"] - 0.03*out["organism_evidence_score"] - 0.04*out["anchor_score"], 0.05, 0.65)
    out["pathway_essentiality_score"] = np.select(
        [out["stage_assigned"].isin(["germination", "seedling_emergence", "early_vegetative", "vegetative_expansion"]), out["anchor_score"] > 0],
        [0.90, 0.85], default=0.55)
    out["criticality_score_formula"] = (
        0.24*out["pathway_essentiality_score"] +
        0.18*out["kinetic_evidence_score"].clip(0, 5)/5 +
        0.16*out["anchor_score"] +
        0.14*out["structure_score"] +
        0.12*out["crop_selectivity_margin"] +
        0.10*out["natural_inhibitor_evidence_score"] -
        0.14*out["uncertainty_penalty"]
    ).clip(0, 1)
    # Lifecycle curvature from enzyme-state trajectory.
    print(f"[PESI] _build_features scoring done {time.time()-_bt:.1f}s", flush=True)
    curves = [_life_curve(st, sc) for st, sc in zip(out["stage_assigned"], out["criticality_score_formula"])]
    curve_df = pd.DataFrame(curves)
    out = pd.concat([out.reset_index(drop=True), curve_df], axis=1)
    print(f"[PESI] _build_features curves done {time.time()-_bt:.1f}s", flush=True)
    out["enzyme_state_text"] = out.apply(lambda r: _text(r.get("enzyme_name"), r.get("enzyme_family"), r.get("substrate"), r.get("product"), r.get("target_class"), r.get("stage_assigned")), axis=1)
    print(f"[PESI] _build_features text done {time.time()-_bt:.1f}s", flush=True)
    return out

def train_family_classifier(curated: pd.DataFrame, artifact_dir: Path) -> tuple[Any, dict[str, Any]]:
    """
    Train enzyme-family classifier with strict canonical key handling.

    Canonical ML label key:
    - curated_family

    Important:
    - The workbook column `family` is a taxonomic family field, not an enzyme-family label.
    - `family` must never be used as the classifier target.
    - If `curated_family` is missing/lost, recover the label from source_resource/source_file.
    """
    report: dict[str, Any] = {
        "status": "not_trained",
        "reason": "",
        "input_rows": 0,
        "input_columns_original": [],
        "input_columns_normalized": [],
        "required_label_key": "curated_family",
        "label_recovery_keys": ["curated_family", "source_resource", "source_file", "filename", "file_name", "path", "workbook"],
        "family_column_policy": "`family` is taxonomy; never use it as the ML target label",
        "evidence_class": "real_evidence_or_recovered_labels",
    }

    artifact_dir.mkdir(parents=True, exist_ok=True)

    def _remove_stale_trained_artifacts() -> None:
        for name in [
            "enzyme_family_classifier.joblib",
            "enzyme_family_classifier_report.json",
        ]:
            p = artifact_dir / name
            if p.exists():
                p.unlink()

    def _remove_stale_not_trained_marker() -> None:
        p = artifact_dir / "enzyme_family_classifier_not_trained.json"
        if p.exists():
            p.unlink()

    def _write_not_trained(reason: str, extra: dict[str, Any] | None = None) -> tuple[None, dict[str, Any]]:
        report["status"] = "not_trained"
        report["reason"] = reason
        if extra:
            report.update(extra)

        _remove_stale_trained_artifacts()
        write_json(artifact_dir / "enzyme_family_classifier_not_trained.json", report)
        return None, report

    def _clean_label(series: pd.Series) -> pd.Series:
        return (
            series
            .astype(str)
            .str.strip()
            .replace({"": np.nan, "nan": np.nan, "None": np.nan, "null": np.nan})
        )

    def _family_from_source(value: Any) -> str | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None

        name = Path(str(value)).name
        name = re.sub(r"\.xlsx$", "", name, flags=re.IGNORECASE)
        name = re.sub(r"_?minimally_?curated_?set$", "", name, flags=re.IGNORECASE)
        name = name.replace("_", " ").replace("-", " ").strip()
        return name or None

    def _looks_like_taxonomic_family(series: pd.Series) -> bool:
        """
        Taxonomic family values often look like:
        1131320|Euglenaceae
        9608|Canidae
        8352|Pipidae

        These must not become enzyme-family classifier targets.
        """
        s = series.dropna().astype(str).str.strip()
        if len(s) == 0:
            return False

        sample = s.sample(min(len(s), 5000), random_state=42) if len(s) > 5000 else s
        taxon_pattern_ratio = sample.str.match(r"^\d+\|[A-Za-z0-9_\- ]+$").mean()
        return bool(taxon_pattern_ratio > 0.25)

    def _recover_label_from_source(df_in: pd.DataFrame) -> tuple[pd.Series | None, str | None]:
        source_variants = [
            "source_resource",
            "source_file",
            "filename",
            "file_name",
            "path",
            "workbook",
        ]
        source_col = next((c for c in source_variants if c in df_in.columns), None)

        if source_col is None:
            return None, None

        return df_in[source_col].map(_family_from_source), f"recovered_from_{source_col}"

    def _bounded_stratified_sample(df_in: pd.DataFrame, label_col: str, max_rows: int = 12000) -> pd.DataFrame:
        """
        Avoid groupby.apply because some pandas versions/drop paths can lose the
        grouping column. Sampling by index preserves all columns.
        """
        if len(df_in) <= max_rows:
            return df_in.copy()

        n_classes = max(1, int(df_in[label_col].nunique()))
        per_class = max(8, int(max_rows / n_classes))

        sampled_indices: list[Any] = []
        for _, group in df_in.groupby(label_col, sort=False):
            n = min(len(group), per_class)
            sampled_indices.extend(group.sample(n=n, random_state=42).index.tolist())

        return df_in.loc[sampled_indices].reset_index(drop=True).copy()

    if curated is None or len(curated) == 0:
        return _write_not_trained("empty_curated_family_dataframe")

    df = curated.copy()
    report["input_rows"] = int(len(df))
    report["input_columns_original"] = [str(c) for c in df.columns]

    # Canonicalize all column names immediately.
    df.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for c in df.columns
    ]
    report["input_columns_normalized"] = list(df.columns)

    # ------------------------------------------------------------------
    # Canonical enzyme-family label recovery.
    # DO NOT use `family` as target. It is taxonomic family.
    # ------------------------------------------------------------------
    label_source = None

    if "curated_family" in df.columns:
        df["curated_family"] = _clean_label(df["curated_family"])
        label_source = "curated_family"

        # Guard against accidental taxonomic-label contamination.
        if _looks_like_taxonomic_family(df["curated_family"]):
            recovered, recovered_source = _recover_label_from_source(df)
            if recovered is not None:
                df["curated_family"] = _clean_label(recovered)
                label_source = recovered_source

    if "curated_family" not in df.columns or df["curated_family"].notna().sum() < 100:
        recovered, recovered_source = _recover_label_from_source(df)
        if recovered is not None:
            df["curated_family"] = _clean_label(recovered)
            label_source = recovered_source

    if "curated_family" not in df.columns:
        return _write_not_trained(
            "missing_curated_family_after_key_normalization_and_source_recovery",
            {
                "available_columns": list(df.columns),
                "family_column_policy": "`family` is taxonomy; never use it as target",
            },
        )

    df["curated_family"] = _clean_label(df["curated_family"])
    df = df.dropna(subset=["curated_family"]).copy()

    if len(df) < 100:
        return _write_not_trained(
            "not_enough_labeled_rows_after_curated_family_recovery",
            {
                "labeled_rows": int(len(df)),
                "label_source": label_source,
            },
        )

    if df["curated_family"].nunique() < 2:
        return _write_not_trained(
            "not_enough_distinct_enzyme_family_labels",
            {
                "labeled_rows": int(len(df)),
                "classes": sorted(map(str, df["curated_family"].unique())),
                "label_source": label_source,
            },
        )

    # ------------------------------------------------------------------
    # Text-feature construction.
    # Exclude source_resource/source_file to avoid label leakage when labels
    # are recovered from workbook filenames.
    # ------------------------------------------------------------------
    preferred_text_cols = [
        "enzyme_full_name",
        "enzyme_common_name",
        "enzyme_name",
        "protein_name",
        "species",
        "organism",
        "organism_name",
        "substrate",
        "product",
        "title",
        "doi",
        "uniprot_id",
        "genbank",
        "alt_id",
        "flag",
        "kingdom",
        "pfam_domains",
        "uniprot_name",
        "uniprot_accessions",
        "refseq",
        "genbank_id",
        "uniprot_name_organism",
    ]

    for col in preferred_text_cols:
        if col not in df.columns:
            df[col] = ""

    df["text"] = (
        df[preferred_text_cols]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str[:5000]
    )

    df = df[df["text"].str.strip().str.len() > 0].copy()

    if "curated_family" not in df.columns:
        recovered, recovered_source = _recover_label_from_source(df)
        if recovered is not None:
            df["curated_family"] = _clean_label(recovered)
            label_source = recovered_source

    if "curated_family" not in df.columns:
        return _write_not_trained(
            "curated_family_lost_after_text_filtering",
            {
                "available_columns_after_text_filtering": list(df.columns),
                "family_column_policy": "`family` is taxonomy; never use it as target",
            },
        )

    df["curated_family"] = _clean_label(df["curated_family"])
    df = df.dropna(subset=["curated_family"]).copy()

    # ------------------------------------------------------------------
    # Class-balance filter.
    # Require enough samples per enzyme-family class for stratified split.
    # ------------------------------------------------------------------
    vc = df["curated_family"].value_counts()
    keep = vc[vc >= 8].index
    df = df[df["curated_family"].isin(keep)].copy()

    if len(df) < 100 or df["curated_family"].nunique() < 2:
        return _write_not_trained(
            "not_enough_class_balance",
            {
                "rows_after_filter": int(len(df)),
                "classes_after_filter": int(df["curated_family"].nunique()) if "curated_family" in df.columns else 0,
                "class_counts": df["curated_family"].value_counts().to_dict() if "curated_family" in df.columns else {},
                "label_source": label_source,
            },
        )

    # Bound runtime for first audits while preserving class coverage and columns.
    df = _bounded_stratified_sample(df, "curated_family", max_rows=12000)

    # ------------------------------------------------------------------
    # Final label lock before sklearn.
    # Never recover from `family`; only recover from source metadata.
    # ------------------------------------------------------------------
    if "curated_family" not in df.columns:
        recovered, recovered_source = _recover_label_from_source(df)
        if recovered is not None:
            df["curated_family"] = _clean_label(recovered)
            label_source = recovered_source

    if "curated_family" not in df.columns:
        return _write_not_trained(
            "missing_required_keys_before_train_test_split",
            {
                "missing": ["curated_family"],
                "available_columns": list(df.columns),
                "required_label_key": "curated_family",
                "fallback_checked": "source_resource/source_file",
                "fix_result": "source metadata not available or not recoverable",
                "family_column_policy": "`family` is taxonomy; never use it as target",
            },
        )

    df["curated_family"] = _clean_label(df["curated_family"])
    df = df.dropna(subset=["curated_family"]).copy()

    if _looks_like_taxonomic_family(df["curated_family"]):
        recovered, recovered_source = _recover_label_from_source(df)
        if recovered is not None:
            df["curated_family"] = _clean_label(recovered)
            label_source = recovered_source
            df = df.dropna(subset=["curated_family"]).copy()

    if "text" not in df.columns:
        return _write_not_trained(
            "missing_text_before_train_test_split",
            {
                "missing": ["text"],
                "available_columns": list(df.columns),
            },
        )

    df["text"] = df["text"].astype(str).fillna("").str.strip()
    df = df[df["text"].str.len() > 0].copy()

    # Final minimum class check after all recovery.
    vc = df["curated_family"].value_counts()
    keep = vc[vc >= 8].index
    df = df[df["curated_family"].isin(keep)].copy()

    if len(df) < 100 or df["curated_family"].nunique() < 2:
        return _write_not_trained(
            "not_enough_class_balance_before_train_test_split",
            {
                "rows_after_final_label_lock": int(len(df)),
                "classes_after_final_label_lock": int(df["curated_family"].nunique()),
                "class_counts": df["curated_family"].value_counts().to_dict(),
                "label_source": label_source,
            },
        )

    df = _bounded_stratified_sample(df, "curated_family", max_rows=12000)

    # Persist final diagnostic files.
    diagnostic_cols = [
        c for c in [
            "curated_family",
            "family",
            "source_resource",
            "source_sheet",
            "enzyme_full_name",
            "enzyme_common_name",
            "species",
            "substrate",
            "product",
            "text",
        ]
        if c in df.columns
    ]

    df[diagnostic_cols].head(300).to_csv(
        artifact_dir / "enzyme_family_classifier_training_sample.csv",
        index=False,
    )

    df["curated_family"].value_counts().to_csv(
        artifact_dir / "enzyme_family_classifier_label_counts.csv",
        header=["count"],
    )

    X_train, X_test, y_train, y_test = train_test_split(
        df["text"],
        df["curated_family"],
        test_size=0.25,
        random_state=42,
        stratify=df["curated_family"],
    )

    model = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=8000, ngram_range=(1, 2), min_df=2)),
        ("clf", SGDClassifier(
            loss="log_loss",
            alpha=1e-5,
            max_iter=25,
            class_weight="balanced",
            random_state=42,
        )),
    ])

    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    trained_report = {
        "status": "trained",
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "total_labeled_rows_used": int(len(df)),
        "classes": sorted(map(str, df["curated_family"].unique())),
        "classification_report": classification_report(
            y_test,
            pred,
            output_dict=True,
            zero_division=0,
        ),
        "required_label_key": "curated_family",
        "label_recovery_keys": ["curated_family", "source_resource", "source_file", "filename", "file_name", "path", "workbook"],
        "evidence_class": "real_evidence_labels",
        "label_source": label_source or "curated_family",
        "family_column_policy": "`family` is taxonomy; never used as target label",
    }

    joblib.dump(model, artifact_dir / "enzyme_family_classifier.joblib")
    write_json(artifact_dir / "enzyme_family_classifier_report.json", trained_report)

    # Remove stale failure marker from earlier failed runs.
    _remove_stale_not_trained_marker()

    return model, trained_report

def train_enzyme_smi_interaction_model(pairs: pd.DataFrame, artifact_dir: Path, max_rows: int = 12000) -> tuple[Any, dict[str, Any]]:
    if pairs is None or len(pairs) < 1000 or not {"sequence", "smiles"}.issubset(pairs.columns):
        return None, {"status": "not_trained"}
    pos = pairs.dropna(subset=["sequence", "smiles"]).head(max_rows).copy()
    pos["label"] = 1
    # Explicit proxy negatives: shuffle SMILES against sequences. Not biochemical truth.
    neg = pos.copy()
    neg["smiles"] = neg["smiles"].sample(frac=1, random_state=99).values
    neg["label"] = 0
    neg["evidence_class"] = "proxy_evidence_negative_sampling"
    df = pd.concat([pos, neg], ignore_index=True)
    df["text"] = df["sequence"].astype(str).str[:1200] + " [SMI] " + df["smiles"].astype(str).str[:1000]
    X_train, X_test, y_train, y_test = train_test_split(df["text"], df["label"], test_size=0.25, random_state=42, stratify=df["label"])
    model = Pipeline([
        ("hash", HashingVectorizer(n_features=2**16, alternate_sign=False, ngram_range=(2, 4), analyzer="char")),
        ("clf", SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=3000, tol=1e-4, early_stopping=True, n_iter_no_change=10, random_state=42))
    ])
    model.fit(X_train, y_train)
    prob = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, prob)
    report = {
        "status": "trained",
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "roc_auc_proxy_negatives": float(auc),
        "negative_sampling_warning": "Negatives are mismatched sequence/SMILES proxy negatives, not experimentally confirmed non-interactions.",
        "training_hardening": {
            "max_iter": 3000,
            "tol": 1e-4,
            "early_stopping": True,
            "n_iter_no_change": 10,
            "purpose": "avoid medium/full-profile SGD convergence warnings while preserving deterministic proxy-training semantics",
        },
        "evidence_class": "real_positive_labels_plus_proxy_negative_labels",
    }
    joblib.dump(model, artifact_dir / "enzyme_smi_interaction_model.joblib")
    return model, report


def evaluate_signatures(features: pd.DataFrame, out_dir: Path) -> dict[str, Any]:
    df = features.copy()
    report: dict[str, Any] = {"status": "not_evaluated"}
    if len(df) < 20:
        return report
    feat_cols = ["pathway_essentiality_score", "kinetic_evidence_score", "organism_evidence_score", "plant_context_score", "structure_score", "crop_selectivity_margin", "natural_inhibitor_evidence_score", "uncertainty_penalty", "trajectory_curvature_max"]
    X = df[feat_cols].fillna(0).to_numpy()
    k = min(8, max(2, int(math.sqrt(len(df)) // 2)))
    km = KMeans(n_clusters=k, random_state=42, n_init=5)
    if len(df) > 5000:
        rng = np.random.default_rng(42)
        idx = rng.choice(len(df), size=5000, replace=False)
        km.fit(X[idx])
        df["enzyme_state_cluster"] = km.predict(X)
    else:
        df["enzyme_state_cluster"] = km.fit_predict(X)
    # Taxonomy/family baseline: compare clusters to enzyme_family and target_class where available.
    family_codes = pd.factorize(df["enzyme_family"].fillna("unknown"))[0]
    target_codes = pd.factorize(df["target_class"].fillna("unknown"))[0]
    report = {
        "status": "evaluated",
        "rows": int(len(df)),
        "clusters": int(k),
        "adjusted_rand_vs_enzyme_family": float(adjusted_rand_score(family_codes, df["enzyme_state_cluster"])),
        "adjusted_rand_vs_target_class": float(adjusted_rand_score(target_codes, df["enzyme_state_cluster"])),
        "metric_interpretation": "ARI is not expected to be maximal; divergence supports testing whether enzyme-state signatures differ from taxonomy/family labels.",
        "evidence_class": "model_inference",
    }
    df.to_csv(out_dir / "enzyme_state_signatures.csv", index=False)
    write_json(out_dir / "aim2_signature_evaluation.json", report)
    return report

def canonicalize_text_key(value: Any) -> str:
    """
    Normalize enzyme/compound labels for semantic de-duplication.

    This does not replace the display label. It only creates a stable comparison key.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    s = str(value).lower().strip()

    # Normalize separators and punctuation.
    s = re.sub(r"[\u2010-\u2015]", "-", s)
    s = re.sub(r"[:;/,_()\[\]{}]+", " ", s)
    s = re.sub(r"[^a-z0-9+\- ]+", " ", s)

    # Normalize frequent biochemical wording variants.
    s = s.replace("coenzyme a", "coa")
    s = s.replace("co-enzyme a", "coa")
    s = s.replace("co enzyme a", "coa")
    s = s.replace("hydroxycinnamoyl-coa", "hydroxycinnamoyl coa")
    s = s.replace("hydroxycinnamoylcoa", "hydroxycinnamoyl coa")
    s = s.replace("hydroxycinnamoyl transferase", "hydroxycinnamoyltransferase")
    s = s.replace("o hydroxycinnamoyl", "hydroxycinnamoyl")

    # Remove isoform-like suffixes that create false duplicates.
    s = re.sub(r"\bisoform\b", " ", s)
    s = re.sub(r"\bprotein\b", " ", s)
    s = re.sub(r"\benzyme\b", " ", s)
    s = re.sub(r"\b\d+[a-z]?\b$", " ", s)

    # Collapse whitespace.
    s = re.sub(r"\s+", " ", s).strip()

    return s


def canonicalize_compound_pair(a: Any, b: Any) -> tuple[str, str]:
    """
    Treat compound pairs as unordered for combination optimization.

    ethanol + methylglyoxal == methylglyoxal + ethanol
    """
    ca = canonicalize_text_key(a)
    cb = canonicalize_text_key(b)
    # Ensure a fixed-size 2-tuple return (sorted order) to satisfy type hints.
    s = sorted([ca, cb])
    return (s[0], s[1])

def rank_critical_transition_enzymes(
    features: pd.DataFrame,
    artifact_dir: Path,
    out_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    def _canonicalize_text_key(value: Any) -> str:
        """
        Normalize enzyme labels for semantic de-duplication.

        This key is only used internally for grouping near-identical enzyme-name
        variants. It does not replace the display label in the output CSV.
        """
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""

        s = str(value).lower().strip()

        s = re.sub(r"[\u2010-\u2015]", "-", s)
        s = re.sub(r"[:;/,_()\[\]{}]+", " ", s)
        s = re.sub(r"[^a-z0-9+\- ]+", " ", s)

        s = s.replace("coenzyme a", "coa")
        s = s.replace("co-enzyme a", "coa")
        s = s.replace("co enzyme a", "coa")
        s = s.replace("hydroxycinnamoyl-coa", "hydroxycinnamoyl coa")
        s = s.replace("hydroxycinnamoylcoa", "hydroxycinnamoyl coa")
        s = s.replace("hydroxycinnamoyl transferase", "hydroxycinnamoyltransferase")
        s = s.replace("o hydroxycinnamoyl", "hydroxycinnamoyl")

        # Domain-specific HCT/HQT/HCT-like label normalization.
        # This collapses common workbook/name variants that refer to the same
        # hydroxycinnamoyl-CoA shikimate/quinate transferase target family.
        if (
            "hydroxycinnamoyl" in s
            and "shikimate" in s
            and (
                "transferase" in s
                or "hydroxycinnamoyltransferase" in s
            )
        ):
            return "hct_hydroxycinnamoyl_coa_shikimate_quinate_transferase"

        s = re.sub(r"\bisoform\b", " ", s)
        s = re.sub(r"\bprotein\b", " ", s)
        s = re.sub(r"\benzyme\b", " ", s)

        # Remove terminal isoform/gene-number suffixes.
        s = re.sub(r"\b\d+[a-z]?\b$", " ", s)

        s = re.sub(r"\s+", " ", s).strip()
        return s

    artifact_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = features.copy()

    feat_cols = [
        "pathway_essentiality_score",
        "kinetic_evidence_score",
        "organism_evidence_score",
        "plant_context_score",
        "structure_score",
        "crop_selectivity_margin",
        "natural_inhibitor_evidence_score",
        "uncertainty_penalty",
        "trajectory_curvature_max",
    ]

    for col in feat_cols:
        if col not in df.columns:
            df[col] = 0.0

    if "anchor_score" not in df.columns:
        df["anchor_score"] = 0.0

    if "criticality_score_formula" not in df.columns:
        df["criticality_score_formula"] = (
            0.24 * df["pathway_essentiality_score"].fillna(0)
            + 0.18 * df["kinetic_evidence_score"].fillna(0)
            + 0.12 * df["structure_score"].fillna(0)
            + 0.16 * df["crop_selectivity_margin"].fillna(0)
            + 0.12 * df["natural_inhibitor_evidence_score"].fillna(0)
            + 0.10 * df["trajectory_curvature_max"].fillna(0).clip(0, 1)
            - 0.18 * df["uncertainty_penalty"].fillna(0)
        ).clip(0, 1)

    # Use anchor-hit as weak/proxy label to learn criticality style from known
    # targets. Keep formula score as the primary transparent score.
    train = df[df["anchor_score"].notna()].copy()
    model_report: dict[str, Any] = {"status": "not_trained"}

    if len(train) >= 30 and train["anchor_score"].nunique() >= 2:
        y = (train["anchor_score"] > 0).astype(int)
        X = train[feat_cols].fillna(0)

        if len(train) > 6000:
            train_sample = train.sample(6000, random_state=42)
            y = (train_sample["anchor_score"] > 0).astype(int)
            X = train_sample[feat_cols].fillna(0)

        clf = RandomForestClassifier(
            n_estimators=60,
            random_state=42,
            class_weight="balanced_subsample",
            min_samples_leaf=3,
            n_jobs=1,
        )
        clf.fit(X, y)

        df["ml_anchor_probability"] = clf.predict_proba(df[feat_cols].fillna(0))[:, 1]

        joblib.dump(clf, artifact_dir / "critical_transition_anchor_model.joblib")

        model_report = {
            "status": "trained",
            "training_label": "anchor_hit_from_known_targets_and_curated_pass_flags",
            "evidence_class": "proxy_evidence_label",
            "feature_importances": dict(zip(feat_cols, map(float, clf.feature_importances_))),
        }
    else:
        df["ml_anchor_probability"] = df["criticality_score_formula"]

    df["critical_transition_score"] = (
        0.72 * df["criticality_score_formula"]
        + 0.28 * df["ml_anchor_probability"]
    ).clip(0, 1)

    df["evidence_class"] = np.where(
        df["anchor_score"] > 0,
        "real_evidence_plus_model_inference",
        "model_inference",
    )

    # Expose herbicide-target atlas labels in Aim 3 so benchmarks can compare
    # criticality ranking against known/curated herbicide target priors.
    try:
        atlas_rows = df.apply(
            lambda r: match_herbicide_targets(r.get("enzyme_name"), r.get("enzyme_family"), r.get("stage_assigned")),
            axis=1,
        ).apply(pd.Series)
        # Avoid duplicate columns if upstream features already include atlas labels.
        atlas_rows = atlas_rows[[c for c in atlas_rows.columns if c not in df.columns]]
        if len(atlas_rows.columns):
            df = pd.concat([df.reset_index(drop=True), atlas_rows.reset_index(drop=True)], axis=1)
    except Exception:
        df["herbicide_target_family"] = "unmapped"
        df["herbicide_target_score"] = 0.0

    if "herbicide_target_score" not in df.columns:
        df["herbicide_target_score"] = 0.0
    if "herbicide_target_family" not in df.columns:
        df["herbicide_target_family"] = "unmapped"

    df["known_target_label"] = (
        (pd.to_numeric(df.get("anchor_score", 0), errors="coerce").fillna(0) > 0)
        | (pd.to_numeric(df.get("herbicide_target_score", 0), errors="coerce").fillna(0) >= 0.35)
    ).astype(int)
    df["herbicide_target_match"] = (
        pd.to_numeric(df.get("herbicide_target_score", 0), errors="coerce").fillna(0) > 0
    ).astype(int)

    # Stricter biological label for benchmarking: the broad known_target_label is
    # intentionally inclusive, but this high-confidence label is restricted to
    # anchors and strong primary site-of-action matches. It is used to avoid a
    # weak benchmark where most rows are treated as positives.
    _score = pd.to_numeric(df.get("herbicide_target_score", 0), errors="coerce").fillna(0)
    _anchor = pd.to_numeric(df.get("anchor_score", 0), errors="coerce").fillna(0) > 0
    _family = df.get("herbicide_target_family", pd.Series(["unmapped"] * len(df))).astype(str).str.lower()
    _wssa = df.get("wssa_group", pd.Series(["unmapped"] * len(df))).astype(str).str.lower()
    _primary_site = (
        _family.ne("unmapped")
        & ~_family.str.contains("detoxification|oxidative stress", na=False)
        & ~_wssa.str.contains("modifier|unmapped", na=False)
    )
    df["high_confidence_known_target_label"] = ((_anchor & (_score >= 0.35)) | (_primary_site & (_score >= 0.75))).astype(int)
    df["high_confidence_target_basis"] = np.select(
        [(_anchor & (_score >= 0.35)), (_primary_site & (_score >= 0.75))],
        ["core_transition_anchor_plus_atlas_match", "strong_primary_site_of_action_atlas_match"],
        default="not_high_confidence",
    )

    cols = [
        "enzyme_key",
        "enzyme_name",
        "enzyme_family",
        "stage_assigned",
        "target_class",
        "critical_transition_score",
        "criticality_score_formula",
        "ml_anchor_probability",
        "anchor_score",
        "known_target_label",
        "high_confidence_known_target_label",
        "high_confidence_target_basis",
        "herbicide_target_match",
        "herbicide_target_family",
        "herbicide_site_of_action",
        "herbicide_target_score",
        "known_inhibitor_classes",
        "wssa_group",
        "resistance_risks",
        "pathway_essentiality_score",
        "kinetic_evidence_score",
        "structure_score",
        "crop_selectivity_margin",
        "natural_inhibitor_evidence_score",
        "uncertainty_penalty",
        "trajectory_curvature_max",
        "trajectory_critical_t",
        "source_evidence",
        "evidence_class",
    ]

    out = df[[c for c in cols if c in df.columns]].sort_values(
        by="critical_transition_score",
        ascending=False,
    )

    # Semantic canonicalization for enzyme-name variants.
    # Keeps the best-scoring display row, but removes near-identical enzyme
    # candidates from repeated curated workbook records.
    if "enzyme_name" in out.columns:
        out["enzyme_name_canonical"] = out["enzyme_name"].map(_canonicalize_text_key)
    elif "enzyme_key" in out.columns:
        out["enzyme_name_canonical"] = out["enzyme_key"].map(_canonicalize_text_key)
    else:
        out["enzyme_name_canonical"] = ""

    dedupe_keys = [
        c for c in [
            "enzyme_name_canonical",
            "enzyme_family",
            "stage_assigned",
            "target_class",
        ]
        if c in out.columns
    ]

    if dedupe_keys:
        out = out.drop_duplicates(subset=dedupe_keys, keep="first").reset_index(drop=True)
    else:
        out = out.drop_duplicates().reset_index(drop=True)

    model_report["ranked_rows_after_dedup"] = int(len(out))
    model_report["ranked_rows_after_semantic_dedup"] = int(len(out))
    model_report["semantic_dedupe_keys"] = dedupe_keys
    model_report["semantic_deduplication"] = True

    if "enzyme_name_canonical" in out.columns:
        out = out.drop(columns=["enzyme_name_canonical"])

    if "known_target_label" in out.columns:
        model_report["known_target_base_rate_after_dedup"] = float(pd.to_numeric(out["known_target_label"], errors="coerce").fillna(0).mean())
    if "high_confidence_known_target_label" in out.columns:
        model_report["high_confidence_known_target_base_rate_after_dedup"] = float(pd.to_numeric(out["high_confidence_known_target_label"], errors="coerce").fillna(0).mean())

    out.to_csv(out_dir / "aim3_critical_transition_enzymes.csv", index=False)
    write_json(out_dir / "aim3_critical_transition_model_report.json", model_report)

    return out, model_report


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return default
        x = float(v)
        return default if np.isnan(x) else x
    except Exception:
        return default

def _rdkit_descriptors(smiles: str) -> dict[str, float]:
    try:
        if smiles is None or str(smiles).strip().lower() in {"", "none", "nan", "null"}:
            return {"mw": np.nan, "logp": np.nan, "tpsa": np.nan, "hbd": np.nan, "hba": np.nan}
        from rdkit import Chem, RDLogger
        from rdkit.Chem import Descriptors
        RDLogger.DisableLog("rdApp.*")
        mol = Chem.MolFromSmiles(str(smiles))
        if mol is None:
            return {"mw": np.nan, "logp": np.nan, "tpsa": np.nan, "hbd": np.nan, "hba": np.nan}
        return {"mw": float(Descriptors.MolWt(mol)), "logp": float(Descriptors.MolLogP(mol)), "tpsa": float(Descriptors.TPSA(mol)), "hbd": float(Descriptors.NumHDonors(mol)), "hba": float(Descriptors.NumHAcceptors(mol))}
    except Exception:
        return {"mw": np.nan, "logp": np.nan, "tpsa": np.nan, "hbd": np.nan, "hba": np.nan}



def build_compound_pool(data: dict[str, Any], top_n: int = 600) -> pd.DataFrame:
    """Build and scientifically annotate a compound pool for Aim 4.

    The pool keeps real source evidence from FoodDB/SKiD, but adds explicit rule-based
    phytochemical/herbicide-suitability annotations. Solvents, buffers, common assay
    chemicals and reactive aldehydes remain in the audit table, but are downgraded to
    control/low-priority classes rather than silently removed.
    """
    rows: list[dict[str, Any]] = []
    food = data.get("fooddb", {})

    if isinstance(food, dict):
        cd = food.get("compound_descriptors", pd.DataFrame())
        if len(cd):
            cols = list(cd.columns)
            id_cols = [c for c in cols if "compound" in c and "id" in c] or [cols[0]]
            name_cols = [c for c in cols if c in {"name", "compound_name", "public_id", "moldb_name", "description"}]
            smi_cols = [c for c in cols if "smiles" in c or "moldb_smiles" in c]
            class_cols = [c for c in cols if any(k in c.lower() for k in ["class", "kingdom", "superclass", "subclass", "taxonomy", "category"])]
            for _, r in cd.head(top_n).iterrows():
                smi = r.get(smi_cols[0]) if smi_cols else None
                name = r.get(name_cols[0]) if name_cols else r.get(id_cols[0])
                rows.append({
                    "compound_id": r.get(id_cols[0]),
                    "compound_name": name,
                    "smiles": smi,
                    "source_resource": "FoodDB",
                    "source_detail": ";".join([str(r.get(c, "")) for c in class_cols[:3] if pd.notna(r.get(c, None))]),
                    "evidence_class": "real_evidence",
                })

        fce = food.get("food_compound_edges", pd.DataFrame())
        if len(fce) and not rows:
            cols = list(fce.columns)
            cid = next((c for c in cols if "compound" in c and "id" in c), cols[0])
            for v in fce[cid].dropna().astype(str).unique()[:top_n]:
                rows.append({
                    "compound_id": v,
                    "compound_name": v,
                    "smiles": None,
                    "source_resource": "FoodDB_edges",
                    "source_detail": "food_compound_edge",
                    "evidence_class": "real_evidence",
                })

    skid = data.get("skid_kinetics", pd.DataFrame())
    if len(skid) and "substrate_smiles" in skid.columns:
        for _, r in skid.dropna(subset=["substrate_smiles"]).drop_duplicates("substrate_smiles").head(max(1, top_n // 2)).iterrows():
            rows.append({
                "compound_id": r.get("substrate"),
                "compound_name": r.get("substrate"),
                "smiles": r.get("substrate_smiles"),
                "source_resource": "SKiD_substrates",
                "source_detail": f"EC={r.get('ec_number', '')};site={r.get('site_type', '')}",
                "evidence_class": "real_evidence",
            })

    cp = pd.DataFrame(rows)
    if not len(cp):
        return pd.DataFrame()

    cp["compound_id"] = cp["compound_id"].astype(str)
    cp["smiles"] = cp.get("smiles", pd.Series([None] * len(cp))).astype(object)
    cp["compound_name"] = cp["compound_name"].fillna(cp["compound_id"]).astype(str)
    cp["compound_name_canonical"] = cp["compound_name"].map(canonicalize_text_key)
    cp = cp.drop_duplicates(subset=["compound_name_canonical", "smiles"], keep="first").reset_index(drop=True)

    desc = cp["smiles"].map(_rdkit_descriptors).apply(pd.Series)
    cp = pd.concat([cp.reset_index(drop=True), desc.reset_index(drop=True)], axis=1)

    cp["hazard_proxy"] = np.clip((cp["logp"].fillna(2).abs() / 8) + (cp["mw"].fillna(300) / 1200), 0, 1)
    cp["persistence_proxy"] = np.clip((cp["logp"].fillna(2) / 6) + (cp["mw"].fillna(300) / 1500), 0, 1)
    cp["availability_score"] = np.where(cp["source_resource"].astype(str).str.contains("FoodDB", case=False, na=False), 0.85, 0.55)

    cp = annotate_compound_pool(cp)
    cp = cp.sort_values(
        ["intervention_suitability_score", "natural_product_evidence_score", "hazard_proxy"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    return cp




def select_diverse_interventions(
    scored: pd.DataFrame,
    max_rows: int = 1000,
    max_per_target: int = 45,
    max_per_target_family: int = 150,
    max_per_compound_pair: int = 14,
    max_per_compound: int = 210,
    max_per_stage: int = 700,
    max_per_phytochemical_class: int = 340,
    max_per_phytochemical_pair: int = 110,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fast breadth-aware final selector for Aim 4 interventions.

    This implementation intentionally avoids the previous O(n * selected_rows)
    greedy rescoring loop. The optimizer can create tens of thousands of scored
    intervention rows in medium/full profiles, so repeatedly scanning the whole
    table for every selected row is too slow on a workstation.

    Selection is now deterministic and bounded:

    1. Semantic de-duplication of identical target/stage/pair interventions.
    2. Candidate-pool bounding that keeps high-score rows and per-target/per-family
       representation.
    3. Target breadth seeding.
    4. Compound breadth seeding.
    5. Target-family floor seeding.
    6. Linear fill passes with controlled relaxation.

    Compound and pair concentration caps remain enforced until the last bounded
    fill pass. The final portfolio is designed to keep roughly 900-1000 rows when
    the candidate pool supports it, because denominator collapse was the reason
    the previous selector failed the individual-compound concentration gate.
    """

    def _empty_report(reason: str = "empty_input") -> dict[str, Any]:
        return {
            "selection_policy": "fast_portfolio_breadth_selector_v2",
            "status": reason,
            "input_rows": 0,
            "selected_rows": 0,
            "caps": {
                "max_rows": max_rows,
                "max_per_target": max_per_target,
                "max_per_target_family": max_per_target_family,
                "max_per_compound_pair": max_per_compound_pair,
                "max_per_compound": max_per_compound,
                "max_per_stage": max_per_stage,
                "max_per_phytochemical_class": max_per_phytochemical_class,
                "max_per_phytochemical_pair": max_per_phytochemical_pair,
            },
        }

    def _norm_entropy(series: pd.Series) -> float | None:
        if series is None or not len(series):
            return None
        counts = series.astype(str).value_counts()
        if len(counts) <= 1:
            return 0.0
        p = counts / counts.sum()
        return float(-(p * np.log(p)).sum() / np.log(len(counts)))

    if scored is None or not len(scored):
        return pd.DataFrame(), _empty_report("empty_input")

    df = scored.copy()
    for col in ["target_enzyme", "target_family", "stage", "compound_a", "compound_b"]:
        if col not in df.columns:
            df[col] = ""
    for col in ["compound_a_phytochemical_class", "compound_b_phytochemical_class"]:
        if col not in df.columns:
            df[col] = "unclassified_or_unknown"
    if "optimization_objective" not in df.columns:
        df["optimization_objective"] = 0.0

    df["optimization_objective"] = pd.to_numeric(df["optimization_objective"], errors="coerce").fillna(0.0)
    df["target_enzyme_canonical"] = df["target_enzyme"].map(canonicalize_text_key)
    df["target_family_canonical"] = df["target_family"].map(canonicalize_text_key)
    df["stage_canonical"] = df["stage"].map(canonicalize_text_key)
    df["compound_a_canonical"] = df["compound_a"].map(canonicalize_text_key)
    df["compound_b_canonical"] = df["compound_b"].map(canonicalize_text_key)
    df["compound_pair_canonical"] = df.apply(
        lambda r: "||".join(canonicalize_compound_pair(r["compound_a"], r["compound_b"])), axis=1
    )
    df["compound_a_phytochemical_class_key"] = df["compound_a_phytochemical_class"].map(canonicalize_text_key)
    df["compound_b_phytochemical_class_key"] = df["compound_b_phytochemical_class"].map(canonicalize_text_key)
    df["phytochemical_class_pair_key"] = df.apply(lambda r: pair_phytochemical_class_key(r), axis=1)

    # Semantic de-duplication keeps only the strongest row for the same target/stage/pair.
    dedupe_cols = ["target_enzyme_canonical", "target_family_canonical", "stage_canonical", "compound_pair_canonical"]
    df = (
        df.sort_values("optimization_objective", ascending=False)
        .drop_duplicates(subset=dedupe_cols, keep="first")
        .reset_index(drop=True)
    )
    if not len(df):
        return pd.DataFrame(), _empty_report("empty_after_deduplication")

    target_rows = min(int(max_rows), 1000, len(df))

    # Bound only extremely large candidate sets. This keeps the selector fast while
    # preserving target/family breadth and high-scoring global candidates.
    bounded_parts: list[pd.DataFrame] = [df.head(min(len(df), 35000))]
    bounded_parts.append(df.groupby("target_enzyme_canonical", group_keys=False).head(350))
    bounded_parts.append(df.groupby("target_family_canonical", group_keys=False).head(2500))
    bounded_parts.append(df.groupby("stage_canonical", group_keys=False).head(3500))
    df = pd.concat(bounded_parts, ignore_index=False)
    df = (
        df.loc[~df.index.duplicated(keep="first")]
        .sort_values("optimization_objective", ascending=False)
        .reset_index(drop=True)
    )

    # Effective caps. Compound cap is set against the requested final denominator
    # so that, if the portfolio reaches target_rows, max compound share remains
    # at or below the 0.10 gate. If the available pool cannot support target_rows,
    # the benchmark will correctly flag that as data/candidate-pool limitation.
    family_floor = max(12, int(target_rows * 0.020))
    family_cap = min(max_per_target_family, max(90, int(target_rows * 0.145)))
    compound_cap = min(max_per_compound, max(80, int(math.floor(target_rows * 0.19))))
    target_cap = max(max_per_target, max(35, int(target_rows * 0.045)))
    stage_cap = min(max_per_stage, max(150, int(target_rows * 0.70)))
    phytochemical_cap = min(max_per_phytochemical_class, max(90, int(target_rows * 0.34)))
    phytochemical_pair_cap = min(max_per_phytochemical_pair, max(45, int(target_rows * 0.110)))

    target_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    pair_counts: dict[str, int] = {}
    compound_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    phytochemical_counts: dict[str, int] = {}
    phytochemical_pair_counts: dict[str, int] = {}
    selected_indices: list[int] = []
    selected_set: set[int] = set()
    selection_phase: dict[int, str] = {}
    relaxation_events: list[str] = []

    def _row_keys(r: pd.Series) -> tuple[str, str, str, str, str, str, str, str, str]:
        return (
            str(r.get("target_enzyme_canonical", "")),
            str(r.get("target_family_canonical", "")),
            str(r.get("stage_canonical", "")),
            str(r.get("compound_pair_canonical", "")),
            str(r.get("compound_a_canonical", "")),
            str(r.get("compound_b_canonical", "")),
            str(r.get("compound_a_phytochemical_class_key", "unclassified_or_unknown")),
            str(r.get("compound_b_phytochemical_class_key", "unclassified_or_unknown")),
            str(r.get("phytochemical_class_pair_key", "unclassified_or_unknown||unclassified_or_unknown")),
        )

    def _can_select(
        r: pd.Series,
        *,
        target_cap_override: int | None = None,
        family_cap_override: int | None = None,
        pair_cap_override: int | None = None,
        compound_cap_override: int | None = None,
        stage_cap_override: int | None = None,
        phytochemical_cap_override: int | None = None,
        phytochemical_pair_cap_override: int | None = None,
    ) -> bool:
        target_key, family_key, stage_key, pair_key, ca, cb, phyto_a, phyto_b, phyto_pair = _row_keys(r)
        tgt_cap = target_cap if target_cap_override is None else target_cap_override
        fam_cap = family_cap if family_cap_override is None else family_cap_override
        pair_cap = max_per_compound_pair if pair_cap_override is None else pair_cap_override
        comp_cap = compound_cap if compound_cap_override is None else compound_cap_override
        stg_cap = stage_cap if stage_cap_override is None else stage_cap_override
        phyto_cap = phytochemical_cap if phytochemical_cap_override is None else phytochemical_cap_override
        phyto_pair_cap = phytochemical_pair_cap if phytochemical_pair_cap_override is None else phytochemical_pair_cap_override

        if target_counts.get(target_key, 0) >= tgt_cap:
            return False
        if family_counts.get(family_key, 0) >= fam_cap:
            return False
        if pair_counts.get(pair_key, 0) >= pair_cap:
            return False
        if compound_counts.get(ca, 0) >= comp_cap or compound_counts.get(cb, 0) >= comp_cap:
            return False
        if stage_counts.get(stage_key, 0) >= stg_cap:
            return False
        if phytochemical_counts.get(phyto_a, 0) >= phyto_cap or phytochemical_counts.get(phyto_b, 0) >= phyto_cap:
            return False
        if phytochemical_pair_counts.get(phyto_pair, 0) >= phyto_pair_cap:
            return False
        return True

    def _add(idx: int, r: pd.Series, phase: str) -> None:
        target_key, family_key, stage_key, pair_key, ca, cb, phyto_a, phyto_b, phyto_pair = _row_keys(r)
        selected_indices.append(idx)
        selected_set.add(idx)
        selection_phase[idx] = phase
        target_counts[target_key] = target_counts.get(target_key, 0) + 1
        family_counts[family_key] = family_counts.get(family_key, 0) + 1
        pair_counts[pair_key] = pair_counts.get(pair_key, 0) + 1
        compound_counts[ca] = compound_counts.get(ca, 0) + 1
        compound_counts[cb] = compound_counts.get(cb, 0) + 1
        stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1
        phytochemical_counts[phyto_a] = phytochemical_counts.get(phyto_a, 0) + 1
        phytochemical_counts[phyto_b] = phytochemical_counts.get(phyto_b, 0) + 1
        phytochemical_pair_counts[phyto_pair] = phytochemical_pair_counts.get(phyto_pair, 0) + 1

    def _try_add_linear(rows: pd.DataFrame, phase: str, **cap_overrides: Any) -> int:
        before = len(selected_indices)
        for idx, r in rows.iterrows():
            if len(selected_indices) >= target_rows:
                break
            if idx in selected_set:
                continue
            if _can_select(r, **cap_overrides):
                _add(int(idx), r, phase)
        return len(selected_indices) - before

    # Pre-compute a deterministic portfolio priority. This does not depend on
    # current counts, so subsequent passes remain linear.
    target_rank = df.groupby("target_enzyme_canonical").cumcount()
    family_rank = df.groupby("target_family_canonical").cumcount()
    pair_rank = df.groupby("compound_pair_canonical").cumcount()
    class_pair_rank = df.groupby("phytochemical_class_pair_key").cumcount()
    df["_portfolio_priority"] = (
        df["optimization_objective"].astype(float)
        + 0.035 / (1.0 + target_rank)
        + 0.025 / (1.0 + family_rank)
        + 0.020 / (1.0 + pair_rank)
        + 0.012 / (1.0 + class_pair_rank)
    )
    priority_df = df.sort_values("_portfolio_priority", ascending=False)

    # Pass 1: seed target breadth. Use one best row per target first, then second
    # and third rows per target if the pool supports it.
    for n in [1, 2, 3]:
        seed = df.groupby("target_enzyme_canonical", group_keys=False).head(n).groupby("target_enzyme_canonical", group_keys=False).tail(1)
        added = _try_add_linear(seed.sort_values("optimization_objective", ascending=False), f"target_breadth_seed_{n}")
        if len(selected_indices) >= target_rows:
            break
        if added == 0 and n > 1:
            break

    # Pass 2: seed compound breadth until at least 50 compounds if feasible.
    available_compounds = pd.concat([df["compound_a_canonical"], df["compound_b_canonical"]], ignore_index=True).nunique()
    desired_unique_compounds = min(50, int(available_compounds))
    for idx, r in priority_df.iterrows():
        if len(selected_indices) >= target_rows:
            break
        if idx in selected_set:
            continue
        ca = str(r.get("compound_a_canonical", ""))
        cb = str(r.get("compound_b_canonical", ""))
        current_unique = len(compound_counts)
        if current_unique >= desired_unique_compounds:
            break
        if compound_counts.get(ca, 0) > 0 and compound_counts.get(cb, 0) > 0:
            continue
        if _can_select(r):
            _add(int(idx), r, "compound_breadth_seed")

    # Pass 3: family floor. This improves entropy without using an expensive
    # repeated global search.
    family_order = sorted(df["target_family_canonical"].dropna().unique(), key=lambda k: family_counts.get(str(k), 0))
    for family_key in family_order:
        if len(selected_indices) >= target_rows:
            break
        if family_counts.get(str(family_key), 0) >= family_floor:
            continue
        fam_rows = priority_df[priority_df["target_family_canonical"] == family_key]
        for idx, r in fam_rows.iterrows():
            if len(selected_indices) >= target_rows or family_counts.get(str(family_key), 0) >= family_floor:
                break
            if idx in selected_set:
                continue
            if _can_select(r):
                _add(int(idx), r, "family_floor_seed")

    # Pass 4: strict linear fill.
    _try_add_linear(priority_df, "strict_linear_fill")

    # Pass 5: bounded relaxation. Pair and compound caps are relaxed only slightly
    # in the final pass; target/family/stage/class caps are relaxed first because
    # they affect breadth rather than chemical concentration.
    relaxation_plan = [
        (
            "breadth_cap_plus_25pct",
            {
                "target_cap_override": int(math.ceil(target_cap * 1.25)),
                "family_cap_override": int(math.ceil(family_cap * 1.25)),
                "stage_cap_override": int(math.ceil(stage_cap * 1.25)),
                "phytochemical_cap_override": int(math.ceil(phytochemical_cap * 1.25)),
                "phytochemical_pair_cap_override": int(math.ceil(phytochemical_pair_cap * 1.25)),
            },
        ),
        (
            "breadth_cap_plus_60pct",
            {
                "target_cap_override": int(math.ceil(target_cap * 1.60)),
                "family_cap_override": int(math.ceil(family_cap * 1.60)),
                "stage_cap_override": int(math.ceil(stage_cap * 1.60)),
                "phytochemical_cap_override": int(math.ceil(phytochemical_cap * 1.60)),
                "phytochemical_pair_cap_override": int(math.ceil(phytochemical_pair_cap * 1.60)),
            },
        ),
        (
            "final_bounded_fill",
            {
                "target_cap_override": int(math.ceil(target_cap * 2.00)),
                "family_cap_override": int(math.ceil(family_cap * 2.00)),
                "pair_cap_override": int(math.ceil(max_per_compound_pair * 1.35)),
                "compound_cap_override": int(math.ceil(compound_cap * 1.05)),
                "stage_cap_override": int(math.ceil(stage_cap * 2.00)),
                "phytochemical_cap_override": int(math.ceil(phytochemical_cap * 2.00)),
                "phytochemical_pair_cap_override": int(math.ceil(phytochemical_pair_cap * 1.50)),
            },
        ),
    ]
    for phase, overrides in relaxation_plan:
        if len(selected_indices) >= target_rows:
            break
        added = _try_add_linear(priority_df, phase, **overrides)
        if added:
            relaxation_events.append(f"{phase}:added_{added}")

    out = df.loc[selected_indices].copy().reset_index(drop=False).rename(columns={"index": "_selection_source_index"})
    if len(out):
        out["diversity_selection_phase"] = out["_selection_source_index"].map(selection_phase).fillna("untracked")
        out["diversity_selection_relaxed"] = out["diversity_selection_phase"].str.contains("plus|final|relaxed", case=False, na=False)
    else:
        out["diversity_selection_phase"] = pd.Series(dtype=str)
        out["diversity_selection_relaxed"] = pd.Series(dtype=bool)

    all_out_compounds = pd.concat([
        out.get("compound_a_canonical", pd.Series(dtype=str)),
        out.get("compound_b_canonical", pd.Series(dtype=str)),
    ]) if len(out) else pd.Series(dtype=str)
    all_out_phyto = pd.concat([
        out.get("compound_a_phytochemical_class_key", pd.Series(dtype=str)),
        out.get("compound_b_phytochemical_class_key", pd.Series(dtype=str)),
    ]) if len(out) else pd.Series(dtype=str)

    report = {
        "selection_policy": "fast_portfolio_breadth_selector_v2",
        "input_rows": int(len(scored)),
        "deduplicated_input_rows": int(len(df)),
        "target_rows": int(target_rows),
        "selected_rows": int(len(out)),
        "selection_phases": {str(k): int(v) for k, v in out.get("diversity_selection_phase", pd.Series(dtype=str)).value_counts().to_dict().items()},
        "relaxation_events": relaxation_events,
        "family_floor": int(family_floor),
        "family_cap_effective": int(family_cap),
        "target_cap_effective": int(target_cap),
        "compound_cap_effective": int(compound_cap),
        "stage_cap_effective": int(stage_cap),
        "phytochemical_cap_effective": int(phytochemical_cap),
        "phytochemical_pair_cap_effective": int(phytochemical_pair_cap),
        "unique_targets": int(out["target_enzyme_canonical"].nunique()) if len(out) else 0,
        "unique_target_families": int(out["target_family_canonical"].nunique()) if len(out) else 0,
        "unique_compound_pairs": int(out["compound_pair_canonical"].nunique()) if len(out) else 0,
        "unique_compounds": int(all_out_compounds.nunique()) if len(out) else 0,
        "unique_phytochemical_classes": int(all_out_phyto.nunique()) if len(out) else 0,
        "unique_phytochemical_class_pairs": int(out["phytochemical_class_pair_key"].nunique()) if len(out) else 0,
        "target_family_entropy_normalized": _norm_entropy(out["target_family_canonical"]) if len(out) else None,
        "stage_entropy_normalized": _norm_entropy(out["stage_canonical"]) if len(out) else None,
        "max_observed_per_target": int(out["target_enzyme_canonical"].value_counts().max()) if len(out) else 0,
        "max_observed_per_target_family": int(out["target_family_canonical"].value_counts().max()) if len(out) else 0,
        "max_observed_per_compound_pair": int(out["compound_pair_canonical"].value_counts().max()) if len(out) else 0,
        "max_observed_per_compound": int(all_out_compounds.value_counts().max()) if len(all_out_compounds) else 0,
        "max_observed_per_stage": int(out["stage_canonical"].value_counts().max()) if len(out) else 0,
        "max_observed_per_phytochemical_class": int(all_out_phyto.value_counts().max()) if len(all_out_phyto) else 0,
        "max_observed_per_phytochemical_class_pair": int(out["phytochemical_class_pair_key"].value_counts().max()) if len(out) else 0,
        "caps": {
            "max_rows_requested": max_rows,
            "target_rows_effective": target_rows,
            "max_per_target_effective": target_cap,
            "max_per_target_family_requested": max_per_target_family,
            "max_per_target_family_effective": family_cap,
            "min_per_target_family_floor": family_floor,
            "max_per_compound_pair": max_per_compound_pair,
            "max_per_compound_requested": max_per_compound,
            "max_per_compound_effective": compound_cap,
            "max_per_stage_effective": stage_cap,
            "max_per_phytochemical_class_effective": phytochemical_cap,
            "max_per_phytochemical_pair_effective": phytochemical_pair_cap,
        },
        "runtime_note": "linear_time_selector_no_repeated_global_rescoring",
    }

    drop_cols = [
        "target_enzyme_canonical",
        "target_family_canonical",
        "stage_canonical",
        "compound_a_canonical",
        "compound_b_canonical",
        "compound_pair_canonical",
        "compound_a_phytochemical_class_key",
        "compound_b_phytochemical_class_key",
        "phytochemical_class_pair_key",
        "_portfolio_priority",
    ]
    out = out.drop(columns=[c for c in drop_cols if c in out.columns])
    return out, report


def optimize_inhibitor_combinations(
    critical: pd.DataFrame,
    data: dict[str, Any],
    out_dir: Path,
    top_targets: int = 56,
    compounds_per_target: int = 18,
) -> pd.DataFrame:
    """Optimize inhibitor combinations with herbicide-biology-aware filters.

    This version implements the production-grade Aim 4 update:
    - compound suitability and priority classes,
    - solvent/reactive-aldehyde/control penalties,
    - herbicide target atlas matching,
    - typed inhibit-synergy evidence edges,
    - unordered-pair semantic de-duplication,
    - per-target diversity caps,
    - explicit proxy/evidence labels.

    Default top_targets is intentionally 56, not 40: downstream portfolio
    gates require at least 35 distinct final target enzymes after semantic
    deduplication, compound caps, family/stage balancing, and control filters.
    A wider upstream target shortlist gives the final selector enough eligible
    target breadth without weakening compound-quality gates.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cp = build_compound_pool(data, top_n=800)

    if not len(cp) or not len(critical):
        empty = pd.DataFrame()
        empty.to_csv(out_dir / "aim4_optimized_interventions.csv", index=False)
        write_json(out_dir / "aim4_optimization_report.json", {
            "status": "not_optimized",
            "reason": "empty_compound_pool_or_empty_critical_targets",
            "candidate_rows": 0,
            "compounds_used": int(len(cp)) if cp is not None else 0,
            "targets_used": int(len(critical)) if critical is not None else 0,
            "semantic_deduplication": True,
            "compound_pair_policy": "unordered_pair",
            "compound_filter_policy": "controls_retained_but_downranked",
        })
        cp.to_csv(out_dir / "compound_pool.csv", index=False)
        return empty

    targets = critical.copy()
    if "enzyme_name" not in targets.columns and "target_enzyme" in targets.columns:
        targets["enzyme_name"] = targets["target_enzyme"]
    if "enzyme_family" not in targets.columns and "target_family" in targets.columns:
        targets["enzyme_family"] = targets["target_family"]
    if "stage_assigned" not in targets.columns and "stage" in targets.columns:
        targets["stage_assigned"] = targets["stage"]

    required_atlas_cols = {
        "herbicide_target_family",
        "herbicide_site_of_action",
        "herbicide_target_score",
        "known_inhibitor_classes",
        "wssa_group",
        "resistance_risks",
    }
    if not required_atlas_cols.issubset(set(targets.columns)):
        atlas_rows = targets.apply(
            lambda r: match_herbicide_targets(r.get("enzyme_name"), r.get("enzyme_family"), r.get("stage_assigned")),
            axis=1,
        ).apply(pd.Series)
        # Do not create duplicate column names when Aim 3 already exposed atlas labels.
        for col in atlas_rows.columns:
            if col not in targets.columns:
                targets[col] = atlas_rows[col].values
            else:
                targets[col] = targets[col].where(targets[col].notna(), atlas_rows[col].values)

    selectivity_rows = targets.apply(lambda r: estimate_contextual_selectivity(r, FieldScenario()), axis=1).apply(pd.Series)
    targets = pd.concat([targets.reset_index(drop=True), selectivity_rows.reset_index(drop=True)], axis=1)

    targets["target_name_canonical"] = targets["enzyme_name"].map(canonicalize_text_key)
    target_dedupe_keys = [c for c in ["target_name_canonical", "enzyme_family", "stage_assigned"] if c in targets.columns]
    if target_dedupe_keys:
        targets = targets.drop_duplicates(subset=target_dedupe_keys, keep="first")

    # Prefer canonical herbicide targets, but keep high-criticality unmapped targets for discovery.
    targets["target_priority_score"] = (
        0.58 * pd.to_numeric(targets.get("critical_transition_score", 0), errors="coerce").fillna(0)
        + 0.24 * pd.to_numeric(targets.get("herbicide_target_score", 0), errors="coerce").fillna(0)
        + 0.18 * pd.to_numeric(targets.get("scenario_selectivity_margin", 0.5), errors="coerce").fillna(0.5)
    )
    targets = targets.sort_values("target_priority_score", ascending=False).head(top_targets).copy()
    write_scenario_selectivity_report(targets, out_dir, FieldScenario())

    # Select candidate compounds by intervention suitability. Control/vehicle compounds remain in compound_pool.csv,
    # but are not allowed to dominate the recommendation set.
    allowed_priority = {
        "natural_product_candidate",
        "known_inhibitor_like",
        "transition_state_mimic_candidate",
        "allelopathic_secondary_metabolite",
        "oxidative_stress_inducer_candidate",
        "low_priority_unknown",
    }
    cp_ranked = cp.sort_values(
        ["intervention_suitability_score", "natural_product_evidence_score", "active_site_compatibility_score", "hazard_proxy"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    cp2 = cp_ranked[
        cp_ranked["compound_priority_class"].isin(allowed_priority)
        & (cp_ranked["intervention_suitability_score"] >= 0.12)
    ].copy()
    # Keep more candidate compounds available for class-aware portfolio construction.
    # The final selector, not this early pool, controls dominance.
    if len(cp2) < max(24, compounds_per_target):
        cp2 = cp_ranked.head(max(140, compounds_per_target * 8)).copy()
    else:
        cp2 = cp2.head(max(180, compounds_per_target * 12)).copy()
    cp2 = cp2.reset_index(drop=True)
    effective_compounds_per_target = max(compounds_per_target, 30)

    rows: list[dict[str, Any]] = []
    epsilon = 0.92

    for _, t in targets.iterrows():
        target_text = f"{t.get('enzyme_name', '')} {t.get('enzyme_family', '')} {t.get('herbicide_target_family', '')}"
        target_hash = (abs(hash(target_text)) % 1000) / 1000.0

        # Per-target diversity: include top scientific candidates plus a deterministic sample by priority class.
        class_frames: list[pd.DataFrame] = []
        group_key = "phytochemical_class" if "phytochemical_class" in cp2.columns else "compound_priority_class"
        per_class = max(2, int(np.ceil(effective_compounds_per_target / max(1, cp2[group_key].nunique()))))
        for class_i, (_, g) in enumerate(cp2.groupby(group_key, sort=False)):
            # Include the best row in each class plus a target-specific deterministic
            # sample so each target does not reuse the same 18-20 compounds.
            g_sorted = g.sort_values(["intervention_suitability_score", "natural_product_evidence_score"], ascending=[False, False])
            head = g_sorted.head(1)
            rest = g_sorted.iloc[1:]
            n_rest = max(0, min(len(rest), per_class - len(head)))
            if n_rest:
                sampled = rest.sample(n=n_rest, random_state=int(target_hash * 10000) + 37 + class_i)
                class_frames.append(pd.concat([head, sampled], ignore_index=True, sort=False))
            else:
                class_frames.append(head)
        diversified = pd.concat(class_frames, ignore_index=True, sort=False).drop_duplicates("compound_name_canonical") if class_frames else cp2
        if len(diversified) > effective_compounds_per_target:
            top_block = diversified.head(max(8, effective_compounds_per_target // 3))
            rem = diversified.iloc[len(top_block):]
            if len(rem):
                sampled = rem.sample(n=min(len(rem), effective_compounds_per_target - len(top_block)), random_state=int(target_hash * 10000) + 11)
                subset = pd.concat([top_block, sampled], ignore_index=True, sort=False)
            else:
                subset = top_block
        else:
            subset = diversified

        compounds = subset.head(effective_compounds_per_target).to_dict("records")
        for a, b in itertools.combinations(compounds, 2):
            if canonicalize_compound_pair(a.get("compound_name"), b.get("compound_name"))[0] == canonicalize_compound_pair(a.get("compound_name"), b.get("compound_name"))[1]:
                continue

            comp_raw = (
                abs(_num(a.get("logp"), 0) - _num(b.get("logp"), 0))
                + 0.01 * abs(_num(a.get("tpsa"), 0) - _num(b.get("tpsa"), 0))
                + 0.20 * float(str(a.get("compound_priority_class")) != str(b.get("compound_priority_class")))
            )
            comp = float(np.tanh(abs(comp_raw) / 4))

            suitability_a = _num(a.get("intervention_suitability_score"), 0.2)
            suitability_b = _num(b.get("intervention_suitability_score"), 0.2)
            target_rule_score = _num(t.get("herbicide_target_score"), 0.0)
            scenario_selectivity = _num(t.get("scenario_selectivity_margin"), _num(t.get("crop_selectivity_margin"), 0.5))

            base_a = float(np.clip(
                0.18
                + 0.30 * suitability_a
                + 0.18 * _num(a.get("active_site_compatibility_score"), 0.2)
                + 0.12 * _num(a.get("known_inhibitor_similarity_score"), 0.1)
                + 0.10 * target_rule_score
                - 0.18 * _num(a.get("solvent_penalty"), 0.0)
                - 0.16 * _num(a.get("reactive_aldehyde_penalty"), 0.0)
                - 0.12 * _num(a.get("generic_assay_penalty"), 0.0),
                0,
                0.95,
            ))
            base_b = float(np.clip(
                0.18
                + 0.30 * suitability_b
                + 0.18 * _num(b.get("active_site_compatibility_score"), 0.2)
                + 0.12 * _num(b.get("known_inhibitor_similarity_score"), 0.1)
                + 0.10 * target_rule_score
                - 0.18 * _num(b.get("solvent_penalty"), 0.0)
                - 0.16 * _num(b.get("reactive_aldehyde_penalty"), 0.0)
                - 0.12 * _num(b.get("generic_assay_penalty"), 0.0),
                0,
                0.95,
            ))

            bliss = base_a + base_b - base_a * base_b
            synergy_info = score_pair_synergy(t, a, b, epsilon=epsilon)
            synergy = float(
                0.03
                + 0.18 * comp
                + 0.18 * synergy_info["synergy_group_score"]
                + 0.08 * _num(t.get("natural_inhibitor_evidence_score"), 0)
                + 0.06 * target_rule_score
            )
            combined = min(0.99, bliss + synergy * (1 - bliss))

            crop_impact = float((1 - scenario_selectivity) * combined)
            env_persist = float(np.mean([_num(a.get("persistence_proxy", 0.4), 0.4), _num(b.get("persistence_proxy", 0.4), 0.4)]))
            hazard = float(np.mean([_num(a.get("hazard_proxy", 0.4), 0.4), _num(b.get("hazard_proxy", 0.4), 0.4)]))
            suitability_mean = float(np.mean([suitability_a, suitability_b]))
            control_penalty = float(np.mean([
                _num(a.get("solvent_penalty"), 0.0) + _num(a.get("reactive_aldehyde_penalty"), 0.0) + _num(a.get("generic_assay_penalty"), 0.0),
                _num(b.get("solvent_penalty"), 0.0) + _num(b.get("reactive_aldehyde_penalty"), 0.0) + _num(b.get("generic_assay_penalty"), 0.0),
            ]))

            objective = (
                0.56 * combined
                + 0.20 * synergy_info["synergy_group_score"]
                + 0.14 * suitability_mean
                + 0.10 * scenario_selectivity
                - 0.48 * crop_impact
                - 0.28 * env_persist
                - 0.26 * hazard
                - 0.22 * control_penalty
                - 0.16 * _num(t.get("uncertainty_penalty", 0.3), 0.3)
            )

            rows.append({
                "target_enzyme": t.get("enzyme_name"),
                "target_family": t.get("enzyme_family"),
                "stage": t.get("stage_assigned"),
                "critical_transition_score": t.get("critical_transition_score"),
                "herbicide_target_family": t.get("herbicide_target_family"),
                "herbicide_site_of_action": t.get("herbicide_site_of_action"),
                "wssa_group": t.get("wssa_group"),
                "known_inhibitor_classes": t.get("known_inhibitor_classes"),
                "resistance_risks": t.get("resistance_risks"),
                "scenario_selectivity_margin": scenario_selectivity,
                "weed_vulnerability_score": t.get("weed_vulnerability_score"),
                "crop_vulnerability_score": t.get("crop_vulnerability_score"),
                "compound_a": a.get("compound_name"),
                "compound_b": b.get("compound_name"),
                "compound_a_source": a.get("source_resource"),
                "compound_b_source": b.get("source_resource"),
                "compound_a_priority_class": a.get("compound_priority_class"),
                "compound_b_priority_class": b.get("compound_priority_class"),
                "compound_a_exclusion_reason": a.get("compound_exclusion_reason"),
                "compound_b_exclusion_reason": b.get("compound_exclusion_reason"),
                "compound_a_phytochemical_class": a.get("phytochemical_class", "unclassified_or_unknown"),
                "compound_b_phytochemical_class": b.get("phytochemical_class", "unclassified_or_unknown"),
                "compound_a_phytochemical_class_score": a.get("phytochemical_class_score", 0.0),
                "compound_b_phytochemical_class_score": b.get("phytochemical_class_score", 0.0),
                "phytochemical_class_pair": pair_phytochemical_class_key({
                    "compound_a_phytochemical_class": a.get("phytochemical_class", "unclassified_or_unknown"),
                    "compound_b_phytochemical_class": b.get("phytochemical_class", "unclassified_or_unknown"),
                }),
                "compound_a_intervention_suitability_score": suitability_a,
                "compound_b_intervention_suitability_score": suitability_b,
                "intervention_suitability_score": suitability_mean,
                "compound_priority_class": pair_diversity_key({
                    "compound_a_priority_class": a.get("compound_priority_class"),
                    "compound_b_priority_class": b.get("compound_priority_class"),
                }),
                "compound_exclusion_reason": ";".join([
                    str(x) for x in [a.get("compound_exclusion_reason"), b.get("compound_exclusion_reason")] if str(x or "").strip()
                ]),
                "compound_a_functional_group_hits": a.get("functional_group_hits"),
                "compound_b_functional_group_hits": b.get("functional_group_hits"),
                "predicted_single_a": base_a,
                "predicted_single_b": base_b,
                "bliss_expected": bliss,
                "mechanistic_complementarity": comp,
                "synergy_delta": synergy,
                "inhibit_synergy": synergy_info["inhibit_synergy"],
                "synergy_group_score": synergy_info["synergy_group_score"],
                "synergy_edge_sum": synergy_info["synergy_edge_sum"],
                "epsilon_threshold": synergy_info["epsilon_threshold"],
                "synergy_match_schema": synergy_info["synergy_match_schema"],
                "compound_source_score_list": synergy_info["compound_source_score_list"],
                "compound_a_evidence_types": synergy_info["compound_a_evidence_types"],
                "compound_b_evidence_types": synergy_info["compound_b_evidence_types"],
                "predicted_combined_perturbation": combined,
                "crop_impact_estimate": crop_impact,
                "environmental_persistence_proxy": env_persist,
                "toxicity_hazard_proxy": hazard,
                "control_compound_penalty": control_penalty,
                "optimization_objective": objective,
                "functional_silencing_threshold": 0.72,
                "meets_functional_silencing_proxy": combined >= 0.72,
                "evidence_class": "model_inference_with_real_compound_and_target_rule_evidence",
                "synergy_evidence_class": "inhibit_synergy_model_inference_requires_assay_validation",
                "proxy_notes": (
                    "Combination synergy is inferred from typed inhibition evidence edges, active-site/transition-state rules, "
                    "compound suitability, and herbicide target atlas matches. It is not wet-lab validated."
                ),
            })

    scored = pd.DataFrame(rows)
    intervention_dedupe_keys: list[str] = [
        "target_enzyme_canonical",
        "target_family_canonical",
        "stage_canonical",
        "compound_pair_canonical",
    ]
    diversity_report: dict[str, Any] = {}

    if len(scored):
        # Final recommendation set: diversity-aware greedy selection across targets,
        # families, compound pairs, individual compounds, and growth stages.
        out, diversity_report = select_diverse_interventions(
            scored,
            max_rows=1000,
            max_per_target=25,
            max_per_target_family=110,
            max_per_compound_pair=12,
            max_per_compound=180,
            max_per_stage=600,
            max_per_phytochemical_class=260,
            max_per_phytochemical_pair=90,
        )
        out = out.sort_values("optimization_objective", ascending=False).reset_index(drop=True)

        # Keep useful pair class label, but drop only internal canonical helper columns.
        out = out.drop(
            columns=[
                c for c in [
                    "target_enzyme_canonical",
                    "target_family_canonical",
                    "stage_canonical",
                    "compound_a_canonical",
                    "compound_b_canonical",
                    "compound_pair_canonical",
                    "compound_a_phytochemical_class_key",
                    "compound_b_phytochemical_class_key",
                    "phytochemical_class_pair_key",
                    "_selection_source_index",
                ]
                if c in out.columns
            ]
        )
    else:
        out = pd.DataFrame()
        diversity_report = {"selection_policy": "target_family_quota_rebalanced_diversity_selector", "input_rows": 0, "selected_rows": 0}

    out.to_csv(out_dir / "aim4_optimized_interventions.csv", index=False)
    synergy_groups = build_synergy_groups(out, epsilon=epsilon)
    synergy_groups.to_csv(out_dir / "aim4_inhibit_synergy_groups.csv", index=False)

    report = {
        "status": "optimized",
        "candidate_rows": int(len(out)),
        "compounds_used": int(len(cp2)),
        "targets_used": int(len(targets)),
        "target_dedupe_keys": target_dedupe_keys,
        "intervention_dedupe_keys": intervention_dedupe_keys,
        "semantic_deduplication": True,
        "compound_pair_policy": "unordered_pair",
        "compound_filter_policy": "controls_retained_in_compound_pool_but_downranked_in_recommendations",
        "diversity_selection_report": diversity_report,
        "synergy_groups": int(len(synergy_groups)),
        "epsilon_threshold": epsilon,
        "objective": (
            "maximize predicted enzyme-state perturbation and typed inhibit-synergy while penalizing crop impact, "
            "persistence, hazard, generic controls, reactive aldehydes, and uncertainty"
        ),
        "evidence_class": "model_inference_with_real_evidence_inputs",
        "unsupported_assumption_warning": (
            "No wet-lab synergy labels are available. All pair synergy is computationally inferred and must be validated "
            "with enzyme assays and crop/weed dose-response experiments."
        ),
    }

    write_json(out_dir / "aim4_optimization_report.json", report)
    cp.to_csv(out_dir / "compound_pool.csv", index=False)
    return out

def pseudo_lab_simulations(optimized: pd.DataFrame, out_dir: Path, n_targets: int = 50) -> pd.DataFrame:
    rows = []
    if optimized is None or not len(optimized):
        return pd.DataFrame()
    doses = np.array([0, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0])
    for _, r in optimized.head(n_targets).iterrows():
        max_eff = min(0.99, float(r.get("predicted_combined_perturbation", 0.7)))
        ic50 = max(0.05, 2.5 * (1 - float(r.get("optimization_objective", 0.3))))
        hill = 1.1 + float(r.get("mechanistic_complementarity", 0.2))
        for d in doses:
            inhibition = 0 if d <= 0 else max_eff * (d**hill) / (ic50**hill + d**hill)
            weed_activity_remaining = max(0, 1 - inhibition)
            crop_activity_remaining = max(0, 1 - float(r.get("crop_impact_estimate", 0.2))*inhibition/max_eff)
            rows.append({
                "target_enzyme": r.get("target_enzyme"),
                "target_family": r.get("target_family"),
                "stage": r.get("stage"),
                "compound_a": r.get("compound_a"),
                "compound_b": r.get("compound_b"),
                "dose_relative": d,
                "predicted_inhibition": inhibition,
                "weed_activity_remaining": weed_activity_remaining,
                "crop_activity_remaining": crop_activity_remaining,
                "selectivity_index": crop_activity_remaining / max(0.001, weed_activity_remaining),
                "model": "Hill dose-response with Bliss/synergy-derived maximum effect",
                "evidence_class": "pseudo_lab_model_inference",
            })
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "pseudo_lab_dose_response.csv", index=False)
    report = {
        "status": "simulated",
        "rows": int(len(df)),
        "model": "Hill curve; parameters derived from optimization outputs and explicitly proxy/model-inferred.",
        "evidence_class": "pseudo_lab_model_inference",
    }
    write_json(out_dir / "pseudo_lab_report.json", report)
    return df


def write_proxy_and_assumption_reports(out_dir: Path) -> None:
    unsupported = [
        {"assumption": "Every weed has naturally sourced inhibitors for every critical enzyme", "status": "not_supported_as_universal", "handling": "Converted to testable hypothesis; all inhibitor availability is evidence-scored and missing direct evidence is penalized."},
        {"assumption": "A/B combinations silence enzymes at critical lifecycle points", "status": "not_supported_without_assay", "handling": "Modeled as functional activity below threshold; outputs marked pseudo_lab_model_inference until wet-lab validation."},
        {"assumption": "Crop-weed selectivity exists for every pair", "status": "not_supported_as_universal", "handling": "Implemented as crop_selectivity_margin with uncertainty penalty; broad conserved enzymes receive reduced margins."},
        {"assumption": "Taxonomy is inferior to enzyme-state signatures", "status": "hypothesis_under_test", "handling": "Aim 2 compares enzyme-state clustering against family/taxonomy-like labels with ARI and recovery metrics."},
    ]
    write_json(out_dir / "unsupported_assumptions.json", unsupported)
    proxy_rows = [
        {"component": "critical_transition_anchor_model", "proxy_type": "weak label", "description": "Known herbicide anchors and curated pass flags used as weak labels for model calibration."},
        {"component": "enzyme_smi_interaction_model", "proxy_type": "negative sampling", "description": "Mismatched sequence/SMILES pairs are proxy negatives, not experimentally confirmed non-interactions."},
        {"component": "inhibitor_combination_optimizer", "proxy_type": "typed synergy inference", "description": "Bliss/synergy score is now augmented by typed inhibition evidence edges, compound suitability, and herbicide target atlas matches; still requires lab validation."},
        {"component": "compound_suitability_filter", "proxy_type": "rule-based chemical credibility model", "description": "Solvents, buffers, generic assay chemicals, and reactive aldehydes are retained for audit but down-ranked or treated as controls."},
        {"component": "scenario_selectivity_margin", "proxy_type": "contextual crop/weed risk proxy", "description": "Computed from scenario taxa, target conservation, growth stage, and detox/stress rules; not a measured crop assay."},
    ]
    pd.DataFrame(proxy_rows).to_csv(out_dir / "proxy_evidence_report.csv", index=False)


def run_all(raw_dir: str | Path, out_dir: str | Path, artifact_dir: str | Path, limits: dict[str, Any] | None = None) -> dict[str, Any]:
    out_dir = ensure_dir(out_dir); artifact_dir = ensure_dir(artifact_dir)
    kg = build_pesi_kg(raw_dir, artifact_dir, out_dir, limits=limits)
    data = kg["data"]
    import gc, time
    gc.collect()
    print("[PESI] training/evaluating ML layers", flush=True)

    # Build the enzyme-state layer before fitting heavier text classifiers. This reduces memory contention after KG materialization.
    _t=time.time(); print("[PESI] building enzyme universe features", flush=True)
    universe = _make_enzyme_universe(data)
    features = _build_features(universe, data.get("fooddb", {}))
    print(f"[PESI] features built in {time.time()-_t:.1f}s rows={len(features)}", flush=True)
    features.to_csv(out_dir / "enzyme_universe_features.csv", index=False)

    _t=time.time(); print("[PESI] evaluating signatures", flush=True)
    sig_report = evaluate_signatures(features, out_dir)
    print(f"[PESI] signatures done in {time.time()-_t:.1f}s", flush=True)

    _t=time.time(); print("[PESI] ranking critical transition enzymes", flush=True)
    critical, critical_model_report = rank_critical_transition_enzymes(features, artifact_dir, out_dir)
    print(f"[PESI] ranking done in {time.time()-_t:.1f}s", flush=True)

    _t=time.time(); print("[PESI] optimizing interventions", flush=True)
    optimized = optimize_inhibitor_combinations(critical, data, out_dir)
    print(f"[PESI] optimization done in {time.time()-_t:.1f}s", flush=True)

    _t=time.time(); print("[PESI] pseudo-lab simulations", flush=True)
    pseudo = pseudo_lab_simulations(optimized, out_dir)
    print(f"[PESI] pseudo-lab done in {time.time()-_t:.1f}s", flush=True)

    _t=time.time(); print("[PESI] mapping compounds to FoodDB food sources", flush=True)
    try:
        food_source_report = build_food_source_artifacts(
            raw_dir=raw_dir,
            out_dir=out_dir,
            optimized=optimized,
            compound_pool=None,
            artifact_dir=artifact_dir,
            top_n_per_compound=max(1, min(200, int(os.getenv("PESI_FOOD_SOURCE_TOP_N", "30")))),
        )
    except Exception as exc:
        food_source_report = {
            "status": "failed",
            "error": repr(exc),
            "evidence_policy": "No food-source claims were emitted because FoodDB mapping failed.",
        }
        write_json(Path(out_dir) / "food_source_mapping_report.json", food_source_report)
    print(f"[PESI] food-source mapping done in {time.time()-_t:.1f}s status={food_source_report.get('status')}", flush=True)

    models = {}
    _t=time.time(); print("[PESI] family classifier", flush=True)
    family_model, family_report = train_family_classifier(data.get("curated_families", pd.DataFrame()), artifact_dir)
    print(f"[PESI] family classifier done in {time.time()-_t:.1f}s", flush=True)

    _t=time.time(); print("[PESI] enzyme-smi interaction model", flush=True)
    smi_model, smi_report = train_enzyme_smi_interaction_model(data.get("enzyme_smi_pairs", pd.DataFrame()), artifact_dir)
    print(f"[PESI] enzyme-smi done in {time.time()-_t:.1f}s", flush=True)
    models["family_classifier"] = family_model
    models["enzyme_smi_interaction"] = smi_model

    write_proxy_and_assumption_reports(out_dir)
    synergy_groups_path = Path(out_dir) / "aim4_inhibit_synergy_groups.csv"
    scenario_selectivity_path = Path(out_dir) / "scenario_selectivity.csv"
    synergy_group_rows = int(len(pd.read_csv(synergy_groups_path))) if synergy_groups_path.exists() else 0
    scenario_selectivity_rows = int(len(pd.read_csv(scenario_selectivity_path))) if scenario_selectivity_path.exists() else 0

    ml_report = {
        "family_classifier": family_report,
        "enzyme_smi_interaction_model": smi_report,
        "aim2_signature_evaluation": sig_report,
        "aim3_critical_transition_model": critical_model_report,
        "aim4_optimized_rows": int(len(optimized)) if optimized is not None else 0,
        "aim4_inhibit_synergy_group_rows": synergy_group_rows,
        "scenario_selectivity_rows": scenario_selectivity_rows,
        "pseudo_lab_rows": int(len(pseudo)) if pseudo is not None else 0,
        "food_source_mapping": food_source_report,
        "axioms_implemented": [
            "finite_enzyme_processes_as_enzyme_universe_and_stage_anchors",
            "discrete_transitions_as_development_stage_nodes_and_trajectory_curvature",
            "genetic_biochemical_environmental_context_as_feature_groups_and_uncertainty_penalties",
        ],
        "hypotheses_operationalized": [
            "enzyme_state_signatures_vs_family/taxonomy-like_labels",
            "critical_transition_enzyme_ranking_from_pathway_kinetic_lifecycle_data",
            "naturally_derived_combination_optimization_with_explicit_proxy_synergy",
        ],
        "optimization_objectives_implemented": [
            "maximize_predicted_weed_perturbation",
            "penalize_crop_impact_and_low_selectivity",
            "penalize_persistence_hazard_and_uncertainty",
        ],
    }
    write_json(out_dir / "ml_report.json", ml_report)
    joblib.dump({"models": {k: v for k, v in models.items() if v is not None}, "reports": ml_report}, artifact_dir / "model_bundle.joblib")
    write_json(out_dir / "run_manifest.json", {
        "kg_report": kg["kg_report"],
        "ml_report": ml_report,
        "outputs": sorted([p.name for p in Path(out_dir).glob("*")]),
        "artifacts": sorted([p.name for p in Path(artifact_dir).glob("*")]),
    })
    return {"kg_report": kg["kg_report"], "ml_report": ml_report}
