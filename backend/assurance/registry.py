"""Assurance service registry.

The single discovery point for available assurance modules. The agent and
API layer iterate ``ASSURANCE_REGISTRY`` to dispatch a run across every
module without hard-coding the list anywhere else.
"""
from __future__ import annotations

from backend.assurance.activation_assurance import ActivationAssuranceService
from backend.assurance.base import BaseAssuranceService
from backend.assurance.commission_assurance import CommissionAssuranceService
from backend.assurance.inventory_assurance import InventoryAssuranceService
from backend.assurance.payment_assurance import PaymentAssuranceService

# Stub services — the registry uses this to mark them as not yet built.
# Phase 3 removed InventoryAssuranceService from this list; Phase 4 removed
# PaymentAssuranceService. All four modules now have real implementations.
_STUB_SERVICES: tuple[type, ...] = ()


ASSURANCE_REGISTRY: dict[str, BaseAssuranceService] = {
    "activation": ActivationAssuranceService(),
    "commission": CommissionAssuranceService(),
    "inventory": InventoryAssuranceService(),
    "payment": PaymentAssuranceService(),
}


def is_implemented(svc: BaseAssuranceService) -> bool:
    """True iff the service has real logic (not a Phase-3+ stub)."""
    return svc.__class__ not in _STUB_SERVICES


def get_available_modules() -> list[dict]:
    """List every registered module with its phase and implementation state.

    Returns:
        ``[{"module": name, "phase": int, "implemented": bool}, ...]``
        in the order they were registered.
    """
    return [
        {
            "module": name,
            "phase": svc.phase,
            "implemented": is_implemented(svc),
        }
        for name, svc in ASSURANCE_REGISTRY.items()
    ]
