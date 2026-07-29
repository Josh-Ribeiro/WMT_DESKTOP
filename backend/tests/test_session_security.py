from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.app.api import auth as auth_routes
from backend.app.core.security import password_hash
from backend.app.main import app
from backend.app.services import auth


def request_with_method(method: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": "/api/settings",
            "raw_path": b"/api/settings",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("wmt.example.test", 443),
        }
    )


class SessionSecurityTests(unittest.TestCase):
    def tearDown(self) -> None:
        auth.SESSIONS.clear()
        auth.LOGIN_FAILURES.clear()

    def test_session_cookie_is_http_only_secure_and_scoped(self) -> None:
        response = Response()

        with (
            patch.object(auth, "SESSION_COOKIE_SECURE", True),
            patch.object(auth, "SESSION_COOKIE_SAMESITE", "none"),
        ):
            auth.set_session_cookie(response, "opaque-session-token")

        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)
        self.assertIn("path=/api", cookie)
        self.assertIn("samesite=none", cookie)

    def test_cookie_session_requires_csrf_for_mutations(self) -> None:
        user = {
            "id": "usr-test",
            "username": "operator",
            "role": "operator",
            "status": "active",
            "auth_source": "local",
        }
        token, _expires_at, csrf_token = auth.create_session_for_user(user)

        with patch.object(auth, "state_user_by_id", return_value=user):
            current = auth.current_user(
                request_with_method("GET"),
                session_cookie=token,
                authorization=None,
                x_csrf_token=None,
            )
            self.assertEqual("operator", current["username"])

            with self.assertRaises(HTTPException) as raised:
                auth.current_user(
                    request_with_method("POST"),
                    session_cookie=token,
                    authorization=None,
                    x_csrf_token=None,
                )
            self.assertEqual(403, raised.exception.status_code)

            current = auth.current_user(
                request_with_method("POST"),
                session_cookie=token,
                authorization=None,
                x_csrf_token=csrf_token,
            )
            self.assertEqual("operator", current["username"])

    def test_bearer_authentication_is_disabled_by_default(self) -> None:
        user = {
            "id": "usr-test",
            "username": "operator",
            "role": "operator",
            "status": "active",
            "auth_source": "local",
        }
        token, _expires_at, _csrf_token = auth.create_session_for_user(user)

        with (
            patch.object(auth, "ALLOW_BEARER_AUTH", False),
            self.assertRaises(HTTPException) as raised,
        ):
            auth.current_user(
                request_with_method("GET"),
                session_cookie=None,
                authorization=f"Bearer {token}",
                x_csrf_token=None,
            )

        self.assertEqual(401, raised.exception.status_code)

    def test_fastapi_cookie_and_csrf_binding(self) -> None:
        user = {
            "id": "usr-test",
            "username": "operator",
            "role": "operator",
            "status": "active",
            "auth_source": "local",
        }
        token, _expires_at, csrf_token = auth.create_session_for_user(user)
        test_app = FastAPI()

        @test_app.get("/api/read")
        def read(current: dict = Depends(auth.current_user)) -> dict:
            return {"username": current["username"]}

        @test_app.post("/api/write")
        def write(current: dict = Depends(auth.current_user)) -> dict:
            return {"username": current["username"]}

        client = TestClient(test_app, base_url="https://testserver")
        client.cookies.set(
            auth.SESSION_COOKIE_NAME,
            token,
            path="/api",
        )
        with patch.object(auth, "state_user_by_id", return_value=user):
            self.assertEqual(200, client.get("/api/read").status_code)
            self.assertEqual(403, client.post("/api/write").status_code)
            self.assertEqual(
                200,
                client.post(
                    "/api/write",
                    headers={"X-CSRF-Token": csrf_token},
                ).status_code,
            )

    def test_login_returns_cookie_and_not_bearer_token(self) -> None:
        state = {
            "users": [
                {
                    "id": "usr-local",
                    "username": "admin",
                    "role": "admin",
                    "status": "active",
                    "password_hash": password_hash("a-secure-test-password"),
                }
            ]
        }

        def mutate(mutator):
            return mutator(state)

        with (
            patch.object(auth_routes, "mutate_state", side_effect=mutate),
            patch.object(auth_routes, "audit"),
            patch.object(auth, "SESSION_COOKIE_SECURE", True),
            patch.object(auth, "SESSION_COOKIE_SAMESITE", "none"),
        ):
            response = TestClient(
                app,
                base_url="https://testserver",
            ).post(
                "/api/auth/login",
                json={
                    "username": "admin",
                    "password": "a-secure-test-password",
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertNotIn("access_token", response.json())
        self.assertTrue(response.json()["csrf_token"])
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("secure", cookie)

    def test_repeated_invalid_logins_are_rate_limited(self) -> None:
        state = {
            "users": [
                {
                    "id": "usr-local",
                    "username": "admin",
                    "role": "admin",
                    "status": "active",
                    "password_hash": password_hash("a-secure-test-password"),
                }
            ]
        }

        def mutate(mutator):
            return mutator(state)

        with (
            patch.object(auth_routes, "mutate_state", side_effect=mutate),
            patch.object(auth, "LOGIN_RATE_LIMIT_MAX_ATTEMPTS", 2),
        ):
            client = TestClient(app, base_url="https://testserver")
            payload = {"username": "admin", "password": "invalid-password"}
            self.assertEqual(401, client.post("/api/auth/login", json=payload).status_code)
            self.assertEqual(401, client.post("/api/auth/login", json=payload).status_code)
            limited = client.post("/api/auth/login", json=payload)

        self.assertEqual(429, limited.status_code)
        self.assertIn("retry-after", limited.headers)


if __name__ == "__main__":
    unittest.main()
