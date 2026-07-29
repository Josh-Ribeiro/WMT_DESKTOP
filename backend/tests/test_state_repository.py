from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.core.security import password_hash, verify_password
from backend.app.repositories import state as state_repository


class SQLiteStateRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        data_dir = Path(self.temporary_directory.name)
        self.patchers = (
            patch.object(state_repository, "DATA_DIR", data_dir),
            patch.object(state_repository, "STATE_DB_FILE", data_dir / "state.db"),
            patch.object(state_repository, "STATE_FILE", data_dir / "state.json"),
            patch.object(state_repository, "BOOTSTRAP_ADMIN_USERNAME", "admin"),
            patch.object(state_repository, "BOOTSTRAP_ADMIN_EMAIL", ""),
            patch.object(state_repository, "BOOTSTRAP_ADMIN_PASSWORD", ""),
        )
        for patcher in self.patchers:
            patcher.start()
        state_repository.STATE_CACHE = None
        state_repository.STATE_CACHE_REVISION = None

    def tearDown(self) -> None:
        state_repository.STATE_CACHE = None
        state_repository.STATE_CACHE_REVISION = None
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temporary_directory.cleanup()

    def test_new_database_has_no_default_credentials_or_demo_job(self) -> None:
        state = state_repository.load_state()

        self.assertEqual([], state["users"])
        self.assertEqual([], state["backup_jobs"])
        self.assertTrue(state_repository.STATE_DB_FILE.is_file())
        self.assertFalse(state_repository.STATE_FILE.exists())

    def test_legacy_json_is_migrated_and_insecure_admin_is_locked(self) -> None:
        legacy = {
            "users": [
                {
                    "id": "usr-admin",
                    "username": "admin",
                    "email": "admin@example.test",
                    "role": "admin",
                    "status": "active",
                    "password_hash": password_hash("admin123"),
                }
            ],
            "backup_jobs": [
                {
                    "id": "BK001",
                    "workstation": "localhost",
                    "start_time": "2026-05-28 10:00:00",
                    "size": "256 GB",
                },
                {"id": "REAL-1", "workstation": "WKS048-001BR"},
            ],
        }
        state_repository.STATE_FILE.write_text(
            json.dumps(legacy),
            encoding="utf-8",
        )

        migrated = state_repository.load_state()

        self.assertEqual("locked", migrated["users"][0]["status"])
        self.assertEqual(["REAL-1"], [job["id"] for job in migrated["backup_jobs"]])
        self.assertTrue(state_repository.STATE_FILE.is_file())
        self.assertTrue(state_repository.STATE_DB_FILE.is_file())

    def test_strong_bootstrap_secret_creates_the_first_admin(self) -> None:
        with (
            patch.object(
                state_repository,
                "BOOTSTRAP_ADMIN_PASSWORD",
                "a-unique-bootstrap-secret",
            ),
            patch.object(
                state_repository,
                "BOOTSTRAP_ADMIN_EMAIL",
                "wmt-admin@example.test",
            ),
        ):
            state = state_repository.load_state()

        self.assertEqual(1, len(state["users"]))
        admin = state["users"][0]
        self.assertEqual("admin", admin["username"])
        self.assertEqual("admin", admin["role"])
        self.assertTrue(
            verify_password("a-unique-bootstrap-secret", admin["password_hash"])
        )

    def test_stale_snapshot_cannot_overwrite_newer_state(self) -> None:
        first = state_repository.load_state()
        stale = state_repository.load_state()
        first["settings"]["display_language"] = "pt-BR"
        state_repository.save_state(first)
        stale["settings"]["display_language"] = "de-DE"

        with self.assertRaises(state_repository.StateConflictError):
            state_repository.save_state(stale)

        self.assertEqual(
            "pt-BR",
            state_repository.load_state()["settings"]["display_language"],
        )

    def test_mutation_retries_after_a_revision_conflict(self) -> None:
        original_save = state_repository.save_state
        attempts = 0

        def conflict_once(state: dict) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise state_repository.StateConflictError("simulated conflict")
            original_save(state)

        def enable_portuguese(state: dict) -> str:
            state["settings"]["display_language"] = "pt-BR"
            return "updated"

        with patch.object(state_repository, "save_state", conflict_once):
            result = state_repository.mutate_state(enable_portuguese)

        self.assertEqual("updated", result)
        self.assertEqual(2, attempts)
        self.assertEqual(
            "pt-BR",
            state_repository.load_state()["settings"]["display_language"],
        )


if __name__ == "__main__":
    unittest.main()
