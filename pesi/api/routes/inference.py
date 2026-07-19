from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from pesi.api.auth import AuthContext
from pesi.api.config import ApiSettings, get_settings
from pesi.api.services.inference_adapter import InferenceAdapter
from pesi.api.services.json_safe import to_json_safe

router = APIRouter(prefix="/inference", tags=["inference"])


class AnalysisStartRequest(BaseModel):
    scenario: dict[str, Any] = Field(default_factory=dict)
    analysis_goal: str = "candidate_pairs"
    profile: str = "audit"
    sabio_mode: str = "cache"
    raw_dir: str = "raw"
    out_dir: str | None = None
    artifact_dir: str | None = None
    run_benchmark: bool = True


class ExplainRequest(BaseModel):
    run_id: str | None = None
    row_index: int | None = None
    recommendation_id: str | None = None
    target_id: str | None = None


class InferenceReportRequest(BaseModel):
    run_id: str | None = None
    report_type: str = "summary"
    format: str = "json"
    scenario: dict[str, Any] = Field(default_factory=dict)


def adapter(settings: ApiSettings) -> InferenceAdapter:
    return InferenceAdapter(settings)


@router.get("/options")
def options(_auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    return adapter(settings).options()


@router.post("/analyses")
def start_analysis(request: AnalysisStartRequest, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    return adapter(settings).start_analysis(request.model_dump())


@router.get("/analyses/{run_id}/progress")
def analysis_progress(run_id: str, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    return adapter(settings).progress(run_id)


@router.get("/results")
def inference_results(_auth: AuthContext, run_id: str | None = None, limit: int = Query(40, ge=1, le=200), settings: ApiSettings = Depends(get_settings)):
    return adapter(settings).results(run_id=run_id, limit=limit)


@router.post("/explain/recommendation")
def explain_recommendation(request: ExplainRequest, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    return adapter(settings).explain_recommendation(request.model_dump())


@router.post("/explain/target")
def explain_target(request: ExplainRequest, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    return adapter(settings).explain_target(request.model_dump())


@router.get("/recommendations/{recommendation_id}/evidence-path")
def recommendation_evidence_path(
    recommendation_id: str,
    _auth: AuthContext,
    run_id: str | None = None,
    row_index: int | None = Query(None, ge=0),
    settings: ApiSettings = Depends(get_settings),
):
    return adapter(settings).recommendation_evidence({
        "run_id": run_id,
        "row_index": row_index,
        "recommendation_id": recommendation_id,
    })


@router.get("/targets/{target_id}/state-reasoning")
def target_state_reasoning(
    target_id: str,
    _auth: AuthContext,
    run_id: str | None = None,
    row_index: int | None = Query(None, ge=0),
    settings: ApiSettings = Depends(get_settings),
):
    return adapter(settings).target_state_reasoning({
        "run_id": run_id,
        "row_index": row_index,
        "target_id": target_id,
    })


@router.get("/food-sources/compound")
def compound_food_sources(
    _auth: AuthContext,
    compound: str = Query(..., min_length=1),
    run_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    settings: ApiSettings = Depends(get_settings),
):
    return adapter(settings).compound_food_sources(compound, run_id=run_id, limit=limit)


@router.get("/food-sources/pair")
def pair_food_context(
    _auth: AuthContext,
    compound_a: str = Query(..., min_length=1),
    compound_b: str = Query(..., min_length=1),
    run_id: str | None = None,
    settings: ApiSettings = Depends(get_settings),
):
    return adapter(settings).pair_food_context(compound_a, compound_b, run_id=run_id)


@router.post("/reports")
def report(request: InferenceReportRequest, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    app = adapter(settings)
    payload = request.model_dump()
    if request.format == "html":
        return Response(content=app.build_report_html(payload), media_type="text/html")
    return JSONResponse(content=to_json_safe(app.build_report(payload)))
