"""Regression coverage for a P0 found across two rounds of owner review of the
fix-shift-start / origin/main merge: resolveWorkerShiftState() used to check
dead_letter outbox records BEFORE ever asking the server (round 1), and then
-- even after that fix -- still checked dead_letter before a valid LOCAL
active session when the server itself was unreachable (round 3).

Concretely (round 1): a worker whose Finish permanently failed to sync
yesterday (now sitting as a dead_letter record for OBJECT-A) would see "⚠️
Ошибка синхронизации" and have Start/Finish disabled TODAY on OBJECT-B, even
though the server has a perfectly normal ACTIVE session open for them right
now -- the resolver never got that far, because the stale dead_letter from an
unrelated, already-finished shift short-circuited the whole function first.

Concretely (round 3): the same bug class survived in the OFFLINE branch --
when the server call itself throws (no connectivity), the resolver fell
straight to dead_letter, before ever checking whether localStorage already
has a valid ACTIVE/PAUSED session for a DIFFERENT, unrelated object. A worker
genuinely mid-shift on OBJECT-B, with an old dead_letter from OBJECT-A's
already-finished Finish still in the outbox, would see the same false
SYNC_ERROR the moment connectivity dropped.

Final precedence: live pending outbox -> server (if reachable) -> [server
unreachable: local ACTIVE/PAUSED first (dead_letter surfaced only as a
non-blocking syncWarning alongside it), otherwise dead_letter as a real
block] -> localStorage fallback for whatever's left. See the runtime test
(node-worker-shift-state-dead-letter-offline.js) for the actual state-machine
behavior across concrete scenarios -- this file covers the structural
placement in source.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER_SHIFT_STATE_JS = ROOT / "frontend" / "js" / "worker-shift-state.js"


def _source() -> str:
    return WORKER_SHIFT_STATE_JS.read_text(encoding="utf-8")


def _fn(src: str, signature: str) -> str:
    start = src.index(signature)
    depth = 0
    # Search for the body's opening brace AFTER the signature text ends --
    # resolveWorkerShiftState's own signature contains a literal "{}" (the
    # options = {} default parameter), which would otherwise be mistaken for
    # the function body's opening brace and produce a truncated body.
    i = src.index("{", start + len(signature))
    j = i
    while True:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1


def test_pending_outbox_resolver_no_longer_checks_dead_letter():
    body = _fn(_source(), "async function _resolveWorkerShiftOutboxState(objectId)")
    assert "dead_letter" not in body, (
        "_resolveWorkerShiftOutboxState must only resolve LIVE pending "
        "records now -- dead_letter handling moved to "
        "_findDeadLetterShiftRecord(), consulted separately after the server."
    )


def test_dead_letter_lookup_is_a_separate_function():
    src = _source()
    assert "async function _findDeadLetterShiftRecord(objectId)" in src
    body = _fn(src, "async function _findDeadLetterShiftRecord(objectId)")
    assert "dead_letter" in body
    assert "WORKER_SHIFT_STATE.SYNC_ERROR" in body


def test_resolver_checks_pending_then_server_before_any_dead_letter_lookup():
    body = _fn(_source(), "async function resolveWorkerShiftState(options = {})")
    pending_idx = body.index("_resolveWorkerShiftOutboxState(objectId)")
    server_idx = body.index("await api(path)")
    first_dead_letter_idx = body.index("_findDeadLetterShiftRecord(objectId)")

    assert pending_idx < server_idx < first_dead_letter_idx, (
        "Precedence must start: live pending outbox -> server. A stale "
        "dead_letter from an unrelated shift must never be checked before "
        "the server gets a chance to report the CURRENT real state."
    )


def test_dead_letter_is_checked_in_both_the_offline_and_online_branches():
    # 21.09 round 3: dead_letter is now consulted in TWO places -- once inside
    # the offline branch (server unreachable), gated behind a local-active-
    # session check first, and once in the online/fallback branch (server
    # reachable but reported no session, or the offline branch found no
    # local active session to protect). Both must exist; a single lookup
    # would mean one of the two branches regressed back to skipping it.
    body = _fn(_source(), "async function resolveWorkerShiftState(options = {})")
    assert body.count("_findDeadLetterShiftRecord(objectId)") == 2


def test_offline_branch_checks_local_active_session_before_its_dead_letter_lookup():
    # The offline branch (if (serverError) { ... }) must resolve local state
    # and check workerShiftStateHasActiveSession() BEFORE consulting
    # dead_letter -- a real local ACTIVE/PAUSED session takes precedence over
    # an unrelated stale sync failure.
    body = _fn(_source(), "async function resolveWorkerShiftState(options = {})")
    if_server_error_idx = body.index("if (serverError) {")
    local_state_idx = body.index("_resolveWorkerShiftLocalState(objectId, serverError)", if_server_error_idx)
    has_active_idx = body.index("workerShiftStateHasActiveSession(localState)", if_server_error_idx)
    offline_dead_letter_idx = body.index("_findDeadLetterShiftRecord(objectId)", if_server_error_idx)

    assert if_server_error_idx < local_state_idx < has_active_idx < offline_dead_letter_idx


def test_offline_branch_returns_local_state_annotated_with_sync_warning_not_overridden():
    # A dead_letter found alongside a valid local active session must be
    # surfaced as a non-blocking annotation, not replace the real state.
    body = _fn(_source(), "async function resolveWorkerShiftState(options = {})")
    assert "{ ...localState, syncWarning: deadLetterWhileOffline }" in body


def test_dead_letter_only_consulted_after_the_server_try_block():
    # The dead_letter lookups must be positioned textually after the try/catch
    # that calls the server, not inside an early branch that could return
    # before the server was actually attempted.
    body = _fn(_source(), "async function resolveWorkerShiftState(options = {})")
    try_idx = body.index("try {")
    catch_idx = body.index("} catch (e) {\n    serverError = e;\n  }")
    first_dead_letter_idx = body.index("_findDeadLetterShiftRecord(objectId)")
    assert try_idx < catch_idx < first_dead_letter_idx
