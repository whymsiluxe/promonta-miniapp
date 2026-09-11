"""P0 assignment integrity fix regression tests (09.09.2026 evening, external
review after owner live screenshots showed the same worker rendered 2-3 times
on one object card, and appearing "assigned to another object at the same
time"). See main.py's list_objects/_assignment_periods_overlap/batch_assign/
assign_user/update_assignment comments for the full root-cause writeups this
covers.

Same style as test_assignment_lifecycle.py / test_worker_object_privacy.py --
route handlers called directly, patch.object on the real backend module.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}
_ROLES_10_20_WORKER = {'1': 'owner', '10': 'worker', '20': 'worker'}
_OBJ1_ROWS = [['ID объекта', 'Статус'], ['OBJ-1', 'В работе']]


def _today():
    return backend.business_today_str()


def _assignment(uid, work_type_id='tile_work', status='accepted', date_from=None, date_to=None, **extra):
    if date_from is None:
        date_from = _today()
    if date_to is None:
        date_to = _today()
    a = {
        'id': f'a-{uid}-{work_type_id}', 'user_id': str(uid), 'status': status,
        'work_type_id': work_type_id, 'date_from': date_from, 'date_to': date_to,
        'task_note': '', 'decline_reason': '',
    }
    a.update(extra)
    return a


def _list_objects_context(assignments):
    fake_objekte_lib = MagicMock()
    fake_objekte_lib.all_stages_grouped.return_value = {}
    return [
        patch.object(backend, '_load_assignments', return_value=assignments),
        patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS),
        patch.object(backend, '_load_repo_objekte_lib', return_value=fake_objekte_lib),
        patch.object(backend, '_load_worker_profiles', return_value={
            '10': {'name': 'Работник Десять'}, '20': {'name': 'Работник Двадцать'},
        }),
        patch.object(backend, '_load_object_images', return_value={}),
    ]


class ObjectCardTeamDedupTests(unittest.TestCase):
    def test_worker_with_multiple_work_types_shows_once_in_assigned_users(self):
        assignments = {'OBJ-1': [
            _assignment('10', work_type_id='tile_work'),
            _assignment('10', work_type_id='demolition'),
            _assignment('10', work_type_id='electrical'),
        ]}
        ctxs = _list_objects_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=OWNER, role='owner')
        finally:
            for c in ctxs:
                c.stop()
        obj = result['objects'][0]
        self.assertEqual(len(obj['assigned_users']), 1)
        self.assertEqual(obj['assigned_users'][0]['user_id'], '10')

    def test_underlying_assignment_records_are_not_touched(self):
        # dedup is display-only -- assigned_users_detail keeps all 3 records for
        # Object Info's "Команда и смены" to group under one worker row.
        assignments = {'OBJ-1': [
            _assignment('10', work_type_id='tile_work'),
            _assignment('10', work_type_id='demolition'),
            _assignment('10', work_type_id='electrical'),
        ]}
        ctxs = _list_objects_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=OWNER, role='owner')
        finally:
            for c in ctxs:
                c.stop()
        obj = result['objects'][0]
        self.assertEqual(len(obj['assigned_users_detail']), 3)
        work_types = {u['work_type_id'] for u in obj['assigned_users_detail']}
        self.assertEqual(work_types, {'tile_work', 'demolition', 'electrical'})

    def test_declined_assignment_not_shown_as_current_team(self):
        assignments = {'OBJ-1': [_assignment('10', status='declined')]}
        ctxs = _list_objects_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=OWNER, role='owner')
        finally:
            for c in ctxs:
                c.stop()
        obj = result['objects'][0]
        self.assertEqual(obj['assigned_users'], [])

    def test_past_dated_assignment_not_shown_as_current_team(self):
        import datetime
        past = (backend.business_today() - datetime.timedelta(days=30)).isoformat()
        assignments = {'OBJ-1': [_assignment('10', date_from=past, date_to=past)]}
        ctxs = _list_objects_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=OWNER, role='owner')
        finally:
            for c in ctxs:
                c.stop()
        obj = result['objects'][0]
        self.assertEqual(obj['assigned_users'], [])

    def test_future_dated_assignment_not_shown_as_current_team(self):
        import datetime
        future = (backend.business_today() + datetime.timedelta(days=30)).isoformat()
        assignments = {'OBJ-1': [_assignment('10', date_from=future, date_to=future)]}
        ctxs = _list_objects_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=OWNER, role='owner')
        finally:
            for c in ctxs:
                c.stop()
        obj = result['objects'][0]
        self.assertEqual(obj['assigned_users'], [])

    def test_legacy_undated_assignment_still_shown_as_current_team(self):
        # An assignment with no dates at all is treated as indefinite/always-active
        # everywhere else in this codebase (_assignment_status, the new
        # _assignment_periods_overlap) -- the card must show it too, not hide it.
        assignments = {'OBJ-1': [_assignment('10', date_from='', date_to='')]}
        ctxs = _list_objects_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=OWNER, role='owner')
        finally:
            for c in ctxs:
                c.stop()
        obj = result['objects'][0]
        self.assertEqual(len(obj['assigned_users']), 1)


class CrossObjectOverlapWithLegacyDataTests(unittest.TestCase):
    """_assignment_periods_overlap() must treat a legacy undated assignment as
    indefinite/always-conflicting for cross-object protection -- the plain
    _dates_overlap() used before this fix returned False whenever either side
    was undated, silently letting a worker get double-booked across objects.
    """

    def test_new_dated_assignment_blocked_by_existing_undated_legacy_on_other_object(self):
        # batch_assign raises 409 when EVERY requested pair got skipped (existing,
        # pre-existing behavior, not something this fix changes) -- with only one
        # user/work_type requested and it being blocked, that's exactly what
        # happens here. The real assertion is that it WAS blocked at all -- before
        # this fix, plain _dates_overlap() returned False for the undated legacy
        # side and this call would have succeeded instead of raising.
        existing = {'OBJ-1': [_assignment('10', date_from='', date_to='')]}
        with patch.object(backend, '_load_abwesenheit', return_value=[]), \
             patch.object(backend, '_cached_get_used_range', return_value=[
                 ['ID объекта', 'Статус'], ['OBJ-2', 'В работе']]), \
             patch.object(backend, '_load_roles', return_value=_ROLES_10_20_WORKER), \
             patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                self.captured = data
                return None
            mock_txn.side_effect = fake_txn
            body = backend.BatchAssignBody(
                user_ids=['10'], work_type_ids=['tile_work'],
                date_from=_today(), date_to=_today(),
            )
            with self.assertRaises(HTTPException) as ctx:
                backend.batch_assign('OBJ-2', body, user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 409)
        # OBJ-2 must remain empty -- nothing got created.
        self.assertEqual(self.captured.get('OBJ-2', []), [])

    def test_same_object_multiple_work_types_same_dates_allowed(self):
        # Multi-work-type on the SAME object/dates must remain allowed -- the
        # cross-object check must not accidentally block same-object siblings.
        existing = {'OBJ-1': [_assignment('10', work_type_id='tile_work')]}
        with patch.object(backend, '_load_abwesenheit', return_value=[]), \
             patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS), \
             patch.object(backend, '_load_roles', return_value=_ROLES_10_20_WORKER), \
             patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                return None
            mock_txn.side_effect = fake_txn
            body = backend.BatchAssignBody(
                user_ids=['10'], work_type_ids=['demolition'],
                date_from=_today(), date_to=_today(),
            )
            result = backend.batch_assign('OBJ-1', body, user=OWNER, _=None)
        self.assertEqual(len(result['created']), 1)
        self.assertEqual(result['skipped'], [])

    def test_non_overlapping_dated_assignments_on_different_objects_allowed(self):
        # Real owner data: same worker, OBJ-1 on one day, OBJ-3 the next -- not
        # an actual conflict, must remain allowed.
        import datetime
        tomorrow = (backend.business_today() + datetime.timedelta(days=1)).isoformat()
        existing = {'OBJ-1': [_assignment('10', date_from=_today(), date_to=_today())]}
        with patch.object(backend, '_load_abwesenheit', return_value=[]), \
             patch.object(backend, '_cached_get_used_range', return_value=[
                 ['ID объекта', 'Статус'], ['OBJ-3', 'В работе']]), \
             patch.object(backend, '_load_roles', return_value=_ROLES_10_20_WORKER), \
             patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                return None
            mock_txn.side_effect = fake_txn
            body = backend.BatchAssignBody(
                user_ids=['10'], work_type_ids=['tile_work'],
                date_from=tomorrow, date_to=tomorrow,
            )
            result = backend.batch_assign('OBJ-3', body, user=OWNER, _=None)
        self.assertEqual(len(result['created']), 1)
        self.assertEqual(result['skipped'], [])

    def test_single_assign_endpoint_also_blocked_by_undated_legacy(self):
        existing = {'OBJ-1': [_assignment('10', date_from='', date_to='')]}
        with patch.object(backend, '_load_abwesenheit', return_value=[]), \
             patch.object(backend, '_cached_get_used_range', return_value=[
                 ['ID объекта', 'Статус'], ['OBJ-2', 'В работе']]), \
             patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                return None
            mock_txn.side_effect = fake_txn
            body = backend.AssignBody(
                user_id='10', stage_id='Демонтаж',
                date_from=_today(), date_to=_today(),
            )
            with self.assertRaises(HTTPException) as ctx:
                backend.assign_user('OBJ-2', body, user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == '__main__':
    unittest.main()
