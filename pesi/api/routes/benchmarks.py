from __future__ import annotations

from fastapi import APIRouter, Depends

from pesi.api.auth import AuthContext
from pesi.api.config import ApiSettings, get_settings
from pesi.api.services.artifact_reader import ArtifactReader

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("/summary")
def summary(_auth: AuthContext, out_dir: str | None = None, settings: ApiSettings = Depends(get_settings)):
    return ArtifactReader(settings).benchmark_summary(out_dir)


@router.get("/leaderboard")
def leaderboard(_auth: AuthContext, out_dir: str | None = None, settings: ApiSettings = Depends(get_settings)):
    return ArtifactReader(settings).read_table("leaderboard", out_dir, limit=500)


@router.get("/gates")
def gates(_auth: AuthContext, out_dir: str | None = None, settings: ApiSettings = Depends(get_settings)):
    return ArtifactReader(settings).benchmark_gates(out_dir)


@router.get("/report")
def report(_auth: AuthContext, out_dir: str | None = None, settings: ApiSettings = Depends(get_settings)):
    return ArtifactReader(settings).read_json("benchmark", out_dir)
