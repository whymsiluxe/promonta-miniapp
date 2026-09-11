"""Regression tests for the worker roster/access invariant (owner report:
worker "Ivan" appeared in team/dashboard, had no avatar, Worker Card 404'd,
and was missing entirely from the Доступ tab).

Root cause (two separate defaults that both silently invented access):
1. /api/workers did `roles.get(uid, 'worker')` -- ANY uid in worker_profiles.json
   but absent from roles.json was presented as an active 'worker', not as
   having no access at all.
2. /api/roles built `pending` from `notified_users - roles`, not from
   `worker_profiles - roles` -- a profile that existed without ever being in
   notified_users was invisible in Access entirely (not in roles, not in
   pending).

Same style as test_ui_fix_round_tofu_names.py -- route handlers called
directly, patch.object on the real backend module.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}


class WorkerRosterAccessInvariantTests(unittest.TestCase):
    def test_profile_only_user_is_not_presented_as_worker(self):
        # Ivan: has a worker_profiles.json entry (completed onboarding at some
        # point) but is NOT in roles.json (access revoked or never granted).
        roles = {'1': 'owner', '2': 'worker'}
        profiles = {
            '2': {'name': 'Настоящий Воркер', 'avatar': 'x.jpg'},
            '99': {'name': 'Иван', 'avatar': ''},
        }
        with patch.object(backend, '_load_roles', return_value=roles), \
             patch.object(backend, '_load_worker_profiles', return_value=profiles), \
             patch.object(backend, '_last_seen', {}):
            result = backend.list_workers(user=OWNER)
        by_id = {w['user_id']: w for w in result['workers']}
        self.assertEqual(by_id['2']['role'], 'worker')
        self.assertTrue(by_id['2']['access_granted'])
        # Ivan must NOT be silently defaulted to role='worker' -- that was the bug.
        self.assertIsNone(by_id['99']['role'])
        self.assertFalse(by_id['99']['access_granted'])

    def test_worker_filter_call_sites_exclude_profile_only_ghosts(self):
        # Every frontend consumer of /api/workers filters on w.role == 'worker'
        # (mangel.js, tools.js, home.js, abwesenheit.js, today-plan.js) -- this
        # test proves that filter now correctly excludes a profile-only user,
        # simulating exactly what those call sites do client-side.
        roles = {'1': 'owner', '2': 'worker'}
        profiles = {'2': {'name': 'Настоящий'}, '99': {'name': 'Иван'}}
        with patch.object(backend, '_load_roles', return_value=roles), \
             patch.object(backend, '_load_worker_profiles', return_value=profiles), \
             patch.object(backend, '_last_seen', {}):
            result = backend.list_workers(user=OWNER)
        actual_workers = [w for w in result['workers'] if w['role'] == 'worker']
        self.assertEqual([w['user_id'] for w in actual_workers], ['2'])

    def test_roles_pending_includes_profile_without_role_even_if_never_notified(self):
        # Ivan was never in notified_users (e.g. notification failed, or the
        # profile was created through a different path) -- the OLD pending
        # (notified - roles) would never surface him. New pending is
        # (profiles - roles), independent of notified_users.
        roles = {'1': 'owner'}
        notified = {}  # Ivan never notified -- old code would hide him entirely
        profiles = {'99': {'name': 'Иван'}}
        with patch.object(backend, '_load_roles', return_value=roles), \
             patch.object(backend, '_load_notified_users', return_value=notified), \
             patch.object(backend, '_load_worker_profiles', return_value=profiles):
            result = backend.list_roles(user=OWNER, _=None)
        pending_ids = [p['user_id'] for p in result['pending']]
        self.assertIn('99', pending_ids)
        ivan = next(p for p in result['pending'] if p['user_id'] == '99')
        self.assertFalse(ivan['was_notified'])

    def test_roles_pending_still_marks_notified_users(self):
        roles = {'1': 'owner'}
        notified = {'50': True}
        profiles = {'50': {'name': 'Уведомлённый'}}
        with patch.object(backend, '_load_roles', return_value=roles), \
             patch.object(backend, '_load_notified_users', return_value=notified), \
             patch.object(backend, '_load_worker_profiles', return_value=profiles):
            result = backend.list_roles(user=OWNER, _=None)
        pending = next(p for p in result['pending'] if p['user_id'] == '50')
        self.assertTrue(pending['was_notified'])

    def test_granting_access_moves_user_from_pending_to_roles(self):
        # After _: grant access via set_role -- the same user must disappear
        # from pending and appear in roles on the next /api/roles read.
        roles = {'1': 'owner'}
        profiles = {'99': {'name': 'Иван'}}
        with patch.object(backend, '_load_roles', return_value=roles), \
             patch.object(backend, '_load_notified_users', return_value={}), \
             patch.object(backend, '_load_worker_profiles', return_value=profiles):
            before = backend.list_roles(user=OWNER, _=None)
        self.assertIn('99', [p['user_id'] for p in before['pending']])

        roles_after_grant = {'1': 'owner', '99': 'worker'}
        with patch.object(backend, '_load_roles', return_value=roles_after_grant), \
             patch.object(backend, '_load_notified_users', return_value={}), \
             patch.object(backend, '_load_worker_profiles', return_value=profiles):
            after = backend.list_roles(user=OWNER, _=None)
        self.assertNotIn('99', [p['user_id'] for p in after['pending']])
        self.assertIn('99', [r['user_id'] for r in after['roles']])


if __name__ == '__main__':
    unittest.main()
