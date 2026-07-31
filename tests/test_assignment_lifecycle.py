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

class BatchAssignmentTests(unittest.TestCase):
    def test_multiple_workers_get_distinct_assignment_ids(self):
        with patch.object(backend, '_load_abwesenheit', return_value=[]), \
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
        body = backend.BatchAssignBody(user_ids=['10'], work_type_id='tile_work', date_from='2026-08-16', date_to='2026-08-05')
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
            {'id': 'a1', 'user_id': '10', 'status': 'accepted', 'task_note': 'old'},
            {'id': 'a2', 'user_id': '20', 'status': 'accepted', 'task_note': 'unchanged'},
        ]}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
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
        existing = {'OBJ-1': [{'id': 'a1', 'user_id': '10', 'status': 'accepted', 'responded_at': 'sometime'}]}
        with patch.object(backend, 'update_json_transaction') as mock_txn:
            def fake_txn(path, default, mutator):
                data = {k: list(v) for k, v in existing.items()}
                mutator(data)
                self.captured = data
                return None
            mock_txn.side_effect = fake_txn
            body = backend.AssignmentUpdateBody(date_from='2026-09-01')
            backend.update_assignment('OBJ-1', 'a1', body, user=OWNER, _=None)
        a1 = self.captured['OBJ-1'][0]
        self.assertEqual(a1['status'], 'pending')
        self.assertEqual(a1['responded_at'], '')

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


if __name__ == '__main__':
    unittest.main()
