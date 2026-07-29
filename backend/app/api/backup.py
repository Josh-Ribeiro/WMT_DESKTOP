from __future__ import annotations

import datetime
import concurrent.futures
import subprocess
import threading
import time
from typing import Literal
from uuid import uuid4
from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi import APIRouter

from ..core.config import (
    BACKUP_CHECKLIST_ITEMS,
    BACKUP_EXCLUDED_FILE_PATTERNS,
    BACKUP_FOLDERS,
    BACKUP_TEMPORARY_SHARE_TTL_MINUTES,
    MAX_CONCURRENT_BACKUP_JOBS,
    TEMPORARY_C_SHARE_NAME,
)
from ..core.security import utc_now
from ..core.validators import (
    _temporary_share_name,
    validate_backup_host,
)
from ..repositories.state import (
    audit,
    current_settings,
    load_state,
    mutate_state,
    script_enabled,
)
from ..schemas import (
    BackupChecklistRequest,
    BackupCreateRequest,
    BackupCustomFolderRequest,
    BackupOpenDestinationRequest,
    BackupPrecheckRequest,
    BackupRetentionRequest,
    BackupRetryFolderRequest,
    BackupUsersRequest,
)
from ..services.auth import require_role
from ..services.backup import (
    BACKUP_JOBS,
    BACKUP_JOBS_LOCK,
    _build_destination_base_path,
    _build_destination_path,
    _build_source_path,
    _build_temporary_destination_browse_path,
    _connect_share,
    _disconnect_share,
    _ensure_remote_directory,
    _find_backup_job_snapshot,
    _format_bytes,
    _get_users_remote,
    _list_users_from_share,
    _normalize_absolute_windows_path,
    _normalize_destination_root,
    _persist_backup_job,
    _public_backup_job,
    _remote_drive_exists,
    _remote_drive_free_bytes,
    _require_windows_backup_identity,
    _resolve_backup_smb_credentials,
    _run_backup_job,
    _run_custom_folder_backup_job,
    _safe_robocopy_exclude_patterns,
    _unc_folder_size_bytes,
    _unc_path_exists,
    _unc_write_test,
    run_temporary_share_action,
)

router = APIRouter()


def _ensure_backup_capacity(*, exclude_job_id: str | None = None) -> None:
    active_count = sum(
        1
        for job_id, job in BACKUP_JOBS.items()
        if job_id != exclude_job_id and job.get("status") in {"queued", "running"}
    )
    if active_count >= MAX_CONCURRENT_BACKUP_JOBS:
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {MAX_CONCURRENT_BACKUP_JOBS} backups simultâneos atingido.",
            headers={"Retry-After": "60"},
        )


