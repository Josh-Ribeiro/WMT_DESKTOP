"""Transactional application-state repository backed by SQLite."""

from __future__ import annotations

import copy
import json
import secrets
import sqlite3
import threading
from collections.abc import Callable
from typing import TypeVar
from uuid import uuid4

from ..core.config import (
    BOOTSTRAP_ADMIN_EMAIL,
    BOOTSTRAP_ADMIN_PASSWORD,
    BOOTSTRAP_ADMIN_USERNAME,
    DATA_DIR,
    DEFAULT_SETTINGS,
    STATE_DB_FILE,
    STATE_FILE,
)
from ..core.security import password_hash, utc_now, verify_password


STATE_LOCK = threading.RLock()
STATE_CACHE: dict | None = None
STATE_CACHE_REVISION: int | None = None
STATE_INITIALIZED_DB: str | None = None
STATE_REVISION_KEY = "__wmt_state_revision"
STATE_SCHEMA_VERSION = 2
T = TypeVar("T")


class StateConflictError(RuntimeError):
    """Raised when a stale state snapshot would overwrite newer data."""


def _bootstrap_admin() -> dict | None:
    if not BOOTSTRAP_ADMIN_PASSWORD:
        return None
    if len(BOOTSTRAP_ADMIN_PASSWORD) < 12:
        raise RuntimeError(
            "WMT_BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters."
        )
    if BOOTSTRAP_ADMIN_PASSWORD == "admin123":
        raise RuntimeError(
            "WMT_BOOTSTRAP_ADMIN_PASSWORD cannot use the legacy default password."
        )
    username = BOOTSTRAP_ADMIN_USERNAME or "admin"
    return {
        "id": f"usr-{uuid4().hex[:12]}",
        "username": username,
        "email": BOOTSTRAP_ADMIN_EMAIL,
        "role": "admin",
        "status": "active",
        "password_hash": password_hash(BOOTSTRAP_ADMIN_PASSWORD),
        "last_login": "",
        "created_at": utc_now(),
        "auth_source": "local",
    }


def default_state() -> dict:
    bootstrap_user = _bootstrap_admin()
    return {
        "users": [bootstrap_user] if bootstrap_user else [],
        "backup_jobs": [],
        "remote_jobs": [],
        "temp_shares": [],
        "update_jobs": [],
        "settings": copy.deepcopy(DEFAULT_SETTINGS),
        "audit": [],
    }


