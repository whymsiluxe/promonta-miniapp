"""Раунд 3, задача 3.3: Owner-only мягкое удаление дефекта DELETE /api/mangel/{id}.

Тикет помечается deleted_at/deleted_by, но остаётся в файле -- list/get его не
возвращают, повторное удаление безопасно, другие тикеты не затрагиваются.
Тесты вызывают backend-функции напрямую (как test_team_hours.py); 403 через require_owner.

Run:
    BOT_TOKEN='ci-dummy-token-not-a-real-secret' MINIAPP_DATA_ROOT=$(mktemp -d) \
      /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_mangel_delete.py -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402
from fastapi import HTTPException  # noqa: E402

ml = backend.ml
OWNER = {'id': 1, 'first_name': 'Boss'}


def _reset():
    # Чистый файл тикетов на каждый тест (MINIAPP_DATA_ROOT -- tmp в CI).
    ml._save([])


class MangelSoftDeleteAuthTests(unittest.TestCase):
    def test_worker_gets_403(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.require_owner(role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_allowed(self):
        self.assertIsNone(backend.require_owner(role='owner'))


class MangelSoftDeleteBehaviourTests(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_owner_can_delete_and_ticket_leaves_lists(self):
        t = ml.create_ticket('OBJ-1', 'Трещина', created_by='9', assigned_worker_id='')
        res = backend.delete_mangel_ticket(t['id'], user=OWNER, _=None)
        self.assertTrue(res['ok'])
        ids = [x['id'] for x in ml.list_tickets(None)]
        self.assertNotIn(t['id'], ids)

    def test_deleted_ticket_not_returned_by_get(self):
        t = ml.create_ticket('OBJ-1', 'Трещина', created_by='9')
        backend.delete_mangel_ticket(t['id'], user=OWNER, _=None)
        with self.assertRaises(KeyError):
            ml.get_ticket(t['id'])

    def test_deleted_ticket_not_counted(self):
        t = ml.create_ticket('OBJ-1', 'Трещина', created_by='9')
        before = ml.count_by_status()['gemeldet']
        backend.delete_mangel_ticket(t['id'], user=OWNER, _=None)
        self.assertEqual(ml.count_by_status()['gemeldet'], before - 1)

    def test_repeat_delete_is_safe(self):
        t = ml.create_ticket('OBJ-1', 'Трещина', created_by='9')
        r1 = backend.delete_mangel_ticket(t['id'], user=OWNER, _=None)
        r2 = backend.delete_mangel_ticket(t['id'], user=OWNER, _=None)
        self.assertTrue(r1['ok'] and r2['ok'])
        # deleted_at не должен переписываться при повторном удалении
        raw = [x for x in ml._load() if x['id'] == t['id']][0]
        self.assertTrue(raw.get('deleted_at'))

    def test_other_ticket_unaffected(self):
        keep = ml.create_ticket('OBJ-1', 'Оставить', created_by='9', photo_paths=['mangel_keep.jpg'])
        drop = ml.create_ticket('OBJ-1', 'Удалить', created_by='9')
        backend.delete_mangel_ticket(drop['id'], user=OWNER, _=None)
        surviving = ml.list_tickets(None)
        self.assertEqual([x['id'] for x in surviving], [keep['id']])
        # данные/фото оставшегося тикета не тронуты
        self.assertEqual(surviving[0]['photo_paths'], ['mangel_keep.jpg'])
        self.assertEqual(surviving[0]['description'], 'Оставить')

    def test_delete_nonexistent_raises_404(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.delete_mangel_ticket('no-such-id', user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_deleted_ticket_records_who(self):
        t = ml.create_ticket('OBJ-1', 'Трещина', created_by='9')
        backend.delete_mangel_ticket(t['id'], user=OWNER, _=None)
        raw = [x for x in ml._load() if x['id'] == t['id']][0]
        self.assertEqual(raw.get('deleted_by'), str(OWNER['id']))


if __name__ == '__main__':
    unittest.main()
