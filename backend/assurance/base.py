"""Base contract for the Assurance Layer.

The Assurance Layer sits between the intelligence modules (Commission,
Activation, and eventually Inventory, Payment, Trade Partner) and the
Finance Agent / API. Each assurance service translates raw intelligence
output into a uniform :class:`AssuranceResult` shape so downstream consumers
don't need module-specific logic.

This is scaffolding only — concrete fraud detection, inventory assurance,
and payment assurance logic lives in Phases 3, 4, and 5 respectively.

Status vocabulary:
    * ``PASS``            — no findings; the module's checks all cleared
    * ``FLAG``            — findings present, manual review recommended
    * ``FAIL``            — reserved for future use when severity thresholds
                            warrant a hard fail (not used by Phase 2 services)
    * ``NOT_IMPLEMENTED`` — service stub registered but logic deferred
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AssuranceResult:
    """Result of one assurance run, for one (module, period) and optional dealer.

    Attributes:
        module:    Human-readable module name (e.g. ``"Activation Assurance"``).
        status:    One of ``"PASS"``, ``"FLAG"``, ``"FAIL"``, ``"NOT_IMPLEMENTED"``.
        findings:  Zero or more finding dicts. Each finding carries:
                       * ``type``               — short label / category
                       * ``severity``           — ``"HIGH" | "MEDIUM" | "LOW"``
                       * ``dealer_id``          — distributor code
                       * ``dealer_name``
                       * ``description``        — one-line summary
                       * ``recommended_action`` — what Finance should do next
        summary:   One-line human summary suitable for the agent / UI.
        metadata:  Free-form key/value bag (counts, period echo, etc.).
    """

    module: str
    status: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAssuranceService(ABC):
    """Abstract base. Concrete services implement :meth:`run` and declare
    :attr:`module_name` and :attr:`phase` as class attributes."""

    @property
    @abstractmethod
    def module_name(self) -> str:
        """Human-readable module name."""

    @property
    @abstractmethod
    def phase(self) -> int:
        """The build-phase this service was introduced in (or is planned for)."""

    @abstractmethod
    async def run(
        self,
        mon_period: str,
        dealer_id: str | None = None,
    ) -> AssuranceResult:
        """Execute the service's checks for ``mon_period`` (optionally narrowed
        to a single ``dealer_id``) and return an :class:`AssuranceResult`."""

    def not_implemented(self) -> AssuranceResult:
        """Standard stub response for services whose logic isn't built yet."""
        return AssuranceResult(
            module=self.module_name,
            status="NOT_IMPLEMENTED",
            findings=[],
            summary=(
                f"{self.module_name} is not yet implemented. "
                f"Planned for Phase {self.phase}."
            ),
            metadata={},
        )
