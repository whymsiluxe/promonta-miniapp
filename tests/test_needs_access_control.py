"""03.08 (ТЗ Задача 4): access control на Потребности (/api/tasks GET+POST) -- worker
должен иметь has_active_object_access(user_id, object_id), чтобы читать/создавать
потребность НА КОНКРЕТНОМ объекте. Owner -- доступ всегда. Запрос list_tasks() без
object_id (глобальный экран "мои потребности") НЕ трогается этой задачей.

Тот же стиль, что tests/test_object_access_and_checkin_photos.py.

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_needs_access_control.py -v
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}
WORKER_A = {'id': 10, 'first_name': 'Ivan'}


def _assignment(uid, status='accepted', date_from='2026-08-01', date_to='2026-08-31'):
    return {'user_id': str(uid), 'status': status, 'date_from': date_from, 'date_to': date_to}


class ListTasksAccessTests(unittest.TestCase):
    def test_active_worker_reads_object_tasks(self):
        assignments = {'OBJ-1': [_assignment(10)]}
        with patch.object(backend, '_load_assignments', return_value=assignments), \
             patch.object(backend, '_load_tasks', return_value=[]):
            result = backend.list_tasks(object_id='OBJ-1', user=WORKER_A, role='worker')
        self.assertEqual(result['tasks'], [])

    def test_worker_without_object_access_gets_403(self):
        with patch.object(backend, '_load_assignments', return_value={}):
            with self.assertRaises(HTTPException) as ctx:
                backend.list_tasks(object_id='OBJ-1', user=WORKER_A, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_future_assignment_denies_read_access(self):
        assignments = {'OBJ-1': [_assignment(10, date_from='2099-01-01', date_to='2099-01-10')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            with self.assertRaises(HTTPException) as ctx:
                backend.list_tasks(object_id='OBJ-1', user=WORKER_A, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_pending_assignment_denies_read_access(self):
        assignments = {'OBJ-1': [_assignment(10, status='pending')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            with self.assertRaises(HTTPException) as ctx:
                backend.list_tasks(object_id='OBJ-1', user=WORKER_A, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_declined_assignment_denies_read_access(self):
        assignments = {'OBJ-1': [_assignment(10, status='declined')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            with self.assertRaises(HTTPException) as ctx:
                backend.list_tasks(object_id='OBJ-1', user=WORKER_A, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_expired_assignment_denies_read_access(self):
        assignments = {'OBJ-1': [_assignment(10, date_from='2020-01-01', date_to='2020-01-10')]}
        with patch.object(backend, '_load_assignments', return_value=assignments):
            with self.assertRaises(HTTPException) as ctx:
                backend.list_tasks(object_id='OBJ-1', user=WORKER_A, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_always_has_read_access(self):
        with patch.object(backend, '_load_assignments', return_value={}), \
             patch.object(backend, '_load_tasks', return_value=[]):
            result = backend.list_tasks(object_id='OBJ-1', user=OWNER, role='owner')
        self.assertEqual(result['tasks'], [])

    def test_no_object_id_worker_sees_only_own_unaffected(self):
        # object_id не передан -- эта ветка НЕ трогается задачей 4, доступ не должен
        # требовать has_active_object_access вообще (глобальный "мои потребности").
        tasks = [{'from_user_id': '10', 'priority': 'обычная', 'created_at': 1}]
        with patch.object(backend, '_load_tasks', return_value=tasks):
            result = backend.list_tasks(object_id='', user=WORKER_A, role='worker')
        self.assertEqual(len(result['tasks']), 1)


class CreateTaskAccessTests(unittest.TestCase):
    def test_active_worker_creates_task(self):
        assignments = {'OBJ-1': [_assignment(10)]}
        body = backend.TaskCreateBody(title='Нужен цемент', object_id='OBJ-1')
        with patch.object(backend, '_load_assignments', return_value=assignments), \
             patch.object(backend, '_load_roles', return_value={'1': 'owner', '10': 'worker'}), \
             patch.object(backend, '_get_worker_profile', return_value={'name': 'Ivan'}), \
             patch.object(backend, '_load_tasks', return_value=[]), \
             patch.object(backend, '_save_tasks'), \
             patch.object(backend, 'send_telegram_message'):
            task = backend.create_task(body, user=WORKER_A, role='worker')
        self.assertEqual(task['object_id'], 'OBJ-1')

    def test_worker_without_object_access_cannot_create(self):
        body = backend.TaskCreateBody(title='Нужен цемент', object_id='OBJ-1')
        with patch.object(backend, '_load_assignments', return_value={}):
            with self.assertRaises(HTTPException) as ctx:
                backend.create_task(body, user=WORKER_A, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_pending_assignment_cannot_create(self):
        assignments = {'OBJ-1': [_assignment(10, status='pending')]}
        body = backend.TaskCreateBody(title='Нужен цемент', object_id='OBJ-1')
        with patch.object(backend, '_load_assignments', return_value=assignments):
            with self.assertRaises(HTTPException) as ctx:
                backend.create_task(body, user=WORKER_A, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_cannot_create_task_regardless_of_access(self):
        # Существующее поведение (не менять по спеке п.4) -- owner вообще не создаёт
        # Потребности, роль-проверка идёт РАНЬШЕ access-проверки.
        body = backend.TaskCreateBody(title='Нужен цемент', object_id='OBJ-1')
        with self.assertRaises(HTTPException) as ctx:
            backend.create_task(body, user=OWNER, role='owner')
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn('работники', ctx.exception.detail)


if __name__ == '__main__':
    unittest.main()
