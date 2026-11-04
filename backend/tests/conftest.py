"""Shared test setup: generated demo logins and a signed-in default client.

The application is closed by default, so ``TestClient`` starts with an internal
session and suites about other behaviour are unaffected. Tests about access
clear the cookies and sign in through the API.
"""
from __future__ import annotations

import json
import secrets

import pytest
from starlette.testclient import TestClient

from backend import config
from backend.auth import session

DEMO_LOGINS = [
    {"username": "finance", "password": secrets.token_urlsafe(16), "role": "internal"},
    {"username": "partner-296065", "password": secrets.token_urlsafe(16), "role": "partner", "account_code": "296065"},
    {"username": "partner-353072", "password": secrets.token_urlsafe(16), "role": "partner", "account_code": "353072"},
]

# Set on the loaded config, because loading it applies a developer's .env.
config.DEMO_LOGINS = json.dumps(DEMO_LOGINS)
config.DEMO_SESSION_SECRET = secrets.token_urlsafe(32)

_original_init = TestClient.__init__


def _signed_in_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self.cookies.set(session.COOKIE_NAME, session.issue_token(session.Principal("finance", "internal")))


TestClient.__init__ = _signed_in_init


@pytest.fixture
def demo_logins() -> dict[str, dict]:
    return {login["username"]: login for login in DEMO_LOGINS}
