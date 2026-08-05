from __future__ import annotations

import datetime
import unittest
from unittest.mock import patch

from fastapi import HTTPException, Response
from starlette.requests import Request

from backend.app.api import auth
from backend.app.services import auth as auth_service


def request_from(client_ip: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/auth/sso",
            "raw_path": b"/api/auth/sso",
            "query_string": b"",
            "headers": [],
            "client": (client_ip, 50000),
            "server": ("127.0.0.1", 8000),
        }
    )


class SSOSecurityTests(unittest.TestCase):
    def test_forwarded_client_host_removes_ephemeral_port(self) -> None:
        self.assertEqual(
            "10.131.173.34",
            auth._forwarded_client_host("10.131.173.34:60116"),
        )
        self.assertEqual(
            "2001:db8::10",
            auth._forwarded_client_host("[2001:db8::10]:60116"),
        )

    def test_sso_without_allowed_group_fails_closed(self) -> None:
        with (
            patch.object(auth_service, "SSO_ALLOWED_GROUPS", set()),
            self.assertRaises(HTTPException) as raised,
        ):
            auth_service.sso_user_from_identity("CORP\\operator")

        self.assertEqual(503, raised.exception.status_code)

    def test_forwarded_for_cannot_turn_an_untrusted_client_into_proxy(self) -> None:
        request = request_from("10.20.30.40")
        with (
            patch.object(auth, "SSO_ENABLED", True),
            patch.object(auth, "SSO_TRUSTED_PROXY_IPS", {"127.0.0.1"}),
            self.assertRaises(HTTPException) as raised,
        ):
            auth.sso_login(
                request,
                Response(),
                x_remote_user="CORP\\attacker",
                x_windows_user=None,
                x_iis_winauth_user=None,
                x_forwarded_for="127.0.0.1",
            )

        self.assertEqual(403, raised.exception.status_code)

    def test_uvicorn_client_host_with_port_is_normalized(self) -> None:
        request = request_from("10.131.173.34:60116")
        sso_user = {
            "id": "sso-user",
            "username": "operator",
            "role": "operator",
            "status": "active",
            "auth_source": "windows",
        }
        with (
            patch.object(auth, "SSO_ENABLED", True),
            patch.object(auth, "SSO_DESKTOP_FALLBACK", False),
            patch.object(auth, "SSO_CLIENT_IP_FALLBACK", True),
            patch.object(auth, "SSO_TRUSTED_PROXY_IPS", {"127.0.0.1"}),
            patch.object(auth, "logged_user_from_host", return_value="CORP\\operator") as detected_user,
            patch.object(auth, "sso_user_from_identity", return_value=sso_user),
            patch.object(
                auth,
                "create_session_for_user",
                return_value=("token", datetime.datetime(2030, 1, 1), "csrf-token"),
            ),
            patch.object(auth, "set_session_cookie"),
            patch.object(auth, "audit"),
        ):
            auth.sso_login(
                request,
                Response(),
                x_remote_user=None,
                x_windows_user=None,
                x_iis_winauth_user=None,
                x_forwarded_for="10.131.173.34:60116",
            )

        detected_user.assert_called_once_with("10.131.173.34")

    def test_identity_header_is_accepted_from_the_configured_proxy(self) -> None:
        request = request_from("127.0.0.1")
        sso_user = {
            "id": "sso-user",
            "username": "operator",
            "role": "operator",
            "status": "active",
            "auth_source": "windows",
        }
        with (
            patch.object(auth, "SSO_ENABLED", True),
            patch.object(auth, "SSO_TRUSTED_PROXY_IPS", {"127.0.0.1"}),
            patch.object(auth, "sso_user_from_identity", return_value=sso_user),
            patch.object(
                auth,
                "create_session_for_user",
                return_value=(
                    "token",
                    datetime.datetime(2030, 1, 1),
                    "csrf-token",
                ),
            ),
            patch.object(auth, "set_session_cookie"),
            patch.object(auth, "audit"),
        ):
            response = auth.sso_login(
                request,
                Response(),
                x_remote_user="CORP\\operator",
                x_windows_user=None,
                x_iis_winauth_user=None,
                x_forwarded_for="10.20.30.50",
            )

        self.assertEqual("operator", response["user"])
        self.assertEqual("iis", response["auth_mode"])

    def test_remote_desktop_login_resolves_the_direct_client_machine(self) -> None:
        request = request_from("10.20.30.40")
        sso_user = {
            "id": "sso-user",
            "username": "operator",
            "role": "operator",
            "status": "active",
            "auth_source": "windows",
        }
        with (
            patch.object(auth, "SSO_ENABLED", True),
            patch.object(auth, "SSO_DESKTOP_FALLBACK", True),
            patch.object(auth, "SSO_CLIENT_IP_FALLBACK", True),
            patch.object(auth, "SSO_TRUSTED_PROXY_IPS", {"127.0.0.1"}),
            patch.object(
                auth,
                "logged_user_from_host",
                return_value="CORP\\operator",
            ) as detected_user,
            patch.object(auth, "sso_user_from_identity", return_value=sso_user),
            patch.object(
                auth,
                "create_session_for_user",
                return_value=(
                    "token",
                    datetime.datetime(2030, 1, 1),
                    "csrf-token",
                ),
            ),
            patch.object(auth, "set_session_cookie"),
            patch.object(auth, "audit"),
        ):
            response = auth.sso_login(
                request,
                Response(),
                x_remote_user=None,
                x_windows_user=None,
                x_iis_winauth_user=None,
                x_forwarded_for="127.0.0.1",
            )

        detected_user.assert_called_once_with("10.20.30.40")
        self.assertEqual("operator", response["user"])
        self.assertEqual("client-ip", response["auth_mode"])

    def test_proxy_login_removes_port_before_resolving_client_machine(self) -> None:
        request = request_from("127.0.0.1")
        sso_user = {
            "id": "sso-user",
            "username": "operator",
            "role": "operator",
            "status": "active",
            "auth_source": "windows",
        }
        with (
            patch.object(auth, "SSO_ENABLED", True),
            patch.object(auth, "SSO_DESKTOP_FALLBACK", False),
            patch.object(auth, "SSO_CLIENT_IP_FALLBACK", True),
            patch.object(auth, "SSO_TRUSTED_PROXY_IPS", {"127.0.0.1"}),
            patch.object(auth, "logged_user_from_host", return_value="CORP\\operator") as detected_user,
            patch.object(auth, "sso_user_from_identity", return_value=sso_user),
            patch.object(
                auth,
                "create_session_for_user",
                return_value=("token", datetime.datetime(2030, 1, 1), "csrf-token"),
            ),
            patch.object(auth, "set_session_cookie"),
            patch.object(auth, "audit"),
        ):
            response = auth.sso_login(
                request,
                Response(),
                x_remote_user=None,
                x_windows_user=None,
                x_iis_winauth_user=None,
                x_forwarded_for="10.131.173.34:60116",
            )

        detected_user.assert_called_once_with("10.131.173.34")
        self.assertEqual("client-ip", response["auth_mode"])

    def test_local_desktop_login_uses_the_backend_windows_session(self) -> None:
        request = request_from("127.0.0.1")
        sso_user = {
            "id": "sso-user",
            "username": "operator",
            "role": "operator",
            "status": "active",
            "auth_source": "windows",
        }
        with (
            patch.object(auth, "SSO_ENABLED", True),
            patch.object(auth, "SSO_DESKTOP_FALLBACK", True),
            patch.object(auth, "SSO_CLIENT_IP_FALLBACK", True),
            patch.object(auth, "current_windows_identity", return_value="CORP\\operator"),
            patch.object(auth, "sso_user_from_identity", return_value=sso_user),
            patch.object(
                auth,
                "create_session_for_user",
                return_value=(
                    "token",
                    datetime.datetime(2030, 1, 1),
                    "csrf-token",
                ),
            ),
            patch.object(auth, "set_session_cookie"),
            patch.object(auth, "audit"),
        ):
            response = auth.sso_login(
                request,
                Response(),
                x_remote_user=None,
                x_windows_user=None,
                x_iis_winauth_user=None,
                x_forwarded_for=None,
            )

        self.assertEqual("operator", response["user"])
        self.assertEqual("desktop", response["auth_mode"])

    def test_sso_debug_is_hidden_when_diagnostics_are_disabled(self) -> None:
        request = request_from("127.0.0.1")
        with (
            patch.object(auth, "SSO_DEBUG_ENABLED", False),
            self.assertRaises(HTTPException) as raised,
        ):
            auth.sso_debug(
                request,
                x_forwarded_for=None,
                user={"username": "admin", "role": "admin"},
            )

        self.assertEqual(404, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
