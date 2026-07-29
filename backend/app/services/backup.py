"""WMT backup components."""

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
    BACKUP_EXCLUDED_FILE_PATTERNS,
    BACKUP_FOLDERS,
    BACKUP_TEMPORARY_SHARE_TTL_MINUTES,
    REMOTE_ADMIN_PASS,
    REMOTE_ADMIN_USER,
    SCRIPT_DIR,
    TEMPORARY_C_SHARE_NAME,
)
from .powershell import (
    powershell_executable,
)
from .backup_paths import (
    build_destination_base_path as _build_destination_base_path,
    build_destination_path as _build_destination_path,
    build_source_path as _build_source_path,
    build_temporary_destination_browse_path as _build_temporary_destination_browse_path,
    build_unc_from_absolute_path as _build_unc_from_absolute_path,
    normalize_absolute_windows_path as _normalize_absolute_windows_path,
    normalize_destination_root as _normalize_destination_root,
    safe_robocopy_exclude_patterns as _safe_robocopy_exclude_patterns,
)
from ..core.security import (
    friendly_error_message,
    utc_now,
)
from ..repositories.state import (
    load_state,
    mutate_state,
)
from .temp_shares import (
    _track_temp_share,
    _untrack_temp_share,
    _utc_after_minutes,
)
from ..core.validators import (
    _normalize_drive_letter,
    _temporary_share_name,
)

BACKUP_JOBS_LOCK = threading.Lock()


BACKUP_JOBS: dict[str, dict] = {}


def backup_status_for_ui(status: str) -> str:
    return {
        "error": "failed",
        "cancelled": "canceled",
    }.get(status, status)


def _set_backup_job(job_id: str, **fields: object) -> None:
    with BACKUP_JOBS_LOCK:
        job = BACKUP_JOBS.get(job_id)
        if job:
            job.update(fields)


def _backup_estimated_end_time(eta_seconds: int | None) -> str | None:
    if eta_seconds is None or eta_seconds <= 0:
        return None
    return (datetime.datetime.utcnow() + datetime.timedelta(seconds=eta_seconds)).isoformat(timespec="seconds") + "Z"


def _robocopy_failure_detail(output: str, stderr: str = "") -> str:
    lines = [
        line.strip()
        for line in f"{output or ''}\n{stderr or ''}".splitlines()
        if line.strip()
    ]
    error_lines = [
        line
        for line in lines
        if re.search(r"\bERROR\s+\d+\b", line, re.IGNORECASE)
        or "access is denied" in line.lower()
        or "access denied" in line.lower()
        or "cannot find" in line.lower()
        or "the system cannot find" in line.lower()
    ]
    if error_lines:
        return " | ".join(error_lines[-3:])

    failed_summary = [line for line in lines if re.search(r"\bFAILED\b", line, re.IGNORECASE)]
    if failed_summary:
        return failed_summary[-1]

    return ""


def _append_backup_log(job_id: str, text: str) -> None:
    if not text:
        return
    with BACKUP_JOBS_LOCK:
        job = BACKUP_JOBS.get(job_id)
        if job:
            job["log"] = (job.get("log") or "") + text


def _is_backup_job_cancelled(job_id: str) -> bool:
    with BACKUP_JOBS_LOCK:
        job = BACKUP_JOBS.get(job_id)
        return bool(job and job.get("cancel_requested"))


def _disconnect_share(host: str, share_name: str) -> None:
    share = (share_name or "C").strip("\\/").upper()
    try:
        subprocess.run(["net", "use", f"\\\\{host}\\{share}", "/delete", "/yes"], capture_output=True, text=True, timeout=8)
    except subprocess.TimeoutExpired:
        pass


def _disconnect_host_sessions(host: str) -> None:
    host = (host or "").strip("\\/ ")
    if not host:
        return
    for target in [
        f"\\\\{host}\\IPC$",
        f"\\\\{host}\\ADMIN$",
        f"\\\\{host}\\C$",
        f"\\\\{host}\\C",
        f"\\\\{host}\\{TEMPORARY_C_SHARE_NAME}",
        f"\\\\{host}",
    ]:
        try:
            subprocess.run(["net", "use", target, "/delete", "/yes"], capture_output=True, text=True, timeout=8)
        except subprocess.TimeoutExpired:
            pass


def _connect_share(host: str, share_name: str, username: str, password: str) -> dict:
    share = (share_name or "C").strip("\\/").upper()
    target = f"\\\\{host}\\{share}"
    clean_username = (username or "").strip()

    def connect() -> subprocess.CompletedProcess[str]:
        command = ["net", "use", target, "/persistent:no"]
        if clean_username:
            command = ["net", "use", target, password or "", f"/user:{clean_username}", "/persistent:no"]
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )

    try:
        result = connect()
    except subprocess.TimeoutExpired:
        return {
            "host": host,
            "share": share,
            "success": False,
            "stdout": "",
            "stderr": f"Timeout connecting to \\\\{host}\\{share}",
            "returncode": -1,
        }
    combined = " ".join(part for part in [result.stdout, result.stderr] if part).lower()
    if result.returncode != 0 and "1219" in combined:
        _disconnect_host_sessions(host)
        try:
            result = connect()
        except subprocess.TimeoutExpired:
            return {
                "host": host,
                "share": share,
                "success": False,
                "stdout": "",
                "stderr": f"Timeout connecting to \\\\{host}\\{share}",
                "returncode": -1,
            }

    return {
        "host": host,
        "share": share,
        "success": result.returncode == 0,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
        "returncode": result.returncode,
    }


