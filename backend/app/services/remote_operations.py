"""WMT remote operations components."""

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
    HOST_PATTERN,
    SCRIPT_DIR,
)
from .powershell import (
    _canonical_remote_action,
    powershell_executable,
)
from ..schemas import (
    RemoteActionRequest,
)
from ..core.security import (
    friendly_error_message,
)

def validate_remote_action_request(request: RemoteActionRequest, user: dict | None = None) -> tuple[str, str]:
    host = request.host.strip() or "localhost"
    action = _canonical_remote_action(request.action).strip()

    if not action:
        raise HTTPException(status_code=400, detail="Action is required")
    if not HOST_PATTERN.match(host):
        raise HTTPException(status_code=400, detail="Host contains unsupported characters")
    return host, action


def run_maintenance_mode(
    host: str,
    action: str,
    technician: str = "",
    technician_username: str = "",
    contact: str = "",
    ticket: str = "",
    reason: str = "",
    duration_minutes: int = 60,
    target_user: str = "",
) -> dict:
    normalized_host = host.strip().upper()
    if not normalized_host:
        raise HTTPException(status_code=400, detail="Host is required")
    executable = powershell_executable()
    script_path = SCRIPT_DIR / "maintenance_mode.ps1"
    if executable is None or not script_path.exists():
        raise HTTPException(status_code=500, detail="Maintenance mode script is not available")
    command = [
        executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path),
        "-HostName", normalized_host, "-Action", action,
    ]
    if technician:
        command.extend(["-Technician", technician])
    if technician_username:
        command.extend(["-TechnicianUsername", technician_username])
    if contact:
        command.extend(["-Contact", contact])
    if ticket:
        command.extend(["-Ticket", ticket])
    if reason:
        command.extend(["-Reason", reason])
    command.extend(["-DurationMinutes", str(duration_minutes)])
    if target_user:
        command.extend(["-TargetUser", target_user])
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"Maintenance mode operation timed out on {normalized_host}")
    if result.returncode != 0:
        detail = friendly_error_message((result.stderr or result.stdout or "").strip(), f"modo manutenção em {normalized_host}")
        raise HTTPException(status_code=502, detail=detail)
    try:
        payload = json.loads(next(line for line in reversed(result.stdout.splitlines()) if line.strip()))
    except Exception:
        raise HTTPException(status_code=502, detail="Invalid maintenance mode response")
    if not isinstance(payload.get("protected_users"), list):
        payload["protected_users"] = []
    return {"host": normalized_host, **payload}
