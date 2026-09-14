import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402


class ManagementCommandParserTests(unittest.TestCase):
    def test_russian_assignment_command_extracts_safe_draft(self):
        draft = backend.parse_management_command(
            'Поставь Ивану завтра задачу закончить потолок у Мюллера и скажи ему взять лазер.',
            base_dt=datetime(2026, 9, 14, 10, 0, 0),
            workers=[{'user_id': '42', 'name': 'Иван Петров'}],
            objects=[{'id': 'OBJ-MULLER', 'name': 'Дом Мюллера'}],
        )

        self.assertEqual(draft['intent'], 'assign_task')
        self.assertEqual(draft['worker_query'], 'Ивану')
        self.assertEqual(draft['worker_id'], '42')
        self.assertEqual(draft['worker_name'], 'Иван Петров')
        self.assertEqual(draft['date'], '2026-09-15')
        self.assertEqual(draft['object_query'], 'Мюллера')
        self.assertEqual(draft['object_id'], 'OBJ-MULLER')
        self.assertEqual(draft['task'], 'закончить потолок')
        self.assertEqual(draft['comment'], 'взять лазер')
        self.assertTrue(draft['requires_confirmation'])

    def test_parser_does_not_require_exact_resolution(self):
        draft = backend.parse_management_command(
            'Поставь Марии 20.09 задачу проверить материалы у склада',
            base_dt=datetime(2026, 9, 14, 10, 0, 0),
        )

        self.assertEqual(draft['date'], '2026-09-20')
        self.assertEqual(draft['worker_name'], 'Марии')
        self.assertEqual(draft['object_name'], 'склада')
        self.assertEqual(draft['task'], 'проверить материалы')
        self.assertEqual(draft['comment'], '')
        self.assertTrue(draft['requires_confirmation'])

    def test_endpoint_is_owner_only_and_returns_draft(self):
        body = backend.ManagementCommandBody(
            text='Поставь Ивану завтра задачу закончить потолок у Мюллера и скажи ему взять лазер.'
        )
        with patch.object(backend, '_management_workers_for_parse', return_value=[{'user_id': '42', 'name': 'Иван'}]), \
             patch.object(backend, '_management_objects_for_parse', return_value=[{'id': 'OBJ-1', 'name': 'Мюллера'}]):
            result = backend.parse_manager_command(body, user={'id': 1}, role='owner')

        self.assertTrue(result['requires_confirmation'])
        self.assertEqual(result['draft']['worker_id'], '42')
        self.assertEqual(result['draft']['object_id'], 'OBJ-1')

        with self.assertRaises(HTTPException) as ctx:
            backend.parse_manager_command(body, user={'id': 2}, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_route_registered(self):
        paths = {route.path for route in backend.app.routes}
        self.assertIn('/api/manager/command/parse', paths)


if __name__ == '__main__':
    unittest.main()
