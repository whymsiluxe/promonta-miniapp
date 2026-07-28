"""Minimal unit tests for the Phase 06 chat backend additions.

No test framework is installed in this repo yet (see docs/TESTING.md) -- this is
a plain stdlib unittest script, runnable directly with no new dependency, unlike
tests/smoke-nav-fab.js (Playwright, written but never actually executed in this
environment -- see that file's header comment). These ARE executed, right now,
against the real backend/main.py, importable because the functions under test
(_chat_thread_id, _reject_self_chat, _reactions_summary_for_message,
_thread_user_prefs) are pure/near-pure -- no file I/O, no network.

Run:
    cd miniapp-repo && python3 -m unittest tests.test_chat_backend -v
(needs BOT_TOKEN in the environment for backend/main.py's module-level
`BOT_TOKEN = os.environ['BOT_TOKEN']` -- already true on this VPS's shell/venv;
fastapi/pydantic/python-magic must be importable, i.e. run with
/home/promonta/agent/miniapp/.venv/bin/python3, the same venv the live service
uses, not bare system python3.)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402


class ChatThreadIdTests(unittest.TestCase):
    def test_direct_pair_is_order_independent(self):
        self.assertEqual(backend._chat_thread_id('5', '10'), backend._chat_thread_id('10', '5'))

    def test_group_thread_has_fixed_id(self):
        self.assertEqual(backend._chat_thread_id('5', None), 'group')
        self.assertEqual(backend._chat_thread_id('5', ''), 'group')

    def test_different_pairs_get_different_ids(self):
        self.assertNotEqual(backend._chat_thread_id('5', '10'), backend._chat_thread_id('5', '11'))


class SelfChatRejectionTests(unittest.TestCase):
    def test_self_chat_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            backend._reject_self_chat('42', '42')
        self.assertEqual(ctx.exception.status_code, 400)

    def test_self_chat_rejected_regardless_of_type(self):
        with self.assertRaises(HTTPException):
            backend._reject_self_chat(42, '42')

    def test_other_user_not_rejected(self):
        backend._reject_self_chat('42', '43')  # should not raise

    def test_group_message_not_rejected(self):
        backend._reject_self_chat('42', None)  # should not raise
        backend._reject_self_chat('42', '')  # should not raise


class ReactionSummaryTests(unittest.TestCase):
    def test_empty_reactions_gives_empty_summary(self):
        self.assertEqual(backend._reactions_summary_for_message([], 'm1', 'u1'), [])

    def test_single_reaction_counted_and_marked_mine(self):
        reactions = [{'message_id': 'm1', 'user_id': 'u1', 'reaction': '👍', 'created_at': 1}]
        summary = backend._reactions_summary_for_message(reactions, 'm1', 'u1')
        self.assertEqual(summary, [{'reaction': '👍', 'count': 1, 'mine': True}])

    def test_reaction_from_other_user_not_marked_mine(self):
        reactions = [{'message_id': 'm1', 'user_id': 'u2', 'reaction': '👍', 'created_at': 1}]
        summary = backend._reactions_summary_for_message(reactions, 'm1', 'u1')
        self.assertEqual(summary, [{'reaction': '👍', 'count': 1, 'mine': False}])

    def test_multiple_users_same_reaction_aggregate_count(self):
        reactions = [
            {'message_id': 'm1', 'user_id': 'u1', 'reaction': '👍', 'created_at': 1},
            {'message_id': 'm1', 'user_id': 'u2', 'reaction': '👍', 'created_at': 2},
        ]
        summary = backend._reactions_summary_for_message(reactions, 'm1', 'u1')
        self.assertEqual(summary, [{'reaction': '👍', 'count': 2, 'mine': True}])

    def test_reactions_for_other_messages_are_ignored(self):
        reactions = [{'message_id': 'other', 'user_id': 'u1', 'reaction': '👍', 'created_at': 1}]
        self.assertEqual(backend._reactions_summary_for_message(reactions, 'm1', 'u1'), [])

    def test_summary_order_follows_chat_reaction_options(self):
        reactions = [
            {'message_id': 'm1', 'user_id': 'u1', 'reaction': '❗', 'created_at': 1},
            {'message_id': 'm1', 'user_id': 'u1', 'reaction': '👍', 'created_at': 2},
        ]
        summary = backend._reactions_summary_for_message(reactions, 'm1', 'u1')
        self.assertEqual([s['reaction'] for s in summary], ['👍', '❗'])


class ThreadPrefsTests(unittest.TestCase):
    def test_defaults_when_no_prefs_stored(self):
        self.assertEqual(backend._thread_user_prefs({}, 'group', 'u1'), dict(backend.DEFAULT_THREAD_PREFS))

    def test_stored_prefs_override_defaults(self):
        meta = {'group': {'user_prefs': {'u1': {'muted': True}}}}
        prefs = backend._thread_user_prefs(meta, 'group', 'u1')
        self.assertEqual(prefs, {'muted': True, 'pinned': False, 'archived': False})

    def test_prefs_are_per_user(self):
        meta = {'group': {'user_prefs': {'u1': {'pinned': True}}}}
        self.assertEqual(backend._thread_user_prefs(meta, 'group', 'u2'), dict(backend.DEFAULT_THREAD_PREFS))


if __name__ == '__main__':
    unittest.main()
