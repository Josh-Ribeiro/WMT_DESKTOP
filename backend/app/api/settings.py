from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi import APIRouter

from ..core.config import DEFAULT_SETTINGS
from ..repositories.state import (
    audit,
    current_settings,
    mutate_state,
)
from ..schemas import AppSettingsUpdateRequest
from ..services.auth import require_role

router = APIRouter()


@router.get("/api/settings")
def app_settings(user: dict = Depends(require_role("admin"))):
    return current_settings()


@router.get("/api/app-preferences")
def app_preferences():
    settings = current_settings()
    return {
        "display_language": settings.get("display_language", "en-US"),
        "backup_default_destination_path": settings.get("backup_default_destination_path", ""),
    }


@router.put("/api/settings")
def update_app_settings(request: AppSettingsUpdateRequest, user: dict = Depends(require_role("admin"))):
    def update(state: dict) -> dict:
        settings = state.setdefault("settings", {})
        settings["display_language"] = request.display_language
        settings["software_center_timeout_seconds"] = request.software_center_timeout_seconds
        settings["software_center_poll_interval_seconds"] = request.software_center_poll_interval_seconds
        settings["update_job_timeout_minutes"] = request.update_job_timeout_minutes
        settings["backup_default_destination_path"] = request.backup_default_destination_path.strip()
        enabled = DEFAULT_SETTINGS["scripts_enabled"].copy()
        enabled.update(
            {key: bool(value) for key, value in request.scripts_enabled.items()}
        )
        settings["scripts_enabled"] = enabled
        settings["remote_action_aliases"] = {
            str(key).strip(): str(value).strip()
            for key, value in request.remote_action_aliases.items()
            if str(key).strip() and str(value).strip()
        }
        return settings

    mutate_state(update)
    updated_settings = current_settings()
    audit("settings.update", user["username"], {"settings": updated_settings})
    return updated_settings
