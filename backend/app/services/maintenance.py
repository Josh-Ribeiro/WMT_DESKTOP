"""Persistence helpers for active workstation maintenance modes."""

from __future__ import annotations

import datetime

from ..core.security import utc_now
from ..repositories.state import mutate_state


def _parse_utc(value: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(str(value or "").replace("Z", ""))
    except ValueError:
        return None


def track_maintenance_mode(
    payload: dict,
    *,
    opened_by: str,
    technician: str,
    contact: str,
    ticket: str,
    reason: str,
    duration_minutes: int,
) -> None:
    host = str(payload.get("host") or "").upper()
    entry = {
        "id": host,
        "host": host,
        "active": bool(payload.get("active", True)),
        "opened_by": opened_by,
        "technician": technician,
        "contact": contact,
        "ticket": ticket,
        "reason": reason,
        "duration_minutes": duration_minutes,
        "opened_at": utc_now(),
        "expires_at": str(payload.get("expires_at") or ""),
        "protected_users": payload.get("protected_users") or [],
        "last_seen": utc_now(),
    }

    def track(state: dict) -> None:
        modes = [
            item
            for item in state.get("maintenance_modes", [])
            if str(item.get("host") or "").upper() != host
        ]
        modes.insert(0, entry)
        state["maintenance_modes"] = modes

    mutate_state(track)


def untrack_maintenance_mode(host: str) -> None:
    normalized_host = str(host or "").upper()

    def untrack(state: dict) -> None:
        state["maintenance_modes"] = [
            item
            for item in state.get("maintenance_modes", [])
            if str(item.get("host") or "").upper() != normalized_host
        ]

    mutate_state(untrack)


def _modes_recovered_from_audit(entries: list[dict]) -> list[dict]:
    latest_by_host: dict[str, dict] = {}
    for event in entries:
        details = event.get("details") or {}
        host = str(details.get("host") or "").upper()
        if not host or host in latest_by_host:
            continue
        latest_by_host[host] = event

    recovered: list[dict] = []
    for host, event in latest_by_host.items():
        if event.get("action") != "maintenance.enable":
            continue
        details = event.get("details") or {}
        opened_at = str(event.get("timestamp") or "")
        opened = _parse_utc(opened_at)
        duration_minutes = int(details.get("duration_minutes") or 60)
        expires = (
            opened + datetime.timedelta(minutes=duration_minutes)
            if opened
            else None
        )
        recovered.append(
            {
                "id": host,
                "host": host,
                "active": True,
                "opened_by": event.get("username") or "",
                "technician": details.get("technician") or "",
                "contact": details.get("contact") or "",
                "ticket": details.get("ticket") or "",
                "reason": details.get("reason") or "",
                "duration_minutes": duration_minutes,
                "opened_at": opened_at,
                "expires_at": (
                    expires.isoformat(timespec="seconds") + "Z"
                    if expires
                    else ""
                ),
                "protected_users": details.get("protected_users") or [],
                "last_seen": opened_at,
            }
        )
    return recovered


def build_maintenance_modes_payload(
    state: dict,
    audit_entries: list[dict] | None = None,
) -> dict:
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    modes: list[dict] = []
    stored_by_host = {
        str(item.get("host") or "").upper(): item
        for item in state.get("maintenance_modes", [])
    }
    for recovered in _modes_recovered_from_audit(audit_entries or []):
        stored_by_host.setdefault(str(recovered.get("host") or ""), recovered)

    for stored in stored_by_host.values():
        expires_at = str(stored.get("expires_at") or "")
        expires = _parse_utc(expires_at)
        expired = bool(expires and expires <= now)
        if expired or not stored.get("active", True):
            continue
        remaining_seconds = (
            max(0, int((expires - now).total_seconds())) if expires else None
        )
        modes.append(
            {
                **stored,
                "active": True,
                "expired": False,
                "remaining_seconds": remaining_seconds,
            }
        )
    modes.sort(key=lambda item: str(item.get("expires_at") or ""))
    return {"modes": modes, "total": len(modes), "active": len(modes)}
