from __future__ import annotations

import re
from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi import APIRouter

from ..core.config import API_VERSION, APP_VERSION, SERVICE_NAME, UPDATES_DIR
from ..repositories.state import probe_state_repository

router = APIRouter()


@router.get("/")
def read_root():
    return {"message": "WMT Desktop backend is running"}


@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "api_version": API_VERSION,
        "version": APP_VERSION,
    }


@router.get("/health/live")
def health_live():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "api_version": API_VERSION,
        "version": APP_VERSION,
    }


@router.get("/health/ready")
def health_ready():
    try:
        probe_state_repository()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": SERVICE_NAME,
                "api_version": API_VERSION,
                "version": APP_VERSION,
            },
        )
    return {
        "status": "ready",
        "service": SERVICE_NAME,
        "api_version": API_VERSION,
        "version": APP_VERSION,
    }


@router.get("/api/updates/latest.json")
def latest_update():
    latest_path = UPDATES_DIR / "latest.json"
    if not latest_path.exists():
        raise HTTPException(status_code=404, detail="No update is available")
    return FileResponse(latest_path, media_type="application/json")


@router.get("/api/updates/{filename}")
def update_artifact(filename: str):
    if not re.fullmatch(r"[A-Za-z0-9_. ()@+-]+", filename):
        raise HTTPException(status_code=404, detail="Update artifact not found")

    artifact_path = (UPDATES_DIR / filename).resolve()
    updates_root = UPDATES_DIR.resolve()
    if updates_root not in artifact_path.parents or not artifact_path.is_file():
        raise HTTPException(status_code=404, detail="Update artifact not found")

    media_type = "application/octet-stream"
    if artifact_path.suffix.lower() == ".msi":
        media_type = "application/x-msi"
    elif artifact_path.suffix.lower() == ".json":
        media_type = "application/json"

    return FileResponse(artifact_path, media_type=media_type, filename=artifact_path.name)
