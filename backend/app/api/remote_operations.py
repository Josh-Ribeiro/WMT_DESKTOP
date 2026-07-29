from __future__ import annotations

import datetime
from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi import APIRouter

from ..core.config import BACKUP_TEMPORARY_SHARE_TTL_MINUTES
from ..core.security import utc_now
from ..repositories.state import (
    audit,
    list_audit_entries,
    load_state,
    load_state_fields,
    mutate_state,
)
from ..schemas import (
    MaintenanceModeRequest,
    RemoteActionRequest,
    RemoteActionResponse,
)
from ..services.auth import (
    current_user,
    require_role,
)
from ..services.backup import run_temporary_share_action
from ..services.powershell import (
    REMOTE_JOBS_LOCK,
    REMOTE_JOB_PROCESSES,
    execute_remote_action,
)
from ..services.remote_jobs import (
    REMOTE_JOBS,
    _public_remote_job,
    create_remote_job,
)
from ..services.remote_operations import (
    run_maintenance_mode,
    validate_remote_action_request,
)
from ..services.maintenance import (
    build_maintenance_modes_payload,
    track_maintenance_mode,
    untrack_maintenance_mode,
)
from ..services.temp_shares import (
    _normalize_history_host,
    _temp_share_drive_from_name,
    _untrack_temp_share,
    build_temp_shares_payload,
)

router = APIRouter()


@router.get("/api/remote-jobs")
def list_remote_jobs(
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(current_user),
):
    state = load_state_fields("remote_jobs", "temp_shares", "maintenance_modes")
    persisted_jobs = state.get("remote_jobs", [])
    with REMOTE_JOBS_LOCK:
        runtime_jobs = [_public_remote_job(job) for job in REMOTE_JOBS.values()]

    jobs_by_id = {job.get("id"): job for job in persisted_jobs}
    for job in runtime_jobs:
        jobs_by_id[job.get("id")] = job

    jobs = sorted(
        jobs_by_id.values(),
        key=lambda item: item.get("created_at") or item.get("started_at") or "",
        reverse=True,
    )
    public_jobs = [_public_remote_job(job) for job in jobs]
    running = sum(1 for job in public_jobs if job.get("status") in {"queued", "running"})
    failed = sum(1 for job in public_jobs if job.get("status") == "failed")
    completed = sum(1 for job in public_jobs if job.get("status") == "completed")
    start = (page - 1) * page_size
    return {
        "jobs": public_jobs[start : start + page_size],
        "total": len(public_jobs),
        "page": page,
        "page_size": page_size,
        "has_next": start + page_size < len(public_jobs),
        "running": running,
        "failed": failed,
        "completed": completed,
        "temp_shares": build_temp_shares_payload(state, verify_live=False),
        "maintenance_modes": build_maintenance_modes_payload(
            state,
            list_audit_entries(action_prefix="maintenance."),
        ),
    }


@router.get("/api/temp-shares")
def list_temp_shares(user: dict = Depends(require_role("admin", "operator"))):
    return build_temp_shares_payload()


@router.delete("/api/temp-shares/{host}/{share_name}")
def remove_temp_share(host: str, share_name: str, user: dict = Depends(require_role("admin", "operator"))):
    normalized_host = _normalize_history_host(host)
    decoded_share_name = share_name.strip()
    drive = _temp_share_drive_from_name(decoded_share_name)
    try:
        if decoded_share_name.lower() == "tempc$":
            ok, message, details = execute_remote_action(normalized_host, "remove-temp-c-share")
            if not ok:
                raise RuntimeError(details or message)
        else:
            run_temporary_share_action(normalized_host, "remove", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, drive)
            message = f"Temporary share {decoded_share_name} removed from {normalized_host}."
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao remover share temporaria {decoded_share_name} em {normalized_host}: {exc}")

    _untrack_temp_share(normalized_host, decoded_share_name)
    audit("temp_share.remove", user["username"], {"host": normalized_host, "share": decoded_share_name, "drive": drive})
    return {"ok": True, "message": message}


