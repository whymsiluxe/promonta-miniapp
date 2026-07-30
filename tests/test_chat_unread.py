"""Backend tests for chat unread counters (Release-аудит Этап 5): общий nav-badge
(GET /api/chat/unread_count) раньше вообще не учитывал thread_key-треды (obj:/
mangel:/task:) -- фильтровал только по to_user_id, поэтому любое сообщение с
thread_key попадало в ветку "group" и считалось непрочитанным ДЛЯ ЛЮБОГО
пользователя, независимо от того, участник ли он этого конкретного треда.

Same plain stdlib unittest approach as tests/test_chat_backend.py -- route handler
called directly with mocked _load_chat/_load_reads/_object_chat_participants etc.,
no real Google Sheets or filesystem access needed.

Run:
    cd miniapp-repo && python3 -m unittest tests.test_chat_unread -v
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402


class UnreadCountThreadKeyTests(unittest.TestCase):
    """Основной фикс: общий unread_count badge должен учитывать thread_key
    (obj:/mangel:/task:) так же строго, как unread_by_thread уже делал."""

    def test_own_messages_never_count_as_unread(self):
        messages = [{'user_id': 111, 'ts': 1000, 'text': 'привет'}]
        with patch.object(backend, '_load_chat', return_value=messages), \
             patch.object(backend, '_load_reads', return_value={}), \
             patch.object(backend, '_load_chat_thread_meta', return_value={}):
            result = backend.get_unread_count(user={'id': 111}, role='worker')
        self.assertEqual(result['unread'], 0)

    def test_group_message_counts_when_not_read(self):
        messages = [{'user_id': 222, 'ts': 1000, 'text': 'всем привет'}]
        with patch.object(backend, '_load_chat', return_value=messages), \
             patch.object(backend, '_load_reads', return_value={}), \
             patch.object(backend, '_load_chat_thread_meta', return_value={}):
            result = backend.get_unread_count(user={'id': 111}, role='worker')
        self.assertEqual(result['unread'], 1)

    def test_group_message_does_not_count_after_read(self):
        messages = [{'user_id': 222, 'ts': 1000, 'text': 'всем привет'}]
        reads = {'111': {'group': 2000}}  # прочитано после ts сообщения
        with patch.object(backend, '_load_chat', return_value=messages), \
             patch.object(backend, '_load_reads', return_value=reads), \
             patch.object(backend, '_load_chat_thread_meta', return_value={}):
            result = backend.get_unread_count(user={'id': 111}, role='worker')
        self.assertEqual(result['unread'], 0)

    def test_object_thread_message_counts_only_for_participant(self):
        # Сообщение в obj:OBJ-1 треде -- участник (222) должен видеть unread,
        # посторонний (333) -- нет (403 от _check_thread_access -- continue).
        messages = [{'user_id': 111, 'ts': 1000, 'thread_key': 'obj:OBJ-1', 'text': 'нужен материал'}]
        with patch.object(backend, '_load_chat', return_value=messages), \
             patch.object(backend, '_load_reads', return_value={}), \
             patch.object(backend, '_load_chat_thread_meta', return_value={}), \
             patch.object(backend, '_object_chat_participants', return_value=['222']):
            result_participant = backend.get_unread_count(user={'id': 222}, role='worker')
            result_stranger = backend.get_unread_count(user={'id': 333}, role='worker')
        self.assertEqual(result_participant['unread'], 1)
        self.assertEqual(result_stranger['unread'], 0)

    def test_object_thread_does_not_leak_into_group_count(self):
        # Регрессия основного бага: сообщение с thread_key раньше считалось как
        # "group" для ЛЮБОГО юзера. Теперь оно должно учитываться ТОЛЬКО против
        # last-read именно этого thread_key, не смешиваясь с group-веткой.
        messages = [{'user_id': 111, 'ts': 1000, 'thread_key': 'obj:OBJ-1', 'text': 'X'}]
        # Юзер прочитал GROUP полностью (large timestamp), но НЕ читал obj:OBJ-1.
        reads = {'222': {'group': 999999}}
        with patch.object(backend, '_load_chat', return_value=messages), \
             patch.object(backend, '_load_reads', return_value=reads), \
             patch.object(backend, '_load_chat_thread_meta', return_value={}), \
             patch.object(backend, '_object_chat_participants', return_value=['222']):
            result = backend.get_unread_count(user={'id': 222}, role='worker')
        # Правильное поведение: всё ещё unread, т.к. group-last-read не покрывает
        # obj:OBJ-1-тред -- это отдельный ключ в _thread_last_read.
        self.assertEqual(result['unread'], 1)

    def test_muted_thread_excluded_from_count(self):
        messages = [{'user_id': 111, 'ts': 1000, 'thread_key': 'mangel:T-1', 'text': 'статус изменён'}]
        meta = {'mangel:T-1': {'user_prefs': {'222': {'muted': True}}}}
        with patch.object(backend, '_load_chat', return_value=messages), \
             patch.object(backend, '_load_reads', return_value={}), \
             patch.object(backend, '_load_chat_thread_meta', return_value=meta), \
             patch.object(backend, '_mangel_chat_participants', return_value=['222']):
            result = backend.get_unread_count(user={'id': 222}, role='worker')
        self.assertEqual(result['unread'], 0)

    def test_dm_message_only_counts_for_recipient(self):
        messages = [{'user_id': 111, 'to_user_id': '222', 'ts': 1000, 'text': 'личное'}]
        with patch.object(backend, '_load_chat', return_value=messages), \
             patch.object(backend, '_load_reads', return_value={}), \
             patch.object(backend, '_load_chat_thread_meta', return_value={}):
            result_recipient = backend.get_unread_count(user={'id': 222}, role='worker')
            result_other = backend.get_unread_count(user={'id': 333}, role='worker')
        self.assertEqual(result_recipient['unread'], 1)
        self.assertEqual(result_other['unread'], 0)

    def test_matches_unread_by_thread_counts_for_same_data(self):
        # Согласованность: unread_count (сумма) должен совпадать с суммой
        # unread_by_thread для одного и того же набора данных -- иначе badge на
        # общей навигации разойдётся с суммой badge'ей по вкладкам.
        messages = [
            {'user_id': 111, 'ts': 1000, 'text': 'group msg'},
            {'user_id': 111, 'ts': 1001, 'thread_key': 'obj:OBJ-1', 'text': 'obj msg'},
            {'user_id': 111, 'to_user_id': '222', 'ts': 1002, 'text': 'dm msg'},
        ]
        with patch.object(backend, '_load_chat', return_value=messages), \
             patch.object(backend, '_load_reads', return_value={}), \
             patch.object(backend, '_load_chat_thread_meta', return_value={}), \
             patch.object(backend, '_object_chat_participants', return_value=['222']):
            total = backend.get_unread_count(user={'id': 222}, role='worker')
            by_thread = backend.get_unread_by_thread(user={'id': 222}, role='worker')
        self.assertEqual(total['unread'], sum(by_thread['unread_by_thread'].values()))


if __name__ == '__main__':
    unittest.main()
