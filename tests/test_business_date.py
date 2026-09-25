"""03.08 (доп.раунд, ТЗ Задача 5): business_now()/business_today()/business_today_str()
единая точка для Europe/Berlin "сегодня" -- проверяем поведение НА ГРАНИЦЕ полуночи
Europe/Berlin, где UTC и Berlin расходятся в дате (напр. 23:30 Berlin летом = 21:30 UTC,
но интереснее обратный случай: 01:30 Berlin = 23:30 UTC предыдущего дня -- date.today()
на UTC-сервере в этот момент вернул бы ВЧЕРАШНЮЮ дату).

freezegun не в зависимостях проекта (requirements-test.txt) -- время подменяется через
monkeypatch реальной функции business_now(), как и предписано в ТЗ.

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_business_date.py -v
"""
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402
import core.permissions as permissions  # noqa: E402
import assignment_matching as amatch  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}
WORKER_A = {'id': 10, 'first_name': 'Ivan'}

# 00:30 Europe/Berlin -- уже "завтра" по местному времени, но ещё "вчера" 22:30 UTC.
# Конкретная дата выбрана без DST-неоднозначности (не в переходные даты).
MIDNIGHT_EDGE_BERLIN = datetime(2026, 8, 4, 0, 30, tzinfo=ZoneInfo('Europe/Berlin'))
MIDNIGHT_EDGE_UTC_DATE = '2026-08-03'   # то, что вернул бы наивный date.today() на UTC-сервере
MIDNIGHT_EDGE_BERLIN_DATE = '2026-08-04'  # то, что должен вернуть business_today_str()


class BusinessNowHelpersTests(unittest.TestCase):
    def test_business_today_str_returns_berlin_date_at_midnight_edge(self):
        with patch.object(backend, 'business_now', return_value=MIDNIGHT_EDGE_BERLIN):
            self.assertEqual(backend.business_today_str(), MIDNIGHT_EDGE_BERLIN_DATE)

    def test_business_today_returns_date_object(self):
        with patch.object(backend, 'business_now', return_value=MIDNIGHT_EDGE_BERLIN):
            result = backend.business_today()
        self.assertEqual(result.isoformat(), MIDNIGHT_EDGE_BERLIN_DATE)

    def test_today_berlin_str_matches_business_today_str(self):
        # _today_berlin_str() -- существовавшая до этого раунда обёртка, теперь тонкий
        # алиас над business_today_str() -- has_active_object_access() продолжает
        # работать одинаково.
        with patch.object(backend, 'business_now', return_value=MIDNIGHT_EDGE_BERLIN):
            self.assertEqual(backend._today_berlin_str(), backend.business_today_str())


class AssignmentCandidateAvailabilityBoundaryTests(unittest.TestCase):
    """assignment_matching.py:availability_for_worker -- 'уже работает сегодня' проверка
    должна использовать Berlin-дату, не UTC."""

    def test_open_checkin_session_today_berlin_blocks_other_object(self):
        # Сессия помечена датой "2026-08-04" (Berlin-датой открытия смены). Если бы
        # availability_for_worker считал "сегодня" по UTC в момент MIDNIGHT_EDGE_BERLIN,
        # он бы решил, что сегодня ещё 2026-08-03, и period-проверка ниже не сработала
        # бы (session.date != "today") -- реальный найденный класс бага.
        #
        # availability_for_worker() делает локальный `import datetime` внутри функции --
        # это всегда резолвится через sys.modules['datetime'], так что патчим реальный
        # stdlib datetime.datetime (не 'assignment_matching.datetime', который local
        # import всё равно перезапишет своим собственным lookup).
        checkin_sessions = [{'user_id': '10', 'object_id': 'OBJ-OTHER', 'finish_at': None}]
        with patch('datetime.datetime') as mock_dt:
            mock_dt.now.return_value = MIDNIGHT_EDGE_BERLIN
            avail, reason = amatch.availability_for_worker(
                '10', MIDNIGHT_EDGE_BERLIN_DATE, MIDNIGHT_EDGE_BERLIN_DATE, 'OBJ-1',
                {}, [], checkin_sessions,
            )
        self.assertEqual(avail, 'unavailable')
        self.assertEqual(reason, 'Назначен на другой объект')


