"""WMT schemas components."""

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

Role = Literal["admin", "operator", "viewer"]


UserStatus = Literal["active", "inactive", "locked"]


BackupStatus = Literal["completed", "running", "failed", "scheduled", "canceled"]


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12)


class LookupRequest(BaseModel):
    host: str


class ADUserLookupRequest(BaseModel):
    query: str = Field(min_length=2)


class UniversalSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=8, ge=1, le=20)


class LookupResponse(BaseModel):
    device_type: str = "workstation"
    online: bool
    hostname: str = ""
    error: str = ""
    active_directory: dict = Field(default_factory=dict)
    printer: dict = Field(default_factory=dict)
    current_user: str = ""
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    os: str = ""
    ram_gb: int = 0
    processor: str = ""
    last_boot: str = ""
    storage_total_gb: int = 0
    storage_free_gb: int = 0
    ip_address: str = ""
    mac_address: str = ""


class RemoteActionRequest(BaseModel):
    host: str
    action: str


class MaintenanceModeRequest(BaseModel):
    host: str
    action: Literal["enable", "disable"]
    contact: str = Field(default="Service Desk", max_length=200)
    ticket: str = Field(default="", max_length=100)
    reason: str = Field(default="", max_length=500)
    duration_minutes: int = Field(default=60, ge=5, le=1440)
    target_user: str = Field(default="", max_length=200)


class HostRequest(BaseModel):
    host: str


class WorkstationHistoryRequest(BaseModel):
    host: str


class DiagnosticRequest(BaseModel):
    host: str
    detailed: bool = False


class RemoteActionResponse(BaseModel):
    ok: bool
    job_id: str = ""
    status: str = ""
    action: str
    host: str
    message: str
    details: str = ""
    open_path: str = ""
    timestamp: str


class SoftwareCenterInstallRequest(BaseModel):
    host: str = "localhost"


class AppSettingsUpdateRequest(BaseModel):
    display_language: Literal["en-US", "pt-BR"] = "en-US"
    software_center_timeout_seconds: int = Field(ge=30, le=1800)
    software_center_poll_interval_seconds: int = Field(ge=5, le=300)
    update_job_timeout_minutes: int = Field(ge=5, le=720)
    backup_default_destination_path: str = ""
    scripts_enabled: dict[str, bool] = Field(default_factory=dict)
    remote_action_aliases: dict[str, str] = Field(default_factory=dict)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3)
    email: str
    role: Role = "viewer"
    password: str = Field(min_length=12)


class UserUpdateRequest(BaseModel):
    email: str | None = None
    role: Role | None = None
    status: UserStatus | None = None


class UserStatusRequest(BaseModel):
    status: UserStatus


class BackupUsersRequest(BaseModel):
    source: str = Field(min_length=1)
    remote_user: str | None = None
    remote_pass: str | None = None


class BackupOpenDestinationRequest(BaseModel):
    destination: str = Field(min_length=1)
    destination_path: str | None = None
    create_if_missing: bool = True
    remote_user: str | None = None
    remote_pass: str | None = None


class BackupCreateRequest(BaseModel):
    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    users: list[str] = Field(default_factory=list)
    destination_path: str | None = None
    exclude_patterns: list[str] = Field(default_factory=list)
    remote_user: str | None = None
    remote_pass: str | None = None


class BackupPrecheckRequest(BackupCreateRequest):
    quick: bool = False


class BackupCustomFolderRequest(BaseModel):
    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    destination_path: str = Field(min_length=1)
    exclude_patterns: list[str] = Field(default_factory=list)
    remote_user: str | None = None
    remote_pass: str | None = None


class BackupChecklistRequest(BaseModel):
    checklist: dict[str, bool] = Field(default_factory=dict)


class BackupRetryFolderRequest(BaseModel):
    profile: str = Field(min_length=1)
    folder: str = Field(min_length=1)


class BackupRetentionRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=3650)
    keep_last: int = Field(default=20, ge=0, le=500)


class MachineReplacementReportRequest(BaseModel):
    source: str = Field(min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    employee_name: str = Field(default="", max_length=200)
    technician: str = Field(default="", max_length=200)
    profiles: list[str] = Field(default_factory=list, max_length=200)
    precheck_status: str = Field(default="", max_length=40)
    precheck_message: str = Field(default="", max_length=500)
    backup_job_id: str = Field(default="", max_length=100)
    backup_status: str = Field(default="", max_length=40)
    backup_summary: str = Field(default="", max_length=2000)
    validation_status: str = Field(default="", max_length=80)
    term_generated: bool = False
    applications: list[dict[str, str]] = Field(default_factory=list, max_length=1000)


class TermsGenerateRequest(BaseModel):
    wk: str = Field(min_length=1)
    employee_name: str = ""
    term_type: Literal["responsibility", "return"] = "responsibility"
