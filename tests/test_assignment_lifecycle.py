"""01.08: backend endpoints для onboarding v2, batch-назначения, точечного
PATCH/DELETE по assignment_id, owner-only verification, privacy. Тот же стиль,
что tests/test_release_audit2.py -- route handlers вызываются напрямую,
patch.object на реальный backend module (import main as backend).

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_assignment_lifecycle.py -v
"""
import os
import sys
import unittest
import unittest.mock
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}
WORKER_A = {'id': 10, 'first_name': 'Ivan'}
WORKER_B = {'id': 20, 'first_name': 'Petr'}


# ---------- Onboarding v2 validation ----------

class OnboardingCompletionValidationTests(unittest.TestCase):
    def test_cannot_complete_without_name(self):
        with patch.object(backend, '_load_worker_profiles', return_value={}), \
             patch.object(backend, '_save_worker_profiles'):
            body = backend.ProfileUpdateBody(
                skills_v2=[backend.SkillV2Body(skill_id='tile_work', level='independent')],
                onboarding_completed=True,
            )
            with self.assertRaises(HTTPException) as ctx:
                backend.update_my_profile(body, user=WORKER_A)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cannot_complete_without_skills(self):
        with patch.object(backend, '_load_worker_profiles', return_value={}), \
             patch.object(backend, '_save_worker_profiles'):
            body = backend.ProfileUpdateBody(name='Ivan', onboarding_completed=True)
            with self.assertRaises(HTTPException) as ctx:
                backend.update_my_profile(body, user=WORKER_A)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cannot_complete_without_level_for_each_skill(self):
        # skills_v2 без обязательного level -- Pydantic сам отклонит на уровне модели,
        # но проверим случай когда level передан пустым/некорректным явно.
        with patch.object(backend, '_load_worker_profiles', return_value={}), \
             patch.object(backend, '_save_worker_profiles'):
            body = backend.ProfileUpdateBody(
                name='Ivan',
                skills_v2=[backend.SkillV2Body(skill_id='tile_work', level='bogus_level')],
            )
            with self.assertRaises(HTTPException) as ctx:
                backend.update_my_profile(body, user=WORKER_A)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_worker_cannot_self_verify_skill(self):
        with patch.object(backend, '_load_worker_profiles', return_value={}), \
             patch.object(backend, '_save_worker_profiles'):
            body = backend.ProfileUpdateBody(
                name='Ivan',
                skills_v2=[backend.SkillV2Body(skill_id='tile_work', level='master', verified=True)],
                onboarding_completed=True,
            )
            result = backend.update_my_profile(body, user=WORKER_A)
        self.assertFalse(result['skills_v2'][0]['verified'])

    def test_complete_onboarding_with_all_requirements_succeeds(self):
        with patch.object(backend, '_load_worker_profiles', return_value={}), \
             patch.object(backend, '_save_worker_profiles'):
            body = backend.ProfileUpdateBody(
                name='Ivan',
                skills_v2=[backend.SkillV2Body(skill_id='tile_work', level='independent')],
                onboarding_completed=True,
            )
            result = backend.update_my_profile(body, user=WORKER_A)
        self.assertTrue(result['onboarding_completed'])
        self.assertEqual(result['onboarding_version'], 2)
        self.assertTrue(result['quiz_completed'])  # legacy-совместимость

    def test_existing_quiz_completed_user_not_blocked_by_v2(self):
        # get_my_profile: quiz_completed:true (старый флаг) должен считаться
        # завершённым онбордингом даже без onboarding_completed.
        profile = {'skills': ['Плитка'], 'quiz_completed': True, 'name': 'Old User'}
        with patch.object(backend, '_load_worker_profiles', return_value={'10': profile}), \
             patch.object(backend, '_save_worker_profiles'):
            result = backend.get_my_profile(user=WORKER_A)
        self.assertTrue(result['onboarding_completed'])

    def test_birthday_not_required_for_onboarding_completion(self):
        with patch.object(backend, '_load_worker_profiles', return_value={}), \
             patch.object(backend, '_save_worker_profiles'):
            body = backend.ProfileUpdateBody(
                name='Ivan',
                skills_v2=[backend.SkillV2Body(skill_id='tile_work', level='independent')],
                onboarding_completed=True,
            )
            # birthday не передан вообще -- должно пройти без ошибки
            result = backend.update_my_profile(body, user=WORKER_A)
        self.assertTrue(result['onboarding_completed'])


