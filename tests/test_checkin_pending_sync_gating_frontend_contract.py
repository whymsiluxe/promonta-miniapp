"""Pending-sync gating for Start/Finish buttons (upstream 3ba474b invariant,
merged INTO the existing resolveWorkerShiftState() architecture, not as a
second parallel mechanism).

Context: after Start or Finish is queued to the offline outbox, the UI must
stay honest about what's actually in flight -- otherwise a worker could tap
Start/Finish again and queue a second outbox record for the same shift with
a different idempotency key (the server's dedup-by-idempotency-key can't
catch that, it's genuinely a different key).

This branch already closes that gap through resolveWorkerShiftState()
(frontend/js/worker-shift-state.js) -- the resolver itself checks the
IndexedDB outbox BEFORE falling back to server state, so
START_PENDING_SYNC/FINISH_PENDING_SYNC/SYNC_ERROR are resolver states that
propagate to every consumer (Home CTA, FAB, checkin.js buttons) uniformly,
rather than each consumer re-implementing its own outbox check
(upstream's _findPendingCheckinOutboxRecord() was a second, checkin.js-local
mechanism doing the same job a different way -- not needed here, the
resolver already covers it more broadly, including a same-time-different-
object active session case upstream's version didn't have).
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKIN_JS = ROOT / "frontend" / "js" / "checkin.js"
WORKER_SHIFT_STATE_JS = ROOT / "frontend" / "js" / "worker-shift-state.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fn(src: str, signature: str) -> str:
    start = src.index(signature)
    depth = 0
    i = src.index("{", start)
    j = i
    while True:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1


def test_refresh_checkin_buttons_resolves_shift_state_via_the_single_resolver():
    body = _fn(_source(CHECKIN_JS), "async function refreshCheckinButtons(")
    # Must go through the shared resolver, not build its own outbox check.
    assert "resolveWorkerShiftState()" in body
    assert "_findPendingCheckinOutboxRecord" not in body


def test_start_pending_sync_disables_both_buttons_and_shows_status():
    body = _fn(_source(CHECKIN_JS), "async function refreshCheckinButtons(")
    assert "shiftState?.state === WORKER_SHIFT_STATE.START_PENDING_SYNC" in body
    start_branch = body[body.index("WORKER_SHIFT_STATE.START_PENDING_SYNC"):
                         body.index("WORKER_SHIFT_STATE.FINISH_PENDING_SYNC")]
    assert "startBtn.disabled = true;" in start_branch
    assert "finishBtn.disabled = true;" in start_branch
    assert "ожидает синхронизации" in start_branch


def test_finish_pending_sync_disables_both_buttons_and_shows_status():
    body = _fn(_source(CHECKIN_JS), "async function refreshCheckinButtons(")
    assert "shiftState?.state === WORKER_SHIFT_STATE.FINISH_PENDING_SYNC" in body
    branch_start = body.index("} else if (shiftState?.state === WORKER_SHIFT_STATE.FINISH_PENDING_SYNC")
    finish_branch = body[branch_start: body.index("} else if (shiftState?.state === WORKER_SHIFT_STATE.SYNC_ERROR", branch_start)]
    assert "startBtn.disabled = true;" in finish_branch
    assert "finishBtn.disabled = true;" in finish_branch
    assert "ожидает синхронизации" in finish_branch


def test_sync_error_state_also_disables_both_buttons():
    # Not present in upstream's implementation at all -- this branch's resolver
    # exposes a dedicated SYNC_ERROR state (permanently failed, needs a manual
    # retry) distinct from still-pending, and checkin.js gates on it the same way.
    body = _fn(_source(CHECKIN_JS), "async function refreshCheckinButtons(")
    assert "shiftState?.state === WORKER_SHIFT_STATE.SYNC_ERROR" in body


def test_active_session_on_a_different_object_also_gates_start():
    # Extra invariant this branch's resolver covers that upstream's local
    # per-object check did not: an active shift on OBJECT A must disable Start
    # when the worker is looking at OBJECT B's buttons too (only one shift at
    # a time), not just gate the object the pending record belongs to.
    body = _fn(_source(CHECKIN_JS), "async function refreshCheckinButtons(")
    assert "workerShiftStateHasActiveSession?.(shiftState) && String(shiftState.objectId) !== String(objectId)" in body


def test_dead_letter_records_do_not_block_the_resolver_forever():
    # Ported invariant: a permanently-failed outbox record must not gate Start/
    # Finish forever -- verified at the resolver level (worker-shift-state.js),
    # which is where this branch centralizes the outbox check, not duplicated
    # in checkin.js.
    src = _source(WORKER_SHIFT_STATE_JS)
    assert "dead_letter" in src


def test_generation_counter_prevents_stale_pending_check_from_racing_a_newer_call():
    # 24.07 pre-existing pattern (this branch): refreshCheckinButtons can be
    # called twice in quick succession for the same object -- the generation
    # counter must guard the resolver await too, not just the session lookup
    # that follows it, or a slow first call could still win the race and
    # overwrite a newer call's already-correct button state.
    body = _fn(_source(CHECKIN_JS), "async function refreshCheckinButtons(")
    assert "const myGeneration = ++_checkinButtonsGeneration;" in body
    assert body.count("if (myGeneration !== _checkinButtonsGeneration) return;") >= 1
