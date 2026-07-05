"""Structured verification-trail primitives.

A ``VerificationTrail`` is the audit artifact behind a single
"Partner X was not paid commission for period Y" claim. It is a data
object — not a text explanation — so it can be:

  1. Inspected by an auditor (the ordered step chain shows exactly what
     was checked and why the conclusion was reached), and
  2. Aggregated for evaluation (each step's result is a discrete,
     queryable field, so "show me all trails where step 6 raised a
     caveat" is a cheap query).

Phase 1 covers zero-commission flagging only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _json_safe(value: Any) -> Any:
    """Coerce pandas/numpy scalars into native JSON-serializable types.

    Detail dicts are built from pandas rows, so they can carry numpy.bool_,
    numpy.int64, numpy.float64 etc. — none of which json.dumps accepts.
    Recurses through dicts/lists. Anything with a numpy-style ``.item()``
    is unwrapped to its Python scalar.
    """
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # numpy scalars (np.bool_, np.int64, np.float64) expose .item().
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    return str(value)

# Conclusion + confidence vocabularies — mirror the Postgres CHECK-style
# expectations in infra/postgres/audit_init.sql.
CONCLUSIONS = ("NOT_PAID", "PAID", "INSUFFICIENT_DATA")
CONFIDENCES = ("HIGH", "MEDIUM", "LOW")


@dataclass
class TrailStep:
    """One step in the verification chain.

    Attributes:
        step:    1-based ordinal (1..6).
        name:    stable machine key, e.g. ``"upstream_completeness"``. Used
                 in ``caveat_steps`` for aggregate queries — do not rename
                 without a migration.
        checked: human description of *what* was checked.
        result:  human-readable result of the check.
        passed:  did the check clear cleanly (no caveat)?
        caveat:  caveat text if this step raised one, else ``None``. A step
                 can be informative (``passed=True``) yet still carry a
                 caveat when the data is ambiguous.
        detail:  structured evidence (source table, counts, amounts, the
                 query description). This is what makes the step auditable.
    """

    step: int
    name: str
    checked: str
    result: str
    passed: bool
    caveat: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": int(self.step),
            "name": self.name,
            "checked": self.checked,
            "result": self.result,
            "passed": bool(self.passed),
            "caveat": self.caveat,
            "detail": _json_safe(self.detail),
        }


@dataclass
class VerificationTrail:
    """The full chain + conclusion for one (partner, period) claim."""

    partner_code: str
    partner_name: str
    mon_period: str
    payment_source: str          # "simulated" | "apdp"
    steps: list[TrailStep]
    conclusion: str              # one of CONCLUSIONS
    confidence: str              # one of CONFIDENCES
    pipeline_version: str = "1.0.0"

    # ── Derived helpers ──────────────────────────────────────────────────
    @property
    def caveat_steps(self) -> list[str]:
        """Names of steps that raised a caveat — powers aggregate queries."""
        return [s.name for s in self.steps if s.caveat]

    @property
    def caveat_count(self) -> int:
        return len(self.caveat_steps)

    def step(self, n: int) -> TrailStep | None:
        for s in self.steps:
            if s.step == n:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "partner_code": self.partner_code,
            "partner_name": self.partner_name,
            "mon_period": self.mon_period,
            "payment_source": self.payment_source,
            "pipeline_version": self.pipeline_version,
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "caveat_count": self.caveat_count,
            "caveat_steps": self.caveat_steps,
            "steps": [s.to_dict() for s in self.steps],
        }

    def __post_init__(self) -> None:
        if self.conclusion not in CONCLUSIONS:
            raise ValueError(f"invalid conclusion: {self.conclusion!r}")
        if self.confidence not in CONFIDENCES:
            raise ValueError(f"invalid confidence: {self.confidence!r}")
