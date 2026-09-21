"""Architecture guard: resolveWorkerShiftState() must stay the single source
of truth for worker shift state (Worker UX V2 Этап 1's canonical target,
per plan review during the c23894d/3ba474b/4a69bc6 upstream merge).

The risk this guards against: Home, FAB, Object entry, and Stages each
determining shift state independently (their own /api/checkin call, their
own localStorage read, their own outbox check) is exactly the bug class this
branch's resolver was built to eliminate -- and upstream's parallel
_findPendingCheckinOutboxRecord() (a second, checkin.js-local mechanism
doing the same job the resolver already does) showed how easily that
architecture can silently re-fragment if a new consumer bypasses the
resolver instead of extending it.

This is a regression guard, not a full architecture test -- it does not (and
cannot, via source grep) prove correctness, only that the known consumer
files keep going through the resolver rather than reintroducing a parallel
path.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOME_JS = ROOT / "frontend" / "js" / "home.js"
WORKER_CHECKIN_FAB_JS = ROOT / "frontend" / "js" / "worker-checkin-fab.js"
CHECKIN_JS = ROOT / "frontend" / "js" / "checkin.js"
OBJECT_INFO_JS = ROOT / "frontend" / "js" / "object-info.js"
WORKER_SHIFT_STATE_JS = ROOT / "frontend" / "js" / "worker-shift-state.js"

# Every file that displays or gates on "is there an active/pending shift"
# must call the resolver at least once -- not reimplement its own check.
CONSUMER_FILES = [HOME_JS, WORKER_CHECKIN_FAB_JS, CHECKIN_JS, OBJECT_INFO_JS]


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_worker_shift_state_resolver_exists_as_the_single_module():
    assert WORKER_SHIFT_STATE_JS.exists(), (
        "worker-shift-state.js is the canonical target architecture for "
        "Worker UX V2 Этап 1 -- if this file is gone, shift-state "
        "determination has silently re-fragmented across consumers."
    )


def test_every_known_consumer_calls_the_shared_resolver():
    for path in CONSUMER_FILES:
        src = _source(path)
        assert "resolveWorkerShiftState(" in src, (
            f"{path.name} shows/gates on worker shift state but does not call "
            "resolveWorkerShiftState() -- it must extend the resolver, not "
            "reimplement its own state check."
        )


def test_no_consumer_reimplements_its_own_pending_outbox_check():
    # The exact anti-pattern found in upstream's 3ba474b: a second,
    # file-local "is there a pending outbox record for this object" check
    # that duplicates what the resolver already does internally.
    forbidden_names = ("_findPendingCheckinOutboxRecord", "_findActiveWorkerCheckinObjectId")
    for path in CONSUMER_FILES:
        src = _source(path)
        for name in forbidden_names:
            # _findActiveWorkerCheckinObjectId is allowed to exist as a definition
            # (it's dead code kept for now, see worker-checkin-fab.js), but must
            # never be CALLED elsewhere -- count all "name(" occurrences and
            # subtract the one that's the function's own declaration line.
            def_pattern = f"function {name}("
            total_occurrences = src.count(f"{name}(")
            has_definition = def_pattern in src
            call_count = total_occurrences - (1 if has_definition else 0)
            assert call_count == 0, (
                f"{path.name} calls {name}() -- this is either the exact "
                "truncated-session-write bug class this branch's resolver "
                "architecture eliminated, or a parallel shift-state mechanism "
                "outside the resolver. Route through resolveWorkerShiftState() "
                "instead of calling/reviving this function."
            )


def test_no_consumer_reads_checkin_outbox_directly_bypassing_the_resolver():
    # promontaOutboxList(CHECKIN_OUTBOX_KIND_*) is a low-level primitive the
    # resolver itself uses internally -- a consumer calling it directly to
    # answer "is a shift pending" (rather than going through the resolver)
    # would be reintroducing the exact parallel-mechanism problem.
    for path in (HOME_JS, WORKER_CHECKIN_FAB_JS, OBJECT_INFO_JS):
        src = _source(path)
        assert "promontaOutboxList(CHECKIN_OUTBOX_KIND" not in src, (
            f"{path.name} reads the checkin outbox directly -- shift-pending "
            "state must be obtained via resolveWorkerShiftState(), which "
            "already does this internally."
        )
