from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query, Request, Response
from fastapi import APIRouter

from ..core.config import (
    ALLOW_BEARER_AUTH,
    SSO_CLIENT_IP_FALLBACK,
    SSO_DEBUG_ENABLED,
    SSO_DESKTOP_FALLBACK,
    SSO_ENABLED,
    SSO_TRUSTED_PROXY_IPS,
    cors_origins,
)
from ..core.security import (
    is_loopback_client,
    password_hash,
    public_user,
    role_permissions,
    utc_now,
    verify_password,
)
from ..repositories.state import (
    audit,
    mutate_state,
)
from ..schemas import (
    ChangePasswordRequest,
    LoginRequest,
)
from ..services.auth import (
    SESSIONS,
    clear_session_cookie,
    clear_login_failures,
    create_session_for_user,
    current_user,
    current_windows_identity,
    enforce_login_rate_limit,
    logged_user_from_host,
    record_login_failure,
    require_role,
    set_session_cookie,
    sso_user_from_identity,
)

router = APIRouter()


@router.post("/api/auth/login")
def login(request: LoginRequest, response: Response, http_request: Request):
    client_ip = http_request.client.host if http_request.client else "unknown"
    enforce_login_rate_limit(client_ip, request.username)

    def authenticate(state: dict) -> dict:
        user = next(
            (
                item
                for item in state["users"]
                if item["username"].lower() == request.username.lower()
            ),
            None,
        )
        if not user or not verify_password(request.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if user["status"] != "active":
            raise HTTPException(status_code=403, detail="User is not active")
        user["last_login"] = utc_now()
        return dict(user)

    try:
        user = mutate_state(authenticate)
    except HTTPException as exc:
        if exc.status_code == 401:
            record_login_failure(client_ip, request.username)
        raise
    clear_login_failures(client_ip, request.username)
    user["auth_source"] = "local"
    token, expires_at, csrf_token = create_session_for_user(user)
    set_session_cookie(response, token)
    audit("auth.login", user["username"])

    payload = {
        "user": user["username"],
        "role": user["role"],
        "permissions": role_permissions(user["role"]),
        "csrf_token": csrf_token,
        "expires_at": expires_at.isoformat(timespec="seconds") + "Z",
    }
    if ALLOW_BEARER_AUTH:
        payload["access_token"] = token
    return payload


@router.post("/api/auth/sso")
def sso_login(
    request: Request,
    response: Response,
    x_remote_user: str | None = Header(default=None),
    x_windows_user: str | None = Header(default=None),
    x_iis_winauth_user: str | None = Header(default=None),
    x_forwarded_for: str | None = Header(default=None),
):
    if not SSO_ENABLED:
        raise HTTPException(status_code=404, detail="SSO is disabled")

    direct_client_ip = request.client.host if request.client else ""
    forwarded_client_ip = (x_forwarded_for or "").split(",", 1)[0].strip()
    trusted_proxy = direct_client_ip in SSO_TRUSTED_PROXY_IPS
    client_ip = forwarded_client_ip if trusted_proxy and forwarded_client_ip else direct_client_ip
    identity = x_remote_user or x_windows_user or x_iis_winauth_user
    auth_mode = "iis"

    if identity and not trusted_proxy:
        raise HTTPException(status_code=403, detail="SSO headers are accepted only from trusted proxy")

    if not identity and SSO_DESKTOP_FALLBACK and is_loopback_client(direct_client_ip):
        identity = current_windows_identity()
        auth_mode = "desktop"
    elif not identity and SSO_CLIENT_IP_FALLBACK:
        identity = logged_user_from_host(client_ip)
        auth_mode = "client-ip"
    if not identity:
        raise HTTPException(
            status_code=401,
            detail="Não foi possível identificar o usuário Windows desta estação",
        )

    user = sso_user_from_identity(identity)
    if user.get("status") != "active":
        raise HTTPException(status_code=403, detail="User is not active")
    token, expires_at, csrf_token = create_session_for_user(user)
    set_session_cookie(response, token)
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
    payload = {
        "user": user["username"],
        "role": user["role"],
        "permissions": role_permissions(user["role"]),
        "display_name": user.get("display_name") or user["username"],
        "email": user.get("email") or "",
        "domain": user.get("domain") or "",
        "groups": user.get("groups") or [],
        "auth_source": "windows",
        "auth_mode": auth_mode,
        "csrf_token": csrf_token,
        "expires_at": expires_at.isoformat(timespec="seconds") + "Z",
    }
    if ALLOW_BEARER_AUTH:
        payload["access_token"] = token
    return payload


@router.get("/api/auth/sso/debug")
def sso_debug(
    request: Request,
    x_forwarded_for: str | None = Header(default=None),
    user: dict = Depends(require_role("admin")),
):
    if not SSO_DEBUG_ENABLED:
        raise HTTPException(status_code=404, detail="SSO diagnostics are disabled")

    direct_client_ip = request.client.host if request.client else ""
    forwarded_client_ip = (x_forwarded_for or "").split(",", 1)[0].strip()
    trusted_proxy = direct_client_ip in SSO_TRUSTED_PROXY_IPS
    client_ip = forwarded_client_ip if trusted_proxy and forwarded_client_ip else direct_client_ip
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


@router.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return {
        **public_user(user),
        "permissions": role_permissions(user["role"]),
        "csrf_token": user.get("_csrf_token", ""),
    }


@router.post("/api/auth/logout")
def logout(
    response: Response,
    user: dict = Depends(current_user),
):
    SESSIONS.pop(str(user.get("_session_token") or ""), None)
    clear_session_cookie(response)
    return {"message": "logged out"}


@router.post("/api/account/change-password")
def change_password(request: ChangePasswordRequest, user: dict = Depends(current_user)):
    def change(state: dict) -> str:
        stored_user = next(
            (item for item in state["users"] if item["id"] == user["id"]),
            None,
        )
        if not stored_user or not verify_password(
            request.old_password,
            stored_user["password_hash"],
        ):
            raise HTTPException(
                status_code=400,
                detail="Current password is incorrect",
            )
        stored_user["password_hash"] = password_hash(request.new_password)
        return stored_user["username"]

    username = mutate_state(change)
    audit("account.change_password", username)
    return {"message": "Password changed successfully"}
    enforce_login_rate_limit,
