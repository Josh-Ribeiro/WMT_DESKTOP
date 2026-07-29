from __future__ import annotations

import importlib
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.app.core.security import password_hash, verify_password
from backend.app.core.validators import validate_backup_host
from backend.app.core import config


APP_DIR = Path(__file__).resolve().parents[1] / "app"
SERVICE_MODULES = (
    "auth",
    "backup",
    "cache",
    "diagnostics",
    "directory",
    "documents",
    "history",
    "inventory",
    "powershell",
    "remote_jobs",
    "remote_operations",
    "snmp",
    "temp_shares",
    "update_jobs",
)


class ModuleBoundaryTests(unittest.TestCase):
    def test_routes_use_explicit_modular_imports(self) -> None:
        for path in (APP_DIR / "api").glob("*.py"):
            with self.subTest(module=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("runtime import", source)
                self.assertNotIn("import *", source)

    def test_composition_and_compatibility_facade_stay_small(self) -> None:
        main_lines = (APP_DIR / "main.py").read_text(encoding="utf-8").splitlines()
        runtime_lines = (APP_DIR / "runtime.py").read_text(encoding="utf-8").splitlines()

        self.assertLessEqual(len(main_lines), 100)
        self.assertLessEqual(len(runtime_lines), 100)

    def test_backend_paths_are_resolved_outside_the_app_package(self) -> None:
        backend_dir = APP_DIR.parent

        self.assertEqual(backend_dir / "data", config.DATA_DIR)
        self.assertEqual(backend_dir / "scripts", config.SCRIPT_DIR)

    def test_service_modules_import_independently(self) -> None:
        for module in SERVICE_MODULES:
            with self.subTest(module=module):
                imported = importlib.import_module(f"backend.app.services.{module}")
                self.assertIsNotNone(imported)


class SecurityPrimitiveTests(unittest.TestCase):
    def test_password_hash_round_trip(self) -> None:
        encoded = password_hash("a-long-test-password")

        self.assertTrue(verify_password("a-long-test-password", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))

    def test_host_validation_rejects_command_fragments(self) -> None:
        self.assertEqual("WKS048-001BR", validate_backup_host("wks048-001br"))

        with self.assertRaises(HTTPException):
            validate_backup_host("WKS01; Remove-Item C:\\")


if __name__ == "__main__":
    unittest.main()
