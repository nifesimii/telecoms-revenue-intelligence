"""Known product-code alias groups for the FBB catalog.

Some devices are registered under multiple product codes that refer to the
same physical SKU — the canonical case from the KB is the Hynex /
Hynex_1 denomination split (see backend/knowledge_base/fbb_commission_kb.md,
"Issue 4"). These alias groups matter for two audit domains:

  * ``zero_commission`` — a zero-rate row on ``Hynex`` may be explained by a
    non-zero rate on its sibling ``Hynex_1`` (or vice versa).
  * ``inventory_mismatch`` — activation counts on one code may draw down
    purchases invoiced under a sibling code.

This module is the single source of truth for those groups. Update it +
the KB in lockstep; do not fork the mapping into per-module hardcodes.

The list is small on purpose. Add new groups only when a new alias is
confirmed by the product-master owners (not on a hunch from data noise).
"""
from __future__ import annotations

# Each tuple is a set of product codes that refer to the same physical
# SKU. Membership is order-agnostic; ``siblings_of("Hynex_1")`` returns
# ``["Hynex"]``.
_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("Hynex", "Hynex_1"),
)


def siblings_of(product_code: str) -> list[str]:
    """Return the alias siblings of ``product_code`` (excluding itself).

    Case- and whitespace-sensitive: alias groups store canonical codes as
    they appear in the product master. Returns ``[]`` if the code is not
    a member of any known alias group.
    """
    key = str(product_code)
    for group in _ALIAS_GROUPS:
        if key in group:
            return [c for c in group if c != key]
    return []


def alias_group(product_code: str) -> list[str]:
    """Return every code in the alias group containing ``product_code``.

    Convenience for callers that want to look up purchases across the
    full group in one shot (``[code] + siblings_of(code)`` avoids the
    special-case for non-aliased codes).
    """
    key = str(product_code)
    for group in _ALIAS_GROUPS:
        if key in group:
            return list(group)
    return [key]
