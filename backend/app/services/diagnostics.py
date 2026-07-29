"""WMT diagnostics components."""

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
    _cache_for,
    _cache_get,
    _cache_set,
)
from ..core.config import (
    SCRIPT_DIR,
    UPDATES_DIR,
)
from .powershell import (
    powershell_executable,
    run_powershell_script,
    run_software_center_script,
)
from ..core.security import (
    friendly_error_message,
    utc_now,
)
from ..repositories.state import (
    script_enabled,
)
from ..core.validators import (
    validate_backup_host,
)

DIAGNOSTIC_JOBS_LOCK = threading.Lock()


DIAGNOSTIC_JOBS: dict[str, dict] = {}


DIAGNOSTIC_JOB_SEMAPHORE = threading.Semaphore(3)


def run_diagnostic_pack(host: str, run_cleanup: bool = False, include_details: bool = False) -> dict:
    executable = powershell_executable()
    if executable is None:
        raise RuntimeError("PowerShell nao encontrado neste ambiente.")
    script_path = SCRIPT_DIR / "diagnostic_pack.ps1"
    if not script_path.exists():
        raise RuntimeError(f"Script nao encontrado: {script_path}")

    command = [
        executable,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-HostName",
        host,
    ]
    if run_cleanup:
        command.append("-RunCleanup")
    if include_details:
        command.append("-IncludeDetails")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    payload_text = (result.stdout or "").strip()
    try:
        payload = json.loads(payload_text or "{}")
    except json.JSONDecodeError:
        payload = {"host": host, "checks": [], "inventory": {}, "error": payload_text or (result.stderr or "").strip()}
    if result.returncode != 0 and not payload.get("error"):
        payload["error"] = (result.stderr or "").strip() or "Falha ao executar diagnostico."
    return payload


def collect_performance_sample(host: str) -> dict:
    if not script_enabled("performance_monitor"):
        return {
            "host": host,
            "requested_host": host,
            "generated_at": utc_now(),
            "ok": False,
            "message": "Monitoramento de performance esta desabilitado nas configuracoes do WMT.",
        }

    try:
        result = run_powershell_script("performance_sample.ps1", host, "sample", timeout=45)
    except subprocess.TimeoutExpired as exc:
        details = "\n".join(item for item in [exc.stdout or "", exc.stderr or ""] if item).strip()
        raise HTTPException(
            status_code=504,
            detail=friendly_error_message(details or f"Tempo limite excedido ao coletar performance em {host}.", "monitoramento de performance"),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=friendly_error_message(str(exc), "monitoramento de performance"))

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail=friendly_error_message(stdout or stderr or "A coleta de performance nao retornou JSON valido.", "monitoramento de performance"),
        )

    payload["ok"] = result.returncode == 0
    if result.returncode != 0:
        payload["message"] = friendly_error_message(stderr or payload.get("message") or "Falha ao coletar performance.", "monitoramento de performance")
    return payload


def cached_diagnostic_pack(host: str, include_details: bool = False) -> dict:
    normalized = validate_backup_host(host)
    ttl_seconds = 120 if include_details else 75
    return _cache_for(
        f"diagnostic:{normalized}:details={int(include_details)}",
        ttl_seconds,
        lambda: run_diagnostic_pack(normalized, run_cleanup=False, include_details=include_details),
    )


def cached_software_center_status(host: str) -> dict:

    normalized = host.strip() or "localhost"
    return _cache_for(
        f"software-center:{normalized.upper()}:status",
        60,
        lambda: run_software_center_script(normalized, "status"),
    )


def _public_diagnostic_job(job: dict) -> dict:
    return {
        "id": job.get("id", ""),
        "host": job.get("host", ""),
        "status": job.get("status", "queued"),
        "detailed": bool(job.get("detailed")),
        "message": job.get("message", ""),
        "error": job.get("error", ""),
        "created_by": job.get("created_by", ""),
        "created_at": job.get("created_at", ""),
        "started_at": job.get("started_at", ""),
        "ended_at": job.get("ended_at", ""),
        "duration_ms": job.get("duration_ms", 0),
        "payload": job.get("payload"),
    }


