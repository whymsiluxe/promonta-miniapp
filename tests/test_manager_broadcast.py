import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402


OWNER = {'id': '1', 'first_name': 'Борис'}


class ManagerBroadcastTests(unittest.TestCase):
    def test_company_broadcast_appends_group_chat_message(self):
        saved = {}

        def fake_save(messages):
            saved['messages'] = messages

        with patch.object(backend, '_load_chat', return_value=[]), \
             patch.object(backend, '_save_chat', side_effect=fake_save), \
             patch.object(backend, '_load_roles', return_value={'1': 'owner', '10': 'worker'}):
            result = backend.send_manager_broadcast(
                backend.BroadcastBody(scope='company', text='Завтра общий сбор в 8:00'),
                user=OWNER, _=None,
            )

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['thread_key'], 'group')
        self.assertEqual(result['audience_count'], 2)
        self.assertEqual(len(saved['messages']), 1)
        msg = saved['messages'][0]
        self.assertIsNone(msg['thread_key'])
        self.assertIsNone(msg['to_user_id'])
        self.assertEqual(msg['text'], 'Завтра общий сбор в 8:00')
        self.assertEqual(msg['broadcast']['scope'], 'company')

    def test_object_broadcast_appends_object_chat_and_history(self):
        saved = {}

        def fake_save(messages):
            saved['messages'] = messages

        with patch.object(backend, '_load_chat', return_value=[]), \
             patch.object(backend, '_save_chat', side_effect=fake_save), \
             patch.object(backend, '_find_object_row_by_id', return_value={'ID объекта': 'OBJ-1', 'Объект': 'Мюллер'}), \
             patch.object(backend, '_object_chat_participants', return_value=['1', '10', '20']), \
             patch.object(backend, '_append_object_history_best_effort') as history_mock:
            result = backend.send_manager_broadcast(
                backend.BroadcastBody(scope='object', object_id='OBJ-1', text='Берём лазер и защиту пола'),
                user=OWNER, _=None,
            )

        self.assertEqual(result['thread_key'], 'obj:OBJ-1')
        self.assertEqual(result['audience_count'], 3)
        msg = saved['messages'][0]
        self.assertEqual(msg['thread_key'], 'obj:OBJ-1')
        self.assertEqual(msg['broadcast']['object_name'], 'Мюллер')
        history_mock.assert_called_once()
        args, kwargs = history_mock.call_args
        self.assertEqual(args[:3], ('OBJ-1', 'broadcast_sent', 'Объявление отправлено'))
        self.assertIn('Берём лазер', kwargs['subtitle'])
        self.assertEqual(kwargs['meta']['message_id'], msg['id'])

    def test_object_broadcast_requires_existing_object(self):
        with patch.object(backend, '_find_object_row_by_id', return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                backend.send_manager_broadcast(
                    backend.BroadcastBody(scope='object', object_id='MISSING', text='Текст'),
                    user=OWNER, _=None,
                )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_broadcast_validates_scope_and_text(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.send_manager_broadcast(
                backend.BroadcastBody(scope='team', text='Привет'),
                user=OWNER, _=None,
            )
        self.assertEqual(ctx.exception.status_code, 400)

        with self.assertRaises(HTTPException) as empty_ctx:
            backend.send_manager_broadcast(
                backend.BroadcastBody(scope='company', text='   '),
                user=OWNER, _=None,
            )
        self.assertEqual(empty_ctx.exception.status_code, 400)

    def test_broadcast_route_registered_and_owner_only(self):
        route = next(route for route in backend.app.routes if route.path == '/api/manager/broadcast')
        dep_callables = {dep.call for dep in route.dependant.dependencies}
        self.assertIn(backend.require_owner, dep_callables)


if __name__ == '__main__':
    unittest.main()
