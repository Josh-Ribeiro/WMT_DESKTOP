"""Windows path validation and UNC construction for backup operations."""

from __future__ import annotations

import re

from fastapi import HTTPException

from ..core.validators import _temporary_share_name


def normalize_destination_root(
    destination_path: str | None,
) -> tuple[str, str] | None:
    path = (destination_path or "").strip()
    if not path:
        return None
    normalized = path.replace("/", "\\")
    if not re.match(r"^[A-Za-z]:\\", normalized):
        raise HTTPException(
            status_code=400,
            detail="Custom destination path must be absolute, like D:\\Backup\\Migration",
        )
    return normalized[0].upper(), normalized[3:].strip("\\")


def normalize_absolute_windows_path(
    path: str,
    field_name: str,
) -> tuple[str, str]:
    normalized = str(path or "").strip().replace("/", "\\")
    if not re.match(r"^[A-Za-z]:\\", normalized):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be absolute, like D:\\Backup\\Folder",
        )
    return normalized[0].upper(), normalized[3:].strip("\\")


def build_unc_from_absolute_path(
    host: str,
    path: str,
    share_name: str | None = None,
) -> tuple[str, str, str]:
    drive, relative = normalize_absolute_windows_path(path, "Path")
    share = share_name or drive
    base = f"\\\\{host}\\{share}"
    return drive, relative, f"{base}\\{relative}" if relative else base


def safe_robocopy_exclude_patterns(patterns: list[str]) -> list[str]:
    safe: list[str] = []
    for item in patterns:
        pattern = str(item or "").strip()
        if not pattern or any(char in pattern for char in ['"', "'", "\r", "\n"]):
            continue
        safe.append(pattern)
    return safe[:25]


def build_source_path(
    host: str,
    user: str,
    folder: str,
    share_name: str = "C",
) -> str:
    return f"\\\\{host}\\{share_name}\\Users\\{user}\\{folder}"


def build_destination_path(
    host: str,
    user: str,
    folder: str,
    destination_path: str | None,
    share_name: str | None = None,
) -> tuple[str, str]:
    destination_root = normalize_destination_root(destination_path)
    if not destination_root:
        share = share_name or "C"
        return "C", f"\\\\{host}\\{share}\\Users\\{user}\\{folder}"

    drive, relative = destination_root
    base = f"\\\\{host}\\{share_name or drive}"
    if relative:
        base = f"{base}\\{relative}"
    return drive, f"{base}\\{user}\\{folder}"


def build_destination_base_path(
    host: str,
    destination_path: str | None,
    share_name: str | None = None,
) -> str:
    destination_root = normalize_destination_root(destination_path)
    if not destination_root:
        return f"\\\\{host}\\{share_name or 'C'}\\Users"

    drive, relative = destination_root
    base = f"\\\\{host}\\{share_name or drive}"
    return f"{base}\\{relative}" if relative else base


def build_temporary_destination_browse_path(
    host: str,
    drive: str,
    relative: str,
) -> str:
    base = f"\\\\{host}\\{_temporary_share_name(drive)}"
    return f"{base}\\{relative}" if relative else base
