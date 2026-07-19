from __future__ import annotations

from typing import Any

import pandas as pd

from pesi.api.config import ApiSettings
from pesi.api.services.artifact_reader import ArtifactReader
from pesi.domain.compound_rules import canonicalize_compound_pair, canonicalize_text_key
from pesi.domain.enzyme_identity import resolve_enzyme_identity
from pesi.domain.herbicide_targets import match_herbicide_targets
from pesi.domain.scientific_semantics import classify_selectivity_scope

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
            requested = resolve_enzyme_identity(target)
            requested_id = requested.get("canonical_id")
            chosen = next(
                (
                    r for r in rows
                    if resolve_enzyme_identity(
                        r.get("enzyme_name") or r.get("target_enzyme"),
                        r.get("enzyme_family") or r.get("target_family"),
                    ).get("canonical_id") == requested_id
                ),
                None,
            )
        chosen = chosen or (rows[0] if rows else None)
        return {"status": "ok" if chosen else "missing", "target_rationale": self._target_rationale(chosen) if chosen else None, "caveats": MANDATORY_CAVEATS}

    def interpret_intervention(self, request: Any, out_dir: str | None = None) -> dict[str, Any]:
        table = self.reader.read_table("aim4", out_dir, limit=self.settings.max_table_rows)
        rows = table.get("rows", [])
        chosen = None
        if getattr(request, "row_index", None) is not None and request.row_index < len(rows):
            chosen = rows[request.row_index]
        else:
            requested_target = getattr(request, "target_enzyme", None) or getattr(request, "target", None) or ""
            requested_target_id = resolve_enzyme_identity(requested_target).get("canonical_id") if requested_target else None
            requested_a = canonicalize_text_key(getattr(request, "compound_a", None) or "")
            requested_b = canonicalize_text_key(getattr(request, "compound_b", None) or "")
            for r in rows:
                row_target_id = resolve_enzyme_identity(r.get("target_enzyme"), r.get("target_family")).get("canonical_id")
                target_ok = not requested_target_id or row_target_id == requested_target_id
                row_pair = set(canonicalize_compound_pair(r.get("compound_a"), r.get("compound_b")))
                a_ok = not requested_a or requested_a in row_pair
                b_ok = not requested_b or requested_b in row_pair
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
        reported_target = row.get("enzyme_name") or row.get("target_enzyme")
        reported_family = row.get("enzyme_family") or row.get("target_family")
        identity = resolve_enzyme_identity(reported_target, reported_family, source=row.get("source_evidence"))
        atlas = match_herbicide_targets(
            identity.get("canonical_name"),
            identity.get("canonical_family"),
            row.get("stage_assigned") or row.get("stage"),
        )
        mapping_status = atlas.get("target_match_status")
        if mapping_status in {"validated", "validated_target"}:
            herbicide_context = (
                f"Validated target-specific atlas mapping: {atlas.get('herbicide_target_family')}; "
                f"site of action: {atlas.get('herbicide_site_of_action')}; "
                f"curated inhibitor classes: {atlas.get('known_inhibitor_classes') or 'not listed'}."
            )
        elif mapping_status == "family_context":
            herbicide_context = (
                "Only broad family/process context is available. No target-specific inhibitor class or WSSA group is asserted."
            )
        else:
            herbicide_context = (
                "No target-specific herbicide-atlas identity was validated; pathway and inhibitor-class claims are withheld."
            )
        high = bool(row.get("high_confidence_known_target_label")) and mapping_status in {"validated", "validated_target"}
        return {
            "target": identity.get("canonical_name"),
            "target_reported": reported_target,
            "target_canonical_id": identity.get("canonical_id"),
            "target_family": identity.get("canonical_family"),
            "target_family_reported": reported_family,
            "identity_resolution": identity,
            "stage": row.get("stage_assigned") or row.get("stage"),
            "why_ranked": (
                f"{identity.get('canonical_name')} was ranked using pathway-essentiality and enzyme-state model signals, "
                f"available kinetic/structural/plant-context evidence, and uncertainty penalties. "
                f"Critical-transition score: {_score(row.get('critical_transition_score'))}. "
                "A strong model signal is not presented as confirmed pathway membership when target-specific atlas identity is unresolved."
            ),
            "herbicide_biology": herbicide_context,
            "target_atlas_validation": atlas,
            "high_confidence_known_target_label": high,
            "high_confidence_target_basis": row.get("high_confidence_target_basis") if high else None,
            "evidence_class": row.get("evidence_class"),
            "limitations": "Ranking is computational and requires target-specific biochemical and plant assay validation.",
        }

    def _intervention_rationale(self, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {}
        reported_target = row.get("target_enzyme")
        reported_family = row.get("target_family")
        identity = resolve_enzyme_identity(reported_target, reported_family)
        ca, cb = canonicalize_compound_pair(row.get("compound_a"), row.get("compound_b"))
        display_pair = sorted(
            [str(row.get("compound_a") or ""), str(row.get("compound_b") or "")],
            key=canonicalize_text_key,
        )
        scope = classify_selectivity_scope(row)
        scope_note = (
            "Target-specific crop-versus-weed inputs were present."
            if scope["selectivity_scope"] == "target_specific"
            else "This is a scenario-level baseline applied to the target context, not a target-specific selectivity measurement."
        )
        atlas = match_herbicide_targets(
            identity.get("canonical_name"), identity.get("canonical_family"), row.get("stage")
        )
        return {
            "target": identity.get("canonical_name"),
            "target_reported": reported_target,
            "target_canonical_id": identity.get("canonical_id"),
            "target_family": identity.get("canonical_family"),
            "target_family_reported": reported_family,
            "identity_resolution": identity,
            "target_atlas_validation": atlas,
            "stage": row.get("stage"),
            "compound_pair": display_pair,
            "canonical_pair_key": f"{ca}||{cb}",
            "optimization_objective": _score(row.get("optimization_objective")),
            "optimization_objective_raw": _score(row.get("optimization_objective_raw")),
            "evidence_adjusted_priority": row.get("evidence_adjusted_priority") or "Not evaluated in this artifact",
            "evidence_adjusted_priority_score": _score(row.get("evidence_adjusted_priority_score")),
            "scientific_priority_gating_reasons": str(row.get("scientific_priority_gating_reasons") or "").split(";") if row.get("scientific_priority_gating_reasons") else [],
            "intervention_suitability_score": _score(row.get("intervention_suitability_score")),
            "phytochemical_class_pair": row.get("phytochemical_class_pair"),
            "rationale": (
                f"The pair combines {row.get('compound_a_priority_class')} and {row.get('compound_b_priority_class')} evidence, "
                f"with functional-group hits {row.get('compound_a_functional_group_hits')} / {row.get('compound_b_functional_group_hits')} "
                f"and predicted combined perturbation {_score(row.get('predicted_combined_perturbation'))}. "
                "These are model-derived screening features rather than measured compound-target engagement."
            ),
            "synergy_basis": (
                f"Inhibit-synergy flag: {row.get('inhibit_synergy')}; score {_score(row.get('synergy_group_score'))}; "
                f"schema: {row.get('synergy_match_schema')}; evidence: {row.get('synergy_evidence_class')}."
            ),
            "selectivity_notes": (
                f"Weed-minus-crop selectivity difference {_score(row.get('scenario_selectivity_margin'))}; "
                f"centered ranking index {_score(row.get('scenario_selectivity_index'))}; "
                f"weed vulnerability {_score(row.get('weed_vulnerability_score'))}; crop vulnerability {_score(row.get('crop_vulnerability_score'))}. "
                f"{scope_note} The centered index is used for ranking and must not be described as the biological difference."
            ),
            "selectivity_scope": scope,
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
