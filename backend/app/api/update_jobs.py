from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi import APIRouter

from ..repositories.state import load_state
from ..services.auth import current_user
from ..services.update_jobs import (
    UPDATE_JOBS,
    UPDATE_JOBS_LOCK,
    _public_update_job,
)

router = APIRouter()


@router.get("/api/update-jobs")
def list_update_jobs(
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(current_user),
):
    state = load_state()
    persisted_jobs = state.get("update_jobs", [])
    with UPDATE_JOBS_LOCK:
        runtime_jobs = [_public_update_job(job) for job in UPDATE_JOBS.values()]
    jobs_by_id = {job.get("id"): job for job in persisted_jobs}
    for job in runtime_jobs:
        jobs_by_id[job.get("id")] = job
    jobs = sorted(
        jobs_by_id.values(),
        key=lambda item: item.get("created_at") or item.get("started_at") or item.get("ended_at") or "",
        reverse=True,
    )
    start = (page - 1) * page_size
    return {
        "jobs": jobs[start : start + page_size],
        "total": len(jobs),
        "page": page,
        "page_size": page_size,
        "has_next": start + page_size < len(jobs),
        "active": sum(1 for job in jobs if job.get("status") in {"queued", "running"}),
        "failed": sum(1 for job in jobs if job.get("status") == "failed"),
        "completed": sum(1 for job in jobs if job.get("status") == "completed"),
    }


@router.get("/api/update-jobs/{job_id}")
def get_update_job(job_id: str, user: dict = Depends(current_user)):
    with UPDATE_JOBS_LOCK:
        runtime = UPDATE_JOBS.get(job_id)
        if runtime:
            return _public_update_job(runtime)
    state = load_state()
    job = next((item for item in state.get("update_jobs", []) if item.get("id") == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Update job not found")
    return job
