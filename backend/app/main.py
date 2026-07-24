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

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

app = FastAPI(title="WMT Desktop Backend")

def cors_origins() -> list[str]:
    defaults = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
        "app://localhost",
        "asset://localhost",
        "null",
    ]
    extra = [
        item.strip()
        for item in os.getenv("WMT_CORS_ORIGINS", "").split(",")
        if item.strip()
    ]
    return defaults + extra


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1|tauri\.localhost)(:\d+)?|tauri://localhost|app://localhost|asset://localhost|null)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Missing-Placeholders"],
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
STATE_FILE = DATA_DIR / "state.json"
UPDATES_DIR = DATA_DIR / "updates"
TOKEN_TTL_SECONDS = 8 * 60 * 60
SESSIONS: dict[str, dict] = {}
HOST_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
STATE_LOCK = threading.RLock()
STATE_CACHE: dict | None = None
STATE_CACHE_MTIME_NS: int | None = None
BACKUP_JOBS_LOCK = threading.Lock()
BACKUP_JOBS: dict[str, dict] = {}
REMOTE_JOBS_LOCK = threading.Lock()
REMOTE_JOBS: dict[str, dict] = {}
REMOTE_JOB_PROCESSES: dict[str, subprocess.Popen[str]] = {}
UPDATE_JOBS_LOCK = threading.Lock()
UPDATE_JOBS: dict[str, dict] = {}
DIAGNOSTIC_JOBS_LOCK = threading.Lock()
DIAGNOSTIC_JOBS: dict[str, dict] = {}
DIAGNOSTIC_JOB_SEMAPHORE = threading.Semaphore(3)
TEMP_SHARES_CACHE_LOCK = threading.Lock()
TEMP_SHARES_CACHE: dict[str, dict] = {}
RESPONSE_CACHE_LOCK = threading.Lock()
RESPONSE_CACHE: dict[str, dict] = {}
RESPONSE_CACHE_INFLIGHT_LOCK = threading.Lock()
RESPONSE_CACHE_INFLIGHT: dict[str, threading.Event] = {}
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
SSO_ENABLED = os.getenv("WMT_SSO_ENABLED", "true").lower() == "true"
SSO_TRUSTED_PROXY_IPS = {
    item.strip()
    for item in os.getenv("WMT_SSO_TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",")
    if item.strip()
}
SSO_DESKTOP_FALLBACK = os.getenv("WMT_SSO_DESKTOP_FALLBACK", "true").lower() == "true"
SSO_CLIENT_IP_FALLBACK = os.getenv("WMT_SSO_CLIENT_IP_FALLBACK", "true").lower() == "true"
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
SSO_ALLOW_PRIVILEGED_DEFAULT_ROLE = os.getenv("WMT_SSO_ALLOW_PRIVILEGED_DEFAULT_ROLE", "false").lower() == "true"


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

Role = Literal["admin", "operator", "viewer"]
UserStatus = Literal["active", "inactive", "locked"]
BackupStatus = Literal["completed", "running", "failed", "scheduled", "canceled"]


def utc_now() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def password_hash(password: str, salt: str | None = None) -> str:
    current_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), current_salt.encode("utf-8"), 150_000)
    return f"{current_salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, _digest = stored_hash.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(password_hash(password, salt), stored_hash)


def default_state() -> dict:
    now = utc_now()
    return {
        "users": [
            {
                "id": "usr-admin",
                "username": "admin",
                "email": "admin@company.com",
                "role": "admin",
                "status": "active",
                "password_hash": password_hash("admin123"),
                "last_login": "",
                "created_at": now,
            }
        ],
        "backup_jobs": [
            {
                "id": "BK001",
                "workstation": "localhost",
                "status": "completed",
                "start_time": "2026-05-28 10:00:00",
                "end_time": "2026-05-28 10:45:00",
                "size": "256 GB",
                "progress": 100,
            }
        ],
        "remote_jobs": [],
        "temp_shares": [],
        "update_jobs": [],
        "settings": DEFAULT_SETTINGS,
        "audit": [],
    }


def ensure_state_defaults(state: dict) -> dict:
    changed = False
    for key, value in {
        "users": [],
        "backup_jobs": [],
        "remote_jobs": [],
        "temp_shares": [],
        "update_jobs": [],
        "audit": [],
    }.items():
        if key not in state:
            state[key] = value
            changed = True

    settings = state.setdefault("settings", {})
    for key, value in DEFAULT_SETTINGS.items():
        if key not in settings:
            settings[key] = value.copy() if isinstance(value, dict) else value
            changed = True
        elif isinstance(value, dict) and isinstance(settings.get(key), dict):
            for nested_key, nested_value in value.items():
                if nested_key not in settings[key]:
                    settings[key][nested_key] = nested_value
                    changed = True

    if changed:
        save_state(state)
    return state


def _state_cache_unlocked() -> dict:
    global STATE_CACHE, STATE_CACHE_MTIME_NS
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        state = default_state()
        save_state(state)
        return STATE_CACHE if STATE_CACHE is not None else state
    state_mtime_ns = STATE_FILE.stat().st_mtime_ns
    if STATE_CACHE is not None and STATE_CACHE_MTIME_NS == state_mtime_ns:
        return STATE_CACHE
    with STATE_FILE.open("r", encoding="utf-8") as state_file:
        state = json.load(state_file)
    state = ensure_state_defaults(state)
    STATE_CACHE = copy.deepcopy(state)
    STATE_CACHE_MTIME_NS = STATE_FILE.stat().st_mtime_ns
    return STATE_CACHE


def load_state() -> dict:
    with STATE_LOCK:
        return copy.deepcopy(_state_cache_unlocked())


def load_state_fields(*keys: str) -> dict:
    with STATE_LOCK:
        state = _state_cache_unlocked()
        return {key: copy.deepcopy(state.get(key)) for key in keys}


def state_user_by_id(user_id: str | None) -> dict | None:
    if not user_id:
        return None
    with STATE_LOCK:
        state = _state_cache_unlocked()
        user = next((item for item in state.get("users", []) if item.get("id") == user_id), None)
        return copy.deepcopy(user) if user else None


def save_state(state: dict) -> None:
    global STATE_CACHE, STATE_CACHE_MTIME_NS
    with STATE_LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp_file = STATE_FILE.with_name(
            f".{STATE_FILE.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        with tmp_file.open("w", encoding="utf-8") as state_file:
            json.dump(state, state_file, ensure_ascii=False, indent=2)
        tmp_file.replace(STATE_FILE)
        STATE_CACHE = copy.deepcopy(state)
        STATE_CACHE_MTIME_NS = STATE_FILE.stat().st_mtime_ns


@app.on_event("startup")
def reconcile_interrupted_update_jobs() -> None:
    state = load_state()
    changed = False
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
        changed = True
    if changed:
        save_state(state)


def current_settings() -> dict:
    state = load_state()
    settings = state.get("settings", {})
    merged = DEFAULT_SETTINGS.copy()
    for key, value in DEFAULT_SETTINGS.items():
        if isinstance(value, dict):
            nested = value.copy()
            nested.update(settings.get(key) or {})
            merged[key] = nested
        else:
            merged[key] = settings.get(key, value)
    return merged


def script_enabled(script_key: str) -> bool:
    settings = current_settings()
    return bool(settings.get("scripts_enabled", {}).get(script_key, True))


def friendly_error_message(raw_message: str, context: str = "operaÃ§Ã£o") -> str:
    text = (raw_message or "").strip()
    lowered = text.lower()
    if not text:
        return f"NÃ£o foi possÃ­vel concluir a {context}."

    if any(item in lowered for item in ["access is denied", "access denied", "acesso negado", "system error 5", "unauthorizedaccess"]):
        return f"Acesso negado ao executar {context}. Verifique se a conta do backend tem permissÃ£o administrativa no host de destino."
    if any(item in lowered for item in ["winrm", "wsman", "cannot connect to the destination", "the client cannot connect", "access is denied. for more information, see the about_remote_troubleshooting"]):
        return f"WinRM/PowerShell Remoting indisponÃ­vel para {context}. Confirme se o host estÃ¡ online, com WinRM habilitado e liberado no firewall."
    if any(item in lowered for item in ["no such host", "could not resolve", "host not found", "ping request could not find host"]):
        return f"Host nÃ£o encontrado para {context}. Confira o nome da WKS ou DNS."
    if any(item in lowered for item in ["network path was not found", "the network path was not found", "0x80070035", "nÃ£o foi encontrado o caminho da rede"]):
        return f"Host offline ou compartilhamento administrativo inacessÃ­vel para {context}. Verifique rede, firewall e admin share."
    if any(item in lowered for item in ["sms_client", "root\\ccm", "invalid namespace", "ccmexec", "ccm_softwareupdate"]):
        return f"SCCM Client nÃ£o foi encontrado ou nÃ£o respondeu no host durante {context}. Verifique se o cliente SCCM estÃ¡ instalado e saudÃ¡vel."
    if any(item in lowered for item in ["logon failure", "unknown user name or bad password", "falha de logon", "usuÃ¡rio ou senha incorretos"]):
        return f"Credencial sem permissÃ£o ou invÃ¡lida para {context}. Confira usuÃ¡rio, senha e privilÃ©gios locais no host."
    if any(item in lowered for item in ["admin$", "c$", "multiple connections", "error 1219"]):
        return f"Admin share bloqueado ou sessÃ£o SMB conflitante durante {context}. Feche conexÃµes antigas e confirme acesso ao C$/ADMIN$."
    return text


def public_user(user: dict) -> dict:
    payload = {key: value for key, value in user.items() if key != "password_hash"}
    payload["permissions"] = role_permissions(str(payload.get("role") or "viewer"))
    return payload


def role_permissions(role: str) -> list[str]:
    permissions = {
        "admin": ["dashboard", "monitor", "tasks", "backup", "history", "terms", "users", "settings", "account"],
        "operator": ["dashboard", "monitor", "tasks", "backup", "history", "terms", "account"],
        "viewer": ["dashboard", "monitor", "tasks", "account"],
    }
    return permissions.get(role, [])


def normalize_windows_identity(identity: str) -> tuple[str, str, str]:
    value = (identity or "").strip()
    if not value:
        raise HTTPException(status_code=401, detail="Windows identity was not provided")

    if "@" in value and "\\" not in value:
        username, domain = value.split("@", 1)
        return domain.upper(), username.lower(), value

    if "\\" in value:
        domain, username = value.split("\\", 1)
        return domain.upper(), username.lower(), f"{domain.upper()}\\{username.lower()}"

    return "", value.lower(), value.lower()


def is_loopback_client(value: str) -> bool:
    normalized = (value or "").strip().lower()
    return normalized in {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}


def escape_ldap_filter_value(value: str) -> str:
    return (
        value.replace("\\", r"\5c")
        .replace("*", r"\2a")
        .replace("(", r"\28")
        .replace(")", r"\29")
        .replace("\x00", r"\00")
    )


def group_matches(user_groups: list[str], configured_groups: set[str]) -> bool:
    if not configured_groups:
        return False

    normalized_groups = [group.lower() for group in user_groups]
    for expected in configured_groups:
        if any(expected == group or expected in group for group in normalized_groups):
            return True
    return False


def user_matches(username: str, domain: str, ad_user: dict, configured_users: set[str]) -> bool:
    if not configured_users:
        return False

    candidates = {
        (username or "").strip().lower(),
        (ad_user.get("upn") or "").strip().lower(),
        (ad_user.get("email") or "").strip().lower(),
    }
    if domain and username:
        candidates.add(f"{domain}\\{username}".lower())
        candidates.add(f"{username}@{domain}".lower())

    return any(candidate and candidate in configured_users for candidate in candidates)


def sso_role_for_user(username: str, domain: str, ad_user: dict, groups: list[str]) -> Role:
    if user_matches(username, domain, ad_user, SSO_ADMIN_USERS):
        return "admin"
    if user_matches(username, domain, ad_user, SSO_OPERATOR_USERS):
        return "operator"
    if user_matches(username, domain, ad_user, SSO_VIEWER_USERS):
        return "viewer"
    return sso_role_for_groups(groups)


def sso_role_for_groups(groups: list[str]) -> Role:
    if group_matches(groups, SSO_ADMIN_GROUPS):
        return "admin"
    if group_matches(groups, SSO_OPERATOR_GROUPS):
        return "operator"
    if group_matches(groups, SSO_VIEWER_GROUPS):
        return "viewer"
    if SSO_DEFAULT_ROLE == "viewer":
        return "viewer"
    if SSO_DEFAULT_ROLE in {"admin", "operator"} and SSO_ALLOW_PRIVILEGED_DEFAULT_ROLE:
        return SSO_DEFAULT_ROLE  # type: ignore[return-value]
    return "viewer"


def query_ad_user(username: str) -> dict:
    executable = powershell_executable()
    if executable is None:
        return {"display_name": username, "email": "", "groups": []}

    escaped_username = escape_ldap_filter_value(username)
    command = (
        "$ErrorActionPreference='Stop'; "
        f"$sam={json.dumps(escaped_username)}; "
        "$searcher = New-Object DirectoryServices.DirectorySearcher; "
        "$searcher.Filter = \"(&(objectCategory=person)(objectClass=user)(sAMAccountName=$sam))\"; "
        "$searcher.PropertiesToLoad.Add('displayName') | Out-Null; "
        "$searcher.PropertiesToLoad.Add('mail') | Out-Null; "
        "$searcher.PropertiesToLoad.Add('userPrincipalName') | Out-Null; "
        "$searcher.PropertiesToLoad.Add('memberOf') | Out-Null; "
        "$result = $searcher.FindOne(); "
        "if ($null -eq $result) { throw 'User not found in Active Directory' }; "
        "$props = $result.Properties; "
        "$groups = @($props.memberof | ForEach-Object { [string]$_ }); "
        "try { "
        "  Add-Type -AssemblyName System.DirectoryServices.AccountManagement -ErrorAction Stop; "
        "  $ctx = New-Object System.DirectoryServices.AccountManagement.PrincipalContext([System.DirectoryServices.AccountManagement.ContextType]::Domain); "
        "  $principal = [System.DirectoryServices.AccountManagement.UserPrincipal]::FindByIdentity($ctx, $sam); "
        "  if ($null -ne $principal) { "
        "    $authGroups = @($principal.GetAuthorizationGroups() | ForEach-Object { "
        "      if ($_.DistinguishedName) { [string]$_.DistinguishedName } elseif ($_.SamAccountName) { [string]$_.SamAccountName } else { [string]$_.Name } "
        "    }); "
        "    if ($authGroups.Count -gt 0) { $groups = $authGroups }; "
        "  } "
        "} catch { } "
        "$payload = [ordered]@{ "
        "display_name = [string]($props.displayname | Select-Object -First 1); "
        "email = [string]($props.mail | Select-Object -First 1); "
        "upn = [string]($props.userprincipalname | Select-Object -First 1); "
        "groups = @($groups | Sort-Object -Unique) "
        "}; "
        "$payload | ConvertTo-Json -Compress -Depth 4"
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
        detail = (result.stderr or result.stdout or "").strip()
        raise HTTPException(status_code=403, detail=detail or "Unable to load Active Directory user")

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        payload = {}

    groups = payload.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]

    return {
        "display_name": payload.get("display_name") or username,
        "email": payload.get("email") or "",
        "upn": payload.get("upn") or "",
        "groups": [str(group) for group in groups],
    }


def _ad_user_lookup_key(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip()).lower()


def _cn_from_distinguished_name(value: str) -> str:
    first = str(value or "").split(",", 1)[0]
    if first.lower().startswith("cn="):
        return first[3:].replace("\\,", ",")
    return first


def _ou_from_distinguished_name(value: str) -> str:
    return ",".join(part for part in re.split(r"(?<!\\),", str(value or "")) if part.upper().startswith("OU="))


def _looks_like_office_entitlement(value: str) -> bool:
    text = value.lower()
    needles = [
        "office",
        "m365",
        "o365",
        "microsoft 365",
        "e1",
        "e3",
        "e5",
        "exchange",
        "teams",
        "onedrive",
        "sharepoint",
        "power bi",
        "powerbi",
        "visio",
        "project",
    ]
    return any(needle in text for needle in needles)


def _license_label_from_group(value: str) -> str:
    clean = _cn_from_distinguished_name(value)
    clean = re.sub(r"^(lic|license|grp|sg|dl)[-_ ]+", "", clean, flags=re.IGNORECASE)
    clean = clean.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", clean).strip() or value


def collect_ad_user_info(query: str) -> dict:
    executable = powershell_executable()
    normalized = (query or "").strip()
    if executable is None:
        return {
            "found": False,
            "query": normalized,
            "status": "unknown",
            "status_label": "PowerShell unavailable",
            "error": "PowerShell nao encontrado neste ambiente.",
        }

    script = r"""
$Query = $env:WMT_AD_USER_QUERY
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
function FirstText($Value) {
    if ($null -eq $Value) { return "" }
    $item = @($Value | Select-Object -First 1)
    if ($null -eq $item -or $item.Count -eq 0) { return "" }
    return [string]$item[0]
}
function FileTimeText($Value) {
    try {
        $raw = [Int64](FirstText $Value)
        if ($raw -le 0 -or $raw -ge 9223372036854775807) { return "" }
        return [DateTime]::FromFileTimeUtc($raw).ToLocalTime().ToString("dd-MM-yyyy HH:mm:ss")
    } catch { return "" }
}
function DateText($Value) {
    $text = FirstText $Value
    if ([string]::IsNullOrWhiteSpace($text)) { return "" }
    try { return ([DateTime]$text).ToString("dd-MM-yyyy HH:mm:ss") } catch { return $text }
}
function EscapeLdap($Value) {
    return ([string]$Value).Replace('\','\5c').Replace('*','\2a').Replace('(','\28').Replace(')','\29').Replace([string][char]0,'\00')
}
try {
    $safe = EscapeLdap $Query
    $searcher = New-Object DirectoryServices.DirectorySearcher
    $searcher.PageSize = 1
    $searcher.Filter = "(&(objectCategory=person)(objectClass=user)(|(sAMAccountName=$safe)(userPrincipalName=$safe)(mail=$safe)(displayName=*$safe*)))"
    @(
        "displayName","mail","userPrincipalName","sAMAccountName","userAccountControl","lockoutTime",
        "pwdLastSet","accountExpires","whenCreated","whenChanged","lastLogonTimestamp","lastLogon",
        "badPasswordTime","badPwdCount","logonCount","distinguishedName",
        "department","title","company","manager","telephoneNumber","mobile","physicalDeliveryOfficeName",
        "memberOf","proxyAddresses","employeeID","extensionAttribute1","extensionAttribute2","extensionAttribute3",
        "extensionAttribute4","extensionAttribute5","extensionAttribute6","extensionAttribute7","extensionAttribute8",
        "extensionAttribute9","extensionAttribute10","extensionAttribute11","extensionAttribute12","extensionAttribute13",
        "extensionAttribute14","extensionAttribute15","msDS-ExternalDirectoryObjectId"
    ) | ForEach-Object { $searcher.PropertiesToLoad.Add($_) | Out-Null }
    $result = $searcher.FindOne()
    if ($null -eq $result) { throw "User not found in Active Directory" }
    $props = $result.Properties
    $groups = @($props.memberof | ForEach-Object { [string]$_ } | Sort-Object -Unique)
    try {
        Add-Type -AssemblyName System.DirectoryServices.AccountManagement -ErrorAction Stop
        $ctx = New-Object System.DirectoryServices.AccountManagement.PrincipalContext([System.DirectoryServices.AccountManagement.ContextType]::Domain)
        $principal = [System.DirectoryServices.AccountManagement.UserPrincipal]::FindByIdentity($ctx, (FirstText $props.samaccountname))
        if ($null -ne $principal) {
            $authGroups = @($principal.GetAuthorizationGroups() | ForEach-Object {
                if ($_.DistinguishedName) { [string]$_.DistinguishedName } elseif ($_.SamAccountName) { [string]$_.SamAccountName } else { [string]$_.Name }
            } | Sort-Object -Unique)
            if ($authGroups.Count -gt 0) { $groups = $authGroups }
        }
    } catch { }
    $uac = 0
    try { $uac = [int](FirstText $props.useraccountcontrol) } catch { $uac = 0 }
    $disabled = (($uac -band 2) -ne 0)
    $locked = $false
    try { $locked = ([Int64](FirstText $props.lockouttime)) -gt 0 } catch { $locked = $false }
    $passwordNeverExpires = (($uac -band 65536) -ne 0)
    $cannotChangePassword = (($uac -band 64) -ne 0)
    $proxy = @($props.proxyaddresses | ForEach-Object { [string]$_ })
    $extensions = [ordered]@{}
    1..15 | ForEach-Object {
        $name = "extensionattribute$_"
        $value = FirstText $props.$name
        if (-not [string]::IsNullOrWhiteSpace($value)) { $extensions["extensionAttribute$_"] = $value }
    }
    [PSCustomObject]@{
        found = $true
        query = $Query
        sam_account_name = FirstText $props.samaccountname
        display_name = FirstText $props.displayname
        email = FirstText $props.mail
        upn = FirstText $props.userprincipalname
        employee_id = FirstText $props.employeeid
        title = FirstText $props.title
        department = FirstText $props.department
        company = FirstText $props.company
        office = FirstText $props.physicaldeliveryofficename
        phone = FirstText $props.telephonenumber
        mobile = FirstText $props.mobile
        manager = FirstText $props.manager
        enabled = -not $disabled
        locked = $locked
        password_never_expires = $passwordNeverExpires
        cannot_change_password = $cannotChangePassword
        created = DateText $props.whencreated
        changed = DateText $props.whenchanged
        last_logon = FileTimeText $props.lastlogontimestamp
        last_logon_raw = FileTimeText $props.lastlogon
        last_bad_password = FileTimeText $props.badpasswordtime
        bad_password_count = FirstText $props.badpwdcount
        logon_count = FirstText $props.logoncount
        lockout_time = FileTimeText $props.lockouttime
        password_last_set = FileTimeText $props.pwdlastset
        account_expires = FileTimeText $props.accountexpires
        distinguished_name = FirstText $props.distinguishedname
        groups = $groups
        proxy_addresses = $proxy
        extension_attributes = $extensions
        azure_object_id = FirstText $props.'msds-externaldirectoryobjectid'
        error = ""
    } | ConvertTo-Json -Compress -Depth 5
}
catch {
    [PSCustomObject]@{
        found = $false
        query = $Query
        status = "not_found"
        status_label = "Not found"
        error = $_.Exception.Message
    } | ConvertTo-Json -Compress -Depth 5
}
"""

    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "WMT_AD_USER_QUERY": normalized},
            timeout=35,
        )
        payload = json.loads((result.stdout or "").strip() or "{}")
    except Exception as exc:
        return {
            "found": False,
            "query": normalized,
            "status": "error",
            "status_label": "Lookup error",
            "error": str(exc),
        }

    groups = payload.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    groups = [str(group) for group in groups if str(group or "").strip()]
    office_groups = sorted({_license_label_from_group(group) for group in groups if _looks_like_office_entitlement(group)})

    proxy_addresses = payload.get("proxy_addresses") or []
    if isinstance(proxy_addresses, str):
        proxy_addresses = [proxy_addresses]

    extensions = payload.get("extension_attributes") or {}
    if not isinstance(extensions, dict):
        extensions = {}
    extension_license_hints = [
        f"{key}: {value}"
        for key, value in extensions.items()
        if _looks_like_office_entitlement(str(value))
    ]

    found = bool(payload.get("found"))
    enabled = bool(payload.get("enabled"))
    locked = bool(payload.get("locked"))
    status = "not_found"
    status_label = "Not found"
    if found:
        if locked:
            status = "locked"
            status_label = "Locked"
        elif not enabled:
            status = "disabled"
            status_label = "Disabled"
        else:
            status = "active"
            status_label = "Active"

    distinguished_name = text_value(payload.get("distinguished_name"))
    response = {
        "found": found,
        "query": normalized,
        "status": status,
        "status_label": status_label,
        "sam_account_name": text_value(payload.get("sam_account_name")),
        "display_name": text_value(payload.get("display_name") or normalized),
        "email": text_value(payload.get("email")),
        "upn": text_value(payload.get("upn")),
        "employee_id": text_value(payload.get("employee_id")),
        "title": text_value(payload.get("title")),
        "department": text_value(payload.get("department")),
        "company": text_value(payload.get("company")),
        "office": text_value(payload.get("office")),
        "phone": text_value(payload.get("phone")),
        "mobile": text_value(payload.get("mobile")),
        "manager": _cn_from_distinguished_name(text_value(payload.get("manager"))),
        "enabled": enabled,
        "locked": locked,
        "password_never_expires": bool(payload.get("password_never_expires")),
        "cannot_change_password": bool(payload.get("cannot_change_password")),
        "created": text_value(payload.get("created")),
        "changed": text_value(payload.get("changed")),
        "last_logon": text_value(payload.get("last_logon")),
        "last_logon_raw": text_value(payload.get("last_logon_raw")),
        "last_bad_password": text_value(payload.get("last_bad_password")),
        "bad_password_count": text_value(payload.get("bad_password_count")),
        "logon_count": text_value(payload.get("logon_count")),
        "lockout_time": text_value(payload.get("lockout_time")),
        "password_last_set": text_value(payload.get("password_last_set")),
        "account_expires": text_value(payload.get("account_expires")),
        "distinguished_name": distinguished_name,
        "organizational_unit": _ou_from_distinguished_name(distinguished_name),
        "groups": groups,
        "group_count": len(groups),
        "release_groups": sorted({_license_label_from_group(group) for group in groups if not _looks_like_office_entitlement(group)})[:80],
        "office_licenses": office_groups,
        "license_hints": extension_license_hints,
        "proxy_addresses": [str(item) for item in proxy_addresses],
        "extension_attributes": extensions,
        "azure_object_id": text_value(payload.get("azure_object_id")),
        "error": text_value(payload.get("error")),
    }
    response["last_workstation"] = find_last_user_workstation(response) if found else {}
    return response


