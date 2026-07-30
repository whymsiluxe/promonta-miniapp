"""Backend tests for План работ (Roadmap) -- data model, progress calc, status
transitions, dependency/permission logic, and the worker->owner stage-change
approval flow.

Same plain stdlib unittest approach as the rest of tests/ (no test framework
installed, see docs/TESTING.md) -- roadmap_lib.py functions are pure (take/return
plain dicts/lists), tested directly without needing a running server or signed
Telegram initData. Endpoint-level access/permission checks are tested the same way
test_owner_kt_requirements.py does it -- calling the route handler coroutine
directly with explicit kwargs.

Run:
    cd miniapp-repo && python3 -m unittest tests.test_roadmap -v
(same environment requirements as test_chat_backend.py: BOT_TOKEN in env, run with
the miniapp .venv's python3, not bare system python3.)
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import roadmap_lib as rl  # noqa: E402
import main as backend  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class CategoryItemCrudTests(unittest.TestCase):
    def setUp(self):
        self.store = rl._default_store()
        self.stage_key = 'OBJ-001-S1'

    def test_new_category_gets_incrementing_order(self):
        c1 = rl.new_category(self.store, self.stage_key, 'Подготовка')
        c2 = rl.new_category(self.store, self.stage_key, 'Работы')
        self.assertEqual(c1['order'], 1)
        self.assertEqual(c2['order'], 2)

    def test_new_item_defaults(self):
        item = rl.new_item(self.store, self.stage_key, 'Проверить основание')
        self.assertEqual(item['status'], 'open')
        self.assertTrue(item['required'])
        self.assertFalse(item['safety_critical'])
        self.assertEqual(item['weight'], 1)

    def test_delete_category_uncategorizes_its_items_not_delete_them(self):
        cat = rl.new_category(self.store, self.stage_key, 'Временная')
        item = rl.new_item(self.store, self.stage_key, 'Пункт', category_id=cat['id'])
        # Direct delete_category (bypassing main.py's "category must be empty" guard,
        # which is the actual enforcement point) -- verifying THIS function's own
        # contract: items survive, category_id becomes None, not silently dropped.
        rl.delete_category(self.store, self.stage_key, cat['id'])
        surviving = rl._find_item(self.store, self.stage_key, item['id'])
        self.assertIsNotNone(surviving)
        self.assertIsNone(surviving['category_id'])

    def test_delete_item_removes_only_that_item(self):
        i1 = rl.new_item(self.store, self.stage_key, 'A')
        i2 = rl.new_item(self.store, self.stage_key, 'B')
        rl.delete_item(self.store, self.stage_key, i1['id'])
        remaining_ids = [i['id'] for i in self.store['items'][self.stage_key]]
        self.assertNotIn(i1['id'], remaining_ids)
        self.assertIn(i2['id'], remaining_ids)

    def test_edit_item_only_touches_allowed_fields(self):
        item = rl.new_item(self.store, self.stage_key, 'Оригинал')
        rl.edit_item(self.store, self.stage_key, item['id'], title='Новое название', status='done')
        updated = rl._find_item(self.store, self.stage_key, item['id'])
        self.assertEqual(updated['title'], 'Новое название')
        # 'status' is not in edit_item's allowlist -- must go through update_item_status,
        # which enforces the completed_by/completed_at bookkeeping. Silent no-op here
        # is the correct contract (edit_item is for metadata, not workflow state).
        self.assertEqual(updated['status'], 'open')


class ItemStatusTransitionTests(unittest.TestCase):
    def setUp(self):
        self.store = rl._default_store()
        self.stage_key = 'OBJ-001-S1'
        self.item = rl.new_item(self.store, self.stage_key, 'Пункт')

    def test_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            rl.update_item_status(self.store, self.stage_key, self.item['id'], 'nonsense', 'u1')

    def test_done_sets_completed_by_and_at(self):
        updated = rl.update_item_status(self.store, self.stage_key, self.item['id'], 'done', 'worker-7')
        self.assertEqual(updated['completed_by'], 'worker-7')
        self.assertIsNotNone(updated['completed_at'])

    def test_reopen_clears_completion_fields(self):
        rl.update_item_status(self.store, self.stage_key, self.item['id'], 'done', 'worker-7')
        reopened = rl.update_item_status(self.store, self.stage_key, self.item['id'], 'open', 'owner-1')
        self.assertIsNone(reopened['completed_by'])
        self.assertIsNone(reopened['completed_at'])

    def test_missing_item_returns_none(self):
        self.assertIsNone(rl.update_item_status(self.store, self.stage_key, 'nonexistent', 'done', 'u1'))


class StageProgressTests(unittest.TestCase):
    """ТЗ п.15 -- прогресс считается по весам, required items влияют на review-
    готовность отдельно от общего процента."""

    def setUp(self):
        self.store = rl._default_store()
        self.stage_key = 'OBJ-001-S1'

    def test_empty_stage_has_zero_progress(self):
        progress = rl.stage_progress(self.store, self.stage_key)
        self.assertEqual(progress['percent'], 0)
        self.assertEqual(progress['total_weight'], 0)

    def test_weighted_progress_not_just_item_count(self):
        # Один тяжёлый (weight=5) и один лёгкий (weight=1) пункт -- если выполнен
        # только тяжёлый, процент должен быть намного выше 50% (не "1 из 2 = 50%").
        heavy = rl.new_item(self.store, self.stage_key, 'Заливка', weight=5)
        rl.new_item(self.store, self.stage_key, 'Мелочь', weight=1)
        rl.update_item_status(self.store, self.stage_key, heavy['id'], 'done', 'u1')
        progress = rl.stage_progress(self.store, self.stage_key)
        self.assertEqual(progress['completed_weight'], 5)
        self.assertEqual(progress['total_weight'], 6)
        self.assertGreater(progress['percent'], 80)

    def test_required_open_counts_only_required_incomplete_items(self):
        req_item = rl.new_item(self.store, self.stage_key, 'Обязательный', required=True)
        rl.new_item(self.store, self.stage_key, 'Опциональный', required=False)
        progress = rl.stage_progress(self.store, self.stage_key)
        self.assertEqual(progress['required_total'], 1)
        self.assertEqual(progress['required_open'], 1)
        rl.update_item_status(self.store, self.stage_key, req_item['id'], 'done', 'u1')
        progress = rl.stage_progress(self.store, self.stage_key)
        self.assertEqual(progress['required_open'], 0)

class NotesTests(unittest.TestCase):
    def test_stage_level_note_has_null_item_id(self):
        store = rl._default_store()
        note = rl.new_note(store, 'OBJ-001-S1', 'u1', 'Иван', 'Общая заметка по этапу')
        self.assertIsNone(note['item_id'])

    def test_notes_filtered_by_item_id(self):
        store = rl._default_store()
        stage_key = 'OBJ-001-S1'
        rl.new_note(store, stage_key, 'u1', 'Иван', 'Про этап целиком')
        rl.new_note(store, stage_key, 'u1', 'Иван', 'Про конкретный пункт', item_id='item-5')
        only_item = rl.stage_notes(store, stage_key, item_id='item-5')
        self.assertEqual(len(only_item), 1)
        self.assertEqual(only_item[0]['text'], 'Про конкретный пункт')
        all_notes = rl.stage_notes(store, stage_key)
        self.assertEqual(len(all_notes), 2)


class StageSnapshotTests(unittest.TestCase):
    def test_snapshot_is_single_read_with_everything_needed(self):
        # ТЗ п.47 -- "не делать отдельный запрос для каждого этапа": snapshot должен
        # содержать categories+items+progress+notes_count в одном вызове.
        store = rl._default_store()
        stage_key = 'OBJ-001-S1'
        cat = rl.new_category(store, stage_key, 'Подготовка')
        rl.new_item(store, stage_key, 'Пункт', category_id=cat['id'])
        rl.new_note(store, stage_key, 'u1', 'Иван', 'Заметка')
        snap = rl.stage_snapshot(store, stage_key)
        self.assertEqual(len(snap['categories']), 1)
        self.assertEqual(len(snap['items']), 1)
        self.assertEqual(snap['notes_count'], 1)
        self.assertIn('percent', snap['progress'])


class StageChangeRequestTests(unittest.TestCase):
    """Worker->owner approval flow -- delete/status-change этапа не применяется
    напрямую, а создаёт pending-запрос, который owner одобряет или отклоняет
    (owner decision, 29.07 -- 'через алерт', переиспользует critical_alerts)."""

    def test_new_request_starts_pending(self):
        requests = rl._default_requests()
        req = rl.new_stage_request(requests, 'OBJ-001', 'OBJ-001-S1', 3, 'delete_stage',
                                    'worker-1', 'Иван')
        self.assertEqual(req['status'], 'pending')
        self.assertIsNone(req['decided_at'])

    def test_rejects_unknown_kind(self):
        requests = rl._default_requests()
        with self.assertRaises(ValueError):
            rl.new_stage_request(requests, 'OBJ-001', 'OBJ-001-S1', 3, 'rename_stage',
                                  'worker-1', 'Иван')

    def test_decide_approve_marks_approved_with_decider(self):
        requests = rl._default_requests()
        req = rl.new_stage_request(requests, 'OBJ-001', 'OBJ-001-S1', 3, 'delete_stage',
                                    'worker-1', 'Иван')
        decided = rl.decide_stage_request(requests, req['id'], True, 'owner-1')
        self.assertEqual(decided['status'], 'approved')
        self.assertEqual(decided['decided_by'], 'owner-1')

    def test_decide_reject_marks_rejected(self):
        requests = rl._default_requests()
        req = rl.new_stage_request(requests, 'OBJ-001', 'OBJ-001-S1', 3, 'delete_stage',
                                    'worker-1', 'Иван')
        decided = rl.decide_stage_request(requests, req['id'], False, 'owner-1')
        self.assertEqual(decided['status'], 'rejected')

    def test_cannot_decide_same_request_twice(self):
        # Гонка/двойной клик owner -- второе решение по уже обработанному запросу
        # должно быть отклонено (None), не тихо перезаписывать первое.
        requests = rl._default_requests()
        req = rl.new_stage_request(requests, 'OBJ-001', 'OBJ-001-S1', 3, 'delete_stage',
                                    'worker-1', 'Иван')
        rl.decide_stage_request(requests, req['id'], True, 'owner-1')
        second = rl.decide_stage_request(requests, req['id'], False, 'owner-2')
        self.assertIsNone(second)

    def test_pending_requests_scoped_to_object(self):
        requests = rl._default_requests()
        rl.new_stage_request(requests, 'OBJ-001', 'OBJ-001-S1', 1, 'delete_stage', 'w1', 'A')
        rl.new_stage_request(requests, 'OBJ-002', 'OBJ-002-S1', 1, 'delete_stage', 'w1', 'A')
        only_obj1 = rl.pending_requests_for_object(requests, 'OBJ-001')
        self.assertEqual(len(only_obj1), 1)
        self.assertEqual(only_obj1[0]['object_id'], 'OBJ-001')

    def test_decided_requests_excluded_from_pending_list(self):
        requests = rl._default_requests()
        req = rl.new_stage_request(requests, 'OBJ-001', 'OBJ-001-S1', 1, 'delete_stage', 'w1', 'A')
        rl.decide_stage_request(requests, req['id'], True, 'owner-1')
        self.assertEqual(len(rl.pending_requests_for_object(requests, 'OBJ-001')), 0)


class RoadmapEndpointPermissionTests(unittest.TestCase):
    """Owner-only structural endpoints reject worker role -- calling the route
    handler coroutine directly, same style as test_owner_kt_requirements.py."""

    def test_create_category_requires_owner(self):
        with self.assertRaises(HTTPException) as ctx:
            run(backend.require_owner(role='worker'))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_role_passes_require_owner(self):
        # require_owner is a plain sync function (returns None on success, raises on
        # failure) -- called directly, not wrapped in run()/asyncio.run().
        backend.require_owner(role='owner')

    def test_worker_cannot_create_stage_request_as_owner_role(self):
        # create_stage_request explicitly rejects role='owner' with a 400 (owner
        # changes stages directly, no approval loop for themselves).
        body = backend.StageRequestBody(kind='delete_stage')
        with self.assertRaises(HTTPException) as ctx:
            run(backend.create_stage_request(
                object_id='OBJ-001', row_num=1, body=body,
                user={'id': 872079437}, role='owner', _=None,
            ))
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == '__main__':
    unittest.main()
