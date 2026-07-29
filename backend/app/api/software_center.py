from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi import APIRouter

from ..core.config import HOST_PATTERN
from ..repositories.state import audit
from ..schemas import SoftwareCenterInstallRequest
from ..services.auth import (
    current_user,
    require_role,
)
from ..services.cache import _cache_delete_prefix
from ..services.diagnostics import cached_software_center_status
from ..services.update_jobs import create_update_job

router = APIRouter()


@router.get("/api/software-center")
def software_center_status(host: str = Query(default="localhost"), user: dict = Depends(current_user)):
    target = host.strip() or "localhost"
    if not HOST_PATTERN.match(target):
        raise HTTPException(status_code=400, detail="Host contains unsupported characters")
    return cached_software_center_status(target)


@router.post("/api/software-center/install")
def software_center_install(request: SoftwareCenterInstallRequest, user: dict = Depends(require_role("admin", "operator"))):
    host = request.host.strip() or "localhost"
    if not HOST_PATTERN.match(host):
        raise HTTPException(status_code=400, detail="Host contains unsupported characters")

    _cache_delete_prefix(f"software-center:{host.upper()}:")
    try:
        job = create_update_job(host, user["username"])
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "60"}) from exc
    audit("software_center.install_updates", user["username"], {"host": host, "job_id": job["id"]})
    return {
        "ok": True,
        "job": job,
        "job_id": job["id"],
        "status": job["status"],
        "message": f"Update job {job['id']} criado para {host}.",
    }
