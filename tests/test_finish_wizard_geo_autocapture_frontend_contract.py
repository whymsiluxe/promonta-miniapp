"""Worker UX V2, Этап 8 — Finish Wizard geo auto-capture (AUTO-CAPTURE PRINCIPLE).

Removes the standalone blocking "Геолокация" step: geolocation is something
the system can get on its own, so it starts capturing in the background as
soon as the wizard opens (parallel to photo/summary), and its status is
folded into the existing Сводка/review screen instead of a dedicated screen
between "Готовность на завтра" and "Сводка".

Same source-assertion style as the rest of this repo's *_frontend_contract.py
suite.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINISH_WIZARD = ROOT / "frontend" / "js" / "finish-wizard.js"


def _source() -> str:
    return FINISH_WIZARD.read_text(encoding="utf-8")


def test_geo_is_no_longer_a_standalone_step_in_the_sequence():
    src = _source()
    start = src.index("function _fwStepSequence(")
    end = src.index("\n}\n", start)
    body = src[start:end]

    assert "'geo'" not in body
    # Этап 8 remainder (same session, later commit): summary+plan-fact and
    # extra+needs+tomorrow-prep were also merged, so both branches converge
    # on the same 4-screen sequence regardless of whether a DailyPlan exists.
    assert "['photo', 'summary', 'extra', 'review']" in body


def test_no_dangling_step5_render_or_wire_functions_remain():
    src = _source()
    assert "function _fwRenderStep5(" not in src
    assert "function _fwWireStep5(" not in src
    assert "_fwRenderStep5()" not in src
    assert "_fwWireStep5()" not in src


def test_geo_capture_starts_in_background_on_wizard_open():
    src = _source()
    start = src.index("function openFinishShiftWizard(")
    end = src.index("\n}\n", start)
    body = src[start:end]
    assert "_fwStartBackgroundGeoCapture(sessionId);" in body

    fn_start = src.index("function _fwStartBackgroundGeoCapture(")
    fn_end = src.index("\n}\n", fn_start)
    fn_body = src[fn_start:fn_end]
    assert "_getGeolocation().then(" in fn_body
    # Re-renders the review screen once geo resolves, but only if the worker
    # is already looking at it -- must not yank them to a different step.
    assert "if (_fwCurrentKey() === 'review') _fwRenderStep();" in fn_body


def test_geo_capture_is_a_single_in_flight_promise_with_explicit_state():
    """Owner review finding: retry tapped while the background capture is
    still pending must NOT start a second parallel getCurrentPosition() --
    both callers (wizard-open and the review retry button) must await the
    SAME promise, and the UI must be able to distinguish "still loading"
    from "failed", not just null vs truthy _fwFinishGeo."""
    src = _source()

    assert "let _fwGeoState = 'loading'; // loading | success | error" in src
    assert "let _fwGeoCapturePromise = null;" in src

    fn_start = src.index("function _fwStartBackgroundGeoCapture(")
    fn_end = src.index("\n}\n", fn_start)
    fn_body = src[fn_start:fn_end]

    # Guard: an existing in-flight promise is returned as-is, not replaced
    assert "if (_fwGeoCapturePromise) return _fwGeoCapturePromise;" in fn_body
    assert "_fwGeoState = 'loading';" in fn_body
    assert "_fwGeoState = 'success';" in fn_body
    assert "_fwGeoState = 'error';" in fn_body
    assert "_fwGeoCapturePromise = null;" in fn_body  # cleared on resolve, allows a real retry after failure


def test_geo_capture_has_stale_session_guard_matching_finish_context_pattern():
    """Owner review finding: a late geo response must not attach coordinates
    to a wizard session that has since closed/reopened for a different
    shift -- same pattern already used by _fwLoadFinishContext."""
    src = _source()
    fn_start = src.index("function _fwStartBackgroundGeoCapture(")
    fn_end = src.index("\n}\n", fn_start)
    fn_body = src[fn_start:fn_end]
    assert "if (_fwSessionId !== sessionId) return;" in fn_body


def test_review_screen_distinguishes_loading_success_and_error_states():
    src = _source()
    start = src.index("function _fwRenderStep6(")
    end = src.index("\n}\n", start)
    body = src[start:end]

    assert "fw-geo-summary-row" in body
    assert "_fwGeoState === 'success'" in body
    assert "_fwGeoState === 'loading'" in body
    assert "определена" in body
    assert "определяем" in body
    assert "fw-geo-retry-btn" in body

    wire_start = src.index("function _fwWireStep6(")
    wire_end = src.index("\n}\n", wire_start)
    wire_body = src[wire_start:wire_end]
    # Retry reuses the same single-entry-point function with the real
    # session id, not a bare no-arg call that would defeat the stale-guard.
    assert "_fwStartBackgroundGeoCapture(_fwSessionId)" in wire_body


def test_submit_guard_awaits_existing_in_flight_capture_before_blocking():
    src = _source()
    start = src.index("async function _fwSubmitFinish(")
    end = src.index("\n  btn.disabled = true;", start)
    body = src[start:end]

    assert "await _fwStartBackgroundGeoCapture(_fwSessionId);" in body
    # No longer navigates to a 'geo' step index that no longer exists
    assert "_fwStepSequence().indexOf('geo')" not in body