def _require_windows_backup_identity(user: dict) -> str:
    identity = str(user.get("windows_identity") or "").strip()
    domain = str(user.get("domain") or "").strip()
    username = str(user.get("username") or "").strip()
    if user.get("auth_source") != "windows" or not (identity or (domain and username)):
        raise HTTPException(
            status_code=403,
            detail="Backup exige login Windows/AD no WMT. Entre via SSO/Windows para usar as permissoes do usuario AD.",
        )
    return identity or f"{domain}\\{username}"


def _resolve_backup_smb_credentials(remote_user: str | None, remote_pass: str | None) -> tuple[str, str]:
    username = (remote_user or REMOTE_ADMIN_USER or "").strip()
    password = (remote_pass or REMOTE_ADMIN_PASS or "").strip()
    return username, password


def _powershell_single_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _ensure_remote_directory(host: str, drive: str, relative: str) -> None:
    if not relative:
        return
    safe_drive = _normalize_drive_letter(drive)
    clean_relative = relative.strip("\\/")
    if not clean_relative:
        return
    if re.search(r'["<>|?*]', clean_relative):
        raise RuntimeError("Invalid destination folder characters")
    if any(part in {"", ".", ".."} for part in re.split(r"[\\/]+", clean_relative)):
        raise RuntimeError("Invalid destination folder")
    target_path = f"{safe_drive}:\\{clean_relative}"
    executable = powershell_executable()
    if executable is None:
        raise RuntimeError("PowerShell nao encontrado neste ambiente.")
    command = f'cmd.exe /c mkdir "{target_path}"'
    process_class = f"\\\\{host}\\root\\cimv2:Win32_Process"
    result = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "$ErrorActionPreference='Stop'; "
                f"$p=[wmiclass]{_powershell_single_quote(process_class)}; "
                f"$r=$p.Create({_powershell_single_quote(command)}); "
                "if ([int]$r.ReturnValue -ne 0) { throw \"mkdir failed ReturnValue=$($r.ReturnValue)\" }"
            ),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    if result.returncode != 0:
        detail = ((result.stderr) or (result.stdout) or "").strip()
        raise RuntimeError(detail or f"Could not create destination folder {target_path}")


