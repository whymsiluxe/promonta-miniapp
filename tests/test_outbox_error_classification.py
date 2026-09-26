"""Regression coverage for HTTP transient/permanent error classification in the
offline outbox (18.09, audit finding). Before this pass, appOutboxIsTransientError()
treated ANY error carrying `err.status` (i.e. any real HTTP response) as permanent --
so a transient 502/503/429 from checkin start/finish uploads went straight to
dead_letter after one failed attempt instead of being retried, because the two
upload call sites never set `err.status` on the thrown Error in the first place
(the classifier had no status to look at even when one existed).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED_JS = ROOT / "frontend" / "js" / "shared.js"
CHECKIN_JS = ROOT / "frontend" / "js" / "checkin.js"
FINISH_WIZARD_JS = ROOT / "frontend" / "js" / "finish-wizard.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_transient_classifier_distinguishes_permanent_vs_transient_status_codes():
    js = _source(SHARED_JS)
    assert "APP_OUTBOX_PERMANENT_STATUSES = new Set([400, 401, 403, 404, 409, 422]);" in js
    # Must actually consult the set, not just define it unused.
    assert "return !APP_OUTBOX_PERMANENT_STATUSES.has(err.status);" in js
    # The old behavior -- any err.status at all means permanent -- must be gone.
    assert "if (err?.status) return false;" not in js


def test_checkin_start_upload_sets_error_status_from_real_response():
    js = _source(CHECKIN_JS)
    assert "err.status = res.status;" in js
    assert "const err = new Error(detail || `HTTP ${res.status}`);" in js


def test_finish_upload_sets_error_status_from_real_response():
    js = _source(FINISH_WIZARD_JS)
    assert "err.status = res.status;" in js


def test_finish_wizard_reuses_shared_classifier_not_its_own_copy():
    # Before this pass, _fwIsTransientFinishError() was an independent copy of the
    # same heuristic -- meaning a first-attempt send and a later retry-from-outbox
    # could reach DIFFERENT verdicts for the exact same error. Now it must delegate
    # to the one shared implementation so both paths always agree.
    js = _source(FINISH_WIZARD_JS)
    assert "function _fwIsTransientFinishError(err) {\n  return appOutboxIsTransientError(err);\n}" in js
