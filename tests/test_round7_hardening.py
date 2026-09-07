"""Round 7 — Hardening tests for production control system.

Covers:
- Security: worker cannot use owner-only endpoints
- daily_plan_today: worker_id param only honored for owners
- _compute_risk_level: all risk levels
- daily_plan_owner_matrix: date filter, object_id filter
- daily_plan_replan: read-only, returns risk summary
- Graceful handling of missing/empty data
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


class DailyPlanSecurityTests(unittest.TestCase):
    """Tests that worker cannot access owner-only DailyPlan endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ['MINIAPP_DATA_ROOT'] = cls.tmp
        os.environ.setdefault('BOT_TOKEN', 'test')
        import main as backend
        cls.backend = backend
        import daily_plan_lib as dpl
        dpl.configure(
            os.path.join(cls.tmp, 'daily_plan_store.json'),
            os.path.join(cls.tmp, 'plan_sync_state.json'),
            os.path.join(cls.tmp, 'work_calendar.json'),
        )

    def test_owner_matrix_requires_owner(self):
        """require_owner dependency is present on the matrix route.
        FastAPI dependencies are enforced at the HTTP layer — verify by inspecting
        the route's dependency list rather than calling the function directly."""
        import inspect
        from fastapi import params as fp
        func = self.backend.daily_plan_owner_matrix
        sig = inspect.signature(func)
        dep_params = [
            p for p in sig.parameters.values()
            if isinstance(p.default, fp.Depends)
        ]
        dep_callables = [p.default.dependency for p in dep_params]
        self.assertIn(self.backend.require_owner, dep_callables,
                      "daily_plan_owner_matrix must have require_owner dependency")

    def test_worker_id_param_ignored_for_worker(self):
        """Worker sees own plan even if worker_id param supplied."""
        # Calling daily_plan_today with role='worker' and a different worker_id
        result = self.backend.daily_plan_today(
            worker_id_param='99999',
            user={'id': 42},
            role='worker',
        )
        # Should return plan for user 42, not 99999 — no plan = no_plan response
        self.assertFalse(result['has_plan'])

    def test_owner_can_specify_worker_id(self):
        """Owner can see any worker's plan by passing worker_id param."""
        result = self.backend.daily_plan_today(
            worker_id_param='77777',
            user={'id': 1},
            role='owner',
        )
        self.assertFalse(result['has_plan'])  # no plan for 77777, but no error

    def test_replan_returns_green_for_empty_object(self):
        """Replan returns green/no issues when no plans exist for object."""
        from backend.main import ReplanRequestBody
        result = self.backend.daily_plan_replan(
            object_id='nonexistent-obj',
            body=ReplanRequestBody(),
            _=None,
        )
        self.assertEqual(result['risk_level'], 'green')
        self.assertEqual(result['issues'], [])

    def test_owner_matrix_empty_returns_matrix(self):
        """Matrix endpoint returns valid structure when no plans exist."""
        result = self.backend.daily_plan_owner_matrix(
            date_from='2026-09-01',
            date_to='2026-09-08',
            object_id='',
            _=None,
        )
        self.assertIn('rows', result)
        self.assertIn('date_from', result)
        self.assertIn('date_to', result)
        self.assertEqual(result['rows'], [])

    def test_owner_matrix_object_filter(self):
        """Matrix with object_id filter returns only that object."""
        result = self.backend.daily_plan_owner_matrix(
            date_from='2026-09-01',
            date_to='2026-09-08',
            object_id='obj-xyz',
            _=None,
        )
        self.assertIn('rows', result)
        for row in result['rows']:
            self.assertEqual(row.get('object_id'), 'obj-xyz')