@router.get("/api/backup/jobs")
def backup_jobs(
    page: int = Query(default=1, ge=1, le=10000),
    page_size: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(require_role("admin", "operator")),
):
    state = load_state()
    persisted_jobs = state.get("backup_jobs", [])
    with BACKUP_JOBS_LOCK:
        runtime_jobs = [_public_backup_job(item) for item in BACKUP_JOBS.values()]
    runtime_ids = {item.get("id") for item in runtime_jobs}
    jobs = runtime_jobs + [item for item in persisted_jobs if item.get("id") not in runtime_ids]
    total_size_gb = 0
    for job in jobs:
        if job.get("size", "").endswith(" GB"):
            try:
                total_size_gb += int(job["size"].split(" ", 1)[0])
            except ValueError:
                pass
    completed = sum(1 for job in jobs if job["status"] == "completed")
    success_rate = round((completed / len(jobs)) * 100, 1) if jobs else 0
    start = (page - 1) * page_size
    return {
        "jobs": jobs[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "has_next": start + page_size < len(jobs),
        "summary": {
            "total": len(jobs),
            "total_size": f"{total_size_gb} GB",
            "success_rate": success_rate,
        },
    }


@router.post("/api/backup/users")
def backup_users(request: BackupUsersRequest, user: dict = Depends(require_role("admin", "operator"))):
    access_identity = _require_windows_backup_identity(user)
    smb_username, smb_password = _resolve_backup_smb_credentials(request.remote_user, request.remote_pass)
    source = validate_backup_host(request.source)
    try:
        users = _get_users_remote(source, smb_username, smb_password)
    except Exception as exc:
        audit("backup.load_users_failed", user["username"], {"source": source, "credential_user": access_identity, "smb_user": smb_username, "error": str(exc)})
        raise HTTPException(
            status_code=502,
            detail=f"Nao foi possivel carregar os perfis de {source} com a identidade Windows do WMT ({access_identity}): {exc}",
        )
    audit("backup.load_users", user["username"], {"source": source, "count": len(users), "credential_user": access_identity, "smb_user": smb_username})
    return {
        "users": users,
        "count": len(users),
        "warning": "" if users else "No user profiles were found on the source workstation.",
    }


@router.post("/api/backup/open-destination")
def backup_open_destination(request: BackupOpenDestinationRequest, user: dict = Depends(require_role("admin", "operator"))):
    access_identity = _require_windows_backup_identity(user)
    smb_username, smb_password = _resolve_backup_smb_credentials(request.remote_user, request.remote_pass)
    destination = validate_backup_host(request.destination)
    destination_root = _normalize_destination_root(request.destination_path)
    if destination_root:
        drive, relative = destination_root
    else:
        drive, relative = "C", "Users"

    try:
        if destination_root and request.create_if_missing:
            _ensure_remote_directory(destination, drive, relative)
        share_result = run_temporary_share_action(destination, "create", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, drive)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Nao foi possivel preparar o destino com a identidade Windows do WMT ({access_identity}): {exc}",
        )

    share_name = share_result.get("ShareName") or _temporary_share_name(drive)
    path = _build_temporary_destination_browse_path(destination, drive, relative)
    connect = _connect_share(destination, share_name, smb_username, smb_password)
    if not connect["success"]:
        raise HTTPException(
            status_code=502,
            detail=f"Nao foi possivel acessar o destino com a identidade Windows do WMT ({access_identity}): {connect['stderr'] or connect['stdout']}",
        )
    _disconnect_share(destination, share_name)
    audit(
        "backup.open_destination",
        user["username"],
        {
            "destination": destination,
            "path": path,
            "credential_user": access_identity,
            "smb_user": smb_username,
            "share": share_name,
            "cleanup_task": share_result.get("CleanupTaskName") or "",
        },
    )
    return {
        "ok": True,
        "path": path,
        "message": f"Destination path is available for up to {BACKUP_TEMPORARY_SHARE_TTL_MINUTES} minutes: {path}",
    }


