from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from pesi.api.config import ApiSettings
from pesi.api.services.interpretation_service import InterpretationService, MANDATORY_CAVEATS


class ReportBuilder:
    def __init__(self, settings: ApiSettings):
        self.settings = settings
        self.interpreter = InterpretationService(settings)

    def build_json_report(self, out_dir: str | None = None, artifact_dir: str | None = None) -> dict[str, Any]:
        interpretation = self.interpreter.interpret_run(out_dir=out_dir, artifact_dir=artifact_dir)
        return {
            "report_type": "full_scientific_interpretation_report",
            "title": "PESI-KG Scientific Run Interpretation",
            "sections": {
                "run_summary": interpretation["run_summary"],
                "critical_targets": interpretation["critical_target_rationale"],
                "intervention_portfolio": interpretation["intervention_rationale"],
                "synergy_graph": interpretation["synergy_rationale"],
                "caveats": MANDATORY_CAVEATS,
            },
            "evidence_policy": interpretation["evidence_policy"],
        }

    def build_html_report(self, out_dir: str | None = None, artifact_dir: str | None = None) -> str:
        report = self.build_json_report(out_dir, artifact_dir)
        summary = report["sections"]["run_summary"]
        targets = report["sections"]["critical_targets"]
        interventions = report["sections"]["intervention_portfolio"]
        caveats = report["sections"]["caveats"]
        def esc(x: Any) -> str:
            return html.escape(str(x if x is not None else ""))
        findings = "".join(f"<li>{esc(x)}</li>" for x in summary.get("main_findings", []))
        caveat_html = "".join(f"<li>{esc(x)}</li>" for x in caveats)
        target_html = "".join(
            f"<article><h3>{esc(t.get('target'))}</h3><p>{esc(t.get('why_ranked'))}</p><p><strong>Biology:</strong> {esc(t.get('herbicide_biology'))}</p><p><strong>Evidence:</strong> {esc(t.get('evidence_class'))}</p></article>"
            for t in targets
        )
        intervention_html = "".join(
            f"<article><h3>{esc(' + '.join([str(i) for i in r.get('compound_pair', [])]))}</h3><p><strong>Target:</strong> {esc(r.get('target'))} / {esc(r.get('target_family'))}</p><p>{esc(r.get('rationale'))}</p><p><strong>Synergy:</strong> {esc(r.get('synergy_basis'))}</p><p><strong>Selectivity:</strong> {esc(r.get('selectivity_notes'))}</p></article>"
            for r in interventions
        )
        return f"""<!doctype html>
<html lang=\"en\">
<head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{esc(report['title'])}</title>
<style>
:root {{ --ink:#17211b; --muted:#5b655f; --line:#dce5dd; --paper:#fbf9ef; --panel:#ffffff; --accent:#2f6b4f; --warn:#8a4a12; }}
body {{ margin:0; font-family: ui-serif, Georgia, serif; background:var(--paper); color:var(--ink); line-height:1.55; }}
main {{ max-width: 1040px; margin: 0 auto; padding: 48px 24px; }}
h1 {{ font-size: clamp(2.2rem, 5vw, 4.5rem); line-height:.95; letter-spacing:-.05em; max-width: 820px; }}
section {{ margin: 36px 0; }}
article {{ background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 20px; margin: 14px 0; box-shadow: 0 12px 30px rgba(20,30,20,.06); }}
.badge {{ display:inline-block; padding:6px 10px; border:1px solid var(--accent); border-radius:999px; color:var(--accent); font-weight:700; }}
.caveat {{ border-color:#e2c8a2; background:#fff8eb; }}
</style></head><body><main>
<p class=\"badge\">PESI-KG Computational Research Report</p>
<h1>{esc(report['title'])}</h1>
<section><h2>Run summary</h2><ul>{findings}</ul></section>
<section class=\"caveat\"><h2>Scientific caveats</h2><ul>{caveat_html}</ul></section>
<section><h2>Critical target rationale</h2>{target_html}</section>
<section><h2>Intervention portfolio rationale</h2>{intervention_html}</section>
</main></body></html>"""

    def persist_html_report(self, out_dir: str | None = None, artifact_dir: str | None = None, report_id: str = "latest") -> Path:
        output_dir = self.settings.resolve_out_dir(out_dir)
        report_dir = output_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / f"{report_id}.html"
        path.write_text(self.build_html_report(out_dir, artifact_dir), encoding="utf-8")
        return path
