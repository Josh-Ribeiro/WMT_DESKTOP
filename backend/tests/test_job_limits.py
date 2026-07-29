from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.app.services import remote_jobs, update_jobs


class JobLimitTests(unittest.TestCase):
    def tearDown(self) -> None:
        remote_jobs.REMOTE_JOBS.clear()
        update_jobs.UPDATE_JOBS.clear()

    def test_remote_jobs_reject_new_work_when_capacity_is_full(self) -> None:
        remote_jobs.REMOTE_JOBS["active"] = {"status": "running"}
        with patch.object(remote_jobs, "MAX_CONCURRENT_REMOTE_JOBS", 1):
            with self.assertRaisesRegex(RuntimeError, "Limite"):
                remote_jobs.create_remote_job("WK-001", "gpupdate", "operator")

    def test_update_jobs_reject_new_work_when_capacity_is_full(self) -> None:
        update_jobs.UPDATE_JOBS["active"] = {"status": "queued"}
        with patch.object(update_jobs, "MAX_CONCURRENT_UPDATE_JOBS", 1):
            with self.assertRaisesRegex(RuntimeError, "Limite"):
                update_jobs.create_update_job("WK-001", "operator")


if __name__ == "__main__":
    unittest.main()
