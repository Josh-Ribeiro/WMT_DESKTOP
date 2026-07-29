"""WMT cache components."""

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

RESPONSE_CACHE_LOCK = threading.Lock()


RESPONSE_CACHE: dict[str, dict] = {}


RESPONSE_CACHE_INFLIGHT_LOCK = threading.Lock()


RESPONSE_CACHE_INFLIGHT: dict[str, threading.Event] = {}


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