def _is_legacy_demo_backup(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    return (
        item.get("id") == "BK001"
        and str(item.get("workstation") or "").lower() == "localhost"
        and item.get("start_time") == "2026-05-28 10:00:00"
        and item.get("size") == "256 GB"
    )


def ensure_state_defaults(
    state: dict,
    *,
    apply_security_migrations: bool = True,
) -> dict:
    for key, value in {
        "users": [],
        "backup_jobs": [],
        "remote_jobs": [],
        "temp_shares": [],
        "update_jobs": [],
        "audit": [],
    }.items():
        state.setdefault(key, copy.deepcopy(value))

    if apply_security_migrations:
        state["backup_jobs"] = [
            item
            for item in state.get("backup_jobs", [])
            if not _is_legacy_demo_backup(item)
        ]

        insecure_users: list[dict] = []
        for user in state.get("users", []):
            stored_hash = str(user.get("password_hash") or "")
            if stored_hash and verify_password("admin123", stored_hash):
                insecure_users.append(user)

        needs_bootstrap = not state["users"] or any(
            BOOTSTRAP_ADMIN_PASSWORD
            and str(user.get("username") or "").lower()
            == (BOOTSTRAP_ADMIN_USERNAME or "admin").lower()
            for user in insecure_users
        )
        bootstrap_user = _bootstrap_admin() if needs_bootstrap else None

        for user in insecure_users:
            if (
                bootstrap_user
                and str(user.get("username") or "").lower()
                == bootstrap_user["username"].lower()
            ):
                user.update(
                    {
                        "password_hash": bootstrap_user["password_hash"],
                        "status": "active",
                        "email": bootstrap_user["email"] or user.get("email", ""),
                        "legacy_password_replaced_at": utc_now(),
                    }
                )
            else:
                user["status"] = "locked"
                user["security_notice"] = (
                    "Locked automatically because it used the retired default password."
                )

        if not state["users"] and bootstrap_user:
            state["users"].append(bootstrap_user)

    settings = state.setdefault("settings", {})
    for key, value in DEFAULT_SETTINGS.items():
        if key not in settings:
            settings[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(settings.get(key), dict):
            for nested_key, nested_value in value.items():
                settings[key].setdefault(nested_key, copy.deepcopy(nested_value))
    return state


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(STATE_DB_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    return connection


def _legacy_state() -> dict | None:
    if not STATE_FILE.is_file():
        return None
    with STATE_FILE.open("r", encoding="utf-8-sig") as state_file:
        payload = json.load(state_file)
    if not isinstance(payload, dict):
        raise RuntimeError("Legacy state.json must contain a JSON object.")
    return payload


def _initialize_database_unlocked() -> None:
    global STATE_INITIALIZED_DB
    database_key = str(STATE_DB_FILE.resolve())
    if STATE_INITIALIZED_DB == database_key and STATE_DB_FILE.is_file():
        return

    connection = _connect()
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS state_snapshot (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    revision INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS state_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            row = connection.execute(
                "SELECT revision, payload FROM state_snapshot WHERE id = 1"
            ).fetchone()
            if row is None:
                legacy = _legacy_state()
                state = ensure_state_defaults(
                    legacy if legacy is not None else default_state()
                )
                connection.execute(
                    """
                    INSERT INTO state_snapshot (id, revision, payload, updated_at)
                    VALUES (1, 1, ?, ?)
                    """,
                    (json.dumps(state, ensure_ascii=False), utc_now()),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO state_metadata (key, value) VALUES (?, ?)",
                    ("schema_version", str(STATE_SCHEMA_VERSION)),
                )
                if legacy is not None:
                    connection.execute(
                        "INSERT OR REPLACE INTO state_metadata (key, value) VALUES (?, ?)",
                        ("legacy_json_migrated_at", utc_now()),
                    )
                STATE_INITIALIZED_DB = database_key
                return

            metadata = connection.execute(
                "SELECT value FROM state_metadata WHERE key = ?",
                ("schema_version",),
            ).fetchone()
            stored_version = int(metadata["value"]) if metadata else 0
            if stored_version < STATE_SCHEMA_VERSION:
                stored = json.loads(row["payload"])
                prepared = ensure_state_defaults(copy.deepcopy(stored))
                if prepared != stored:
                    connection.execute(
                        """
                        UPDATE state_snapshot
                        SET revision = ?, payload = ?, updated_at = ?
                        WHERE id = 1
                        """,
                        (
                            int(row["revision"]) + 1,
                            json.dumps(prepared, ensure_ascii=False),
                            utc_now(),
                        ),
                    )
                connection.execute(
                    "INSERT OR REPLACE INTO state_metadata (key, value) VALUES (?, ?)",
                    ("schema_version", str(STATE_SCHEMA_VERSION)),
                )
            STATE_INITIALIZED_DB = database_key
    finally:
        connection.close()


def _refresh_state_cache_unlocked() -> tuple[dict, int]:
    global STATE_CACHE, STATE_CACHE_REVISION
    _initialize_database_unlocked()
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT revision, payload FROM state_snapshot WHERE id = 1"
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("SQLite state repository was not initialized.")
    revision = int(row["revision"])
    if STATE_CACHE is None or STATE_CACHE_REVISION != revision:
        STATE_CACHE = json.loads(row["payload"])
        STATE_CACHE_REVISION = revision
    return STATE_CACHE, revision


def _state_cache_unlocked() -> dict:
    state_cache, revision = _refresh_state_cache_unlocked()
    snapshot = copy.deepcopy(state_cache)
    snapshot[STATE_REVISION_KEY] = revision
    return snapshot


def load_state() -> dict:
    with STATE_LOCK:
        return _state_cache_unlocked()


def load_state_fields(*keys: str) -> dict:
    with STATE_LOCK:
        state_cache, _revision = _refresh_state_cache_unlocked()
        selected = {key: state_cache.get(key) for key in keys}
        return copy.deepcopy(selected)


def state_user_by_id(user_id: str | None) -> dict | None:
    if not user_id:
        return None
    with STATE_LOCK:
        state, _revision = _refresh_state_cache_unlocked()
        user = next(
            (item for item in state.get("users", []) if item.get("id") == user_id),
            None,
        )
        return copy.deepcopy(user) if user else None


def probe_state_repository() -> None:
    """Fail when the SQLite repository cannot be initialized and read."""
    with STATE_LOCK:
        state = _state_cache_unlocked()
        if STATE_REVISION_KEY not in state:
            raise RuntimeError("SQLite state repository revision is unavailable.")


def save_state(state: dict) -> None:
    global STATE_CACHE, STATE_CACHE_REVISION
    with STATE_LOCK:
        expected_revision = state.get(STATE_REVISION_KEY)
        payload = copy.deepcopy(state)
        payload.pop(STATE_REVISION_KEY, None)
        payload = ensure_state_defaults(
            payload,
            apply_security_migrations=False,
        )

        _initialize_database_unlocked()
        connection = _connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revision FROM state_snapshot WHERE id = 1"
            ).fetchone()
            if row is None:
                raise RuntimeError("SQLite state repository was not initialized.")
            current_revision = int(row["revision"])
            if (
                expected_revision is not None
                and int(expected_revision) != current_revision
            ):
                raise StateConflictError(
                    "State changed after it was loaded; refusing to overwrite newer data."
                )
            new_revision = current_revision + 1
            connection.execute(
                """
                UPDATE state_snapshot
                SET revision = ?, payload = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    new_revision,
                    json.dumps(payload, ensure_ascii=False),
                    utc_now(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        STATE_CACHE = copy.deepcopy(payload)
        STATE_CACHE_REVISION = new_revision
        state[STATE_REVISION_KEY] = new_revision


def mutate_state(mutator: Callable[[dict], T], retries: int = 3) -> T:
    last_conflict: StateConflictError | None = None
    for _attempt in range(max(1, retries)):
        state = load_state()
        result = mutator(state)
        try:
            save_state(state)
            return result
        except StateConflictError as exc:
            last_conflict = exc
    raise last_conflict or StateConflictError("Unable to update application state.")


def reconcile_interrupted_update_jobs() -> None:
    def reconcile(state: dict) -> None:
        for job in state.get("update_jobs", []):
            if job.get("status") not in {"queued", "running"}:
                continue
            job.update(
                {
                    "status": "failed",
                    "ok": False,
                    "message": "Monitoramento interrompido por reinicio do backend.",
                    "ended_at": utc_now(),
                }
            )

    mutate_state(reconcile)


def current_settings() -> dict:
    settings = load_state().get("settings", {})
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    for key, value in DEFAULT_SETTINGS.items():
        if isinstance(value, dict):
            merged[key].update(settings.get(key) or {})
        else:
            merged[key] = settings.get(key, value)
    return merged


def script_enabled(script_key: str) -> bool:
    settings = current_settings()
    return bool(settings.get("scripts_enabled", {}).get(script_key, True))


def audit(action: str, username: str, details: dict | None = None) -> None:
    def append_audit(state: dict) -> None:
        state.setdefault("audit", []).insert(
            0,
            {
                "id": secrets.token_hex(8),
                "action": action,
                "username": username,
                "details": details or {},
                "timestamp": utc_now(),
            },
        )
        state["audit"] = state["audit"][:1000]

    mutate_state(append_audit)
