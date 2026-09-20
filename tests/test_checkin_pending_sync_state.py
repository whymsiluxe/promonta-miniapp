"""Regression coverage for START_PENDING_SYNC/FINISH_PENDING_SYNC gating
(18.09, audit finding).

Before this pass, once Start (or Finish) was queued to the offline outbox,
the preview modal/wizard closed and NO local UI state reflected that a
submission was already in flight -- checkin.js's Start/Finish buttons kept
showing whatever the last-known server state was (usually still "Смена не
начата" for Start, since the local session is only set on a SUCCESSFUL
send). A worker could tap Start/Finish again and queue a SECOND outbox
record for the same shift with a DIFFERENT idempotency key -- the server's
dedup-by-idempotency-key can't catch that, it's a genuinely different key.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKIN_JS = ROOT / "frontend" / "js" / "checkin.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_pending_outbox_checker_covers_both_kinds_excludes_dead_letter():
    js = _source(CHECKIN_JS)
    assert "async function _findPendingCheckinOutboxRecord(objectId) {" in js
    assert "promontaOutboxList(CHECKIN_OUTBOX_KIND_START)" in js
    assert "promontaOutboxList(CHECKIN_OUTBOX_KIND_FINISH)" in js
    # A permanently-failed record must not block a fresh retry attempt forever.
    assert "r.state !== 'dead_letter'" in js


def test_refresh_checkin_buttons_checks_pending_before_server_state():
    js = _source(CHECKIN_JS)
    fn_start = js.index("async function refreshCheckinButtons() {")
    fn_end = js.index("\n}\n", js.index("_updateActiveShiftPanel(session"))
    body = js[fn_start:fn_end]

    pending_check_idx = body.index("_findPendingCheckinOutboxRecord(objectId)")
    server_check_idx = body.index("api(`/api/checkin?object_id=")
    assert pending_check_idx < server_check_idx, (
        "pending-outbox check must run BEFORE the server session lookup -- a "
        "queued-but-not-yet-sent submission means the server hasn't seen it "
        "at all, so server state alone can't be trusted to gate the buttons"
    )


def test_pending_start_disables_both_buttons_with_sync_label():
    js = _source(CHECKIN_JS)
    assert "startBtn.textContent = '⏳ Начало смены ожидает синхронизации';" in js


def test_pending_finish_shows_sync_label():
    js = _source(CHECKIN_JS)
    assert "finishBtn.textContent = '⏳ Завершение смены ожидает синхронизации';" in js


def test_finish_button_label_restored_when_no_longer_pending():
    # A pending Finish sets a "⏳ ..." label on the button -- once the pending
    # record clears (sent successfully, or the session becomes active again
    # through the normal path), the button must go back to its real label,
    # not stay stuck on the sync-pending text forever.
    js = _source(CHECKIN_JS)
    assert "finishBtn.textContent = '■ Финиш смены';" in js
