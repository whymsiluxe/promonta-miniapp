"""Tests for Round 6 productivity observation auto-recording.

Tests cover:
- auto_record_execution_productivity: distributes hours proportionally / equally
- Skips items without work_type_id, not-done items, zero quantity
- Integration with record_productivity_observation (idempotent)
- GET /api/productivity/workers/{uid} permission check (403 for wrong worker)
- POST /api/productivity/workers/{uid}/baseline
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


class AutoRecordProductivityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ['MINIAPP_DATA_ROOT'] = cls.tmp
        os.environ.setdefault('BOT_TOKEN', 'test')
        import daily_plan_lib as dpl
        cls.dpl = dpl
        cls.store_path = os.path.join(cls.tmp, 'daily_plan_store.json')
        dpl.configure(
            cls.store_path,
            os.path.join(cls.tmp, 'plan_sync_state.json'),
            os.path.join(cls.tmp, 'work_calendar.json'),
        )

    def setUp(self):
        # Reset store before each test
        if os.path.exists(self.store_path):
            os.remove(self.store_path)

    def _plan(self, items=None):
        return {
            "id": "plan-1",
            "date": "2026-09-08",
            "worker_id": "42",
            "assigned_worker_ids": ["42"],
            "items": items or [],
        }

    def _item(self, item_id, work_type_id=None, time_est=None, unit='m²'):
        return {
            "id": item_id,
            "title": f"Task {item_id}",
            "planned_quantity": 100.0,
            "unit": unit,
            "work_type_id": work_type_id,
            "time_estimate_hours": time_est,
        }

    def _result(self, item_id, status='done', qty=50.0):
        return {"item_id": item_id, "status": status, "actual_quantity": qty}

    def test_no_eligible_items_returns_empty(self):
        plan = self._plan([self._item("i1")])  # no work_type_id
        result = self.dpl.auto_record_execution_productivity(
            session_id="sess-1", worker_id="42",
            plan=plan, item_results=[self._result("i1")], shift_hours=8.0,
        )
        self.assertEqual(result, [])

    def test_not_done_items_skipped(self):
        plan = self._plan([self._item("i1", work_type_id="trockenbau")])
        result = self.dpl.auto_record_execution_productivity(
            session_id="sess-2", worker_id="42",
            plan=plan,
            item_results=[self._result("i1", status="partial", qty=30.0)],
            shift_hours=4.0,
        )
        self.assertEqual(result, [])

    def test_zero_quantity_skipped(self):
        plan = self._plan([self._item("i1", work_type_id="trockenbau")])
        result = self.dpl.auto_record_execution_productivity(
            session_id="sess-3", worker_id="42",
            plan=plan,
            item_results=[self._result("i1", status="done", qty=0.0)],
            shift_hours=4.0,
        )
        self.assertEqual(result, [])

    def test_single_item_gets_all_shift_hours(self):
        plan = self._plan([self._item("i1", work_type_id="trockenbau", time_est=8.0)])
        result = self.dpl.auto_record_execution_productivity(
            session_id="sess-4", worker_id="42",
            plan=plan,
            item_results=[self._result("i1", status="done", qty=200.0)],
            shift_hours=8.0,
        )
        self.assertEqual(len(result), 1)
        obs = result[0]
        self.assertAlmostEqual(obs['person_hours'], 8.0, places=2)
        self.assertAlmostEqual(obs['actual_quantity'], 200.0)
        self.assertAlmostEqual(obs['observed_rate'], 25.0, places=2)  # 200/8

    def test_proportional_distribution_by_time_estimate(self):
        plan = self._plan([
            self._item("i1", work_type_id="trockenbau", time_est=6.0),
            self._item("i2", work_type_id="maler", time_est=2.0),
        ])
        result = self.dpl.auto_record_execution_productivity(
            session_id="sess-5", worker_id="42",
            plan=plan,
            item_results=[
                self._result("i1", qty=60.0),
                self._result("i2", qty=20.0),
            ],
            shift_hours=8.0,
        )
        self.assertEqual(len(result), 2)
        hours_by_type = {obs['work_type_id']: obs['person_hours'] for obs in result}
        self.assertAlmostEqual(hours_by_type['trockenbau'], 6.0, places=3)
        self.assertAlmostEqual(hours_by_type['maler'], 2.0, places=3)

    def test_equal_distribution_when_no_time_estimate(self):
        plan = self._plan([
            self._item("i1", work_type_id="trockenbau"),   # no time_est
            self._item("i2", work_type_id="maler"),
        ])
        result = self.dpl.auto_record_execution_productivity(
            session_id="sess-6", worker_id="42",
            plan=plan,
            item_results=[self._result("i1", qty=50.0), self._result("i2", qty=30.0)],
            shift_hours=8.0,
        )
        self.assertEqual(len(result), 2)
        for obs in result:
            self.assertAlmostEqual(obs['person_hours'], 4.0, places=3)

    def test_idempotent_second_call_returns_existing(self):
        plan = self._plan([self._item("i1", work_type_id="trockenbau", time_est=4.0)])
        kwargs = dict(
            session_id="sess-7", worker_id="42",
            plan=plan, item_results=[self._result("i1", qty=100.0)],
            shift_hours=4.0,
        )
        r1 = self.dpl.auto_record_execution_productivity(**kwargs)
        r2 = self.dpl.auto_record_execution_productivity(**kwargs)
        self.assertEqual(len(r1), 1)
        self.assertEqual(len(r2), 1)
        # Second call: idempotent — same obs returned
        self.assertEqual(r1[0]['id'], r2[0]['id'])

    def test_productivity_aggregate_updated(self):
        plan = self._plan([self._item("i1", work_type_id="fliesen", time_est=8.0)])
        self.dpl.auto_record_execution_productivity(
            session_id="sess-8", worker_id="99",
            plan=plan, item_results=[self._result("i1", qty=80.0)],
            shift_hours=8.0,
        )
        prod = self.dpl.get_worker_productivity("99")
        self.assertIsNotNone(prod)
        agg_key = "99:fliesen"
        self.assertIn(agg_key, prod['aggregates'])
        agg = prod['aggregates'][agg_key]
        self.assertEqual(agg['observation_count'], 1)
        self.assertAlmostEqual(agg['effective_rate'], 10.0, places=2)  # 80/8

    def test_shift_hours_zero_returns_empty(self):
        plan = self._plan([self._item("i1", work_type_id="trockenbau")])
        result = self.dpl.auto_record_execution_productivity(
            session_id="sess-9", worker_id="42",
            plan=plan, item_results=[self._result("i1")], shift_hours=0.0,
        )
        self.assertEqual(result, [])


class ProductivityApiTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ['MINIAPP_DATA_ROOT'] = cls.tmp
        os.environ.setdefault('BOT_TOKEN', 'test')
        import main as backend
        cls.backend = backend

    def test_get_worker_productivity_self_allowed(self):
        """Worker can read their own productivity."""
        result = self.backend.get_worker_productivity_api(
            target_user_id="42",
            user={'id': 42},
            role='worker',
        )
        self.assertIn('aggregates', result)
        self.assertIn('observations', result)

    def test_get_worker_productivity_other_forbidden(self):
        """Worker cannot read another worker's productivity."""
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.backend.get_worker_productivity_api(
                target_user_id="99",
                user={'id': 42},
                role='worker',
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_get_worker_productivity_owner_can_read_any(self):
        """Owner can read any worker's productivity."""
        result = self.backend.get_worker_productivity_api(
            target_user_id="42",
            user={'id': 1},
            role='owner',
        )
        self.assertIn('aggregates', result)

    def test_set_baseline_negative_value_rejected(self):
        """Baseline must be > 0."""
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.backend.set_worker_baseline(
                target_user_id="42",
                work_type_id="trockenbau",
                baseline=-1.0,
                _=None,
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_set_baseline_valid(self):
        """Valid baseline sets manual_baseline_factor."""
        result = self.backend.set_worker_baseline(
            target_user_id="42",
            work_type_id="trockenbau",
            baseline=25.0,
            _=None,
        )
        self.assertEqual(result.get('manual_baseline_factor'), 25.0)
        self.assertEqual(result.get('work_type_id'), 'trockenbau')


if __name__ == '__main__':
    unittest.main()
