"""Tests for backend/daily_plan_cutoff_check.py -- the owner alert that fires
when a worker with an active object assignment for today still has no
published/accepted DailyPlan by the time the script runs (18.09, owner request:
the plan should arrive the evening before, this is a lagging-indicator alert
for the owner, not a start-time block on the worker -- checkin_start's freely-
allowed-without-a-plan behavior is intentionally untouched).
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


class DailyPlanCutoffCheckTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ['MINIAPP_DATA_ROOT'] = self.tmp
        os.environ.setdefault('BOT_TOKEN', 'test')

        import main as backend
        self.backend = backend
        # Re-point every store this test touches at the isolated tmp dir --
        # main.py module-level _FILE constants were computed at first import
        # (possibly by an earlier test) and won't auto-follow env var changes.
        self.backend.ROLES_FILE = os.path.join(self.tmp, 'roles.json')
        self.backend.OBJECT_ASSIGNMENTS_FILE = os.path.join(self.tmp, 'object_assignments.json')
        self.backend.WORKER_PROFILES_FILE = os.path.join(self.tmp, 'worker_profiles.json')
        self.backend.CRITICAL_ALERTS_FILE = os.path.join(self.tmp, 'critical_alerts.json')
        self.backend.CHAT_FILE = os.path.join(self.tmp, 'chat.json')

        import daily_plan_lib as dpl
        self.dpl = dpl
        dpl.configure(
            os.path.join(self.tmp, 'daily_plan_store.json'),
            os.path.join(self.tmp, 'plan_sync_state.json'),
            os.path.join(self.tmp, 'work_calendar.json'),
        )

        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'daily_plan_cutoff_check.py'
        )
        spec = importlib.util.spec_from_file_location('daily_plan_cutoff_check', script_path)
        self.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.script)
        self.script.STATE_FILE = os.path.join(self.tmp, 'daily_plan_cutoff_state.json')
        # main was already imported by this test (sys.modules cached) -- the
        # script's own `import main as backend` inside main() resolves to the
        # same cached module object, so pointing self.backend's _FILE
        # constants above is enough; no separate patching needed here.

        self.backend._save_roles({'1': 'owner', '555': 'worker'})

    def _assign(self, worker_id: str, object_id: str = 'OBJ-1', date_from='', date_to=''):
        assignments = self.backend._load_assignments()
        assignments.setdefault(object_id, []).append({
            'id': f'a-{worker_id}', 'user_id': worker_id, 'status': 'accepted',
            'date_from': date_from, 'date_to': date_to,
        })
        self.backend._save_assignments(assignments)

    def _publish_plan(self, worker_id: str, date_str: str):
        body = self.backend.DailyPlanIn(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date=date_str,
            assigned_worker_ids=[worker_id],
            items=[self.backend.DailyPlanItemIn(
                id='i1', sequence=1, title='Action', planned_quantity=1.0, unit='м²',
            )],
            publish=True,
        )
        self.backend.daily_plan_create(body=body, user={'id': 1})

    def test_no_owner_no_crash(self):
        self.backend._save_roles({'555': 'worker'})  # no owner
        self._assign('555')
        rc = self.script.main()
        self.assertEqual(rc, 0)
        alerts = self.backend._load_critical_alerts()
        self.assertEqual(alerts, [])

    def test_worker_with_no_plan_triggers_alert(self):
        self._assign('555')
        rc = self.script.main()
        self.assertEqual(rc, 0)
        alerts = self.backend._load_critical_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['kind'], 'plan_overdue')
        self.assertEqual(alerts[0]['target_user_id'], '1')

    def test_worker_with_published_plan_no_alert(self):
        self._assign('555')
        today = self.backend.business_today_str()
        self._publish_plan('555', today)
        rc = self.script.main()
        self.assertEqual(rc, 0)
        alerts = self.backend._load_critical_alerts()
        self.assertEqual(alerts, [])

    def test_unassigned_worker_does_not_trigger_alert(self):
        # No assignment at all for today -- e.g. worker never scheduled to work.
        rc = self.script.main()
        self.assertEqual(rc, 0)
        alerts = self.backend._load_critical_alerts()
        self.assertEqual(alerts, [])

    def test_assignment_outside_date_range_does_not_trigger_alert(self):
        self._assign('555', date_from='2020-01-01', date_to='2020-01-02')
        rc = self.script.main()
        self.assertEqual(rc, 0)
        alerts = self.backend._load_critical_alerts()
        self.assertEqual(alerts, [])

    def test_idempotent_second_run_same_day_no_duplicate_alert(self):
        self._assign('555')
        self.script.main()
        self.script.main()
        alerts = self.backend._load_critical_alerts()
        self.assertEqual(len(alerts), 1)

    def test_pending_assignment_does_not_trigger_alert(self):
        # Not yet accepted -- worker hasn't confirmed they're even working today.
        assignments = self.backend._load_assignments()
        assignments['OBJ-1'] = [{
            'id': 'a-555', 'user_id': '555', 'status': 'pending',
            'date_from': '', 'date_to': '',
        }]
        self.backend._save_assignments(assignments)
        rc = self.script.main()
        self.assertEqual(rc, 0)
        alerts = self.backend._load_critical_alerts()
        self.assertEqual(alerts, [])


if __name__ == '__main__':
    unittest.main()
