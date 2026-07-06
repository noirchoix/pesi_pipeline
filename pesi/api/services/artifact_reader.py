from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from pesi.api.config import ApiSettings


CSV_MAP = {
    "aim2": "aim2_signature_evaluation.json",
    "aim2-signatures": "enzyme_state_signatures.csv",
    "aim3": "aim3_critical_transition_enzymes.csv",
    "aim4": "aim4_optimized_interventions.csv",
    "synergy": "aim4_inhibit_synergy_groups.csv",
    "scenario-selectivity": "scenario_selectivity.csv",
    "compound-pool": "compound_pool.csv",
    "pseudo-lab": "pseudo_lab_dose_response.csv",
    "leaderboard": "benchmark_leaderboard.csv",
}

JSON_MAP = {
    "kg-summary": "aim1_kg_report.json",
    "benchmark": "benchmark_report.json",
    "ml-report": "ml_report.json",
    "run-manifest": "run_manifest.json",
    "aim4-report": "aim4_optimization_report.json",
    "scenario-report": "scenario_selectivity_report.json",
    "unsupported-assumptions": "unsupported_assumptions.json",
}


def _jsonable(value: Any) -> Any:
    if pd.isna(value) if not isinstance(value, (list, dict, tuple, set)) else False:
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    if isinstance(value, float) and (value != value):
        return None
    return value


class ArtifactReader:
    def __init__(self, settings: ApiSettings):
        self.settings = settings

    def out_dir(self, value: str | Path | None = None) -> Path:
        return self.settings.resolve_out_dir(value)

    def artifact_dir(self, value: str | Path | None = None) -> Path:
        return self.settings.resolve_artifact_dir(value)

    def json_path(self, key: str, out_dir: str | Path | None = None) -> Path:
        if key not in JSON_MAP:
            raise KeyError(key)
        return self.out_dir(out_dir) / JSON_MAP[key]

    def csv_path(self, key: str, out_dir: str | Path | None = None) -> Path:
        if key not in CSV_MAP:
            raise KeyError(key)
        return self.out_dir(out_dir) / CSV_MAP[key]

    def read_json(self, key: str, out_dir: str | Path | None = None) -> dict[str, Any]:
        path = self.json_path(key, out_dir)
        if not path.exists():
            return {"status": "missing", "path": str(path)}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            return {"status": "ok", "value": data}
        except json.JSONDecodeError as exc:
            return {"status": "error", "path": str(path), "error": str(exc)}

    def read_table(
        self,
        key: str,
        out_dir: str | Path | None = None,
        limit: int | None = None,
        offset: int = 0,
        query: str | None = None,
        filters: dict[str, str] | None = None,
        sort_by: str | None = None,
        descending: bool = True,
    ) -> dict[str, Any]:
        path = self.csv_path(key, out_dir)
        lim = min(limit or self.settings.default_table_rows, self.settings.max_table_rows)
        if not path.exists():
            return {"status": "missing", "path": str(path), "rows": [], "total_rows": 0, "limit": lim, "offset": offset, "columns": []}

        df = pd.read_csv(path)
        df = self._apply_filters(df, query=query, filters=filters)
        if sort_by and sort_by in df.columns:
            df = df.sort_values(sort_by, ascending=not descending, kind="mergesort")
        total = len(df)
        page = df.iloc[offset: offset + lim].copy()
        page = page.where(pd.notnull(page), None)
        return {
            "status": "ok",
            "path": str(path),
            "rows": [{k: _jsonable(v) for k, v in row.items()} for row in page.to_dict("records")],
            "total_rows": total,
            "limit": lim,
            "offset": offset,
            "columns": list(df.columns),
        }

    def _apply_filters(self, df: pd.DataFrame, query: str | None, filters: dict[str, str] | None) -> pd.DataFrame:
        out = df
        for key, val in (filters or {}).items():
            if val and key in out.columns:
                out = out[out[key].astype(str).str.contains(str(val), case=False, na=False)]
        if query:
            q = str(query)
            mask = pd.Series(False, index=out.index)
            text_cols = [c for c in out.columns if out[c].dtype == object]
            for col in text_cols:
                mask = mask | out[col].astype(str).str.contains(q, case=False, na=False)
            out = out[mask]
        return out

    def list_artifacts(self, out_dir: str | Path | None = None, artifact_dir: str | Path | None = None) -> dict[str, Any]:
        dirs = [self.out_dir(out_dir), self.artifact_dir(artifact_dir)]
        files: list[dict[str, Any]] = []
        for base in dirs:
            if not base.exists():
                continue
            for path in sorted(base.glob("*")):
                if path.is_file():
                    files.append({
                        "name": path.name,
                        "path": str(path),
                        "size_bytes": path.stat().st_size,
                        "kind": "artifact" if base.name.startswith("artifact") else "output",
                    })
        return {"status": "ok", "files": files, "count": len(files)}

    def kg_summary(self, out_dir: str | Path | None = None, artifact_dir: str | Path | None = None) -> dict[str, Any]:
        report = self.read_json("kg-summary", out_dir)
        db_path = self.artifact_dir(artifact_dir) / "pesi_kg.sqlite"
        if db_path.exists():
            try:
                report["sqlite"] = self._sqlite_counts(db_path)
            except Exception as exc:
                report["sqlite_error"] = str(exc)
        return report

    def _sqlite_counts(self, db_path: Path) -> dict[str, Any]:
        with sqlite3.connect(db_path) as con:
            tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", con)["name"].tolist()
            counts: dict[str, int] = {}
            for table in tables[:50]:
                try:
                    counts[table] = int(pd.read_sql_query(f'SELECT COUNT(*) AS n FROM "{table}"', con)["n"].iloc[0])
                except Exception:
                    continue
        return {"path": str(db_path), "tables": tables, "table_counts": counts}

    def benchmark_summary(self, out_dir: str | Path | None = None) -> dict[str, Any]:
        report = self.read_json("benchmark", out_dir)
        if report.get("status") == "missing":
            return report
        gates = report.get("production_gate_summary", {})
        diversity = report.get("aim4_diversity_summary", {})
        return {
            "status": "ok",
            "production_gate_summary": gates,
            "aim4_diversity_summary": diversity,
            "evidence_class": report.get("evidence_class"),
            "leaderboard_rows": report.get("benchmarks", {}).get("leaderboard_rows"),
        }

    def benchmark_gates(self, out_dir: str | Path | None = None) -> dict[str, Any]:
        report = self.read_json("benchmark", out_dir)
        gates = report.get("production_gate_summary", {}).get("gates", [])
        return {"status": "ok" if gates else "missing", "gates": gates, "summary": report.get("production_gate_summary", {})}
