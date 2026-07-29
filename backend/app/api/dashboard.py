from __future__ import annotations

import datetime
from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi import APIRouter

from ..repositories.state import load_state_fields
from ..services.auth import current_user
from ..services.backup import (
    BACKUP_JOBS,
    BACKUP_JOBS_LOCK,
    backup_status_for_ui,
)
from ..services.powershell import REMOTE_JOBS_LOCK
from ..services.remote_jobs import (
    REMOTE_JOBS,
    _public_remote_job,
)
from ..services.temp_shares import build_temp_shares_payload
from ..services.update_jobs import (
    UPDATE_JOBS,
    UPDATE_JOBS_LOCK,
    _public_update_job,
)

router = APIRouter()


def _daily_operation_metrics(collections: list[list[dict]], days: int = 7) -> list[dict]:
    today = datetime.datetime.utcnow().date()
    result = []
    for offset in range(days - 1, -1, -1):
        day = today - datetime.timedelta(days=offset)
        completed = failed = total = 0
        for collection in collections:
            for item in collection:
                raw_date = item.get("ended_at") or item.get("end_time") or item.get("created_at") or item.get("start_time")
                parsed = _parse_dashboard_date(raw_date)
                if not parsed or parsed.date() != day:
                    continue
                total += 1
                status = str(item.get("status") or "")
                completed += status == "completed"
                failed += status == "failed"
        result.append({
            "date": day.isoformat(),
            "label": day.strftime("%d/%m"),
            "total": total,
            "completed": completed,
            "failed": failed,
        })
    return result


