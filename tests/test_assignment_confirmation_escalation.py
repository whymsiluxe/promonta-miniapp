import os
import sys
import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402
import core.permissions as permissions  # noqa: E402


OWNER = {'id': '1'}
OBJ_ROWS = [
    ['ID объекта', 'Объект', 'Статус'],
    ['OBJ-1', 'Дом Мюллера', 'В работе'],
    ['OBJ-2', 'Склад', 'В работе'],
]


def _iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None).isoformat()


class AssignmentConfirmationEscalationTests(unittest.TestCase):
    def test_pending_assignment_thresholds_are_two_and_four_hours(self):
        now = 2_000_000

        fresh = backend._assignment_pending_escalation(
            {'status': 'pending', 'pending_since': _iso_utc(now - 7199)}, now_ts=now
        )
        warning = backend._assignment_pending_escalation(
            {'status': 'pending', 'pending_since': _iso_utc(now - 7200)}, now_ts=now
        )
        danger = backend._assignment_pending_escalation(
            {'status': 'pending', 'pending_since': _iso_utc(now - 14400)}, now_ts=now
        )
        accepted = backend._assignment_pending_escalation(
            {'status': 'accepted', 'pending_since': _iso_utc(now - 20000)}, now_ts=now
        )

        self.assertEqual(fresh['level'], '')
        self.assertEqual(warning['level'], 'warning')
        self.assertEqual(warning['type'], 'yellow')
        self.assertEqual(danger['level'], 'danger')
        self.assertEqual(danger['type'], 'red')
        self.assertEqual(accepted['level'], '')

    def test_owner_alerts_include_yellow_and_red_confirmation_escalations(self):
        now = int(time.time())
        assignments = {
            'OBJ-1': [
                {'id': 'warn', 'user_id': '10', 'status': 'pending',
                 'pending_since': _iso_utc(now - 3 * 3600), 'work_type_id': 'tile_work'},
                {'id': 'fresh', 'user_id': '10', 'status': 'pending',
                 'pending_since': _iso_utc(now - 30 * 60)},
            ],
            'OBJ-2': [
                {'id': 'danger', 'user_id': '20', 'status': 'pending',
                 'pending_since': _iso_utc(now - 5 * 3600), 'stage_id': 'Монтаж'},
                {'id': 'done', 'user_id': '20', 'status': 'accepted',
                 'pending_since': _iso_utc(now - 6 * 3600)},
            ],
        }
        with patch.object(backend, '_load_assignments', return_value=assignments), \
             patch.object(backend, '_load_worker_profiles', return_value={'10': {'name': 'Иван'}, '20': {'name': 'Мария'}}), \
             patch.object(backend, '_cached_get_used_range', return_value=OBJ_ROWS):
            alerts = backend._assignment_confirmation_alerts(now_ts=now)

        self.assertEqual(len(alerts), 2)
        by_id = {a['assignment_id']: a for a in alerts}
        self.assertEqual(by_id['warn']['type'], 'yellow')
        self.assertEqual(by_id['warn']['response_escalation'], 'warning')
        self.assertIn('Иван', by_id['warn']['title'])
        self.assertEqual(by_id['danger']['type'], 'red')
        self.assertEqual(by_id['danger']['response_escalation'], 'danger')
        self.assertIn('Склад', by_id['danger']['subtitle'])
        self.assertNotIn('fresh', by_id)
        self.assertNotIn('done', by_id)

    def test_get_alerts_surfaces_assignment_confirmation_for_owner(self):
        now = int(time.time())
        assignments = {'OBJ-1': [{'id': 'a1', 'user_id': '10', 'status': 'pending',
                                  'pending_since': _iso_utc(now - 4 * 3600 - 10)}]}
        with patch.object(backend.time, 'time', return_value=now), \
             patch.object(backend, '_load_assignments', return_value=assignments), \
             patch.object(backend, '_load_worker_profiles', return_value={'10': {'name': 'Иван'}}), \
             patch.object(backend, '_cached_get_used_range', return_value=OBJ_ROWS), \
             patch.object(backend, '_load_repo_objekte_lib', return_value=SimpleNamespace(get_budget_percent=lambda obj: 0)), \
             patch.object(backend, '_load_repo_tools_lib', side_effect=RuntimeError('tools unavailable')), \
             patch.object(backend, '_load_abwesenheit', return_value=[]), \
             patch.object(backend, '_load_tasks', return_value=[]), \
             patch.object(backend, '_load_critical_alerts', return_value=[]), \
             patch.object(backend, '_load_activity_alerts', return_value=[]), \
             patch.object(backend, '_load_alert_dismissals', return_value={}):
            alerts = backend.get_alerts(user=OWNER, role='owner')['alerts']

        confirmation = [a for a in alerts if a.get('assignment_confirmation')]
        self.assertEqual(len(confirmation), 1)
        self.assertEqual(confirmation[0]['type'], 'red')
        self.assertEqual(confirmation[0]['assignment_id'], 'a1')

    def test_dashboard_awaiting_response_includes_escalation_fields(self):
        now = int(time.time())
        assignments = {'OBJ-1': [{'id': 'a1', 'user_id': '10', 'status': 'pending',
                                  'pending_since': _iso_utc(now - 2 * 3600 - 60),
                                  'date_from': '2000-01-01', 'date_to': '2999-01-01',
                                  'task_note': 'закончить потолок'}]}
        with patch.object(backend.time, 'time', return_value=now), \
             patch.object(backend, '_load_checkin_meta', return_value=[]), \
             patch.object(backend, '_load_assignments', return_value=assignments), \
             patch.object(backend, '_load_worker_profiles', return_value={'10': {'name': 'Иван', 'skills': ['tile']}}), \
             patch.object(backend, '_cached_get_used_range', return_value=OBJ_ROWS), \
             patch.object(backend, '_load_abwesenheit', return_value=[]), \
             patch.object(backend, '_load_roles', return_value={'10': 'worker'}):
            payload = backend.get_dashboard_shifts_today(user=OWNER, _=None)

        self.assertEqual(len(payload['awaiting_response']), 1)
        row = payload['awaiting_response'][0]
        self.assertEqual(row['assignment_id'], 'a1')
        self.assertEqual(row['response_escalation'], 'warning')
        self.assertEqual(row['response_alert_type'], 'yellow')
        self.assertGreaterEqual(row['response_wait_seconds'], 2 * 3600)


if __name__ == '__main__':
    unittest.main()
