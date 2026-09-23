"""Pause toggle -- server-authoritative timestamp semantics (hardening Этап 0.5, п.1).

Тот же стиль, что tests/test_chat_actions.py -- функции эндпоинтов вызываются
напрямую, _load_checkin_meta/_save_checkin_meta мокаются через patch.object.

Проверяет ровно то, что нашёл аудит фронтенда: сервер хранит pause_started_at
как unix-timestamp и на resume сворачивает прошедшее время в
pause_accumulated_seconds -- это единственный источник истины, не client-side
счётчик. Тест не про фронтенд-таймер (это UI-риск, отдельно закрыт в
checkin.js), а про то, что backend-контракт, на который таймер опирается,
не может тихо сломаться.

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m unittest tests.test_checkin_pause_authority -v
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}
WORKER = {'id': 10, 'first_name': 'Ivan'}
OTHER_WORKER = {'id': 20, 'first_name': 'Petr'}


def _session(session_id='S1', user_id=10, pause_started_at=None, pause_accumulated_seconds=0, finish_at=None):
    return {
        'id': session_id,
        'user_id': user_id,
        'object_id': 'OBJ-1',
        'start_at': 1000,
        'finish_at': finish_at,
        'pause_started_at': pause_started_at,
        'pause_accumulated_seconds': pause_accumulated_seconds,
    }


class PauseActionTests(unittest.TestCase):
    def test_first_tap_starts_pause_with_server_timestamp(self):
        session = _session()
        items = [session]
        with patch.object(backend, '_load_checkin_meta', return_value=items), \
             patch.object(backend, '_save_checkin_meta') as save_mock, \
             patch.object(backend.time, 'time', return_value=2000):
            result = backend.checkin_pause('S1', action='pause', user=WORKER, role='worker')

        self.assertTrue(result['paused'])
        self.assertTrue(result['changed'])
        self.assertEqual(session['pause_started_at'], 2000)
        self.assertEqual(session['pause_accumulated_seconds'], 0)
        save_mock.assert_called_once()

    def test_resume_action_folds_elapsed_into_accumulated_and_clears_started_at(self):
        # pause начата на t=2000, resume на t=2090 -> 90 секунд в accumulated
        session = _session(pause_started_at=2000, pause_accumulated_seconds=30)
        items = [session]
        with patch.object(backend, '_load_checkin_meta', return_value=items), \
             patch.object(backend, '_save_checkin_meta'), \
             patch.object(backend.time, 'time', return_value=2090):
            result = backend.checkin_pause('S1', action='resume', user=WORKER, role='worker')

        self.assertFalse(result['paused'])
        self.assertTrue(result['changed'])
        self.assertIsNone(session['pause_started_at'])
        self.assertEqual(session['pause_accumulated_seconds'], 120)  # 30 + 90
        self.assertEqual(result['pause_accumulated_seconds'], 120)
        self.assertEqual(result['pause_accumulated_minutes'], 2)

    def test_repeated_pause_action_keeps_original_started_at(self):
        session = _session()
        items = [session]
        with patch.object(backend, '_load_checkin_meta', return_value=items), \
             patch.object(backend, '_save_checkin_meta') as save_mock, \
             patch.object(backend.time, 'time', return_value=2000):
            first = backend.checkin_pause('S1', action='pause', user=WORKER, role='worker')
        self.assertTrue(first['changed'])
        self.assertEqual(session['pause_started_at'], 2000)

        save_mock.reset_mock()
        with patch.object(backend, '_load_checkin_meta', return_value=items), \
             patch.object(backend, '_save_checkin_meta') as save_again, \
             patch.object(backend.time, 'time', return_value=2050):
            second = backend.checkin_pause('S1', action='pause', user=WORKER, role='worker')

        self.assertTrue(second['paused'])
        self.assertFalse(second['changed'])
        self.assertEqual(session['pause_started_at'], 2000)
        save_again.assert_not_called()

    def test_repeated_resume_action_does_not_double_count_pause(self):
        session = _session(pause_started_at=2000, pause_accumulated_seconds=30)
        items = [session]
        with patch.object(backend, '_load_checkin_meta', return_value=items), \
             patch.object(backend, '_save_checkin_meta'), \
             patch.object(backend.time, 'time', return_value=2090):
            first = backend.checkin_pause('S1', action='resume', user=WORKER, role='worker')
        self.assertTrue(first['changed'])
        self.assertEqual(session['pause_accumulated_seconds'], 120)

        with patch.object(backend, '_load_checkin_meta', return_value=items), \
             patch.object(backend, '_save_checkin_meta') as save_again, \
             patch.object(backend.time, 'time', return_value=2200):
            second = backend.checkin_pause('S1', action='resume', user=WORKER, role='worker')

        self.assertFalse(second['paused'])
        self.assertFalse(second['changed'])
        self.assertEqual(session['pause_accumulated_seconds'], 120)
        save_again.assert_not_called()

    def test_owner_can_toggle_worker_session(self):
        session = _session(user_id=10)
        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_meta'):
            result = backend.checkin_pause('S1', action='pause', user=OWNER, role='owner')
        self.assertTrue(result['paused'])

    def test_worker_cannot_toggle_another_workers_session(self):
        session = _session(user_id=10)
        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_meta'):
            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_pause('S1', action='pause', user=OTHER_WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_finished_session_cannot_be_paused(self):
        session = _session(finish_at=5000)
        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_meta'):
            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_pause('S1', action='pause', user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_manual_entry_cannot_be_paused(self):
        # F01 (owner review commit db584ac, CHANGES REQUIRED): manual entries have
        # no finish_at, so the old finish_at-only check let a manual entry be
        # "paused" by its known session id -- it's not a photo shift at all.
        session = _session(finish_at=None)
        session['manual_entry'] = True
        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_meta') as save_mock:
            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_pause('S1', action='pause', user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 400)
        save_mock.assert_not_called()

    def test_missing_or_unknown_action_rejected_before_mutation(self):
        session = _session()
        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_meta') as save_mock:
            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_pause('S1', user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 400)
        save_mock.assert_not_called()

        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_meta') as save_mock:
            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_pause('S1', action='toggle', user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 400)
        save_mock.assert_not_called()

    def test_unknown_session_404(self):
        with patch.object(backend, '_load_checkin_meta', return_value=[]), \
             patch.object(backend, '_save_checkin_meta'):
            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_pause('missing', action='pause', user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == '__main__':
    unittest.main()
