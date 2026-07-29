"""WMT security components."""

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

from .config import (
    SSO_ADMIN_GROUPS,
    SSO_ADMIN_USERS,
    SSO_ALLOW_PRIVILEGED_DEFAULT_ROLE,
    SSO_DEFAULT_ROLE,
    SSO_OPERATOR_GROUPS,
    SSO_OPERATOR_USERS,
    SSO_VIEWER_GROUPS,
    SSO_VIEWER_USERS,
)
from ..schemas import (
    Role,
)

def utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


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


def friendly_error_message(raw_message: str, context: str = "operação") -> str:
    text = (raw_message or "").strip()
    lowered = text.lower()
    if not text:
        return f"Não foi possível concluir a {context}."

    if any(item in lowered for item in ["access is denied", "access denied", "acesso negado", "system error 5", "unauthorizedaccess"]):
        return f"Acesso negado ao executar {context}. Verifique se a conta do backend tem permissão administrativa no host de destino."
    if any(item in lowered for item in ["winrm", "wsman", "cannot connect to the destination", "the client cannot connect", "access is denied. for more information, see the about_remote_troubleshooting"]):
        return f"WinRM/PowerShell Remoting indisponível para {context}. Confirme se o host está online, com WinRM habilitado e liberado no firewall."
    if any(item in lowered for item in ["no such host", "could not resolve", "host not found", "ping request could not find host"]):
        return f"Host não encontrado para {context}. Confira o nome da WKS ou DNS."
    if any(item in lowered for item in ["network path was not found", "the network path was not found", "0x80070035", "não foi encontrado o caminho da rede", "nÃ£o foi encontrado o caminho da rede"]):
        return f"Host offline ou compartilhamento administrativo inacessível para {context}. Verifique rede, firewall e admin share."
    if any(item in lowered for item in ["sms_client", "root\\ccm", "invalid namespace", "ccmexec", "ccm_softwareupdate"]):
        return f"SCCM Client não foi encontrado ou não respondeu no host durante {context}. Verifique se o cliente SCCM está instalado e saudável."
    if any(item in lowered for item in ["logon failure", "unknown user name or bad password", "falha de logon", "usuário ou senha incorretos", "usuÃ¡rio ou senha incorretos"]):
        return f"Credencial sem permissão ou inválida para {context}. Confira usuário, senha e privilégios locais no host."
    if any(item in lowered for item in ["admin$", "c$", "multiple connections", "error 1219"]):
        return f"Admin share bloqueado ou sessão SMB conflitante durante {context}. Feche conexões antigas e confirme acesso ao C$/ADMIN$."
    return text


def public_user(user: dict) -> dict:
    payload = {
        key: value
        for key, value in user.items()
        if key != "password_hash" and not key.startswith("_")
    }
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
