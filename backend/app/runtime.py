"""Compatibility facade for the modular backend runtime.

New code should import from ``core``, ``repositories``, ``schemas``, or
``services`` directly. Route modules still import this facade so their public
contract can remain unchanged during the migration.
"""

from __future__ import annotations

from . import schemas as _schemas
from .core import (
    config as _config,
    security as _security,
    utils as _utils,
    validators as _validators,
)
from .repositories import state as _state
from .services import (
    auth as _auth,
    backup as _backup,
    cache as _cache,
    diagnostics as _diagnostics,
    directory as _directory,
    documents as _documents,
    history as _history,
    inventory as _inventory,
    powershell as _powershell,
    remote_jobs as _remote_jobs,
    remote_operations as _remote_operations,
    snmp as _snmp,
    temp_shares as _temp_shares,
    update_jobs as _update_jobs,
)

_RUNTIME_MODULES = (
    _config,
    _security,
    _validators,
    _utils,
    _schemas,
    _state,
    _cache,
    _powershell,
    _directory,
    _auth,
    _temp_shares,
    _remote_jobs,
    _update_jobs,
    _snmp,
    _inventory,
    _diagnostics,
    _documents,
    _history,
    _backup,
    _remote_operations,
)

for _module in _RUNTIME_MODULES:
    for _name, _value in vars(_module).items():
        if not _name.startswith("__"):
            globals()[_name] = _value

del _module, _name, _value