@router.post("/api/backup/precheck")
def backup_precheck(request: BackupPrecheckRequest, user: dict = Depends(require_role("admin", "operator"))):
    access_identity = _require_windows_backup_identity(user)
    smb_username, smb_password = _resolve_backup_smb_credentials(request.remote_user, request.remote_pass)
    source = validate_backup_host(request.source)
    destination = validate_backup_host(request.destination)
    selected_users = [item.strip() for item in request.users if item.strip()]
    if not selected_users:
        raise HTTPException(status_code=400, detail="Select at least one user")

    destination_path = request.destination_path or str(current_settings().get("backup_default_destination_path") or "")
    destination_root = _normalize_destination_root(destination_path)
    destination_drive = destination_root[0] if destination_root else "C"
    destination_relative = destination_root[1] if destination_root else "Users"

    checks: list[dict[str, str]] = []
    warnings: list[str] = []
    errors: list[str] = []
    source_share = TEMPORARY_C_SHARE_NAME
    destination_share = _temporary_share_name(destination_drive)
    source_share_created = False
    destination_share_created = False
    source_share_owned = False
    destination_share_owned = False
    estimated_bytes = 0
    estimate_incomplete = False
    missing_folders: list[str] = []
    source_folders_checked = False

    def add_check(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})
        if status == "blocked":
            errors.append(message)
        elif status == "warning":
            warnings.append(message)

    if request.quick:
        def ping_target(host: str) -> tuple[bool, str]:
            try:
                result = subprocess.run(["ping", "-n", "1", "-w", "900", host], capture_output=True, text=True, timeout=3)
                return result.returncode == 0, host
            except Exception as exc:
                return False, str(exc)

        def prepare_destination() -> tuple[bool, str]:
            try:
                if destination_root:
                    _ensure_remote_directory(destination, destination_drive, destination_relative)
                    return True, f"{destination_drive}:\\{destination_relative} is available"
                return True, f"Default destination C:\\Users selected on {destination}"
            except Exception as exc:
                return False, str(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            source_ping_future = executor.submit(ping_target, source)
            destination_ping_future = executor.submit(ping_target, destination)
            destination_space_future = executor.submit(_remote_drive_free_bytes, destination, destination_drive)
            destination_access_future = executor.submit(prepare_destination)

            source_online, source_detail = source_ping_future.result()
            destination_online, destination_detail = destination_ping_future.result()
            add_check("Source online", "ok" if source_online else "blocked", f"{source} responded" if source_online else f"{source} did not respond: {source_detail}")
            add_check("Destination online", "ok" if destination_online else "blocked", f"{destination} responded" if destination_online else f"{destination} did not respond: {destination_detail}")
            add_check("Selected profiles", "ok", f"{len(selected_users)} profile(s) already selected in the previous step")

            try:
                free_bytes = destination_space_future.result()
                add_check("Destination free space", "ok", f"Free on {destination_drive}: {_format_bytes(free_bytes)}")
            except Exception as exc:
                add_check("Destination free space", "blocked", f"Could not query free space on {destination_drive}: {exc}")

            destination_access, destination_access_detail = destination_access_future.result()
            add_check(
                "Destination access",
                "ok" if destination_access else "blocked",
                destination_access_detail if destination_access else f"Could not prepare destination: {destination_access_detail}",
            )

        status = "blocked" if errors else "warning" if warnings else "ok"
        audit(
            "backup.precheck",
            user["username"],
            {
                "source": source,
                "destination": destination,
                "users": selected_users,
                "destination_path": destination_path or "",
                "status": status,
                "quick": True,
                "credential_user": access_identity,
                "smb_user": smb_username,
            },
        )
        return {
            "status": status,
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
            "estimated_bytes": 0,
            "estimated_size": "Quick validation",
            "message": "Quick pre-check blocked the migration." if status == "blocked" else "Quick pre-check completed.",
            "quick": True,
        }

    try:
        source_ping = subprocess.run(["ping", "-n", "1", "-w", "1200", source], capture_output=True, text=True, timeout=4)
        add_check("Source online", "ok" if source_ping.returncode == 0 else "blocked", f"{source} {'responded' if source_ping.returncode == 0 else 'did not respond'}")

        destination_ping = subprocess.run(["ping", "-n", "1", "-w", "1200", destination], capture_output=True, text=True, timeout=4)
        add_check("Destination online", "ok" if destination_ping.returncode == 0 else "blocked", f"{destination} {'responded' if destination_ping.returncode == 0 else 'did not respond'}")

        try:
            source_result = run_temporary_share_action(source, "create", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, "C")
            source_share_created = True
            source_share_owned = not bool(source_result.get("AlreadyExisted"))
            source_share = source_result.get("ShareName") or TEMPORARY_C_SHARE_NAME
            add_check("Source temporary share", "ok", f"Available: \\\\{source}\\{source_share}")
        except Exception as exc:
            source_share = "C$"
            add_check("Source temporary share", "blocked", f"Could not create source temporary share: {exc}")

        try:
            if not _remote_drive_exists(destination, destination_drive):
                raise RuntimeError(f"Drive {destination_drive}: does not exist on {destination}")
            if destination_root:
                _ensure_remote_directory(destination, destination_drive, destination_relative)
            destination_result = run_temporary_share_action(destination, "create", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, destination_drive)
            destination_share_created = True
            destination_share_owned = not bool(destination_result.get("AlreadyExisted"))
            destination_share = destination_result.get("ShareName") or _temporary_share_name(destination_drive)
            add_check("Destination temporary share", "ok", f"Available: \\\\{destination}\\{destination_share}")
            destination_base = _build_destination_base_path(destination, destination_path, destination_share)
            connect_destination = _connect_share(destination, destination_share, smb_username, smb_password)
            if not connect_destination["success"]:
                add_check(
                    "Destination write access",
                    "blocked",
                    f"Could not connect to {destination_base}: {connect_destination['stderr'] or connect_destination['stdout']}",
                )
            else:
                try:
                    can_write_destination, write_detail = _unc_write_test(destination_base)
                    add_check(
                        "Destination write access",
                        "ok" if can_write_destination else "blocked",
                        f"Writable: {destination_base}" if can_write_destination else f"Cannot write to {destination_base}: {write_detail}",
                    )
                finally:
                    _disconnect_share(destination, destination_share)
        except Exception as exc:
            add_check("Destination temporary share", "blocked", f"Could not prepare destination temporary share: {exc}")

        if source_share_created:
            available_profiles = set(_list_users_from_share(source, source_share, smb_username, smb_password))
            missing_profiles = [profile for profile in selected_users if profile not in available_profiles]
            add_check(
                "Selected profiles",
                "blocked" if missing_profiles else "ok",
                f"Missing profiles: {', '.join(missing_profiles)}" if missing_profiles else f"{len(selected_users)} selected profile(s) found",
            )

            if request.quick:
                add_check("Source folders", "ok", "Selected profiles are reachable (quick validation)")
                add_check("Size estimate", "warning", "Deep folder size scan skipped in quick mode")
                estimate_incomplete = True
                source_folders_checked = True
            else:
                connect_source = _connect_share(source, source_share, smb_username, smb_password)
                if not connect_source["success"]:
                    add_check("Source folders", "warning", f"Could not reconnect to source for size estimate: {connect_source['stderr'] or connect_source['stdout']}")
                    estimate_incomplete = True
                    source_folders_checked = True
                else:
                    try:
                        for profile in selected_users:
                            for folder in BACKUP_FOLDERS:
                                path = _build_source_path(source, profile, folder, source_share)
                                if not _unc_path_exists(path):
                                    missing_folders.append(f"{profile}/{folder}")
                                    continue
                                try:
                                    folder_size, timed_out = _unc_folder_size_bytes(path, timeout_seconds=20)
                                    estimated_bytes += folder_size
                                    estimate_incomplete = estimate_incomplete or timed_out
                                except Exception:
                                    estimate_incomplete = True
                    finally:
                        _disconnect_share(source, source_share)

            if not source_folders_checked:
                if missing_folders:
                    add_check("Source folders", "warning", f"Missing or inaccessible folders: {', '.join(missing_folders[:8])}")
                else:
                    add_check("Source folders", "ok", "All selected profile folders are reachable")
            if request.quick:
                pass
            elif estimate_incomplete:
                add_check("Size estimate", "warning", f"Estimated at least {_format_bytes(estimated_bytes)}; some folders could not be fully measured")
            else:
                add_check("Size estimate", "ok", f"Estimated source data: {_format_bytes(estimated_bytes)}")

        try:
            free_bytes = _remote_drive_free_bytes(destination, destination_drive)
            if estimated_bytes and free_bytes < estimated_bytes:
                add_check("Destination free space", "blocked", f"Free: {_format_bytes(free_bytes)}; estimated needed: {_format_bytes(estimated_bytes)}")
            elif estimated_bytes and free_bytes < int(estimated_bytes * 1.1):
                add_check("Destination free space", "warning", f"Free: {_format_bytes(free_bytes)}; estimated needed: {_format_bytes(estimated_bytes)}")
            else:
                add_check("Destination free space", "ok", f"Free on {destination_drive}: {_format_bytes(free_bytes)}")
        except Exception as exc:
            free_space_status = "blocked" if "not found" in str(exc).lower() else "warning"
            add_check("Destination free space", free_space_status, f"Could not query free space on {destination_drive}: {exc}")

        status = "blocked" if errors else "warning" if warnings else "ok"
        audit(
            "backup.precheck",
            user["username"],
            {
                "source": source,
                "destination": destination,
                "users": selected_users,
                "destination_path": destination_path or "",
                "status": status,
                "quick": request.quick,
                "credential_user": access_identity,
                "smb_user": smb_username,
            },
        )
        return {
            "status": status,
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
            "estimated_bytes": estimated_bytes,
            "estimated_size": _format_bytes(estimated_bytes),
            "quick": request.quick,
            "message": "Pre-check blocked the backup." if status == "blocked" else "Pre-check completed with warnings." if status == "warning" else "Pre-check passed.",
        }
    finally:
        if source_share_created and source_share_owned:
            try:
                _disconnect_share(source, source_share)
                run_temporary_share_action(source, "remove", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, "C")
            except Exception:
                pass
        if destination_share_created and destination_share_owned:
            try:
                _disconnect_share(destination, destination_share)
                run_temporary_share_action(destination, "remove", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, destination_drive)
            except Exception:
                pass


@router.post("/api/backup/jobs")
def create_backup_job(request: BackupCreateRequest, user: dict = Depends(require_role("admin", "operator"))):
    if not script_enabled("backup"):
        raise HTTPException(status_code=403, detail="Backups estão desabilitados nas configurações do WMT.")
    access_identity = _require_windows_backup_identity(user)
    smb_username, smb_password = _resolve_backup_smb_credentials(request.remote_user, request.remote_pass)
    source = validate_backup_host(request.source)
    destination = validate_backup_host(request.destination)
    selected_users = [item.strip() for item in request.users if item.strip()]
    if not selected_users:
        raise HTTPException(status_code=400, detail="Select at least one user")
    destination_path = request.destination_path or str(current_settings().get("backup_default_destination_path") or "")
    _normalize_destination_root(destination_path)
    exclude_patterns = _safe_robocopy_exclude_patterns(request.exclude_patterns) or BACKUP_EXCLUDED_FILE_PATTERNS

    job_id = f"BK-{uuid4().hex[:8].upper()}"
    job = {
        "id": job_id,
        "source": source,
        "destination": destination,
        "users": selected_users,
        "status": "running",
        "start_time": utc_now(),
        "end_time": "-",
        "size": "0 GB",
        "progress": 0,
        "current_step": 0,
        "total_steps": max(1, len(selected_users) * len(BACKUP_FOLDERS)),
        "message": "Backup job started.",
        "summary": "",
        "failures": [],
        "log": "",
        "eta_seconds": None,
        "estimated_end_time": None,
        "cancel_requested": False,
        "started_ts": time.time(),
        "checklist": {},
        "backup_type": "profiles",
        "destination_path": destination_path or "",
        "source_path": "",
        "exclude_patterns": exclude_patterns,
    }
    with BACKUP_JOBS_LOCK:
        _ensure_backup_capacity()
        BACKUP_JOBS[job_id] = job

    thread = threading.Thread(
        target=_run_backup_job,
        args=(job_id, source, destination, selected_users, access_identity, destination_path, smb_username, smb_password, BACKUP_FOLDERS, exclude_patterns),
        daemon=True,
    )
    thread.start()
    audit(
        "backup.create",
        user["username"],
        {
            "job_id": job_id,
            "source": source,
            "destination": destination,
            "users_count": len(selected_users),
            "destination_path": destination_path or "",
            "credential_user": access_identity,
            "smb_user": smb_username,
        },
    )
    return _public_backup_job(job)


@router.post("/api/backup/simulate")
def simulate_backup(request: BackupPrecheckRequest, user: dict = Depends(require_role("admin", "operator"))):
    access_identity = _require_windows_backup_identity(user)
    smb_username, smb_password = _resolve_backup_smb_credentials(request.remote_user, request.remote_pass)
    source = validate_backup_host(request.source)
    destination = validate_backup_host(request.destination)
    selected_users = [item.strip() for item in request.users if item.strip()]
    if not selected_users:
        raise HTTPException(status_code=400, detail="Select at least one user")
    destination_path = request.destination_path or str(current_settings().get("backup_default_destination_path") or "")
    destination_root = _normalize_destination_root(destination_path)
    destination_drive = destination_root[0] if destination_root else "C"
    exclude_patterns = _safe_robocopy_exclude_patterns(request.exclude_patterns) or BACKUP_EXCLUDED_FILE_PATTERNS
    source_share = TEMPORARY_C_SHARE_NAME
    destination_share = _temporary_share_name(destination_drive)
    source_share_created = False
    destination_share_created = False
    log_parts: list[str] = [f"Simulation using WMT Windows identity: {access_identity}"]
    planned_items = 0

    try:
        try:
            source_result = run_temporary_share_action(source, "create", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, "C")
            source_share_created = True
            source_share = source_result.get("ShareName") or TEMPORARY_C_SHARE_NAME
        except Exception as exc:
            source_share = "C$"
            log_parts.append(f"Source temporary share unavailable, using {source_share}: {exc}")

        try:
            destination_result = run_temporary_share_action(destination, "create", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, destination_drive)
            destination_share_created = True
            destination_share = destination_result.get("ShareName") or _temporary_share_name(destination_drive)
        except Exception as exc:
            destination_share = f"{destination_drive}$"
            log_parts.append(f"Destination temporary share unavailable, using {destination_share}: {exc}")

        connect_src = _connect_share(source, source_share, smb_username, smb_password)
        connect_dst = _connect_share(destination, destination_share, smb_username, smb_password)
        if not connect_src["success"] or not connect_dst["success"]:
            raise HTTPException(status_code=502, detail="Could not connect to source/destination shares for simulation")

        for profile in selected_users:
            for folder in BACKUP_FOLDERS:
                source_path = _build_source_path(source, profile, folder, source_share)
                _, destination_folder = _build_destination_path(destination, profile, folder, destination_path, destination_share)
                command = ["robocopy", source_path, destination_folder, "/E", "/COPY:DAT", "/XJ", "/R:0", "/W:0", "/L"]
                if exclude_patterns:
                    command.extend(["/XF", *exclude_patterns])
                result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
                planned_items += 1
                log_parts.append(f"\n===== SIMULATION {profile} - {folder} =====")
                log_parts.append(f"ROBOCOPY source: {source_path}")
                log_parts.append(f"ROBOCOPY dest: {destination_folder}")
                log_parts.append(result.stdout or "")
                if result.stderr:
                    log_parts.append(result.stderr)

        audit("backup.simulate", user["username"], {"source": source, "destination": destination, "users": selected_users, "destination_path": destination_path or ""})
        return {
            "ok": True,
            "planned_items": planned_items,
            "exclude_patterns": exclude_patterns,
            "message": f"Simulation completed for {planned_items} folder(s). No files were copied.",
            "log": "\n".join(log_parts)[-20000:],
        }
    finally:
        _disconnect_share(source, source_share)
        _disconnect_share(destination, destination_share)
        if source_share_created:
            try:
                run_temporary_share_action(source, "remove", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, "C")
            except Exception:
                pass
        if destination_share_created:
            try:
                run_temporary_share_action(destination, "remove", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, destination_drive)
            except Exception:
                pass


@router.post("/api/backup/custom-folder/jobs")
def create_custom_folder_backup_job(request: BackupCustomFolderRequest, user: dict = Depends(require_role("admin", "operator"))):
    if not script_enabled("backup"):
        raise HTTPException(status_code=403, detail="Backups estao desabilitados nas configuracoes do WMT.")
    access_identity = _require_windows_backup_identity(user)
    smb_username, smb_password = _resolve_backup_smb_credentials(request.remote_user, request.remote_pass)
    source = validate_backup_host(request.source)
    destination = validate_backup_host(request.destination)
    source_drive, source_relative = _normalize_absolute_windows_path(request.source_path, "Source path")
    destination_drive, destination_relative = _normalize_absolute_windows_path(request.destination_path, "Destination path")
    if not source_relative:
        raise HTTPException(status_code=400, detail="Source path must include a folder, not only a drive root.")
    if not destination_relative:
        raise HTTPException(status_code=400, detail="Destination path must include a folder, not only a drive root.")
    exclude_patterns = _safe_robocopy_exclude_patterns(request.exclude_patterns)

    job_id = f"BK-{uuid4().hex[:8].upper()}"
    job = {
        "id": job_id,
        "source": f"{source}:{source_drive}\\{source_relative}",
        "destination": f"{destination}:{destination_drive}\\{destination_relative}",
        "users": ["Custom folder"],
        "status": "running",
        "start_time": utc_now(),
        "end_time": "-",
        "size": "0 GB",
        "progress": 0,
        "current_step": 0,
        "total_steps": 1,
        "message": "Custom folder backup job started.",
        "summary": "",
        "failures": [],
        "log": "",
        "eta_seconds": None,
        "estimated_end_time": None,
        "cancel_requested": False,
        "started_ts": time.time(),
        "backup_type": "custom-folder",
        "checklist": {},
        "source_path": request.source_path,
        "destination_path": request.destination_path,
        "exclude_patterns": exclude_patterns,
    }
    with BACKUP_JOBS_LOCK:
        _ensure_backup_capacity()
        BACKUP_JOBS[job_id] = job

    thread = threading.Thread(
        target=_run_custom_folder_backup_job,
        args=(job_id, source, destination, request.source_path, request.destination_path, access_identity, exclude_patterns, smb_username, smb_password),
        daemon=True,
    )
    thread.start()
    audit(
        "backup.custom_folder.create",
        user["username"],
        {
            "job_id": job_id,
            "source": source,
            "destination": destination,
            "source_path": request.source_path,
            "destination_path": request.destination_path,
            "exclude_patterns": exclude_patterns,
            "credential_user": access_identity,
        },
    )
    return _public_backup_job(job)


@router.get("/api/backup/jobs/{job_id}")
def backup_job_progress(job_id: str, user: dict = Depends(require_role("admin", "operator"))):
    with BACKUP_JOBS_LOCK:
        job = BACKUP_JOBS.get(job_id)
        if job:
            return _public_backup_job(job)

    state = load_state()
    persisted = next((item for item in state.get("backup_jobs", []) if item.get("id") == job_id), None)
    if not persisted:
        raise HTTPException(status_code=404, detail="Backup job not found")
    return persisted


@router.put("/api/backup/jobs/{job_id}/checklist")
def update_backup_checklist(job_id: str, request: BackupChecklistRequest, user: dict = Depends(require_role("admin", "operator"))):
    allowed = set(BACKUP_CHECKLIST_ITEMS)
    next_checklist = {key: bool(value) for key, value in request.checklist.items() if key in allowed}

    with BACKUP_JOBS_LOCK:
        job = BACKUP_JOBS.get(job_id)
        if job:
            job["checklist"] = next_checklist
            snapshot = _public_backup_job(job)
            _persist_backup_job(job)
            audit("backup.checklist", user["username"], {"job_id": job_id, "checked": [key for key, value in next_checklist.items() if value]})
            return snapshot

    def update_persisted(state: dict) -> dict:
        item = next(
            (
                candidate
                for candidate in state.get("backup_jobs", [])
                if candidate.get("id") == job_id
            ),
            None,
        )
        if not item:
            raise HTTPException(status_code=404, detail="Backup job not found")
        item["checklist"] = next_checklist
        return _public_backup_job(item)

    snapshot = mutate_state(update_persisted)
    audit("backup.checklist", user["username"], {"job_id": job_id, "checked": [key for key, value in next_checklist.items() if value]})
    return snapshot


@router.post("/api/backup/jobs/{job_id}/retry-folder")
def retry_backup_folder(job_id: str, request: BackupRetryFolderRequest, user: dict = Depends(require_role("admin", "operator"))):
    if not script_enabled("backup"):
        raise HTTPException(status_code=403, detail="Backups estao desabilitados nas configuracoes do WMT.")
    access_identity = _require_windows_backup_identity(user)
    original = _find_backup_job_snapshot(job_id)
    if original.get("backup_type") != "profiles":
        raise HTTPException(status_code=400, detail="Retry by folder is available only for profile backups.")
    profile = request.profile.strip()
    folder = request.folder.strip()
    if folder not in BACKUP_FOLDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported folder. Choose one of: {', '.join(BACKUP_FOLDERS)}")
    source = validate_backup_host(str(original.get("source") or ""))
    destination = validate_backup_host(str(original.get("destination") or ""))
    destination_path = str(original.get("destination_path") or "")
    exclude_patterns = _safe_robocopy_exclude_patterns(original.get("exclude_patterns") or []) or BACKUP_EXCLUDED_FILE_PATTERNS

    retry_id = f"BK-{uuid4().hex[:8].upper()}"
    job = {
        "id": retry_id,
        "source": source,
        "destination": destination,
        "users": [profile],
        "status": "running",
        "start_time": utc_now(),
        "end_time": "-",
        "size": "0 GB",
        "progress": 0,
        "current_step": 0,
        "total_steps": 1,
        "message": f"Retrying {profile}/{folder}.",
        "summary": "",
        "failures": [],
        "log": f"Retry requested from {job_id}: {profile}/{folder}\n",
        "eta_seconds": None,
        "estimated_end_time": None,
        "cancel_requested": False,
        "started_ts": time.time(),
        "checklist": {},
        "backup_type": "profiles",
        "destination_path": destination_path,
        "source_path": "",
        "exclude_patterns": exclude_patterns,
    }
    with BACKUP_JOBS_LOCK:
        _ensure_backup_capacity()
        BACKUP_JOBS[retry_id] = job
    thread = threading.Thread(
        target=_run_backup_job,
        args=(retry_id, source, destination, [profile], access_identity, destination_path, "", "", [folder], exclude_patterns),
        daemon=True,
    )
    thread.start()
    audit("backup.retry_folder", user["username"], {"source_job_id": job_id, "job_id": retry_id, "profile": profile, "folder": folder})
    return _public_backup_job(job)


@router.get("/api/backup/jobs/{job_id}/open-path")
def backup_job_open_path(job_id: str, kind: Literal["source", "destination"] = Query(default="destination"), user: dict = Depends(require_role("admin", "operator"))):
    job = _find_backup_job_snapshot(job_id)
    if job.get("backup_type") == "custom-folder":
        value = str(job.get("source_path" if kind == "source" else "destination_path") or "")
        host = str(job.get("source" if kind == "source" else "destination") or "").split(":")[0]
        drive, relative = _normalize_absolute_windows_path(value, "Path")
        share = f"{drive}$"
        path = f"\\\\{host}\\{share}"
        if relative:
            path = f"{path}\\{relative}"
    else:
        host = validate_backup_host(str(job.get("source" if kind == "source" else "destination") or ""))
        if kind == "source":
            path = f"\\\\{host}\\C$\\Users"
        else:
            destination_path = str(job.get("destination_path") or "")
            destination_root = _normalize_destination_root(destination_path)
            if destination_root:
                drive, relative = destination_root
                path = f"\\\\{host}\\{drive}$"
                if relative:
                    path = f"{path}\\{relative}"
            else:
                path = f"\\\\{host}\\C$\\Users"
    audit("backup.open_path", user["username"], {"job_id": job_id, "kind": kind, "path": path})
    return {"path": path, "message": f"{kind.title()} path ready."}


@router.post("/api/backup/jobs/{job_id}/cancel")
def cancel_backup_job(job_id: str, user: dict = Depends(require_role("admin", "operator"))):
    with BACKUP_JOBS_LOCK:
        job = BACKUP_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Backup job not found")
        if job.get("status") != "running":
            return _public_backup_job(job)
        job["cancel_requested"] = True
        job["message"] = "Cancelling backup..."
    audit("backup.cancel", user["username"], {"job_id": job_id})
    return _public_backup_job(job)


@router.delete("/api/backup/jobs/{job_id}")
def delete_backup_job(job_id: str, user: dict = Depends(require_role("admin", "operator"))):
    with BACKUP_JOBS_LOCK:
        removed_runtime = BACKUP_JOBS.pop(job_id, None) is not None

    def delete_persisted(state: dict) -> None:
        jobs = state.get("backup_jobs", [])
        next_jobs = [job for job in jobs if job["id"] != job_id]
        if len(next_jobs) == len(jobs) and not removed_runtime:
            raise HTTPException(status_code=404, detail="Backup job not found")
        state["backup_jobs"] = next_jobs

    mutate_state(delete_persisted)
    audit("backup.delete", user["username"], {"job_id": job_id})
    return {"ok": True}


@router.post("/api/backup/jobs/retention")
def apply_backup_retention(request: BackupRetentionRequest, user: dict = Depends(require_role("admin", "operator"))):
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=request.days)

    def job_date(item: dict) -> datetime.datetime:
        for key in ("end_time", "start_time"):
            value = str(item.get(key) or "").replace("Z", "")
            if not value or value == "-":
                continue
            try:
                return datetime.datetime.fromisoformat(value)
            except Exception:
                continue
        return datetime.datetime.min

    def apply_retention(state: dict) -> tuple[int, int]:
        jobs = sorted(
            state.get("backup_jobs", []),
            key=job_date,
            reverse=True,
        )
        kept: list[dict] = []
        removed: list[dict] = []
        for index, job in enumerate(jobs):
            status = str(job.get("status") or "")
            if (
                index < request.keep_last
                or status == "running"
                or job_date(job) >= cutoff
            ):
                kept.append(job)
            else:
                removed.append(job)
        state["backup_jobs"] = kept
        return len(removed), len(kept)

    removed_count, kept_count = mutate_state(apply_retention)
    audit("backup.retention", user["username"], {"days": request.days, "keep_last": request.keep_last, "removed": removed_count})
    return {"ok": True, "removed": removed_count, "kept": kept_count}


@router.post("/api/backup/jobs/{job_id}/download")
def prepare_backup_download(job_id: str, user: dict = Depends(require_role("admin", "operator"))):
    with BACKUP_JOBS_LOCK:
        job = BACKUP_JOBS.get(job_id)
    if not job:
        state = load_state()
        job = next((item for item in state.get("backup_jobs", []) if item["id"] == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Backup job not found")
    audit("backup.download", user["username"], {"job_id": job_id})
    return {"ok": True, "message": "Backup log is available in the job details."}
