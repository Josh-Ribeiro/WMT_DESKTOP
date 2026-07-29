"""WMT history components."""

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

from .backup import (
    BACKUP_JOBS,
    BACKUP_JOBS_LOCK,
    _public_backup_job,
)
from .cache import (
    text_value,
)
from .powershell import (
    REMOTE_JOBS_LOCK,
)
from .remote_jobs import (
    REMOTE_JOBS,
    _public_remote_job,
)
from .snmp import is_forced_printer_host
from ..core.security import (
    utc_now,
)
from ..repositories.state import (
    load_state,
    load_state_fields,
)
from .temp_shares import (
    _audit_hosts,
    _history_detail_value,
    _list_active_temp_shares,
    _matches_history_host,
    _normalize_history_host,
)

def _universal_workstation_matches(query: str, limit: int) -> list[dict]:
    needle = query.strip().lower()
    if not needle:
        return []

    state = load_state_fields("audit", "backup_jobs", "remote_jobs", "update_jobs")
    candidates: dict[str, dict] = {}

    def remember(host_value: object, payload: dict | None = None, timestamp: object = "") -> None:
        host = str(host_value or "").strip().upper()
        if not host:
            return
        details = payload if isinstance(payload, dict) else {}
        searchable = " ".join(
            str(details.get(key) or "")
            for key in ("host", "ip_address", "serial_number", "asset_number", "patrimony", "manufacturer", "model", "current_user")
        ).lower()
        if needle not in host.lower() and needle not in searchable:
            return
        existing = candidates.get(host)
        candidate = {
            "host": host,
            "ip_address": text_value(details.get("ip_address")),
            "serial_number": text_value(details.get("serial_number")),
            "manufacturer": text_value(details.get("manufacturer")),
            "model": text_value(details.get("model")),
            "current_user": text_value(details.get("current_user")),
            "last_seen": text_value(timestamp),
            "known": True,
            "device_type": (
                "printer"
                if is_forced_printer_host(host)
                or is_forced_printer_host(text_value(details.get("ip_address")))
                or text_value(details.get("device_type")) == "printer"
                else "workstation"
            ),
        }
        if existing is None or str(candidate["last_seen"]) > str(existing.get("last_seen") or ""):
            candidates[host] = candidate

    for item in state.get("audit") or []:
        details = item.get("details") or {}
        if not isinstance(details, dict):
            continue
        for host in _audit_hosts(details):
            remember(host, details, item.get("timestamp"))

    for collection in ("backup_jobs", "remote_jobs", "update_jobs"):
        for item in state.get(collection) or []:
            if not isinstance(item, dict):
                continue
            timestamp = item.get("created_at") or item.get("start_time") or item.get("ended_at") or ""
            for key in ("host", "source", "destination", "workstation"):
                remember(item.get(key), item, timestamp)

    host_like = bool(
        re.fullmatch(r"(?:[A-Za-z][A-Za-z0-9_.-]*\d[A-Za-z0-9_.-]*|\d{1,3}(?:\.\d{1,3}){3})", query.strip())
    )
    exact_host = query.strip().upper()
    if host_like and exact_host not in candidates:
        candidates[exact_host] = {
            "host": exact_host,
            "ip_address": exact_host if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", exact_host) else "",
            "serial_number": "",
            "manufacturer": "",
            "model": "",
            "current_user": "",
            "last_seen": "",
            "known": False,
            "device_type": (
                "printer"
                if is_forced_printer_host(exact_host)
                else "workstation"
            ),
        }

    return sorted(
        candidates.values(),
        key=lambda item: (item["host"].lower() != needle, not item["known"], item["host"]),
    )[:limit]