# ---------- Owner-only skill verification ----------

class SkillVerificationTests(unittest.TestCase):
    def test_owner_can_verify_skill(self):
        profile = {'skills_v2': [{'skill_id': 'tile_work', 'level': 'master', 'verified': False}]}
        with patch.object(backend, '_load_worker_profiles', return_value={'10': profile}), \
             patch.object(backend, '_save_worker_profiles'):
            result = backend.verify_worker_skill(
                '10', 'tile_work', backend.SkillVerificationBody(verified=True), user=OWNER, _=None,
            )
        self.assertTrue(result['verified'])

    def test_verify_nonexistent_skill_404(self):
        profile = {'skills_v2': []}
        with patch.object(backend, '_load_worker_profiles', return_value={'10': profile}):
            with self.assertRaises(HTTPException) as ctx:
                backend.verify_worker_skill(
                    '10', 'tile_work', backend.SkillVerificationBody(verified=True), user=OWNER, _=None,
                )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_verify_nonexistent_profile_404(self):
        with patch.object(backend, '_load_worker_profiles', return_value={}):
            with self.assertRaises(HTTPException) as ctx:
                backend.verify_worker_skill(
                    '999', 'tile_work', backend.SkillVerificationBody(verified=True), user=OWNER, _=None,
                )
        self.assertEqual(ctx.exception.status_code, 404)


# ---------- Batch assignment ----------

_OBJ1_ROWS = [['ID объекта', 'Статус'], ['OBJ-1', 'В работе']]
_OBJ1_COMPLETED_ROWS = [['ID объекта', 'Статус'], ['OBJ-1', 'Завершён']]
_ROLES_10_20_WORKER = {'10': 'worker', '20': 'worker'}


