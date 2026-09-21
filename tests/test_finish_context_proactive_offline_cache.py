"""Regression coverage for a P0 found in round-2 owner review of the
fix-shift-start merge: the offline Finish-context cache
(_fwReadCachedFinishContext/_fwWriteCachedFinishContext, finish-wizard.js) was
write-on-read only -- it was written the FIRST time Finish Wizard successfully
fetched /finish-context online. That leaves a real gap: Start online -> a full
day of work -> network drops before Finish is opened even once -> there is
nothing to fall back to, even though the worker DID accept a plan at Start and
the server DOES have the frozen accepted snapshot, just unreachable right now.

Fix: _prefetchFinishContextAfterStart(sessionId) is called right after a
CONFIRMED Start succeeds -- both the direct online path
(checkin.js::_confirmCheckinPreview) and the offline-outbox-retry path
(checkin.js::_sendCheckinStartOutboxRecord, for a Start that was queued
offline and only just synced) -- so the cache exists before Finish is ever
opened, not only after.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKIN_JS = ROOT / "frontend" / "js" / "checkin.js"
FINISH_WIZARD_JS = ROOT / "frontend" / "js" / "finish-wizard.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fn(src: str, signature: str) -> str:
    start = src.index(signature)
    depth = 0
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


def test_prefetch_function_exists_and_writes_cache_only_when_has_plan():
    src = _source(FINISH_WIZARD_JS)
    body = _fn(src, "async function _prefetchFinishContextAfterStart(sessionId)")
    assert "`/api/checkin/${sessionId}/finish-context`" in body
    assert "if (data?.has_plan) _fwWriteCachedFinishContext(sessionId, data);" in body
    # Best-effort: a failed prefetch must not throw/block anything upstream.
    assert "catch (e)" in body


def test_online_start_success_path_calls_the_prefetch():
    body = _fn(_source(CHECKIN_JS), "async function _confirmCheckinPreview()")
    assert "_prefetchFinishContextAfterStart(session.id)" in body
    # Must run AFTER the modal closes -- fire-and-forget, must not block the
    # worker from seeing Start succeed and moving on.
    close_idx = body.index("_closeCheckinPreviewModal();")
    prefetch_idx = body.index("_prefetchFinishContextAfterStart(session.id)")
    assert close_idx < prefetch_idx


def test_offline_start_retry_success_path_also_calls_the_prefetch():
    # The path a Start takes when it was queued offline and only just synced
    # once connectivity returned -- exactly the case where having the cache
    # already warm matters most, since the worker may be mid-shift by then.
    body = _fn(_source(CHECKIN_JS), "async function _sendCheckinStartOutboxRecord(record)")
    assert "_prefetchFinishContextAfterStart(session.id)" in body