class ProfileStatsPeriodAggregateBoundaryTests(unittest.TestCase):
    def test_profile_stats_week_ring_uses_berlin_today(self):
        sessions = [{'user_id': '10', 'object_id': 'OBJ-1', 'date': MIDNIGHT_EDGE_BERLIN_DATE}]
        with patch.object(backend, 'business_now', return_value=MIDNIGHT_EDGE_BERLIN), \
             patch.object(backend, '_load_checkin_meta', return_value=sessions), \
             patch.object(backend, '_load_assignments', return_value={}), \
             patch.object(backend, '_cached_get_used_range', return_value=None), \
             patch.object(backend, '_load_abwesenheit', return_value=[]), \
             patch.object(backend, '_get_worker_profile', return_value={}), \
             patch.object(backend, '_get_worker_skills_v2', return_value=[]), \
             patch.object(backend, '_load_roles', return_value={'10': 'worker'}), \
             patch.object(backend, '_hours_from_session', return_value=8.0):
            result = backend.profile_stats(user_id='', period='week', user=WORKER_A, role='worker')
        # Последний день недельного кольца ("сегодня") обязан быть Berlin-датой,
        # не UTC-датой (которая на границе была бы на день раньше).
        self.assertEqual(result['week'][-1]['date'], MIDNIGHT_EDGE_BERLIN_DATE)
        self.assertEqual(result['week'][-1]['hours'], 8.0)


class StageCompletionDateBoundaryTests(unittest.TestCase):
    def test_worker_complete_stage_uses_berlin_date(self):
        with patch.object(backend, 'business_now', return_value=MIDNIGHT_EDGE_BERLIN), \
             patch.object(backend, '_load_repo_objekte_lib') as mock_lib:
            fake_o = mock_lib.return_value
            backend.worker_complete_stage('OBJ-1', 3, user=WORKER_A, _=None)
            called_date = fake_o.worker_complete_stage.call_args[0][3]
        self.assertEqual(called_date, MIDNIGHT_EDGE_BERLIN_DATE)


class DashboardTodayBoundaryTests(unittest.TestCase):
    def test_team_plan_defaults_to_berlin_today(self):
        fake_objekte_lib = MagicMock()
        fake_objekte_lib.all_stages_grouped.return_value = {}
        with patch.object(backend, 'business_now', return_value=MIDNIGHT_EDGE_BERLIN), \
             patch.object(backend, '_cached_get_used_range', return_value=None), \
             patch.object(backend, '_load_worker_profiles', return_value={}), \
             patch.object(backend, '_load_assignments', return_value={}), \
             patch.object(backend, '_load_roles', return_value={'1': 'owner'}), \
             patch.object(backend, '_load_checkin_meta', return_value=[]), \
             patch.object(backend, '_load_repo_objekte_lib', return_value=fake_objekte_lib):
            result = backend.get_team_plan(date='', user=OWNER, _=None)
        self.assertEqual(result['date'], MIDNIGHT_EDGE_BERLIN_DATE)

    def test_shifts_today_exposes_berlin_week_sparkline(self):
        sessions = [
            {'id': 's-prev', 'user_id': '10', 'object_id': 'OBJ-1', 'date': '2026-08-03',
             'manual_entry': True, 'start_time': '08:00', 'end_time': '10:00', 'pause_minutes': 0,
             'finish_at': 1},
            {'id': 's-today', 'user_id': '10', 'object_id': 'OBJ-1', 'date': MIDNIGHT_EDGE_BERLIN_DATE,
             'manual_entry': True, 'start_time': '08:00', 'end_time': '11:00', 'pause_minutes': 0,
             'finish_at': 1},
        ]
        with patch.object(backend, 'business_now', return_value=MIDNIGHT_EDGE_BERLIN), \
             patch.object(backend, '_load_checkin_meta', return_value=sessions), \
             patch.object(backend, '_load_worker_profiles', return_value={'10': {'name': 'Ivan'}}), \
             patch.object(backend, '_cached_get_used_range', return_value=None), \
             patch.object(backend, '_load_assignments', return_value={}), \
             patch.object(backend, '_load_abwesenheit', return_value=[]), \
             patch.object(backend, '_load_roles', return_value={'10': 'worker'}):
            result = backend.get_dashboard_shifts_today(user=OWNER, _=None)

        days = result['sparkline']['days']
        self.assertEqual(len(days), 7)
        self.assertEqual(days[-1]['date'], MIDNIGHT_EDGE_BERLIN_DATE)
        self.assertEqual(days[-1]['hours'], 3.0)
        self.assertEqual(days[-1]['shifts'], 1)
        self.assertEqual(days[-1]['finished'], 1)
        self.assertEqual(days[-2]['hours'], 2.0)


