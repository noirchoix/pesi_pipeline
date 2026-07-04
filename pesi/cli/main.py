from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import pandas as pd
import typer

from pesi.core.registry import bootstrap_raw, base_registry
from pesi.core.utils import ensure_dir, write_json
from pesi.ml.pipeline import run_all
from pesi.sabio.client import fetch_kinlaw_entries
from pesi.config import get_run_profile
from pesi.benchmarks.evaluate import evaluate_outputs

app = typer.Typer(help="PESI-KG production research backend CLI")


@app.command()
def bootstrap(
    source_dir: str = typer.Option(..., help="Directory containing uploaded source files, e.g. Downloads"),
    raw: str = typer.Option("raw", help="Normalized raw directory to create inside project"),
    force: bool = typer.Option(False, help="Overwrite/extract existing normalized files"),
):
    df = bootstrap_raw(source_dir, raw, force=force)
    typer.echo(f"Bootstrapped {len(df)} resource records into {raw}")
    typer.echo(str(Path(raw) / "_registry" / "resource_registry_bootstrap.csv"))


@app.command("fetch-sabio")
def fetch_sabio(
    raw: str = typer.Option("raw", help="Normalized raw directory"),
    queries: Optional[List[str]] = typer.Option(None, help="Solr queries, e.g. ECNumber:1.1.1.1"),
    page_size: int = typer.Option(100, help="Rows per SABIO page"),
    max_pages: int = typer.Option(2, help="Max pages per query"),
):
    q = queries or ["ParameterType:Ki", "ParameterType:Km", "ParameterType:kcat", "EnzymeName:*synthase*"]
    manifest = fetch_kinlaw_entries(raw, q, page_size=page_size, max_pages=max_pages)
    typer.echo(json.dumps(manifest, indent=2)[:4000])


@app.command("run-all")
def run_all_cmd(
    raw: str = typer.Option("raw", help="Normalized raw directory"),
    out: str = typer.Option("outputs", help="Output directory"),
    artifact: str = typer.Option("artifacts", help="Artifact directory"),
    sabio_mode: str = typer.Option("offline", help="offline/cache. Online fetching is done via fetch-sabio first."),
    profile: str = typer.Option("audit", help="Run profile: audit, medium, large, full"),
    full: bool = typer.Option(False, help="Deprecated alias for --profile full."),
):
    limits = None if full or profile.lower() == "full" else get_run_profile(profile)
    result = run_all(raw, out, artifact, limits=limits)
    typer.echo("PESI production run complete.")
    typer.echo(json.dumps({"kg": result["kg_report"], "ml_keys": list(result["ml_report"].keys()), "profile": "full" if limits is None else profile}, indent=2, default=str)[:5000])
    # Large scientific DataFrames can make interpreter shutdown slow. CLI exits fast after all outputs are flushed.
    import sys, os
    sys.stdout.flush(); sys.stderr.flush(); os._exit(0)


@app.command()
def audit(out: str = typer.Option("outputs", help="Output directory")):
    outp = Path(out)
    manifest = outp / "run_manifest.json"
    if not manifest.exists():
        typer.echo("No run_manifest.json found. Run run-all first.")
        raise typer.Exit(code=1)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    typer.echo(json.dumps(data, indent=2)[:8000])


@app.command()
def recommend(
    out: str = typer.Option("outputs", help="Output directory"),
    stage: str = typer.Option("germination", help="Development stage"),
    top_k: int = typer.Option(10, help="Top rows"),
):
    p = Path(out) / "aim4_optimized_interventions.csv"
    if not p.exists():
        typer.echo("No optimized interventions found. Run run-all first.")
        raise typer.Exit(code=1)
    df = pd.read_csv(p)
    if "stage" in df.columns:
        df = df[df["stage"].astype(str).str.contains(stage, case=False, na=False)]
    cols = [c for c in ["stage", "target_enzyme", "target_family", "compound_a", "compound_b", "predicted_combined_perturbation", "crop_impact_estimate", "optimization_objective", "evidence_class"] if c in df.columns]
    typer.echo(df[cols].head(top_k).to_string(index=False))


@app.command("benchmark")
def benchmark_cmd(
    out: str = typer.Option("outputs", help="Output directory"),
    artifact: str = typer.Option("artifacts", help="Artifact directory"),
):
    report = evaluate_outputs(out, artifact)
    typer.echo(json.dumps(report, indent=2, default=str)[:8000])

if __name__ == "__main__":
    app()
