import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402


WORKER = {'id': 10, 'first_name': 'Worker'}
OTHER_WORKER = {'id': 20, 'first_name': 'Other'}
OWNER = {'id': 1, 'first_name': 'Owner'}


def _manual_body(**overrides):
    data = {
        'object_id': 'OBJ-1',
        'art': 'Arbeitszeit',
        'date': '2026-09-22',
        'start_time': '08:00',
        'end_time': '16:00',
        'pause_minutes': 30,
        'description': 'Коррекция времени',
    }
    data.update(overrides)
    return backend.ZeiterfassungBody(**data)


class CheckinManualAndIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='checkin-manual-idem-')
        backend.CHECKIN_META_FILE = os.path.join(self.tmpdir, 'checkin_meta.json')
        backend.CHECKIN_IDEMPOTENCY_FILE = os.path.join(self.tmpdir, 'checkin_idempotency.json')
        backend.ROLES_FILE = os.path.join(self.tmpdir, 'roles.json')
        backend.OBJECT_ASSIGNMENTS_FILE = os.path.join(self.tmpdir, 'object_assignments.json')
        backend._idempotency_cache.clear()
        backend._save_roles({'1': 'owner', '10': 'worker', '20': 'worker'})
        backend._atomic_write_json(backend.OBJECT_ASSIGNMENTS_FILE, {
            'OBJ-1': [
                {'id': 'assign-10', 'user_id': '10', 'status': 'accepted', 'date_from': '2026-09-01', 'date_to': '2026-09-30'},
                {'id': 'assign-20', 'user_id': '20', 'status': 'accepted', 'date_from': '2026-09-01', 'date_to': '2026-09-30'},
            ],
        })

    def tearDown(self):
        backend._idempotency_cache.clear()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _object_rows(self):
        return [['ID объекта', 'Объект'], ['OBJ-1', 'Дом Мюллер']]

    def test_manual_time_does_not_block_next_photo_shift_start(self):
        with patch.object(backend, '_cached_get_used_range', return_value=self._object_rows()), \
             patch.object(backend, '_write_zeiterfassung_row'):
            manual = backend.checkin_manual(_manual_body(), user=WORKER, role='worker', idempotency_key='manual-1')

        save_photos = AsyncMock(return_value=['OBJ-1/2026-09-22/start.jpg'])
        with patch.object(backend, '_today_berlin_str', return_value='2026-09-22'), \
             patch.object(backend, '_save_checkin_photos', new=save_photos), \
             patch.object(backend, '_cached_get_used_range', return_value=self._object_rows()), \
             patch.object(backend, '_upsert_checkin_feed_post'):
            started = asyncio.run(backend.checkin_start(
                object_id='OBJ-1', lat='52.5', lon='13.4', accuracy='', geo_timestamp='',
                stage_name='', files=[MagicMock()], daily_plan_id='', daily_plan_version='',
                daily_plan_acceptance_id='', user=WORKER, role='worker', idempotency_key='start-1',
            ))
            backend._idempotency_cache.clear()
            replayed = asyncio.run(backend.checkin_start(
                object_id='OBJ-1', lat='52.5', lon='13.4', accuracy='', geo_timestamp='',
                stage_name='', files=[MagicMock()], daily_plan_id='', daily_plan_version='',
                daily_plan_acceptance_id='', user=WORKER, role='worker', idempotency_key='start-1',
            ))

        items = backend._load_checkin_meta()
        self.assertTrue(manual['manual_entry'])
        self.assertEqual(started['object_id'], 'OBJ-1')
        self.assertEqual(started['id'], replayed['id'])
        self.assertEqual(save_photos.await_count, 1)
        self.assertEqual(len(items), 2)
        self.assertEqual(len([s for s in items if backend._is_active_photo_checkin_session(s)]), 1)

    def test_manual_time_rejects_invalid_date_time_pause_and_missing_assignment(self):
        with patch.object(backend, '_cached_get_used_range', return_value=self._object_rows()):
            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_manual(_manual_body(pause_minutes=-1), user=WORKER, role='worker', idempotency_key='')
            self.assertEqual(ctx.exception.status_code, 400)

            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_manual(_manual_body(date='22.09.2026'), user=WORKER, role='worker', idempotency_key='')
            self.assertEqual(ctx.exception.status_code, 400)

            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_manual(_manual_body(start_time='16:00', end_time='08:00'), user=WORKER, role='worker', idempotency_key='')
            self.assertEqual(ctx.exception.status_code, 400)

            with self.assertRaises(HTTPException) as ctx:
                backend.checkin_manual(_manual_body(date='2026-08-31'), user=WORKER, role='worker', idempotency_key='')
            self.assertEqual(ctx.exception.status_code, 403)

    def test_manual_time_replays_same_key_without_duplicate_entry(self):
        with patch.object(backend, '_cached_get_used_range', return_value=self._object_rows()), \
             patch.object(backend, '_write_zeiterfassung_row') as write_row:
            first = backend.checkin_manual(_manual_body(), user=WORKER, role='worker', idempotency_key='manual-same')
            backend._idempotency_cache.clear()
            second = backend.checkin_manual(_manual_body(), user=WORKER, role='worker', idempotency_key='manual-same')

        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(backend._load_checkin_meta()), 1)
        write_row.assert_called_once()

    def test_idempotency_is_scoped_by_actor_endpoint_entity_and_payload(self):
        scope_worker = backend._idempotency_scope('checkin_start', WORKER['id'], 'OBJ-1', {'object_id': 'OBJ-1'})
        scope_other = backend._idempotency_scope('checkin_start', OTHER_WORKER['id'], 'OBJ-1', {'object_id': 'OBJ-1'})
        scope_other_payload = backend._idempotency_scope('checkin_start', WORKER['id'], 'OBJ-2', {'object_id': 'OBJ-2'})

        backend._idempotency_save('same-raw-key', {'ok': True, 'user_id': '10'}, scope_worker)
        backend._idempotency_cache.clear()

        self.assertIsNone(backend._idempotency_get('same-raw-key', scope_other))
        self.assertEqual(backend._idempotency_get('same-raw-key', scope_worker), {'ok': True, 'user_id': '10'})
        with self.assertRaises(HTTPException) as ctx:
            backend._idempotency_get('same-raw-key', scope_other_payload)
        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == '__main__':
    unittest.main()
