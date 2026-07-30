"""WMT config components."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


def env_bool(name: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be greater than or equal to {minimum}.")
    return value


def cors_origins() -> list[str]:
    defaults = [
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
        "app://localhost",
        "asset://localhost",
    ]
    if DEVELOPMENT_MODE:
        defaults.extend(
            [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ]
        )
    extra = [
        item.strip()
        for item in os.getenv("WMT_CORS_ORIGINS", "").split(",")
        if item.strip() and item.strip().lower() != "null"
    ]
    return list(dict.fromkeys(defaults + extra))


BACKEND_DIR = Path(__file__).resolve().parents[2]


BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BACKEND_DIR))


DATA_DIR = Path(os.getenv("WMT_DATA_DIR", str(BACKEND_DIR / "data")))


SCRIPT_DIR = BUNDLE_DIR / "scripts"


STATE_FILE = DATA_DIR / "state.json"


STATE_DB_FILE = Path(os.getenv("WMT_STATE_DB_PATH", str(DATA_DIR / "state.db")))


UPDATES_DIR = DATA_DIR / "updates"


TOKEN_TTL_SECONDS = 8 * 60 * 60


SERVICE_NAME = "wmt-backend"


API_VERSION = 1


APP_VERSION = os.getenv("WMT_VERSION", "1.0.123").strip() or "1.0.123"


DEVELOPMENT_MODE = env_bool("WMT_DEV")


LOGIN_RATE_LIMIT_MAX_ATTEMPTS = env_int(
    "WMT_LOGIN_RATE_LIMIT_MAX_ATTEMPTS",
    5,
)


LOGIN_RATE_LIMIT_WINDOW_SECONDS = env_int(
    "WMT_LOGIN_RATE_LIMIT_WINDOW_SECONDS",
    5 * 60,
)


MAX_CONCURRENT_REMOTE_JOBS = env_int("WMT_MAX_CONCURRENT_REMOTE_JOBS", 8)


MAX_CONCURRENT_UPDATE_JOBS = env_int("WMT_MAX_CONCURRENT_UPDATE_JOBS", 4)


MAX_CONCURRENT_BACKUP_JOBS = env_int("WMT_MAX_CONCURRENT_BACKUP_JOBS", 2)


SESSION_COOKIE_NAME = os.getenv("WMT_SESSION_COOKIE_NAME", "wmt_session").strip() or "wmt_session"


SESSION_COOKIE_SECURE = env_bool(
    "WMT_SESSION_COOKIE_SECURE",
    not DEVELOPMENT_MODE,
)


SESSION_COOKIE_SAMESITE = os.getenv(
    "WMT_SESSION_COOKIE_SAMESITE",
    "none" if SESSION_COOKIE_SECURE else "lax",
).strip().lower()
if SESSION_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError(
        "WMT_SESSION_COOKIE_SAMESITE must be lax, strict, or none."
    )
if SESSION_COOKIE_SAMESITE == "none" and not SESSION_COOKIE_SECURE:
    raise RuntimeError(
        "SameSite=None requires WMT_SESSION_COOKIE_SECURE=true."
    )


ALLOW_BEARER_AUTH = env_bool("WMT_ALLOW_BEARER_AUTH")


HOST_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


BACKUP_FOLDERS = ["Desktop", "Documents", "Downloads", "Favorites", "Pictures", "Videos"]


BACKUP_EXCLUDED_FILE_PATTERNS = ["*.ost"]


BACKUP_CHECKLIST_ITEMS = [
    "desktop_copied",
    "documents_copied",
    "downloads_copied",
    "pictures_copied",
    "videos_copied",
    "favorites_copied",
    "ost_ignored",
    "destination_opened",
    "size_checked",
    "validated_with_user",
]


BACKUP_TEMPORARY_SHARE_TTL_MINUTES = 60


TEMPORARY_C_SHARE_NAME = "WMT_TEMP_C$"


DEFAULT_SETTINGS = {
    "display_language": "en-US",
    "software_center_timeout_seconds": 180,
    "software_center_poll_interval_seconds": 10,
    "update_job_timeout_minutes": 120,
    "backup_default_destination_path": "",
    "scripts_enabled": {
        "software_center": True,
        "remote_actions": True,
        "performance_monitor": True,
        "backup": True,
        "terms": True,
    },
    "remote_action_aliases": {},
}


REMOTE_ADMIN_USER = os.getenv("REMOTE_ADMIN_USER", "")


REMOTE_ADMIN_PASS = os.getenv("REMOTE_ADMIN_PASS", "")


BOOTSTRAP_ADMIN_USERNAME = os.getenv("WMT_BOOTSTRAP_ADMIN_USERNAME", "admin").strip()


BOOTSTRAP_ADMIN_EMAIL = os.getenv("WMT_BOOTSTRAP_ADMIN_EMAIL", "").strip()


BOOTSTRAP_ADMIN_PASSWORD = os.getenv("WMT_BOOTSTRAP_ADMIN_PASSWORD", "")


SSO_ENABLED = env_bool("WMT_SSO_ENABLED")


SSO_TRUSTED_PROXY_IPS = {
    item.strip()
    for item in os.getenv("WMT_SSO_TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",")
    if item.strip()
}


SSO_DESKTOP_FALLBACK = env_bool("WMT_SSO_DESKTOP_FALLBACK")


SSO_CLIENT_IP_FALLBACK = env_bool("WMT_SSO_CLIENT_IP_FALLBACK")


SSO_DEBUG_ENABLED = env_bool("WMT_SSO_DEBUG_ENABLED")


SSO_ALLOWED_GROUPS = {
    item.strip().lower()
    for item in re.split(r"[;,]", os.getenv("WMT_SSO_ALLOWED_GROUPS", ""))
    if item.strip()
}


SSO_ADMIN_GROUPS = {
    item.strip().lower()
    for item in re.split(r"[;,]", os.getenv("WMT_SSO_ADMIN_GROUPS", ""))
    if item.strip()
}


SSO_OPERATOR_GROUPS = {
    item.strip().lower()
    for item in re.split(r"[;,]", os.getenv("WMT_SSO_OPERATOR_GROUPS", ""))
    if item.strip()
}


SSO_VIEWER_GROUPS = {
    item.strip().lower()
    for item in re.split(r"[;,]", os.getenv("WMT_SSO_VIEWER_GROUPS", ""))
    if item.strip()
}


SSO_ADMIN_USERS = {
    item.strip().lower()
    for item in re.split(r"[;,]", os.getenv("WMT_SSO_ADMIN_USERS", ""))
    if item.strip()
}


SSO_OPERATOR_USERS = {
    item.strip().lower()
    for item in re.split(r"[;,]", os.getenv("WMT_SSO_OPERATOR_USERS", ""))
    if item.strip()
}


SSO_VIEWER_USERS = {
    item.strip().lower()
    for item in re.split(r"[;,]", os.getenv("WMT_SSO_VIEWER_USERS", ""))
    if item.strip()
}


SSO_DEFAULT_ROLE = os.getenv("WMT_SSO_DEFAULT_ROLE", "viewer").lower()


SSO_ALLOW_PRIVILEGED_DEFAULT_ROLE = env_bool("WMT_SSO_ALLOW_PRIVILEGED_DEFAULT_ROLE")


def repair_config_mojibake(value: str) -> str:
    if "Ã" not in value and "Â" not in value:
        return value
    try:
        return value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return value


TERMS_RESPONSIBILITY_TEMPLATE_PATH = Path(
    repair_config_mojibake(
        os.getenv(
            "TERMS_RESPONSIBILITY_TEMPLATE_PATH",
            "\\\\fss048-01br\\CSI\\04 - TERMOS DE RESPONSABILIDADE & FORMULARIOS\\TERMO DE RESPONSABILIDADE E ACEITA\u00c7\u00c3O NOTEBOOK 2026\\TRA - PIRELLI PNEUS - NOTEBOOK - NOME COMPLETO - SERIAL - NOVO.docx",
        )
    )
)


TERMS_RETURN_TEMPLATE_PATH = Path(
    repair_config_mojibake(
        os.getenv(
            "TERMS_RETURN_TEMPLATE_PATH",
            "\\\\fss048-01br\\CSI\\04 - TERMOS DE RESPONSABILIDADE & FORMULARIOS\\TERMO DEVOLU\u00c7\u00c3O NOTEBOOK 2026\\T D - NOTEBOOK - PIRELLI PNEUS - NOME COMPLETO - SERIAL.docx",
        )
    )
)


TERM_TYPES = {
    "responsibility": {
        "label": "Responsibility and acceptance",
        "template": lambda: TERMS_RESPONSIBILITY_TEMPLATE_PATH,
        "filename_suffix": "responsibility",
    },
    "return": {
        "label": "Equipment return",
        "template": lambda: TERMS_RETURN_TEMPLATE_PATH,
        "filename_suffix": "return",
    },
}


WORD_XML_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


for _prefix, _uri in {
    "w": WORD_XML_NS,
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}.items():
    ET.register_namespace(_prefix, _uri)

