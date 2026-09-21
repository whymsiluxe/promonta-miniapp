"""Regression coverage for offline Finish-context caching, hardened across two
rounds of owner review of the fix-shift-start merge.

Round 2 found: the offline cache (_fwReadCachedFinishContext/
_fwWriteCachedFinishContext, finish-wizard.js) was write-on-read only -- it
was written the FIRST time Finish Wizard successfully fetched /finish-context
online. Gap: Start online -> a full day of work -> network drops before
Finish is opened even once -> nothing to fall back to, even though the
worker DID accept a plan at Start and the server DOES have the frozen
accepted snapshot, just unreachable right now. Fix: a second GET
/finish-context request fired right after a confirmed Start
(_prefetchFinishContextAfterStart).

Round 3 found that fix was still non-deterministic: a SECOND network
round-trip can itself fail to complete in the window between Start
succeeding and connectivity actually dropping. Fix: checkin_start()'s
response now embeds the exact same finish-context shape directly
(backend's _build_finish_context(), shared with the GET endpoint) -- the
frontend prefers that zero-extra-round-trip field when present, and only
falls back to a live GET request when it isn't.
"""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import daily_plan_lib as dpl  # noqa: E402
import main as backend  # noqa: E402


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


# ── Frontend: prefers the embedded field, falls back to a live GET ─────────

def test_prefetch_function_prefers_embedded_finish_context_over_a_live_fetch():
    src = _source(FINISH_WIZARD_JS)
    body = _fn(src, "async function _prefetchFinishContextAfterStart(sessionId, startResponse)")
    # 21.09 (owner review finding, round 4): must check the field is non-null,
    # not merely PRESENT -- checkin_start()'s own try/except around
    # _build_finish_context() can legitimately send back
    # `finish_context: null`, and hasOwnProperty() would still be true for a
    # null value, wrongly skipping the live-GET fallback below.
    assert "Object.prototype.hasOwnProperty.call(startResponse" not in body, (
        "must check startResponse?.finish_context != null, not "
        "hasOwnProperty -- the field can be present but null"
    )
    assert "startResponse?.finish_context != null" in body
    assert "startResponse.finish_context" in body
    assert "if (embedded?.has_plan) _fwWriteCachedFinishContext(sessionId, embedded);" in body
    # Fallback path for when the embedded field is absent OR null.
    assert "`/api/checkin/${sessionId}/finish-context`" in body
    assert "if (data?.has_plan) _fwWriteCachedFinishContext(sessionId, data);" in body
    assert "catch (e)" in body

    embedded_idx = body.index("startResponse?.finish_context != null")
    fallback_idx = body.index("await api(`/api/checkin/${sessionId}/finish-context`)")
    assert embedded_idx < fallback_idx, "embedded response must be checked BEFORE falling back to a live fetch"


def test_online_start_success_path_passes_the_full_response_through():
    body = _fn(_source(CHECKIN_JS), "async function _confirmCheckinPreview()")
    assert "_prefetchFinishContextAfterStart(session.id, session)" in body
    close_idx = body.index("_closeCheckinPreviewModal();")
    prefetch_idx = body.index("_prefetchFinishContextAfterStart(session.id, session)")
    assert close_idx < prefetch_idx


def test_offline_start_retry_success_path_also_passes_the_full_response_through():
    # The path a Start takes when it was queued offline and only just synced
    # once connectivity returned -- exactly the case where having the cache
    # already warm matters most, since the worker may be mid-shift by then.
    body = _fn(_source(CHECKIN_JS), "async function _sendCheckinStartOutboxRecord(record)")
    assert "_prefetchFinishContextAfterStart(session.id, session)" in body


# ── Backend: checkin_start embeds the same shape checkin_finish_context uses ──

class StartEmbedsFinishContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        dpl.configure(
            os.path.join(self.tmp, 'daily_plan_store.json'),
            os.path.join(self.tmp, 'plan_sync_state.json'),
            os.path.join(self.tmp, 'work_calendar.json'),
        )

    def test_build_finish_context_is_shared_by_both_endpoints(self):
        # Source-level guard against the exact bug class the architecture
        # guard test already protects on the frontend: two independent
        # implementations of the same shape silently drifting apart. Both
        # checkin_start and checkin_finish_context must call the ONE helper.
        src = open(os.path.join(os.path.dirname(__file__), '..', 'backend', 'main.py'),
                    encoding='utf-8').read()
        assert 'def _build_finish_context(session: dict) -> dict:' in src
        start_fn = src[src.index('async def checkin_start('):src.index('@app.post("/api/checkin/{session_id}/pause")')]
        assert "response['finish_context'] = _build_finish_context(entry)" in start_fn
        finish_ctx_fn = src[src.index('def checkin_finish_context('):src.index('@app.get("/api/checkin/{session_id}/photo/{which}/{index}")')]
        assert 'return _build_finish_context(session)' in finish_ctx_fn

    def test_plan_linked_start_response_embeds_a_populated_finish_context(self):
        plan = dpl.create_plan(
            object_id='OBJ-1', stage_key='stage-1', date_str=backend._today_berlin_str(),
            assigned_worker_ids=['77'],
            items=[{
                "id": "item-1", "sequence": 1, "title": "Task 1", "objective": "Do work",
                "planned_quantity": 1, "unit": "pcs", "time_estimate_hours": 1,
                "work_type_id": "work", "required_tools": [], "required_materials": [],
            }],
            created_by='owner',
        )
        dpl.publish_plan(plan['id'], 'owner')
        acceptance = dpl.accept_plan(plan['id'], plan['version'], '77')

        entry = {
            'id': 'sess-embed-test', 'object_id': 'OBJ-1', 'user_id': '77',
            'daily_plan_id': plan['id'], 'daily_plan_version': str(plan['version']),
            'daily_plan_acceptance_id': acceptance['id'],
        }
        result = backend._build_finish_context(entry)
        self.assertTrue(result['has_plan'])
        self.assertEqual(result['plan']['id'], plan['id'])
        self.assertEqual(len(result['plan']['items']), 1)
        self.assertEqual(result['plan']['items'][0]['id'], 'item-1')

    def test_plan_less_start_embeds_a_graceful_no_plan_context_not_none(self):
        entry = {'id': 'sess-no-plan', 'object_id': 'OBJ-1', 'user_id': '77'}
        result = backend._build_finish_context(entry)
        self.assertEqual(result, {
            'session_id': 'sess-no-plan', 'object_id': 'OBJ-1', 'has_plan': False,
        })


if __name__ == '__main__':
    unittest.main()
