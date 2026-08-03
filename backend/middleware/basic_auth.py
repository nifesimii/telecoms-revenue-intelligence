"""HTTP Basic Auth gate for the GM preview deploy.

Reads ``DEMO_USERNAME`` / ``DEMO_PASSWORD`` from the environment. Applies to
every request except paths in :data:`_OPEN_PATHS` (health probe + the SPA's
own asset directory, so the browser can render the login form the same way it
would render any static asset).

If either env var is missing/empty the middleware is a no-op — local dev
without the vars set behaves exactly as before.
"""
from __future__ import annotations

import base64
import os
import secrets
from typing import Callable, Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Paths that must remain reachable without credentials.
#   /health  — Render (and any load balancer) probes this to decide readiness.
_OPEN_PATHS: tuple[str, ...] = ("/health",)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Prompt for HTTP Basic Auth on every request unless whitelisted."""

    def __init__(
        self,
        app: ASGIApp,
        username: str,
        password: str,
        realm: str = "FBB Preview",
        open_paths: Iterable[str] = _OPEN_PATHS,
    ) -> None:
        super().__init__(app)
        self._username = username
        self._password = password
        self._realm = realm
        self._open_paths = tuple(open_paths)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self._open_paths:
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
                user, _, pw = decoded.partition(":")
            except Exception:
                user, pw = "", ""
            # Constant-time compares so a wrong username can't be
            # distinguished from a wrong password by response timing.
            ok_user = secrets.compare_digest(user, self._username)
            ok_pw = secrets.compare_digest(pw, self._password)
            if ok_user and ok_pw:
                return await call_next(request)

        return Response(
            status_code=401,
            content="Authentication required.",
            headers={"WWW-Authenticate": f'Basic realm="{self._realm}"'},
        )


def install_if_configured(app) -> bool:
    """Mount the gate iff both env vars are set. Returns True if installed."""
    username = os.getenv("DEMO_USERNAME", "").strip()
    password = os.getenv("DEMO_PASSWORD", "").strip()
    if not username or not password:
        return False
    app.add_middleware(
        BasicAuthMiddleware, username=username, password=password
    )
    return True
