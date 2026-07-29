"""WMT powershell components."""

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
    SCRIPT_DIR,
)
from ..core.security import (
    friendly_error_message,
)
from ..repositories.state import (
    current_settings,
    script_enabled,
)

REMOTE_JOBS_LOCK = threading.Lock()


REMOTE_JOB_PROCESSES: dict[str, subprocess.Popen[str]] = {}


def launch_windows_action(command: list[str]) -> bool:
    try:
        subprocess.Popen(command, shell=False)
        return True
    except Exception:
        return False


REMOTE_ACTION_ALIASES = {
    "remote access": "remote-access",
    "remote-access": "remote-access",
    "rdp": "remote-access",
    "remote desktop": "remote-access",
    "remote assistance": "remote-assistance",
    "remote-assistance": "remote-assistance",
    "admin share": "admin-share",
    "admin-share": "admin-share",
    "create temp c share": "create-temp-c-share",
    "create-temp-c-share": "create-temp-c-share",
    "remove temp c share": "remove-temp-c-share",
    "remove-temp-c-share": "remove-temp-c-share",
    "computer management": "computer-management",
    "computer-management": "computer-management",
    "gpupdate": "gpupdate",
    "restart spooler": "restart-spooler",
    "restart-spooler": "restart-spooler",
    "renew ip": "renew-ip",
    "renew-ip": "renew-ip",
    "reconfigure ip": "renew-ip",
    "reconfigurar ip": "renew-ip",
    "renovar ip": "renew-ip",
}


CONFIGMGR_ACTION_ALIASES = {
    "force all actions": "force-all-actions",
    "force-all-actions": "force-all-actions",
    "configmgr force all actions": "force-all-actions",
    "clear sccm cache": "clear-sccm-cache",
    "clear-sccm-cache": "clear-sccm-cache",
    "limpar cache sccm": "clear-sccm-cache",
    "sccm clear cache": "clear-sccm-cache",
}


def _normalize_remote_action_key(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _canonical_remote_action(value: str) -> str:
    normalized = _normalize_remote_action_key(value)
    settings_aliases = {
        _normalize_remote_action_key(key): str(alias_value).strip()
        for key, alias_value in (current_settings().get("remote_action_aliases") or {}).items()
        if str(key).strip() and str(alias_value).strip()
    }
    normalized = _normalize_remote_action_key(settings_aliases.get(normalized, normalized))
    if normalized in REMOTE_ACTION_ALIASES:
        return REMOTE_ACTION_ALIASES[normalized]
    if normalized in CONFIGMGR_ACTION_ALIASES:
        return CONFIGMGR_ACTION_ALIASES[normalized]
    return normalized.replace(" ", "-")


def powershell_executable() -> str | None:
    return shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh.exe") or shutil.which("pwsh")


def run_powershell_script(
    script_name: str,
    host: str,
    action: str,
    timeout: int = 75,
    job_id: str | None = None,
) -> subprocess.CompletedProcess[str]:
    executable = powershell_executable()
    if executable is None:
        raise RuntimeError("PowerShell nao encontrado neste ambiente.")

    script_path = SCRIPT_DIR / script_name
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
        "-Action",
        action,
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if job_id:
        with REMOTE_JOBS_LOCK:
            REMOTE_JOB_PROCESSES[job_id] = process
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        stdout, stderr = process.communicate()
        exc.stdout = stdout
        exc.stderr = stderr
        raise exc
    finally:
        if job_id:
            with REMOTE_JOBS_LOCK:
                REMOTE_JOB_PROCESSES.pop(job_id, None)

    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def run_software_center_script(host: str, action: str) -> dict:
    if not script_enabled("software_center"):
        return {
            "installed": False,
            "clientVersion": "",
            "serviceStatus": "",
            "pendingUpdates": 0,
            "updates": [],
            "ok": False,
            "message": "Scripts do Software Center estão desabilitados nas configurações do WMT.",
        }

    timeout = int(current_settings().get("software_center_timeout_seconds") or 180)
    try:
        result = run_powershell_script("software_center.ps1", host, action, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        details = "\n".join(item for item in [exc.stdout or "", exc.stderr or ""] if item).strip()
        return {
            "installed": False,
            "clientVersion": "",
            "serviceStatus": "",
            "pendingUpdates": 0,
            "updates": [],
            "ok": False,
            "message": f"Tempo limite excedido ao consultar Software Center em {host}.",
            "details": details,
        }
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if not stdout:
        return {
            "installed": False,
            "clientVersion": "",
            "serviceStatus": "",
            "pendingUpdates": 0,
            "updates": [],
            "ok": False,
            "message": friendly_error_message(stderr or "Software Center nao retornou dados.", "consulta do Software Center"),
        }

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        payload = {
            "installed": False,
            "clientVersion": "",
            "serviceStatus": "",
            "pendingUpdates": 0,
            "updates": [],
            "ok": False,
            "message": friendly_error_message(stdout, "consulta do Software Center"),
        }

    if result.returncode != 0:
        payload["ok"] = False
        payload["message"] = friendly_error_message(stderr or payload.get("message") or "Falha ao consultar Software Center.", "consulta do Software Center")

    return payload


def execute_remote_action(host: str, requested_action: str, job_id: str | None = None) -> tuple[bool, str, str]:
    if not script_enabled("remote_actions"):
        return False, "Ações remotas estão desabilitadas nas configurações do WMT.", ""

    normalized = _canonical_remote_action(requested_action)

    if normalized in set(REMOTE_ACTION_ALIASES.values()):
        script_name = "remote_action.ps1"
        script_action = normalized
    elif normalized in set(CONFIGMGR_ACTION_ALIASES.values()):
        script_name = "configmgr_action.ps1"
        script_action = normalized
    else:
        supported = sorted([*REMOTE_ACTION_ALIASES.keys(), *CONFIGMGR_ACTION_ALIASES.keys()])
        raise HTTPException(status_code=400, detail=f"Unsupported remote action. Supported actions: {', '.join(supported)}")

    try:
        result = run_powershell_script(script_name, host, script_action, timeout=75, job_id=job_id)
    except subprocess.TimeoutExpired as exc:
        details = "\n".join(item for item in [exc.stdout or "", exc.stderr or ""] if item).strip()
        return False, f"Ação '{requested_action}' excedeu o tempo limite em {host}.", details
    except Exception as exc:
        details = str(exc)
        return False, friendly_error_message(details, f"ação remota '{requested_action}' em {host}"), details

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    details = "\n".join(item for item in [stdout, stderr] if item).strip()

    if result.returncode == 0:
        message = stdout.splitlines()[-1] if stdout else f"Remote action '{requested_action}' executed on {host}."
        return True, message, details

    lowered_details = details.lower()
    first_error_line = next((line.strip() for line in (stderr or stdout).splitlines() if line.strip()), "")
    message = friendly_error_message(
        first_error_line or lowered_details or f"Remote action '{requested_action}' failed on {host}.",
        f"remote action '{requested_action}' on {host}",
    )
    return False, message, details