@router.get("/api/remote-jobs/{job_id}")
def get_remote_job(job_id: str, user: dict = Depends(current_user)):
    with REMOTE_JOBS_LOCK:
        runtime = REMOTE_JOBS.get(job_id)
        if runtime:
            return _public_remote_job(runtime)

    state = load_state()
    job = next((item for item in state.get("remote_jobs", []) if item.get("id") == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Remote job not found")
    return _public_remote_job(job)


@router.post("/api/remote-jobs/{job_id}/cancel")
def cancel_remote_job(job_id: str, user: dict = Depends(require_role("admin", "operator"))):
    ended_at = utc_now()
    duration_ms = 0
    with REMOTE_JOBS_LOCK:
        process = REMOTE_JOB_PROCESSES.pop(job_id, None)
        job = REMOTE_JOBS.get(job_id)
        if process and process.poll() is None:
            process.kill()
        if job:
            try:
                started = datetime.datetime.fromisoformat(str(job.get("started_at", "")).replace("Z", ""))
                duration_ms = int((datetime.datetime.utcnow() - started).total_seconds() * 1000)
            except Exception:
                duration_ms = int(job.get("duration_ms") or 0)
            job.update(
                {
                    "status": "canceled",
                    "ok": False,
                    "message": "Remote action canceled by user.",
                    "details": str(job.get("details") or ""),
                    "ended_at": ended_at,
                    "duration_ms": duration_ms,
                }
            )
            snapshot = dict(job)
        else:
            snapshot = {}

    def persist_cancellation(state: dict) -> dict:
        jobs = state.get("remote_jobs", [])
        persisted = next(
            (item for item in jobs if item.get("id") == job_id),
            None,
        )
        persisted_snapshot = snapshot
        if not persisted_snapshot and not persisted:
            raise HTTPException(status_code=404, detail="Remote job not found")
        if not persisted_snapshot and persisted:
            persisted.update(
                {
                    "status": "canceled",
                    "ok": False,
                    "message": "Remote action canceled by user.",
                    "ended_at": ended_at,
                }
            )
            persisted_snapshot = persisted
        jobs = [item for item in jobs if item.get("id") != job_id]
        public_snapshot = _public_remote_job(persisted_snapshot)
        jobs.insert(0, public_snapshot)
        state["remote_jobs"] = jobs[:100]
        return public_snapshot

    persisted_snapshot = mutate_state(persist_cancellation)
    audit("remote.job.cancel", user["username"], {"job_id": job_id})
    return persisted_snapshot


@router.post("/api/remote-jobs")
def start_remote_job(request: RemoteActionRequest, user: dict = Depends(require_role("admin", "operator"))):
    host, action = validate_remote_action_request(request, user)
    try:
        job = create_remote_job(host, action, user["username"])
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "30"}) from exc
    audit("remote.job.create", user["username"], {"job_id": job["id"], "host": host, "action": action})
    return job


@router.post("/api/remote-actions", response_model=RemoteActionResponse)
def remote_actions(request: RemoteActionRequest, user: dict = Depends(require_role("admin", "operator"))):
    host, action = validate_remote_action_request(request, user)
    try:
        job = create_remote_job(host, action, user["username"])
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "30"}) from exc

    audit("remote.action", user["username"], {"job_id": job["id"], "host": host, "action": action, "status": job["status"]})
    return {
        "ok": True,
        "job_id": job["id"],
        "status": job["status"],
        "action": action,
        "host": host,
        "message": f"Remote action '{action}' sent for execution on {host}.",
        "details": "",
        "open_path": job.get("open_path") or "",
        "timestamp": job["created_at"],
    }


@router.get("/api/maintenance-mode")
def maintenance_mode_status(host: str = Query(...), user: dict = Depends(current_user)):
    return run_maintenance_mode(host, "status")


@router.post("/api/maintenance-mode")
def change_maintenance_mode(request: MaintenanceModeRequest, user: dict = Depends(require_role("admin", "operator"))):
    technician = str(user.get("display_name") or user.get("username") or "Equipe de TI")
    technician_username = str(user.get("username") or "")
    contact = request.contact.strip() or "Service Desk"
    ticket = request.ticket.strip()
    reason = request.reason.strip()
    if request.action == "enable" and not ticket:
        raise HTTPException(status_code=400, detail="Informe o chamado da manutenção")
    if request.action == "enable" and not reason:
        raise HTTPException(status_code=400, detail="Informe o motivo da manutenção")
    payload = run_maintenance_mode(
        request.host,
        request.action,
        technician,
        technician_username,
        contact,
        ticket,
        reason,
        request.duration_minutes,
        request.target_user.strip(),
    )
    if request.action == "enable":
        track_maintenance_mode(
            payload,
            opened_by=technician_username,
            technician=technician,
            contact=contact,
            ticket=ticket,
            reason=reason,
            duration_minutes=request.duration_minutes,
        )
    elif request.action == "disable":
        untrack_maintenance_mode(payload["host"])
    audit(
        f"maintenance.{request.action}",
        user["username"],
        {
            "host": payload["host"],
            "technician": technician,
            "contact": contact,
            "ticket": ticket,
            "reason": reason,
            "duration_minutes": request.duration_minutes,
            "protected_users": payload.get("protected_users", []),
            "target_user": request.target_user.strip(),
        },
    )
    return payload