class BatchAssignmentTests(unittest.TestCase):
    def test_multiple_workers_get_distinct_assignment_ids(self):
        with patch.object(backend, '_load_abwesenheit', return_value=[]), \
             patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS), \
             patch.object(backend, '_load_roles', return_value=_ROLES_10_20_WORKER), \
             patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {}
                mutator(data)
                return None
            mock_txn.side_effect = fake_txn
            body = backend.BatchAssignBody(
                user_ids=['10', '20'], work_type_id='tile_work',
                date_from='2026-08-05', date_to='2026-08-16',
            )
            result = backend.batch_assign('OBJ-1', body, user=OWNER, _=None)
        self.assertEqual(len(result['created']), 2)
        ids = [c['assignment_id'] for c in result['created']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_duplicate_user_ids_deduplicated(self):
        with patch.object(backend, '_load_abwesenheit', return_value=[]), \
             patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS), \
             patch.object(backend, '_load_roles', return_value=_ROLES_10_20_WORKER), \
             patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {}
                mutator(data)
                return None
            mock_txn.side_effect = fake_txn
            body = backend.BatchAssignBody(
                user_ids=['10', '10', '10'], work_type_id='tile_work',
                date_from='2026-08-05', date_to='2026-08-16',
            )
            result = backend.batch_assign('OBJ-1', body, user=OWNER, _=None)
        self.assertEqual(len(result['created']), 1)

    def test_partial_result_when_some_skipped(self):
        existing = {'OBJ-1': [{'id': 'existing1', 'user_id': '20', 'work_type_id': 'tile_work',
                                'status': 'accepted', 'date_from': '2026-08-05', 'date_to': '2026-08-16'}]}
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
                user_ids=['10', '20'], work_type_id='tile_work',
                date_from='2026-08-05', date_to='2026-08-16',
            )
            result = backend.batch_assign('OBJ-1', body, user=OWNER, _=None)
        self.assertEqual(len(result['created']), 1)
        self.assertEqual(len(result['skipped']), 1)
        self.assertEqual(result['skipped'][0]['user_id'], '20')

    def test_no_assignments_created_returns_409(self):
        existing = {'OBJ-1': [{'id': 'existing1', 'user_id': '10', 'work_type_id': 'tile_work',
                                'status': 'accepted', 'date_from': '2026-08-05', 'date_to': '2026-08-16'}]}
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
                user_ids=['10'], work_type_id='tile_work',
                date_from='2026-08-05', date_to='2026-08-16',
            )
            with self.assertRaises(HTTPException) as ctx:
                backend.batch_assign('OBJ-1', body, user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_empty_user_ids_rejected(self):
        with patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS):
            body = backend.BatchAssignBody(user_ids=[], work_type_id='tile_work', date_from='2026-08-05', date_to='2026-08-16')
            with self.assertRaises(HTTPException) as ctx:
                backend.batch_assign('OBJ-1', body, user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_unknown_work_type_rejected(self):
        body = backend.BatchAssignBody(user_ids=['10'], work_type_id='not_a_real_skill', date_from='2026-08-05', date_to='2026-08-16')
        with self.assertRaises(HTTPException) as ctx:
            backend.batch_assign('OBJ-1', body, user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_date_from_after_date_to_rejected(self):
        with patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS):
            body = backend.BatchAssignBody(user_ids=['10'], work_type_id='tile_work', date_from='2026-08-16', date_to='2026-08-05')
            with self.assertRaises(HTTPException) as ctx:
                backend.batch_assign('OBJ-1', body, user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_nonexistent_object_rejected(self):
        with patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS):
            body = backend.BatchAssignBody(user_ids=['10'], work_type_id='tile_work', date_from='2026-08-05', date_to='2026-08-16')
            with self.assertRaises(HTTPException) as ctx:
                backend.batch_assign('OBJ-NONEXISTENT', body, user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_completed_object_rejected(self):
        with patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_COMPLETED_ROWS):
            body = backend.BatchAssignBody(user_ids=['10'], work_type_id='tile_work', date_from='2026-08-05', date_to='2026-08-16')
            with self.assertRaises(HTTPException) as ctx:
                backend.batch_assign('OBJ-1', body, user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_unknown_user_id_rejected(self):
        with patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS), \
             patch.object(backend, '_load_roles', return_value={}):
            body = backend.BatchAssignBody(user_ids=['999'], work_type_id='tile_work', date_from='2026-08-05', date_to='2026-08-16')
            with self.assertRaises(HTTPException) as ctx:
                backend.batch_assign('OBJ-1', body, user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_owner_user_id_rejected(self):
        with patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS), \
             patch.object(backend, '_load_roles', return_value={'1': 'owner'}):
            body = backend.BatchAssignBody(user_ids=['1'], work_type_id='tile_work', date_from='2026-08-05', date_to='2026-08-16')
            with self.assertRaises(HTTPException) as ctx:
                backend.batch_assign('OBJ-1', body, user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 400)


# ---------- Update/delete by assignment_id ----------

class PreciseAssignmentUpdateDeleteTests(unittest.TestCase):
    def test_delete_removes_only_target_assignment_id(self):
        existing = {'OBJ-1': [
            {'id': 'a1', 'user_id': '10', 'status': 'accepted'},
            {'id': 'a2', 'user_id': '10', 'status': 'accepted'},
        ]}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                self.captured = data
                return None
            mock_txn.side_effect = fake_txn
            backend.delete_assignment('OBJ-1', 'a1', user=OWNER, _=None)
        remaining_ids = [a['id'] for a in self.captured['OBJ-1']]
        self.assertEqual(remaining_ids, ['a2'])

    def test_delete_nonexistent_assignment_404(self):
        existing = {'OBJ-1': []}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                return None
            mock_txn.side_effect = fake_txn
            with self.assertRaises(HTTPException) as ctx:
                backend.delete_assignment('OBJ-1', 'nonexistent', user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_patch_updates_only_target_assignment(self):
        existing = {'OBJ-1': [
            {'id': 'a1', 'user_id': '10', 'status': 'accepted', 'task_note': 'old',
             'work_type_id': 'tile_work', 'date_from': '2026-08-05', 'date_to': '2026-08-16'},
            {'id': 'a2', 'user_id': '20', 'status': 'accepted', 'task_note': 'unchanged'},
        ]}
        with patch.object(backend, 'update_json_transaction') as mock_txn, \
             patch.object(backend, '_load_roles', return_value=_ROLES_10_20_WORKER), \
             patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS), \
             patch.object(backend, '_load_abwesenheit', return_value=[]):
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                self.captured = data
                return None
            mock_txn.side_effect = fake_txn
            body = backend.AssignmentUpdateBody(task_note='new note')
            backend.update_assignment('OBJ-1', 'a1', body, user=OWNER, _=None)
        a1 = next(a for a in self.captured['OBJ-1'] if a['id'] == 'a1')
        a2 = next(a for a in self.captured['OBJ-1'] if a['id'] == 'a2')
        self.assertEqual(a1['task_note'], 'new note')
        self.assertEqual(a2['task_note'], 'unchanged')

    def test_patch_on_accepted_assignment_resets_to_pending(self):
        existing = {'OBJ-1': [{'id': 'a1', 'user_id': '10', 'status': 'accepted', 'responded_at': 'sometime',
                                'work_type_id': 'tile_work', 'date_from': '2026-08-05', 'date_to': '2026-08-16'}]}
        with patch.object(backend, 'update_json_transaction') as mock_txn, \
             patch.object(backend, '_load_roles', return_value=_ROLES_10_20_WORKER), \
             patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS), \
             patch.object(backend, '_load_abwesenheit', return_value=[]):
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                self.captured = data
                return None
            mock_txn.side_effect = fake_txn
            body = backend.AssignmentUpdateBody(date_from='2026-09-01', date_to='2026-09-05')
            backend.update_assignment('OBJ-1', 'a1', body, user=OWNER, _=None)
        a1 = self.captured['OBJ-1'][0]
        self.assertEqual(a1['status'], 'pending')
        self.assertEqual(a1['responded_at'], '')

    def test_patch_noop_does_not_reset_accepted(self):
        # 01.08 (доп.раунд П6): PATCH с теми же значениями, что уже сохранены,
        # НЕ должен сбрасывать accepted -> pending.
        existing = {'OBJ-1': [{'id': 'a1', 'user_id': '10', 'status': 'accepted', 'responded_at': 'sometime',
                                'work_type_id': 'tile_work', 'date_from': '2026-08-05', 'date_to': '2026-08-16',
                                'task_note': 'same'}]}
        with patch.object(backend, 'update_json_transaction') as mock_txn, \
             patch.object(backend, '_load_roles', return_value=_ROLES_10_20_WORKER), \
             patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS), \
             patch.object(backend, '_load_abwesenheit', return_value=[]):
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                self.captured = data
                return None
            mock_txn.side_effect = fake_txn
            body = backend.AssignmentUpdateBody(task_note='same', work_type_id='tile_work',
                                                  date_from='2026-08-05', date_to='2026-08-16')
            backend.update_assignment('OBJ-1', 'a1', body, user=OWNER, _=None)
        a1 = self.captured['OBJ-1'][0]
        self.assertEqual(a1['status'], 'accepted')
        self.assertEqual(a1['responded_at'], 'sometime')

    def test_patch_excludes_current_assignment_from_overlap_check(self):
        # 01.08 (доп.раунд П6): проверка пересечений должна исключать САМО это
        # назначение -- иначе PATCH любого accepted/pending назначения на себя же
        # ложно 409-ил бы (оно всегда "пересекается" само с собой).
        existing = {'OBJ-1': [{'id': 'a1', 'user_id': '10', 'status': 'accepted',
                                'work_type_id': 'tile_work', 'date_from': '2026-08-05', 'date_to': '2026-08-16'}]}
        with patch.object(backend, 'update_json_transaction') as mock_txn, \
             patch.object(backend, '_load_roles', return_value=_ROLES_10_20_WORKER), \
             patch.object(backend, '_cached_get_used_range', return_value=_OBJ1_ROWS), \
             patch.object(backend, '_load_abwesenheit', return_value=[]):
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                return None
            mock_txn.side_effect = fake_txn
            body = backend.AssignmentUpdateBody(task_note='updated')
            result = backend.update_assignment('OBJ-1', 'a1', body, user=OWNER, _=None)
        self.assertEqual(result['status'], 'ok')

    def test_patch_unknown_work_type_rejected(self):
        existing = {'OBJ-1': [{'id': 'a1', 'user_id': '10', 'status': 'pending'}]}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                return None
            mock_txn.side_effect = fake_txn
            body = backend.AssignmentUpdateBody(work_type_id='not_a_real_skill')
            with self.assertRaises(HTTPException) as ctx:
                backend.update_assignment('OBJ-1', 'a1', body, user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_old_delete_by_user_id_with_multiple_active_returns_409(self):
        existing = {'OBJ-1': [
            {'id': 'a1', 'user_id': '10', 'status': 'accepted'},
            {'id': 'a2', 'user_id': '10', 'status': 'pending'},
        ]}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                return None
            mock_txn.side_effect = fake_txn
            with self.assertRaises(HTTPException) as ctx:
                backend.unassign_user('OBJ-1', '10', user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_old_delete_by_user_id_with_single_active_still_works(self):
        existing = {'OBJ-1': [{'id': 'a1', 'user_id': '10', 'status': 'accepted'}]}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                self.captured = data
                return None
            mock_txn.side_effect = fake_txn
            result = backend.unassign_user('OBJ-1', '10', user=OWNER, _=None)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(self.captured['OBJ-1'], [])

    def test_delete_does_not_touch_other_workers_assignments(self):
        # 01.08 (доп.раунд, реальный найденный баг): старая версия фильтровала
        # "активные" по ВСЕМ user_id на объекте -- DELETE для worker A мог 409-ить
        # из-за активного назначения worker B, а при "одном активном" (не именно
        # A) стирал ВСЕ записи, включая B. Теперь строго изолировано по user_id.
        existing = {'OBJ-1': [
            {'id': 'a1', 'user_id': '10', 'status': 'accepted'},
            {'id': 'a2', 'user_id': '20', 'status': 'accepted'},
        ]}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                self.captured = data
                return None
            mock_txn.side_effect = fake_txn
            result = backend.unassign_user('OBJ-1', '10', user=OWNER, _=None)
        self.assertEqual(result['status'], 'ok')
        remaining_ids = [a['id'] for a in self.captured['OBJ-1']]
        self.assertEqual(remaining_ids, ['a2'])  # worker 20 не тронут

    def test_delete_no_active_assignment_404(self):
        existing = {'OBJ-1': [{'id': 'a1', 'user_id': '10', 'status': 'declined'}]}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                return None
            mock_txn.side_effect = fake_txn
            with self.assertRaises(HTTPException) as ctx:
                backend.unassign_user('OBJ-1', '10', user=OWNER, _=None)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_delete_does_not_remove_declined_records(self):
        existing = {'OBJ-1': [
            {'id': 'a1', 'user_id': '10', 'status': 'accepted'},
            {'id': 'a2', 'user_id': '10', 'status': 'declined'},
        ]}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                self.captured = data
                return None
            mock_txn.side_effect = fake_txn
            backend.unassign_user('OBJ-1', '10', user=OWNER, _=None)
        remaining_ids = [a['id'] for a in self.captured['OBJ-1']]
        self.assertEqual(remaining_ids, ['a2'])  # declined осталась

    def test_delete_legacy_record_without_id_does_not_wipe_other_worker(self):
        # 03.08 (реальный найденный баг): legacy-записи (созданные до введения поля
        # id) не имеют 'id' вообще -- старая логика искала target_id = None и
        # `a.get('id') != None` удаляла ВСЕ записи с реальным id, включая других
        # работников. Две legacy-записи без id, разные работники -- удаление A не
        # должно тронуть B.
        existing = {'OBJ-1': [
            {'user_id': '10', 'status': 'accepted'},  # legacy, без id
            {'user_id': '20', 'status': 'accepted'},  # legacy, другой работник, без id
        ]}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                self.captured = data
                return None
            mock_txn.side_effect = fake_txn
            result = backend.unassign_user('OBJ-1', '10', user=OWNER, _=None)
        self.assertEqual(result['status'], 'ok')
        remaining = self.captured['OBJ-1']
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]['user_id'], '20')  # worker B не тронут

    def test_delete_legacy_record_mixed_with_id_records_other_worker(self):
        # Смешанный случай: legacy-запись без id у одного работника, обычная запись
        # с id у другого -- удаление legacy-записи не должно задеть запись с id.
        existing = {'OBJ-1': [
            {'user_id': '10', 'status': 'accepted'},  # legacy, без id
            {'id': 'a2', 'user_id': '20', 'status': 'accepted'},
        ]}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                self.captured = data
                return None
            mock_txn.side_effect = fake_txn
            backend.unassign_user('OBJ-1', '10', user=OWNER, _=None)
        remaining = self.captured['OBJ-1']
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].get('id'), 'a2')


