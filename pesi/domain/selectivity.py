from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pesi.domain.compound_rules import canonicalize_text_key
from pesi.schemas.scenario import FieldScenario


def load_field_scenario(path: str | Path | None = None) -> FieldScenario:
    if path is None:
        return FieldScenario()
    p = Path(path)
    if not p.exists():
        return FieldScenario(scenario_id=str(path), evidence_class="missing_scenario_file_defaulted")
    data = json.loads(p.read_text(encoding="utf-8"))
    return FieldScenario.model_validate(data)


def _text_hit_any(text: str, values: list[str]) -> float:
    c = canonicalize_text_key(text)
    vals = [canonicalize_text_key(v) for v in values if v]
    return 1.0 if vals and any(v in c or c in v for v in vals) else 0.0


def estimate_contextual_selectivity(target: pd.Series | dict[str, Any], scenario: FieldScenario | None = None) -> dict[str, Any]:
    scenario = scenario or FieldScenario()
    get = target.get if hasattr(target, "get") else dict(target).get
    enzyme_name = str(get("enzyme_name", get("target_enzyme", "")) or "")
    enzyme_family = str(get("enzyme_family", get("target_family", "")) or "")
    target_family = str(get("herbicide_target_family", "") or "")
    stage = str(get("stage_assigned", get("stage", scenario.growth_stage or "")) or "")
    text = f"{enzyme_name} {enzyme_family} {target_family}"

    # These values are contextual proxies. They are explicit because measured crop/weed assays are not available.
    crop_overlap = max(_text_hit_any(text, scenario.crop_taxa), _text_hit_any(text, scenario.crop_family))
    weed_overlap = max(_text_hit_any(text, scenario.weed_taxa), _text_hit_any(text, scenario.weed_family))

    broad_conserved = 1.0 if any(tok in canonicalize_text_key(text) for tok in ["rubisco", "photosystem", "pepc", "glycolysis", "respiration"]) else 0.0
    detox_or_stress = 1.0 if any(tok in canonicalize_text_key(text) for tok in ["p450", "glutathione", "glycosyltransferase", "peroxidase", "catalase", "sod"]) else 0.0
    meristem_specific = 1.0 if stage in {"germination", "seedling_emergence", "early_vegetative"} else 0.0

    weed_vulnerability = float(np.clip(0.42 + 0.18 * weed_overlap + 0.16 * meristem_specific + 0.08 * _safe_float(get("critical_transition_score"), 0.5) - 0.10 * detox_or_stress, 0, 1))
    crop_vulnerability = float(np.clip(0.38 + 0.20 * crop_overlap + 0.18 * broad_conserved - 0.10 * meristem_specific + 0.05 * detox_or_stress, 0, 1))
    selectivity_margin = float(np.clip(weed_vulnerability - crop_vulnerability + 0.5, 0, 1))

    return {
        "scenario_id": scenario.scenario_id,
        "weed_vulnerability_score": weed_vulnerability,
        "crop_vulnerability_score": crop_vulnerability,
        "scenario_selectivity_margin": selectivity_margin,
        "scenario_crop_taxa": ";".join(scenario.crop_taxa),
        "scenario_weed_taxa": ";".join(scenario.weed_taxa),
        "selectivity_evidence_class": "contextual_model_inference_requires_crop_weed_assay_validation",
    }


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


def write_scenario_selectivity_report(targets: pd.DataFrame, out_dir: str | Path, scenario: FieldScenario | None = None) -> dict[str, Any]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    scenario = scenario or FieldScenario()
    if targets is None or not len(targets):
        report = {"status": "not_evaluated", "reason": "no_targets", "scenario_id": scenario.scenario_id}
        (out_path / "scenario_selectivity_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    rows = []
    for _, r in targets.iterrows():
        row = dict(r)
        row.update(estimate_contextual_selectivity(r, scenario))
        rows.append(row)
    df = pd.DataFrame(rows)
    keep = [c for c in ["enzyme_name", "target_enzyme", "enzyme_family", "target_family", "stage_assigned", "stage", "scenario_selectivity_margin", "weed_vulnerability_score", "crop_vulnerability_score", "selectivity_evidence_class"] if c in df.columns]
    df[keep].to_csv(out_path / "scenario_selectivity.csv", index=False)
    report = {
        "status": "evaluated",
        "scenario_id": scenario.scenario_id,
        "rows": int(len(df)),
        "mean_selectivity_margin": float(df["scenario_selectivity_margin"].mean()) if "scenario_selectivity_margin" in df.columns else None,
        "evidence_class": "contextual_model_inference_requires_crop_weed_assay_validation",
    }
    (out_path / "scenario_selectivity_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
