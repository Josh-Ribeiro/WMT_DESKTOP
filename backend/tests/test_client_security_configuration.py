from __future__ import annotations

import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app


ROOT = Path(__file__).resolve().parents[2]


class ClientSecurityConfigurationTests(unittest.TestCase):
    def test_tauri_has_csp_and_https_updater(self) -> None:
        config = json.loads(
            (ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
        )
        csp = config["app"]["security"]["csp"]
        updater = config["plugins"]["updater"]

        self.assertIsInstance(csp, str)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertFalse(updater["dangerousInsecureTransportProtocol"])
        self.assertTrue(
            all(
                endpoint.startswith("https://")
                for endpoint in updater["endpoints"]
            )
        )

    def test_frontend_does_not_persist_or_send_bearer_token(self) -> None:
        client_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "client" / "src").rglob("*")
            if path.suffix in {".ts", ".tsx"}
        )

        self.assertNotIn("localStorage.setItem('wmt_token'", client_source)
        self.assertNotIn("localStorage.getItem('wmt_token'", client_source)
        self.assertNotIn("Authorization: `Bearer", client_source)

    def test_production_api_url_uses_https(self) -> None:
        production_env = (ROOT / ".env.production").read_text(encoding="utf-8")

        self.assertIn("VITE_API_BASE_URL=https://", production_env)

    def test_tauri_origin_receives_credentialed_cors_headers(self) -> None:
        response = TestClient(app).options(
            "/api/auth/me",
            headers={
                "Origin": "https://tauri.localhost",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            "https://tauri.localhost",
            response.headers["access-control-allow-origin"],
        )
        self.assertEqual(
            "true",
            response.headers["access-control-allow-credentials"],
        )

    def test_opaque_and_arbitrary_local_origins_are_rejected(self) -> None:
        client = TestClient(app)
        for origin in ("null", "http://localhost:43127"):
            with self.subTest(origin=origin):
                response = client.options(
                    "/api/auth/me",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "GET",
                    },
                )
                self.assertEqual(400, response.status_code)
                self.assertNotIn(
                    "access-control-allow-origin",
                    response.headers,
                )

    def test_frontend_validates_backend_identity_before_authentication(self) -> None:
        gate_source = (
            ROOT / "client" / "src" / "components" / "BackendGate.tsx"
        ).read_text(encoding="utf-8")
        app_source = (ROOT / "client" / "src" / "App.tsx").read_text(
            encoding="utf-8"
        )

        self.assertRegex(
            gate_source,
            r"""payload\.service\s*!==\s*["']wmt-backend["']""",
        )
        self.assertRegex(
            gate_source,
            r"payload\.api_version\s*!==\s*EXPECTED_API_VERSION",
        )
        self.assertIn("<BackendGate>", app_source)

    def test_authenticated_routes_share_guards_policy_and_layout(self) -> None:
        app_source = (ROOT / "client" / "src" / "App.tsx").read_text(
            encoding="utf-8"
        )
        sidebar_source = (
            ROOT / "client" / "src" / "components" / "Sidebar.tsx"
        ).read_text(encoding="utf-8")
        page_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "client" / "src" / "pages").glob("*.tsx")
        )

        self.assertIn("<AuthenticationGuard>", app_source)
        self.assertIn("<AuthenticatedLayout>", app_source)
        self.assertIn("ROUTE_POLICIES[route]", app_source)
        self.assertIn("NAVIGATION_ROUTES", sidebar_source)
        self.assertNotIn("components/Sidebar", page_sources)

    def test_authentication_surfaces_use_language_context(self) -> None:
        login_source = (
            ROOT / "client" / "src" / "pages" / "Login.tsx"
        ).read_text(encoding="utf-8")
        guard_source = (
            ROOT / "client" / "src" / "components" / "ProtectedRoute.tsx"
        ).read_text(encoding="utf-8")
        language_source = (
            ROOT / "client" / "src" / "contexts" / "LanguageContext.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("useLanguage()", login_source)
        self.assertIn("useLanguage()", guard_source)
        self.assertIn("record.addedNodes.forEach(translateNode)", language_source)
        self.assertIn("characterData: true", language_source)
        self.assertIn("attributes: true", language_source)
        self.assertIn('"placeholder", "title", "aria-label"', language_source)
        self.assertNotIn("new MutationObserver(run)", language_source)

    def test_admin_settings_are_embedded_and_collapsed_in_account(self) -> None:
        account_source = (
            ROOT / "client" / "src" / "pages" / "Account.tsx"
        ).read_text(encoding="utf-8")
        policy_source = (
            ROOT / "client" / "src" / "lib" / "routePolicy.ts"
        ).read_text(encoding="utf-8")

        self.assertIn('user.role === "admin"', account_source)
        self.assertIn("<AdminSettings embedded />", account_source)
        self.assertIn("adminSettingsOpen", account_source)
        self.assertRegex(
            policy_source,
            r'"admin-settings":\s*\{[\s\S]*?navigation:\s*false',
        )

    def test_custom_backup_destination_uses_folder_picker(self) -> None:
        backup_source = (
            ROOT / "client" / "src" / "pages" / "Backup.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("const selectedPath = await openDialog({", backup_source)
        self.assertIn("directory: true", backup_source)
        self.assertIn("setDestinationDrive(", backup_source)
        self.assertIn("setDestinationFolder(", backup_source)
        self.assertIn("Selecionar pasta", backup_source)

    def test_dashboard_search_dropdown_is_not_clipped_by_header(self) -> None:
        dashboard_source = (
            ROOT / "client" / "src" / "pages" / "Dashboard.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("relative z-30 overflow-visible", dashboard_source)
        self.assertIn("overflow-hidden rounded-[inherit]", dashboard_source)

    def test_dashboard_failure_review_opens_contextual_failure_list(self) -> None:
        dashboard_source = (
            ROOT / "client" / "src" / "pages" / "Dashboard.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("const reviewFailures = () =>", dashboard_source)
        self.assertIn('getElementById("dashboard-attention")', dashboard_source)
        self.assertIn('id="dashboard-attention"', dashboard_source)
        self.assertIn("onClick={reviewFailures}", dashboard_source)
        self.assertIn('title="Excluir falha da lista"', dashboard_source)
        self.assertIn(
            "onClick={() => dismissAttentionItem(item.id)}", dashboard_source
        )
        self.assertIn("id: `backup-${job.id}`", dashboard_source)
        self.assertIn("id: `remote-${job.id}`", dashboard_source)
        self.assertIn("id: `update-${job.id}`", dashboard_source)
        self.assertRegex(
            dashboard_source,
            r'id="dashboard-attention"[\s\S]{0,500}?title="Precisa de atenção"',
        )
        review_handler = dashboard_source.split(
            "const reviewFailures = () =>", 1
        )[1].split("const attentionItems", 1)[0]
        self.assertNotIn("setDismissedAttentionIds", review_handler)
        self.assertNotIn("localStorage.removeItem", review_handler)
        self.assertNotIn(
            'onClick={() => navigate("/history")}>\n'
            "                    <AlertTriangle size={15} /> Revisar falhas",
            dashboard_source,
        )

    def test_versioned_runtime_configuration_has_no_internal_machine_name(self) -> None:
        runtime_files = [
            ROOT / ".env.production",
            ROOT / "start_backend.ps1",
            ROOT / "src-tauri" / "tauri.conf.json",
            ROOT / "backend" / "data" / "updates" / "latest.json",
            ROOT / "backend" / "data" / "updates" / "latest-debug.json",
        ]
        combined = "\n".join(
            path.read_text(encoding="utf-8-sig") for path in runtime_files
        )

        self.assertNotIn("WKS" + "048-", combined)
        self.assertNotRegex(combined, r"C:\\Users\\[^\\]+\\")

    def test_release_script_defaults_to_central_and_supports_sidecar(self) -> None:
        release_script = (
            ROOT / "scripts" / "build-and-release.ps1"
        ).read_text(encoding="utf-8-sig")
        sidecar_script = (
            ROOT / "scripts" / "build-backend-sidecar.ps1"
        ).read_text(encoding="utf-8-sig")

        self.assertIn('[string]$BackendMode = "central"', release_script)
        self.assertIn('"binaries/wmt-backend"', release_script)
        self.assertIn('"--onefile"', sidecar_script)
        self.assertIn("wmt-backend-$TargetTriple.exe", sidecar_script)


if __name__ == "__main__":
    unittest.main()
