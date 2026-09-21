"""Tests for GET /api/checkin/{session_id}/finish-context (18.09, audit finding).

Before this endpoint existed, finish-wizard.js read window._todayPlanState --
the LIVE current DailyPlan -- to show the worker their task list at Finish. If
the owner amended the plan after this worker started their shift, Finish would
show the amended item list, not what this worker actually accepted and started
against. checkin_finish() itself already validates against the immutable
accepted_context_snapshot (Round 1.2 #2, daily_plan_lib.py) -- this endpoint
closes the same gap on the read side by giving the frontend the matching
frozen item list to display.

20.09 (merged from upstream c23894d): upstream independently added a second
route registration for the same path/function name pair with a different
(flat, not nested-under-"plan") response shape -- get_checkin_finish_context().
FastAPI silently used whichever was registered first and left the other dead;
this is the same "shift-state logic re-fragments across files" risk class the
architecture guard test (test_worker_shift_state_architecture_guard.py) covers
for the frontend resolver, just at the route level. The duplicate was deleted;
this file only tests the one surviving function, whose nested plan.{id,
version, items} shape is what finish-wizard.js's _fwApplyFinishContext()
actually reads.
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import daily_plan_lib as dpl  # noqa: E402
import main as backend  # noqa: E402


WORKER = {'id': 42, 'first_name': 'Worker'}


def _item(idx=1):
    return {
        "id": f"item-{idx}",
        "sequence": idx,
        "title": f"Task {idx}",
        "objective": "Do work",
        "planned_quantity": 1,
        "unit": "pcs",
        "time_estimate_hours": 1,
        "work_type_id": "work",
        "required_tools": [],
        "required_materials": [],
    }


class CheckinFinishContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        dpl.configure(
            os.path.join(self.tmp, 'daily_plan_store.json'),
            os.path.join(self.tmp, 'plan_sync_state.json'),
            os.path.join(self.tmp, 'work_calendar.json'),
        )

    def test_finish_context_without_plan_is_explicit_no_plan(self):
        session = {'id': 'sess-no-plan', 'user_id': '42', 'object_id': 'OBJ-1'}
        with patch.object(backend, '_load_checkin_meta', return_value=[session]):
            result = backend.checkin_finish_context('sess-no-plan', user=WORKER, role='worker')

        self.assertFalse(result['has_plan'])
        self.assertEqual(result['object_id'], 'OBJ-1')

    def test_finish_context_returns_accepted_snapshot_items(self):
        plan = dpl.create_plan(
            object_id='OBJ-1',
            stage_key='stage-1',
            date_str='2026-09-21',
            assigned_worker_ids=['42'],
            items=[_item(1)],
            created_by='owner',
        )
        dpl.publish_plan(plan['id'], 'owner')
        acceptance = dpl.accept_plan(plan['id'], 1, '42')
        dpl.update_plan_items(plan['id'], [_item(1), _item(2)], 'sheets_edit', 'Added second item', 'owner')

        session = {
            'id': 'sess-plan',
            'user_id': '42',
            'object_id': 'OBJ-1',
            'daily_plan_id': plan['id'],
            'daily_plan_version': '1',
            'daily_plan_acceptance_id': acceptance['id'],
        }
        with patch.object(backend, '_load_checkin_meta', return_value=[session]):
            result = backend.checkin_finish_context('sess-plan', user=WORKER, role='worker')

        self.assertTrue(result['has_plan'])
        self.assertEqual(result['plan']['id'], plan['id'])
        self.assertEqual(result['plan']['version'], 1)
        self.assertEqual(len(result['plan']['items']), 1)
        self.assertEqual(result['plan']['items'][0]['id'], 'item-1')

    def test_finish_context_uses_the_sessions_exact_acceptance_after_reaccept(self):
        # 21.09 (owner review finding, round 4, real data-integrity bug): each
        # accept_plan() call after an amendment creates a NEW acceptance record
        # for the same (plan_id, worker_id) pair -- accept v1 -> Acceptance A1,
        # owner amends -> plan v2, worker accepts v2 -> Acceptance A2. Both A1
        # and A2 now exist. dpl.get_accepted_snapshot() without an explicit
        # acceptance_id picked the FIRST matching acceptance (effectively A1,
        # the oldest) regardless of which one the session actually references --
        # a session started against A2/v2 got v1's items while this response
        # correctly reported plan.version=2 from A2's own plan_version field, a
        # real version/content mismatch in what Finish shows and submits as
        # plan-fact. And since this gets embedded in checkin_start()'s response
        # and cached offline immediately, the wrong items were durably cached
        # too, not just transiently wrong.
        plan = dpl.create_plan(
            object_id='OBJ-1', stage_key='stage-1', date_str='2026-09-21',
            assigned_worker_ids=['42'], items=[_item(1)], created_by='owner',
        )
        dpl.publish_plan(plan['id'], 'owner')
        acceptance_v1 = dpl.accept_plan(plan['id'], 1, '42')

        dpl.update_plan_items(plan['id'], [_item(1), _item(2), _item(3)], 'sheets_edit', 'Amendment', 'owner')
        plan_v2 = dpl.get_plan(plan['id'])
        acceptance_v2 = dpl.accept_plan(plan['id'], plan_v2['version'], '42')
        self.assertNotEqual(acceptance_v1['id'], acceptance_v2['id'])

        session = {
            'id': 'sess-reaccept', 'user_id': '42', 'object_id': 'OBJ-1',
            'daily_plan_id': plan['id'], 'daily_plan_version': str(plan_v2['version']),
            'daily_plan_acceptance_id': acceptance_v2['id'],
        }
        with patch.object(backend, '_load_checkin_meta', return_value=[session]):
            result = backend.checkin_finish_context('sess-reaccept', user=WORKER, role='worker')

        self.assertTrue(result['has_plan'])
        self.assertEqual(result['plan']['version'], plan_v2['version'])
        self.assertEqual(len(result['plan']['items']), 3, "must be v2's 3 items, not v1's 1 item")
        self.assertEqual({i['id'] for i in result['plan']['items']}, {'item-1', 'item-2', 'item-3'})

    def test_session_not_found_404(self):
        with patch.object(backend, '_load_checkin_meta', return_value=[]):
            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_finish_context('missing', user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_worker_cannot_read_another_workers_session(self):
        session = {'id': 'sess1', 'user_id': '555', 'object_id': 'OBJ-1'}
        with patch.object(backend, '_load_checkin_meta', return_value=[session]):
            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_finish_context('sess1', user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_can_read_any_workers_session(self):
        session = {'id': 'sess1', 'user_id': '555', 'object_id': 'OBJ-1'}
        with patch.object(backend, '_load_checkin_meta', return_value=[session]):
            result = backend.checkin_finish_context('sess1', user={'id': 1}, role='owner')
        self.assertFalse(result['has_plan'])

    def test_stale_acceptance_reference_is_graceful_no_plan_not_an_error(self):
        # 18.09 (audit finding, merged from upstream 170bf24): a session
        # referencing a plan_id/acceptance_id that no longer resolves cleanly
        # (deleted plan, dangling acceptance id) must not turn Finish into a
        # hard error -- same "not a plan-linked shift, carry on" fallback
        # checkin_start already uses elsewhere. Regression for a 409 this used
        # to raise here, which could block a worker from finishing their shift.
        session = {
            'id': 'sess-stale',
            'user_id': '42',
            'object_id': 'OBJ-1',
            'daily_plan_id': 'plan-does-not-exist',
            'daily_plan_acceptance_id': 'acceptance-does-not-exist',
        }
        with patch.object(backend, '_load_checkin_meta', return_value=[session]):
            result = backend.checkin_finish_context('sess-stale', user=WORKER, role='worker')
        self.assertFalse(result['has_plan'])


if __name__ == '__main__':
    unittest.main()
