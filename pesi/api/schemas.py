from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RunProfile(str, Enum):
    audit = "audit"
    medium = "medium"
    large = "large"
    full = "full"


class SabioMode(str, Enum):
    offline = "offline"
    cache = "cache"


class ScenarioPayload(BaseModel):
    crop_taxa: list[str] = Field(default_factory=list)
    weed_taxa: list[str] = Field(default_factory=list)
    crop_family: list[str] = Field(default_factory=list)
    weed_family: list[str] = Field(default_factory=list)
    growth_stage: str | None = None
    location: dict[str, Any] | None = None
    visual_identification_source: str | None = None
    confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)


class RunRequest(BaseModel):
    profile: RunProfile = RunProfile.audit
    sabio_mode: SabioMode = SabioMode.cache
    raw_dir: str = "raw"
    out_dir: str = "outputs"
    artifact_dir: str = "artifacts"
    scenario: ScenarioPayload | None = None
    run_benchmark: bool = True

    @field_validator("raw_dir", "out_dir", "artifact_dir")
    @classmethod
    def no_empty_paths(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Path cannot be empty")
        return value


class RunRecord(BaseModel):
    run_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    created_at: datetime
    updated_at: datetime
    request: RunRequest
    return_code: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_dir: str
    artifact_dir: str
    log_path: str
    error: str | None = None


class TableResponse(BaseModel):
    status: Literal["ok", "missing"]
    path: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total_rows: int = 0
    limit: int
    offset: int = 0
    columns: list[str] = Field(default_factory=list)


class InterpretationRequest(BaseModel):
    out_dir: str | None = None
    artifact_dir: str | None = None
    run_id: str | None = None
    target: str | None = None
    target_enzyme: str | None = None
    compound_a: str | None = None
    compound_b: str | None = None
    group_id: str | None = None
    row_index: int | None = Field(default=None, ge=0)


class ReportRequest(BaseModel):
    out_dir: str | None = None
    artifact_dir: str | None = None
    run_id: str | None = None
    format: Literal["json", "html"] = "json"