def collect_ad_user_matches(query: str, limit: int = 40) -> dict:
    executable = powershell_executable()
    normalized = (query or "").strip()
    if executable is None:
        return {
            "query": normalized,
            "matches": [],
            "total": 0,
            "truncated": False,
            "error": "PowerShell nao encontrado neste ambiente.",
        }

    script = r"""
$Query = $env:WMT_AD_USER_QUERY
$Limit = [int]$env:WMT_AD_USER_LIMIT
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
function FirstText($Value) {
    if ($null -eq $Value) { return "" }
    $item = @($Value | Select-Object -First 1)
    if ($null -eq $item -or $item.Count -eq 0) { return "" }
    return [string]$item[0]
}
function FileTimeText($Value) {
    try {
        $raw = [Int64](FirstText $Value)
        if ($raw -le 0 -or $raw -ge 9223372036854775807) { return "" }
        return [DateTime]::FromFileTimeUtc($raw).ToLocalTime().ToString("dd-MM-yyyy HH:mm:ss")
    } catch { return "" }
}
function EscapeLdap($Value) {
    return ([string]$Value).Replace('\','\5c').Replace('*','\2a').Replace('(','\28').Replace(')','\29').Replace([string][char]0,'\00')
}
try {
    $safe = EscapeLdap $Query
    $searcher = New-Object DirectoryServices.DirectorySearcher
    $searcher.PageSize = 100
    $searcher.SizeLimit = [Math]::Max($Limit + 1, 2)
    $searcher.Filter = "(&(objectCategory=person)(objectClass=user)(|(sAMAccountName=*$safe*)(userPrincipalName=*$safe*)(mail=*$safe*)(displayName=*$safe*)(employeeID=*$safe*)(cn=*$safe*)))"
    @(
        "displayName","mail","userPrincipalName","sAMAccountName","userAccountControl","lockoutTime",
        "employeeID","department","title","company","physicalDeliveryOfficeName","lastLogonTimestamp","distinguishedName"
    ) | ForEach-Object { $searcher.PropertiesToLoad.Add($_) | Out-Null }
    $results = @($searcher.FindAll())
    $matches = @()
    foreach ($result in ($results | Select-Object -First $Limit)) {
        $props = $result.Properties
        $uac = 0
        try { $uac = [int](FirstText $props.useraccountcontrol) } catch { $uac = 0 }
        $disabled = (($uac -band 2) -ne 0)
        $locked = $false
        try { $locked = ([Int64](FirstText $props.lockouttime)) -gt 0 } catch { $locked = $false }
        $status = if ($locked) { "locked" } elseif ($disabled) { "disabled" } else { "active" }
        $matches += [PSCustomObject]@{
            sam_account_name = FirstText $props.samaccountname
            display_name = FirstText $props.displayname
            email = FirstText $props.mail
            upn = FirstText $props.userprincipalname
            employee_id = FirstText $props.employeeid
            title = FirstText $props.title
            department = FirstText $props.department
            company = FirstText $props.company
            office = FirstText $props.physicaldeliveryofficename
            status = $status
            last_logon = FileTimeText $props.lastlogontimestamp
            distinguished_name = FirstText $props.distinguishedname
        }
    }
    [PSCustomObject]@{
        query = $Query
        matches = @($matches | Sort-Object display_name, sam_account_name)
        total = $results.Count
        truncated = ($results.Count -gt $Limit)
        error = ""
    } | ConvertTo-Json -Compress -Depth 4
}
catch {
    [PSCustomObject]@{
        query = $Query
        matches = @()
        total = 0
        truncated = $false
        error = $_.Exception.Message
    } | ConvertTo-Json -Compress -Depth 4
}
"""

    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "WMT_AD_USER_QUERY": normalized, "WMT_AD_USER_LIMIT": str(limit)},
            timeout=35,
        )
        payload = json.loads((result.stdout or "").strip() or "{}")
    except Exception as exc:
        return {
            "query": normalized,
            "matches": [],
            "total": 0,
            "truncated": False,
            "error": str(exc),
        }

    matches = payload.get("matches") or []
    if isinstance(matches, dict):
        matches = [matches]
    public_matches = []
    for item in matches:
        if not isinstance(item, dict):
            continue
        public_matches.append(
            {
                "sam_account_name": text_value(item.get("sam_account_name")),
                "display_name": text_value(item.get("display_name")),
                "email": text_value(item.get("email")),
                "upn": text_value(item.get("upn")),
                "employee_id": text_value(item.get("employee_id")),
                "title": text_value(item.get("title")),
                "department": text_value(item.get("department")),
                "company": text_value(item.get("company")),
                "office": text_value(item.get("office")),
                "status": text_value(item.get("status") or "unknown"),
                "last_logon": text_value(item.get("last_logon")),
                "distinguished_name": text_value(item.get("distinguished_name")),
            }
        )

    return {
        "query": normalized,
        "matches": public_matches,
        "total": int(payload.get("total") or len(public_matches)),
        "truncated": bool(payload.get("truncated")),
        "error": text_value(payload.get("error")),
    }


def cached_ad_user_info(query: str) -> dict:
    key = _ad_user_lookup_key(query)
    return _cache_for(f"ad-user:{key}", 60, lambda: collect_ad_user_info(query))  # type: ignore[return-value]


def cached_ad_user_matches(query: str) -> dict:
    key = _ad_user_lookup_key(query)
    return _cache_for(f"ad-user-search:{key}", 60, lambda: collect_ad_user_matches(query))  # type: ignore[return-value]


def current_windows_identity() -> str:
    for args in (["whoami", "/upn"], ["whoami"]):
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            identity = (result.stdout or "").strip()
            if result.returncode == 0 and identity:
                return identity
        except Exception:
            continue
    raise HTTPException(status_code=401, detail="Unable to detect current Windows user")


def logged_user_from_host(host: str) -> str:
    target = (host or "").strip()
    if not target:
        raise HTTPException(status_code=401, detail="Client host was not detected")

    if is_loopback_client(target):
        return current_windows_identity()

    try:
        if pythoncom is not None:
            pythoncom.CoInitialize()
        if wmi:
            c = wmi.WMI(computer=target)
            sysinfo = next(iter(c.Win32_ComputerSystem()), None)
            logged_user = text_value(getattr(sysinfo, "UserName", None)) if sysinfo else ""
            if logged_user:
                return logged_user
    except Exception:
        pass
    finally:
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    executable = powershell_executable()
    if executable is None:
        raise HTTPException(status_code=401, detail="PowerShell nao encontrado para consultar usuÃ¡rio remoto")

    script = (
        "$ErrorActionPreference='Stop'; "
        f"$ComputerName={json.dumps(target)}; "
        "$computer = Get-CimInstance -ComputerName $ComputerName -ClassName Win32_ComputerSystem; "
        "[string]$computer.UserName"
    )
    result = subprocess.run(
        [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    logged_user = (result.stdout or "").strip()
    if result.returncode != 0 or not logged_user:
        detail = (result.stderr or result.stdout or "").strip()
        raise HTTPException(
            status_code=401,
            detail=f"NÃ£o foi possÃ­vel detectar usuÃ¡rio logado no cliente {target}. {friendly_error_message(detail, 'consulta do usuÃ¡rio logado')}",
        )
    return logged_user


def sso_user_from_identity(identity: str) -> dict:
    domain, username, normalized_identity = normalize_windows_identity(identity)
    ad_user = query_ad_user(username)
    groups = ad_user.get("groups", [])

    if SSO_ALLOWED_GROUPS and not group_matches(groups, SSO_ALLOWED_GROUPS):
        raise HTTPException(status_code=403, detail="User is not authorized for WMT")

    role = sso_role_for_user(username, domain, ad_user, groups)
    return upsert_sso_user({
        "id": f"sso-{domain}-{username}",
        "username": username,
        "email": ad_user.get("email") or "",
        "role": role,
        "status": "active",
        "display_name": ad_user.get("display_name") or username,
        "domain": domain,
        "windows_identity": normalized_identity,
        "upn": ad_user.get("upn") or "",
        "groups": groups,
        "auth_source": "windows",
        "role_source": "sso",
    })


def upsert_sso_user(sso_user: dict) -> dict:
    state = load_state()
    users = state.setdefault("users", [])
    now = utc_now()
    username = str(sso_user.get("username") or "").lower()
    domain = str(sso_user.get("domain") or "").lower()
    upn = str(sso_user.get("upn") or "").lower()
    email = str(sso_user.get("email") or "").lower()

    stored_user = next(
        (
            item
            for item in users
            if str(item.get("id") or "").lower() == str(sso_user.get("id") or "").lower()
            or (
                str(item.get("auth_source") or "") == "windows"
                and str(item.get("username") or "").lower() == username
                and str(item.get("domain") or "").lower() == domain
            )
            or (upn and str(item.get("upn") or "").lower() == upn)
            or (email and str(item.get("email") or "").lower() == email and str(item.get("auth_source") or "") == "windows")
        ),
        None,
    )

    if not stored_user:
        stored_user = {
            **sso_user,
            "created_at": now,
            "last_login": now,
        }
        users.append(stored_user)
        save_state(state)
        return stored_user

    manual_role = stored_user.get("role_source") == "manual"
    stored_user.update(
        {
            "email": sso_user.get("email") or stored_user.get("email", ""),
            "display_name": sso_user.get("display_name") or stored_user.get("display_name") or sso_user.get("username", ""),
            "domain": sso_user.get("domain") or stored_user.get("domain", ""),
            "windows_identity": sso_user.get("windows_identity") or stored_user.get("windows_identity", ""),
            "upn": sso_user.get("upn") or stored_user.get("upn", ""),
            "groups": sso_user.get("groups") or [],
            "auth_source": "windows",
            "last_login": now,
        }
    )
    if not stored_user.get("created_at"):
        stored_user["created_at"] = now
    if not stored_user.get("status"):
        stored_user["status"] = "active"
    if not manual_role:
        stored_user["role"] = sso_user.get("role", "viewer")
        stored_user["role_source"] = "sso"

    save_state(state)
    return stored_user


def create_session_for_user(user: dict) -> tuple[str, datetime.datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=TOKEN_TTL_SECONDS)
    session = {
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "source": user.get("auth_source", "local"),
    }
    if user.get("auth_source") == "windows":
        session["user"] = user
    else:
        session["user_id"] = user["id"]
    SESSIONS[token] = session
    return token, expires_at


def audit(action: str, username: str, details: dict | None = None) -> None:
    state = load_state()
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
    save_state(state)


def _normalize_identity_candidates(value: str) -> set[str]:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return set()
    candidates = {normalized}
    if "\\" in normalized:
        _domain, username = normalized.rsplit("\\", 1)
        if username:
            candidates.add(username)
    if "@" in normalized:
        username, _domain = normalized.split("@", 1)
        if username:
            candidates.add(username)
    return {candidate for candidate in candidates if candidate}


def _ad_user_identity_candidates(ad_user: dict) -> set[str]:
    candidates: set[str] = set()
    for key in ("sam_account_name", "upn", "email", "display_name"):
        candidates.update(_normalize_identity_candidates(str(ad_user.get(key) or "")))
    return candidates


def find_last_user_workstation(ad_user: dict) -> dict:
    candidates = _ad_user_identity_candidates(ad_user)
    if not candidates:
        return {}

    state = load_state_fields("audit")
    for item in state.get("audit") or []:
        if item.get("action") != "workstation.lookup":
            continue
        details = item.get("details") or {}
        if not isinstance(details, dict):
            continue
        current_user = str(details.get("current_user") or "").strip()
        if not current_user:
            continue
        if candidates.isdisjoint(_normalize_identity_candidates(current_user)):
            continue
        host = str(details.get("host") or "").strip()
        if not host:
            continue
        return {
            "host": host,
            "current_user": current_user,
            "ip_address": text_value(details.get("ip_address")),
            "os": text_value(details.get("os")),
            "timestamp": text_value(item.get("timestamp")),
            "source": "wmt_lookup",
        }
    return {}


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
    state = load_state()
    shares = [
        item
        for item in state.get("temp_shares", [])
        if not (
            _matches_history_host(item.get("host"), normalized_host)
            and str(item.get("share_name") or "").lower() == normalized_share.lower()
        )
    ]
    shares.insert(
        0,
        {
            "id": f"{normalized_host}:{normalized_share}",
            "host": normalized_host,
            "share_name": normalized_share,
            "drive": _normalize_drive_letter(drive),
            "path": path or f"{_normalize_drive_letter(drive)}:\\",
            "unc_path": f"\\\\{normalized_host}\\{normalized_share}",
            "source": source,
            "created_at": utc_now(),
            "expires_at": expires_at or _utc_after_minutes(BACKUP_TEMPORARY_SHARE_TTL_MINUTES),
            "cleanup_task": cleanup_task,
            "active": True,
            "last_seen": utc_now(),
        },
    )
    state["temp_shares"] = shares[:200]
    save_state(state)
    with TEMP_SHARES_CACHE_LOCK:
        TEMP_SHARES_CACHE.pop(normalized_host, None)


def _untrack_temp_share(host: str, share_name: str) -> None:
    normalized_host = _normalize_history_host(host)
    normalized_share = str(share_name or "").strip()
    state = load_state()
    state["temp_shares"] = [
        item
        for item in state.get("temp_shares", [])
        if not (
            _matches_history_host(item.get("host"), normalized_host)
            and str(item.get("share_name") or "").lower() == normalized_share.lower()
        )
    ]
    save_state(state)
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


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    session = SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = datetime.datetime.fromisoformat(session["expires_at"])
    if expires_at < datetime.datetime.utcnow():
        SESSIONS.pop(token, None)
        raise HTTPException(status_code=401, detail="Session expired")

    if session.get("user"):
        user = session["user"]
        stored_user = state_user_by_id(user.get("id"))
        if stored_user:
            user = stored_user
            session["user"] = stored_user
        if user.get("status") != "active":
            raise HTTPException(status_code=403, detail="User is not active")
        return user

    user = state_user_by_id(session.get("user_id"))
    if not user or user["status"] != "active":
        raise HTTPException(status_code=403, detail="User is not active")
    return user


def require_role(*roles: Role):
    def dependency(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return dependency


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


class LookupRequest(BaseModel):
    host: str


class ADUserLookupRequest(BaseModel):
    query: str = Field(min_length=2)


class UniversalSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=8, ge=1, le=20)


class LookupResponse(BaseModel):
    device_type: str = "workstation"
    online: bool
    hostname: str = ""
    error: str = ""
    active_directory: dict = Field(default_factory=dict)
    printer: dict = Field(default_factory=dict)
    current_user: str = ""
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    os: str = ""
    ram_gb: int = 0
    processor: str = ""
    last_boot: str = ""
    storage_total_gb: int = 0
    storage_free_gb: int = 0
    ip_address: str = ""
    mac_address: str = ""


class RemoteActionRequest(BaseModel):
    host: str
    action: str


class HostRequest(BaseModel):
    host: str


class WorkstationHistoryRequest(BaseModel):
    host: str


class DiagnosticRequest(BaseModel):
    host: str
    detailed: bool = False


class RemoteActionResponse(BaseModel):
    ok: bool
    job_id: str = ""
    status: str = ""
    action: str
    host: str
    message: str
    details: str = ""
    open_path: str = ""
    timestamp: str


class SoftwareCenterInstallRequest(BaseModel):
    host: str = "localhost"


class AppSettingsUpdateRequest(BaseModel):
    display_language: Literal["en-US", "pt-BR"] = "en-US"
    software_center_timeout_seconds: int = Field(ge=30, le=1800)
    software_center_poll_interval_seconds: int = Field(ge=5, le=300)
    update_job_timeout_minutes: int = Field(ge=5, le=720)
    backup_default_destination_path: str = ""
    scripts_enabled: dict[str, bool] = Field(default_factory=dict)
    remote_action_aliases: dict[str, str] = Field(default_factory=dict)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3)
    email: str
    role: Role = "viewer"
    password: str = Field(min_length=8)


class UserUpdateRequest(BaseModel):
    email: str | None = None
    role: Role | None = None
    status: UserStatus | None = None


class UserStatusRequest(BaseModel):
    status: UserStatus


class BackupUsersRequest(BaseModel):
    source: str = Field(min_length=1)
    remote_user: str | None = None
    remote_pass: str | None = None


class BackupOpenDestinationRequest(BaseModel):
    destination: str = Field(min_length=1)
    destination_path: str | None = None
    create_if_missing: bool = True
    remote_user: str | None = None
    remote_pass: str | None = None


class BackupCreateRequest(BaseModel):
    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    users: list[str] = Field(default_factory=list)
    destination_path: str | None = None
    exclude_patterns: list[str] = Field(default_factory=list)
    remote_user: str | None = None
    remote_pass: str | None = None


class BackupPrecheckRequest(BackupCreateRequest):
    quick: bool = False


class BackupCustomFolderRequest(BaseModel):
    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    destination_path: str = Field(min_length=1)
    exclude_patterns: list[str] = Field(default_factory=list)
    remote_user: str | None = None
    remote_pass: str | None = None


class BackupChecklistRequest(BaseModel):
    checklist: dict[str, bool] = Field(default_factory=dict)


class BackupRetryFolderRequest(BaseModel):
    profile: str = Field(min_length=1)
    folder: str = Field(min_length=1)


class BackupRetentionRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=3650)
    keep_last: int = Field(default=20, ge=0, le=500)


