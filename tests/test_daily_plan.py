"""Tests for DailyPlan backend (Round 1 — Production Control Program).

Tests the daily_plan_lib store operations and the /api/daily-plan/* routes in main.py.
Uses the same plain-function call pattern as the other tests (no HTTP test client),
with MINIAPP_DATA_ROOT isolated to a temp dir per-test so nothing touches production.
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402


def _make_env(tmp: str):
    os.environ['MINIAPP_DATA_ROOT'] = tmp
    os.environ.setdefault('BOT_TOKEN', 'test')


# ── daily_plan_lib unit tests ────────────────────────────────────────────────

class DailyPlanLibTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        import daily_plan_lib as dpl
        self.dpl = dpl
        store = os.path.join(self.tmp, 'daily_plan_store.json')
        sync = os.path.join(self.tmp, 'plan_sync_state.json')
        cal = os.path.join(self.tmp, 'work_calendar.json')
        dpl.configure(store, sync, cal)

    def _make_item(self, idx=1) -> dict:
        return {
            "id": f"item-{idx}",
            "sequence": idx,
            "title": f"Шпаклевание зона {idx}",
            "objective": "Нанести шпаклёвку Q2",
            "planned_quantity": 10.0,
            "unit": "м²",
            "time_estimate_hours": 2.0,
            "work_type_id": "filling_q1_q4",
            "required_tools": [],
            "required_materials": [],
        }

    def test_create_plan_returns_draft(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        self.assertEqual(plan['status'], 'draft')
        self.assertEqual(plan['version'], 1)
        self.assertIsNotNone(plan['id'])
        self.assertIsNotNone(plan['content_hash'])

    def test_publish_plan(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        published = self.dpl.publish_plan(plan['id'], 'owner')
        self.assertEqual(published['status'], 'published')
        self.assertIsNotNone(published['published_at'])

    def test_cannot_publish_already_published(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        with self.assertRaises(ValueError):
            self.dpl.publish_plan(plan['id'], 'owner')

    def test_accept_plan_by_assigned_worker(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        acceptance = self.dpl.accept_plan(plan['id'], 1, '42')
        self.assertEqual(acceptance['worker_id'], '42')
        self.assertIsNotNone(acceptance['accepted_at'])

    def test_accept_idempotent(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        a1 = self.dpl.accept_plan(plan['id'], 1, '42')
        a2 = self.dpl.accept_plan(plan['id'], 1, '42')
        self.assertEqual(a1['id'], a2['id'])  # same record

    def test_unassigned_worker_cannot_accept(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        with self.assertRaises(PermissionError):
            self.dpl.accept_plan(plan['id'], 1, '99')

    def test_update_items_pre_acceptance_increments_version(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        new_items = [self._make_item(1), self._make_item(2)]
        updated = self.dpl.update_plan_items(
            plan['id'], new_items, 'sheets_edit', 'Added item 2', 'plan_sync'
        )
        self.assertEqual(updated['version'], 2)
        self.assertEqual(updated['status'], 'published')  # still published, not amendment

    def test_update_items_post_acceptance_creates_amendment(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        self.dpl.accept_plan(plan['id'], 1, '42')
        new_items = [self._make_item(1), self._make_item(2)]
        updated = self.dpl.update_plan_items(
            plan['id'], new_items, 'sheets_edit', 'Added item 2', 'plan_sync'
        )
        self.assertEqual(updated['status'], 'amendment_pending')
        amendments = self.dpl.get_pending_amendments(plan['id'])
        self.assertEqual(len(amendments), 1)

    def test_update_items_idempotent_same_hash(self):
        items = [self._make_item()]
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=items, created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        result = self.dpl.update_plan_items(plan['id'], items, 'sheets_edit', 'no change', 'sync')
        self.assertEqual(result['version'], 1)  # unchanged

    def test_get_today_plan_prefers_published_over_draft(self):
        self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        plan2 = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item(2)], created_by='owner',
        )
        self.dpl.publish_plan(plan2['id'], 'owner')
        result = self.dpl.get_today_plan_for_worker('42', '2026-09-10')
        self.assertEqual(result['id'], plan2['id'])

    def test_apply_execution_creates_carryover_for_partial_items(self):
        items = [self._make_item(1), self._make_item(2)]
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=items, created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        self.dpl.accept_plan(plan['id'], 1, '42')

        results = [
            {"item_id": "item-1", "status": "done", "actual_quantity": 10.0, "reason_code": None, "comment": ""},
            {"item_id": "item-2", "status": "partial", "actual_quantity": 5.0, "reason_code": "time_limit", "comment": ""}
        ]
        execution = self.dpl.apply_daily_execution(
            session_id='sess-001', daily_plan_id=plan['id'], plan_version=1,
            worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
            item_results=results,
        )
        self.assertIsNotNone(execution)

        carryovers = self.dpl.get_carryovers_for_worker('42', '2026-09-11')
        # item-2 is partial → carried over to next working day
        self.assertEqual(len(carryovers), 1)
        self.assertEqual(carryovers[0]['item_id'], 'item-2')
        self.assertEqual(carryovers[0]['remaining_quantity'], 5.0)

    def test_apply_execution_idempotent(self):
        items = [self._make_item()]
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=items, created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        results = [{"item_id": "item-1", "status": "done", "actual_quantity": 10.0,
                    "reason_code": None, "comment": ""}]
        e1 = self.dpl.apply_daily_execution(
            'sess-dup', plan['id'], 1, '42', '2026-09-10', 'OBJ-1', results)
        e2 = self.dpl.apply_daily_execution(
            'sess-dup', plan['id'], 1, '42', '2026-09-10', 'OBJ-1', results)
        self.assertEqual(e1['session_id'], e2['session_id'])

    def test_carryover_idempotent(self):
        items = [self._make_item()]
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=items, created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        results = [{"item_id": "item-1", "status": "not_done", "actual_quantity": None,
                    "reason_code": "blocked", "comment": "blocked"}]
        self.dpl.apply_daily_execution('s1', plan['id'], 1, '42', '2026-09-10', 'OBJ-1', results)
        # Second execution with same session → idempotent, no duplicate carryover
        self.dpl.apply_daily_execution('s1', plan['id'], 1, '42', '2026-09-10', 'OBJ-1', results)
        cos = self.dpl.get_carryovers_for_worker('42', '2026-09-11')
        self.assertEqual(len(cos), 1)

    def test_productivity_observation_and_aggregate(self):
        obs = self.dpl.record_productivity_observation(
            session_id='s-p1', worker_id='42', work_type_id='painting',
            date_str='2026-09-10', actual_quantity=50.0, unit='м²', person_hours=10.0,
        )
        self.assertEqual(obs['observed_rate'], 5.0)
        productivity = self.dpl.get_worker_productivity('42')
        self.assertIsNotNone(productivity)
        agg_key = '42:painting'
        self.assertIn(agg_key, productivity['aggregates'])
        agg = productivity['aggregates'][agg_key]
        self.assertEqual(agg['weighted_rate'], 5.0)
        self.assertEqual(agg['observation_count'], 1)

    def test_productivity_blends_with_baseline(self):
        self.dpl.set_manual_baseline('42', 'painting', 3.0)
        self.dpl.record_productivity_observation(
            's-p2', '42', 'painting', '2026-09-10', 10.0, 'м²', 2.0,
        )
        prod = self.dpl.get_worker_productivity('42')
        agg = prod['aggregates']['42:painting']
        # 2 hours observed < PRIOR_HOURS (40), so effective_rate blends baseline and observed
        self.assertIsNotNone(agg['effective_rate'])
        self.assertAlmostEqual(agg['effective_rate'],
                               (2/40) * 5.0 + (38/40) * 3.0, places=2)

    def test_worker_cannot_get_other_workers_productivity(self):
        # set_manual_baseline for worker 99
        self.dpl.set_manual_baseline('99', 'painting', 5.0)
        # verify get_worker_productivity respects worker_id filter
        prod = self.dpl.get_worker_productivity('42')
        if prod:
            for agg in prod['aggregates'].values():
                self.assertEqual(agg['worker_id'], '42')

    def test_is_working_day_defaults(self):
        from datetime import date
        # Monday = working day
        self.assertTrue(self.dpl.is_working_day(date(2026, 9, 7)))
        # Saturday = not working day
        self.assertFalse(self.dpl.is_working_day(date(2026, 9, 12)))

    def test_next_working_day(self):
        from datetime import date
        # Friday Sept 11 → next working day Mon Sept 14
        nwd = self.dpl.next_working_day(date(2026, 9, 11))
        self.assertEqual(nwd, date(2026, 9, 14))

    def test_accepted_snapshot_returns_accepted_version(self):
        items_v1 = [self._make_item(1)]
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=items_v1, created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        self.dpl.accept_plan(plan['id'], 1, '42')

        # Now update items (post-acceptance)
        items_v2 = [self._make_item(1), self._make_item(2)]
        self.dpl.update_plan_items(plan['id'], items_v2, 'sheets_edit', 'Added', 'owner')

        # get_accepted_snapshot should return v1 (what was accepted), not v2
        snap = self.dpl.get_accepted_snapshot(plan['id'], '42')
        self.assertEqual(len(snap), 1)

    def test_concurrent_accept_no_duplicate(self):
        """Concurrent accepts from the same worker produce only one acceptance record."""
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')

        results = []
        def do_accept():
            try:
                a = self.dpl.accept_plan(plan['id'], 1, '42')
                results.append(a)
            except Exception as e:
                results.append(e)

        threads = [threading.Thread(target=do_accept) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        # All must succeed (idempotent), and there must be exactly one record
        store = self.dpl._load_store()
        plan_acceptances = [
            a for a in store['acceptances'].values()
            if a['daily_plan_id'] == plan['id'] and a['worker_id'] == '42'
        ]
        self.assertEqual(len(plan_acceptances), 1)


# ── API route tests (calling FastAPI handlers directly) ────────────────────

class DailyPlanRouteTests(unittest.TestCase):

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

    def _make_item(self, idx=1):
        return {
            "id": f"item-{idx}", "sequence": idx,
            "title": f"Action {idx}", "objective": "",
            "planned_quantity": 5.0, "unit": "м²",
            "time_estimate_hours": 1.0, "work_type_id": "painting",
            "required_tools": [], "required_materials": [],
        }

    def test_daily_plan_today_no_plan(self):
        result = self.backend.daily_plan_today(
            user={'id': 777777}, role='worker')
        self.assertFalse(result['has_plan'])
        self.assertIn('date', result)

    def test_create_and_get_plan_as_owner(self):
        body = self.backend.DailyPlanIn(
            object_id='OBJ-ROUTE-1', stage_key='OBJ-ROUTE-1-S1',
            date='2026-09-10', assigned_worker_ids=['555'],
            items=[self.backend.DailyPlanItemIn(
                id='ri1', sequence=1, title='Test action',
                planned_quantity=5.0, unit='м²',
            )],
            publish=True,
        )
        plan = self.backend.daily_plan_create(body=body, user={'id': 1})
        self.assertEqual(plan['status'], 'published')
        return plan

    def test_worker_can_accept_published_plan(self):
        # Create a plan assigned to worker 555
        body = self.backend.DailyPlanIn(
            object_id='OBJ-ACCEPT-1', stage_key='OBJ-ACCEPT-1-S1',
            date='2026-09-10', assigned_worker_ids=['555'],
            items=[self.backend.DailyPlanItemIn(
                id='a1', sequence=1, title='Accept test',
                planned_quantity=3.0, unit='м²',
            )],
            publish=True,
        )
        plan = self.backend.daily_plan_create(body=body, user={'id': 1})

        result = self.backend.daily_plan_accept(
            plan_id=plan['id'], user={'id': 555}, role='worker')
        self.assertEqual(result['status'], 'accepted')

    def test_owner_cannot_accept_as_worker(self):
        body = self.backend.DailyPlanIn(
            object_id='OBJ-OWNR', stage_key='OBJ-OWNR-S1',
            date='2026-09-10', assigned_worker_ids=['1'],
            items=[self.backend.DailyPlanItemIn(id='o1', sequence=1, title='T')],
            publish=True,
        )
        plan = self.backend.daily_plan_create(body=body, user={'id': 1})
        with self.assertRaises(HTTPException) as ctx:
            self.backend.daily_plan_accept(plan_id=plan['id'], user={'id': 1}, role='owner')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_worker_cannot_accept_plan_not_assigned_to_them(self):
        body = self.backend.DailyPlanIn(
            object_id='OBJ-NOTME', stage_key='OBJ-NOTME-S1',
            date='2026-09-10', assigned_worker_ids=['555'],
            items=[self.backend.DailyPlanItemIn(id='nm1', sequence=1, title='T')],
            publish=True,
        )
        plan = self.backend.daily_plan_create(body=body, user={'id': 1})
        with self.assertRaises(HTTPException) as ctx:
            self.backend.daily_plan_accept(plan_id=plan['id'], user={'id': 999}, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_productivity_baseline_invalid_value(self):
        # Baseline ≤ 0 must be rejected
        with self.assertRaises(HTTPException) as ctx:
            self.backend.set_worker_baseline(
                target_user_id='42', work_type_id='painting', baseline=0.0)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_get_worker_productivity_own_data(self):
        self.dpl.set_manual_baseline('888', 'drywall', 4.0)
        result = self.backend.get_worker_productivity_api(
            target_user_id='888', user={'id': 888}, role='worker')
        self.assertIn('aggregates', result)

    def test_worker_cannot_get_other_worker_productivity(self):
        self.dpl.set_manual_baseline('999', 'drywall', 4.0)
        with self.assertRaises(HTTPException) as ctx:
            self.backend.get_worker_productivity_api(
                target_user_id='999', user={'id': 888}, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_plan_not_found_returns_404(self):
        with self.assertRaises(HTTPException) as ctx:
            self.backend.daily_plan_get(
                plan_id='nonexistent-id', user={'id': 888}, role='worker')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_report_blocker_worker(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-B-1', stage_key='OBJ-B-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        body = self.backend.PlanBlockerBody(reason_code='material_missing', comment='Нет краски')
        result = self.backend.daily_plan_report_blocker(
            plan_id=plan['id'], body=body, user={'id': 42}, role='worker')
        self.assertEqual(result['status'], 'recorded')
        self.assertEqual(result['blocker']['reason_code'], 'material_missing')
        self.assertEqual(result['blocker']['comment'], 'Нет краски')

    def test_report_blocker_owner_forbidden(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-B-2', stage_key='OBJ-B-2-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        body = self.backend.PlanBlockerBody(reason_code='other', comment='')
        with self.assertRaises(HTTPException) as ctx:
            self.backend.daily_plan_report_blocker(
                plan_id=plan['id'], body=body, user={'id': 1}, role='owner')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_report_blocker_not_assigned(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-B-3', stage_key='OBJ-B-3-S1', date_str='2026-09-10',
            assigned_worker_ids=['99'], items=[self._make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        body = self.backend.PlanBlockerBody(reason_code='tool_missing', comment='')
        with self.assertRaises(HTTPException) as ctx:
            self.backend.daily_plan_report_blocker(
                plan_id=plan['id'], body=body, user={'id': 42}, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_report_blocker_invalid_reason(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-B-4', stage_key='OBJ-B-4-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        body = self.backend.PlanBlockerBody(reason_code='unknown_reason', comment='')
        with self.assertRaises(HTTPException) as ctx:
            self.backend.daily_plan_report_blocker(
                plan_id=plan['id'], body=body, user={'id': 42}, role='worker')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_record_blocker_lib(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-B-5', stage_key='OBJ-B-5-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[self._make_item()], created_by='owner',
        )
        blocker = self.dpl.record_blocker(plan['id'], '42', 'weather', 'Rain')
        self.assertEqual(blocker['reason_code'], 'weather')
        self.assertEqual(blocker['comment'], 'Rain')
        self.assertIsNotNone(blocker['reported_at'])
        self.assertIsNone(blocker['resolved_at'])
        # Verify persisted
        store = self.dpl._load_store()
        self.assertIn(blocker['id'], store['blockers'])


# ── Round 3: apply_daily_execution lib tests ─────────────────────────────────

class ApplyDailyExecutionTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        import daily_plan_lib as dpl
        self.dpl = dpl
        store = os.path.join(self.tmp, 'daily_plan_store.json')
        sync = os.path.join(self.tmp, 'plan_sync_state.json')
        cal = os.path.join(self.tmp, 'work_calendar.json')
        dpl.configure(store, sync, cal)

    def _make_item(self, idx=1) -> dict:
        return {
            "id": f"item-{idx}", "sequence": idx, "title": f"Задача {idx}",
            "objective": "", "planned_quantity": 20.0, "unit": "м²",
            "time_estimate_hours": 2.0, "work_type_id": "filling_q1_q4",
            "required_tools": [], "required_materials": [],
        }

    def _make_published_plan(self, date_str='2026-09-10', items=None):
        items = items or [self._make_item(1), self._make_item(2)]
        plan = self.dpl.create_plan(
            object_id='OBJ-R3', stage_key='OBJ-R3-S1', date_str=date_str,
            assigned_worker_ids=['42'], items=items, created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        return plan

    def test_apply_execution_creates_execution_record(self):
        plan = self._make_published_plan()
        item_results = [{'item_id': 'item-1', 'status': 'done', 'actual_quantity': 20.0, 'unit': 'м²', 'reason_code': '', 'comment': ''}]
        execution = self.dpl.apply_daily_execution(
            session_id='sess-r3-1', daily_plan_id=plan['id'],
            plan_version=1, worker_id='42', date_str='2026-09-10',
            object_id='OBJ-R3', item_results=item_results,
        )
        self.assertEqual(execution['session_id'], 'sess-r3-1')
        self.assertEqual(execution['daily_plan_id'], plan['id'])
        store = self.dpl._load_store()
        self.assertIn('sess-r3-1', store['executions'])

    def test_apply_execution_marks_plan_completed(self):
        plan = self._make_published_plan()
        item_results = [{'item_id': 'item-1', 'status': 'done', 'actual_quantity': 20.0, 'unit': 'м²', 'reason_code': '', 'comment': ''}]
        self.dpl.apply_daily_execution(
            session_id='sess-r3-2', daily_plan_id=plan['id'],
            plan_version=1, worker_id='42', date_str='2026-09-10',
            object_id='OBJ-R3', item_results=item_results,
        )
        store = self.dpl._load_store()
        self.assertEqual(store['daily_plans'][plan['id']]['status'], 'completed')

    def test_apply_execution_creates_carryover_for_partial(self):
        plan = self._make_published_plan()
        item_results = [
            {'item_id': 'item-1', 'status': 'partial', 'actual_quantity': 8.0, 'unit': 'м²', 'reason_code': '', 'comment': 'Не успели'},
            {'item_id': 'item-2', 'status': 'done', 'actual_quantity': 20.0, 'unit': 'м²', 'reason_code': '', 'comment': ''},
        ]
        self.dpl.apply_daily_execution(
            session_id='sess-r3-3', daily_plan_id=plan['id'],
            plan_version=1, worker_id='42', date_str='2026-09-10',
            object_id='OBJ-R3', item_results=item_results,
        )
        store = self.dpl._load_store()
        carryovers = list(store['carryovers'].values())
        self.assertEqual(len(carryovers), 1)
        co = carryovers[0]
        self.assertEqual(co['item_id'], 'item-1')
        self.assertAlmostEqual(co['remaining_quantity'], 12.0, places=3)
        self.assertEqual(co['source_plan_id'], plan['id'])

    def test_apply_execution_creates_carryover_for_not_done(self):
        plan = self._make_published_plan(items=[self._make_item(1)])
        item_results = [{'item_id': 'item-1', 'status': 'not_done', 'actual_quantity': None, 'unit': 'м²', 'reason_code': '', 'comment': ''}]
        self.dpl.apply_daily_execution(
            session_id='sess-r3-4', daily_plan_id=plan['id'],
            plan_version=1, worker_id='42', date_str='2026-09-10',
            object_id='OBJ-R3', item_results=item_results,
        )
        store = self.dpl._load_store()
        carryovers = list(store['carryovers'].values())
        self.assertEqual(len(carryovers), 1)
        self.assertEqual(carryovers[0]['item_id'], 'item-1')
        # when actual_quantity is None, remaining_quantity copies planned_quantity
        self.assertAlmostEqual(carryovers[0]['remaining_quantity'], 20.0, places=3)

    def test_apply_execution_idempotent(self):
        plan = self._make_published_plan(items=[self._make_item(1)])
        item_results = [{'item_id': 'item-1', 'status': 'done', 'actual_quantity': 20.0, 'unit': 'м²', 'reason_code': '', 'comment': ''}]
        ex1 = self.dpl.apply_daily_execution(
            session_id='sess-r3-idem', daily_plan_id=plan['id'],
            plan_version=1, worker_id='42', date_str='2026-09-10',
            object_id='OBJ-R3', item_results=item_results,
        )
        ex2 = self.dpl.apply_daily_execution(
            session_id='sess-r3-idem', daily_plan_id=plan['id'],
            plan_version=1, worker_id='42', date_str='2026-09-10',
            object_id='OBJ-R3', item_results=item_results,
        )
        self.assertEqual(ex1['session_id'], ex2['session_id'])
        store = self.dpl._load_store()
        self.assertEqual(len(store['executions']), 1)


# ── Round 4: matrix + replan + risk + worker_id param ──────────────────────

class Round4RouteTests(unittest.TestCase):

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

    def _make_item(self, idx=1):
        return {
            "id": f"item-{idx}", "sequence": idx,
            "title": f"R4 Action {idx}", "objective": "",
            "planned_quantity": 5.0, "unit": "м²",
            "time_estimate_hours": 1.0, "work_type_id": "painting",
            "required_tools": [], "required_materials": [],
        }

    def _create_published_plan(self, object_id, date='2026-09-10', workers=None):
        body = self.backend.DailyPlanIn(
            object_id=object_id, stage_key=f'{object_id}-S1',
            date=date, assigned_worker_ids=workers or ['900'],
            items=[self.backend.DailyPlanItemIn(
                id='ri1', sequence=1, title='R4 test action',
                planned_quantity=5.0, unit='м²',
            )],
            publish=True,
        )
        return self.backend.daily_plan_create(body=body, user={'id': 1})

    def test_owner_today_with_worker_id_param(self):
        """Owner can see a specific worker's today plan via ?worker_id=."""
        # No plan for worker 999 → has_plan=False
        result = self.backend.daily_plan_today(
            worker_id_param='999', user={'id': 1}, role='owner')
        self.assertFalse(result['has_plan'])

    def test_worker_cannot_use_worker_id_param(self):
        """Worker always sees their own plan (worker_id_param is ignored)."""
        result = self.backend.daily_plan_today(
            worker_id_param='1', user={'id': 888}, role='worker')
        self.assertFalse(result['has_plan'])

    def test_owner_matrix_empty(self):
        """Owner matrix returns empty rows for date with no plans."""
        result = self.backend.daily_plan_owner_matrix(
            date_from='2025-01-01', date_to='2025-01-31',
            object_id='', _=None,
        )
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['total'], 0)

    def test_owner_matrix_returns_plans(self):
        """Owner matrix returns plans for the given date range."""
        self._create_published_plan('OBJ-M1', '2026-09-10')
        self._create_published_plan('OBJ-M2', '2026-09-11')
        result = self.backend.daily_plan_owner_matrix(
            date_from='2026-09-10', date_to='2026-09-11',
            object_id='', _=None,
        )
        self.assertGreaterEqual(result['total'], 2)
        dates = [r['date'] for r in result['rows']]
        self.assertIn('2026-09-10', dates)
        self.assertIn('2026-09-11', dates)

    def test_owner_matrix_filter_by_object(self):
        """Owner matrix filters by object_id."""
        self._create_published_plan('OBJ-MFILT', '2026-09-15')
        result = self.backend.daily_plan_owner_matrix(
            date_from='2026-09-01', date_to='2026-09-30',
            object_id='OBJ-MFILT', _=None,
        )
        for row in result['rows']:
            self.assertEqual(row['object_id'], 'OBJ-MFILT')
        self.assertGreaterEqual(result['total'], 1)

    def test_replan_no_plans_returns_green(self):
        """Replan on object with no plans returns green risk."""
        result = self.backend.daily_plan_replan(
            object_id='OBJ-NOPLAN', body=self.backend.ReplanRequestBody(), _=None,
        )
        self.assertEqual(result['risk_level'], 'green')
        self.assertEqual(result['issues'], [])

    def test_replan_with_plans_returns_summary(self):
        """Replan summarises plans and returns a risk assessment."""
        self._create_published_plan('OBJ-REPLAN', '2026-09-20')
        result = self.backend.daily_plan_replan(
            object_id='OBJ-REPLAN', body=self.backend.ReplanRequestBody(), _=None,
        )
        self.assertIn('risk_level', result)
        self.assertIn('issues', result)
        self.assertIn('recommendations', result)
        self.assertGreaterEqual(result['plan_count'], 1)

    def test_compute_risk_level_green(self):
        """No carryovers, no amendments, no blockers → green."""
        risk = self.backend._compute_risk_level([], [], [], None)
        self.assertEqual(risk, 'green')

    def test_compute_risk_level_yellow_carryover(self):
        """Carryovers present → yellow."""
        risk = self.backend._compute_risk_level([{'id': 'c1'}], [], [], None)
        self.assertEqual(risk, 'yellow')

    def test_compute_risk_level_yellow_amendments(self):
        """Pending amendments → yellow."""
        risk = self.backend._compute_risk_level([], [{'id': 'a1'}], [], None)
        self.assertEqual(risk, 'yellow')

    def test_compute_risk_level_orange_blocker(self):
        """Blocker reported → orange."""
        risk = self.backend._compute_risk_level([], [], [{'id': 'b1'}], None)
        self.assertEqual(risk, 'orange')

    def test_get_blockers_for_plan_lib(self):
        """get_blockers_for_plan returns only unresolved blockers for the given plan."""
        plan = self.dpl.create_plan(
            object_id='OBJ-BFP', stage_key='OBJ-BFP-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[{
                "id": "i1", "sequence": 1, "title": "t", "objective": "",
                "planned_quantity": 5.0, "unit": "м²", "time_estimate_hours": 1.0,
                "work_type_id": "painting", "required_tools": [], "required_materials": [],
            }], created_by='owner',
        )
        self.dpl.record_blocker(plan['id'], '42', 'weather', 'Rain')
        blockers = self.dpl.get_blockers_for_plan(plan['id'])
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0]['reason_code'], 'weather')
        # Another plan's blockers must not appear
        other_plan = self.dpl.create_plan(
            object_id='OBJ-BFP2', stage_key='OBJ-BFP2-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[{
                "id": "i1", "sequence": 1, "title": "t", "objective": "",
                "planned_quantity": 5.0, "unit": "м²", "time_estimate_hours": 1.0,
                "work_type_id": "painting", "required_tools": [], "required_materials": [],
            }], created_by='owner',
        )
        self.dpl.record_blocker(other_plan['id'], '42', 'tool_missing', 'No drill')
        blockers_filtered = self.dpl.get_blockers_for_plan(plan['id'])
        self.assertEqual(len(blockers_filtered), 1)  # still just the first plan's blocker


if __name__ == '__main__':
    unittest.main()
