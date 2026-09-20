"""Tests for GET /api/checkin/{session_id}/finish-context (18.09, audit finding).

Before this endpoint existed, finish-wizard.js read window._todayPlanState --
the LIVE current DailyPlan -- to show the worker their task list at Finish. If
the owner amended the plan after this worker started their shift, Finish would
show the amended item list, not what this worker actually accepted and started
against. checkin_finish() itself already validates against the immutable
accepted_context_snapshot (Round 1.2 #2, daily_plan_lib.py) -- this endpoint
closes the same gap on the read side by giving the frontend the matching
frozen item list to display.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


class CheckinFinishContextTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ['MINIAPP_DATA_ROOT'] = cls.tmp
        os.environ.setdefault('BOT_TOKEN', 'test')
        import main as backend
        cls.backend = backend
        import daily_plan_lib as dpl
        cls.dpl = dpl
        dpl.configure(
            os.path.join(cls.tmp, 'daily_plan_store.json'),
            os.path.join(cls.tmp, 'plan_sync_state.json'),
            os.path.join(cls.tmp, 'work_calendar.json'),
        )

    def setUp(self):
        self.backend.CHECKIN_META_FILE = os.path.join(self.tmp, f'checkin_meta_{self._testMethodName}.json')

    def _create_and_accept_plan(self, worker_id='555', object_id='OBJ-1', n_items=1):
        body = self.backend.DailyPlanIn(
            object_id=object_id, stage_key=f'{object_id}-S1', date='2026-09-10',
            assigned_worker_ids=[worker_id],
            items=[self.backend.DailyPlanItemIn(
                id=f'i{i}', sequence=i, title=f'Action {i}', planned_quantity=1.0, unit='м²',
            ) for i in range(1, n_items + 1)],
            publish=True,
        )
        plan = self.backend.daily_plan_create(body=body, user={'id': 1})
        acceptance = self.dpl.accept_plan(plan['id'], plan['version'], worker_id)
        return plan, acceptance

    def _save_session(self, session_id, worker_id, **extra):
        session = {
            'id': session_id, 'object_id': 'OBJ-1', 'user_id': worker_id,
            'date': '2026-09-10', 'finished': False,
            **extra,
        }
        self.backend._save_checkin_meta([session])
        return session

    def test_session_not_found_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.backend.get_checkin_finish_context(
                session_id='nonexistent', user={'id': 555}, role='worker')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_worker_cannot_read_another_workers_session(self):
        self._save_session('sess1', '555')
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.backend.get_checkin_finish_context(
                session_id='sess1', user={'id': 888}, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_can_read_any_workers_session(self):
        self._save_session('sess1', '555')
        result = self.backend.get_checkin_finish_context(
            session_id='sess1', user={'id': 1}, role='owner')
        self.assertFalse(result['has_plan'])  # no plan linked, but no 403 either

    def test_session_without_plan_returns_has_plan_false(self):
        self._save_session('sess1', '555')  # no daily_plan_id at all
        result = self.backend.get_checkin_finish_context(
            session_id='sess1', user={'id': 555}, role='worker')
        self.assertEqual(result, {'has_plan': False})

    def test_session_with_plan_returns_frozen_accepted_items(self):
        plan, acceptance = self._create_and_accept_plan(n_items=2)
        self._save_session(
            'sess1', '555',
            daily_plan_id=plan['id'],
            daily_plan_version=plan['version'],
            daily_plan_acceptance_id=acceptance['id'],
        )
        result = self.backend.get_checkin_finish_context(
            session_id='sess1', user={'id': 555}, role='worker')
        self.assertTrue(result['has_plan'])
        self.assertEqual(result['plan_id'], plan['id'])
        self.assertEqual(result['object_id'], 'OBJ-1')
        self.assertEqual(len(result['items']), 2)
        self.assertEqual({i['id'] for i in result['items']}, {'i1', 'i2'})

    def test_amendment_after_start_does_not_change_finish_context(self):
        # The core bug this endpoint fixes: an owner amendment to the LIVE plan
        # after the worker already started their shift must not change what
        # Finish shows them -- they report against what they accepted at Start.
        plan, acceptance = self._create_and_accept_plan(n_items=1)
        self._save_session(
            'sess1', '555',
            daily_plan_id=plan['id'],
            daily_plan_version=plan['version'],
            daily_plan_acceptance_id=acceptance['id'],
        )
        # Owner adds a second item to the plan post-acceptance (simulates an
        # amendment/edit to the live plan after this worker already started).
        store = self.dpl.get_store_snapshot()
        store['daily_plans'][plan['id']]['items'].append({
            'id': 'i2', 'sequence': 2, 'title': 'Added after accept',
            'objective': '', 'planned_quantity': 1.0, 'unit': 'м²',
            'time_estimate_hours': 1.0, 'work_type_id': 'painting',
            'required_tools': [], 'required_materials': [], 'status': 'pending',
        })
        self.dpl._save_store(store)

        result = self.backend.get_checkin_finish_context(
            session_id='sess1', user={'id': 555}, role='worker')
        self.assertTrue(result['has_plan'])
        # Still just the ONE item this worker actually accepted, not the
        # live plan's now-two items.
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(result['items'][0]['id'], 'i1')

    def test_stale_acceptance_id_falls_back_to_no_plan(self):
        # Defensive: session references an acceptance that doesn't resolve
        # cleanly (e.g. data corruption, manual edit) -- must not 500, falls
        # back to has_plan=False like checkin_start does for the analogous case.
        self._save_session(
            'sess1', '555',
            daily_plan_id='nonexistent-plan',
            daily_plan_version=1,
            daily_plan_acceptance_id='nonexistent-acceptance',
        )
        result = self.backend.get_checkin_finish_context(
            session_id='sess1', user={'id': 555}, role='worker')
        self.assertEqual(result, {'has_plan': False})


if __name__ == '__main__':
    unittest.main()