class EveningCutoffCheckTomorrowDateTests(unittest.TestCase):
    """22.09 iPhone screenshot audit, item A (P0): screenshot showed an owner
    alert reading 'План на 2026-09-22 ещё не опубликован на завтра' while
    viewed at 2026-09-22 23:30 Europe/Berlin -- at that moment 'завтра' must
    be 2026-09-23, not the same day. This pins the EXACT reported moment
    (not just an arbitrary midnight-edge instant like the rest of this file)
    and proves business_today()+1 day is correct there, isolating whether
    the screenshot was a live bug or an old, already-correctly-dated alert
    still sitting unread the next day (see docs/IPHONE_SCREENSHOT_AUDIT_*.md
    for the conclusion -- this test is the evidence, not the verdict)."""

    REPORTED_MOMENT = datetime(2026, 9, 22, 23, 30, 0, tzinfo=ZoneInfo('Europe/Berlin'))

    def test_business_today_at_reported_moment_is_the_22nd_not_the_23rd(self):
        with patch.object(backend, 'business_now', return_value=self.REPORTED_MOMENT):
            self.assertEqual(backend.business_today_str(), '2026-09-22')

    def test_tomorrow_computed_at_reported_moment_is_the_23rd(self):
        from datetime import timedelta
        with patch.object(backend, 'business_now', return_value=self.REPORTED_MOMENT):
            tomorrow = (backend.business_today() + timedelta(days=1)).strftime('%Y-%m-%d')
        self.assertEqual(tomorrow, '2026-09-23')

    def test_evening_cutoff_check_alert_dates_correctly_if_run_at_reported_moment(self):
        # If daily_plan_cutoff_check.py's evening mode were literally executed
        # AT 23:30 (not its actual 18:00 systemd schedule), the alert it
        # creates must say 2026-09-23, never 2026-09-22 -- proving the
        # date-computation logic itself has no off-by-one, regardless of
        # what time the check actually runs.
        import importlib.util
        import tempfile
        tmp = tempfile.mkdtemp(prefix='cutoff-evening-moment-')
        os.environ['MINIAPP_DATA_ROOT'] = tmp
        backend.ROLES_FILE = os.path.join(tmp, 'roles.json')
        backend.OBJECT_ASSIGNMENTS_FILE = os.path.join(tmp, 'object_assignments.json')
        backend.WORKER_PROFILES_FILE = os.path.join(tmp, 'worker_profiles.json')
        backend.CRITICAL_ALERTS_FILE = os.path.join(tmp, 'critical_alerts.json')
        backend._save_roles({'1': 'owner', '555': 'worker'})
        assignments = {'OBJ-1': [{
            'id': 'a-555', 'user_id': '555', 'status': 'accepted',
            'date_from': '2026-09-22', 'date_to': '2026-09-23',
        }]}
        backend._save_assignments(assignments)

        script_path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'daily_plan_cutoff_check.py')
        spec = importlib.util.spec_from_file_location('daily_plan_cutoff_check_moment', script_path)
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        script.STATE_FILE = os.path.join(tmp, 'daily_plan_cutoff_state.json')

        with patch.object(backend, 'business_now', return_value=self.REPORTED_MOMENT):
            rc = script.main('evening')
        self.assertEqual(rc, 0)

        alerts = backend._load_critical_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertIn('2026-09-23', alerts[0]['title'])
        self.assertNotIn('2026-09-22', alerts[0]['title'])


class AbwesenheitBusinessDateBoundaryTests(unittest.TestCase):
    """20.09: стор пишется через реальный временный файл, а не patch.object на
    _load/_save -- мутации ушли под update_json_transaction(), которая читает файл
    напрямую, мимо запатченного загрузчика."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp(prefix='abw-bizdate-')
        self._orig_file = backend.ABWESENHEIT_FILE
        backend.ABWESENHEIT_FILE = os.path.join(self._tmp, 'abwesenheit.json')

    def tearDown(self):
        backend.ABWESENHEIT_FILE = self._orig_file

    def _stored(self):
        import json
        with open(backend.ABWESENHEIT_FILE, encoding='utf-8') as f:
            return json.load(f)

    def test_close_abwesenheit_uses_berlin_business_today(self):
        backend._save_abwesenheit([{
            'id': 'abw-1', 'user_id': '10', 'name': 'Ivan',
            'date_from': '2026-08-01', 'date_to': '2026-08-31',
            'open_ended': True, 'status': 'approved',
        }])

        with patch.object(backend, 'business_now', return_value=MIDNIGHT_EDGE_BERLIN):
            result = backend.close_abwesenheit('abw-1', user=WORKER_A, role='worker')

        self.assertEqual(result['date_to'], MIDNIGHT_EDGE_BERLIN_DATE)
        self.assertFalse(result['open_ended'])
        self.assertEqual(self._stored()[0]['date_to'], MIDNIGHT_EDGE_BERLIN_DATE)

    def test_auto_close_open_ended_uses_berlin_business_today(self):
        backend._save_abwesenheit([{
            'id': 'abw-1', 'user_id': '10', 'name': 'Ivan',
            'date_from': MIDNIGHT_EDGE_UTC_DATE, 'date_to': MIDNIGHT_EDGE_UTC_DATE,
            'open_ended': True, 'status': 'approved',
        }])

        with patch.object(backend, 'business_now', return_value=MIDNIGHT_EDGE_BERLIN), \
             patch.object(backend, '_load_roles', return_value={'1': 'owner', '10': 'worker'}), \
             patch.object(backend, 'send_telegram_message'):
            backend._auto_close_expired_open_ended_abwesenheit()

        self.assertFalse(self._stored()[0]['open_ended'])


if __name__ == '__main__':
    unittest.main()