class MachineReplacementReportRequest(BaseModel):
    source: str = Field(min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    employee_name: str = Field(default="", max_length=200)
    technician: str = Field(default="", max_length=200)
    profiles: list[str] = Field(default_factory=list, max_length=200)
    precheck_status: str = Field(default="", max_length=40)
    precheck_message: str = Field(default="", max_length=500)
    backup_job_id: str = Field(default="", max_length=100)
    backup_status: str = Field(default="", max_length=40)
    backup_summary: str = Field(default="", max_length=2000)
    validation_status: str = Field(default="", max_length=80)
    term_generated: bool = False
    applications: list[dict[str, str]] = Field(default_factory=list, max_length=1000)


class TermsGenerateRequest(BaseModel):
    wk: str = Field(min_length=1)
    employee_name: str = ""
    term_type: Literal["responsibility", "return"] = "responsibility"


try:
    import wmi
except ImportError:
    wmi = None

try:
    import pythoncom
except ImportError:
    pythoncom = None


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
            "message": "Scripts do Software Center estÃ£o desabilitados nas configuraÃ§Ãµes do WMT.",
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
        return False, "AÃ§Ãµes remotas estÃ£o desabilitadas nas configuraÃ§Ãµes do WMT.", ""

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
        return False, f"AÃ§Ã£o '{requested_action}' excedeu o tempo limite em {host}.", details
    except Exception as exc:
        details = str(exc)
        return False, friendly_error_message(details, f"aÃ§Ã£o remota '{requested_action}' em {host}"), details

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


def remote_job_status_for_ui(status: str) -> str:
    normalized = (status or "").lower()
    if normalized in {"queued", "running", "completed", "failed", "canceled"}:
        return normalized
    return "queued"


def _public_remote_job(job: dict) -> dict:
    return {
        "id": job.get("id", ""),
        "host": job.get("host", ""),
        "action": job.get("action", ""),
        "status": remote_job_status_for_ui(str(job.get("status") or "")),
        "ok": bool(job.get("ok")) if job.get("status") in {"completed", "failed"} else False,
        "message": repair_mojibake(job.get("message", "")),
        "details": repair_mojibake(job.get("details", "")),
        "created_by": job.get("created_by", ""),
        "created_at": job.get("created_at", ""),
        "started_at": job.get("started_at", ""),
        "ended_at": job.get("ended_at", ""),
        "duration_ms": job.get("duration_ms", 0),
        "open_path": job.get("open_path", ""),
    }


def _persist_remote_job(job: dict) -> None:
    state = load_state()
    jobs = [item for item in state.get("remote_jobs", []) if item.get("id") != job.get("id")]
    jobs.insert(0, _public_remote_job(job))
    state["remote_jobs"] = jobs[:100]
    save_state(state)


def _set_remote_job(job_id: str, *, persist: bool = True, **fields: object) -> None:
    with REMOTE_JOBS_LOCK:
        job = REMOTE_JOBS.get(job_id)
        if not job:
            return
        job.update(fields)
        snapshot = dict(job)
    if persist:
        _persist_remote_job(snapshot)


def _run_remote_job(job_id: str, host: str, action: str) -> None:
    started = time.perf_counter()
    _set_remote_job(
        job_id,
        persist=False,
        status="running",
        started_at=utc_now(),
        message="Running remote action...",
    )

    ok, message, details = execute_remote_action(host, action, job_id=job_id)
    if ok:
        normalized_action = " ".join(action.strip().lower().replace("_", " ").split())
        normalized_action = REMOTE_ACTION_ALIASES.get(normalized_action, normalized_action)
        if normalized_action == "create-temp-c-share":
            open_path = f"\\\\{host}\\TempC$"
            _track_temp_share(
                host,
                "TempC$",
                "C",
                "C:\\",
                _utc_after_minutes(BACKUP_TEMPORARY_SHARE_TTL_MINUTES),
                "remote_action",
                "WMT_Remove_TempC",
            )
            message = f"{message} Active folder: {open_path}"
            details = "\n".join(item for item in [details, f"Active folder: {open_path}"] if item).strip()
            _set_remote_job(job_id, persist=False, open_path=open_path)
        elif normalized_action == "remove-temp-c-share":
            _untrack_temp_share(host, "TempC$")
    duration_ms = int((time.perf_counter() - started) * 1000)
    with REMOTE_JOBS_LOCK:
        current_status = REMOTE_JOBS.get(job_id, {}).get("status")
    if current_status == "canceled":
        return
    _set_remote_job(
        job_id,
        status="completed" if ok else "failed",
        ok=ok,
        message=message,
        details=details,
        ended_at=utc_now(),
        duration_ms=duration_ms,
    )


def create_remote_job(host: str, action: str, username: str) -> dict:
    canonical_action = _canonical_remote_action(action)
    normalized_host = host.strip().upper()
    job = {
        "id": f"RJ-{secrets.token_hex(4).upper()}",
        "host": normalized_host,
        "action": canonical_action,
        "status": "queued",
        "ok": False,
        "message": "Remote action added to queue.",
        "details": "",
        "created_by": username,
        "created_at": utc_now(),
        "started_at": "",
        "ended_at": "",
        "duration_ms": 0,
        "open_path": f"\\\\{host}\\TempC$" if canonical_action == "create-temp-c-share" else "",
    }

    with REMOTE_JOBS_LOCK:
        if canonical_action == "create-temp-c-share":
            existing = next(
                (
                    current
                    for current in REMOTE_JOBS.values()
                    if str(current.get("host") or "").strip().upper() == normalized_host
                    and current.get("action") == canonical_action
                    and current.get("status") in {"queued", "running"}
                ),
                None,
            )
            if existing:
                return _public_remote_job(existing)
        REMOTE_JOBS[job["id"]] = job

    _persist_remote_job(job)
    thread = threading.Thread(target=_run_remote_job, args=(job["id"], normalized_host, canonical_action), daemon=True)
    thread.start()
    return _public_remote_job(job)


def update_job_status_for_ui(status: str) -> str:
    normalized = (status or "").lower()
    if normalized in {"queued", "running", "completed", "failed", "canceled"}:
        return normalized
    return "queued"


def _public_update_job(job: dict) -> dict:
    return {
        "id": job.get("id", ""),
        "host": job.get("host", ""),
        "status": update_job_status_for_ui(str(job.get("status") or "")),
        "ok": bool(job.get("ok")) if job.get("status") in {"completed", "failed"} else False,
        "message": job.get("message", ""),
        "details": job.get("details", ""),
        "created_by": job.get("created_by", ""),
        "created_at": job.get("created_at", ""),
        "started_at": job.get("started_at", ""),
        "ended_at": job.get("ended_at", ""),
        "duration_ms": job.get("duration_ms", 0),
        "progress": int(job.get("progress") or 0),
        "pending_updates": int(job.get("pending_updates") or 0),
        "updates": job.get("updates") or [],
    }


def _persist_update_job(job: dict) -> None:
    state = load_state()
    jobs = [item for item in state.get("update_jobs", []) if item.get("id") != job.get("id")]
    jobs.insert(0, _public_update_job(job))
    state["update_jobs"] = jobs[:100]
    save_state(state)


def _set_update_job(job_id: str, **fields: object) -> None:
    with UPDATE_JOBS_LOCK:
        job = UPDATE_JOBS.get(job_id)
        if not job:
            return
        job.update(fields)
        snapshot = dict(job)
    _persist_update_job(snapshot)


def _progress_from_updates(updates: list[dict]) -> int:
    values = [
        int(item.get("percentComplete") or item.get("percent_complete") or 0)
        for item in updates
        if isinstance(item, dict)
    ]
    if not values:
        return 0
    return max(0, min(99, int(sum(values) / len(values))))


def _run_update_job(job_id: str, host: str) -> None:
    started = time.perf_counter()
    settings = current_settings()
    poll_interval = int(settings.get("software_center_poll_interval_seconds") or 10)
    timeout_seconds = int(settings.get("update_job_timeout_minutes") or 120) * 60

    _set_update_job(job_id, status="running", started_at=utc_now(), message="Iniciando updates pelo Software Center...")
    install_result = run_software_center_script(host, "install-updates")
    if install_result.get("ok") is False:
        _set_update_job(
            job_id,
            status="failed",
            ok=False,
            message=install_result.get("message") or "Falha ao iniciar updates.",
            details=install_result.get("details", ""),
            ended_at=utc_now(),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return

    _set_update_job(
        job_id,
        message=install_result.get("message") or "Installation started. Monitoring progress...",
        pending_updates=int(install_result.get("pendingUpdates") or 0),
    )

    while True:
        elapsed = time.perf_counter() - started
        if elapsed > timeout_seconds:
            _set_update_job(
                job_id,
                status="failed",
                ok=False,
                message=f"Tempo limite excedido monitorando updates em {host}.",
                ended_at=utc_now(),
                duration_ms=int(elapsed * 1000),
            )
            return

        time.sleep(max(5, poll_interval))
        status_result = run_software_center_script(host, "status")
        if status_result.get("ok") is False:
            _set_update_job(
                job_id,
                status="failed",
                ok=False,
                message=status_result.get("message") or "Falha ao monitorar updates.",
                details=status_result.get("details", ""),
                ended_at=utc_now(),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return

        pending = int(status_result.get("pendingUpdates") or 0)
        updates = status_result.get("updates") or []
        progress = 100 if pending == 0 else _progress_from_updates(updates)
        _set_update_job(
            job_id,
            status="running",
            message=f"Monitorando updates em {host}: {pending} pendente(s).",
            pending_updates=pending,
            updates=updates,
            progress=progress,
        )

        if pending == 0:
            _set_update_job(
                job_id,
                status="completed",
                ok=True,
                message="Updates completed or no pending updates in Software Center.",
                progress=100,
                pending_updates=0,
                updates=[],
                ended_at=utc_now(),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return


def create_update_job(host: str, username: str) -> dict:
    job = {
        "id": f"UP-{secrets.token_hex(4).upper()}",
        "host": host,
        "status": "queued",
        "ok": False,
        "message": "Update adicionado Ã  fila.",
        "details": "",
        "created_by": username,
        "created_at": utc_now(),
        "started_at": "",
        "ended_at": "",
        "duration_ms": 0,
        "progress": 0,
        "pending_updates": 0,
        "updates": [],
    }
    with UPDATE_JOBS_LOCK:
        UPDATE_JOBS[job["id"]] = job
    _persist_update_job(job)
    thread = threading.Thread(target=_run_update_job, args=(job["id"], host), daemon=True)
    thread.start()
    return _public_update_job(job)


def ping_host(host: str) -> bool:
    for timeout_ms in (2500, 4500):
        try:
            output = subprocess.check_output(
                ["ping", "-n", "1", "-w", str(timeout_ms), host],
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                timeout=(timeout_ms / 1000) + 1.5,
            )
            if "TTL=" in output:
                return True
        except Exception:
            continue
    return False


def text_value(value: object) -> str:
    return "" if value is None else str(value).strip()


def repair_mojibake(value: object) -> str:
    text = "" if value is None else str(value)
    if "Ã" not in text and "Â" not in text:
        return text
    try:
        return text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text


def _clone_payload(payload: object) -> object:
    try:
        return copy.deepcopy(payload)
    except Exception:
        return payload


def _cache_get(key: str, ttl_seconds: int) -> object | None:
    now_ts = time.time()
    with RESPONSE_CACHE_LOCK:
        item = RESPONSE_CACHE.get(key)
        if not item:
            return None
        if now_ts - float(item.get("ts") or 0) > ttl_seconds:
            RESPONSE_CACHE.pop(key, None)
            return None
        return _clone_payload(item.get("value"))


def _cache_set(key: str, value: object) -> object:
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[key] = {"ts": time.time(), "value": _clone_payload(value)}
        if len(RESPONSE_CACHE) > 300:
            oldest_keys = sorted(RESPONSE_CACHE, key=lambda item_key: RESPONSE_CACHE[item_key].get("ts") or 0)[:60]
            for item_key in oldest_keys:
                RESPONSE_CACHE.pop(item_key, None)
    return value


def _cache_for(key: str, ttl_seconds: int, factory) -> object:
    cached = _cache_get(key, ttl_seconds)
    if cached is not None:
        return cached

    with RESPONSE_CACHE_INFLIGHT_LOCK:
        pending = RESPONSE_CACHE_INFLIGHT.get(key)
        if pending is None:
            pending = threading.Event()
            RESPONSE_CACHE_INFLIGHT[key] = pending
            is_owner = True
        else:
            is_owner = False

    if not is_owner:
        pending.wait(timeout=120)
        cached = _cache_get(key, ttl_seconds)
        if cached is not None:
            return cached

    try:
        return _cache_set(key, factory())
    finally:
        if is_owner:
            with RESPONSE_CACHE_INFLIGHT_LOCK:
                RESPONSE_CACHE_INFLIGHT.pop(key, None)
                pending.set()


def _cache_delete_prefix(prefix: str) -> None:
    with RESPONSE_CACHE_LOCK:
        for key in list(RESPONSE_CACHE.keys()):
            if key.startswith(prefix):
                RESPONSE_CACHE.pop(key, None)


def snmp_available() -> bool:
    return True


def ber_length(length: int) -> bytes:
    if length < 128:
        return bytes([length])
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def ber_tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + ber_length(len(value)) + value


def ber_integer(value: int) -> bytes:
    if value == 0:
        raw = b"\x00"
    else:
        raw = value.to_bytes((value.bit_length() + 7) // 8, "big", signed=False)
        if raw[0] & 0x80:
            raw = b"\x00" + raw
    return ber_tlv(0x02, raw)


def ber_octet_string(value: str) -> bytes:
    return ber_tlv(0x04, value.encode("utf-8", errors="replace"))


def ber_null() -> bytes:
    return ber_tlv(0x05, b"")


def ber_oid(oid: str) -> bytes:
    parts = [int(item) for item in oid.strip(".").split(".") if item]
    if len(parts) < 2:
        raise ValueError("OID invalido")
    encoded = bytearray([parts[0] * 40 + parts[1]])
    for part in parts[2:]:
        stack = [part & 0x7F]
        part >>= 7
        while part:
            stack.append(0x80 | (part & 0x7F))
            part >>= 7
        encoded.extend(reversed(stack))
    return ber_tlv(0x06, bytes(encoded))


def read_ber_length(data: bytes, offset: int) -> tuple[int, int]:
    first = data[offset]
    offset += 1
    if first < 128:
        return first, offset
    count = first & 0x7F
    return int.from_bytes(data[offset:offset + count], "big"), offset + count


def read_ber_tlv(data: bytes, offset: int) -> tuple[int, bytes, int]:
    tag = data[offset]
    length, value_offset = read_ber_length(data, offset + 1)
    end = value_offset + length
    return tag, data[value_offset:end], end


def decode_ber_integer(value: bytes) -> int:
    return int.from_bytes(value or b"\x00", "big", signed=bool(value and value[0] & 0x80))


def decode_ber_oid(value: bytes) -> str:
    if not value:
        return ""
    first = value[0]
    parts = [first // 40, first % 40]
    current = 0
    for byte in value[1:]:
        current = (current << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(current)
            current = 0
    return ".".join(str(part) for part in parts)


def decode_ber_value(tag: int, value: bytes) -> str:
    if tag in {0x02, 0x41, 0x42, 0x43, 0x46}:
        return str(decode_ber_integer(value))
    if tag == 0x04:
        return value.decode("utf-8", errors="replace").strip("\x00").strip()
    if tag == 0x05:
        return ""
    if tag == 0x06:
        return decode_ber_oid(value)
    return value.hex()


def raw_snmp_request(host: str, oid: str, pdu_tag: int, community: str = "public", timeout: float = 1.0) -> tuple[str, str] | None:
    request_id = secrets.randbelow(2_000_000_000)
    varbind = ber_tlv(0x30, ber_oid(oid) + ber_null())
    varbind_list = ber_tlv(0x30, varbind)
    pdu = ber_tlv(pdu_tag, ber_integer(request_id) + ber_integer(0) + ber_integer(0) + varbind_list)
    message = ber_tlv(0x30, ber_integer(0) + ber_octet_string(community) + pdu)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(message, (host, 161))
        data, _addr = sock.recvfrom(8192)

    tag, message_value, _end = read_ber_tlv(data, 0)
    if tag != 0x30:
        return None
    offset = 0
    _version_tag, _version_value, offset = read_ber_tlv(message_value, offset)
    _community_tag, _community_value, offset = read_ber_tlv(message_value, offset)
    response_tag, response_value, _offset = read_ber_tlv(message_value, offset)
    if response_tag != 0xA2:
        return None
    pdu_offset = 0
    _request_tag, _request_value, pdu_offset = read_ber_tlv(response_value, pdu_offset)
    _error_tag, error_value, pdu_offset = read_ber_tlv(response_value, pdu_offset)
    _error_index_tag, _error_index_value, pdu_offset = read_ber_tlv(response_value, pdu_offset)
    if decode_ber_integer(error_value) != 0:
        return None
    _list_tag, list_value, _pdu_end = read_ber_tlv(response_value, pdu_offset)
    _vb_tag, vb_value, _list_end = read_ber_tlv(list_value, 0)
    vb_offset = 0
    oid_tag, oid_value, vb_offset = read_ber_tlv(vb_value, vb_offset)
    value_tag, value_value, _vb_end = read_ber_tlv(vb_value, vb_offset)
    if oid_tag != 0x06:
        return None
    return decode_ber_oid(oid_value), decode_ber_value(value_tag, value_value)


def snmp_get(host: str, oid: str, community: str = "public", timeout: int = 1, retries: int = 0) -> str:
    for _attempt in range(max(1, retries + 1)):
        try:
            response = raw_snmp_request(host, oid, 0xA0, community=community, timeout=float(timeout))
            return response[1] if response else ""
        except Exception:
            continue
    return ""


def snmp_walk(host: str, oid: str, community: str = "public", timeout: int = 1, retries: int = 0, limit: int = 80) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    current_oid = oid
    try:
        while len(rows) < limit:
            response = raw_snmp_request(host, current_oid, 0xA1, community=community, timeout=float(timeout))
            if not response:
                break
            next_oid, value = response
            if not next_oid.startswith(oid + "."):
                break
            rows.append((next_oid, value))
            current_oid = next_oid
    except Exception:
        return rows
    return rows


def oid_index(oid: str) -> str:
    return oid.rsplit(".", 1)[-1] if "." in oid else oid


def normalize_supply_level(raw_level: str, raw_max: str) -> tuple[int | None, str]:
    try:
        level = int(str(raw_level).strip())
    except ValueError:
        return None, raw_level or ""
    try:
        max_value = int(str(raw_max).strip())
    except ValueError:
        max_value = 0

    if level < 0:
        special = {-1: "other", -2: "unknown", -3: "some remaining"}
        return None, special.get(level, str(level))
    if max_value <= 0:
        return None, str(level)
    return max(0, min(100, round((level / max_value) * 100))), f"{level}/{max_value}"


def collect_printer_info(host: str) -> dict:
    if not snmp_available():
        return {"detected": False, "error": "pysnmp nao disponivel no backend."}

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="snmp")
    try:
        initial = {
            "sys_descr": executor.submit(snmp_get, host, "1.3.6.1.2.1.1.1.0"),
            "sys_name": executor.submit(snmp_get, host, "1.3.6.1.2.1.1.5.0"),
        }
        sys_descr = str(future_result(initial["sys_descr"], 1.3, "") or "")
        sys_name = str(future_result(initial["sys_name"], 1.3, "") or "")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    if not sys_descr and not sys_name:
        return {"detected": False, "error": "SNMP nao respondeu."}

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="snmp")
    try:
        scalar_futures = {
            "printer_name": executor.submit(snmp_get, host, "1.3.6.1.2.1.43.5.1.1.16.1"),
            "serial": executor.submit(snmp_get, host, "1.3.6.1.2.1.43.5.1.1.17.1"),
            "location": executor.submit(snmp_get, host, "1.3.6.1.2.1.1.6.0"),
            "contact": executor.submit(snmp_get, host, "1.3.6.1.2.1.1.4.0"),
            "page_count": executor.submit(snmp_get, host, "1.3.6.1.2.1.43.10.2.1.4.1.1"),
            "uptime": executor.submit(snmp_get, host, "1.3.6.1.2.1.1.3.0"),
            "status_primary": executor.submit(snmp_get, host, "1.3.6.1.2.1.25.3.2.1.5.1"),
            "status_secondary": executor.submit(snmp_get, host, "1.3.6.1.2.1.25.3.5.1.1.1"),
        }
        walk_futures = {
            "descriptions": executor.submit(snmp_walk, host, "1.3.6.1.2.1.43.11.1.1.6.1"),
            "max_values": executor.submit(snmp_walk, host, "1.3.6.1.2.1.43.11.1.1.8.1"),
            "levels": executor.submit(snmp_walk, host, "1.3.6.1.2.1.43.11.1.1.9.1"),
            "supply_types": executor.submit(snmp_walk, host, "1.3.6.1.2.1.43.11.1.1.5.1"),
        }

        printer_name = str(future_result(scalar_futures["printer_name"], 1.5, "") or "")
        serial = str(future_result(scalar_futures["serial"], 1.5, "") or "")
        location = str(future_result(scalar_futures["location"], 1.5, "") or "")
        contact = str(future_result(scalar_futures["contact"], 1.5, "") or "")
        page_count = str(future_result(scalar_futures["page_count"], 1.5, "") or "")
        uptime = str(future_result(scalar_futures["uptime"], 1.5, "") or "")
        status = str(future_result(scalar_futures["status_primary"], 1.5, "") or "") or str(future_result(scalar_futures["status_secondary"], 0.2, "") or "")

        descriptions = {oid_index(oid): value for oid, value in (future_result(walk_futures["descriptions"], 3.0, []) or [])}
        max_values = {oid_index(oid): value for oid, value in (future_result(walk_futures["max_values"], 3.0, []) or [])}
        levels = {oid_index(oid): value for oid, value in (future_result(walk_futures["levels"], 3.0, []) or [])}
        supply_types = {oid_index(oid): value for oid, value in (future_result(walk_futures["supply_types"], 3.0, []) or [])}
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    supplies = []
    for index, description in descriptions.items():
        percent, display_level = normalize_supply_level(levels.get(index, ""), max_values.get(index, ""))
        if not description and percent is None:
            continue
        supplies.append(
            {
                "index": index,
                "description": description or f"Supply {index}",
                "type": supply_types.get(index, ""),
                "level": levels.get(index, ""),
                "max": max_values.get(index, ""),
                "percent": percent,
                "display_level": display_level,
            }
        )

    has_printer_mib = bool(printer_name or serial or supplies or page_count)
    signature = f"{sys_descr} {sys_name}".lower()
    detected = has_printer_mib or any(word in signature for word in ["printer", "impressora", "laserjet", "officejet", "lexmark", "xerox", "ricoh", "zebra"])
    if not detected:
        return {"detected": False, "error": "Dispositivo SNMP encontrado, mas nao parece ser impressora."}

    return {
        "detected": True,
        "name": printer_name or sys_name or host,
        "hostname": sys_name or host,
        "model": sys_descr,
        "serial_number": serial,
        "location": location,
        "contact": contact,
        "page_count": int(page_count) if str(page_count).isdigit() else 0,
        "status": status,
        "uptime": uptime,
        "supplies": supplies[:20],
        "raw": {"sys_descr": sys_descr, "sys_name": sys_name},
    }


def looks_like_printer_host(host: str) -> bool:
    lowered = host.lower()
    if any(token in lowered for token in ["prt", "print", "printer", "imp", "impressora"]):
        return True
    for port in (9100, 515, 631):
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return True
        except OSError:
            continue
    return False


def future_result(future: concurrent.futures.Future, timeout: float, default: object = None) -> object:
    try:
        return future.result(timeout=timeout)
    except Exception:
        return default


def collect_active_directory_info(host: str) -> dict:
    executable = powershell_executable()
    if executable is None:
        return {
            "found": False,
            "name": host,
            "enabled": "",
            "created": "",
            "last_logon": "",
            "distinguished_name": "",
            "organizational_unit": "",
            "error": "PowerShell nao encontrado neste ambiente.",
        }

    script = r"""
$ComputerName = $env:WMT_AD_COMPUTER
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    Import-Module ActiveDirectory -WarningAction SilentlyContinue
    $computer = Get-ADComputer $ComputerName -Properties LastLogonDate, Created, Enabled, DistinguishedName
    $ou = (($computer.DistinguishedName -split '(?<!\\),') | Where-Object { $_ -like 'OU=*' }) -join ','
    [PSCustomObject]@{
        found = $true
        name = $computer.Name
        enabled = if ($computer.Enabled) { "Enabled" } else { "Disabled" }
        created = if ($computer.Created) { $computer.Created.ToString("dd-MM-yyyy HH:mm:ss") } else { "" }
        last_logon = if ($computer.LastLogonDate) { $computer.LastLogonDate.ToString("dd-MM-yyyy HH:mm:ss") } else { "" }
        distinguished_name = if ($computer.DistinguishedName) { $computer.DistinguishedName } else { "" }
        organizational_unit = $ou
        error = ""
    } | ConvertTo-Json -Compress
}
catch {
    [PSCustomObject]@{
        found = $false
        name = $ComputerName
        enabled = ""
        created = ""
        last_logon = ""
        distinguished_name = ""
        organizational_unit = ""
        error = $_.Exception.Message
    } | ConvertTo-Json -Compress
}
"""

    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "WMT_AD_COMPUTER": host},
            timeout=30,
        )
        payload = json.loads((result.stdout or "").strip() or "{}")
        return {
            "found": bool(payload.get("found")),
            "name": text_value(payload.get("name") or host),
            "enabled": text_value(payload.get("enabled")),
            "created": text_value(payload.get("created")),
            "last_logon": text_value(payload.get("last_logon")),
            "distinguished_name": text_value(payload.get("distinguished_name")),
            "organizational_unit": text_value(payload.get("organizational_unit")),
            "error": text_value(payload.get("error")),
        }
    except Exception as exc:
        return {
            "found": False,
            "name": host,
            "enabled": "",
            "created": "",
            "last_logon": "",
            "distinguished_name": "",
            "organizational_unit": "",
            "error": str(exc),
        }


def collect_wmi_workstation_info(host: str) -> dict:
    info = {"device_type": "workstation", "online": True, "hostname": host}

    if pythoncom is not None:
        pythoncom.CoInitialize()

    try:
        c = wmi.WMI(computer=host) if wmi else None
        if not c:
            return {**info, "hostname": host}

        sysinfo = next(iter(c.Win32_ComputerSystem()), None)
        bios = next(iter(c.Win32_BIOS()), None)
        osinfo = next(iter(c.Win32_OperatingSystem()), None)
        proc = next(iter(c.Win32_Processor()), None)
        disk = next(iter(c.Win32_LogicalDisk(DeviceID="C:")), None)

        hostname = getattr(sysinfo, "DNSHostName", None) or getattr(sysinfo, "Name", None) or host
        info.update(
            {
                "hostname": text_value(hostname),
                "current_user": text_value(getattr(sysinfo, "UserName", None)) if sysinfo else "",
                "manufacturer": text_value(getattr(sysinfo, "Manufacturer", None)) if sysinfo else "",
                "model": text_value(getattr(sysinfo, "Model", None)) if sysinfo else "",
                "serial_number": text_value(getattr(bios, "SerialNumber", None)) if bios else "",
                "os": text_value(getattr(osinfo, "Caption", None)) if osinfo else "",
                "ram_gb": int(float(getattr(sysinfo, "TotalPhysicalMemory", 0)) / (1024**3)) if sysinfo else 0,
                "processor": text_value(getattr(proc, "Name", None)) if proc else "",
                "last_boot": text_value(getattr(osinfo, "LastBootUpTime", None)) if osinfo else "",
                "storage_total_gb": int(float(getattr(disk, "Size", 0)) / (1024**3)) if disk else 0,
                "storage_free_gb": int(float(getattr(disk, "FreeSpace", 0)) / (1024**3)) if disk else 0,
            }
        )

        nics = list(c.Win32_NetworkAdapterConfiguration(IPEnabled=True))
        if nics:
            nic = nics[0]
            info["ip_address"] = nic.IPAddress[0] if hasattr(nic, "IPAddress") and nic.IPAddress else ""
            info["mac_address"] = text_value(getattr(nic, "MACAddress", None))

        return info
    finally:
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def collect_machine_info(host: str) -> dict:
    info = {"device_type": "workstation", "online": False, "hostname": host}

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="lookup")
    try:
        ad_future = executor.submit(collect_active_directory_info, host)
        ping_future = executor.submit(ping_host, host)

        if not bool(future_result(ping_future, 8.0, False)):
            active_directory = future_result(ad_future, 4.0, {}) or {}
            return {
                **info,
                "error": "Host is offline or unreachable",
                "active_directory": active_directory,
            }

        info["online"] = True
        printer_likely_future = executor.submit(looks_like_printer_host, host)
        wmi_future = executor.submit(collect_wmi_workstation_info, host)
        printer_future: concurrent.futures.Future | None = None

        if bool(future_result(printer_likely_future, 1.0, False)):
            printer_future = executor.submit(collect_printer_info, host)
            printer = future_result(printer_future, 4.0, {}) or {}
            if isinstance(printer, dict) and printer.get("detected"):
                active_directory = future_result(ad_future, 2.0, {}) or {}
                return {
                    **info,
                    "device_type": "printer",
                    "hostname": printer.get("hostname") or host,
                    "manufacturer": "",
                    "model": printer.get("model", ""),
                    "serial_number": printer.get("serial_number", ""),
                    "ip_address": host,
                    "active_directory": active_directory,
                    "printer": printer,
                }

        wmi_info = future_result(wmi_future, 8.0, None)
        if isinstance(wmi_info, dict):
            active_directory = future_result(ad_future, 2.0, {}) or {}
            return {**wmi_info, "active_directory": active_directory}

        print("[collect_machine_info] WMI lookup timed out or failed for", host)
        if printer_future is None:
            printer_future = executor.submit(collect_printer_info, host)
        printer = future_result(printer_future, 4.0, {}) or {}
        if isinstance(printer, dict) and printer.get("detected"):
            active_directory = future_result(ad_future, 2.0, {}) or {}
            return {
                **info,
                "device_type": "printer",
                "online": True,
                "hostname": printer.get("hostname") or host,
                "manufacturer": "",
                "model": printer.get("model", ""),
                "serial_number": printer.get("serial_number", ""),
                "ip_address": host,
                "active_directory": active_directory,
                "printer": printer,
            }

        active_directory = future_result(ad_future, 2.0, {}) or {}
        return {
            **info,
            "online": False,
            "hostname": host,
            "error": "Host is online, but WMI is unavailable",
            "active_directory": active_directory,
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def cached_collect_machine_info(host: str) -> dict:
    normalized = host.strip().upper()
    return _cache_for(f"lookup:{normalized}", 45, lambda: collect_machine_info(host))  # type: ignore[return-value]


def run_diagnostic_pack(host: str, run_cleanup: bool = False, include_details: bool = False) -> dict:
    executable = powershell_executable()
    if executable is None:
        raise RuntimeError("PowerShell nao encontrado neste ambiente.")
    script_path = SCRIPT_DIR / "diagnostic_pack.ps1"
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
    ]
    if run_cleanup:
        command.append("-RunCleanup")
    if include_details:
        command.append("-IncludeDetails")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    payload_text = (result.stdout or "").strip()
    try:
        payload = json.loads(payload_text or "{}")
    except json.JSONDecodeError:
        payload = {"host": host, "checks": [], "inventory": {}, "error": payload_text or (result.stderr or "").strip()}
    if result.returncode != 0 and not payload.get("error"):
        payload["error"] = (result.stderr or "").strip() or "Falha ao executar diagnostico."
    return payload


def collect_performance_sample(host: str) -> dict:
    if not script_enabled("performance_monitor"):
        return {
            "host": host,
            "requested_host": host,
            "generated_at": utc_now(),
            "ok": False,
            "message": "Monitoramento de performance esta desabilitado nas configuracoes do WMT.",
        }

    try:
        result = run_powershell_script("performance_sample.ps1", host, "sample", timeout=45)
    except subprocess.TimeoutExpired as exc:
        details = "\n".join(item for item in [exc.stdout or "", exc.stderr or ""] if item).strip()
        raise HTTPException(
            status_code=504,
            detail=friendly_error_message(details or f"Tempo limite excedido ao coletar performance em {host}.", "monitoramento de performance"),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=friendly_error_message(str(exc), "monitoramento de performance"))

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail=friendly_error_message(stdout or stderr or "A coleta de performance nao retornou JSON valido.", "monitoramento de performance"),
        )

    payload["ok"] = result.returncode == 0
    if result.returncode != 0:
        payload["message"] = friendly_error_message(stderr or payload.get("message") or "Falha ao coletar performance.", "monitoramento de performance")
    return payload


def cached_diagnostic_pack(host: str, include_details: bool = False) -> dict:
    normalized = validate_backup_host(host)
    ttl_seconds = 120 if include_details else 75
    return _cache_for(
        f"diagnostic:{normalized}:details={int(include_details)}",
        ttl_seconds,
        lambda: run_diagnostic_pack(normalized, run_cleanup=False, include_details=include_details),
    )  # type: ignore[return-value]


@app.get("/api/performance-sample")
def performance_sample_endpoint(
    host: str = Query(default="localhost"),
    user: dict = Depends(current_user),
):
    target = (host or "").strip() or "localhost"
    target = validate_backup_host(target)
    return collect_performance_sample(target)


def cached_software_center_status(host: str) -> dict:

    normalized = host.strip() or "localhost"
    return _cache_for(
        f"software-center:{normalized.upper()}:status",
        60,
        lambda: run_software_center_script(normalized, "status"),
    )  # type: ignore[return-value]


def _public_diagnostic_job(job: dict) -> dict:
    return {
        "id": job.get("id", ""),
        "host": job.get("host", ""),
        "status": job.get("status", "queued"),
        "detailed": bool(job.get("detailed")),
        "message": job.get("message", ""),
        "error": job.get("error", ""),
        "created_by": job.get("created_by", ""),
        "created_at": job.get("created_at", ""),
        "started_at": job.get("started_at", ""),
        "ended_at": job.get("ended_at", ""),
        "duration_ms": job.get("duration_ms", 0),
        "payload": job.get("payload"),
    }


def _trim_diagnostic_jobs() -> None:
    if len(DIAGNOSTIC_JOBS) <= 80:
        return
    removable = sorted(
        DIAGNOSTIC_JOBS.values(),
        key=lambda item: item.get("ended_at") or item.get("created_at") or "",
    )[:20]
    for job in removable:
        DIAGNOSTIC_JOBS.pop(job.get("id"), None)


def _set_diagnostic_job(job_id: str, **fields) -> dict | None:
    with DIAGNOSTIC_JOBS_LOCK:
        job = DIAGNOSTIC_JOBS.get(job_id)
        if not job:
            return None
        job.update(fields)
        return _public_diagnostic_job(job)


def _run_diagnostic_job(job_id: str, host: str, detailed: bool) -> None:
    _set_diagnostic_job(job_id, status="queued", message="Aguardando vaga para coletar diagnostico...")
    with DIAGNOSTIC_JOB_SEMAPHORE:
        started = time.time()
        _set_diagnostic_job(job_id, status="running", message="Coletando diagnostico...", started_at=utc_now())
        try:
            payload = run_diagnostic_pack(host, run_cleanup=False, include_details=detailed)
            _cache_set(f"diagnostic:{host}:details={int(detailed)}", payload)
            _set_diagnostic_job(
                job_id,
                status="completed",
                message="Diagnostico concluido.",
                payload=payload,
                ended_at=utc_now(),
                duration_ms=int((time.time() - started) * 1000),
            )
        except Exception as exc:
            _set_diagnostic_job(
                job_id,
                status="failed",
                message="Falha ao executar diagnostico.",
                error=str(exc),
                payload={"host": host, "checks": [], "error": str(exc)},
                ended_at=utc_now(),
                duration_ms=int((time.time() - started) * 1000),
            )


def create_diagnostic_job(host: str, detailed: bool, username: str) -> dict:
    normalized = validate_backup_host(host)
    cached = _cache_get(f"diagnostic:{normalized}:details={int(detailed)}", 120 if detailed else 75)
    if cached is not None:
        return {
            "id": f"cache-{secrets.token_hex(4)}",
            "host": normalized,
            "status": "completed",
            "detailed": detailed,
            "message": "Resultado recente reaproveitado.",
            "error": "",
            "created_by": username,
            "created_at": utc_now(),
            "started_at": "",
            "ended_at": utc_now(),
            "duration_ms": 0,
            "payload": cached,
        }

    with DIAGNOSTIC_JOBS_LOCK:
        existing = next(
            (
                item
                for item in DIAGNOSTIC_JOBS.values()
                if item.get("host") == normalized
                and bool(item.get("detailed")) == bool(detailed)
                and item.get("status") in {"queued", "running"}
            ),
            None,
        )
        if existing:
            return _public_diagnostic_job(existing)

    job = {
        "id": secrets.token_hex(8),
        "host": normalized,
        "status": "queued",
        "detailed": detailed,
        "message": "Diagnostico na fila.",
        "error": "",
        "created_by": username,
        "created_at": utc_now(),
        "started_at": "",
        "ended_at": "",
        "duration_ms": 0,
        "payload": None,
    }
    with DIAGNOSTIC_JOBS_LOCK:
        DIAGNOSTIC_JOBS[job["id"]] = job
        _trim_diagnostic_jobs()
    thread = threading.Thread(target=_run_diagnostic_job, args=(job["id"], normalized, detailed), daemon=True)
    thread.start()
    return _public_diagnostic_job(job)


def build_wmt_health(host: str) -> dict:
    checks: list[dict] = []
    checks.append({"name": "Backend", "status": "ok", "message": "Backend local respondeu."})
    checks.append({
        "name": "Updater",
        "status": "ok" if (UPDATES_DIR / "latest.json").exists() else "warn",
        "message": "Manifesto de update encontrado." if (UPDATES_DIR / "latest.json").exists() else "Manifesto de update nao encontrado.",
    })

    diagnostic = cached_diagnostic_pack(host, include_details=False)
    for item in diagnostic.get("checks", []):
        checks.append(item)

    return {
        "host": host,
        "generated_at": utc_now(),
        "checks": checks,
    }


def terms_template_path(term_type: str) -> Path:
    entry = TERM_TYPES.get(term_type)
    if not entry:
        raise HTTPException(status_code=400, detail="Unsupported term type")

    path = Path(entry["template"]())
    if term_type == "return" and (not str(path).strip() or str(path) == "."):
        responsibility_path = TERMS_RESPONSIBILITY_TEMPLATE_PATH
        try:
            for candidate in responsibility_path.parent.glob("*.docx"):
                if "DEVOL" in candidate.name.upper():
                    return candidate
        except OSError:
            pass

    if not str(path).strip() or str(path) == ".":
        config_name = "TERMS_RETURN_TEMPLATE_PATH" if term_type == "return" else "TERMS_RESPONSIBILITY_TEMPLATE_PATH"
        raise HTTPException(
            status_code=500,
            detail=f"Template path is not configured. Configure {config_name}.",
        )

    return path


def build_terms_payload(wk: str, employee_name: str = "") -> dict:
    host = validate_backup_host(wk)
    lookup = collect_machine_info(host)

    hostname = lookup.get("hostname") or host
    serial = lookup.get("serial_number") or ""
    model = lookup.get("model") or ""
    manufacturer = lookup.get("manufacturer") or ""
    if not serial or not model or not manufacturer:
        fallback = query_terms_inventory_powershell(host)
        hostname = fallback.get("hostname") or hostname
        serial = serial or fallback.get("serial_number", "")
        model = model or fallback.get("model", "")
        manufacturer = manufacturer or fallback.get("manufacturer", "")

    if lookup.get("error") and not serial:
        raise HTTPException(status_code=502, detail=lookup.get("error") or "Unable to query workstation")

    return {
        "Hostname": hostname,
        "WKS": hostname,
        "SerialNumber": serial,
        "Serial": serial,
        "Modelo": model,
        "Model": model,
        "Marca": manufacturer,
        "Fabricante": manufacturer,
        "EmployeeName": (employee_name or "").strip(),
        "BP": "na",
        "GeneratedAt": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


def query_terms_inventory_powershell(host: str) -> dict:
    executable = powershell_executable()
    if executable is None:
        return {}
    script = (
        "$ErrorActionPreference='Stop'; "
        f"$ComputerName={json.dumps(host)}; "
        "$bios=Get-CimInstance -ClassName Win32_BIOS -ComputerName $ComputerName; "
        "$cs=Get-CimInstance -ClassName Win32_ComputerSystem -ComputerName $ComputerName; "
        "[pscustomobject]@{ "
        "hostname=if($cs.DNSHostName){$cs.DNSHostName}else{$ComputerName}; "
        "serial_number=[string]$bios.SerialNumber; "
        "model=[string]$cs.Model; "
        "manufacturer=[string]$cs.Manufacturer "
        "} | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode != 0:
            return {}
        payload = json.loads((result.stdout or "{}").strip() or "{}")
        return {
            "hostname": text_value(payload.get("hostname")),
            "serial_number": text_value(payload.get("serial_number")),
            "model": text_value(payload.get("model")),
            "manufacturer": text_value(payload.get("manufacturer")),
        }
    except Exception:
        return {}


def _terms_aliases(key: str) -> set[str]:
    compact = re.sub(r"[^A-Za-z0-9]+", "", key)
    aliases = {key, key.upper(), key.lower(), compact, compact.upper(), compact.lower()}
    if compact:
        aliases.add(compact[0].lower() + compact[1:])
        aliases.add(compact[0].upper() + compact[1:])
    return {item for item in aliases if item}


def term_replacements(data: dict) -> dict[str, str]:
    values = {
        "WKS": data.get("WKS", ""),
        "HOSTNAME": data.get("Hostname", ""),
        "SERIAL": data.get("SerialNumber", ""),
        "SERIALNUMBER": data.get("SerialNumber", ""),
        "SERIAL_NUMBER": data.get("SerialNumber", ""),
        "SERIAL NUMBER": data.get("SerialNumber", ""),
        "serialNumber": data.get("SerialNumber", ""),
        "serial_number": data.get("SerialNumber", ""),
        "MODELO": data.get("Modelo", ""),
        "MODEL": data.get("Model", ""),
        "MARCA": data.get("Marca", ""),
        "FABRICANTE": data.get("Fabricante", ""),
        "NOME_COMPLETO": data.get("EmployeeName", ""),
        "NOME": data.get("EmployeeName", ""),
        "BP": data.get("BP", "na"),
        "DATA_GERACAO": data.get("GeneratedAt", ""),
    }

    replacements: dict[str, str] = {}
    for key, value in values.items():
        text = str(value or "")
        for alias in _terms_aliases(key):
            replacements[f"{{{{{alias}}}}}"] = text
            replacements[f"[[{alias}]]"] = text
            replacements[f"<<{alias}>>"] = text
            replacements[f"${{{alias}}}"] = text

    replacements.update(
        {
            "NOME COMPLETO": str(data.get("EmployeeName") or ""),
            "SERIAL NUMBER": str(data.get("SerialNumber") or ""),
            "SERIALNUMBER": str(data.get("SerialNumber") or ""),
            "SERIAL": str(data.get("SerialNumber") or ""),
            "MODELO": str(data.get("Modelo") or ""),
            "MARCA": str(data.get("Marca") or ""),
            "FABRICANTE": str(data.get("Fabricante") or ""),
        }
    )
    return replacements


def apply_terms_text_replacements(text: str, replacements: dict[str, str]) -> tuple[str, set[str]]:
    matched: set[str] = set()
    replaced = text

    for token, value in replacements.items():
        if token in replaced:
            replaced = replaced.replace(token, str(value or ""))
            matched.add(token)

    degree = r"[°ºÂ]"
    serie = r"S(?:[ée]|Ã©)rie"
    next_label = rf"(?:Cart(?:[ãa]|Ã£)o\s+Ponto:|Departamento:|WKS:|C\.\s*Custo:|Centro\s+de\s+Custo:|Marca:|Modelo:|N\.?\s*{degree}\.?\s*(?:de\s*)?{serie}:|Serial\s*Number:|BP:|Componentes:|$)"
    label_rules = [
        (rf"(Nome:\s*)(?={next_label})", replacements.get("{{NOME_COMPLETO}}", ""), "NOME_COMPLETO"),
        (rf"(WKS:\s*)(?={next_label})", replacements.get("{{WKS}}", ""), "WKS"),
        (rf"(Marca:\s*)(?={next_label})", replacements.get("{{MARCA}}", ""), "MARCA"),
        (rf"(Modelo:\s*)(?={next_label})", replacements.get("{{MODELO}}", ""), "MODELO"),
        (rf"(N\.?\s*{degree}\.?\s*(?:de\s*)?{serie}:\s*)(?={next_label})", replacements.get("{{SERIAL}}", ""), "SERIAL"),
        (rf"(Serial\s*Number:\s*)(?={next_label})", replacements.get("{{SERIAL}}", ""), "SERIAL"),
        (rf"(BP:\s*)(?={next_label})", replacements.get("{{BP}}", "na"), "BP"),
    ]

    for pattern, value, key in label_rules:
        if not value:
            continue

        def fill_label(match: re.Match[str]) -> str:
            matched.add(key)
            prefix = match.group(1)
            if not prefix.endswith(" "):
                prefix = f"{prefix} "
            return f"{prefix}{value} "

        replaced = re.sub(pattern, fill_label, replaced, flags=re.IGNORECASE)

    return replaced, matched


def replace_docx_paragraph_tokens(xml: str, replacements: dict[str, str]) -> tuple[str, set[str]]:
    matched: set[str] = set()

    def replace_paragraph(match: re.Match[str]) -> str:
        paragraph = match.group(0)
        text_matches = list(re.finditer(r"(<w:t(?:\s+[^>]*)?>)([\s\S]*?)(</w:t>)", paragraph))
        if not text_matches:
            return paragraph

        combined = "".join(unescape(item.group(2)) for item in text_matches)
        replaced, replacement_matches = apply_terms_text_replacements(combined, replacements)
        matched.update(replacement_matches)

        if replaced == combined:
            return paragraph

        output_parts = []
        cursor = 0
        for index, item in enumerate(text_matches):
            output_parts.append(paragraph[cursor:item.start()])
            if index == 0:
                output_parts.append(f"{item.group(1)}{escape(replaced, quote=False)}{item.group(3)}")
            else:
                output_parts.append(f"{item.group(1)}{item.group(3)}")
            cursor = item.end()
        output_parts.append(paragraph[cursor:])
        return "".join(output_parts)

    return re.sub(r"<w:p[\s\S]*?</w:p>", replace_paragraph, xml), matched


def replace_docx_xml_tokens(content: bytes, replacements: dict[str, str]) -> tuple[bytes, set[str]]:
    matched: set[str] = set()
    root = ET.fromstring(content)
    paragraph_tag = f"{{{WORD_XML_NS}}}p"
    text_tag = f"{{{WORD_XML_NS}}}t"

    for paragraph in root.iter(paragraph_tag):
        text_nodes = list(paragraph.iter(text_tag))
        if not text_nodes:
            continue

        combined = "".join(node.text or "" for node in text_nodes)
        replaced, text_matches = apply_terms_text_replacements(combined, replacements)
        if replaced == combined:
            continue

        matched.update(text_matches)
        for index, node in enumerate(text_nodes):
            node.text = replaced if index == 0 else ""

    return ET.tostring(root, encoding="utf-8", xml_declaration=True), matched


def validate_docx_xml(docx_bytes: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as archive:
            archive.testzip()
            for name in archive.namelist():
                if not name.endswith(".xml"):
                    continue
                ET.fromstring(archive.read(name))
    except ET.ParseError as exc:
        raise HTTPException(status_code=500, detail=f"Generated DOCX has invalid XML: {exc}")
    except zipfile.BadZipFile:
        raise HTTPException(status_code=500, detail="Generated DOCX is not a valid zip package")


def convert_docx_to_pdf(docx_bytes: bytes, filename_stem: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="wmt_terms_") as temp_dir:
        temp_path = Path(temp_dir)
        docx_path = temp_path / f"{filename_stem}.docx"
        pdf_path = temp_path / f"{filename_stem}.pdf"
        docx_path.write_bytes(docx_bytes)

        script = (
            "$ErrorActionPreference = 'Stop'; "
            f"$docx = {json.dumps(str(docx_path))}; "
            f"$pdf = {json.dumps(str(pdf_path))}; "
            "$word = $null; $doc = $null; "
            "try { "
            "$word = New-Object -ComObject Word.Application; "
            "$word.Visible = $false; "
            "$word.DisplayAlerts = 0; "
            "$doc = $word.Documents.Open($docx, $false, $true); "
            "$doc.ExportAsFixedFormat($pdf, 17); "
            "} finally { "
            "if ($doc -ne $null) { $doc.Close($false) | Out-Null }; "
            "if ($word -ne $null) { $word.Quit() | Out-Null }; "
            "[GC]::Collect(); [GC]::WaitForPendingFinalizers(); "
            "} "
        )
        executable = powershell_executable()
        if executable is None:
            raise HTTPException(status_code=500, detail="PowerShell not found. Cannot convert DOCX to PDF.")

        result = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
        if result.returncode != 0 or not pdf_path.exists():
            detail = (result.stderr or result.stdout or "").strip()
            raise HTTPException(
                status_code=500,
                detail=detail or "Microsoft Word could not convert the term to PDF.",
            )

        return pdf_path.read_bytes()


def convert_html_to_pdf(html: str, filename_stem: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="wmt_report_") as temp_dir:
        temp_path = Path(temp_dir)
        html_path = temp_path / f"{filename_stem}.html"
        pdf_path = temp_path / f"{filename_stem}.pdf"
        html_path.write_text(html, encoding="utf-8")
        script = (
            "$ErrorActionPreference = 'Stop'; "
            f"$source = {json.dumps(str(html_path))}; "
            f"$pdf = {json.dumps(str(pdf_path))}; "
            "$word = $null; $doc = $null; "
            "try { "
            "$word = New-Object -ComObject Word.Application; "
            "$word.Visible = $false; $word.DisplayAlerts = 0; "
            "$doc = $word.Documents.Open($source, $false, $true); "
            "$doc.ExportAsFixedFormat($pdf, 17); "
            "} finally { "
            "if ($doc -ne $null) { $doc.Close($false) | Out-Null }; "
            "if ($word -ne $null) { $word.Quit() | Out-Null }; "
            "[GC]::Collect(); [GC]::WaitForPendingFinalizers(); "
            "} "
        )
        executable = powershell_executable()
        if executable is None:
            raise HTTPException(status_code=500, detail="PowerShell not found. Cannot generate PDF report.")
        result = subprocess.run(
            [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
        if result.returncode != 0 or not pdf_path.exists():
            detail = (result.stderr or result.stdout or "").strip()
            raise HTTPException(status_code=500, detail=detail or "Microsoft Word could not generate the PDF report.")
        return pdf_path.read_bytes()


def simple_text_pdf(title: str, sections: list[tuple[str, list[str]]]) -> bytes:
    lines: list[tuple[str, int]] = [(title, 18)]
    for heading, values in sections:
        lines.append(("", 10))
        lines.append((heading, 13))
        for value in values:
            wrapped = textwrap.wrap(str(value or ""), width=92, break_long_words=False, break_on_hyphens=False) or [""]
            lines.extend((item, 9) for item in wrapped)

    pages: list[list[tuple[str, int]]] = []
    current: list[tuple[str, int]] = []
    used_height = 0
    for line, size in lines:
        line_height = max(13, size + 4)
        if current and used_height + line_height > 720:
            pages.append(current)
            current = []
            used_height = 0
        current.append((line, size))
        used_height += line_height
    if current:
        pages.append(current)

    def pdf_text(value: str) -> bytes:
        encoded = value.encode("cp1252", errors="replace")
        return encoded.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")

    objects: dict[int, bytes] = {}
    page_ids: list[int] = []
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    for index, page_lines in enumerate(pages):
        page_id = 4 + index * 2
        content_id = page_id + 1
        page_ids.append(page_id)
        stream = bytearray(b"BT\n")
        y = 800
        for line, size in page_lines:
            y -= max(13, size + 4)
            stream.extend(f"/F1 {size} Tf 50 {y} Td (".encode("ascii"))
            stream.extend(pdf_text(line))
            stream.extend(b") Tj\n")
            stream.extend(f"-50 {-y} Td\n".encode("ascii"))
        stream.extend(b"ET")
        objects[content_id] = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + bytes(stream) + b"\nendstream"
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(f'{item} 0 R' for item in page_ids)}] /Count {len(page_ids)} >>".encode("ascii")
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id in range(1, max(objects) + 1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("ascii"))
    return bytes(output)


def fallback_term_pdf(payload: dict, employee_name: str) -> bytes:
    return simple_text_pdf(
        "TERMO DE RESPONSABILIDADE DE EQUIPAMENTO",
        [
            ("COLABORADOR", [employee_name or payload.get("Employee Name") or "Nao informado"]),
            (
                "EQUIPAMENTO",
                [
                    f"Hostname: {payload.get('WKS') or payload.get('Hostname') or 'Nao informado'}",
                    f"Fabricante: {payload.get('Brand') or 'Nao informado'}",
                    f"Modelo: {payload.get('Model') or 'Nao informado'}",
                    f"Numero de serie: {payload.get('SerialNumber') or 'Nao informado'}",
                ],
            ),
            (
                "RESPONSABILIDADE",
                [
                    "Declaro o recebimento do equipamento descrito acima em condicoes de uso.",
                    "Comprometo-me a utilizar o equipamento exclusivamente para atividades profissionais, zelar por sua conservacao e comunicar imediatamente qualquer perda, dano ou incidente.",
                    "A devolucao devera ocorrer quando solicitada pela empresa ou no encerramento da relacao de trabalho.",
                ],
            ),
            ("ASSINATURAS", ["Colaborador: ______________________________________", "Data: ____/____/________", "Responsavel TI: ___________________________________"]),
        ],
    )


def machine_replacement_report_html(request: MachineReplacementReportRequest) -> str:
    applications = request.applications[:1000]
    app_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('name') or ''))}</td>"
        f"<td>{escape(str(item.get('source_version') or 'Nao instalado'))}</td>"
        f"<td>{escape(str(item.get('destination_version') or 'Nao instalado'))}</td>"
        f"<td>{escape(str(item.get('action') or 'Verificar'))}</td>"
        "</tr>"
        for item in applications
    )
    if not app_rows:
        app_rows = '<tr><td colspan="4">Nenhuma diferenca de software identificada.</td></tr>'
    profiles = ", ".join(escape(item) for item in request.profiles) or "Nenhum perfil informado"
    generated_at = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 18mm; }}
