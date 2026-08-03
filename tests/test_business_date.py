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
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402
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
        with patch.object(backend, 'business_now', return_value=MIDNIGHT_EDGE_BERLIN), \
             patch.object(backend, '_cached_get_used_range', return_value=None), \
             patch.object(backend, '_load_worker_profiles', return_value={}), \
             patch.object(backend, '_load_assignments', return_value={}), \
             patch.object(backend, '_load_roles', return_value={'1': 'owner'}), \
             patch.object(backend, '_load_checkin_meta', return_value=[]):
            result = backend.get_team_plan(date='', user=OWNER, _=None)
        self.assertEqual(result['date'], MIDNIGHT_EDGE_BERLIN_DATE)


if __name__ == '__main__':
    unittest.main()
