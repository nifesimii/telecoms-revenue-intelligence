"""Login, sessions and deny-by-default access through the public HTTP API."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.auth import access, session
from backend.main import app


def anonymous() -> TestClient:
    client = TestClient(app)
    client.cookies.clear()
    return client


def signed_in(login: dict) -> TestClient:
    client = anonymous()
    response = client.post("/auth/login", json={"username": login["username"], "password": login["password"]})
    assert response.status_code == 200
    return client


def api_operations() -> list[tuple[str, str]]:
    return [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    ]


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


INTERNAL_OPERATIONS = [
    (method, path) for method, path in api_operations()
    if access.ROUTE_ACCESS.get(path) is access.Access.INTERNAL
]


def test_every_route_has_an_access_classification():
    assert {path for _, path in api_operations()} - set(access.ROUTE_ACCESS) == set()


def test_only_the_expected_routes_are_open():
    open_paths = {path for path, level in access.ROUTE_ACCESS.items() if level is access.Access.OPEN}
    assert open_paths == {"/health", "/auth/login", "/auth/logout"}


@pytest.mark.parametrize("method,path", INTERNAL_OPERATIONS)
def test_internal_routes_refuse_requests_without_a_session(method, path):
    assert anonymous().request(method, concrete(path)).status_code == 401


@pytest.mark.parametrize("method,path", INTERNAL_OPERATIONS)
def test_internal_routes_refuse_partners(method, path, demo_logins):
    assert signed_in(demo_logins["partner-296065"]).request(method, concrete(path)).status_code == 403


def test_unclassified_routes_are_internal_only():
    assert access.access_for("/some/new/route") is access.Access.INTERNAL


def test_api_documentation_is_not_exposed():
    client = anonymous()
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code != 200


def test_readiness_probe_stays_open():
    assert anonymous().get("/health").status_code == 200


def test_internal_login_reaches_internal_routes(demo_logins):
    client = signed_in(demo_logins["finance"])
    assert client.get("/auth/session").json() == {"username": "finance", "role": "internal", "account_code": None}
    assert client.get("/periods").status_code == 200


def test_partner_login_is_tied_to_its_exact_account(demo_logins):
    first = signed_in(demo_logins["partner-296065"]).get("/auth/session").json()
    second = signed_in(demo_logins["partner-353072"]).get("/auth/session").json()
    assert (first["role"], first["account_code"]) == ("partner", "296065")
    assert (second["role"], second["account_code"]) == ("partner", "353072")


def test_failed_login_does_not_reveal_which_field_was_wrong(demo_logins):
    client = anonymous()
    wrong_password = client.post("/auth/login", json={"username": "finance", "password": "wrong"})
    unknown_user = client.post("/auth/login", json={"username": "nobody", "password": demo_logins["finance"]["password"]})
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert session.COOKIE_NAME not in client.cookies


def test_session_cookie_cannot_be_read_by_scripts(demo_logins):
    login = demo_logins["finance"]
    response = anonymous().post("/auth/login", json={"username": login["username"], "password": login["password"]})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_session_cookie_is_secure_on_hosted_deployments(demo_logins, monkeypatch):
    monkeypatch.setattr(config, "HOSTED_DEPLOYMENT", True)
    login = demo_logins["finance"]
    response = anonymous().post("/auth/login", json={"username": login["username"], "password": login["password"]})
    assert "secure" in response.headers["set-cookie"].lower()


def test_session_survives_new_requests_until_sign_out(demo_logins):
    client = signed_in(demo_logins["finance"])
    assert client.get("/auth/session").status_code == 200
    assert client.get("/auth/session").status_code == 200
    assert client.post("/auth/logout").status_code == 204
    assert session.COOKIE_NAME not in client.cookies
    assert client.get("/auth/session").status_code == 401


def test_tampered_session_is_refused(demo_logins):
    client = signed_in(demo_logins["partner-296065"])
    payload, signature = client.cookies[session.COOKIE_NAME].split(".")
    forged = session.issue_token(session.Principal("finance", "internal")).split(".")[0]
    client.cookies.clear()
    client.cookies.set(session.COOKIE_NAME, f"{forged}.{signature}")
    assert client.get("/auth/session").status_code == 401
    client.cookies.clear()
    client.cookies.set(session.COOKIE_NAME, payload)
    assert client.get("/auth/session").status_code == 401


def test_expired_session_is_refused():
    client = anonymous()
    client.cookies.set(session.COOKIE_NAME, session.issue_token(session.Principal("finance", "internal"), lifetime_seconds=-1))
    assert client.get("/auth/session").status_code == 401


def test_session_signed_with_another_secret_is_refused(monkeypatch):
    token = session.issue_token(session.Principal("finance", "internal"))
    monkeypatch.setattr(config, "DEMO_SESSION_SECRET", "a-different-secret")
    client = anonymous()
    client.cookies.set(session.COOKIE_NAME, token)
    assert client.get("/auth/session").status_code == 401


@pytest.mark.parametrize("logins,secret", [("", "secret"), ("not json", "secret"), ('[{"username": "x"}]', "secret"), ('[]', "secret")])
def test_invalid_login_configuration_keeps_the_application_closed(monkeypatch, logins, secret):
    monkeypatch.setattr(config, "DEMO_LOGINS", logins)
    monkeypatch.setattr(config, "DEMO_SESSION_SECRET", secret)
    client = anonymous()
    assert client.post("/auth/login", json={"username": "x", "password": "x"}).status_code == 503
    assert client.get("/periods").status_code == 401


def test_missing_secret_keeps_the_application_closed(monkeypatch, demo_logins):
    login = demo_logins["finance"]
    monkeypatch.setattr(config, "DEMO_SESSION_SECRET", "")
    client = anonymous()
    assert client.post("/auth/login", json={"username": login["username"], "password": login["password"]}).status_code == 503
    assert client.get("/periods").status_code == 401


def test_partner_login_without_an_account_is_invalid_configuration(monkeypatch):
    monkeypatch.setattr(config, "DEMO_LOGINS", '[{"username": "p", "password": "x", "role": "partner"}]')
    assert anonymous().post("/auth/login", json={"username": "p", "password": "x"}).status_code == 503


def test_cross_site_state_changes_are_refused(demo_logins):
    client = signed_in(demo_logins["finance"])
    payload = {"question": "x"}
    assert client.post("/chat", json=payload, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/chat", json=payload, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/auth/login", json={"username": "x", "password": "x"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/auth/session").status_code == 200


def test_state_changes_from_allowed_and_same_origins_pass_the_origin_check(demo_logins, monkeypatch):
    monkeypatch.setattr(config, "CORS_ORIGINS", ["http://localhost:5173"])
    client = anonymous()
    for origin in ("http://localhost:5173", "http://testserver"):
        response = client.post("/auth/login", json={"username": "x", "password": "x"}, headers={"Origin": origin})
        assert response.status_code == 401


def test_cross_site_reads_with_a_session_are_not_granted_cors(demo_logins):
    client = signed_in(demo_logins["finance"])
    response = client.get("/auth/session", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers
