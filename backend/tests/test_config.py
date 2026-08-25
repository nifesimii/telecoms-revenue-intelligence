"""Configuration contract tests."""

from backend.config import _resolve_payment_source


def test_fbb_render_preview_always_matches_local_simulated_source():
    assert _resolve_payment_source("apdp", "fbb-preview") == "simulated"
    assert _resolve_payment_source("simulated", "fbb-preview") == "simulated"


def test_separate_integration_environment_can_enable_apdp():
    assert _resolve_payment_source("apdp", "fbb-apdp-integration") == "apdp"


def test_unknown_payment_source_fails_safe_to_simulated():
    assert _resolve_payment_source("unknown", "") == "simulated"
