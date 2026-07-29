from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi import APIRouter

from ..repositories.state import audit
from ..schemas import (
    ADUserLookupRequest,
    LookupRequest,
    LookupResponse,
    UniversalSearchRequest,
    WorkstationHistoryRequest,
)
from ..services.auth import (
    current_user,
    require_role,
)
from ..services.cache import text_value
from ..services.directory import (
    cached_ad_user_info,
    cached_ad_user_matches,
)
from ..services.history import (
    _universal_workstation_matches,
    build_workstation_history,
)
from ..services.inventory import (
    cached_collect_machine_info,
    collect_machine_info,
)

router = APIRouter()


@router.post("/api/lookup", response_model=LookupResponse)
def lookup_machine(request: LookupRequest, user: dict = Depends(current_user)):
    host = request.host.strip()
    if not host:
        raise HTTPException(status_code=400, detail="Host is required")
    result = cached_collect_machine_info(host)
    current = str(result.get("current_user") or "").strip()
    audit(
        "workstation.lookup",
        user["username"],
        {
            "host": str(result.get("hostname") or host),
            "device_type": str(result.get("device_type") or "workstation"),
            "current_user": current,
            "ip_address": str(result.get("ip_address") or ""),
            "os": str(result.get("os") or ""),
            "serial_number": str(result.get("serial_number") or ""),
            "manufacturer": str(result.get("manufacturer") or ""),
            "model": str(result.get("model") or ""),
        },
    )
    return LookupResponse(**result)


@router.post("/api/ad-users/lookup")
def lookup_ad_user(request: ADUserLookupRequest, user: dict = Depends(current_user)):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="User query is required")
    result = cached_ad_user_info(query)
    audit("ad_user.lookup", user["username"], {"query": query, "found": bool(result.get("found"))})
    return result


@router.post("/api/ad-users/search")
def search_ad_users(request: ADUserLookupRequest, user: dict = Depends(current_user)):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="User query is required")
    result = cached_ad_user_matches(query)
    audit("ad_user.search", user["username"], {"query": query, "total": result.get("total", 0)})
    return result


@router.post("/api/search/universal")
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


@router.post("/api/workstations/history")
def workstation_history_post(request: WorkstationHistoryRequest, user: dict = Depends(require_role("admin", "operator"))):
    return build_workstation_history(request.host)


@router.get("/api/workstations/{host}/history")
def workstation_history(host: str, user: dict = Depends(require_role("admin", "operator"))):
    return build_workstation_history(host)


@router.get("/api/workstations")
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
