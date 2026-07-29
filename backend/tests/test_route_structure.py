from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.routing import APIRoute

from backend.app.api import (
    auth,
    backup,
    dashboard,
    diagnostics,
    directory,
    documents,
    remote_operations,
    settings,
    software_center,
    system,
    update_jobs,
    users,
)
from backend.app.main import app


ROUTE_MODULES = (
    auth,
    backup,
    dashboard,
    diagnostics,
    directory,
    documents,
    remote_operations,
    settings,
    software_center,
    system,
    update_jobs,
    users,
)


class RouteStructureTests(unittest.TestCase):
    def test_all_legacy_operations_are_registered(self) -> None:
        routes = [route for route in app.routes if isinstance(route, APIRoute)]
        operations = sum(len(route.methods) for route in routes)

        self.assertEqual(68, len(routes))
        self.assertEqual(68, operations)
        self.assertEqual(61, len(app.openapi()["paths"]))

    def test_every_domain_router_has_routes(self) -> None:
        for module in ROUTE_MODULES:
            with self.subTest(module=module.__name__):
                self.assertTrue(module.router.routes)

    def test_health_identifies_the_backend_and_api_contract(self) -> None:
        health = system.health_check()
        self.assertEqual("ok", health["status"])
        self.assertEqual("wmt-backend", health["service"])
        self.assertEqual(1, health["api_version"])
        self.assertTrue(health["version"])
        with patch.object(system, "probe_state_repository"):
            self.assertEqual("ready", system.health_ready()["status"])
        self.assertEqual(
            {"message": "WMT Desktop backend is running"},
            system.read_root(),
        )


if __name__ == "__main__":
    unittest.main()
