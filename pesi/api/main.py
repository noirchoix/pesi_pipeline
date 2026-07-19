from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pesi.api.config import get_settings
from pesi.api.routes import benchmarks, inference, interpretation, results, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.safe_path(settings.job_dir).mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "PESI-KG API for plant enzyme-state KG outputs, run orchestration, "
            "benchmark gates, intervention results, and artifact-grounded scientific interpretation."
        ),
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )
    app.include_router(runs.router, prefix=settings.api_prefix)
    app.include_router(results.router, prefix=settings.api_prefix)
    app.include_router(benchmarks.router, prefix=settings.api_prefix)
    app.include_router(interpretation.router, prefix=settings.api_prefix)
    app.include_router(inference.router, prefix=settings.api_prefix)

    @app.get("/health")
    def health() -> dict[str, Any]:
        from pesi.api.services.llm_client import DeepSeekClient
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
            "auth_mode": settings.auth_mode,
            "ai": DeepSeekClient(settings).configuration_status(),
        }

    @app.get(f"{settings.api_prefix}/health")
    def api_health() -> dict[str, Any]:
        return health()

    @app.exception_handler(ValueError)
    async def value_error_handler(_request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app


app = create_app()
