"""Fictional dealer names for previously saved evidence in sample mode."""
from functools import lru_cache
import json
from pathlib import Path
import re


@lru_cache(maxsize=1)
def _aliases():
    path = Path(__file__).resolve().parents[2] / "data/samples/dealer_aliases.json"
    return json.loads(path.read_text())


def mask_saved_dealer_names(trail: dict) -> dict:
    """Return a demo copy, preserving codes, evidence values and stored records."""
    code = str(trail.get("partner_code", "")).split(":", 1)[0]
    if not code:
        return trail
    alias = _aliases().get(code, f"Demo Partner {code}")
    name_fields = {"partner_name", "dealer_name", "distributor_name", "customer_name"}
    replacements = {}

    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in name_fields and isinstance(item, str) and item:
                    name = item.split(" · ", 1)[0]
                    # A missing name can be represented by the account code.
                    if name != code:
                        replacements[name] = alias
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(trail)
    pattern = re.compile("|".join(re.escape(n) for n in sorted(replacements, key=len, reverse=True))) if replacements else None

    def replace(value):
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, str) and pattern:
            return pattern.sub(lambda match: replacements[match[0]], value)
        return value

    return replace(trail)
