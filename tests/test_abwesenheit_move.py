"""17.09 (audit follow-up): backend coverage for PATCH /api/abwesenheit/{entry_id}
(the move-date endpoint the Codex calendar/drag round added, verified against real
code before being finished off and shipped -- see docs/HANDOFF for context). No
existing test file covered this endpoint directly.

20.09 (merged from upstream c23894d): switched from patch.object(_load_abwesenheit/
_save_abwesenheit) to a real isolated store file. The endpoint now does its
read-modify-write inside update_json_transaction() (one lock, no lost updates),
which reads the file directly -- a patched _load_abwesenheit is simply not on that
path anymore. Writing a real temp file also makes these tests exercise the actual
persistence path instead of asserting against a fake save callback.
"""
import json
import os
import sys
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


class AbwesenheitLegacyIdMigrationTests(unittest.TestCase):
    """Этап 0.5 hardening (this branch, pre-existing): migration for legacy
    abwesenheit rows without an 'id' key, distinct from -- but closely related
    to -- the KeyError lookup bug upstream found and fixed below."""

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


class AbwesenheitMoveEndpointTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix='abw-move-')
        self._orig_file = backend.ABWESENHEIT_FILE
        backend.ABWESENHEIT_FILE = os.path.join(self._tmp, 'abwesenheit.json')

    def tearDown(self):
        backend.ABWESENHEIT_FILE = self._orig_file

    def _seed(self, items):
        backend._save_abwesenheit(items)

    def _stored(self):
        with open(backend.ABWESENHEIT_FILE, encoding='utf-8') as f:
            return json.load(f)

    def test_worker_can_move_own_entry_preserving_duration(self):
        self._seed([_entry()])
        body = backend.AbwesenheitMoveBody(date_from='2026-09-15')
        result = backend.update_abwesenheit_dates('abw-1', body, user=WORKER, role='worker')

        # original span was 2 days (10th to 12th) -- moving to 15th must keep that span
        self.assertEqual(result['date_from'], '2026-09-15')
        self.assertEqual(result['date_to'], '2026-09-17')
        self.assertEqual(self._stored()[0]['date_from'], '2026-09-15')

    def test_open_ended_entry_move_extends_to_month_end(self):
        self._seed([_entry(date_from='2026-09-10', date_to='2026-09-30', open_ended=True)])
        body = backend.AbwesenheitMoveBody(date_from='2026-10-05')
        result = backend.update_abwesenheit_dates('abw-1', body, user=WORKER, role='worker')

        self.assertEqual(result['date_from'], '2026-10-05')
        self.assertEqual(result['date_to'], '2026-10-31')

    def test_explicit_date_to_overrides_duration_preservation(self):
        self._seed([_entry()])
        body = backend.AbwesenheitMoveBody(date_from='2026-09-15', date_to='2026-09-20')
        result = backend.update_abwesenheit_dates('abw-1', body, user=WORKER, role='worker')
        self.assertEqual(result['date_to'], '2026-09-20')

    def test_other_worker_cannot_move_someone_elses_entry(self):
        self._seed([_entry()])
        with self.assertRaises(HTTPException) as ctx:
            body = backend.AbwesenheitMoveBody(date_from='2026-09-15')
            backend.update_abwesenheit_dates('abw-1', body, user=OTHER_WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)
        # rejected request must not have written anything
        self.assertEqual(self._stored()[0]['date_from'], '2026-09-10')

    def test_owner_can_move_any_workers_entry(self):
        self._seed([_entry()])
        body = backend.AbwesenheitMoveBody(date_from='2026-09-15')
        result = backend.update_abwesenheit_dates('abw-1', body, user=OWNER, role='owner')
        self.assertEqual(result['date_from'], '2026-09-15')

    def test_nonexistent_entry_404s(self):
        self._seed([])
        with self.assertRaises(HTTPException) as ctx:
            body = backend.AbwesenheitMoveBody(date_from='2026-09-15')
            backend.update_abwesenheit_dates('missing', body, user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_explicit_date_to_before_date_from_rejected(self):
        self._seed([_entry()])
        with self.assertRaises(HTTPException) as ctx:
            body = backend.AbwesenheitMoveBody(date_from='2026-09-20', date_to='2026-09-15')
            backend.update_abwesenheit_dates('abw-1', body, user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_invalid_date_format_rejected(self):
        self._seed([_entry()])
        with self.assertRaises(HTTPException) as ctx:
            body = backend.AbwesenheitMoveBody(date_from='not-a-date')
            backend.update_abwesenheit_dates('abw-1', body, user=WORKER, role='worker')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_legacy_entry_without_id_does_not_break_lookup(self):
        # 20.09 (live prod bug, merged from upstream c23894d): abwesenheit.json
        # holds legacy rows with no 'id' key at all. The lookup used i['id'], so
        # the generator raised KeyError on the first such row before ever
        # reaching the requested entry -- every single-entry operation 500'd
        # regardless of which entry was targeted.
        self._seed([
            {'user_id': '100', 'date_from': '2026-08-05', 'date_to': '2026-08-06',
             'reason': 'Krankheit', 'status': 'approved'},  # legacy, no 'id'
            _entry(),
        ])
        body = backend.AbwesenheitMoveBody(date_from='2026-09-15')
        result = backend.update_abwesenheit_dates('abw-1', body, user=WORKER, role='worker')
        self.assertEqual(result['date_from'], '2026-09-15')


if __name__ == '__main__':
    unittest.main()