def build_workstation_history(host: str) -> dict:
    normalized_host = _normalize_history_host(host)
    state = load_state()

    with BACKUP_JOBS_LOCK:
        runtime_backup_jobs = [_public_backup_job(job) for job in BACKUP_JOBS.values()]
    backup_jobs_by_id = {job.get("id"): job for job in state.get("backup_jobs", [])}
    for job in runtime_backup_jobs:
        backup_jobs_by_id[job.get("id")] = job
    backups = [
        job
        for job in backup_jobs_by_id.values()
        if _matches_history_host(job.get("source"), normalized_host)
        or _matches_history_host(job.get("destination"), normalized_host)
        or _matches_history_host(job.get("workstation"), normalized_host)
    ]
    backups.sort(key=lambda item: str(item.get("start_time") or ""), reverse=True)

    with REMOTE_JOBS_LOCK:
        runtime_remote_jobs = [_public_remote_job(job) for job in REMOTE_JOBS.values()]
    remote_jobs_by_id = {job.get("id"): job for job in state.get("remote_jobs", [])}
    for job in runtime_remote_jobs:
        remote_jobs_by_id[job.get("id")] = job
    remote_jobs = [
        job
        for job in remote_jobs_by_id.values()
        if _matches_history_host(job.get("host"), normalized_host)
    ]
    remote_jobs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)

    audit_items = [
        item
        for item in state.get("audit", [])
        if normalized_host in _audit_hosts(item.get("details") or {})
    ]
    diagnostics = [
        item
        for item in audit_items
        if item.get("action") in {"diagnostics.run", "diagnostics.job", "cleanup.quick"}
    ]
    terms = [
        item
        for item in audit_items
        if str(item.get("action") or "").startswith("terms.")
    ]
    active_temp_shares, temp_share_error = _list_active_temp_shares(normalized_host)

    events: list[dict] = []
    for job in backups:
        status = str(job.get("status") or "")
        events.append(
            {
                "id": job.get("id") or secrets.token_hex(4),
                "kind": "backup",
                "title": f"Backup {job.get('source') or '-'} -> {job.get('destination') or '-'}",
                "status": status,
                "timestamp": job.get("start_time") or "",
                "actor": "",
                "detail": job.get("summary") or job.get("message") or "",
                "error": bool(status in {"failed", "canceled"} or job.get("failures")),
            }
        )
    for job in remote_jobs:
        status = str(job.get("status") or "")
        events.append(
            {
                "id": job.get("id") or secrets.token_hex(4),
                "kind": "remote",
                "title": str(job.get("action") or "Remote action"),
                "status": status,
                "timestamp": job.get("created_at") or "",
                "actor": job.get("created_by") or "",
                "detail": job.get("message") or "",
                "error": status in {"failed", "canceled"},
            }
        )
    for item in audit_items:
        details = item.get("details") or {}
        action = str(item.get("action") or "")
        kind = "audit"
        if action.startswith("terms."):
            kind = "terms"
        elif action.startswith("diagnostics.") or action.startswith("cleanup."):
            kind = "diagnostic"
        elif action.startswith("backup."):
            kind = "backup"
        detail_parts = []
        for key, value in details.items():
            if key in {"host", "wk", "source", "destination"}:
                continue
            formatted_value = _history_detail_value(value)
            if formatted_value:
                detail_parts.append(f"{key}: {formatted_value}")
        detail = ", ".join(detail_parts)
        events.append(
            {
                "id": item.get("id") or secrets.token_hex(4),
                "kind": kind,
                "title": action,
                "status": "logged",
                "timestamp": item.get("timestamp") or "",
                "actor": item.get("username") or "",
                "detail": detail,
                "error": "error" in action.lower() or "failed" in detail.lower() or "erro" in detail.lower(),
            }
        )

    events.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    recent_errors = [event for event in events if event.get("error")][:10]

    return {
        "host": normalized_host,
        "generated_at": utc_now(),
        "summary": {
            "backups": len(backups),
            "remote_actions": len(remote_jobs),
            "diagnostics": len(diagnostics),
            "terms": len(terms),
            "active_temp_shares": len(active_temp_shares),
            "recent_errors": len(recent_errors),
        },
        "active_temp_shares": active_temp_shares,
        "temp_share_error": temp_share_error,
        "backups": backups[:20],
        "remote_actions": remote_jobs[:30],
        "diagnostics": diagnostics[:20],
        "terms": terms[:20],
        "recent_errors": recent_errors,
        "events": events[:80],
    }
