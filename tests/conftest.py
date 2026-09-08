"""Pytest conftest — import-time test isolation guard.

This module-level code runs BEFORE any test module is imported by pytest, so
MINIAPP_DATA_ROOT is set in the environment before any `import main as backend`
runs anywhere in the test suite. This ensures main.py's module-level DATA_ROOT
constant is never '/home/promonta/agent/miniapp' during any test run.

This is the PRIMARY safety mechanism. Per-test setUpClass env changes are
secondary / belt-and-suspenders (they cannot change DATA_ROOT once main is
imported, but they document intent and protect standalone test runs).
"""
import os
import tempfile

import pytest

# ── PRIMARY GUARD: set env at module level, before any test module is imported ──
_TEST_DATA_ROOT = tempfile.mkdtemp(prefix="promonta-pytest-")
os.environ["MINIAPP_DATA_ROOT"] = _TEST_DATA_ROOT
os.environ["PROMONTA_ENV"] = "test"
os.environ.setdefault("BOT_TOKEN", "ci-dummy-token-not-a-real-secret")


# ── DEFENSE-IN-DEPTH: session-scoped assertion that DATA_ROOT was not production ──
@pytest.fixture(autouse=True, scope="session")
def _verify_test_isolation():
    import main as backend
    assert backend.DATA_ROOT != "/home/promonta/agent/miniapp", (
        f"DATA_ROOT resolved to production path: {backend.DATA_ROOT}"
    )
    assert "promonta-pytest-" in backend.DATA_ROOT or "promonta-test-" in backend.DATA_ROOT, (
        f"DATA_ROOT does not look like a pytest temp dir: {backend.DATA_ROOT}"
    )
    yield
