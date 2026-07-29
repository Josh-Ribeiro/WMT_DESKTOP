from __future__ import annotations

import datetime
import unittest

from backend.app.services.maintenance import build_maintenance_modes_payload


class MaintenanceTrackingTests(unittest.TestCase):
    def test_active_mode_reports_actor_and_remaining_time(self) -> None:
        expires = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        ) + datetime.timedelta(minutes=45)
        payload = build_maintenance_modes_payload(
            {
                "maintenance_modes": [
                    {
                        "id": "WKS001",
                        "host": "WKS001",
                        "active": True,
                        "opened_by": "operator",
                        "technician": "Operator Name",
                        "expires_at": expires.isoformat(timespec="seconds") + "Z",
                    }
                ]
            }
        )

        self.assertEqual(1, payload["active"])
        self.assertEqual("operator", payload["modes"][0]["opened_by"])
        self.assertGreater(payload["modes"][0]["remaining_seconds"], 0)

    def test_latest_audit_event_can_recover_an_existing_mode(self) -> None:
        opened = datetime.datetime.now(datetime.UTC).replace(
            tzinfo=None
        ) - datetime.timedelta(minutes=5)
        payload = build_maintenance_modes_payload(
            {"maintenance_modes": []},
            [
                {
                    "action": "maintenance.enable",
                    "username": "operator",
                    "timestamp": opened.isoformat(timespec="seconds") + "Z",
                    "details": {
                        "host": "WKS002",
                        "technician": "Operator Name",
                        "duration_minutes": 60,
                    },
                }
            ],
        )

        self.assertEqual(["WKS002"], [item["host"] for item in payload["modes"]])


if __name__ == "__main__":
    unittest.main()
