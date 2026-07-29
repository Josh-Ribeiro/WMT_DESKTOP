"""WMT validators components."""

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
    HOST_PATTERN,
)

def validate_backup_host(value: str) -> str:
    host = (value or "").strip().strip("\\/").upper()
    if not host:
        raise HTTPException(status_code=400, detail="Host is required")
    if not HOST_PATTERN.match(host):
        raise HTTPException(status_code=400, detail="Host contains unsupported characters")
    return host


def _temporary_share_name(drive_letter: str) -> str:
    drive = (drive_letter or "C").replace(":", "").replace("\\", "").replace("/", "").strip().upper() or "C"
    return f"WMT_TEMP_{drive}$"


def _normalize_drive_letter(drive: str | None, default: str = "C") -> str:
    safe_drive = (drive or default).replace(":", "").replace("\\", "").replace("/", "").strip().upper() or default
    if not re.fullmatch(r"[A-Z]", safe_drive):
        raise RuntimeError("Invalid destination drive")
    return safe_drive