# ---------- Privacy ----------

class CandidatesPrivacyTests(unittest.TestCase):
    def test_candidates_response_has_no_absence_note_field(self):
        with patch.object(backend, '_load_roles', return_value={'10': 'worker'}), \
             patch.object(backend, '_load_worker_profiles', return_value={'10': {
                 'name': 'Ivan', 'skills_v2': [{'skill_id': 'tile_work', 'level': 'master', 'verified': True}],
             }}), \
             patch.object(backend, '_load_assignments', return_value={}), \
             patch.object(backend, '_load_abwesenheit', return_value=[
                 {'user_id': '10', 'status': 'approved', 'date_from': '2026-08-01', 'date_to': '2026-08-20',
                  'reason': 'Krankheit', 'note': 'приватная деталь про операцию'},
             ]), \
             patch.object(backend, '_load_checkin_meta', return_value=[]):
            result = backend.get_assignment_candidates(
                'OBJ-1', 'tile_work', '2026-08-05', '2026-08-10', user=OWNER, _=None,
            )
        all_candidates = result['recommended'] + result['available'] + result['unavailable']
        for c in all_candidates:
            self.assertNotIn('note', c)
            self.assertNotIn('reason_detail', c)
            if 'reason' in c and c['reason']:
                self.assertNotIn('операция', c['reason'])
                self.assertIn(c['reason'], ('Отсутствует', 'Уже назначен на этот период', 'Назначен на другой объект', ''))


