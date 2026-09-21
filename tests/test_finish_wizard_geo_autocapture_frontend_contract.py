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
    assert "_fwStartBackgroundGeoCapture();" in body

    fn_start = src.index("async function _fwStartBackgroundGeoCapture(")
    fn_end = src.index("\n}\n", fn_start)
    fn_body = src[fn_start:fn_end]
    assert "await _getGeolocation();" in fn_body
    # Re-renders the review screen once geo resolves, but only if the worker
    # is already looking at it -- must not yank them to a different step.
    assert "if (_fwCurrentKey() === 'review') _fwRenderStep();" in fn_body


def test_review_screen_shows_geo_status_with_inline_retry_not_separate_screen():
    src = _source()
    start = src.index("function _fwRenderStep6(")
    end = src.index("\n}\n", start)
    body = src[start:end]

    assert "fw-geo-summary-row" in body
    assert "определена" in body
    assert "fw-geo-retry-btn" in body

    wire_start = src.index("function _fwWireStep6(")
    wire_end = src.index("\n}\n", wire_start)
    wire_body = src[wire_start:wire_end]
    assert "_fwStartBackgroundGeoCapture()" in wire_body


def test_submit_guard_retries_geo_once_more_before_blocking():
    src = _source()
    start = src.index("async function _fwSubmitFinish(")
    end = src.index("\n  btn.disabled = true;", start)
    body = src[start:end]

    assert "await _fwStartBackgroundGeoCapture();" in body
    # No longer navigates to a 'geo' step index that no longer exists
    assert "_fwStepSequence().indexOf('geo')" not in body
