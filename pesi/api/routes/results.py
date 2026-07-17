from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from pesi.api.auth import AuthContext
from pesi.api.config import ApiSettings, get_settings
from pesi.api.services.artifact_reader import ArtifactReader

router = APIRouter(prefix="/results", tags=["results"])


def reader(settings: ApiSettings) -> ArtifactReader:
    return ArtifactReader(settings)


@router.get("/kg-summary")
def kg_summary(_auth: AuthContext, out_dir: str | None = None, artifact_dir: str | None = None, settings: ApiSettings = Depends(get_settings)):
    return reader(settings).kg_summary(out_dir, artifact_dir)


@router.get("/aim2")
def aim2(_auth: AuthContext, settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_json("aim2", out_dir)


@router.get("/aim2-signatures")
def aim2_signatures(_auth: AuthContext, q: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("aim2-signatures", out_dir, limit=limit, offset=offset, query=q)


@router.get("/aim3")
def aim3(_auth: AuthContext, q: str | None = None, stage: str | None = None, family: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("aim3", out_dir, limit=limit, offset=offset, query=q, filters={"stage_assigned": stage or "", "enzyme_family": family or ""}, sort_by="critical_transition_score")


@router.get("/aim4")
def aim4(_auth: AuthContext, q: str | None = None, stage: str | None = None, target: str | None = None, family: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("aim4", out_dir, limit=limit, offset=offset, query=q, filters={"stage": stage or "", "target_enzyme": target or "", "target_family": family or ""}, sort_by="optimization_objective")


@router.get("/synergy")
def synergy(_auth: AuthContext, q: str | None = None, target: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("synergy", out_dir, limit=limit, offset=offset, query=q, filters={"target_enzyme": target or ""}, sort_by="synergy_group_score")


@router.get("/scenario-selectivity")
def scenario_selectivity(_auth: AuthContext, q: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("scenario-selectivity", out_dir, limit=limit, offset=offset, query=q, sort_by="scenario_selectivity_margin")


@router.get("/compound-pool")
def compound_pool(_auth: AuthContext, q: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("compound-pool", out_dir, limit=limit, offset=offset, query=q, sort_by="intervention_suitability_score")


@router.get("/food-source-report")
def food_source_report(_auth: AuthContext, settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_json("food-source-report", out_dir)


@router.get("/fooddb-matches")
def fooddb_matches(_auth: AuthContext, q: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("fooddb-matches", out_dir, limit=limit, offset=offset, query=q, sort_by="match_confidence")


@router.get("/food-sources")
def food_sources(_auth: AuthContext, q: str | None = None, compound: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("food-sources", out_dir, limit=limit, offset=offset, query=q, filters={"pesi_compound_name": compound or ""}, sort_by="source_confidence")


@router.get("/pair-food-context")
def pair_food_context(_auth: AuthContext, q: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("pair-food-context", out_dir, limit=limit, offset=offset, query=q, sort_by="shared_source_confidence")


@router.get("/pair-food-evidence")
def pair_food_evidence(_auth: AuthContext, q: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("pair-food-evidence", out_dir, limit=limit, offset=offset, query=q, sort_by="shared_source_confidence")


@router.get("/proxy-evidence")
def proxy_evidence(_auth: AuthContext, q: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("proxy-evidence", out_dir, limit=limit, offset=offset, query=q)


@router.get("/pseudo-lab")
def pseudo_lab(_auth: AuthContext, q: str | None = None, target: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), settings: ApiSettings = Depends(get_settings), out_dir: str | None = None):
    return reader(settings).read_table("pseudo-lab", out_dir, limit=limit, offset=offset, query=q, filters={"target_enzyme": target or ""}, sort_by="predicted_inhibition")
