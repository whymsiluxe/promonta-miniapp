"""17.09 (audit follow-up): backend coverage for PATCH /api/abwesenheit/{entry_id}
(the move-date endpoint the Codex calendar/drag round added, verified against real
code before being finished off and shipped -- see docs/HANDOFF for context). No
existing test file covered this endpoint directly.

Same style as tests/test_business_date.py -- route handlers called directly,
patch.object on the real backend module.
"""
import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}
WORKER = {'id': 10, 'first_name': 'Ivan'}
OTHER_WORKER = {'id': 20, 'first_name': 'Petr'}


def _entry(**overrides):
    e = {
        'id': 'abw-1', 'user_id': '10', 'name': 'Ivan',
        'date_from': '2026-09-10', 'date_to': '2026-09-12',
        'open_ended': False, 'status': 'approved',
    }
    e.update(overrides)
    return e


class AbwesenheitMoveEndpointTests(unittest.TestCase):
    def test_legacy_entries_without_id_are_migrated_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'abwesenheit.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump([
                    {'user_id': '10', 'date_from': '2026-09-10', 'status': 'approved'},
                    {'id': 'keep-me', 'user_id': '20', 'date_from': '2026-09-11', 'status': 'pending'},
                ], f)

            with patch.object(backend, 'ABWESENHEIT_FILE', path):
                migrated = backend._migrate_abwesenheit_legacy_ids()
                migrated_again = backend._migrate_abwesenheit_legacy_ids()

            with open(path, encoding='utf-8') as f:
                items = json.load(f)

        self.assertEqual(migrated, 1)
        self.assertEqual(migrated_again, 0)
        self.assertTrue(items[0].get('id'))
        self.assertEqual(items[1]['id'], 'keep-me')

    def test_worker_can_move_own_entry_preserving_duration(self):
        entry = _entry()
        saved = {}

        def fake_save(items):
            saved['items'] = items

        with patch.object(backend, '_load_abwesenheit', return_value=[entry]), \
             patch.object(backend, '_save_abwesenheit', side_effect=fake_save):
            body = backend.AbwesenheitMoveBody(date_from='2026-09-15')
            result = backend.update_abwesenheit_dates('abw-1', body, user=WORKER, role='worker')

        # original span was 2 days (10th to 12th) -- moving to 15th must keep that span
        self.assertEqual(result['date_from'], '2026-09-15')
        self.assertEqual(result['date_to'], '2026-09-17')
        self.assertEqual(saved['items'][0]['date_from'], '2026-09-15')

    def test_open_ended_entry_move_extends_to_month_end(self):
        entry = _entry(date_from='2026-09-10', date_to='2026-09-30', open_ended=True)
        saved = {}

        def fake_save(items):
            saved['items'] = items

        with patch.object(backend, '_load_abwesenheit', return_value=[entry]), \
             patch.object(backend, '_save_abwesenheit', side_effect=fake_save):
            body = backend.AbwesenheitMoveBody(date_from='2026-10-05')
            result = backend.update_abwesenheit_dates('abw-1', body, user=WORKER, role='worker')

        self.assertEqual(result['date_from'], '2026-10-05')
        self.assertEqual(result['date_to'], '2026-10-31')

    def test_explicit_date_to_overrides_duration_preservation(self):
        entry = _entry()
        with patch.object(backend, '_load_abwesenheit', return_value=[entry]), \
             patch.object(backend, '_save_abwesenheit'):
            body = backend.AbwesenheitMoveBody(date_from='2026-09-15', date_to='2026-09-20')
            result = backend.update_abwesenheit_dates('abw-1', body, user=WORKER, role='worker')
        self.assertEqual(result['date_to'], '2026-09-20')

    def test_other_worker_cannot_move_someone_elses_entry(self):
        entry = _entry()
        with patch.object(backend, '_load_abwesenheit', return_value=[entry]):
            with self.assertRaises(HTTPException) as ctx:
                body = backend.AbwesenheitMoveBody(date_from='2026-09-15')
                backend.update_abwesenheit_dates('abw-1', body, user=OTHER_WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_can_move_any_workers_entry(self):
        entry = _entry()
        with patch.object(backend, '_load_abwesenheit', return_value=[entry]), \
             patch.object(backend, '_save_abwesenheit'):
            body = backend.AbwesenheitMoveBody(date_from='2026-09-15')
            result = backend.update_abwesenheit_dates('abw-1', body, user=OWNER, role='owner')
        self.assertEqual(result['date_from'], '2026-09-15')

    def test_nonexistent_entry_404s(self):
        with patch.object(backend, '_load_abwesenheit', return_value=[]):
            with self.assertRaises(HTTPException) as ctx:
                body = backend.AbwesenheitMoveBody(date_from='2026-09-15')
                backend.update_abwesenheit_dates('missing', body, user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_explicit_date_to_before_date_from_rejected(self):
        entry = _entry()
        with patch.object(backend, '_load_abwesenheit', return_value=[entry]):
            with self.assertRaises(HTTPException) as ctx:
                body = backend.AbwesenheitMoveBody(date_from='2026-09-20', date_to='2026-09-15')
                backend.update_abwesenheit_dates('abw-1', body, user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_invalid_date_format_rejected(self):
        entry = _entry()
        with patch.object(backend, '_load_abwesenheit', return_value=[entry]):
            with self.assertRaises(HTTPException) as ctx:
                body = backend.AbwesenheitMoveBody(date_from='not-a-date')
                backend.update_abwesenheit_dates('abw-1', body, user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == '__main__':
    unittest.main()
