"""Раунд1 Задача 1.6/6: GET /api/dashboard/team-hours -- часы всей команды за неделю
для экрана Команда → Сводка. owner-only, период Пн-Вс Europe/Berlin, идущая смена
считается один раз, pause вычитается, имя не Telegram ID, текущий объект корректен.

Тесты вызывают backend-функции напрямую (как test_business_date.py), патча loaders --
FastAPI Depends в юнит-тесте не исполняется, 403 проверяется через require_owner.

Run:
    BOT_TOKEN='ci-dummy-token-not-a-real-secret' MINIAPP_DATA_ROOT=$(mktemp -d) \
      /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_team_hours.py -v
"""
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402
from fastapi import HTTPException  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}

# Среда 05.08.2026, 12:00 Europe/Berlin. Неделя Пн-Вс = 03.08 .. 09.08.
NOW_BERLIN = datetime(2026, 8, 5, 12, 0, tzinfo=ZoneInfo('Europe/Berlin'))
NOW_TS = NOW_BERLIN.timestamp()
WEEK_FROM = '2026-08-03'
WEEK_TO = '2026-08-09'
TODAY = '2026-08-05'


def _call(date_from='', date_to=''):
    return backend.get_dashboard_team_hours(date_from=date_from, date_to=date_to, user=OWNER, _=None)


