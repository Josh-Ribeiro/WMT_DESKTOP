"""WMT auth components."""

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
from fastapi import Cookie, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .cache import (
    text_value,
)
from ..core.config import (
    ALLOW_BEARER_AUTH,
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    SSO_ALLOWED_GROUPS,
    TOKEN_TTL_SECONDS,
)
from .directory import (
    query_ad_user,
)
from .powershell import (
    powershell_executable,
)
from ..schemas import (
    Role,
)
from ..core.security import (
    friendly_error_message,
    group_matches,
    is_loopback_client,
    normalize_windows_identity,
    sso_role_for_user,
    utc_now,
)
from ..repositories.state import (
    mutate_state,
    state_user_by_id,
)
from ..core.utils import (
    pythoncom,
    wmi,
)

SESSIONS: dict[str, dict] = {}
LOGIN_FAILURES: dict[str, list[float]] = {}
LOGIN_FAILURES_LOCK = threading.Lock()


def _login_rate_limit_key(client_ip: str, username: str) -> str:
    return f"{(client_ip or 'unknown').strip().lower()}:{username.strip().lower()}"


def _active_login_failures(key: str, now: float) -> list[float]:
    cutoff = now - LOGIN_RATE_LIMIT_WINDOW_SECONDS
    return [
        attempt
        for attempt in LOGIN_FAILURES.get(key, [])
        if attempt >= cutoff
    ]


def enforce_login_rate_limit(client_ip: str, username: str) -> None:
    key = _login_rate_limit_key(client_ip, username)
    now = time.monotonic()
    with LOGIN_FAILURES_LOCK:
        attempts = _active_login_failures(key, now)
        if attempts:
            LOGIN_FAILURES[key] = attempts
        else:
            LOGIN_FAILURES.pop(key, None)
        if len(attempts) < LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
            return
        retry_after = max(
            1,
            int(LOGIN_RATE_LIMIT_WINDOW_SECONDS - (now - attempts[0])),
        )
    raise HTTPException(
        status_code=429,
        detail="Too many login attempts. Try again later.",
        headers={"Retry-After": str(retry_after)},
    )


def record_login_failure(client_ip: str, username: str) -> None:
    key = _login_rate_limit_key(client_ip, username)
    now = time.monotonic()
    with LOGIN_FAILURES_LOCK:
        attempts = _active_login_failures(key, now)
        attempts.append(now)
        LOGIN_FAILURES[key] = attempts[-LOGIN_RATE_LIMIT_MAX_ATTEMPTS:]


def clear_login_failures(client_ip: str, username: str) -> None:
    key = _login_rate_limit_key(client_ip, username)
    with LOGIN_FAILURES_LOCK:
        LOGIN_FAILURES.pop(key, None)


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
        raise HTTPException(status_code=401, detail="PowerShell não encontrado para consultar usuário remoto")

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
            detail=f"Não foi possível detectar usuário logado no cliente {target}. {friendly_error_message(detail, 'consulta do usuário logado')}",
        )
    return logged_user


def sso_user_from_identity(identity: str) -> dict:
    if not SSO_ALLOWED_GROUPS:
        raise HTTPException(
            status_code=503,
            detail="SSO is not configured with an allowed group",
        )

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
    def upsert(state: dict) -> dict:
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
                if str(item.get("id") or "").lower()
                == str(sso_user.get("id") or "").lower()
                or (
                    str(item.get("auth_source") or "") == "windows"
                    and str(item.get("username") or "").lower() == username
                    and str(item.get("domain") or "").lower() == domain
                )
                or (upn and str(item.get("upn") or "").lower() == upn)
                or (
                    email
                    and str(item.get("email") or "").lower() == email
                    and str(item.get("auth_source") or "") == "windows"
                )
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
            return dict(stored_user)

        manual_role = stored_user.get("role_source") == "manual"
        stored_user.update(
            {
                "email": sso_user.get("email") or stored_user.get("email", ""),
                "display_name": sso_user.get("display_name")
                or stored_user.get("display_name")
                or sso_user.get("username", ""),
                "domain": sso_user.get("domain")
                or stored_user.get("domain", ""),
                "windows_identity": sso_user.get("windows_identity")
                or stored_user.get("windows_identity", ""),
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
        return dict(stored_user)

    return mutate_state(upsert)


def create_session_for_user(
    user: dict,
) -> tuple[str, datetime.datetime, str]:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = datetime.datetime.now(datetime.UTC).replace(
        tzinfo=None
    ) + datetime.timedelta(seconds=TOKEN_TTL_SECONDS)
    session = {
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "source": user.get("auth_source", "local"),
        "csrf_token": csrf_token,
    }
    if user.get("auth_source") == "windows":
        session["user"] = user
    else:
        session["user_id"] = user["id"]
    SESSIONS[token] = session
    return token, expires_at, csrf_token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
        path="/api",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/api",
        secure=SESSION_COOKIE_SECURE,
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
    )


def current_user(
    request: Request,
    session_cookie: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE_NAME,
    ),
    authorization: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> dict:
    token = session_cookie or ""
    cookie_authenticated = bool(token)
    if (
        not token
        and ALLOW_BEARER_AUTH
        and authorization
        and authorization.startswith("Bearer ")
    ):
        token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing session cookie")

    session = SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = datetime.datetime.fromisoformat(session["expires_at"])
    if expires_at < datetime.datetime.now(datetime.UTC).replace(tzinfo=None):
        SESSIONS.pop(token, None)
        raise HTTPException(status_code=401, detail="Session expired")

    if cookie_authenticated and request.method.upper() not in {
        "GET",
        "HEAD",
        "OPTIONS",
    }:
        expected_csrf = str(session.get("csrf_token") or "")
        if (
            not expected_csrf
            or not x_csrf_token
            or not secrets.compare_digest(expected_csrf, x_csrf_token)
        ):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")

    if session.get("user"):
        user = session["user"]
        stored_user = state_user_by_id(user.get("id"))
        if stored_user:
            user = stored_user
            session["user"] = stored_user
        if user.get("status") != "active":
            raise HTTPException(status_code=403, detail="User is not active")
        return {
            **user,
            "_session_token": token,
            "_csrf_token": session.get("csrf_token", ""),
        }

    user = state_user_by_id(session.get("user_id"))
    if not user or user["status"] != "active":
        raise HTTPException(status_code=403, detail="User is not active")
    return {
        **user,
        "_session_token": token,
        "_csrf_token": session.get("csrf_token", ""),
    }


def require_role(*roles: Role):
    def dependency(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return dependency
