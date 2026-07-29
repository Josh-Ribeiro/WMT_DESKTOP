"""WMT utils components."""

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

try:
    import wmi
except ImportError:
    wmi = None


try:
    import pythoncom
except ImportError:
    pythoncom = None


def future_result(future: concurrent.futures.Future, timeout: float, default: object = None) -> object:
    try:
        return future.result(timeout=timeout)
    except Exception:
        return default