class TeamHoursAuthTests(unittest.TestCase):
    def test_worker_gets_403(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.require_owner(role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_allowed(self):
        self.assertIsNone(backend.require_owner(role='owner'))


class TeamHoursComputationTests(unittest.TestCase):
    def _patched(self, sessions, roles, profiles):
        return patch.multiple(
            backend,
            business_now=lambda: NOW_BERLIN,
            _load_roles=lambda: roles,
            _load_worker_profiles=lambda: profiles,
            _load_checkin_meta=lambda: sessions,
            _cached_get_used_range=lambda tab: None,
        )

    def test_default_period_is_current_monday_to_sunday_berlin(self):
        with self._patched([], {}, {}):
            r = _call()
        self.assertEqual(r['date_from'], WEEK_FROM)
        self.assertEqual(r['date_to'], WEEK_TO)

    def test_empty_week_valid_empty_response(self):
        with self._patched([], {'1': 'owner'}, {}):
            r = _call()
        self.assertEqual(r['workers'], [])
        self.assertEqual(r['total_hours'], 0)
        self.assertEqual(r['today_hours'], 0)
        self.assertEqual(r['workers_with_hours'], 0)

    def test_totals_pause_open_shift_name_and_current_object(self):
        # w10: manual Вт 08-16 pause 30 -> 7.5ч; открытая фото-смена сегодня 2ч на OBJ-1
        # w20: manual Пн 08-12 -> 4ч (не работает сейчас)
        # w30: без смен -> 0ч
        sessions = [
            {'user_id': '10', 'date': '2026-08-04', 'manual_entry': True,
             'start_time': '08:00', 'end_time': '16:00', 'pause_minutes': 30, 'object_id': 'OBJ-9'},
            {'user_id': '10', 'date': TODAY, 'start_at': NOW_TS - 7200,
             'finish_at': None, 'pause_accumulated_seconds': 0, 'object_id': 'OBJ-1'},
            {'user_id': '20', 'date': WEEK_FROM, 'manual_entry': True,
             'start_time': '08:00', 'end_time': '12:00', 'pause_minutes': 0, 'object_id': 'OBJ-2'},
        ]
        roles = {'1': 'owner', '10': 'worker', '20': 'worker', '30': 'worker'}
        profiles = {
            '10': {'name': 'Иван Петров', 'avatar': 'a.jpg'},
            '20': {},          # без имени -> не Telegram ID, а safe fallback
            '30': {'name': 'Олег'},
        }
        object_names = {'OBJ-1': 'Wohnung Müller'}
        with self._patched(sessions, roles, profiles), \
             patch.object(backend, '_cached_get_used_range',
                          return_value=[['ID объекта', 'Объект'], ['OBJ-1', 'Wohnung Müller']]), \
             patch('time.time', return_value=NOW_TS):
            r = _call()

        by_id = {w['user_id']: w for w in r['workers']}
        # w10: 7.5 (Вт manual) + 2.0 (открытая сегодня) = 9.5, сегодня 2.0, работает на OBJ-1
        self.assertAlmostEqual(by_id['10']['hours_week'], 9.5, places=1)
        self.assertAlmostEqual(by_id['10']['hours_today'], 2.0, places=1)
        self.assertTrue(by_id['10']['is_working_now'])
        self.assertEqual(by_id['10']['current_object_id'], 'OBJ-1')
        self.assertEqual(by_id['10']['current_object_name'], 'Wohnung Müller')
        self.assertTrue(by_id['10']['has_avatar'])
        # w20: 4ч, не работает, без часов сегодня
        self.assertAlmostEqual(by_id['20']['hours_week'], 4.0, places=1)
        self.assertEqual(by_id['20']['hours_today'], 0)
        self.assertFalse(by_id['20']['is_working_now'])
        # имя не голый Telegram ID -- safe fallback "Сотрудник"
        self.assertEqual(by_id['20']['name'], 'Сотрудник')
        self.assertNotEqual(by_id['20']['name'], '20')
        self.assertFalse(by_id['20']['has_avatar'])
        # w30: без часов -> 0
        self.assertEqual(by_id['30']['hours_week'], 0)
        # агрегаты
        self.assertAlmostEqual(r['total_hours'], 13.5, places=1)
        self.assertAlmostEqual(r['today_hours'], 2.0, places=1)
        self.assertEqual(r['workers_with_hours'], 2)
        # сортировка: работающий (10) первым, затем 20 (4ч), затем 30 (0ч)
        self.assertEqual([w['user_id'] for w in r['workers']], ['10', '20', '30'])

    def test_open_shift_counted_once_not_doubled(self):
        # Единственная открытая смена 3ч -> ровно 3ч, не 6 (не суммируется дважды).
        sessions = [{'user_id': '10', 'date': TODAY, 'start_at': NOW_TS - 10800,
                     'finish_at': None, 'pause_accumulated_seconds': 0, 'object_id': 'OBJ-1'}]
        with self._patched(sessions, {'10': 'worker'}, {'10': {'name': 'Иван'}}), \
             patch('time.time', return_value=NOW_TS):
            r = _call()
        self.assertAlmostEqual(r['workers'][0]['hours_week'], 3.0, places=1)
        self.assertAlmostEqual(r['total_hours'], 3.0, places=1)

    def test_owner_not_included_when_not_a_worker(self):
        sessions = [{'user_id': '1', 'date': TODAY, 'manual_entry': True,
                     'start_time': '08:00', 'end_time': '10:00', 'object_id': 'OBJ-1'}]
        with self._patched(sessions, {'1': 'owner', '10': 'worker'}, {'10': {'name': 'Иван'}}):
            r = _call()
        self.assertEqual([w['user_id'] for w in r['workers']], ['10'])

    def test_past_week_range_excludes_today_hours(self):
        # Явный прошлый диапазон -> сегодняшние смены не учитываются, is_working_now False.
        sessions = [{'user_id': '10', 'date': TODAY, 'start_at': NOW_TS - 3600,
                     'finish_at': None, 'pause_accumulated_seconds': 0, 'object_id': 'OBJ-1'}]
        with self._patched(sessions, {'10': 'worker'}, {'10': {'name': 'Иван'}}), \
             patch('time.time', return_value=NOW_TS):
            r = _call(date_from='2026-07-27', date_to='2026-08-02')
        w = r['workers'][0]
        self.assertEqual(w['hours_week'], 0)
        self.assertEqual(w['hours_today'], 0)
        self.assertFalse(w['is_working_now'])


if __name__ == '__main__':
    unittest.main()
