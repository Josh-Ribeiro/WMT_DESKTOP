"""WMT update jobs components."""

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

from .powershell import (
    run_software_center_script,
)
from ..core.config import MAX_CONCURRENT_UPDATE_JOBS
from ..core.security import (
    utc_now,
)
from ..repositories.state import (
    current_settings,
    mutate_state,
)

UPDATE_JOBS_LOCK = threading.Lock()


UPDATE_JOBS: dict[str, dict] = {}


def update_job_status_for_ui(status: str) -> str:
    normalized = (status or "").lower()
    if normalized in {"queued", "running", "completed", "failed", "canceled"}:
        return normalized
    return "queued"


def _public_update_job(job: dict) -> dict:
    return {
        "id": job.get("id", ""),
        "host": job.get("host", ""),
        "status": update_job_status_for_ui(str(job.get("status") or "")),
        "ok": bool(job.get("ok")) if job.get("status") in {"completed", "failed"} else False,
        "message": job.get("message", ""),
        "details": job.get("details", ""),
        "created_by": job.get("created_by", ""),
        "created_at": job.get("created_at", ""),
        "started_at": job.get("started_at", ""),
        "ended_at": job.get("ended_at", ""),
        "duration_ms": job.get("duration_ms", 0),
        "progress": int(job.get("progress") or 0),
        "pending_updates": int(job.get("pending_updates") or 0),
        "updates": job.get("updates") or [],
    }


def _persist_update_job(job: dict) -> None:
    public_job = _public_update_job(job)

    def persist(state: dict) -> None:
        jobs = [
            item
            for item in state.get("update_jobs", [])
            if item.get("id") != job.get("id")
        ]
        jobs.insert(0, public_job)
        state["update_jobs"] = jobs[:100]

    mutate_state(persist)


def _set_update_job(job_id: str, **fields: object) -> None:
    with UPDATE_JOBS_LOCK:
        job = UPDATE_JOBS.get(job_id)
        if not job:
            return
        job.update(fields)
        snapshot = dict(job)
    _persist_update_job(snapshot)


def _progress_from_updates(updates: list[dict]) -> int:
    values = [
        int(item.get("percentComplete") or item.get("percent_complete") or 0)
        for item in updates
        if isinstance(item, dict)
    ]
    if not values:
        return 0
    return max(0, min(99, int(sum(values) / len(values))))


def _run_update_job(job_id: str, host: str) -> None:
    started = time.perf_counter()
    settings = current_settings()
    poll_interval = int(settings.get("software_center_poll_interval_seconds") or 10)
    timeout_seconds = int(settings.get("update_job_timeout_minutes") or 120) * 60

    _set_update_job(job_id, status="running", started_at=utc_now(), message="Iniciando updates pelo Software Center...")
    install_result = run_software_center_script(host, "install-updates")
    if install_result.get("ok") is False:
        _set_update_job(
            job_id,
            status="failed",
            ok=False,
            message=install_result.get("message") or "Falha ao iniciar updates.",
            details=install_result.get("details", ""),
            ended_at=utc_now(),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return

    _set_update_job(
        job_id,
        message=install_result.get("message") or "Installation started. Monitoring progress...",
        pending_updates=int(install_result.get("pendingUpdates") or 0),
    )

    while True:
        elapsed = time.perf_counter() - started
        if elapsed > timeout_seconds:
            _set_update_job(
                job_id,
                status="failed",
                ok=False,
                message=f"Tempo limite excedido monitorando updates em {host}.",
                ended_at=utc_now(),
                duration_ms=int(elapsed * 1000),
            )
            return

        time.sleep(max(5, poll_interval))
        status_result = run_software_center_script(host, "status")
        if status_result.get("ok") is False:
            _set_update_job(
                job_id,
                status="failed",
                ok=False,
                message=status_result.get("message") or "Falha ao monitorar updates.",
                details=status_result.get("details", ""),
                ended_at=utc_now(),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return

        pending = int(status_result.get("pendingUpdates") or 0)
        updates = status_result.get("updates") or []
        progress = 100 if pending == 0 else _progress_from_updates(updates)
        _set_update_job(
            job_id,
            status="running",
            message=f"Monitorando updates em {host}: {pending} pendente(s).",
            pending_updates=pending,
            updates=updates,
            progress=progress,
        )

        if pending == 0:
            _set_update_job(
                job_id,
                status="completed",
                ok=True,
                message="Updates completed or no pending updates in Software Center.",
                progress=100,
                pending_updates=0,
                updates=[],
                ended_at=utc_now(),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return


def create_update_job(host: str, username: str) -> dict:
    job = {
        "id": f"UP-{secrets.token_hex(4).upper()}",
        "host": host,
        "status": "queued",
        "ok": False,
        "message": "Update adicionado à fila.",
        "details": "",
        "created_by": username,
        "created_at": utc_now(),
        "started_at": "",
        "ended_at": "",
        "duration_ms": 0,
        "progress": 0,
        "pending_updates": 0,
        "updates": [],
    }
    with UPDATE_JOBS_LOCK:
        active_count = sum(
            1
            for current in UPDATE_JOBS.values()
            if current.get("status") in {"queued", "running"}
        )
        if active_count >= MAX_CONCURRENT_UPDATE_JOBS:
            raise RuntimeError(
                f"Limite de {MAX_CONCURRENT_UPDATE_JOBS} jobs de atualização simultâneos atingido."
            )
        UPDATE_JOBS[job["id"]] = job
    _persist_update_job(job)
    thread = threading.Thread(target=_run_update_job, args=(job["id"], host), daemon=True)
    thread.start()
    return _public_update_job(job)