def _trim_diagnostic_jobs() -> None:
    if len(DIAGNOSTIC_JOBS) <= 80:
        return
    removable = sorted(
        DIAGNOSTIC_JOBS.values(),
        key=lambda item: item.get("ended_at") or item.get("created_at") or "",
    )[:20]
    for job in removable:
        DIAGNOSTIC_JOBS.pop(job.get("id"), None)


def _set_diagnostic_job(job_id: str, **fields) -> dict | None:
    with DIAGNOSTIC_JOBS_LOCK:
        job = DIAGNOSTIC_JOBS.get(job_id)
        if not job:
            return None
        job.update(fields)
        return _public_diagnostic_job(job)


def _run_diagnostic_job(job_id: str, host: str, detailed: bool) -> None:
    _set_diagnostic_job(job_id, status="queued", message="Aguardando vaga para coletar diagnostico...")
    with DIAGNOSTIC_JOB_SEMAPHORE:
        started = time.time()
        _set_diagnostic_job(job_id, status="running", message="Coletando diagnostico...", started_at=utc_now())
        try:
            payload = run_diagnostic_pack(host, run_cleanup=False, include_details=detailed)
            _cache_set(f"diagnostic:{host}:details={int(detailed)}", payload)
            _set_diagnostic_job(
                job_id,
                status="completed",
                message="Diagnostico concluido.",
                payload=payload,
                ended_at=utc_now(),
                duration_ms=int((time.time() - started) * 1000),
            )
        except Exception as exc:
            _set_diagnostic_job(
                job_id,
                status="failed",
                message="Falha ao executar diagnostico.",
                error=str(exc),
                payload={"host": host, "checks": [], "error": str(exc)},
                ended_at=utc_now(),
                duration_ms=int((time.time() - started) * 1000),
            )


def create_diagnostic_job(host: str, detailed: bool, username: str) -> dict:
    normalized = validate_backup_host(host)
    cached = _cache_get(f"diagnostic:{normalized}:details={int(detailed)}", 120 if detailed else 75)
    if cached is not None:
        return {
            "id": f"cache-{secrets.token_hex(4)}",
            "host": normalized,
            "status": "completed",
            "detailed": detailed,
            "message": "Resultado recente reaproveitado.",
            "error": "",
            "created_by": username,
            "created_at": utc_now(),
            "started_at": "",
            "ended_at": utc_now(),
            "duration_ms": 0,
            "payload": cached,
        }

    with DIAGNOSTIC_JOBS_LOCK:
        existing = next(
            (
                item
                for item in DIAGNOSTIC_JOBS.values()
                if item.get("host") == normalized
                and bool(item.get("detailed")) == bool(detailed)
                and item.get("status") in {"queued", "running"}
            ),
            None,
        )
        if existing:
            return _public_diagnostic_job(existing)

    job = {
        "id": secrets.token_hex(8),
        "host": normalized,
        "status": "queued",
        "detailed": detailed,
        "message": "Diagnostico na fila.",
        "error": "",
        "created_by": username,
        "created_at": utc_now(),
        "started_at": "",
        "ended_at": "",
        "duration_ms": 0,
        "payload": None,
    }
    with DIAGNOSTIC_JOBS_LOCK:
        DIAGNOSTIC_JOBS[job["id"]] = job
        _trim_diagnostic_jobs()
    thread = threading.Thread(target=_run_diagnostic_job, args=(job["id"], normalized, detailed), daemon=True)
    thread.start()
    return _public_diagnostic_job(job)


def build_wmt_health(host: str) -> dict:
    checks: list[dict] = []
    checks.append({"name": "Backend", "status": "ok", "message": "Backend local respondeu."})
    checks.append({
        "name": "Updater",
        "status": "ok" if (UPDATES_DIR / "latest.json").exists() else "warn",
        "message": "Manifesto de update encontrado." if (UPDATES_DIR / "latest.json").exists() else "Manifesto de update nao encontrado.",
    })

    diagnostic = cached_diagnostic_pack(host, include_details=False)
    for item in diagnostic.get("checks", []):
        checks.append(item)

    return {
        "host": host,
        "generated_at": utc_now(),
        "checks": checks,
    }
