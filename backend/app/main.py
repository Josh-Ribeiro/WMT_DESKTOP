from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware

from .api import (
    auth,
    backup,
    dashboard,
    diagnostics,
    directory,
    documents,
    remote_operations,
    settings,
    software_center,
    system,
    update_jobs,
    users,
)
from .core.config import cors_origins
from .repositories.state import StateConflictError, reconcile_interrupted_update_jobs

logger = logging.getLogger("wmt.request")


def create_app() -> FastAPI:
    app = FastAPI(title="WMT Desktop Backend")

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex[:16]
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "request_failed method=%s path=%s request_id=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                request_id,
                elapsed_ms,
            )
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request method=%s path=%s status=%s request_id=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            elapsed_ms,
        )
        return response

    @app.exception_handler(StateConflictError)
    async def state_conflict_handler(
        _request: Request,
        exception: StateConflictError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exception)})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "DELETE"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token"],
        expose_headers=["Content-Disposition", "X-Missing-Placeholders"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    app.router.add_event_handler("startup", reconcile_interrupted_update_jobs)

    routers = (
        diagnostics.router,
        system.router,
        auth.router,
        settings.router,
        dashboard.router,
        directory.router,
        documents.router,
        software_center.router,
        update_jobs.router,
        backup.router,
        users.router,
        remote_operations.router,
    )
    for router in routers:
        app.include_router(router)
    return app


app = create_app()