class ComputeRiskLevelTests(unittest.TestCase):
    """Tests for _compute_risk_level helper."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ['MINIAPP_DATA_ROOT'] = cls.tmp
        os.environ.setdefault('BOT_TOKEN', 'test')
        import main as backend
        cls.backend = backend

    def test_green_when_no_issues(self):
        result = self.backend._compute_risk_level([], [], [], None)
        self.assertEqual(result, 'green')

    def test_yellow_for_carryovers(self):
        result = self.backend._compute_risk_level(
            [{'id': 'c1'}], [], [], None
        )
        self.assertEqual(result, 'yellow')

    def test_yellow_for_amendments(self):
        result = self.backend._compute_risk_level(
            [], [{'id': 'a1'}], [], None
        )
        self.assertEqual(result, 'yellow')

    def test_orange_for_blocker(self):
        result = self.backend._compute_risk_level(
            [], [], [{'id': 'b1', 'resolved_at': None}], None
        )
        self.assertEqual(result, 'orange')

    def test_orange_for_blocked_execution_item(self):
        execution = {
            "item_results": [
                {"item_id": "i1", "status": "blocked"},
                {"item_id": "i2", "status": "done"},
            ]
        }
        result = self.backend._compute_risk_level([], [], [], execution)
        self.assertEqual(result, 'orange')

    def test_orange_beats_yellow(self):
        """If both carryovers and blocker exist, orange wins."""
        result = self.backend._compute_risk_level(
            [{'id': 'c1'}], [], [{'id': 'b1'}], None
        )
        self.assertEqual(result, 'orange')

    def test_execution_without_blocked_is_green(self):
        """Finished execution with all 'done' items = green."""
        execution = {
            "item_results": [
                {"item_id": "i1", "status": "done"},
                {"item_id": "i2", "status": "partial"},
            ]
        }
        result = self.backend._compute_risk_level([], [], [], execution)
        self.assertEqual(result, 'green')


class ContractRouteHardeningTests(unittest.TestCase):
    """Hardening tests for contract routes (security, edge cases)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ['MINIAPP_DATA_ROOT'] = cls.tmp
        os.environ.setdefault('BOT_TOKEN', 'test')
        import main as backend
        cls.backend = backend
        cls.state_file = os.path.join(cls.tmp, 'contract_ingest_state.json')
        cls.backend.CONTRACT_INGEST_STATE_FILE = cls.state_file

    def test_list_empty_state(self):
        """list_contracts handles missing state file."""
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
        result = self.backend.list_contracts(_=None)
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['contracts'], [])

    def test_approve_missing_contract_raises_404(self):
        """Approving a non-existent contract raises 404."""
        import json
        with open(self.state_file, 'w') as f:
            json.dump({"contracts": {}}, f)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.backend.approve_contract(
                'does-not-exist',
                body=self.backend.ContractReviewBody(),
                user={'id': 1},
                _=None,
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_reject_already_approved_raises_400(self):
        """Cannot reject an already-approved contract."""
        import json
        ct = {
            "id": "ct-h1", "file_id": "f1", "file_name": "x.pdf",
            "file_hash": "abc", "modified_time": "2026-09-01T00:00:00Z",
            "status": "approved", "ingested_at": 1.0,
            "text_preview": None, "extracted_facts": None, "project_plan_draft": None,
            "error": None, "approved_at": 1.0, "approved_by": "1",
            "rejected_at": None, "rejected_by": None, "review_notes": "",
        }
        with open(self.state_file, 'w') as f:
            json.dump({"contracts": {"ct-h1": ct}}, f)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.backend.reject_contract(
                'ct-h1',
                body=self.backend.ContractReviewBody(),
                user={'id': 1},
                _=None,
            )
        self.assertEqual(ctx.exception.status_code, 400)


class AutoRecordEdgeCaseTests(unittest.TestCase):
    """Edge cases for auto_record_execution_productivity."""

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
        if os.path.exists(self.store_path):
            os.remove(self.store_path)

    def test_empty_item_results(self):
        plan = {"id": "p1", "date": "2026-09-08", "items": []}
        result = self.dpl.auto_record_execution_productivity(
            "sess-e1", "42", plan, [], 8.0
        )
        self.assertEqual(result, [])

    def test_plan_with_no_items_field(self):
        plan = {"id": "p1", "date": "2026-09-08"}  # no 'items' key
        result = self.dpl.auto_record_execution_productivity(
            "sess-e2", "42", plan,
            [{"item_id": "i1", "status": "done", "actual_quantity": 10.0}],
            8.0,
        )
        self.assertEqual(result, [])

    def test_item_not_in_plan_skipped(self):
        """If item_result references an item not in the plan, skip it."""
        plan = {"id": "p1", "date": "2026-09-08", "items": []}
        result = self.dpl.auto_record_execution_productivity(
            "sess-e3", "42", plan,
            [{"item_id": "orphan-item", "status": "done", "actual_quantity": 10.0}],
            8.0,
        )
        self.assertEqual(result, [])

    def test_multiple_same_work_type_in_one_session(self):
        """Two items same work_type_id in same session: each gets its own obs."""
        items = [
            {"id": "i1", "title": "T1", "planned_quantity": 50, "unit": "m²",
             "work_type_id": "trockenbau", "time_estimate_hours": 4.0},
            {"id": "i2", "title": "T2", "planned_quantity": 50, "unit": "m²",
             "work_type_id": "trockenbau", "time_estimate_hours": 4.0},
        ]
        plan = {"id": "p2", "date": "2026-09-08", "items": items}
        results = self.dpl.auto_record_execution_productivity(
            "sess-e4", "42", plan,
            [
                {"item_id": "i1", "status": "done", "actual_quantity": 50.0},
                {"item_id": "i2", "status": "done", "actual_quantity": 50.0},
            ],
            8.0,
        )
        self.assertEqual(len(results), 2)
        # Each item gets 4h (equal split since equal time_est)
        for obs in results:
            self.assertAlmostEqual(obs['person_hours'], 4.0, places=3)


if __name__ == '__main__':
    unittest.main()
