from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from pesi.api.auth import AuthContext
from pesi.api.config import ApiSettings, get_settings
from pesi.api.schemas import InterpretationRequest, ReportRequest
from pesi.api.services.interpretation_service import InterpretationService
from pesi.api.services.report_builder import ReportBuilder

router = APIRouter(tags=["interpretation", "reports"])


@router.post("/interpret/run")
def interpret_run(request: InterpretationRequest, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    return InterpretationService(settings).interpret_run(out_dir=request.out_dir, artifact_dir=request.artifact_dir)


@router.post("/interpret/intervention")
def interpret_intervention(request: InterpretationRequest, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    return InterpretationService(settings).interpret_intervention(request, out_dir=request.out_dir)


@router.post("/interpret/target")
def interpret_target(request: InterpretationRequest, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    return InterpretationService(settings).interpret_target(target=request.target or request.target_enzyme, row_index=request.row_index, out_dir=request.out_dir)


@router.post("/interpret/synergy-group")
def interpret_synergy_group(request: InterpretationRequest, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    return InterpretationService(settings).interpret_synergy_group(group_id=request.group_id, out_dir=request.out_dir)


@router.post("/reports")
def build_report(request: ReportRequest, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    builder = ReportBuilder(settings)
    if request.format == "html":
        html = builder.build_html_report(request.out_dir, request.artifact_dir)
        return Response(content=html, media_type="text/html")
    return builder.build_json_report(request.out_dir, request.artifact_dir)


@router.get("/reports/{report_id}.html")
def report_html(report_id: str, _auth: AuthContext, out_dir: str | None = None, artifact_dir: str | None = None, settings: ApiSettings = Depends(get_settings)):
    html = ReportBuilder(settings).build_html_report(out_dir, artifact_dir)
    return Response(content=html, media_type="text/html")
