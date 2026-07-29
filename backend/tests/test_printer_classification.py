from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.app.services.inventory import collect_machine_info
from backend.app.services.history import _universal_workstation_matches
from backend.app.services.snmp import (
    is_forced_printer_host,
    looks_like_printer_host,
)


class PrinterNetworkClassificationTests(unittest.TestCase):
    def test_reserved_range_boundaries_are_printers(self) -> None:
        self.assertFalse(is_forced_printer_host("10.131.200.0"))
        self.assertTrue(is_forced_printer_host("10.131.200.1"))
        self.assertTrue(is_forced_printer_host("10.131.200.254"))
        self.assertTrue(is_forced_printer_host("10.131.200.255"))
        self.assertFalse(is_forced_printer_host("10.131.201.1"))
        self.assertFalse(is_forced_printer_host("printer.example"))

        self.assertTrue(looks_like_printer_host("10.131.200.42"))

    @patch(
        "backend.app.services.history.load_state_fields",
        return_value={
            "audit": [],
            "backup_jobs": [],
            "remote_jobs": [],
            "update_jobs": [],
        },
    )
    def test_universal_search_reports_printer_type(self, _state_mock) -> None:
        matches = _universal_workstation_matches("10.131.200.42", 8)

        self.assertEqual(1, len(matches))
        self.assertEqual("printer", matches[0]["device_type"])

    @patch(
        "backend.app.services.inventory.collect_active_directory_info",
        return_value={},
    )
    @patch("backend.app.services.inventory.ping_host", return_value=False)
    def test_offline_address_keeps_printer_type(
        self,
        _ping_mock,
        _ad_mock,
    ) -> None:
        result = collect_machine_info("10.131.200.10")

        self.assertEqual("printer", result["device_type"])
        self.assertFalse(result["online"])
        self.assertIn("Printer", result["error"])

    @patch(
        "backend.app.services.inventory.collect_active_directory_info",
        return_value={},
    )
    @patch(
        "backend.app.services.inventory.collect_wmi_workstation_info",
        return_value={"device_type": "workstation", "online": True},
    )
    @patch(
        "backend.app.services.inventory.collect_printer_info",
        return_value={"detected": False, "error": "SNMP unavailable"},
    )
    @patch("backend.app.services.inventory.ping_host", return_value=True)
    def test_reserved_address_never_falls_back_to_workstation(
        self,
        _ping_mock,
        _printer_mock,
        wmi_mock,
        _ad_mock,
    ) -> None:
        result = collect_machine_info("10.131.200.99")

        self.assertEqual("printer", result["device_type"])
        self.assertTrue(result["online"])
        self.assertEqual("SNMP unavailable", result["printer"]["error"])
        wmi_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
