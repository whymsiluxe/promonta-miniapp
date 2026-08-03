"""03.08: has_active_object_access() единый helper для period-scoped доступа к объекту +
checkin_finish реальная проверка сохранённых фото (не переданных). Тот же стиль, что
tests/test_assignment_lifecycle.py.

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_object_access_and_checkin_photos.py -v
"""
import os
import sys
import unittest
import unittest.mock
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}
WORKER_A = {'id': 10, 'first_name': 'Ivan'}
WORKER_B = {'id': 20, 'first_name': 'Petr'}


def _assignment(uid, status='accepted', date_from='', date_to=''):
    return {'user_id': str(uid), 'status': status, 'date_from': date_from, 'date_to': date_to}


class HasActiveObjectAccessTests(unittest.TestCase):
    def test_owner_always_has_access(self):
        self.assertTrue(backend.can_access_object(OWNER, 'owner', 'OBJ-1'))

    def test_pending_before_period_no_object_access(self):
        assignments = {'OBJ-1': [_assignment('10', 'pending', '2026-09-01', '2026-09-10')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            self.assertFalse(backend.has_active_object_access('10', 'OBJ-1', today='2026-08-15'))

    def test_accepted_before_date_from_denied(self):
        assignments = {'OBJ-1': [_assignment('10', 'accepted', '2026-09-01', '2026-09-10')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            self.assertFalse(backend.has_active_object_access('10', 'OBJ-1', today='2026-08-31'))

    def test_accepted_on_first_day_allowed(self):
        assignments = {'OBJ-1': [_assignment('10', 'accepted', '2026-09-01', '2026-09-10')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            self.assertTrue(backend.has_active_object_access('10', 'OBJ-1', today='2026-09-01'))

    def test_accepted_on_last_day_allowed(self):
        assignments = {'OBJ-1': [_assignment('10', 'accepted', '2026-09-01', '2026-09-10')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            self.assertTrue(backend.has_active_object_access('10', 'OBJ-1', today='2026-09-10'))

    def test_accepted_after_date_to_denied(self):
        assignments = {'OBJ-1': [_assignment('10', 'accepted', '2026-09-01', '2026-09-10')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            self.assertFalse(backend.has_active_object_access('10', 'OBJ-1', today='2026-09-11'))

    def test_declined_no_access(self):
        assignments = {'OBJ-1': [_assignment('10', 'declined', '2026-08-01', '2026-08-31')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            self.assertFalse(backend.has_active_object_access('10', 'OBJ-1', today='2026-08-15'))

    def test_other_worker_assignment_does_not_grant_access(self):
        assignments = {'OBJ-1': [_assignment('20', 'accepted', '2026-08-01', '2026-08-31')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            self.assertFalse(backend.has_active_object_access('10', 'OBJ-1', today='2026-08-15'))

    def test_multiple_assignments_one_active_is_enough(self):
        assignments = {'OBJ-1': [
            _assignment('10', 'accepted', '2026-01-01', '2026-01-31'),  # истёк
            _assignment('10', 'accepted', '2026-08-01', '2026-08-31'),  # активен
        ]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            self.assertTrue(backend.has_active_object_access('10', 'OBJ-1', today='2026-08-15'))

    def test_legacy_assignment_without_dates_is_unbounded(self):
        assignments = {'OBJ-1': [_assignment('10', 'accepted', '', '')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            self.assertTrue(backend.has_active_object_access('10', 'OBJ-1', today='2026-08-15'))

    def test_no_assignment_no_access(self):
        with patch.object(backend, '_load_assignments', return_value={}):
            self.assertFalse(backend.has_active_object_access('10', 'OBJ-1', today='2026-08-15'))

    def test_today_defaults_to_berlin_when_not_passed(self):
        # today=None -> _today_berlin_str() -- не бросает, возвращает bool.
        with patch.object(backend, '_load_assignments', return_value={}):
            result = backend.has_active_object_access('10', 'OBJ-1')
        self.assertIsInstance(result, bool)


class CheckinFinishPhotoValidationTests(unittest.IsolatedAsyncioTestCase):
    def _session(self, session_id='s1', user_id='10'):
        return {'id': session_id, 'user_id': user_id, 'object_id': 'OBJ-1', 'date': '2026-08-15', 'finish_at': None}

    async def test_two_valid_photos_finish_succeeds(self):
        session = self._session()
        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_meta') as mock_save, \
             patch.object(backend, '_save_checkin_photos', return_value=['OBJ-1/2026-08-15/a.jpg', 'OBJ-1/2026-08-15/b.jpg']), \
             patch.object(backend, '_write_zeiterfassung_row'), \
             patch.object(backend, '_upsert_checkin_feed_post'), \
             patch.object(backend, '_load_worker_profiles', return_value={}), \
             patch.object(backend, '_cached_get_used_range', return_value=None), \
             patch.object(backend, '_idempotency_get', return_value=None), \
             patch.object(backend, '_idempotency_save'):
            fake_file = unittest.mock.MagicMock()
            result = await backend.checkin_finish(
                session_id='s1', lat='52.5', lon='13.4', done_summary='',
                extra_work='', extra_works='', needs='', defects='', next_day_needs='',
                pause_minutes=0, voice_note_file_id='', files=[fake_file, fake_file],
                user=WORKER_A, role='worker', idempotency_key='',
            )
        self.assertEqual(session['finish_at'], None if not mock_save.called else session['finish_at'])
        mock_save.assert_called_once()

    async def test_one_valid_one_corrupt_does_not_finish(self):
        session = self._session()
        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_meta') as mock_save, \
             patch.object(backend, '_save_checkin_photos', return_value=['OBJ-1/2026-08-15/a.jpg']), \
             patch.object(backend, '_cleanup_checkin_photo_files') as mock_cleanup, \
             patch.object(backend, '_idempotency_get', return_value=None):
            fake_file = unittest.mock.MagicMock()
            with self.assertRaises(HTTPException) as ctx:
                await backend.checkin_finish(
                    session_id='s1', lat='52.5', lon='13.4', done_summary='',
                    extra_work='', extra_works='', needs='', defects='', next_day_needs='',
                    pause_minutes=0, voice_note_file_id='', files=[fake_file, fake_file],
                    user=WORKER_A, role='worker', idempotency_key='',
                )
        self.assertEqual(ctx.exception.status_code, 400)
        mock_cleanup.assert_called_once_with(['OBJ-1/2026-08-15/a.jpg'])
        mock_save.assert_not_called()
        self.assertIsNone(session['finish_at'])

    async def test_two_corrupt_does_not_finish(self):
        session = self._session()
        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_meta') as mock_save, \
             patch.object(backend, '_save_checkin_photos', return_value=[]), \
             patch.object(backend, '_cleanup_checkin_photo_files') as mock_cleanup, \
             patch.object(backend, '_idempotency_get', return_value=None):
            fake_file = unittest.mock.MagicMock()
            with self.assertRaises(HTTPException) as ctx:
                await backend.checkin_finish(
                    session_id='s1', lat='52.5', lon='13.4', done_summary='',
                    extra_work='', extra_works='', needs='', defects='', next_day_needs='',
                    pause_minutes=0, voice_note_file_id='', files=[fake_file, fake_file],
                    user=WORKER_A, role='worker', idempotency_key='',
                )
        self.assertEqual(ctx.exception.status_code, 400)
        mock_cleanup.assert_called_once_with([])
        mock_save.assert_not_called()

    async def test_oversized_file_not_counted_as_saved(self):
        # _save_checkin_photos сама фильтрует по размеру -- проверяем что checkin_finish
        # доверяет её РЕАЛЬНОМУ возврату, не количеству входных files.
        session = self._session()
        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_meta') as mock_save, \
             patch.object(backend, '_save_checkin_photos', return_value=['OBJ-1/2026-08-15/a.jpg']), \
             patch.object(backend, '_cleanup_checkin_photo_files'), \
             patch.object(backend, '_idempotency_get', return_value=None):
            fake_file = unittest.mock.MagicMock()
            with self.assertRaises(HTTPException):
                await backend.checkin_finish(
                    session_id='s1', lat='52.5', lon='13.4', done_summary='',
                    extra_work='', extra_works='', needs='', defects='', next_day_needs='',
                    pause_minutes=0, voice_note_file_id='', files=[fake_file, fake_file],
                    user=WORKER_A, role='worker', idempotency_key='',
                )
        mock_save.assert_not_called()

    async def test_partial_failure_cleans_up_only_current_request_files(self):
        session = self._session()
        current_request_paths = ['OBJ-1/2026-08-15/new1.jpg']
        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_photos', return_value=current_request_paths), \
             patch.object(backend, '_cleanup_checkin_photo_files') as mock_cleanup, \
             patch.object(backend, '_idempotency_get', return_value=None):
            fake_file = unittest.mock.MagicMock()
            with self.assertRaises(HTTPException):
                await backend.checkin_finish(
                    session_id='s1', lat='52.5', lon='13.4', done_summary='',
                    extra_work='', extra_works='', needs='', defects='', next_day_needs='',
                    pause_minutes=0, voice_note_file_id='', files=[fake_file, fake_file],
                    user=WORKER_A, role='worker', idempotency_key='',
                )
        # cleanup вызван ровно с путями ЭТОГО запроса, не с чем-то ещё
        mock_cleanup.assert_called_once_with(current_request_paths)

    async def test_session_unchanged_on_photo_validation_failure(self):
        session = self._session()
        original_session = dict(session)
        with patch.object(backend, '_load_checkin_meta', return_value=[session]), \
             patch.object(backend, '_save_checkin_meta') as mock_save, \
             patch.object(backend, '_save_checkin_photos', return_value=[]), \
             patch.object(backend, '_cleanup_checkin_photo_files'), \
             patch.object(backend, '_idempotency_get', return_value=None):
            fake_file = unittest.mock.MagicMock()
            with self.assertRaises(HTTPException):
                await backend.checkin_finish(
                    session_id='s1', lat='52.5', lon='13.4', done_summary='',
                    extra_work='', extra_works='', needs='', defects='', next_day_needs='',
                    pause_minutes=0, voice_note_file_id='', files=[fake_file, fake_file],
                    user=WORKER_A, role='worker', idempotency_key='',
                )
        mock_save.assert_not_called()
        self.assertEqual(session, original_session)


class CleanupCheckinPhotoFilesTests(unittest.TestCase):
    def test_cleanup_removes_files_ignores_missing(self):
        with patch.object(backend.os, 'remove') as mock_remove:
            mock_remove.side_effect = [None, OSError()]
            backend._cleanup_checkin_photo_files(['a.jpg', 'b.jpg'])
        self.assertEqual(mock_remove.call_count, 2)

    def test_cleanup_empty_list_noop(self):
        with patch.object(backend.os, 'remove') as mock_remove:
            backend._cleanup_checkin_photo_files([])
        mock_remove.assert_not_called()


if __name__ == '__main__':
    unittest.main()
