from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from pesi.api.auth import AuthContext
from pesi.api.config import ApiSettings, get_settings
from pesi.api.schemas import RunRequest
from pesi.api.services.artifact_reader import ArtifactReader
from pesi.api.services.job_runner import get_job_runner, get_job_store

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def launch_run(request: RunRequest, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    runner = get_job_runner(settings)
    record = runner.launch(request)
    return record.model_dump(mode="json")


@router.get("")
def list_runs(_auth: AuthContext, limit: int = Query(25, ge=1, le=100), settings: ApiSettings = Depends(get_settings)):
    store = get_job_store(settings)
    return {"status": "ok", "runs": [r.model_dump(mode="json") for r in store.list(limit=limit)]}


@router.get("/{run_id}")
def get_run(run_id: str, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    store = get_job_store(settings)
    record = store.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    return record.model_dump(mode="json")


@router.get("/{run_id}/logs")
def get_run_logs(run_id: str, _auth: AuthContext, tail: int = Query(400, ge=1, le=5000), settings: ApiSettings = Depends(get_settings)):
    store = get_job_store(settings)
    if not store.get(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return store.read_log(run_id, tail=tail)


@router.get("/{run_id}/artifacts")
def get_run_artifacts(run_id: str, _auth: AuthContext, settings: ApiSettings = Depends(get_settings)):
    store = get_job_store(settings)
    record = store.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    reader = ArtifactReader(settings)
    return reader.list_artifacts(record.output_dir, record.artifact_dir)
