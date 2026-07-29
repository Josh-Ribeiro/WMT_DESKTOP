"""WMT inventory components."""

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
    ping_host,
    text_value,
)
from .powershell import (
    powershell_executable,
)
from .snmp import (
    collect_printer_info,
    is_forced_printer_host,
    looks_like_printer_host,
)
from ..core.utils import (
    future_result,
    pythoncom,
    wmi,
)

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
    forced_printer = is_forced_printer_host(host)
    info = {
        "device_type": "printer" if forced_printer else "workstation",
        "online": False,
        "hostname": host,
    }

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="lookup")
    try:
        ad_future = executor.submit(collect_active_directory_info, host)
        ping_future = executor.submit(ping_host, host)

        if not bool(future_result(ping_future, 8.0, False)):
            active_directory = future_result(ad_future, 4.0, {}) or {}
            return {
                **info,
                "error": (
                    "Printer is offline or unreachable"
                    if forced_printer
                    else "Host is offline or unreachable"
                ),
                "active_directory": active_directory,
            }

        info["online"] = True
        printer_likely_future = executor.submit(looks_like_printer_host, host)
        wmi_future = (
            None
            if forced_printer
            else executor.submit(collect_wmi_workstation_info, host)
        )
        printer_future: concurrent.futures.Future | None = None

        if bool(future_result(printer_likely_future, 1.0, False)):
            printer_future = executor.submit(collect_printer_info, host)
            printer = future_result(printer_future, 4.0, {}) or {}
            if forced_printer or (
                isinstance(printer, dict) and printer.get("detected")
            ):
                active_directory = future_result(ad_future, 2.0, {}) or {}
                printer = printer if isinstance(printer, dict) else {}
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

        wmi_info = (
            future_result(wmi_future, 8.0, None)
            if wmi_future is not None
            else None
        )
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
    return _cache_for(f"lookup:{normalized}", 45, lambda: collect_machine_info(host))
