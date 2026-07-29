"""WMT temp shares components."""

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

from ..core.config import (
    BACKUP_TEMPORARY_SHARE_TTL_MINUTES,
)
from .powershell import (
    powershell_executable,
)
from ..core.security import (
    utc_now,
)
from ..repositories.state import (
    load_state,
    mutate_state,
)
from ..core.validators import (
    _normalize_drive_letter,
    _temporary_share_name,
    validate_backup_host,
)

TEMP_SHARES_CACHE_LOCK = threading.Lock()


TEMP_SHARES_CACHE: dict[str, dict] = {}


def _normalize_history_host(value: str) -> str:
    return validate_backup_host(value).upper()


def _audit_hosts(details: dict) -> set[str]:
    hosts: set[str] = set()
    for key in ("host", "wk", "source", "destination", "workstation"):
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            try:
                hosts.add(_normalize_history_host(value))
            except HTTPException:
                pass
    return hosts


def _matches_history_host(value: object, host: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        return _normalize_history_host(value) == host
    except HTTPException:
        return False


def _list_active_temp_shares(host: str) -> tuple[list[dict], str]:
    executable = powershell_executable()
    if executable is None:
        return [], "PowerShell nao encontrado neste ambiente."
    command = (
        "$ErrorActionPreference='Stop'; "
        f"$shares=Get-WmiObject -Class Win32_Share -ComputerName {json.dumps(host)} "
        "| Where-Object { $_.Name -like 'WMT_TEMP_*' -or $_.Name -eq 'TempC$' } "
        "| Select-Object Name,Path,Description; "
        "$shares | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=12,
    )
    if result.returncode != 0:
        return [], (result.stderr or result.stdout or "").strip() or "Falha ao consultar shares temporarias."
    payload = (result.stdout or "").strip()
    if not payload:
        return [], ""
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return [], payload
    items = parsed if isinstance(parsed, list) else [parsed]
    return [
        {
            "name": str(item.get("Name") or ""),
            "path": str(item.get("Path") or ""),
            "description": str(item.get("Description") or ""),
        }
        for item in items
        if isinstance(item, dict)
    ], ""


def _history_detail_value(value: object) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value if item is not None and item != "")
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _utc_after_minutes(minutes: int) -> str:
    return (datetime.datetime.utcnow() + datetime.timedelta(minutes=max(1, int(minutes or 1)))).isoformat(timespec="seconds") + "Z"


def _parse_utc(value: str) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", ""))
    except ValueError:
        return None


def _track_temp_share(
    host: str,
    share_name: str,
    drive: str,
    path: str,
    expires_at: str,
    source: str,
    cleanup_task: str = "",
) -> None:
    normalized_host = _normalize_history_host(host)
    normalized_share = str(share_name or "").strip() or _temporary_share_name(drive)
    tracked_share = {
        "id": f"{normalized_host}:{normalized_share}",
        "host": normalized_host,
        "share_name": normalized_share,
        "drive": _normalize_drive_letter(drive),
        "path": path or f"{_normalize_drive_letter(drive)}:\\",
        "unc_path": f"\\\\{normalized_host}\\{normalized_share}",
        "source": source,
        "created_at": utc_now(),
        "expires_at": expires_at
        or _utc_after_minutes(BACKUP_TEMPORARY_SHARE_TTL_MINUTES),
        "cleanup_task": cleanup_task,
        "active": True,
        "last_seen": utc_now(),
    }

    def track(state: dict) -> None:
        shares = [
            item
            for item in state.get("temp_shares", [])
            if not (
                _matches_history_host(item.get("host"), normalized_host)
                and str(item.get("share_name") or "").lower()
                == normalized_share.lower()
            )
        ]
        shares.insert(0, tracked_share)
        state["temp_shares"] = shares[:200]

    mutate_state(track)
    with TEMP_SHARES_CACHE_LOCK:
        TEMP_SHARES_CACHE.pop(normalized_host, None)


def _untrack_temp_share(host: str, share_name: str) -> None:
    normalized_host = _normalize_history_host(host)
    normalized_share = str(share_name or "").strip()

    def untrack(state: dict) -> None:
        state["temp_shares"] = [
            item
            for item in state.get("temp_shares", [])
            if not (
                _matches_history_host(item.get("host"), normalized_host)
                and str(item.get("share_name") or "").lower()
                == normalized_share.lower()
            )
        ]

    mutate_state(untrack)
    with TEMP_SHARES_CACHE_LOCK:
        TEMP_SHARES_CACHE.pop(normalized_host, None)


def _public_temp_share(item: dict, live_names: set[str] | None = None) -> dict:
    expires_at = str(item.get("expires_at") or "")
    expires_dt = _parse_utc(expires_at)
    expired = bool(expires_dt and expires_dt < datetime.datetime.utcnow())
    share_name = str(item.get("share_name") or "")
    live = True if live_names is None else share_name.lower() in live_names
    active = bool(item.get("active", True)) and live and not expired
    return {
        "id": item.get("id") or f"{item.get('host')}:{share_name}",
        "host": item.get("host") or "",
        "share_name": share_name,
        "drive": item.get("drive") or "",
        "path": item.get("path") or "",
        "unc_path": item.get("unc_path") or "",
        "source": item.get("source") or "",
        "created_at": item.get("created_at") or "",
        "expires_at": expires_at,
        "cleanup_task": item.get("cleanup_task") or "",
        "active": active,
        "expired": expired,
        "last_seen": item.get("last_seen") or "",
    }


def _temp_share_drive_from_name(share_name: str) -> str:
    match = re.match(r"^WMT_TEMP_([A-Z])\$$", str(share_name or "").upper())
    if match:
        return match.group(1)
    if str(share_name or "").lower() == "tempc$":
        return "C"
    raise HTTPException(status_code=400, detail="Unsupported temporary share name")


def build_temp_shares_payload(state: dict | None = None, verify_live: bool = True) -> dict:
    if state is None:
        state = load_state()
    shares = state.get("temp_shares", [])
    live_by_host: dict[str, set[str]] = {}
    if verify_live:
        for host in sorted({str(item.get("host") or "").upper() for item in shares if item.get("host")}):
            now_ts = time.time()
            with TEMP_SHARES_CACHE_LOCK:
                cached = TEMP_SHARES_CACHE.get(host)
            if cached and now_ts - float(cached.get("ts") or 0) < 30:
                live_by_host[host] = set(cached.get("names") or [])
                continue

            try:
                live_items, _error = _list_active_temp_shares(host)
                live_names = {str(item.get("name") or "").lower() for item in live_items}
            except Exception:
                live_names = set()
            with TEMP_SHARES_CACHE_LOCK:
                TEMP_SHARES_CACHE[host] = {"ts": now_ts, "names": sorted(live_names)}
            live_by_host[host] = live_names

    public_items = [
        _public_temp_share(item, live_by_host.get(str(item.get("host") or "").upper()) if verify_live else None)
        for item in shares
    ]
    public_items.sort(key=lambda item: (not bool(item.get("active")), str(item.get("expires_at") or "")))
    active_count = sum(1 for item in public_items if item.get("active"))
    expired_count = sum(1 for item in public_items if item.get("expired"))
    return {
        "shares": public_items,
        "total": len(public_items),
        "active": active_count,
        "expired": expired_count,
    }
