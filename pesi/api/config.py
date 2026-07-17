from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ApiSettings(BaseModel):
    app_name: str = "PESI-KG Research Console API"
    app_version: str = "0.5.0"
    api_prefix: str = "/api/v1"
    project_root: Path = Field(default_factory=lambda: Path.cwd())
    default_raw_dir: str = "raw"
    default_out_dir: str = "outputs_medium"
    default_artifact_dir: str = "artifacts_medium"
    fallback_out_dir: str = "outputs"
    fallback_artifact_dir: str = "artifacts"
    allowed_profiles: tuple[str, ...] = ("audit", "medium", "large", "full")
    allowed_sabio_modes: tuple[str, ...] = ("offline", "cache")
    api_key: str | None = None
    auth_mode: Literal["optional", "required"] = "optional"
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ])
    job_dir: Path = Path(".pesi_runs")
    max_table_rows: int = 1000
    default_table_rows: int = 100
    ai_enabled: bool = False
    ai_provider: str = "deepseek"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout_seconds: int = 45
    food_chemistry_dir: str = "raw/food_chemistry"
    food_source_top_n: int = 30

    def safe_path(self, value: str | Path) -> Path:
        raw = Path(value)
        if raw.is_absolute():
            path = raw.resolve()
        else:
            path = (self.project_root / raw).resolve()
        root = self.project_root.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Path escapes project root: {value}") from exc
        return path

    def resolve_out_dir(self, value: str | Path | None = None) -> Path:
        candidate = self.safe_path(value or self.default_out_dir)
        if candidate.exists():
            return candidate
        fallback = self.safe_path(self.fallback_out_dir)
        return fallback if fallback.exists() else candidate

    def resolve_artifact_dir(self, value: str | Path | None = None) -> Path:
        candidate = self.safe_path(value or self.default_artifact_dir)
        if candidate.exists():
            return candidate
        fallback = self.safe_path(self.fallback_artifact_dir)
        return fallback if fallback.exists() else candidate


@lru_cache(maxsize=1)
def get_settings() -> ApiSettings:
    origins = os.getenv("PESI_CORS_ORIGINS", "").strip()
    cors = [x.strip() for x in origins.split(",") if x.strip()] or None
    api_key = os.getenv("PESI_API_KEY", "").strip() or None
    auth_mode = os.getenv("PESI_AUTH_MODE", "required" if api_key else "optional").strip().lower()
    return ApiSettings(
        app_name=os.getenv("PESI_API_APP_NAME", "PESI-KG Research Console API"),
        app_version=os.getenv("PESI_API_VERSION", "0.5.0"),
        project_root=Path(os.getenv("PESI_PROJECT_ROOT", ".")).resolve(),
        default_raw_dir=os.getenv("PESI_RAW_DIR", "raw"),
        default_out_dir=os.getenv("PESI_OUT_DIR", "outputs_medium"),
        default_artifact_dir=os.getenv("PESI_ARTIFACT_DIR", "artifacts_medium"),
        fallback_out_dir=os.getenv("PESI_FALLBACK_OUT_DIR", "outputs"),
        fallback_artifact_dir=os.getenv("PESI_FALLBACK_ARTIFACT_DIR", "artifacts"),
        api_key=api_key,
        auth_mode="required" if auth_mode == "required" else "optional",
        cors_origins=cors or ApiSettings().cors_origins,
        job_dir=Path(os.getenv("PESI_JOB_DIR", ".pesi_runs")),
        max_table_rows=int(os.getenv("PESI_MAX_TABLE_ROWS", "1000")),
        default_table_rows=int(os.getenv("PESI_DEFAULT_TABLE_ROWS", "100")),
        ai_enabled=os.getenv("PESI_AI_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"},
        ai_provider=os.getenv("PESI_AI_PROVIDER", "deepseek"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip() or None,
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        deepseek_timeout_seconds=int(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "45")),
        food_chemistry_dir=os.getenv("PESI_FOOD_CHEMISTRY_DIR", "raw/food_chemistry"),
        food_source_top_n=max(1, min(200, int(os.getenv("PESI_FOOD_SOURCE_TOP_N", "30")))),
    )
