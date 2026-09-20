"""Regression coverage for finish-wizard.js reading the frozen accepted plan
snapshot instead of the live current plan (18.09, audit finding).

Before this pass, openFinishShiftWizard() read window._todayPlanState -- the
LIVE current DailyPlan -- for the item checklist shown/submitted at Finish. If
the owner amended the plan after this worker started their shift, Finish
would show the amended item list, not what this worker actually accepted and
started against. checkin_finish() itself already validated submissions
against the immutable accepted_context_snapshot (Round 1.2 #2) -- this closed
the matching gap on the read/display side via GET
/api/checkin/{session_id}/finish-context (see test_checkin_finish_context.py
for the backend-side coverage).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINISH_WIZARD_JS = ROOT / "frontend" / "js" / "finish-wizard.js"
CHECKIN_JS = ROOT / "frontend" / "js" / "checkin.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_finish_wizard_no_longer_reads_live_today_plan_state():
    js = _source(FINISH_WIZARD_JS)
    # window._todayPlanState is still legitimately WRITTEN (set to null) in
    # _fwMarkFinishConfirmed() -- that's the today-plan-bar UI resetting after
    # a successful finish, unrelated to this bug. What must be gone is READING
    # it to populate the wizard's own item checklist.
    assert "const planState = window._todayPlanState;" not in js
    assert "_fwDailyPlanItems = planState.plan.items;" not in js


def test_finish_wizard_fetches_frozen_finish_context():
    js = _source(FINISH_WIZARD_JS)
    assert "async function openFinishShiftWizard(sessionId, objectId) {" in js
    assert "await api(`/api/checkin/${sessionId}/finish-context`);" in js
    assert "_fwDailyPlanItems = ctx.items;" in js
    # Modal opens and renders immediately with an empty item list -- must not
    # block the modal itself on the network round-trip, only the checklist.
    assert "_fwRenderStep(); // render immediately with an empty item list" in js
    # Stale-response guard: wizard could be closed/reopened for a different
    # session while the request was in flight.
    assert "if (_fwSessionId !== sessionId) return;" in js


def test_checkin_finish_button_awaits_wizard_open():
    js = _source(CHECKIN_JS)
    assert "addEventListener('click', async () => {" in js
    assert "await openFinishShiftWizard(session.id, _stagesCurrentObjectId);" in js
