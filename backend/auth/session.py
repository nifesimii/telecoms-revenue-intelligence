"""Demo logins and signed session tokens for the two-login presentation.

Logins come from ``DEMO_LOGINS``, a JSON list configured in the environment.
Missing or invalid configuration means nobody can sign in, never open access.
A session token is a signed, expiring statement of who the principal is, so the
role and account code cannot be changed by the client.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import asdict, dataclass

from backend import config

logger = logging.getLogger(__name__)

COOKIE_NAME = "fbb_session"
SESSION_LIFETIME_SECONDS = 8 * 60 * 60

INTERNAL = "internal"
PARTNER = "partner"


class LoginsNotConfigured(Exception):
    """Sign-in is unavailable until valid logins and a signing secret are set."""


@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    account_code: str | None = None


@dataclass(frozen=True)
class _Login:
    principal: Principal
    password: str


def _parse_login(entry: dict) -> _Login:
    username, password, role = entry["username"], entry["password"], entry["role"]
    account_code = entry.get("account_code")
    valid = (
        all(isinstance(value, str) and value for value in (username, password))
        and (
            (role == INTERNAL and account_code is None)
            or (role == PARTNER and isinstance(account_code, str) and account_code != "")
        )
    )
    if not valid:
        raise ValueError("invalid login entry")
    return _Login(Principal(username, role, account_code), password)


def _load_logins() -> dict[str, _Login]:
    if not config.DEMO_SESSION_SECRET or not config.DEMO_LOGINS:
        raise LoginsNotConfigured
    try:
        logins = [_parse_login(entry) for entry in json.loads(config.DEMO_LOGINS)]
    except (ValueError, KeyError, TypeError) as exc:
        # The value holds passwords, so log only that it could not be used.
        logger.error("DEMO_LOGINS is invalid: %s", type(exc).__name__)
        raise LoginsNotConfigured from None
    if not logins or len({login.principal.username for login in logins}) != len(logins):
        logger.error("DEMO_LOGINS must list at least one login, with unique usernames.")
        raise LoginsNotConfigured
    return {login.principal.username: login for login in logins}


def require_logins() -> None:
    """Raise LoginsNotConfigured unless at least one valid login and a signing secret are set."""
    _load_logins()


def _same(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def authenticate(username: str, password: str) -> Principal | None:
    """Return the principal for valid credentials.

    A missing user still performs a comparison, so the outcome does not reveal
    through timing whether the username or the password was wrong.
    """
    login = _load_logins().get(username)
    matches = _same(password, login.password if login else "")
    return login.principal if login and matches else None


def _sign(payload: str) -> str:
    return hmac.new(config.DEMO_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_token(principal: Principal, lifetime_seconds: int = SESSION_LIFETIME_SECONDS) -> str:
    claims = {**asdict(principal), "expires_at": time.time() + lifetime_seconds}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
    return f"{payload}.{_sign(payload)}"


def read_token(token: str | None) -> Principal | None:
    """Return the token's principal, or None if it is absent, forged or expired."""
    if not token or not config.DEMO_SESSION_SECRET:
        return None
    payload, _, signature = token.partition(".")
    if not _same(signature, _sign(payload)):
        return None
    claims = json.loads(base64.urlsafe_b64decode(payload))
    if claims["expires_at"] <= time.time():
        return None
    return Principal(claims["username"], claims["role"], claims["account_code"])
