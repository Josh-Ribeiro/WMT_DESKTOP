from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi import APIRouter

from ..core.security import utc_now
from ..core.validators import validate_backup_host
from ..repositories.state import audit
from ..schemas import (
    DiagnosticRequest,
    HostRequest,
)
from ..services.auth import (
    current_user,
    require_role,
)
from ..services.cache import _cache_delete_prefix
from ..services.diagnostics import (
    DIAGNOSTIC_JOBS,
    DIAGNOSTIC_JOBS_LOCK,
    _public_diagnostic_job,
    build_wmt_health,
    cached_diagnostic_pack,
    collect_performance_sample,
    create_diagnostic_job,
    run_diagnostic_pack,
)

router = APIRouter()


@router.get("/api/performance-sample")
def performance_sample_endpoint(
    host: str = Query(default="localhost"),
    user: dict = Depends(current_user),
):
    target = (host or "").strip() or "localhost"
    target = validate_backup_host(target)
    return collect_performance_sample(target)


@router.post("/api/diagnostics")
def diagnostics(request: DiagnosticRequest, user: dict = Depends(require_role("admin", "operator"))):
    host = validate_backup_host(request.host)
    payload = cached_diagnostic_pack(host, include_details=request.detailed)
    audit("diagnostics.run", user["username"], {"host": host, "detailed": request.detailed})
    return payload


@router.post("/api/diagnostics/jobs")
def diagnostics_job_create(request: DiagnosticRequest, user: dict = Depends(require_role("admin", "operator"))):
    job = create_diagnostic_job(request.host, request.detailed, user["username"])
    audit("diagnostics.job", user["username"], {"host": job.get("host"), "detailed": request.detailed, "job_id": job.get("id")})
    return job


@router.get("/api/diagnostics/jobs/{job_id}")
def diagnostics_job_get(job_id: str, user: dict = Depends(require_role("admin", "operator"))):
    if job_id.startswith("cache-"):
        raise HTTPException(status_code=404, detail="Cached diagnostic job is not stored")
    with DIAGNOSTIC_JOBS_LOCK:
        job = DIAGNOSTIC_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Diagnostic job not found")
        return _public_diagnostic_job(job)


@router.post("/api/inventory")
def inventory(request: HostRequest, user: dict = Depends(current_user)):
    host = validate_backup_host(request.host)
    payload = cached_diagnostic_pack(host, include_details=True)
    return {
        "host": host,
        "generated_at": payload.get("generated_at") or utc_now(),
        "inventory": payload.get("inventory") or {},
        "checks": payload.get("checks") or [],
        "error": payload.get("error") or "",
    }


@router.post("/api/quick-cleanup")
def quick_cleanup(request: HostRequest, user: dict = Depends(require_role("admin", "operator"))):
    host = validate_backup_host(request.host)
    payload = run_diagnostic_pack(host, run_cleanup=True)
    _cache_delete_prefix(f"diagnostic:{host}:")
    audit("cleanup.quick", user["username"], {"host": host})
    return payload


@router.post("/api/wmt-health")
def wmt_health(request: HostRequest, user: dict = Depends(current_user)):
    host = validate_backup_host(request.host)
    return build_wmt_health(host)
