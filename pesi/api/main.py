from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Query
from pydantic import BaseModel

app = FastAPI(title="PESI-KG production API", version="0.3.0")

OUTPUT_DIR = Path("outputs")


@app.get("/health")
def health():
    return {"status": "ok", "service": "PESI-KG production"}


@app.get("/reports/run-manifest")
def run_manifest():
    p = OUTPUT_DIR / "run_manifest.json"
    if not p.exists():
        return {"status": "missing", "message": "Run pipeline first."}
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/critical-enzymes")
def critical_enzymes(stage: Optional[str] = Query(None), top_k: int = Query(25, ge=1, le=500)):
    p = OUTPUT_DIR / "aim3_critical_transition_enzymes.csv"
    if not p.exists():
        return {"status": "missing", "rows": []}
    df = pd.read_csv(p)
    if stage and "stage_assigned" in df.columns:
        df = df[df["stage_assigned"].astype(str).str.contains(stage, case=False, na=False)]
    return {"status": "ok", "rows": df.head(top_k).to_dict("records")}


@app.get("/optimized-interventions")
def optimized_interventions(stage: Optional[str] = Query(None), target: Optional[str] = Query(None), top_k: int = Query(25, ge=1, le=500)):
    p = OUTPUT_DIR / "aim4_optimized_interventions.csv"
    if not p.exists():
        return {"status": "missing", "rows": []}
    df = pd.read_csv(p)
    if stage and "stage" in df.columns:
        df = df[df["stage"].astype(str).str.contains(stage, case=False, na=False)]
    if target and "target_enzyme" in df.columns:
        df = df[df["target_enzyme"].astype(str).str.contains(target, case=False, na=False)]
    return {"status": "ok", "rows": df.head(top_k).to_dict("records")}


@app.get("/pseudo-lab")
def pseudo_lab(target: Optional[str] = Query(None), top_k: int = Query(100, ge=1, le=1000)):
    p = OUTPUT_DIR / "pseudo_lab_dose_response.csv"
    if not p.exists():
        return {"status": "missing", "rows": []}
    df = pd.read_csv(p)
    if target and "target_enzyme" in df.columns:
        df = df[df["target_enzyme"].astype(str).str.contains(target, case=False, na=False)]
    return {"status": "ok", "rows": df.head(top_k).to_dict("records")}


@app.get("/synergy-groups")
def synergy_groups(top_k: int = Query(25, ge=1, le=500)):
    p = OUTPUT_DIR / "aim4_inhibit_synergy_groups.csv"
    if not p.exists():
        return {"status": "missing", "rows": []}
    df = pd.read_csv(p)
    return {"status": "ok", "rows": df.head(top_k).to_dict("records")}


@app.get("/benchmarks")
def benchmark_report():
    p = OUTPUT_DIR / "benchmark_report.json"
    if not p.exists():
        return {"status": "missing", "message": "Run benchmark first."}
    return json.loads(p.read_text(encoding="utf-8"))
