"""WMT directory components."""

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

from .cache import (
    _cache_for,
    text_value,
)
from .powershell import (
    powershell_executable,
)
from ..core.security import (
    escape_ldap_filter_value,
)
from ..repositories.state import (
    list_audit_entries,
    load_state_fields,
)

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
    return _cache_for(f"ad-user:{key}", 60, lambda: collect_ad_user_info(query))


def cached_ad_user_matches(query: str) -> dict:
    key = _ad_user_lookup_key(query)
    return _cache_for(f"ad-user-search:{key}", 60, lambda: collect_ad_user_matches(query))


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

    for item in list_audit_entries(actions={"workstation.lookup"}):
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