def _parse_dashboard_date(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


@router.get("/api/dashboard")
def dashboard(user: dict = Depends(current_user)):
    state = load_state_fields(
        "backup_jobs",
        "remote_jobs",
        "update_jobs",
        "audit",
        "users",
        "temp_shares",
    )
    can_view_backup = "backup" in user.get("permissions", [])
    with BACKUP_JOBS_LOCK:
        runtime_jobs = list(BACKUP_JOBS.values())
    with REMOTE_JOBS_LOCK:
        runtime_remote_jobs = list(REMOTE_JOBS.values())
    with UPDATE_JOBS_LOCK:
        runtime_update_jobs = list(UPDATE_JOBS.values())

    persisted_jobs = state.get("backup_jobs", [])
    jobs_by_id = {job.get("id"): job for job in persisted_jobs}
    for job in runtime_jobs:
        jobs_by_id[job.get("id")] = job
    jobs = sorted(
        jobs_by_id.values(),
        key=lambda item: item.get("start_time") or item.get("end_time") or "",
        reverse=True,
    )
    if not can_view_backup:
        jobs = []

    today = datetime.datetime.utcnow().date()

    def is_today(value: str | None) -> bool:
        parsed = _parse_dashboard_date(value)
        return bool(parsed and parsed.date() == today)

    running = sum(1 for job in jobs if job.get("status") == "running")
    completed = sum(1 for job in jobs if job.get("status") == "completed")
    failed = sum(1 for job in jobs if job.get("status") == "failed")
    canceled = sum(1 for job in jobs if job.get("status") == "canceled")
    finished_today = sum(1 for job in jobs if is_today(job.get("end_time") or job.get("start_time")))
    terms_today = sum(
        1
        for item in state.get("audit", [])
        if item.get("action") in {"terms.generate", "terms.print"} and is_today(item.get("timestamp"))
    )
    active_users = sum(1 for item in state.get("users", []) if item.get("status") == "active")

    audit_items = state.get("audit", [])
    if not can_view_backup:
        audit_items = [item for item in audit_items if not str(item.get("action") or "").startswith("backup.")]

    recent = [
        {
            "id": item["id"],
            "action": item["action"],
            "username": item.get("username", ""),
            "details": item.get("details", {}),
            "timestamp": item["timestamp"],
        }
        for item in audit_items[:8]
    ]

    recent_jobs = [
        {
            "id": job.get("id", ""),
            "source": job.get("source", ""),
            "destination": job.get("destination", ""),
            "users": len(job.get("users") or []),
            "status": backup_status_for_ui(str(job.get("status") or "")),
            "progress": job.get("progress", 0),
            "start_time": job.get("start_time", ""),
            "end_time": job.get("end_time", ""),
            "summary": job.get("summary") or job.get("message") or "",
        }
        for job in jobs[:5]
    ]
    persisted_remote_jobs = state.get("remote_jobs", [])
    remote_jobs_by_id = {job.get("id"): job for job in persisted_remote_jobs}
    for job in runtime_remote_jobs:
        remote_jobs_by_id[job.get("id")] = job
    remote_jobs = sorted(
        [_public_remote_job(job) for job in remote_jobs_by_id.values()],
        key=lambda item: item.get("created_at") or item.get("started_at") or item.get("ended_at") or "",
        reverse=True,
    )
    active_remote = sum(1 for job in remote_jobs if job.get("status") in {"queued", "running"})
    failed_remote = sum(1 for job in remote_jobs if job.get("status") == "failed")
    completed_remote = sum(1 for job in remote_jobs if job.get("status") == "completed")
    persisted_update_jobs = state.get("update_jobs", [])
    update_jobs_by_id = {job.get("id"): job for job in persisted_update_jobs}
    for job in runtime_update_jobs:
        update_jobs_by_id[job.get("id")] = job
    update_jobs = sorted(
        [_public_update_job(job) for job in update_jobs_by_id.values()],
        key=lambda item: item.get("created_at") or item.get("started_at") or item.get("ended_at") or "",
        reverse=True,
    )
    active_updates = sum(1 for job in update_jobs if job.get("status") in {"queued", "running"})
    failed_updates = sum(1 for job in update_jobs if job.get("status") == "failed")
    completed_updates = sum(1 for job in update_jobs if job.get("status") == "completed")

    return {
        "total_workstations": len({job.get("source") for job in jobs if job.get("source")} | {job.get("destination") for job in jobs if job.get("destination")}),
        "online": 0,
        "offline": 0,
        "with_updates": 0,
        "critical_alerts": failed,
        "backup_summary": {
            "total": len(jobs),
            "running": running,
            "completed": completed,
            "failed": failed,
            "canceled": canceled,
            "finished_today": finished_today,
        },
        "terms_today": terms_today,
        "active_users": active_users,
        "kpis": [
            {"label": "Workstations touched", "value": len({job.get("source") for job in jobs if job.get("source")} | {job.get("destination") for job in jobs if job.get("destination")})},
            {"label": "Running backups", "value": running},
            {"label": "Backups today", "value": finished_today},
            {"label": "Terms today", "value": terms_today},
            {"label": "Active users", "value": active_users},
        ],
        "recent_activities": recent,
        "recent_jobs": recent_jobs,
        "remote_summary": {
            "total": len(remote_jobs),
            "active": active_remote,
            "completed": completed_remote,
            "failed": failed_remote,
        },
        "recent_remote_jobs": remote_jobs[:6],
        "update_summary": {
            "total": len(update_jobs),
            "active": active_updates,
            "completed": completed_updates,
            "failed": failed_updates,
        },
        "recent_update_jobs": update_jobs[:6],
        "trends": {
            "days": _daily_operation_metrics([jobs, remote_jobs, update_jobs]),
        },
        "temp_shares": build_temp_shares_payload(state, verify_live=False),
    }


@router.get("/api/operational-jobs")
def operational_jobs(user: dict = Depends(current_user)):
    state = load_state_fields("backup_jobs", "remote_jobs", "update_jobs", "temp_shares")
    can_view_backup = "backup" in user.get("permissions", [])

    if can_view_backup:
        with BACKUP_JOBS_LOCK:
            runtime_backup_jobs = list(BACKUP_JOBS.values())
        backup_jobs_by_id = {job.get("id"): job for job in state.get("backup_jobs", [])}
        for job in runtime_backup_jobs:
            backup_jobs_by_id[job.get("id")] = job
        backup_jobs = sorted(
            backup_jobs_by_id.values(),
            key=lambda item: item.get("start_time") or item.get("end_time") or "",
            reverse=True,
        )
        recent_jobs = [
            {
                "id": job.get("id", ""),
                "source": job.get("source", ""),
                "destination": job.get("destination", ""),
                "status": backup_status_for_ui(str(job.get("status") or "")),
                "summary": job.get("summary") or job.get("message") or "",
            }
            for job in backup_jobs[:5]
        ]
    else:
        recent_jobs = []

    with REMOTE_JOBS_LOCK:
        runtime_remote_jobs = [_public_remote_job(job) for job in REMOTE_JOBS.values()]
    remote_jobs_by_id = {job.get("id"): job for job in state.get("remote_jobs", [])}
    for job in runtime_remote_jobs:
        remote_jobs_by_id[job.get("id")] = job
    remote_jobs = sorted(
        [_public_remote_job(job) for job in remote_jobs_by_id.values()],
        key=lambda item: item.get("created_at") or item.get("started_at") or item.get("ended_at") or "",
        reverse=True,
    )

    with UPDATE_JOBS_LOCK:
        runtime_update_jobs = [_public_update_job(job) for job in UPDATE_JOBS.values()]
    update_jobs_by_id = {job.get("id"): job for job in state.get("update_jobs", [])}
    for job in runtime_update_jobs:
        update_jobs_by_id[job.get("id")] = job
    update_jobs = sorted(
        [_public_update_job(job) for job in update_jobs_by_id.values()],
        key=lambda item: item.get("created_at") or item.get("started_at") or item.get("ended_at") or "",
        reverse=True,
    )

    return {
        "recent_jobs": recent_jobs,
        "recent_remote_jobs": remote_jobs[:6],
        "recent_update_jobs": update_jobs[:6],
    }
