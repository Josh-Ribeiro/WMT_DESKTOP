"""WMT snmp components."""

from __future__ import annotations

import datetime
import concurrent.futures
import copy
import hashlib
import ipaddress
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

from ..core.utils import (
    future_result,
)

PRINTER_IPV4_NETWORK = ipaddress.ip_network("10.131.200.0/24")


def is_forced_printer_host(host: str) -> bool:
    """Return True for IPv4 addresses reserved exclusively for printers."""
    try:
        address = ipaddress.ip_address(host.strip())
    except ValueError:
        return False
    return (
        isinstance(address, ipaddress.IPv4Address)
        and address in PRINTER_IPV4_NETWORK
        and int(str(address).rsplit(".", 1)[-1]) >= 1
    )


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
    if is_forced_printer_host(host):
        return True
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
