"""Regression coverage for a P0 found in owner review of the fix-shift-start /
origin/main merge: resolveWorkerShiftState() used to check dead_letter outbox
records BEFORE ever asking the server.

Concretely: a worker whose Finish permanently failed to sync yesterday (now
sitting as a dead_letter record for OBJECT-A) would see "⚠️ Ошибка
синхронизации" and have Start/Finish disabled TODAY on OBJECT-B, even though
the server has a perfectly normal ACTIVE session open for them right now --
the resolver never got that far, because the stale dead_letter from an
unrelated, already-finished shift short-circuited the whole function first.

The fix splits dead_letter handling out of _resolveWorkerShiftOutboxState()
(which now only resolves LIVE pending records) into a separate
_findDeadLetterShiftRecord(), consulted by resolveWorkerShiftState() only
AFTER the server has had a chance to answer -- a dead_letter is a recovery
concern, not proof that no current shift can be resolved.
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


def test_resolver_checks_server_before_dead_letter():
    body = _fn(_source(), "async function resolveWorkerShiftState(options = {})")
    pending_idx = body.index("_resolveWorkerShiftOutboxState(objectId)")
    server_idx = body.index("await api(path)")
    dead_letter_idx = body.index("_findDeadLetterShiftRecord(objectId)")
    local_idx = body.index("_resolveWorkerShiftLocalState(objectId, serverError)")

    assert pending_idx < server_idx < dead_letter_idx < local_idx, (
        "Precedence must be: live pending outbox -> server -> dead_letter "
        "(recovery signal, not a block) -> localStorage fallback. A stale "
        "dead_letter from an unrelated shift must never be checked before "
        "the server gets a chance to report the CURRENT real state."
    )


def test_dead_letter_only_consulted_after_the_server_try_block():
    # The dead_letter lookup must be positioned textually after the try/catch
    # that calls the server, not inside an early branch that could return
    # before the server was actually attempted.
    body = _fn(_source(), "async function resolveWorkerShiftState(options = {})")
    try_idx = body.index("try {")
    catch_idx = body.index("} catch (e) {\n    serverError = e;\n  }")
    dead_letter_idx = body.index("_findDeadLetterShiftRecord(objectId)")
    assert try_idx < catch_idx < dead_letter_idx
