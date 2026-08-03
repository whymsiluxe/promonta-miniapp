"""03.08 (ТЗ Задача 3): worker не должен видеть assignment-метаданные коллег (team_note,
decline_reason, assignment_id, date_from/date_to, work_type, pending/declined статус) через
GET /api/objects -- только публичный список команды (user_id/name/has_avatar) + свои
собственные назначения целиком. Owner видит всё как раньше.

Тот же стиль, что tests/test_assignment_lifecycle.py -- list_objects() вызывается напрямую
с явным user/role, зависимости (_load_assignments и т.п.) мокаются через patch.object.

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_worker_object_privacy.py -v
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}
WORKER_A = {'id': 10, 'first_name': 'Ivan'}
WORKER_B = {'id': 20, 'first_name': 'Petr'}

OBJ_HEADER = ['ID объекта', 'Объект', 'Адрес', 'Статус']
OBJ_ROW = ['OBJ-1', 'Дом на Гауптштрассе', 'Hauptstr. 1', 'В работе']


def _assignment(uid, status='accepted', date_from='2026-08-01', date_to='2026-08-31', **extra):
    a = {
        'id': f'assign-{uid}', 'user_id': str(uid), 'status': status,
        'date_from': date_from, 'date_to': date_to,
        'task_note': f'secret note for {uid}', 'decline_reason': '',
        'work_type_id': 'tile_work',
    }
    a.update(extra)
    return a


def _mocked_context(assignments):
    """Общий набор patch.object для list_objects -- изолирует Google Sheets/JSON I/O."""
    fake_objekte_lib = MagicMock()
    fake_objekte_lib.all_stages_grouped.return_value = {}  # нет этапов -- _stage_summary() вернёт None
    return [
        patch.object(backend, '_cached_get_used_range', return_value=[OBJ_HEADER, OBJ_ROW]),
        patch.object(backend, '_load_assignments', return_value=assignments),
        patch.object(backend, '_load_worker_profiles', return_value={
            '10': {'name': 'Ivan'}, '20': {'name': 'Petr'},
        }),
        patch.object(backend, '_load_object_images', return_value={}),
        patch.object(backend, '_load_repo_objekte_lib', return_value=fake_objekte_lib),
    ]


class OwnerSeesFullAssignmentDtoTests(unittest.TestCase):
    def test_owner_gets_full_assignment_fields_for_every_worker(self):
        assignments = {'OBJ-1': [_assignment(10), _assignment(20, status='pending')]}
        ctxs = _mocked_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=OWNER, role='owner')
        finally:
            for c in ctxs:
                c.stop()
        obj = result['objects'][0]
        self.assertEqual(len(obj['assigned_users']), 2)
        for u in obj['assigned_users']:
            self.assertIn('assignment_id', u)
            self.assertIn('task_note', u)
            self.assertIn('decline_reason', u)
            self.assertIn('date_from', u)
            self.assertIn('date_to', u)
        self.assertNotIn('my_assignments', obj)  # owner-path не проходит через worker-serializer


class WorkerSeesBasicObjectFieldsTests(unittest.TestCase):
    def test_worker_sees_object_id_name_address_status(self):
        assignments = {'OBJ-1': [_assignment(10)]}
        ctxs = _mocked_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=WORKER_A, role='worker')
        finally:
            for c in ctxs:
                c.stop()
        obj = result['objects'][0]
        self.assertEqual(obj['ID объекта'], 'OBJ-1')
        self.assertEqual(obj['Объект'], 'Дом на Гауптштрассе')
        self.assertEqual(obj['Адрес'], 'Hauptstr. 1')
        self.assertEqual(obj['Статус'], 'В работе')
        self.assertIn('stage_summary', obj)
        self.assertIn('photo_count', obj)


class WorkerSeesOwnAssignmentFullyTests(unittest.TestCase):
    def test_worker_sees_own_assignment_including_pending(self):
        assignments = {'OBJ-1': [_assignment(10, status='pending', date_from='2026-09-01', date_to='2026-09-10')]}
        ctxs = _mocked_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=WORKER_A, role='worker')
        finally:
            for c in ctxs:
                c.stop()
        obj = result['objects'][0]
        self.assertEqual(len(obj['my_assignments']), 1)
        mine = obj['my_assignments'][0]
        self.assertEqual(mine['assignment_status'], 'pending')
        self.assertEqual(mine['date_from'], '2026-09-01')
        self.assertEqual(mine['task_note'], 'secret note for 10')

    def test_worker_own_future_assignment_visible(self):
        assignments = {'OBJ-1': [_assignment(10, status='pending', date_from='2099-01-01', date_to='2099-01-10')]}
        ctxs = _mocked_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=WORKER_A, role='worker')
        finally:
            for c in ctxs:
                c.stop()
        self.assertEqual(len(result['objects'][0]['my_assignments']), 1)


class WorkerDoesNotSeeColleagueMetadataTests(unittest.TestCase):
    def test_worker_does_not_see_colleague_assignment_fields(self):
        assignments = {'OBJ-1': [
            _assignment(10),
            _assignment(20, status='declined', decline_reason='болен'),
        ]}
        ctxs = _mocked_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=WORKER_A, role='worker')
        finally:
            for c in ctxs:
                c.stop()
        obj = result['objects'][0]
        colleague = next(u for u in obj['assigned_users'] if u['user_id'] == '20')
        self.assertNotIn('assignment_id', colleague)
        self.assertNotIn('task_note', colleague)
        self.assertNotIn('decline_reason', colleague)
        self.assertNotIn('date_from', colleague)
        self.assertNotIn('date_to', colleague)
        self.assertNotIn('assignment_status', colleague)
        self.assertNotIn('work_type_id', colleague)
        # Публичные поля остаются.
        self.assertIn('user_id', colleague)
        self.assertIn('name', colleague)
        self.assertIn('has_avatar', colleague)

    def test_worker_sees_public_team_list_for_all_assigned(self):
        assignments = {'OBJ-1': [_assignment(10), _assignment(20)]}
        ctxs = _mocked_context(assignments)
        for c in ctxs:
            c.start()
        try:
            result = backend.list_objects(user=WORKER_A, role='worker')
        finally:
            for c in ctxs:
                c.stop()
        obj = result['objects'][0]
        uids = {u['user_id'] for u in obj['assigned_users']}
        self.assertEqual(uids, {'10', '20'})


if __name__ == '__main__':
    unittest.main()
