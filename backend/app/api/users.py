from __future__ import annotations

import secrets
from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi import APIRouter

from ..core.security import (
    password_hash,
    public_user,
    utc_now,
)
from ..repositories.state import (
    audit,
    load_state,
    mutate_state,
)
from ..schemas import (
    UserCreateRequest,
    UserStatusRequest,
    UserUpdateRequest,
)
from ..services.auth import require_role

router = APIRouter()


@router.get("/api/users")
def users(user: dict = Depends(require_role("admin"))):
    state = load_state()
    users_list = sorted(
        [public_user(item) for item in state["users"]],
        key=lambda item: (str(item.get("auth_source") or ""), str(item.get("username") or "").lower()),
    )
    return {"users": users_list, "total": len(users_list)}


@router.post("/api/users")
def create_user(request: UserCreateRequest, user: dict = Depends(require_role("admin"))):
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

    def create(state: dict) -> None:
        if any(
            item["username"].lower() == request.username.lower()
            for item in state["users"]
        ):
            raise HTTPException(status_code=409, detail="Username already exists")
        state["users"].append(new_user)

    mutate_state(create)
    audit("users.create", user["username"], {"target": new_user["username"]})
    return public_user(new_user)


@router.put("/api/users/{user_id}")
def update_user(user_id: str, request: UserUpdateRequest, user: dict = Depends(require_role("admin"))):
    def update(state: dict) -> dict:
        stored_user = next(
            (item for item in state["users"] if item["id"] == user_id),
            None,
        )
        if not stored_user:
            raise HTTPException(status_code=404, detail="User not found")
        if request.email is not None:
            stored_user["email"] = request.email.strip()
        if request.role is not None:
            stored_user["role"] = request.role
            stored_user["role_source"] = "manual"
        if request.status is not None:
            stored_user["status"] = request.status
        return public_user(stored_user)

    updated_user = mutate_state(update)
    audit("users.update", user["username"], {"target": updated_user["username"]})
    return updated_user


@router.post("/api/users/{user_id}/status")
def update_user_status(user_id: str, request: UserStatusRequest, user: dict = Depends(require_role("admin"))):
    return update_user(user_id, UserUpdateRequest(status=request.status), user)


@router.delete("/api/users/{user_id}")
def delete_user(user_id: str, user: dict = Depends(require_role("admin"))):
    if user["id"] == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    def delete(state: dict) -> None:
        users = state["users"]
        next_users = [item for item in users if item["id"] != user_id]
        if len(next_users) == len(users):
            raise HTTPException(status_code=404, detail="User not found")
        state["users"] = next_users

    mutate_state(delete)
    audit("users.delete", user["username"], {"target_id": user_id})
    return {"ok": True}