def _format_bytes(size_bytes: int) -> str:
    value = float(max(0, int(size_bytes or 0)))
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def _remote_drive_free_bytes(host: str, drive: str) -> int:
    executable = powershell_executable()
    if executable is None:
        raise RuntimeError("PowerShell nao encontrado neste ambiente.")
    safe_drive = _normalize_drive_letter(drive)
    drive_filter = json.dumps(f"DeviceID='{safe_drive}:'")
    command = (
        "$ErrorActionPreference='Stop'; "
        f"$disk=Get-WmiObject -Class Win32_LogicalDisk -ComputerName {json.dumps(host)} "
        f"-Filter {drive_filter}; "
        f"if ($null -eq $disk) {{ throw 'Drive {safe_drive}: not found on {host}' }}; "
        "[int64]$disk.FreeSpace"
    )
    result = subprocess.run(
        [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip() or "Could not query destination free space")
    return int((result.stdout or "0").strip() or "0")


def _remote_drive_exists(host: str, drive: str) -> bool:
    try:
        _remote_drive_free_bytes(host, drive)
        return True
    except Exception as exc:
        if "not found" in str(exc).lower():
            return False
        raise


def _unc_path_exists(path: str) -> bool:
    executable = powershell_executable()
    if executable is None:
        return False
    result = subprocess.run(
        [executable, "-NoProfile", "-Command", f"if (Test-Path -LiteralPath {_powershell_single_quote(path)}) {{ 'true' }} else {{ 'false' }}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=12,
    )
    return (result.stdout or "").strip().lower() == "true"


def _unc_write_test(path: str) -> tuple[bool, str]:
    executable = powershell_executable()
    if executable is None:
        return False, "PowerShell nao encontrado neste ambiente."
    test_name = f".wmt_write_test_{uuid4().hex}"
    command = (
        "$ErrorActionPreference='Stop'; "
        f"$base={_powershell_single_quote(path)}; "
        f"$test=Join-Path -Path $base -ChildPath {_powershell_single_quote(test_name)}; "
        "try { "
        "if (-not (Test-Path -LiteralPath $base)) { throw \"Destination path not accessible: $base\" }; "
        "New-Item -ItemType Directory -Path $test -Force | Out-Null; "
        "Remove-Item -LiteralPath $test -Force -Recurse; "
        "'ok' "
        "} catch { Write-Error $_.Exception.Message; exit 1 }"
    )
    result = subprocess.run(
        [executable, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if result.returncode == 0:
        return True, ""
    return False, (result.stderr or result.stdout or "").strip() or f"Could not write to {path}"


def _unc_folder_size_bytes(path: str, timeout_seconds: int = 45) -> tuple[int, bool]:
    executable = powershell_executable()
    if executable is None:
        raise RuntimeError("PowerShell nao encontrado neste ambiente.")
    command = (
        f"$path={_powershell_single_quote(path)}; "
        "if (-not (Test-Path -LiteralPath $path)) { 0; exit 0 }; "
        "$sum = Get-ChildItem -LiteralPath $path -Recurse -Force -File -ErrorAction SilentlyContinue "
        "| Measure-Object -Property Length -Sum; "
        "[int64]($sum.Sum)"
    )
    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return 0, True
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip() or f"Could not estimate size for {path}")
    return int((result.stdout or "0").strip() or "0"), False


def _run_robocopy_monitored(
    job_id: str,
    command: list[str],
    active_message: str,
    heartbeat_seconds: int = 30,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def read_pipe(pipe: object, chunks: list[str]) -> None:
        if pipe is None:
            return
        try:
            for line in iter(pipe.readline, ""):  # type: ignore[attr-defined]
                chunks.append(line)
        finally:
            try:
                pipe.close()  # type: ignore[attr-defined]
            except Exception:
                pass

    stdout_thread = threading.Thread(target=read_pipe, args=(process.stdout, stdout_chunks), daemon=True)
    stderr_thread = threading.Thread(target=read_pipe, args=(process.stderr, stderr_chunks), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    started = time.perf_counter()
    last_heartbeat = started
    while process.poll() is None:
        if _is_backup_job_cancelled(job_id):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            break

        now = time.perf_counter()
        if now - last_heartbeat >= heartbeat_seconds:
            elapsed_seconds = int(now - started)
            elapsed_minutes = max(1, elapsed_seconds // 60)
            _set_backup_job(
                job_id,
                message=f"{active_message} Robocopy still running for {elapsed_minutes} min...",
            )
            _append_backup_log(job_id, f"\nRobocopy still running after {elapsed_minutes} min...\n")
            last_heartbeat = now
        time.sleep(1)

    returncode = process.wait()
    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)
    return subprocess.CompletedProcess(command, returncode, "".join(stdout_chunks), "".join(stderr_chunks))


def run_temporary_share_action(host: str, action: str, ttl_minutes: int = BACKUP_TEMPORARY_SHARE_TTL_MINUTES, drive_letter: str = "C") -> dict:
    ttl_minutes = max(1, min(240, int(ttl_minutes or BACKUP_TEMPORARY_SHARE_TTL_MINUTES)))
    executable = powershell_executable()
    if executable is None:
        raise RuntimeError("PowerShell nao encontrado neste ambiente.")
    script_path = SCRIPT_DIR / "temporary_share.ps1"
    if not script_path.exists():
        raise RuntimeError(f"Script nao encontrado: {script_path}")

    try:
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-wks",
                host,
                "-action",
                action,
                "-ttlMinutes",
                str(ttl_minutes),
                "-driveLetter",
                drive_letter,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=75,
        )
    except subprocess.TimeoutExpired as exc:
        details = "\n".join(str(part or "").strip() for part in [exc.stdout, exc.stderr] if part).strip()
        suffix = f": {details}" if details else ""
        raise RuntimeError(f"Temporary share {action} timed out on {host} drive {drive_letter}{suffix}")
    payload_text = (result.stdout or "").strip()
    try:
        payload = json.loads(payload_text or "{}")
    except json.JSONDecodeError:
        payload = {"erro": payload_text or (result.stderr or "").strip()}
    if result.returncode != 0 or payload.get("erro"):
        raise RuntimeError(payload.get("erro") or (result.stderr or "").strip() or "Temporary share failed")
    share_name = str(payload.get("ShareName") or _temporary_share_name(drive_letter))
    if action == "create":
        _track_temp_share(
            host,
            share_name,
            drive_letter,
            str(payload.get("SharePath") or f"{_normalize_drive_letter(drive_letter)}:\\"),
            _utc_after_minutes(ttl_minutes),
            "temporary_share",
            str(payload.get("CleanupTaskName") or ""),
        )
    elif action == "remove":
        _untrack_temp_share(host, share_name)
    return payload


def _list_users_from_share(host: str, share_name: str, username: str = "", password: str = "") -> list[str]:
    connect = _connect_share(host, share_name, username, password)
    if not connect["success"]:
        raise RuntimeError(connect["stderr"] or connect["stdout"] or f"Failed to connect to \\\\{host}\\{share_name}")

    users_path = f"\\\\{host}\\{share_name}\\Users"
    try:
        command = (
            f"$path='{users_path}'; "
            "if (-not (Test-Path $path)) { throw 'Users path not accessible' }; "
            "Get-ChildItem -Path $path -Directory | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode == 0 and (result.stdout or "").strip():
            parsed = json.loads(result.stdout.strip())
            return [parsed] if isinstance(parsed, str) else [str(item) for item in parsed]

        fallback = subprocess.run(["cmd", "/c", "dir", "/b", "/ad", users_path], capture_output=True, text=True, timeout=15)
        if fallback.returncode == 0:
            return [line.strip() for line in (fallback.stdout or "").splitlines() if line.strip()]

        raise RuntimeError(result.stderr.strip() or fallback.stderr.strip() or f"Unable to list {users_path}")
    finally:
        _disconnect_share(host, share_name)


def _get_users_remote(host: str, username: str = "", password: str = "") -> list[str]:
    ignored = {"Public", "Default", "Default User", "All Users", "DefaultAppPool", "WDAGUtilityAccount"}
    share_name = TEMPORARY_C_SHARE_NAME
    share_created = False
    errors: list[str] = []

    try:
        try:
            share_result = run_temporary_share_action(host, "create", BACKUP_TEMPORARY_SHARE_TTL_MINUTES)
            share_created = True
            share_name = share_result.get("ShareName") or TEMPORARY_C_SHARE_NAME
            users = _list_users_from_share(host, share_name, username, password)
        except Exception as exc:
            errors.append(f"temporary share: {exc}")
            users = []
            if not users:
                for fallback_share in ["C$", "C"]:
                    try:
                        users = _list_users_from_share(host, fallback_share, username, password)
                        share_name = fallback_share
                        break
                    except Exception as fallback_exc:
                        errors.append(f"{fallback_share}: {fallback_exc}")
            if not users:
                raise RuntimeError(" | ".join(errors))

        filtered: list[str] = []
        seen: set[str] = set()
        for user_name in users:
            clean = str(user_name or "").strip()
            if not clean or clean in ignored or clean.lower() in seen:
                continue
            seen.add(clean.lower())
            filtered.append(clean)
        return filtered
    finally:
        if share_created:
            try:
                run_temporary_share_action(host, "remove", BACKUP_TEMPORARY_SHARE_TTL_MINUTES)
            except Exception:
                pass


def _persist_backup_job(job: dict) -> None:
    log_lines = str(job.get("log") or "").splitlines()
    public_job = {
        "id": job.get("id"),
        "workstation": f"{job.get('source')} -> {job.get('destination')}",
        "source": job.get("source"),
        "destination": job.get("destination"),
        "users": job.get("users", []),
        "status": backup_status_for_ui(str(job.get("status") or "")),
        "start_time": job.get("start_time") or "",
        "end_time": job.get("end_time") or "-",
        "size": job.get("size") or "0 GB",
        "progress": int(job.get("progress") or 0),
        "message": job.get("message") or "",
        "summary": job.get("summary") or "",
        "current_step": int(job.get("current_step") or 0),
        "total_steps": int(job.get("total_steps") or 0),
        "eta_seconds": job.get("eta_seconds"),
        "estimated_end_time": job.get("estimated_end_time"),
        "log": "\n".join(log_lines[-80:]),
        "failures": job.get("failures") or [],
        "checklist": job.get("checklist") or {},
        "backup_type": job.get("backup_type") or "profiles",
        "destination_path": job.get("destination_path") or "",
        "source_path": job.get("source_path") or "",
        "exclude_patterns": job.get("exclude_patterns") or [],
        "validation": job.get("validation") or {},
    }
    def persist(state: dict) -> None:
        jobs = [
            item
            for item in state.get("backup_jobs", [])
            if item.get("id") != job.get("id")
        ]
        jobs.insert(0, public_job)
        state["backup_jobs"] = jobs[:50]

    mutate_state(persist)


def _public_backup_job(job: dict) -> dict:
    return {
        "id": job.get("id"),
        "workstation": f"{job.get('source')} -> {job.get('destination')}",
        "source": job.get("source"),
        "destination": job.get("destination"),
        "users": job.get("users", []),
        "status": backup_status_for_ui(str(job.get("status") or "")),
        "start_time": job.get("start_time") or "",
        "end_time": job.get("end_time") or "-",
        "size": job.get("size") or "0 GB",
        "progress": int(job.get("progress") or 0),
        "message": job.get("message") or "",
        "summary": job.get("summary") or "",
        "current_step": int(job.get("current_step") or 0),
        "total_steps": int(job.get("total_steps") or 0),
        "eta_seconds": job.get("eta_seconds"),
        "estimated_end_time": job.get("estimated_end_time"),
        "log": job.get("log") or "",
        "failures": job.get("failures") or [],
        "checklist": job.get("checklist") or {},
        "backup_type": job.get("backup_type") or "profiles",
        "destination_path": job.get("destination_path") or "",
        "source_path": job.get("source_path") or "",
        "exclude_patterns": job.get("exclude_patterns") or [],
        "validation": job.get("validation") or {},
    }


def _start_backup_share_renewal(job_id: str, targets: list[tuple[str, str]]) -> tuple[threading.Event, threading.Thread | None]:
    stop_event = threading.Event()
    if not targets:
        return stop_event, None

    def renew_loop() -> None:
        while not stop_event.wait(600):
            for host, drive_letter in targets:
                if stop_event.is_set():
                    return
                try:
                    result = run_temporary_share_action(host, "create", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, drive_letter)
                    cleanup_task = result.get("CleanupTaskName") or ""
                    share_name = result.get("ShareName") or _temporary_share_name(drive_letter)
                    suffix = f" ({cleanup_task})" if cleanup_task else ""
                    _append_backup_log(job_id, f"\nTemporary share renewed: \\\\{host}\\{share_name}{suffix}\n")
                except Exception as exc:
                    _append_backup_log(job_id, f"\nWARNING: Failed to renew temporary share on {host}: {exc}\n")

    thread = threading.Thread(target=renew_loop, name=f"backup-share-renewal-{job_id}", daemon=True)
    thread.start()
    _append_backup_log(job_id, "Temporary backup shares will be renewed every 10 minutes while the backup is running.\n")
    return stop_event, thread


def _run_backup_job(
    job_id: str,
    source_host: str,
    destination_host: str,
    users: list[str],
    access_identity: str,
    destination_path: str | None,
    smb_username: str = "",
    smb_password: str = "",
    folders: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> None:
    backup_folders = [folder for folder in (folders or BACKUP_FOLDERS) if folder in BACKUP_FOLDERS]
    if not backup_folders:
        backup_folders = BACKUP_FOLDERS
    robocopy_excludes = exclude_patterns if exclude_patterns is not None else BACKUP_EXCLUDED_FILE_PATTERNS
    total_steps = max(1, len(users) * len(backup_folders))
    current_step = 0
    failures: list[str] = []
    source_share = TEMPORARY_C_SHARE_NAME
    destination_drive = "C"
    destination_share = _temporary_share_name(destination_drive)
    source_share_ready = False
    destination_share_ready = False
    renewal_stop_event: threading.Event | None = None
    renewal_thread: threading.Thread | None = None

    try:
        _append_backup_log(job_id, f"Using WMT Windows identity for backup authorization: {access_identity}\n")
        if smb_username:
            _append_backup_log(job_id, f"Using explicit SMB credential for backup connections: {smb_username}\n")

        _set_backup_job(job_id, status="running", message="Creating temporary source share...")
        try:
            share_result = run_temporary_share_action(source_host, "create", BACKUP_TEMPORARY_SHARE_TTL_MINUTES)
            source_share_ready = True
            source_share = share_result.get("ShareName") or TEMPORARY_C_SHARE_NAME
            source_unc = share_result.get("UncPath") or f"\\\\{source_host}\\{source_share}"
            cleanup_task = share_result.get("CleanupTaskName") or ""
            create_method = share_result.get("CreateMethod") or ""
            _append_backup_log(job_id, f"Temporary source share ready: {source_unc}")
            if create_method:
                _append_backup_log(job_id, f" ({create_method})")
            if cleanup_task:
                _append_backup_log(job_id, f" (cleanup task: {cleanup_task})")
            _append_backup_log(job_id, "\n")
        except Exception as exc:
            source_share = "C$"
            source_unc = f"\\\\{source_host}\\{source_share}"
            _append_backup_log(job_id, f"Temporary source share unavailable, falling back to {source_unc}: {exc}\n")

        destination_root = _normalize_destination_root(destination_path)
        destination_drive = destination_root[0] if destination_root else "C"
        _set_backup_job(job_id, message="Creating temporary destination share...")
        try:
            destination_result = run_temporary_share_action(destination_host, "create", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, destination_drive)
            destination_share_ready = True
            destination_share = destination_result.get("ShareName") or _temporary_share_name(destination_drive)
            destination_unc = destination_result.get("UncPath") or f"\\\\{destination_host}\\{destination_share}"
            cleanup_task = destination_result.get("CleanupTaskName") or ""
            create_method = destination_result.get("CreateMethod") or ""
            _append_backup_log(job_id, f"Temporary destination share ready: {destination_unc}")
            if create_method:
                _append_backup_log(job_id, f" ({create_method})")
            if cleanup_task:
                _append_backup_log(job_id, f" (cleanup task: {cleanup_task})")
            _append_backup_log(job_id, "\n")
        except Exception as exc:
            destination_share = f"{destination_drive}$"
            destination_unc = f"\\\\{destination_host}\\{destination_share}"
            _append_backup_log(job_id, f"Temporary destination share unavailable, falling back to {destination_unc}: {exc}\n")

        renewal_targets: list[tuple[str, str]] = []
        if source_share_ready:
            renewal_targets.append((source_host, "C"))
        if destination_share_ready:
            renewal_targets.append((destination_host, destination_drive))
        renewal_stop_event, renewal_thread = _start_backup_share_renewal(job_id, renewal_targets)

        _set_backup_job(job_id, message="Connecting to source and destination...")
        connect_src = _connect_share(source_host, source_share, smb_username, smb_password)
        connect_dst = _connect_share(destination_host, destination_share, smb_username, smb_password)
        if not connect_src["success"] or not connect_dst["success"]:
            details = []
            if not connect_src["success"]:
                details.append(f"source: {connect_src['stderr'] or connect_src['stdout']}")
            if not connect_dst["success"]:
                details.append(f"destination: {connect_dst['stderr'] or connect_dst['stdout']}")
            message = "Failed to connect to backup shares. " + " | ".join(details)
            _set_backup_job(job_id, status="failed", message=message, summary="Backup failed", failures=details, end_time=utc_now(), eta_seconds=0, estimated_end_time=None)
            return

        destination_base = _build_destination_base_path(destination_host, destination_path, destination_share)
        can_write_destination, write_detail = _unc_write_test(destination_base)
        if not can_write_destination:
            message = f"Destination is not writable: {destination_base}. {write_detail}"
            _append_backup_log(job_id, f"{message}\n")
            _set_backup_job(
                job_id,
                status="failed",
                message=message,
                summary="Backup failed",
                failures=[message],
                end_time=utc_now(),
                eta_seconds=0,
                estimated_end_time=None,
            )
            return

        for profile in users:
            for folder in backup_folders:
                if _is_backup_job_cancelled(job_id):
                    _set_backup_job(job_id, status="canceled", message="Backup cancelled by user.", summary="Backup cancelled", end_time=utc_now(), eta_seconds=0, estimated_end_time=None)
                    return

                source = _build_source_path(source_host, profile, folder, source_share)
                _, destination = _build_destination_path(destination_host, profile, folder, destination_path, destination_share)
                with BACKUP_JOBS_LOCK:
                    started_ts = float(BACKUP_JOBS.get(job_id, {}).get("started_ts") or time.time())
                elapsed = max(0.0, time.time() - started_ts)
                eta_seconds = None
                if 0 < current_step < total_steps:
                    eta_seconds = int((elapsed / current_step) * (total_steps - current_step))
                _set_backup_job(
                    job_id,
                    message=f"Copying {profile}/{folder}...",
                    current_step=current_step,
                    total_steps=total_steps,
                    progress=int((current_step / total_steps) * 100),
                    eta_seconds=eta_seconds,
                    estimated_end_time=_backup_estimated_end_time(eta_seconds),
                )

                robocopy_command = ["robocopy", source, destination, "/E", "/COPY:DAT", "/XJ", "/R:0", "/W:0"]
                if robocopy_excludes:
                    robocopy_command.extend(["/XF", *robocopy_excludes])
                _append_backup_log(job_id, f"\nROBOCOPY source: {source}\nROBOCOPY dest: {destination}\n")
                if robocopy_excludes:
                    _append_backup_log(job_id, f"ROBOCOPY excluded files: {', '.join(robocopy_excludes)}\n")
                result = _run_robocopy_monitored(job_id, robocopy_command, f"Copying {profile}/{folder}...")
                _append_backup_log(job_id, f"\n===== {profile} - {folder} =====\n")
                _append_backup_log(job_id, result.stdout or "")
                if result.stderr:
                    _append_backup_log(job_id, result.stderr)
                if result.returncode > 7:
                    detail = _robocopy_failure_detail(result.stdout, result.stderr)
                    suffix = f": {detail}" if detail else ""
                    failures.append(f"{profile}/{folder} (exit code {result.returncode}){suffix}")

                current_step += 1
                with BACKUP_JOBS_LOCK:
                    started_ts = float(BACKUP_JOBS.get(job_id, {}).get("started_ts") or time.time())
                elapsed = max(0.0, time.time() - started_ts)
                eta_seconds = None
                if 0 < current_step < total_steps:
                    eta_seconds = int((elapsed / current_step) * (total_steps - current_step))
                _set_backup_job(
                    job_id,
                    current_step=current_step,
                    total_steps=total_steps,
                    progress=int((current_step / total_steps) * 100),
                    eta_seconds=eta_seconds,
                    estimated_end_time=_backup_estimated_end_time(eta_seconds),
                )

        success = not failures
        validation = {
            "status": "ok" if success else "failed",
            "checked_items": total_steps,
            "failed_items": len(failures),
            "message": "Robocopy completed without critical errors." if success else "Robocopy reported critical errors.",
        }
        _set_backup_job(
            job_id,
            status="completed" if success else "failed",
            summary="Backup completed" if success else "Backup completed with errors",
            message="Backup finished.",
            failures=failures,
            validation=validation,
            progress=100,
            eta_seconds=0,
            estimated_end_time=None,
            end_time=utc_now(),
        )
    except Exception as exc:
        friendly = friendly_error_message(str(exc), f"backup de {source_host} para {destination_host}")
        _append_backup_log(job_id, f"\n\nERROR: {exc}\n")
        _set_backup_job(job_id, status="failed", summary="Backup failed", message=friendly, eta_seconds=0, estimated_end_time=None, end_time=utc_now())
    finally:
        if renewal_stop_event:
            renewal_stop_event.set()
        if renewal_thread:
            renewal_thread.join(timeout=2)

        if source_share_ready:
            _disconnect_share(source_host, source_share)
            try:
                run_temporary_share_action(source_host, "remove", BACKUP_TEMPORARY_SHARE_TTL_MINUTES)
                _append_backup_log(job_id, "\nTemporary source share removed.\n")
            except Exception as exc:
                _append_backup_log(job_id, f"\nWARNING: Failed to remove temporary source share: {exc}\n")
        if destination_share_ready:
            _disconnect_share(destination_host, destination_share)
            try:
                run_temporary_share_action(destination_host, "remove", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, destination_drive)
                _append_backup_log(job_id, "Temporary destination share removed.\n")
            except Exception as exc:
                _append_backup_log(job_id, f"\nWARNING: Failed to remove temporary destination share: {exc}\n")

        with BACKUP_JOBS_LOCK:
            job = dict(BACKUP_JOBS.get(job_id) or {})
        if job:
            _persist_backup_job(job)


def _run_custom_folder_backup_job(
    job_id: str,
    source_host: str,
    destination_host: str,
    source_path: str,
    destination_path: str,
    access_identity: str,
    exclude_patterns: list[str],
    smb_username: str = "",
    smb_password: str = "",
) -> None:
    source_drive, source_relative = _normalize_absolute_windows_path(source_path, "Source path")
    destination_drive, destination_relative = _normalize_absolute_windows_path(destination_path, "Destination path")
    source_share = _temporary_share_name(source_drive)
    destination_share = _temporary_share_name(destination_drive)
    source_share_ready = False
    destination_share_ready = False
    renewal_stop_event: threading.Event | None = None
    renewal_thread: threading.Thread | None = None

    try:
        _append_backup_log(job_id, f"Using WMT Windows identity for custom folder backup: {access_identity}\n")
        _set_backup_job(job_id, status="running", message="Creating temporary source share...", current_step=0, total_steps=1, progress=5)
        try:
            share_result = run_temporary_share_action(source_host, "create", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, source_drive)
            source_share_ready = True
            source_share = share_result.get("ShareName") or _temporary_share_name(source_drive)
            _append_backup_log(job_id, f"Temporary source share ready: \\\\{source_host}\\{source_share}\n")
        except Exception as exc:
            source_share = f"{source_drive}$"
            _append_backup_log(job_id, f"Temporary source share unavailable, falling back to \\\\{source_host}\\{source_share}: {exc}\n")

        _set_backup_job(job_id, message="Creating temporary destination share...", progress=12)
        try:
            share_result = run_temporary_share_action(destination_host, "create", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, destination_drive)
            destination_share_ready = True
            destination_share = share_result.get("ShareName") or _temporary_share_name(destination_drive)
            _append_backup_log(job_id, f"Temporary destination share ready: \\\\{destination_host}\\{destination_share}\n")
        except Exception as exc:
            destination_share = f"{destination_drive}$"
            _append_backup_log(job_id, f"Temporary destination share unavailable, falling back to \\\\{destination_host}\\{destination_share}: {exc}\n")

        renewal_targets: list[tuple[str, str]] = []
        if source_share_ready:
            renewal_targets.append((source_host, source_drive))
        if destination_share_ready:
            renewal_targets.append((destination_host, destination_drive))
        renewal_stop_event, renewal_thread = _start_backup_share_renewal(job_id, renewal_targets)

        source_unc = f"\\\\{source_host}\\{source_share}"
        if source_relative:
            source_unc = f"{source_unc}\\{source_relative}"
        destination_unc = f"\\\\{destination_host}\\{destination_share}"
        if destination_relative:
            destination_unc = f"{destination_unc}\\{destination_relative}"

        _set_backup_job(job_id, message="Connecting to source and destination...", progress=18)
        connect_src = _connect_share(source_host, source_share, smb_username, smb_password)
        connect_dst = _connect_share(destination_host, destination_share, smb_username, smb_password)
        if not connect_src["success"] or not connect_dst["success"]:
            details = []
            if not connect_src["success"]:
                details.append(f"source: {connect_src['stderr'] or connect_src['stdout']}")
            if not connect_dst["success"]:
                details.append(f"destination: {connect_dst['stderr'] or connect_dst['stdout']}")
            message = "Failed to connect to custom backup shares. " + " | ".join(details)
            _set_backup_job(job_id, status="failed", message=message, summary="Custom folder backup failed", failures=details, end_time=utc_now(), eta_seconds=0, estimated_end_time=None)
            return

        _set_backup_job(job_id, message="Preparing destination folder...", progress=20)
        try:
            _ensure_remote_directory(destination_host, destination_drive, destination_relative)
            _append_backup_log(job_id, f"Destination folder prepared: {destination_unc}\n")
        except Exception as exc:
            message = f"Destination folder could not be prepared: {destination_unc}. {exc}"
            _append_backup_log(job_id, f"{message}\n")
            _set_backup_job(
                job_id,
                status="failed",
                message=message,
                summary="Custom folder backup failed",
                failures=[message],
                end_time=utc_now(),
                eta_seconds=0,
                estimated_end_time=None,
            )
            return

        if not _unc_path_exists(source_unc):
            message = f"Source folder is not accessible: {source_unc}"
            _set_backup_job(job_id, status="failed", message=message, summary="Custom folder backup failed", failures=[message], end_time=utc_now(), eta_seconds=0, estimated_end_time=None)
            return

        can_write_destination, write_detail = _unc_write_test(destination_unc)
        if not can_write_destination:
            message = f"Destination folder is not writable: {destination_unc}. {write_detail}"
            _set_backup_job(job_id, status="failed", message=message, summary="Custom folder backup failed", failures=[message], end_time=utc_now(), eta_seconds=0, estimated_end_time=None)
            return

        estimated_bytes, estimate_timed_out = _unc_folder_size_bytes(source_unc, timeout_seconds=30)
        estimated_size = _format_bytes(estimated_bytes)
        if estimate_timed_out:
            _append_backup_log(job_id, "WARNING: Source size estimation timed out; continuing backup.\n")
        else:
            _append_backup_log(job_id, f"Estimated source size: {estimated_size}\n")

        if _is_backup_job_cancelled(job_id):
            _set_backup_job(job_id, status="canceled", message="Backup cancelled by user.", summary="Custom folder backup cancelled", end_time=utc_now(), eta_seconds=0, estimated_end_time=None)
            return

        _set_backup_job(job_id, message="Copying custom folder...", progress=25, current_step=0, total_steps=1, size=estimated_size)
        robocopy_command = ["robocopy", source_unc, destination_unc, "/E", "/COPY:DAT", "/XJ", "/R:0", "/W:0"]
        if exclude_patterns:
            robocopy_command.extend(["/XF", *exclude_patterns])
        _append_backup_log(job_id, f"\nROBOCOPY source: {source_unc}\nROBOCOPY dest: {destination_unc}\n")
        if exclude_patterns:
            _append_backup_log(job_id, f"ROBOCOPY excluded files: {', '.join(exclude_patterns)}\n")
        started = time.perf_counter()
        result = _run_robocopy_monitored(job_id, robocopy_command, "Copying custom folder...")
        duration_ms = int((time.perf_counter() - started) * 1000)
        _append_backup_log(job_id, "\n===== Custom folder backup =====\n")
        _append_backup_log(job_id, result.stdout or "")
        if result.stderr:
            _append_backup_log(job_id, result.stderr)

        if _is_backup_job_cancelled(job_id):
            _set_backup_job(job_id, status="canceled", message="Backup cancelled by user.", summary="Custom folder backup cancelled", end_time=utc_now(), eta_seconds=0, estimated_end_time=None)
            return

        if result.returncode > 7:
            detail = _robocopy_failure_detail(result.stdout, result.stderr)
            message = f"Custom folder backup failed with robocopy exit code {result.returncode}"
            if detail:
                message = f"{message}: {detail}"
            _set_backup_job(
                job_id,
                status="failed",
                message=message,
                summary="Custom folder backup failed",
                failures=[message],
                validation={"status": "failed", "checked_items": 1, "failed_items": 1, "message": "Robocopy reported critical errors."},
                progress=100,
                current_step=1,
                total_steps=1,
                end_time=utc_now(),
                eta_seconds=0,
                estimated_end_time=None,
            )
            return

        copied_bytes, copied_timeout = _unc_folder_size_bytes(destination_unc, timeout_seconds=30)
        copied_size = estimated_size if copied_timeout else _format_bytes(copied_bytes)
        _set_backup_job(
            job_id,
            status="completed",
            summary="Custom folder backup completed",
            message=f"Custom folder backup finished in {duration_ms // 1000}s.",
            size=copied_size,
            validation={
                "status": "ok",
                "checked_items": 1,
                "failed_items": 0,
                "message": "Robocopy completed without critical errors.",
            },
            progress=100,
            current_step=1,
            total_steps=1,
            eta_seconds=0,
            estimated_end_time=None,
            end_time=utc_now(),
        )
    except Exception as exc:
        friendly = friendly_error_message(str(exc), f"custom folder backup de {source_host} para {destination_host}")
        _append_backup_log(job_id, f"\n\nERROR: {exc}\n")
        _set_backup_job(job_id, status="failed", summary="Custom folder backup failed", message=friendly, eta_seconds=0, estimated_end_time=None, end_time=utc_now())
    finally:
        if renewal_stop_event:
            renewal_stop_event.set()
        if renewal_thread:
            renewal_thread.join(timeout=2)
        _disconnect_share(source_host, source_share)
        _disconnect_share(destination_host, destination_share)
        if source_share_ready:
            try:
                run_temporary_share_action(source_host, "remove", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, source_drive)
                _append_backup_log(job_id, "\nTemporary source share removed.\n")
            except Exception as exc:
                _append_backup_log(job_id, f"\nWARNING: Failed to remove temporary source share: {exc}\n")
        if destination_share_ready:
            try:
                run_temporary_share_action(destination_host, "remove", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, destination_drive)
                _append_backup_log(job_id, "Temporary destination share removed.\n")
            except Exception as exc:
                _append_backup_log(job_id, f"\nWARNING: Failed to remove temporary destination share: {exc}\n")
        with BACKUP_JOBS_LOCK:
            job = dict(BACKUP_JOBS.get(job_id) or {})
        if job:
            _persist_backup_job(job)


def _find_backup_job_snapshot(job_id: str) -> dict:
    with BACKUP_JOBS_LOCK:
        job = BACKUP_JOBS.get(job_id)
        if job:
            return _public_backup_job(job)
    state = load_state()
    job = next((item for item in state.get("backup_jobs", []) if item.get("id") == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Backup job not found")
    return _public_backup_job(job)
