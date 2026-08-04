"""Раунд 5 §13/§14: статистика работника за период + CSV по диапазону + алерты ДР.

§13: get_worker_calendar_stats — days_worked (уникальные дни, активная смена не
дублируется), total_hours (с паузами), sick/vacation из одобренных отсутствий,
Owner видит любого / Worker только себя; CSV export принимает date_from/date_to.
§14: _check_upcoming_birthdays — «за 3 дня» и «в день рождения» с idempotency
(повторный вызов не плодит дубликаты).

Run:
    BOT_TOKEN='ci-dummy-token-not-a-real-secret' MINIAPP_DATA_ROOT=$(mktemp -d) \
      /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_worker_calendar_birthday.py -v
"""
import os
import sys
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402
from fastapi import HTTPException  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}
WORKER = {'id': 100, 'first_name': 'Ivan'}
OTHER = {'id': 200, 'first_name': 'Oleg'}


def _manual_session(uid, date, start, end, pause=0, obj='OBJ-1'):
    return {'user_id': str(uid), 'date': date, 'manual_entry': True,
            'start_time': start, 'end_time': end, 'pause_minutes': pause, 'object_id': obj}


class CalendarStatsTests(unittest.TestCase):
    def setUp(self):
        backend._save_checkin_meta([
            _manual_session(100, '2026-08-03', '08:00', '16:00'),           # 8ч
            _manual_session(100, '2026-08-04', '08:00', '16:30', pause=30),  # 8ч (пауза учтена)
            _manual_session(100, '2026-08-04', '17:00', '18:00'),           # тот же день -> уник. день один
            _manual_session(200, '2026-08-03', '08:00', '20:00'),           # другой работник
        ])
        backend._save_abwesenheit([
            {'user_id': '100', 'date_from': '2026-08-05', 'date_to': '2026-08-06',
             'reason': 'Krankheit', 'status': 'approved'},
            {'user_id': '100', 'date_from': '2026-08-10', 'date_to': '2026-08-12',
             'reason': 'Urlaub', 'status': 'approved'},
            {'user_id': '100', 'date_from': '2026-08-20', 'date_to': '2026-08-20',
             'reason': 'Urlaub', 'status': 'pending'},  # не одобрено -> не считается
        ])
        backend._save_worker_profiles({'100': {'name': 'Иван Петров'}})

    def test_days_worked_unique(self):
        s = backend.get_worker_calendar_stats('100', '2026-08-01', '2026-08-31', user=OWNER, role='owner')
        self.assertEqual(s['days_worked'], 2)  # 03 и 04, две сессии 04-го = один день

    def test_total_hours_with_pause(self):
        s = backend.get_worker_calendar_stats('100', '2026-08-01', '2026-08-31', user=OWNER, role='owner')
        # 8 + 8 + 1 = 17ч
        self.assertEqual(s['total_hours'], 17.0)

    def test_sick_and_vacation_counts(self):
        s = backend.get_worker_calendar_stats('100', '2026-08-01', '2026-08-31', user=OWNER, role='owner')
        self.assertEqual(s['sick_days'], 2)
        self.assertEqual(s['vacation_days'], 3)

    def test_range_excludes_outside(self):
        s = backend.get_worker_calendar_stats('100', '2026-08-04', '2026-08-04', user=OWNER, role='owner')
        self.assertEqual(s['days_worked'], 1)
        self.assertEqual(s['total_hours'], 9.0)

    def test_worker_self_allowed(self):
        s = backend.get_worker_calendar_stats('100', '2026-08-01', '2026-08-31', user=WORKER, role='worker')
        self.assertEqual(s['days_worked'], 2)

    def test_worker_other_403(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.get_worker_calendar_stats('100', '2026-08-01', '2026-08-31', user=OTHER, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_bad_dates_400(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.get_worker_calendar_stats('100', 'notadate', '2026-08-31', user=OWNER, role='owner')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_from_after_to_400(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.get_worker_calendar_stats('100', '2026-08-31', '2026-08-01', user=OWNER, role='owner')
        self.assertEqual(ctx.exception.status_code, 400)


class CsvRangeTests(unittest.TestCase):
    def setUp(self):
        backend._save_checkin_meta([_manual_session(100, '2026-08-04', '08:00', '16:00')])

    def test_csv_range_filename_has_dates(self):
        resp = backend.export_stundenzettel(
            user_id='100', date_from='2026-08-01', date_to='2026-08-31',
            user=OWNER, role='owner')
        cd = resp.headers['Content-Disposition']
        self.assertIn('2026-08-01_2026-08-31', cd)

    def test_csv_worker_other_403(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.export_stundenzettel(user_id='100', user=OTHER, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)


class BirthdayAlertTests(unittest.TestCase):
    def setUp(self):
        backend._save_birthday_alerts([])
        backend._save_roles({'1': 'owner', '100': 'worker'})

    def test_three_day_alert_created_and_idempotent(self):
        d3 = backend.business_today() + timedelta(days=3)
        backend._save_worker_profiles({'100': {'name': 'Иван', 'birthday': f'1990-{d3.month:02d}-{d3.day:02d}'}})
        backend._check_upcoming_birthdays()
        alerts = backend._load_birthday_alerts()
        keys = [a['idem'] for a in alerts]
        self.assertIn(f'birthday:100:{d3.year}:3days', keys)
        # повторный вызов не дублирует
        backend._check_upcoming_birthdays()
        alerts2 = backend._load_birthday_alerts()
        self.assertEqual(len(alerts2), len(alerts))

    def test_today_alert(self):
        today = backend.business_today()
        backend._save_worker_profiles({'100': {'name': 'Иван', 'birthday': f'1990-{today.month:02d}-{today.day:02d}'}})
        backend._check_upcoming_birthdays()
        keys = [a['idem'] for a in backend._load_birthday_alerts()]
        self.assertIn(f'birthday:100:{today.year}:today', keys)

    def test_no_alert_for_other_days(self):
        other = backend.business_today() + timedelta(days=40)
        backend._save_worker_profiles({'100': {'name': 'Иван', 'birthday': f'1990-{other.month:02d}-{other.day:02d}'}})
        backend._check_upcoming_birthdays()
        self.assertEqual(backend._load_birthday_alerts(), [])


if __name__ == '__main__':
    unittest.main()