body {{ font-family: Arial, sans-serif; color: #20242a; font-size: 10pt; }}
h1 {{ color: #1d4ed8; font-size: 23pt; margin: 0 0 4px; }}
h2 {{ color: #1f2937; font-size: 13pt; margin: 22px 0 8px; border-bottom: 2px solid #dbeafe; padding-bottom: 5px; }}
.subtitle {{ color: #6b7280; margin-bottom: 20px; }}
.grid {{ width: 100%; border-collapse: separate; border-spacing: 8px; margin-left: -8px; }}
.grid td {{ width: 50%; background: #f5f7fa; border: 1px solid #dfe3e8; padding: 10px; }}
.label {{ color: #6b7280; font-size: 8pt; text-transform: uppercase; }}
.value {{ font-weight: bold; margin-top: 3px; }}
table.apps {{ width: 100%; border-collapse: collapse; font-size: 8.5pt; }}
.apps th {{ background: #1d4ed8; color: white; text-align: left; padding: 7px; }}
.apps td {{ border: 1px solid #dfe3e8; padding: 7px; vertical-align: top; }}
.status {{ display: inline-block; padding: 4px 9px; border: 1px solid #86efac; background: #f0fdf4; color: #166534; font-weight: bold; }}
.footer {{ margin-top: 28px; color: #6b7280; font-size: 8pt; }}
</style></head><body>
<h1>Relatorio de troca de maquina</h1>
<div class="subtitle">WMT - Gerado em {generated_at}</div>
<table class="grid"><tr>
<td><div class="label">Colaborador</div><div class="value">{escape(request.employee_name or "Nao informado")}</div></td>
<td><div class="label">Tecnico responsavel</div><div class="value">{escape(request.technician or "Nao informado")}</div></td>
</tr><tr>
<td><div class="label">Equipamento de origem</div><div class="value">{escape(request.source)}</div></td>
<td><div class="label">Equipamento de destino</div><div class="value">{escape(request.destination)}</div></td>
</tr></table>
<h2>Migracao de dados</h2>
<p><b>Perfis selecionados:</b> {profiles}</p>
<p><b>Pre-check:</b> {escape(request.precheck_status or "Nao executado")} - {escape(request.precheck_message)}</p>
<p><b>Job:</b> {escape(request.backup_job_id or "Nao informado")} <span class="status">{escape(request.backup_status or "Sem status")}</span></p>
<p><b>Resultado:</b> {escape(request.backup_summary or "Sem resumo retornado")}</p>
<p><b>Validacao final:</b> {escape(request.validation_status or "Pendente")}</p>
<p><b>Termo:</b> {"Gerado" if request.term_generated else "Nao gerado"}</p>
<h2>Aplicativos que exigem atencao no destino</h2>
<table class="apps"><thead><tr><th>Aplicativo</th><th>Origem</th><th>Destino</th><th>Acao</th></tr></thead><tbody>{app_rows}</tbody></table>
<div class="footer">Relatorio produzido automaticamente pelo WMT com base nas informacoes coletadas durante a migracao.</div>
</body></html>"""


def fill_docx_template(template_path: Path, replacements: dict[str, str]) -> tuple[bytes, list[str]]:
    if not template_path.exists():
        raise HTTPException(status_code=500, detail=f"Template not found or inaccessible: {template_path}")

    matched_tokens: set[str] = set()
    expected_tokens: set[str] = set()
    output = io.BytesIO()

    try:
        with zipfile.ZipFile(template_path, "r") as source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                content = source.read(item.filename)
                should_replace = (
                    item.filename.startswith("word/") and item.filename.endswith(".xml")
                ) or item.filename.startswith("docProps/")

                if should_replace:
                    xml = content.decode("utf-8", errors="ignore")
                    expected_tokens.update(token for token in replacements if token in xml)
                    xml, matches = replace_docx_paragraph_tokens(xml, replacements)
                    matched_tokens.update(matches)
                    content = xml.encode("utf-8")

                target.writestr(item, content)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=500, detail="Template is not a valid .docx file")

    missing_keys = sorted(token.strip("{}[]<>") for token in expected_tokens if token not in matched_tokens)
    docx_bytes = output.getvalue()
    validate_docx_xml(docx_bytes)
    return docx_bytes, missing_keys


@app.get("/")
def read_root():
    return {"message": "WMT Desktop backend is running"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/updates/latest.json")
def latest_update():
    latest_path = UPDATES_DIR / "latest.json"
    if not latest_path.exists():
        raise HTTPException(status_code=404, detail="No update is available")
    return FileResponse(latest_path, media_type="application/json")


@app.get("/api/updates/{filename}")
def update_artifact(filename: str):
    if not re.fullmatch(r"[A-Za-z0-9_. ()@+-]+", filename):
        raise HTTPException(status_code=404, detail="Update artifact not found")

    artifact_path = (UPDATES_DIR / filename).resolve()
    updates_root = UPDATES_DIR.resolve()
    if updates_root not in artifact_path.parents or not artifact_path.is_file():
        raise HTTPException(status_code=404, detail="Update artifact not found")

    media_type = "application/octet-stream"
    if artifact_path.suffix.lower() == ".msi":
        media_type = "application/x-msi"
    elif artifact_path.suffix.lower() == ".json":
        media_type = "application/json"

    return FileResponse(artifact_path, media_type=media_type, filename=artifact_path.name)


@app.post("/api/auth/login")
def login(request: LoginRequest):
    state = load_state()
    user = next((item for item in state["users"] if item["username"].lower() == request.username.lower()), None)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="User is not active")

    user["last_login"] = utc_now()
    save_state(state)

    user["auth_source"] = "local"
    token, expires_at = create_session_for_user(user)
    audit("auth.login", user["username"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user["username"],
        "role": user["role"],
        "permissions": role_permissions(user["role"]),
        "expires_at": expires_at.isoformat(timespec="seconds") + "Z",
    }


@app.post("/api/auth/sso")
def sso_login(
    request: Request,
    x_remote_user: str | None = Header(default=None),
    x_windows_user: str | None = Header(default=None),
    x_iis_winauth_user: str | None = Header(default=None),
    x_forwarded_for: str | None = Header(default=None),
):
    if not SSO_ENABLED:
        raise HTTPException(status_code=404, detail="SSO is disabled")

    direct_client_ip = request.client.host if request.client else ""
    forwarded_client_ip = (x_forwarded_for or "").split(",", 1)[0].strip()
    client_ip = forwarded_client_ip or direct_client_ip
    identity = x_remote_user or x_windows_user or x_iis_winauth_user
    auth_mode = "iis"

    if identity and SSO_TRUSTED_PROXY_IPS and client_ip not in SSO_TRUSTED_PROXY_IPS and not is_loopback_client(client_ip):
        raise HTTPException(status_code=403, detail="SSO headers are accepted only from trusted proxy")

    if not identity and SSO_DESKTOP_FALLBACK and is_loopback_client(client_ip):
        identity = current_windows_identity()
        auth_mode = "desktop"
    elif not identity and SSO_CLIENT_IP_FALLBACK:
        identity = logged_user_from_host(client_ip)
        auth_mode = "client-ip"
    elif not identity and SSO_DESKTOP_FALLBACK:
        identity = current_windows_identity()
        auth_mode = "desktop"
    if not identity:
        raise HTTPException(status_code=401, detail="Windows identity not provided by IIS")

    user = sso_user_from_identity(identity)
    if user.get("status") != "active":
        raise HTTPException(status_code=403, detail="User is not active")
    token, expires_at = create_session_for_user(user)
    audit(
        "auth.sso",
        user["username"],
        {
            "identity": user.get("windows_identity"),
            "domain": user.get("domain"),
            "role": user.get("role"),
            "mode": auth_mode,
        },
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user["username"],
        "role": user["role"],
        "permissions": role_permissions(user["role"]),
        "display_name": user.get("display_name") or user["username"],
        "email": user.get("email") or "",
        "domain": user.get("domain") or "",
        "groups": user.get("groups") or [],
        "auth_source": "windows",
        "auth_mode": auth_mode,
        "expires_at": expires_at.isoformat(timespec="seconds") + "Z",
    }


@app.get("/api/auth/sso/debug")
def sso_debug(request: Request, x_forwarded_for: str | None = Header(default=None)):
    direct_client_ip = request.client.host if request.client else ""
    forwarded_client_ip = (x_forwarded_for or "").split(",", 1)[0].strip()
    client_ip = forwarded_client_ip or direct_client_ip
    identity = ""
    client_ip_identity = ""
    error = ""
    client_ip_error = ""
    try:
        identity = current_windows_identity() if SSO_DESKTOP_FALLBACK else ""
    except Exception as exc:
        error = str(exc)
    if SSO_CLIENT_IP_FALLBACK:
        try:
            client_ip_identity = logged_user_from_host(client_ip)
        except Exception as exc:
            client_ip_error = str(exc)

    return {
        "sso_enabled": SSO_ENABLED,
        "desktop_fallback": SSO_DESKTOP_FALLBACK,
        "client_ip_fallback": SSO_CLIENT_IP_FALLBACK,
        "client_ip": client_ip,
        "direct_client_ip": direct_client_ip,
        "forwarded_client_ip": forwarded_client_ip,
        "origin": request.headers.get("origin", ""),
        "detected_identity": identity,
        "client_ip_identity": client_ip_identity,
        "error": error,
        "client_ip_error": client_ip_error,
        "cors_origins": cors_origins(),
    }


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return {**public_user(user), "permissions": role_permissions(user["role"])}


@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        SESSIONS.pop(authorization.removeprefix("Bearer ").strip(), None)
    return {"message": "logged out"}


@app.post("/api/account/change-password")
def change_password(request: ChangePasswordRequest, user: dict = Depends(current_user)):
    state = load_state()
    stored_user = next((item for item in state["users"] if item["id"] == user["id"]), None)
    if not stored_user or not verify_password(request.old_password, stored_user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    stored_user["password_hash"] = password_hash(request.new_password)
    save_state(state)
    audit("account.change_password", stored_user["username"])
    return {"message": "Password changed successfully"}


@app.get("/api/settings")
def app_settings(user: dict = Depends(require_role("admin"))):
    return current_settings()


@app.get("/api/app-preferences")
def app_preferences():
    settings = current_settings()
    return {
        "display_language": settings.get("display_language", "en-US"),
        "backup_default_destination_path": settings.get("backup_default_destination_path", ""),
    }


@app.put("/api/settings")
def update_app_settings(request: AppSettingsUpdateRequest, user: dict = Depends(require_role("admin"))):
    state = load_state()
    settings = state.setdefault("settings", {})
    settings["display_language"] = request.display_language
    settings["software_center_timeout_seconds"] = request.software_center_timeout_seconds
    settings["software_center_poll_interval_seconds"] = request.software_center_poll_interval_seconds
    settings["update_job_timeout_minutes"] = request.update_job_timeout_minutes
    settings["backup_default_destination_path"] = request.backup_default_destination_path.strip()
    enabled = DEFAULT_SETTINGS["scripts_enabled"].copy()
    enabled.update({key: bool(value) for key, value in request.scripts_enabled.items()})
    settings["scripts_enabled"] = enabled
    settings["remote_action_aliases"] = {
        str(key).strip(): str(value).strip()
        for key, value in request.remote_action_aliases.items()
        if str(key).strip() and str(value).strip()
    }
    save_state(state)
    audit("settings.update", user["username"], {"settings": current_settings()})
    return current_settings()


@app.get("/api/dashboard")
def dashboard(user: dict = Depends(current_user)):
    state = load_state()
    can_view_backup = "backup" in user.get("permissions", [])
    with BACKUP_JOBS_LOCK:
        runtime_jobs = list(BACKUP_JOBS.values())
    with REMOTE_JOBS_LOCK:
        runtime_remote_jobs = list(REMOTE_JOBS.values())
    with UPDATE_JOBS_LOCK:
        runtime_update_jobs = list(UPDATE_JOBS.values())

    persisted_jobs = state.get("backup_jobs", [])
    jobs_by_id = {job.get("id"): job for job in persisted_jobs}
    for job in runtime_jobs:
        jobs_by_id[job.get("id")] = job
    jobs = sorted(
        jobs_by_id.values(),
        key=lambda item: item.get("start_time") or item.get("end_time") or "",
        reverse=True,
    )
    if not can_view_backup:
        jobs = []

    today = datetime.datetime.utcnow().date()

    def parse_date(value: str | None) -> datetime.datetime | None:
        if not value:
            return None
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def is_today(value: str | None) -> bool:
        parsed = parse_date(value)
        return bool(parsed and parsed.date() == today)

    running = sum(1 for job in jobs if job.get("status") == "running")
    completed = sum(1 for job in jobs if job.get("status") == "completed")
    failed = sum(1 for job in jobs if job.get("status") == "failed")
    canceled = sum(1 for job in jobs if job.get("status") == "canceled")
    finished_today = sum(1 for job in jobs if is_today(job.get("end_time") or job.get("start_time")))
    terms_today = sum(
        1
        for item in state.get("audit", [])
        if item.get("action") in {"terms.generate", "terms.print"} and is_today(item.get("timestamp"))
    )
    active_users = sum(1 for item in state.get("users", []) if item.get("status") == "active")

    audit_items = state.get("audit", [])
    if not can_view_backup:
        audit_items = [item for item in audit_items if not str(item.get("action") or "").startswith("backup.")]

    recent = [
        {
            "id": item["id"],
            "action": item["action"],
            "username": item.get("username", ""),
            "details": item.get("details", {}),
            "timestamp": item["timestamp"],
        }
        for item in audit_items[:8]
    ]

    recent_jobs = [
        {
            "id": job.get("id", ""),
            "source": job.get("source", ""),
            "destination": job.get("destination", ""),
            "users": len(job.get("users") or []),
            "status": backup_status_for_ui(str(job.get("status") or "")),
            "progress": job.get("progress", 0),
            "start_time": job.get("start_time", ""),
            "end_time": job.get("end_time", ""),
            "summary": job.get("summary") or job.get("message") or "",
        }
        for job in jobs[:5]
    ]
    persisted_remote_jobs = state.get("remote_jobs", [])
    remote_jobs_by_id = {job.get("id"): job for job in persisted_remote_jobs}
    for job in runtime_remote_jobs:
        remote_jobs_by_id[job.get("id")] = job
    remote_jobs = sorted(
        [_public_remote_job(job) for job in remote_jobs_by_id.values()],
        key=lambda item: item.get("created_at") or item.get("started_at") or item.get("ended_at") or "",
        reverse=True,
    )
    active_remote = sum(1 for job in remote_jobs if job.get("status") in {"queued", "running"})
    failed_remote = sum(1 for job in remote_jobs if job.get("status") == "failed")
    completed_remote = sum(1 for job in remote_jobs if job.get("status") == "completed")
    persisted_update_jobs = state.get("update_jobs", [])
    update_jobs_by_id = {job.get("id"): job for job in persisted_update_jobs}
    for job in runtime_update_jobs:
        update_jobs_by_id[job.get("id")] = job
    update_jobs = sorted(
        [_public_update_job(job) for job in update_jobs_by_id.values()],
        key=lambda item: item.get("created_at") or item.get("started_at") or item.get("ended_at") or "",
        reverse=True,
    )
    active_updates = sum(1 for job in update_jobs if job.get("status") in {"queued", "running"})
    failed_updates = sum(1 for job in update_jobs if job.get("status") == "failed")
    completed_updates = sum(1 for job in update_jobs if job.get("status") == "completed")

    return {
        "total_workstations": len({job.get("source") for job in jobs if job.get("source")} | {job.get("destination") for job in jobs if job.get("destination")}),
        "online": 0,
        "offline": 0,
        "with_updates": 0,
        "critical_alerts": failed,
        "backup_summary": {
            "total": len(jobs),
            "running": running,
            "completed": completed,
            "failed": failed,
            "canceled": canceled,
            "finished_today": finished_today,
        },
        "terms_today": terms_today,
        "active_users": active_users,
        "kpis": [
            {"label": "Workstations touched", "value": len({job.get("source") for job in jobs if job.get("source")} | {job.get("destination") for job in jobs if job.get("destination")})},
            {"label": "Running backups", "value": running},
            {"label": "Backups today", "value": finished_today},
            {"label": "Terms today", "value": terms_today},
            {"label": "Active users", "value": active_users},
        ],
        "recent_activities": recent,
        "recent_jobs": recent_jobs,
        "remote_summary": {
            "total": len(remote_jobs),
            "active": active_remote,
            "completed": completed_remote,
            "failed": failed_remote,
        },
        "recent_remote_jobs": remote_jobs[:6],
        "update_summary": {
            "total": len(update_jobs),
            "active": active_updates,
            "completed": completed_updates,
            "failed": failed_updates,
        },
        "recent_update_jobs": update_jobs[:6],
        "temp_shares": build_temp_shares_payload(state, verify_live=False),
    }


@app.get("/api/operational-jobs")
def operational_jobs(user: dict = Depends(current_user)):
    state = load_state()
    can_view_backup = "backup" in user.get("permissions", [])

    if can_view_backup:
        with BACKUP_JOBS_LOCK:
            runtime_backup_jobs = list(BACKUP_JOBS.values())
        backup_jobs_by_id = {job.get("id"): job for job in state.get("backup_jobs", [])}
        for job in runtime_backup_jobs:
            backup_jobs_by_id[job.get("id")] = job
        backup_jobs = sorted(
            backup_jobs_by_id.values(),
            key=lambda item: item.get("start_time") or item.get("end_time") or "",
            reverse=True,
        )
        recent_jobs = [
            {
                "id": job.get("id", ""),
                "source": job.get("source", ""),
                "destination": job.get("destination", ""),
                "status": backup_status_for_ui(str(job.get("status") or "")),
                "summary": job.get("summary") or job.get("message") or "",
            }
            for job in backup_jobs[:5]
        ]
    else:
        recent_jobs = []

    with REMOTE_JOBS_LOCK:
        runtime_remote_jobs = [_public_remote_job(job) for job in REMOTE_JOBS.values()]
    remote_jobs_by_id = {job.get("id"): job for job in state.get("remote_jobs", [])}
    for job in runtime_remote_jobs:
        remote_jobs_by_id[job.get("id")] = job
    remote_jobs = sorted(
        [_public_remote_job(job) for job in remote_jobs_by_id.values()],
        key=lambda item: item.get("created_at") or item.get("started_at") or item.get("ended_at") or "",
        reverse=True,
    )

    with UPDATE_JOBS_LOCK:
        runtime_update_jobs = [_public_update_job(job) for job in UPDATE_JOBS.values()]
    update_jobs_by_id = {job.get("id"): job for job in state.get("update_jobs", [])}
    for job in runtime_update_jobs:
        update_jobs_by_id[job.get("id")] = job
    update_jobs = sorted(
        [_public_update_job(job) for job in update_jobs_by_id.values()],
        key=lambda item: item.get("created_at") or item.get("started_at") or item.get("ended_at") or "",
        reverse=True,
    )

    return {
        "recent_jobs": recent_jobs,
        "recent_remote_jobs": remote_jobs[:6],
        "recent_update_jobs": update_jobs[:6],
    }


@app.post("/api/lookup", response_model=LookupResponse)
def lookup_machine(request: LookupRequest, user: dict = Depends(current_user)):
    host = request.host.strip()
    if not host:
        raise HTTPException(status_code=400, detail="Host is required")
    result = cached_collect_machine_info(host)
    current = str(result.get("current_user") or "").strip()
    if current:
        audit(
            "workstation.lookup",
            user["username"],
            {
                "host": str(result.get("hostname") or host),
                "current_user": current,
                "ip_address": str(result.get("ip_address") or ""),
                "os": str(result.get("os") or ""),
                "serial_number": str(result.get("serial_number") or ""),
                "manufacturer": str(result.get("manufacturer") or ""),
                "model": str(result.get("model") or ""),
            },
        )
    return LookupResponse(**result)


@app.post("/api/ad-users/lookup")
def lookup_ad_user(request: ADUserLookupRequest, user: dict = Depends(current_user)):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="User query is required")
    result = cached_ad_user_info(query)
    audit("ad_user.lookup", user["username"], {"query": query, "found": bool(result.get("found"))})
    return result


@app.post("/api/ad-users/search")
def search_ad_users(request: ADUserLookupRequest, user: dict = Depends(current_user)):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="User query is required")
    result = cached_ad_user_matches(query)
    audit("ad_user.search", user["username"], {"query": query, "total": result.get("total", 0)})
    return result


def _universal_workstation_matches(query: str, limit: int) -> list[dict]:
    needle = query.strip().lower()
    if not needle:
        return []

    state = load_state_fields("audit", "backup_jobs", "remote_jobs", "update_jobs")
    candidates: dict[str, dict] = {}

    def remember(host_value: object, payload: dict | None = None, timestamp: object = "") -> None:
        host = str(host_value or "").strip().upper()
        if not host:
            return
        details = payload if isinstance(payload, dict) else {}
        searchable = " ".join(
            str(details.get(key) or "")
            for key in ("host", "ip_address", "serial_number", "asset_number", "patrimony", "manufacturer", "model", "current_user")
        ).lower()
        if needle not in host.lower() and needle not in searchable:
            return
        existing = candidates.get(host)
        candidate = {
            "host": host,
            "ip_address": text_value(details.get("ip_address")),
            "serial_number": text_value(details.get("serial_number")),
            "manufacturer": text_value(details.get("manufacturer")),
            "model": text_value(details.get("model")),
            "current_user": text_value(details.get("current_user")),
            "last_seen": text_value(timestamp),
            "known": True,
        }
        if existing is None or str(candidate["last_seen"]) > str(existing.get("last_seen") or ""):
            candidates[host] = candidate

    for item in state.get("audit") or []:
        details = item.get("details") or {}
        if not isinstance(details, dict):
            continue
        for host in _audit_hosts(details):
            remember(host, details, item.get("timestamp"))

    for collection in ("backup_jobs", "remote_jobs", "update_jobs"):
        for item in state.get(collection) or []:
            if not isinstance(item, dict):
                continue
            timestamp = item.get("created_at") or item.get("start_time") or item.get("ended_at") or ""
            for key in ("host", "source", "destination", "workstation"):
                remember(item.get(key), item, timestamp)

    host_like = bool(
        re.fullmatch(r"(?:[A-Za-z][A-Za-z0-9_.-]*\d[A-Za-z0-9_.-]*|\d{1,3}(?:\.\d{1,3}){3})", query.strip())
    )
    exact_host = query.strip().upper()
    if host_like and exact_host not in candidates:
        candidates[exact_host] = {
            "host": exact_host,
            "ip_address": exact_host if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", exact_host) else "",
            "serial_number": "",
            "manufacturer": "",
            "model": "",
            "current_user": "",
            "last_seen": "",
            "known": False,
        }

    return sorted(
        candidates.values(),
        key=lambda item: (item["host"].lower() != needle, not item["known"], item["host"]),
    )[:limit]


@app.post("/api/search/universal")
def universal_search(request: UniversalSearchRequest, user: dict = Depends(current_user)):
    query = request.query.strip()
    user_result = cached_ad_user_matches(query)
    users = (user_result.get("matches") or [])[: request.limit]
    workstations = _universal_workstation_matches(query, request.limit)
    return {
        "query": query,
        "users": users,
        "workstations": workstations,
        "user_total": int(user_result.get("total") or len(users)),
        "workstation_total": len(workstations),
        "user_error": text_value(user_result.get("error")),
    }


def build_workstation_history(host: str) -> dict:
    normalized_host = _normalize_history_host(host)
    state = load_state()

    with BACKUP_JOBS_LOCK:
        runtime_backup_jobs = [_public_backup_job(job) for job in BACKUP_JOBS.values()]
    backup_jobs_by_id = {job.get("id"): job for job in state.get("backup_jobs", [])}
    for job in runtime_backup_jobs:
        backup_jobs_by_id[job.get("id")] = job
    backups = [
        job
        for job in backup_jobs_by_id.values()
        if _matches_history_host(job.get("source"), normalized_host)
        or _matches_history_host(job.get("destination"), normalized_host)
        or _matches_history_host(job.get("workstation"), normalized_host)
    ]
    backups.sort(key=lambda item: str(item.get("start_time") or ""), reverse=True)

    with REMOTE_JOBS_LOCK:
        runtime_remote_jobs = [_public_remote_job(job) for job in REMOTE_JOBS.values()]
    remote_jobs_by_id = {job.get("id"): job for job in state.get("remote_jobs", [])}
    for job in runtime_remote_jobs:
        remote_jobs_by_id[job.get("id")] = job
    remote_jobs = [
        job
        for job in remote_jobs_by_id.values()
        if _matches_history_host(job.get("host"), normalized_host)
    ]
    remote_jobs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)

    audit_items = [
        item
        for item in state.get("audit", [])
        if normalized_host in _audit_hosts(item.get("details") or {})
    ]
    diagnostics = [
        item
        for item in audit_items
        if item.get("action") in {"diagnostics.run", "diagnostics.job", "cleanup.quick"}
    ]
    terms = [
        item
        for item in audit_items
        if str(item.get("action") or "").startswith("terms.")
    ]
    active_temp_shares, temp_share_error = _list_active_temp_shares(normalized_host)

    events: list[dict] = []
    for job in backups:
        status = str(job.get("status") or "")
        events.append(
            {
                "id": job.get("id") or secrets.token_hex(4),
                "kind": "backup",
                "title": f"Backup {job.get('source') or '-'} -> {job.get('destination') or '-'}",
                "status": status,
                "timestamp": job.get("start_time") or "",
                "actor": "",
                "detail": job.get("summary") or job.get("message") or "",
                "error": bool(status in {"failed", "canceled"} or job.get("failures")),
            }
        )
    for job in remote_jobs:
        status = str(job.get("status") or "")
        events.append(
            {
                "id": job.get("id") or secrets.token_hex(4),
                "kind": "remote",
                "title": str(job.get("action") or "Remote action"),
                "status": status,
                "timestamp": job.get("created_at") or "",
                "actor": job.get("created_by") or "",
                "detail": job.get("message") or "",
                "error": status in {"failed", "canceled"},
            }
        )
    for item in audit_items:
        details = item.get("details") or {}
        action = str(item.get("action") or "")
        kind = "audit"
        if action.startswith("terms."):
            kind = "terms"
        elif action.startswith("diagnostics.") or action.startswith("cleanup."):
            kind = "diagnostic"
        elif action.startswith("backup."):
            kind = "backup"
        detail_parts = []
        for key, value in details.items():
            if key in {"host", "wk", "source", "destination"}:
                continue
            formatted_value = _history_detail_value(value)
            if formatted_value:
                detail_parts.append(f"{key}: {formatted_value}")
        detail = ", ".join(detail_parts)
        events.append(
            {
                "id": item.get("id") or secrets.token_hex(4),
                "kind": kind,
                "title": action,
                "status": "logged",
                "timestamp": item.get("timestamp") or "",
                "actor": item.get("username") or "",
                "detail": detail,
                "error": "error" in action.lower() or "failed" in detail.lower() or "erro" in detail.lower(),
            }
        )

    events.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    recent_errors = [event for event in events if event.get("error")][:10]

    return {
        "host": normalized_host,
        "generated_at": utc_now(),
        "summary": {
            "backups": len(backups),
            "remote_actions": len(remote_jobs),
            "diagnostics": len(diagnostics),
            "terms": len(terms),
            "active_temp_shares": len(active_temp_shares),
            "recent_errors": len(recent_errors),
        },
        "active_temp_shares": active_temp_shares,
        "temp_share_error": temp_share_error,
        "backups": backups[:20],
        "remote_actions": remote_jobs[:30],
        "diagnostics": diagnostics[:20],
        "terms": terms[:20],
        "recent_errors": recent_errors,
        "events": events[:80],
    }


@app.post("/api/workstations/history")
def workstation_history_post(request: WorkstationHistoryRequest, user: dict = Depends(require_role("admin", "operator"))):
    return build_workstation_history(request.host)


@app.get("/api/workstations/{host}/history")
def workstation_history(host: str, user: dict = Depends(require_role("admin", "operator"))):
    return build_workstation_history(host)


@app.post("/api/diagnostics")
def diagnostics(request: DiagnosticRequest, user: dict = Depends(require_role("admin", "operator"))):
    host = validate_backup_host(request.host)
    payload = cached_diagnostic_pack(host, include_details=request.detailed)
    audit("diagnostics.run", user["username"], {"host": host, "detailed": request.detailed})
    return payload


@app.post("/api/diagnostics/jobs")
def diagnostics_job_create(request: DiagnosticRequest, user: dict = Depends(require_role("admin", "operator"))):
    job = create_diagnostic_job(request.host, request.detailed, user["username"])
    audit("diagnostics.job", user["username"], {"host": job.get("host"), "detailed": request.detailed, "job_id": job.get("id")})
    return job


@app.get("/api/diagnostics/jobs/{job_id}")
def diagnostics_job_get(job_id: str, user: dict = Depends(require_role("admin", "operator"))):
    if job_id.startswith("cache-"):
        raise HTTPException(status_code=404, detail="Cached diagnostic job is not stored")
    with DIAGNOSTIC_JOBS_LOCK:
        job = DIAGNOSTIC_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Diagnostic job not found")
        return _public_diagnostic_job(job)


@app.post("/api/inventory")
def inventory(request: HostRequest, user: dict = Depends(current_user)):
    host = validate_backup_host(request.host)
    payload = cached_diagnostic_pack(host, include_details=True)
    return {
        "host": host,
        "generated_at": payload.get("generated_at") or utc_now(),
        "inventory": payload.get("inventory") or {},
        "checks": payload.get("checks") or [],
        "error": payload.get("error") or "",
    }


@app.post("/api/quick-cleanup")
def quick_cleanup(request: HostRequest, user: dict = Depends(require_role("admin", "operator"))):
    host = validate_backup_host(request.host)
    payload = run_diagnostic_pack(host, run_cleanup=True)
    _cache_delete_prefix(f"diagnostic:{host}:")
    audit("cleanup.quick", user["username"], {"host": host})
    return payload


@app.post("/api/wmt-health")
def wmt_health(request: HostRequest, user: dict = Depends(current_user)):
    host = validate_backup_host(request.host)
    return build_wmt_health(host)


@app.get("/api/terms/config")
def terms_config(user: dict = Depends(require_role("admin", "operator"))):
    return {
        "types": [
            {
                "value": key,
                "label": entry["label"],
                "template_path": str(terms_template_path(key)),
                "template_accessible": terms_template_path(key).exists(),
            }
            for key, entry in TERM_TYPES.items()
        ],
        "placeholders": ["WKS", "Hostname", "SerialNumber", "serialNumber", "Serial Number", "Model", "Brand", "Employee Name"],
    }


@app.post("/api/terms/generate")
def terms_generate(request: TermsGenerateRequest, user: dict = Depends(require_role("admin", "operator"))):
    term_entry = TERM_TYPES.get(request.term_type)
    if not term_entry:
        raise HTTPException(status_code=400, detail="Unsupported term type")

    payload = build_terms_payload(request.wk, request.employee_name)
    template_path = terms_template_path(request.term_type)
    docx_bytes, missing_placeholders = fill_docx_template(template_path, term_replacements(payload))

    filename_wk = re.sub(r"[^A-Z0-9_-]+", "_", str(payload.get("WKS") or "WKS").upper())
    filename = f"{filename_wk}-{term_entry['filename_suffix']}.docx"
    audit(
        "terms.generate",
        user["username"],
        {
            "wk": payload.get("WKS", request.wk),
            "term_type": request.term_type,
            "employee_name": request.employee_name,
            "filename": filename,
        },
    )
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Missing-Placeholders": ",".join(missing_placeholders),
        },
    )


@app.post("/api/terms/print")
def terms_print(
    request: TermsGenerateRequest,
    portable: bool = Query(default=False),
    user: dict = Depends(require_role("admin", "operator")),
):
    term_entry = TERM_TYPES.get(request.term_type)
    if not term_entry:
        raise HTTPException(status_code=400, detail="Unsupported term type")

    payload = build_terms_payload(request.wk, request.employee_name)
    filename_wk = re.sub(r"[^A-Z0-9_-]+", "_", str(payload.get("WKS") or "WKS").upper())
    filename = f"{filename_wk}-{term_entry['filename_suffix']}.pdf"
    if portable:
        pdf_bytes = fallback_term_pdf(payload, request.employee_name)
    else:
        template_path = terms_template_path(request.term_type)
        docx_bytes, _missing_placeholders = fill_docx_template(template_path, term_replacements(payload))
        try:
            pdf_bytes = convert_docx_to_pdf(docx_bytes, filename_wk)
        except HTTPException:
            pdf_bytes = fallback_term_pdf(payload, request.employee_name)
    audit(
        "terms.print",
        user["username"],
        {
            "wk": payload.get("WKS", request.wk),
            "term_type": request.term_type,
            "employee_name": request.employee_name,
            "filename": filename,
        },
    )
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.post("/api/machine-replacement/report")
def machine_replacement_report(
    request: MachineReplacementReportRequest,
    user: dict = Depends(require_role("admin", "operator")),
):
    source = validate_backup_host(request.source)
    destination = validate_backup_host(request.destination)
    filename = f"troca-{source}-{destination}.pdf"
    application_sections = [
        (
            f"{index}. {item.get('name') or 'Aplicativo'}",
            [
                f"Versao na origem: {item.get('source_version') or 'Nao instalado'}",
                f"Versao no destino: {item.get('destination_version') or 'Nao instalado'}",
                f"Acao recomendada: {item.get('action') or 'Verificar'}",
                "-" * 72,
            ],
        )
        for index, item in enumerate(request.applications[:1000], start=1)
    ]
    if not application_sections:
        application_sections = [("APLICATIVOS", ["Nenhum aplicativo exige instalacao ou atualizacao."])]
    pdf_bytes = simple_text_pdf(
        "RELATORIO DE TROCA DE MAQUINA",
        [
            (
                "IDENTIFICACAO",
                [
                    f"Colaborador: {request.employee_name or 'Nao informado'}",
                    f"Tecnico: {request.technician or user['username']}",
                    f"Origem: {source}",
                    f"Destino: {destination}",
                    f"Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}",
                ],
            ),
            ("DADOS MIGRADOS", [f"Perfis: {', '.join(request.profiles) or 'Nenhum perfil informado'}"]),
            (
                "VALIDACOES E BACKUP",
                [
                    f"Pre-check: {request.precheck_status or 'Nao executado'} - {request.precheck_message}",
                    f"Job: {request.backup_job_id or 'Nao informado'}",
                    f"Status: {request.backup_status or 'Nao informado'}",
                    f"Resumo: {request.backup_summary or 'Sem resumo retornado'}",
                    f"Validacao final: {request.validation_status or 'Pendente'}",
                    f"Termo: {'Gerado' if request.term_generated else 'Nao gerado'}",
                ],
            ),
            ("APLICATIVOS PARA INSTALAR OU ATUALIZAR", [f"Total identificado: {len(request.applications)}"]),
            *application_sections,
        ],
    )
    audit(
        "machine_replacement.report",
        user["username"],
        {
            "source": source,
            "destination": destination,
            "backup_job_id": request.backup_job_id,
            "applications": len(request.applications),
        },
    )
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/api/software-center")
def software_center_status(host: str = Query(default="localhost"), user: dict = Depends(current_user)):
    target = host.strip() or "localhost"
    if not HOST_PATTERN.match(target):
        raise HTTPException(status_code=400, detail="Host contains unsupported characters")
    return cached_software_center_status(target)


@app.post("/api/software-center/install")
def software_center_install(request: SoftwareCenterInstallRequest, user: dict = Depends(require_role("admin", "operator"))):
    host = request.host.strip() or "localhost"
    if not HOST_PATTERN.match(host):
        raise HTTPException(status_code=400, detail="Host contains unsupported characters")

    _cache_delete_prefix(f"software-center:{host.upper()}:")
    job = create_update_job(host, user["username"])
    audit("software_center.install_updates", user["username"], {"host": host, "job_id": job["id"]})
    return {
        "ok": True,
        "job": job,
        "job_id": job["id"],
        "status": job["status"],
        "message": f"Update job {job['id']} criado para {host}.",
    }


@app.get("/api/update-jobs")
def list_update_jobs(user: dict = Depends(current_user)):
    state = load_state()
    persisted_jobs = state.get("update_jobs", [])
    with UPDATE_JOBS_LOCK:
        runtime_jobs = [_public_update_job(job) for job in UPDATE_JOBS.values()]
    jobs_by_id = {job.get("id"): job for job in persisted_jobs}
    for job in runtime_jobs:
        jobs_by_id[job.get("id")] = job
    jobs = sorted(
        jobs_by_id.values(),
        key=lambda item: item.get("created_at") or item.get("started_at") or item.get("ended_at") or "",
        reverse=True,
    )
    return {
        "jobs": jobs,
        "total": len(jobs),
        "active": sum(1 for job in jobs if job.get("status") in {"queued", "running"}),
        "failed": sum(1 for job in jobs if job.get("status") == "failed"),
        "completed": sum(1 for job in jobs if job.get("status") == "completed"),
    }


@app.get("/api/update-jobs/{job_id}")
def get_update_job(job_id: str, user: dict = Depends(current_user)):
    with UPDATE_JOBS_LOCK:
        runtime = UPDATE_JOBS.get(job_id)
        if runtime:
            return _public_update_job(runtime)
    state = load_state()
    job = next((item for item in state.get("update_jobs", []) if item.get("id") == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Update job not found")
    return job


@app.get("/api/workstations")
def workstations(user: dict = Depends(current_user)):
    info = collect_machine_info("localhost")
    workstation = {
        "id": "local-machine",
        "hostname": info.get("hostname") or "localhost",
        "status": "online" if info.get("online") else "offline",
        "ip_address": info.get("ip_address") or "",
        "os": info.get("os") or "Windows",
        "cpu": info.get("processor") or "",
        "memory": f"{info.get('ram_gb', 0)} GB" if info.get("ram_gb") else "0 GB",
        "disk": f"{info.get('storage_total_gb', 0)} GB" if info.get("storage_total_gb") else "0 GB",
        "last_seen": info.get("last_boot") or "Agora",
    }
    return {"workstations": [workstation], "total": 1}


def validate_backup_host(value: str) -> str:
    host = (value or "").strip().strip("\\/").upper()
    if not host:
        raise HTTPException(status_code=400, detail="Host is required")
    if not HOST_PATTERN.match(host):
        raise HTTPException(status_code=400, detail="Host contains unsupported characters")
    return host


def backup_status_for_ui(status: str) -> str:
    return {
        "error": "failed",
        "cancelled": "canceled",
    }.get(status, status)


def _temporary_share_name(drive_letter: str) -> str:
    drive = (drive_letter or "C").replace(":", "").replace("\\", "").replace("/", "").strip().upper() or "C"
    return f"WMT_TEMP_{drive}$"


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


def _normalize_destination_root(destination_path: str | None) -> tuple[str, str] | None:
    path = (destination_path or "").strip()
    if not path:
        return None
    normalized = path.replace("/", "\\")
    if not re.match(r"^[A-Za-z]:\\", normalized):
        raise HTTPException(status_code=400, detail="Custom destination path must be absolute, like D:\\Backup\\Migration")
    drive = normalized[0].upper()
    relative = normalized[3:].strip("\\")
    return drive, relative


def _normalize_absolute_windows_path(path: str, field_name: str) -> tuple[str, str]:
    normalized = str(path or "").strip().replace("/", "\\")
    if not re.match(r"^[A-Za-z]:\\", normalized):
        raise HTTPException(status_code=400, detail=f"{field_name} must be absolute, like D:\\Backup\\Folder")
    return normalized[0].upper(), normalized[3:].strip("\\")


def _build_unc_from_absolute_path(host: str, path: str, share_name: str | None = None) -> tuple[str, str, str]:
    drive, relative = _normalize_absolute_windows_path(path, "Path")
    share = share_name or drive
    base = f"\\\\{host}\\{share}"
    return drive, relative, f"{base}\\{relative}" if relative else base


def _safe_robocopy_exclude_patterns(patterns: list[str]) -> list[str]:
    safe: list[str] = []
    for item in patterns:
        pattern = str(item or "").strip()
        if not pattern or any(char in pattern for char in ['"', "'", "\r", "\n"]):
            continue
        safe.append(pattern)
    return safe[:25]


def _build_source_path(host: str, user: str, folder: str, share_name: str = "C") -> str:
    return f"\\\\{host}\\{share_name}\\Users\\{user}\\{folder}"


def _build_destination_path(
    host: str,
    user: str,
    folder: str,
    destination_path: str | None,
    share_name: str | None = None,
) -> tuple[str, str]:
    destination_root = _normalize_destination_root(destination_path)
    if not destination_root:
        share = share_name or "C"
        return "C", f"\\\\{host}\\{share}\\Users\\{user}\\{folder}"

    drive, relative = destination_root
    base = f"\\\\{host}\\{share_name or drive}"
    if relative:
        base = f"{base}\\{relative}"
    return drive, f"{base}\\{user}\\{folder}"


def _build_destination_base_path(host: str, destination_path: str | None, share_name: str | None = None) -> str:
    destination_root = _normalize_destination_root(destination_path)
    if not destination_root:
        return f"\\\\{host}\\{share_name or 'C'}\\Users"

    drive, relative = destination_root
    base = f"\\\\{host}\\{share_name or drive}"
    return f"{base}\\{relative}" if relative else base


def _build_temporary_destination_browse_path(host: str, drive: str, relative: str) -> str:
    share_name = _temporary_share_name(drive)
    base = f"\\\\{host}\\{share_name}"
    return f"{base}\\{relative}" if relative else base


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


def _normalize_drive_letter(drive: str | None, default: str = "C") -> str:
    safe_drive = (drive or default).replace(":", "").replace("\\", "").replace("/", "").strip().upper() or default
    if not re.fullmatch(r"[A-Z]", safe_drive):
        raise RuntimeError("Invalid destination drive")
    return safe_drive


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
    state = load_state()
    jobs = [item for item in state.get("backup_jobs", []) if item.get("id") != job.get("id")]
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
    jobs.insert(0, public_job)
    state["backup_jobs"] = jobs[:50]
    save_state(state)


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


@app.get("/api/backup/jobs")
def backup_jobs(user: dict = Depends(require_role("admin", "operator"))):
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
    return {
        "jobs": jobs,
        "summary": {
            "total": len(jobs),
            "total_size": f"{total_size_gb} GB",
            "success_rate": success_rate,
        },
    }


@app.post("/api/backup/users")
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


@app.post("/api/backup/open-destination")
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


@app.post("/api/backup/precheck")
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


@app.post("/api/backup/jobs")
def create_backup_job(request: BackupCreateRequest, user: dict = Depends(require_role("admin", "operator"))):
    if not script_enabled("backup"):
        raise HTTPException(status_code=403, detail="Backups estÃ£o desabilitados nas configuraÃ§Ãµes do WMT.")
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


@app.post("/api/backup/simulate")
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


@app.post("/api/backup/custom-folder/jobs")
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


@app.get("/api/backup/jobs/{job_id}")
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


@app.put("/api/backup/jobs/{job_id}/checklist")
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

    state = load_state()
    jobs = state.get("backup_jobs", [])
    for item in jobs:
        if item.get("id") == job_id:
            item["checklist"] = next_checklist
            save_state(state)
            audit("backup.checklist", user["username"], {"job_id": job_id, "checked": [key for key, value in next_checklist.items() if value]})
            return _public_backup_job(item)
    raise HTTPException(status_code=404, detail="Backup job not found")


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


@app.post("/api/backup/jobs/{job_id}/retry-folder")
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
        BACKUP_JOBS[retry_id] = job
    thread = threading.Thread(
        target=_run_backup_job,
        args=(retry_id, source, destination, [profile], access_identity, destination_path, "", "", [folder], exclude_patterns),
        daemon=True,
    )
    thread.start()
    audit("backup.retry_folder", user["username"], {"source_job_id": job_id, "job_id": retry_id, "profile": profile, "folder": folder})
    return _public_backup_job(job)


@app.get("/api/backup/jobs/{job_id}/open-path")
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


@app.post("/api/backup/jobs/{job_id}/cancel")
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


@app.delete("/api/backup/jobs/{job_id}")
def delete_backup_job(job_id: str, user: dict = Depends(require_role("admin", "operator"))):
    with BACKUP_JOBS_LOCK:
        removed_runtime = BACKUP_JOBS.pop(job_id, None) is not None

    state = load_state()
    jobs = state.get("backup_jobs", [])
    next_jobs = [job for job in jobs if job["id"] != job_id]
    if len(next_jobs) == len(jobs) and not removed_runtime:
        raise HTTPException(status_code=404, detail="Backup job not found")
    state["backup_jobs"] = next_jobs
    save_state(state)
    audit("backup.delete", user["username"], {"job_id": job_id})
    return {"ok": True}


@app.post("/api/backup/jobs/retention")
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

    state = load_state()
    jobs = sorted(state.get("backup_jobs", []), key=job_date, reverse=True)
    kept: list[dict] = []
    removed: list[dict] = []
    for index, job in enumerate(jobs):
        status = str(job.get("status") or "")
        if index < request.keep_last or status == "running" or job_date(job) >= cutoff:
            kept.append(job)
        else:
            removed.append(job)
    state["backup_jobs"] = kept
    save_state(state)
    audit("backup.retention", user["username"], {"days": request.days, "keep_last": request.keep_last, "removed": len(removed)})
    return {"ok": True, "removed": len(removed), "kept": len(kept)}


@app.post("/api/backup/jobs/{job_id}/download")
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


@app.get("/api/users")
def users(user: dict = Depends(require_role("admin"))):
    state = load_state()
    users_list = sorted(
        [public_user(item) for item in state["users"]],
        key=lambda item: (str(item.get("auth_source") or ""), str(item.get("username") or "").lower()),
    )
    return {"users": users_list, "total": len(users_list)}


@app.post("/api/users")
def create_user(request: UserCreateRequest, user: dict = Depends(require_role("admin"))):
    state = load_state()
    if any(item["username"].lower() == request.username.lower() for item in state["users"]):
        raise HTTPException(status_code=409, detail="Username already exists")
    new_user = {
        "id": f"usr-{secrets.token_hex(6)}",
        "username": request.username.strip(),
        "email": request.email.strip(),
        "role": request.role,
        "status": "active",
        "password_hash": password_hash(request.password),
        "last_login": "",
        "created_at": utc_now(),
    }
    state["users"].append(new_user)
    save_state(state)
    audit("users.create", user["username"], {"target": new_user["username"]})
    return public_user(new_user)


@app.put("/api/users/{user_id}")
def update_user(user_id: str, request: UserUpdateRequest, user: dict = Depends(require_role("admin"))):
    state = load_state()
    stored_user = next((item for item in state["users"] if item["id"] == user_id), None)
    if not stored_user:
        raise HTTPException(status_code=404, detail="User not found")
    if request.email is not None:
        stored_user["email"] = request.email.strip()
    if request.role is not None:
        stored_user["role"] = request.role
        stored_user["role_source"] = "manual"
    if request.status is not None:
        stored_user["status"] = request.status
    save_state(state)
    audit("users.update", user["username"], {"target": stored_user["username"]})
    return public_user(stored_user)


@app.post("/api/users/{user_id}/status")
def update_user_status(user_id: str, request: UserStatusRequest, user: dict = Depends(require_role("admin"))):
    return update_user(user_id, UserUpdateRequest(status=request.status), user)


@app.delete("/api/users/{user_id}")
def delete_user(user_id: str, user: dict = Depends(require_role("admin"))):
    if user["id"] == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    state = load_state()
    users = state["users"]
    next_users = [item for item in users if item["id"] != user_id]
    if len(next_users) == len(users):
        raise HTTPException(status_code=404, detail="User not found")
    state["users"] = next_users
    save_state(state)
    audit("users.delete", user["username"], {"target_id": user_id})
    return {"ok": True}


def validate_remote_action_request(request: RemoteActionRequest, user: dict | None = None) -> tuple[str, str]:
    host = request.host.strip() or "localhost"
    action = _canonical_remote_action(request.action).strip()

    if not action:
        raise HTTPException(status_code=400, detail="Action is required")
    if not HOST_PATTERN.match(host):
        raise HTTPException(status_code=400, detail="Host contains unsupported characters")
    return host, action


@app.get("/api/remote-jobs")
def list_remote_jobs(user: dict = Depends(current_user)):
    state = load_state_fields("remote_jobs", "temp_shares")
    persisted_jobs = state.get("remote_jobs", [])
    with REMOTE_JOBS_LOCK:
        runtime_jobs = [_public_remote_job(job) for job in REMOTE_JOBS.values()]

    jobs_by_id = {job.get("id"): job for job in persisted_jobs}
    for job in runtime_jobs:
        jobs_by_id[job.get("id")] = job

    jobs = sorted(
        jobs_by_id.values(),
        key=lambda item: item.get("created_at") or item.get("started_at") or "",
        reverse=True,
    )
    public_jobs = [_public_remote_job(job) for job in jobs]
    running = sum(1 for job in public_jobs if job.get("status") in {"queued", "running"})
    failed = sum(1 for job in public_jobs if job.get("status") == "failed")
    completed = sum(1 for job in public_jobs if job.get("status") == "completed")
    return {
        "jobs": public_jobs[:100],
        "total": len(public_jobs),
        "running": running,
        "failed": failed,
        "completed": completed,
        "temp_shares": build_temp_shares_payload(state, verify_live=False),
    }


@app.get("/api/temp-shares")
def list_temp_shares(user: dict = Depends(require_role("admin", "operator"))):
    return build_temp_shares_payload()


@app.delete("/api/temp-shares/{host}/{share_name}")
def remove_temp_share(host: str, share_name: str, user: dict = Depends(require_role("admin", "operator"))):
    normalized_host = _normalize_history_host(host)
    decoded_share_name = share_name.strip()
    drive = _temp_share_drive_from_name(decoded_share_name)
    try:
        if decoded_share_name.lower() == "tempc$":
            ok, message, details = execute_remote_action(normalized_host, "remove-temp-c-share")
            if not ok:
                raise RuntimeError(details or message)
        else:
            run_temporary_share_action(normalized_host, "remove", BACKUP_TEMPORARY_SHARE_TTL_MINUTES, drive)
            message = f"Temporary share {decoded_share_name} removed from {normalized_host}."
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao remover share temporaria {decoded_share_name} em {normalized_host}: {exc}")

    _untrack_temp_share(normalized_host, decoded_share_name)
    audit("temp_share.remove", user["username"], {"host": normalized_host, "share": decoded_share_name, "drive": drive})
    return {"ok": True, "message": message}


@app.get("/api/remote-jobs/{job_id}")
def get_remote_job(job_id: str, user: dict = Depends(current_user)):
    with REMOTE_JOBS_LOCK:
        runtime = REMOTE_JOBS.get(job_id)
        if runtime:
            return _public_remote_job(runtime)

    state = load_state()
    job = next((item for item in state.get("remote_jobs", []) if item.get("id") == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Remote job not found")
    return _public_remote_job(job)


@app.post("/api/remote-jobs/{job_id}/cancel")
def cancel_remote_job(job_id: str, user: dict = Depends(require_role("admin", "operator"))):
    ended_at = utc_now()
    duration_ms = 0
    with REMOTE_JOBS_LOCK:
        process = REMOTE_JOB_PROCESSES.pop(job_id, None)
        job = REMOTE_JOBS.get(job_id)
        if process and process.poll() is None:
            process.kill()
        if job:
            try:
                started = datetime.datetime.fromisoformat(str(job.get("started_at", "")).replace("Z", ""))
                duration_ms = int((datetime.datetime.utcnow() - started).total_seconds() * 1000)
            except Exception:
                duration_ms = int(job.get("duration_ms") or 0)
            job.update(
                {
                    "status": "canceled",
                    "ok": False,
                    "message": "Remote action canceled by user.",
                    "details": str(job.get("details") or ""),
                    "ended_at": ended_at,
                    "duration_ms": duration_ms,
                }
            )
            snapshot = dict(job)
        else:
            snapshot = {}

    state = load_state()
    jobs = state.get("remote_jobs", [])
    persisted = next((item for item in jobs if item.get("id") == job_id), None)
    if not snapshot and not persisted:
        raise HTTPException(status_code=404, detail="Remote job not found")
    if not snapshot and persisted:
        persisted.update(
            {
                "status": "canceled",
                "ok": False,
                "message": "Remote action canceled by user.",
                "ended_at": ended_at,
            }
        )
        snapshot = persisted
    jobs = [item for item in jobs if item.get("id") != job_id]
    jobs.insert(0, _public_remote_job(snapshot))
    state["remote_jobs"] = jobs[:100]
    save_state(state)
    audit("remote.job.cancel", user["username"], {"job_id": job_id})
    return _public_remote_job(snapshot)


@app.post("/api/remote-jobs")
def start_remote_job(request: RemoteActionRequest, user: dict = Depends(require_role("admin", "operator"))):
    host, action = validate_remote_action_request(request, user)
    job = create_remote_job(host, action, user["username"])
    audit("remote.job.create", user["username"], {"job_id": job["id"], "host": host, "action": action})
    return job


@app.post("/api/remote-actions", response_model=RemoteActionResponse)
def remote_actions(request: RemoteActionRequest, user: dict = Depends(require_role("admin", "operator"))):
    host, action = validate_remote_action_request(request, user)
    job = create_remote_job(host, action, user["username"])

    audit("remote.action", user["username"], {"job_id": job["id"], "host": host, "action": action, "status": job["status"]})
    return {
        "ok": True,
        "job_id": job["id"],
        "status": job["status"],
        "action": action,
        "host": host,
        "message": f"Remote action '{action}' sent for execution on {host}.",
        "details": "",
        "open_path": job.get("open_path") or "",
        "timestamp": job["created_at"],
    }
