"""WMT remote jobs components."""

from __future__ import annotations

import datetime
import concurrent.futures
import copy
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import zipfile
from html import escape, unescape
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree as ET
from uuid import uuid4
from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .cache import (
    repair_mojibake,
)
from ..core.config import (
    BACKUP_TEMPORARY_SHARE_TTL_MINUTES,
    MAX_CONCURRENT_REMOTE_JOBS,
)
from .powershell import (
    REMOTE_ACTION_ALIASES,
    REMOTE_JOBS_LOCK,
    _canonical_remote_action,
    execute_remote_action,
)
from ..core.security import (
    utc_now,
)
from ..repositories.state import (
    mutate_state,
)
from .temp_shares import (
    _track_temp_share,
    _untrack_temp_share,
    _utc_after_minutes,
)

REMOTE_JOBS: dict[str, dict] = {}


def remote_job_status_for_ui(status: str) -> str:
    normalized = (status or "").lower()
    if normalized in {"queued", "running", "completed", "failed", "canceled"}:
        return normalized
    return "queued"


def _public_remote_job(job: dict) -> dict:
    return {
        "id": job.get("id", ""),
        "host": job.get("host", ""),
        "action": job.get("action", ""),
        "status": remote_job_status_for_ui(str(job.get("status") or "")),
        "ok": bool(job.get("ok")) if job.get("status") in {"completed", "failed"} else False,
        "message": repair_mojibake(job.get("message", "")),
        "details": repair_mojibake(job.get("details", "")),
        "created_by": job.get("created_by", ""),
        "created_at": job.get("created_at", ""),
        "started_at": job.get("started_at", ""),
        "ended_at": job.get("ended_at", ""),
        "duration_ms": job.get("duration_ms", 0),
        "open_path": job.get("open_path", ""),
    }


def _persist_remote_job(job: dict) -> None:
    public_job = _public_remote_job(job)

    def persist(state: dict) -> None:
        jobs = [
            item
            for item in state.get("remote_jobs", [])
            if item.get("id") != job.get("id")
        ]
        jobs.insert(0, public_job)
        state["remote_jobs"] = jobs[:100]

    mutate_state(persist)


def _set_remote_job(job_id: str, *, persist: bool = True, **fields: object) -> None:
    with REMOTE_JOBS_LOCK:
        job = REMOTE_JOBS.get(job_id)
        if not job:
            return
        job.update(fields)
        snapshot = dict(job)
    if persist:
        _persist_remote_job(snapshot)


def _run_remote_job(job_id: str, host: str, action: str) -> None:
    started = time.perf_counter()
    _set_remote_job(
        job_id,
        persist=False,
        status="running",
        started_at=utc_now(),
        message="Running remote action...",
    )

    ok, message, details = execute_remote_action(host, action, job_id=job_id)
    if ok:
        normalized_action = " ".join(action.strip().lower().replace("_", " ").split())
        normalized_action = REMOTE_ACTION_ALIASES.get(normalized_action, normalized_action)
        if normalized_action == "create-temp-c-share":
            open_path = f"\\\\{host}\\TempC$"
            _track_temp_share(
                host,
                "TempC$",
                "C",
                "C:\\",
                _utc_after_minutes(BACKUP_TEMPORARY_SHARE_TTL_MINUTES),
                "remote_action",
                "WMT_Remove_TempC",
            )
            message = f"{message} Active folder: {open_path}"
            details = "\n".join(item for item in [details, f"Active folder: {open_path}"] if item).strip()
            _set_remote_job(job_id, persist=False, open_path=open_path)
        elif normalized_action == "remove-temp-c-share":
            _untrack_temp_share(host, "TempC$")
    duration_ms = int((time.perf_counter() - started) * 1000)
    with REMOTE_JOBS_LOCK:
        current_status = REMOTE_JOBS.get(job_id, {}).get("status")
    if current_status == "canceled":
        return
    _set_remote_job(
        job_id,
        status="completed" if ok else "failed",
        ok=ok,
        message=message,
        details=details,
        ended_at=utc_now(),
        duration_ms=duration_ms,
    )


def create_remote_job(host: str, action: str, username: str) -> dict:
    canonical_action = _canonical_remote_action(action)
    normalized_host = host.strip().upper()
    job = {
        "id": f"RJ-{secrets.token_hex(4).upper()}",
        "host": normalized_host,
        "action": canonical_action,
        "status": "queued",
        "ok": False,
        "message": "Remote action added to queue.",
        "details": "",
        "created_by": username,
        "created_at": utc_now(),
        "started_at": "",
        "ended_at": "",
        "duration_ms": 0,
        "open_path": f"\\\\{host}\\TempC$" if canonical_action == "create-temp-c-share" else "",
    }

    with REMOTE_JOBS_LOCK:
        if canonical_action == "create-temp-c-share":
            existing = next(
                (
                    current
                    for current in REMOTE_JOBS.values()
                    if str(current.get("host") or "").strip().upper() == normalized_host
                    and current.get("action") == canonical_action
                    and current.get("status") in {"queued", "running"}
                ),
                None,
            )
            if existing:
                return _public_remote_job(existing)
        active_count = sum(
            1
            for current in REMOTE_JOBS.values()
            if current.get("status") in {"queued", "running"}
        )
        if active_count >= MAX_CONCURRENT_REMOTE_JOBS:
            raise RuntimeError(
                f"Limite de {MAX_CONCURRENT_REMOTE_JOBS} ações remotas simultâneas atingido."
            )
        REMOTE_JOBS[job["id"]] = job

    _persist_remote_job(job)
    thread = threading.Thread(target=_run_remote_job, args=(job["id"], normalized_host, canonical_action), daemon=True)
    thread.start()
    return _public_remote_job(job)
