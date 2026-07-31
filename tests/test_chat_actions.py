"""Тесты для reply/forward/delete-доступа (действия с сообщениями чата).

Тот же стиль, что tests/test_chat_backend.py -- plain unittest, функции
эндпоинтов вызываются напрямую (без TestClient/HTTP-слоя), _load_chat/_save_chat
мокаются через patch.object.

Run:
    /home/promonta/agent/miniapp/.venv/bin/python3 -m unittest tests.test_chat_actions -v
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


def _msg(id_, user_id, text='hi', thread_key=None, to_user_id=None, attachment=None):
    return {
        'id': id_, 'ts': 1000, 'user_id': user_id, 'name': f'user{user_id}',
        'text': text, 'to_user_id': to_user_id, 'thread_key': thread_key,
        'attachment': attachment,
    }


class ReplyTests(unittest.TestCase):
    def test_reply_in_same_thread_ok(self):
        source = _msg('m1', 10, text='original', thread_key='obj:OBJ-1')
        with patch.object(backend, '_load_chat', return_value=[source]), \
             patch.object(backend, '_save_chat'), \
             patch.object(backend, '_check_thread_access'):
            body = backend.ChatMessageBody(text='re', thread_key='obj:OBJ-1', reply_to_id='m1')
            result = backend.post_chat_message(body, user=WORKER_A, role='worker')
        self.assertEqual(result['message']['reply_to']['id'], 'm1')
        self.assertEqual(result['message']['reply_to']['preview'], 'original')

    def test_reply_to_nonexistent_message_404(self):
        with patch.object(backend, '_load_chat', return_value=[]), \
             patch.object(backend, '_check_thread_access'):
            body = backend.ChatMessageBody(text='re', thread_key='obj:OBJ-1', reply_to_id='missing')
            with self.assertRaises(HTTPException) as ctx:
                backend.post_chat_message(body, user=WORKER_A, role='worker')
        self.assertEqual(ctx.exception.status_code, 404)

    def test_cannot_quote_message_from_other_dm(self):
        source = _msg('m1', 10, text='private', to_user_id='1')  # DM 10<->1
        with patch.object(backend, '_load_chat', return_value=[source]):
            body = backend.ChatMessageBody(text='re', to_user_id='30', reply_to_id='m1')  # 20 -> 30
            with self.assertRaises(HTTPException) as ctx:
                backend.post_chat_message(body, user=WORKER_B, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_old_messages_without_reply_field_still_work(self):
        with patch.object(backend, '_load_chat', return_value=[]), \
             patch.object(backend, '_save_chat'), \
             patch.object(backend, '_check_thread_access'):
            body = backend.ChatMessageBody(text='plain', thread_key='obj:OBJ-1')
            result = backend.post_chat_message(body, user=WORKER_A, role='worker')
        self.assertIsNone(result['message']['reply_to'])


class ForwardTests(unittest.TestCase):
    def test_forward_to_allowed_thread(self):
        source = _msg('m1', 10, text='fwd me', thread_key='obj:OBJ-1')
        with patch.object(backend, '_load_chat', return_value=[source]), \
             patch.object(backend, '_save_chat'), \
             patch.object(backend, '_check_message_access'), \
             patch.object(backend, '_check_thread_access'):
            body = backend.ChatMessageBody(text='', thread_key='obj:OBJ-2')
            result = backend.forward_chat_message('m1', body, user=WORKER_A, role='worker')
        self.assertEqual(result['message']['text'], 'fwd me')
        self.assertEqual(result['message']['forwarded_from'], 'user10')

    def test_forward_denied_to_inaccessible_thread(self):
        source = _msg('m1', 10, text='fwd me', thread_key='obj:OBJ-1')
        with patch.object(backend, '_load_chat', return_value=[source]), \
             patch.object(backend, '_check_message_access'), \
             patch.object(backend, '_check_thread_access', side_effect=HTTPException(403, 'no access')):
            body = backend.ChatMessageBody(text='', thread_key='obj:OBJ-2')
            with self.assertRaises(HTTPException) as ctx:
                backend.forward_chat_message('m1', body, user=WORKER_B, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_forward_attachment_preserves_file_reference_not_broken_link(self):
        att = {'file': 'abc123.jpg', 'name': 'photo.jpg', 'content_type': 'image/jpeg'}
        source = _msg('m1', 10, text='', thread_key='obj:OBJ-1', attachment=att)
        with patch.object(backend, '_load_chat', return_value=[source]), \
             patch.object(backend, '_save_chat'), \
             patch.object(backend, '_check_message_access'), \
             patch.object(backend, '_check_thread_access'):
            body = backend.ChatMessageBody(text='', thread_key='obj:OBJ-2')
            result = backend.forward_chat_message('m1', body, user=WORKER_A, role='worker')
        self.assertEqual(result['message']['attachment']['file'], 'abc123.jpg')


class DeleteAccessTests(unittest.TestCase):
    def test_worker_deletes_own_message(self):
        msg = _msg('m1', 10, thread_key='obj:OBJ-1')
        with patch.object(backend, '_load_chat', return_value=[msg]), \
             patch.object(backend, '_save_chat'), \
             patch.object(backend, '_archive_chat_messages'), \
             patch.object(backend, '_load_chat_reactions', return_value=[]):
            result = backend.delete_chat_message('m1', user=WORKER_A, role='worker')
        self.assertEqual(result['status'], 'ok')

    def test_worker_cannot_delete_others_message(self):
        msg = _msg('m1', 10, thread_key='obj:OBJ-1')
        with patch.object(backend, '_load_chat', return_value=[msg]):
            with self.assertRaises(HTTPException) as ctx:
                backend.delete_chat_message('m1', user=WORKER_B, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_deletes_any_message(self):
        msg = _msg('m1', 10, thread_key='obj:OBJ-1')
        with patch.object(backend, '_load_chat', return_value=[msg]), \
             patch.object(backend, '_save_chat'), \
             patch.object(backend, '_archive_chat_messages'), \
             patch.object(backend, '_load_chat_reactions', return_value=[]):
            result = backend.delete_chat_message('m1', user=OWNER, role='owner')
        self.assertEqual(result['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
