"""Deny-by-default access policy, applied to every API route.

A route is internal-only unless this table says otherwise, so a new route is
never exposed to partners by accident. A test also requires each route to be
listed, keeping the decision explicit.
"""
from __future__ import annotations

from enum import Enum
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from backend import config
from backend.auth import session


class Access(Enum):
    OPEN = "open"
    SIGNED_IN = "signed_in"
    INTERNAL = "internal"


_INTERNAL_PATHS = (
    "/activations/accounts",
    "/activations/accounts/export",
    "/activations/accounts/{dealer_id}/detail",
    "/activations/exceptions",
    "/activations/summary",
    "/activations/variance",
    "/assurance/audit/breakdown",
    "/assurance/audit/modules",
    "/assurance/audit/records",
    "/assurance/audit/records/export",
    "/assurance/audit/records/{exact_subject}",
    "/assurance/audit/run",
    "/assurance/audit/trails",
    "/assurance/audit/trails/{partner_code}",
    "/assurance/overview",
    "/assurance/overview/export",
    "/assurance/status",
    "/assurance/zero-commission/breakdown",
    "/assurance/zero-commission/run",
    "/assurance/zero-commission/trails",
    "/assurance/zero-commission/trails/{partner_code}",
    "/chat",
    "/chat/explain",
    "/chat/stream",
    "/commissions",
    "/commissions/export",
    "/commissions/{dealer_id}/detail",
    "/commissions/{dealer_id}/subscription-records",
    "/commissions/{dealer_id}/zero-records",
    "/dealers",
    "/dealers/{dealer_id}/statement",
    "/dealers/{dealer_id}/verification",
    "/financial-health",
    "/financial-health/{dealer_id}",
    "/inventory/comparison",
    "/inventory/comparison-page",
    "/inventory/data-coverage-issues",
    "/partner/health",
    "/payments",
    "/payments/accounts/{dealer_id}",
    "/payments/analytics",
    "/payments/disputes/draft",
    "/payments/exceptions",
    "/payments/export",
    "/payments/position",
    "/payments/summary",
    "/payments/variance",
    "/periods",
)

ROUTE_ACCESS: dict[str, Access] = {
    "/health": Access.OPEN,
    "/auth/login": Access.OPEN,
    "/auth/logout": Access.OPEN,
    "/auth/session": Access.SIGNED_IN,
    **{path: Access.INTERNAL for path in _INTERNAL_PATHS},
}

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def access_for(path: str) -> Access:
    return ROUTE_ACCESS.get(path, Access.INTERNAL)


def _refuse_cross_site_changes(request: Request) -> None:
    """Session cookies travel automatically, so only trusted pages may change state."""
    if request.method in _SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin:
        trusted = origin in config.CORS_ORIGINS or urlsplit(origin).netloc == request.headers.get("host")
    else:
        trusted = request.headers.get("sec-fetch-site") != "cross-site"
    if not trusted:
        raise HTTPException(status_code=403, detail="Cross-site request refused.")


def current_principal(request: Request) -> session.Principal | None:
    return session.read_token(request.cookies.get(session.COOKIE_NAME))


def enforce_access(request: Request) -> None:
    """Application-wide dependency, so it runs before any route handler."""
    _refuse_cross_site_changes(request)
    level = access_for(request.scope["route"].path)
    if level is Access.OPEN:
        return
    principal = current_principal(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if level is Access.INTERNAL and principal.role != session.INTERNAL:
        raise HTTPException(status_code=403, detail="Not available for this login.")
