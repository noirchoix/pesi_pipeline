from __future__ import annotations

from typing import Any

import pandas as pd

from pesi.api.config import ApiSettings
from pesi.api.services.artifact_reader import ArtifactReader

MANDATORY_CAVEATS = [
    "Computational candidate only.",
    "Not validated for field use.",
    "Not a formulation or application recommendation.",
    "Requires toxicity, environmental, crop-safety, and wet-lab validation.",
]


def _score(value: Any, digits: int = 3) -> Any:
    try:
        return round(float(value), digits)
    except Exception:
        return value


class InterpretationService:
    """Artifact-grounded interpretation layer.

    The service deliberately reads only generated PESI artifacts and reference tables.
    It does not invent external claims and it always returns caveats suitable for
    computational pesticide/bioherbicide hypothesis generation.
    """

    def __init__(self, settings: ApiSettings):
        self.settings = settings
        self.reader = ArtifactReader(settings)

    def interpret_run(self, out_dir: str | None = None, artifact_dir: str | None = None) -> dict[str, Any]:
        benchmark = self.reader.read_json("benchmark", out_dir)
        kg = self.reader.kg_summary(out_dir, artifact_dir)
        aim3 = self.reader.read_table("aim3", out_dir, limit=10, sort_by="critical_transition_score")
        aim4 = self.reader.read_table("aim4", out_dir, limit=10, sort_by="optimization_objective")
        synergy = self.reader.read_table("synergy", out_dir, limit=5, sort_by="synergy_group_score")
        gates = benchmark.get("production_gate_summary", {}) if isinstance(benchmark, dict) else {}
        diversity = benchmark.get("aim4_diversity_summary", {}) if isinstance(benchmark, dict) else {}

        findings: list[str] = []
        if gates:
            findings.append(f"Production gate status is {gates.get('status', 'unknown')} with {gates.get('passed_gates', 0)}/{gates.get('total_gates', 0)} gates passing.")
        if diversity:
            findings.append(
                "Aim 4 portfolio contains "
                f"{diversity.get('rows', 'unknown')} rows, {diversity.get('unique_targets', 'unknown')} unique targets, "
                f"{diversity.get('unique_compounds', 'unknown')} unique compounds, and {diversity.get('unique_pairs', 'unknown')} unique pairs."
            )
        if aim3.get("rows"):
            top = aim3["rows"][0]
            findings.append(
                f"Top critical transition candidate is {top.get('enzyme_name') or top.get('target_enzyme')} "
                f"in {top.get('stage_assigned', 'an assigned stage')} with score {_score(top.get('critical_transition_score'))}."
            )
        if aim4.get("rows"):
            row = aim4["rows"][0]
            findings.append(
                f"Top intervention candidate pairs {row.get('compound_a')} with {row.get('compound_b')} "
                f"against {row.get('target_enzyme')} with objective {_score(row.get('optimization_objective'))}."
            )

        return {
            "run_summary": {
                "status": gates.get("status", "not_evaluated"),
                "main_findings": findings,
                "scientific_caveats": MANDATORY_CAVEATS,
                "kg_summary": {
                    "node_count": kg.get("node_count"),
                    "edge_count": kg.get("edge_count"),
                    "node_type_counts": kg.get("node_type_counts", {}),
                },
                "benchmark_summary": gates,
                "diversity_summary": diversity,
            },
            "critical_target_rationale": [self._target_rationale(r) for r in aim3.get("rows", [])[:8]],
            "intervention_rationale": [self._intervention_rationale(r) for r in aim4.get("rows", [])[:8]],
            "synergy_rationale": [self._synergy_rationale(r) for r in synergy.get("rows", [])[:5]],
            "evidence_policy": "Grounded only in PESI run artifacts, KG summaries, benchmark outputs, herbicide target atlas annotations, and generated compound evidence columns.",
            "caveats": MANDATORY_CAVEATS,
        }

    def interpret_target(self, target: str | None = None, row_index: int | None = None, out_dir: str | None = None) -> dict[str, Any]:
        table = self.reader.read_table("aim3", out_dir, limit=self.settings.max_table_rows)
        rows = table.get("rows", [])
        chosen = None
        if row_index is not None and row_index < len(rows):
            chosen = rows[row_index]
        elif target:
            t = target.lower()
            chosen = next((r for r in rows if t in str(r.get("enzyme_name", "")).lower()), None)
        chosen = chosen or (rows[0] if rows else None)
        return {"status": "ok" if chosen else "missing", "target_rationale": self._target_rationale(chosen) if chosen else None, "caveats": MANDATORY_CAVEATS}

    def interpret_intervention(self, request: Any, out_dir: str | None = None) -> dict[str, Any]:
        table = self.reader.read_table("aim4", out_dir, limit=self.settings.max_table_rows)
        rows = table.get("rows", [])
        chosen = None
        if getattr(request, "row_index", None) is not None and request.row_index < len(rows):
            chosen = rows[request.row_index]
        else:
            target = (getattr(request, "target_enzyme", None) or getattr(request, "target", None) or "").lower()
            a = (getattr(request, "compound_a", None) or "").lower()
            b = (getattr(request, "compound_b", None) or "").lower()
            for r in rows:
                target_ok = not target or target in str(r.get("target_enzyme", "")).lower()
                a_ok = not a or a in str(r.get("compound_a", "")).lower() or a in str(r.get("compound_b", "")).lower()
                b_ok = not b or b in str(r.get("compound_a", "")).lower() or b in str(r.get("compound_b", "")).lower()
                if target_ok and a_ok and b_ok:
                    chosen = r
                    break
        chosen = chosen or (rows[0] if rows else None)
        return {"status": "ok" if chosen else "missing", "intervention_rationale": self._intervention_rationale(chosen) if chosen else None, "caveats": MANDATORY_CAVEATS}

    def interpret_synergy_group(self, group_id: str | None = None, out_dir: str | None = None) -> dict[str, Any]:
        table = self.reader.read_table("synergy", out_dir, limit=self.settings.max_table_rows)
        rows = table.get("rows", [])
        chosen = None
        if group_id:
            chosen = next((r for r in rows if str(r.get("group_id")) == group_id), None)
        chosen = chosen or (rows[0] if rows else None)
        return {"status": "ok" if chosen else "missing", "synergy_rationale": self._synergy_rationale(chosen) if chosen else None, "caveats": MANDATORY_CAVEATS}

    def _target_rationale(self, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {}
        target = row.get("enzyme_name") or row.get("target_enzyme")
        high = bool(row.get("high_confidence_known_target_label"))
        return {
            "target": target,
            "target_family": row.get("enzyme_family") or row.get("target_family"),
            "stage": row.get("stage_assigned") or row.get("stage"),
            "why_ranked": (
                f"{target} was prioritized from pathway essentiality, kinetic/structural evidence, stage trajectory signals, "
                f"and herbicide/transition-target priors. Critical transition score: {_score(row.get('critical_transition_score'))}."
            ),
            "herbicide_biology": (
                f"Atlas match: {row.get('herbicide_target_family')}; site of action: {row.get('herbicide_site_of_action')}; "
                f"known inhibitor classes: {row.get('known_inhibitor_classes')}."
            ),
            "high_confidence_known_target_label": high,
            "high_confidence_target_basis": row.get("high_confidence_target_basis"),
            "evidence_class": row.get("evidence_class"),
            "limitations": "Ranking is computational and requires target-specific biochemical and plant assay validation.",
        }

    def _intervention_rationale(self, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {}
        return {
            "target": row.get("target_enzyme"),
            "target_family": row.get("target_family"),
            "stage": row.get("stage"),
            "compound_pair": [row.get("compound_a"), row.get("compound_b")],
            "optimization_objective": _score(row.get("optimization_objective")),
            "intervention_suitability_score": _score(row.get("intervention_suitability_score")),
            "phytochemical_class_pair": row.get("phytochemical_class_pair"),
            "rationale": (
                f"The pair combines {row.get('compound_a_priority_class')} and {row.get('compound_b_priority_class')} evidence, "
                f"with functional-group hits {row.get('compound_a_functional_group_hits')} / {row.get('compound_b_functional_group_hits')} "
                f"and predicted combined perturbation {_score(row.get('predicted_combined_perturbation'))}."
            ),
            "synergy_basis": (
                f"Inhibit-synergy flag: {row.get('inhibit_synergy')}; score {_score(row.get('synergy_group_score'))}; "
                f"schema: {row.get('synergy_match_schema')}; evidence: {row.get('synergy_evidence_class')}."
            ),
            "selectivity_notes": (
                f"Scenario selectivity margin {_score(row.get('scenario_selectivity_margin'))}; "
                f"weed vulnerability {_score(row.get('weed_vulnerability_score'))}; crop vulnerability {_score(row.get('crop_vulnerability_score'))}."
            ),
            "risk_notes": {
                "crop_impact_estimate": _score(row.get("crop_impact_estimate")),
                "toxicity_hazard_proxy": _score(row.get("toxicity_hazard_proxy")),
                "environmental_persistence_proxy": _score(row.get("environmental_persistence_proxy")),
                "control_compound_penalty": _score(row.get("control_compound_penalty")),
            },
            "evidence_class": row.get("evidence_class"),
            "caveats": MANDATORY_CAVEATS,
        }

    def _synergy_rationale(self, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {}
        return {
            "group_id": row.get("group_id"),
            "target": row.get("target_enzyme"),
            "target_family": row.get("target_family"),
            "stage": row.get("stage"),
            "members": str(row.get("members", "")).split(";"),
            "source_score_list": row.get("source_score_list"),
            "match_schema": row.get("match_schema"),
            "epsilon_threshold": row.get("epsilon_threshold"),
            "synergy_group_score": _score(row.get("synergy_group_score")),
            "rationale": "This group is ranked by typed inhibition evidence edges, not by measured wet-lab synergy.",
            "evidence_class": row.get("evidence_class"),
            "caveats": MANDATORY_CAVEATS,
        }
