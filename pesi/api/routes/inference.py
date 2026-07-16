from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from pesi.api.auth import AuthContext
from pesi.api.config import ApiSettings, get_settings
from pesi.api.services.inference_adapter import InferenceAdapter

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


@router.post("/reports")
def report(request: InferenceReportRequest, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    app = adapter(settings)
    payload = request.model_dump()
    if request.format == "html":
        return Response(content=app.build_report_html(payload), media_type="text/html")
    return app.build_report(payload)