# ---------- Production/package imports (доп.раунд П1) ----------

class ProductionPackageImportTests(unittest.TestCase):
    """Production запускается как `uvicorn miniapp.main:app` с
    WorkingDirectory=/home/promonta/agent -- package-import сценарий (namespace
    package, нет __init__.py), sys.path[0] = родительская директория пакета, НЕ
    директория main.py. Top-level `import main` (как во всех остальных тестах этого
    файла) не ловит эту разницу вообще -- собираем временный пакет и импортируем
    как package member, ровно как это делает uvicorn в проде."""

    def test_main_importable_as_package_member(self):
        import shutil
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = os.path.join(tmp, 'miniapp')
            os.makedirs(pkg_dir)
            backend_dir = os.path.join(os.path.dirname(__file__), '..', 'backend')
            for fname in os.listdir(backend_dir):
                if fname.endswith('.py'):
                    shutil.copy(os.path.join(backend_dir, fname), pkg_dir)
            script = (
                "import sys; sys.path.insert(0, '.'); import miniapp.main as m; "
                "print('OK', len(m.app.routes), m.wt.__name__, m.pskills.__name__, m.amatch.__name__)"
            )
            env = dict(os.environ)
            env['BOT_TOKEN'] = 'test-dummy'
            env['MINIAPP_DATA_ROOT'] = tempfile.mkdtemp()
            result = subprocess.run(
                [sys.executable, '-c', script], cwd=tmp, env=env,
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('OK', result.stdout)
        self.assertIn('miniapp.work_types', result.stdout)
        self.assertIn('miniapp.profile_skills', result.stdout)
        self.assertIn('miniapp.assignment_matching', result.stdout)


# ---------- Deploy/rollback coverage for new modules (доп.раунд П1) ----------

class DeployRollbackNewModulesTests(unittest.TestCase):
    def _script_path(self, name):
        return os.path.join(os.path.dirname(__file__), '..', 'scripts', name)

    def test_deploy_sh_covers_all_three_new_modules(self):
        with open(self._script_path('deploy.sh'), encoding='utf-8') as f:
            content = f.read()
        for mod in ('work_types.py', 'profile_skills.py', 'assignment_matching.py'):
            self.assertIn(mod, content, f"{mod} не упомянут в deploy.sh")
            self.assertIn(f'.{mod}.ABSENT', content, f"{mod} ABSENT-marker отсутствует в deploy.sh")

    def test_rollback_sh_covers_all_three_new_modules(self):
        with open(self._script_path('rollback.sh'), encoding='utf-8') as f:
            content = f.read()
        for mod in ('work_types.py', 'profile_skills.py', 'assignment_matching.py'):
            self.assertIn(mod, content, f"{mod} не упомянут в rollback.sh")
            self.assertIn(f'.{mod}.ABSENT', content, f"{mod} ABSENT-marker обработка отсутствует в rollback.sh")

    def test_health_ready_checks_new_modules(self):
        with patch.object(backend, 'os') as mock_os:
            mock_os.path.isdir.return_value = True
            mock_os.access.return_value = True
            mock_os.path.isfile.return_value = True
            mock_os.getpid.return_value = 1
            mock_os.path.join.side_effect = lambda *a: '/'.join(a)
            mock_os.remove = lambda *a: None
            with patch('builtins.open', unittest.mock.mock_open()):
                result = backend.health_ready(user=OWNER, _=None)
        self.assertIn('work_types', result['checks'])
        self.assertIn('profile_skills', result['checks'])
        self.assertIn('assignment_matching', result['checks'])
        self.assertEqual(result['checks']['work_types'], 'ok')


# ---------- Profile stats skills_v2 (доп.раунд П2) ----------

class ProfileStatsSkillsV2Tests(unittest.TestCase):
    def test_profile_stats_returns_skills_v2(self):
        profile = {'name': 'Ivan', 'skills_v2': [{'skill_id': 'tile_work', 'level': 'master', 'verified': True}]}
        with patch.object(backend, '_load_checkin_meta', return_value=[]), \
             patch.object(backend, '_load_worker_profiles', return_value={'10': profile}), \
             patch.object(backend, '_load_roles', return_value={'10': 'worker'}), \
             patch.object(backend, '_load_abwesenheit', return_value=[]):
            result = backend.profile_stats(user_id='10', period='week', user=OWNER, role='owner')
        self.assertIn('skills_v2', result)
        self.assertEqual(result['skills_v2'], profile['skills_v2'])
        self.assertEqual(result['skills'], ['Плиточные работы'])

    def test_profile_stats_migrates_legacy_skills(self):
        profile = {'name': 'Ivan', 'skills': ['Плитка']}
        with patch.object(backend, '_load_checkin_meta', return_value=[]), \
             patch.object(backend, '_load_worker_profiles', return_value={'10': profile}), \
             patch.object(backend, '_save_worker_profiles'), \
             patch.object(backend, '_load_roles', return_value={'10': 'worker'}), \
             patch.object(backend, '_load_abwesenheit', return_value=[]):
            result = backend.profile_stats(user_id='10', period='week', user=OWNER, role='owner')
        self.assertEqual(result['skills_v2'][0]['skill_id'], 'tile_work')


# ---------- Verified preservation on skill edit (доп.раунд П3) ----------

class VerifiedPreservationTests(unittest.TestCase):
    def test_unchanged_skill_keeps_verified(self):
        profile = {'skills_v2': [
            {'skill_id': 'tile_work', 'level': 'master', 'verified': True},
            {'skill_id': 'painting', 'level': 'independent', 'verified': True},
        ]}
        with patch.object(backend, '_load_worker_profiles', return_value={'10': profile}), \
             patch.object(backend, '_save_worker_profiles'):
            # worker меняет уровень painting, tile_work остаётся тем же
            body = backend.ProfileUpdateBody(skills_v2=[
                backend.SkillV2Body(skill_id='tile_work', level='master'),
                backend.SkillV2Body(skill_id='painting', level='master', verified=True),  # verified от worker игнорируется
            ])
            result = backend.update_my_profile(body, user=WORKER_A)
        tile = next(s for s in result['skills_v2'] if s['skill_id'] == 'tile_work')
        painting = next(s for s in result['skills_v2'] if s['skill_id'] == 'painting')
        self.assertTrue(tile['verified'])  # неизменён -- сохранил verified
        self.assertFalse(painting['verified'])  # level изменился -- сброшен, incl. если worker слал true

    def test_new_skill_gets_verified_false(self):
        profile = {'skills_v2': [{'skill_id': 'tile_work', 'level': 'master', 'verified': True}]}
        with patch.object(backend, '_load_worker_profiles', return_value={'10': profile}), \
             patch.object(backend, '_save_worker_profiles'):
            body = backend.ProfileUpdateBody(skills_v2=[
                backend.SkillV2Body(skill_id='tile_work', level='master'),
                backend.SkillV2Body(skill_id='painting', level='helper'),
            ])
            result = backend.update_my_profile(body, user=WORKER_A)
        painting = next(s for s in result['skills_v2'] if s['skill_id'] == 'painting')
        self.assertFalse(painting['verified'])

    def test_removed_skill_is_removed(self):
        profile = {'skills_v2': [
            {'skill_id': 'tile_work', 'level': 'master', 'verified': True},
            {'skill_id': 'painting', 'level': 'independent', 'verified': True},
        ]}
        with patch.object(backend, '_load_worker_profiles', return_value={'10': profile}), \
             patch.object(backend, '_save_worker_profiles'):
            body = backend.ProfileUpdateBody(skills_v2=[
                backend.SkillV2Body(skill_id='tile_work', level='master'),
            ])
            result = backend.update_my_profile(body, user=WORKER_A)
        ids = [s['skill_id'] for s in result['skills_v2']]
        self.assertEqual(ids, ['tile_work'])

    def test_single_change_does_not_reset_all_verified(self):
        # 01.08: реальный найденный баг -- раньше ЛЮБОЙ PATCH сбрасывал verified для
        # ВСЕГО списка, не только изменённого навыка.
        profile = {'skills_v2': [
            {'skill_id': 'tile_work', 'level': 'master', 'verified': True},
            {'skill_id': 'painting', 'level': 'independent', 'verified': True},
            {'skill_id': 'plastering', 'level': 'helper', 'verified': True},
        ]}
        with patch.object(backend, '_load_worker_profiles', return_value={'10': profile}), \
             patch.object(backend, '_save_worker_profiles'):
            body = backend.ProfileUpdateBody(skills_v2=[
                backend.SkillV2Body(skill_id='tile_work', level='master'),
                backend.SkillV2Body(skill_id='painting', level='independent'),
                backend.SkillV2Body(skill_id='plastering', level='master'),  # только этот меняется
            ])
            result = backend.update_my_profile(body, user=WORKER_A)
        by_id = {s['skill_id']: s for s in result['skills_v2']}
        self.assertTrue(by_id['tile_work']['verified'])
        self.assertTrue(by_id['painting']['verified'])
        self.assertFalse(by_id['plastering']['verified'])


if __name__ == '__main__':
    unittest.main()
