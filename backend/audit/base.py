"""Generic audit-module base + registry.

The verification-trail machinery (dataclasses, persistence, backup, the
API shape) is domain-agnostic. Only the *checks* differ per domain. An
``AuditModule`` packages one domain's checks behind a uniform interface so:

  * the persistence layer, run-ledger and endpoints stay generic, and
  * a new domain (e.g. inventory mismatch) is added by writing one module
    and registering it — no storage/UI/endpoint changes.

Phase 1 registers a single module (``zero_commission``). The pattern is
proven against that one real domain before a second is added.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from backend.audit.trail import VerificationTrail

# A builder takes (mon_period, payment_source) and returns the trails for
# every flagged subject in that period.
TrailBuilder = Callable[[str, str], list[VerificationTrail]]


@dataclass(frozen=True)
class AuditModule:
    """One audit domain's registration.

    Attributes:
        name:        stable machine key, e.g. ``"zero_commission"``. Stored on
                     every trail row (``module`` column) — do not rename
                     without a migration.
        label:       human label for the UI dropdown, e.g. ``"Zero-Commission"``.
        claim:       one-line description of the claim this module audits,
                     shown in the UI so a reviewer knows what they're looking at.
        step_names:  ordered step keys the module emits, for UI/reference.
        build:       callable(mon_period, payment_source) -> list[trail].
    """

    name: str
    label: str
    claim: str
    step_names: list[str]
    build: TrailBuilder = field(compare=False)

    def build_trails(self, mon_period: str, payment_source: str) -> list[VerificationTrail]:
        return self.build(mon_period, payment_source)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "claim": self.claim,
            "step_names": self.step_names,
        }


# ── Registry ─────────────────────────────────────────────────────────────
_REGISTRY: dict[str, AuditModule] = {}


def register(module: AuditModule) -> AuditModule:
    """Register an audit module. Idempotent by name (last wins)."""
    _REGISTRY[module.name] = module
    return module


def get_module(name: str) -> AuditModule | None:
    _ensure_loaded()
    return _REGISTRY.get(name)


def list_modules() -> list[AuditModule]:
    _ensure_loaded()
    return list(_REGISTRY.values())


_loaded = False


def _ensure_loaded() -> None:
    """Import the concrete modules so they self-register. Deferred to avoid
    a circular import (modules import trail primitives from this package)."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    # Importing the module runs its register(...) call at module scope.
    from backend.audit import zero_commission_audit  # noqa: F401
    from backend.audit import inventory_mismatch_audit  # noqa: F401
    from backend.audit import payment_reconciliation_audit  # noqa: F401
    from backend.audit import eligibility_window_audit  # noqa: F401
