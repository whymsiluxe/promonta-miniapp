"""Раунд 5, §8: комментарии к новостям + per-user read markers / unread badges.

Тесты вызывают backend-функции напрямую (как test_mangel_delete.py / test_team_hours.py).
Проверяют: добавление/получение/удаление комментария (автор и Owner могут удалить,
чужой Worker -> 403); mark_feed_read пишет отметку; get_feed_unread считает НЕПРОЧИТАННОЕ
(публикация или новый комментарий новее отметки), а не общее число.

Run:
    BOT_TOKEN='ci-dummy-token-not-a-real-secret' MINIAPP_DATA_ROOT=$(mktemp -d) \
      /home/promonta/agent/miniapp/.venv/bin/python3 -m pytest tests/test_news_comments.py -v
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402
from fastapi import HTTPException  # noqa: E402

OWNER = {'id': 1, 'first_name': 'Boss'}
WORKER_A = {'id': 100, 'first_name': 'Ivan'}
WORKER_B = {'id': 200, 'first_name': 'Oleg'}


def _reset():
    backend._save_news_comments({})
    backend._save_feed_reads({})


class NewsCommentTests(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_add_and_get(self):
        backend.add_news_comment('p1', backend.NewsCommentBody(text='Первый'), user=WORKER_A)
        res = backend.get_news_comments('p1', user=WORKER_B)
        self.assertEqual(len(res['comments']), 1)
        self.assertEqual(res['comments'][0]['text'], 'Первый')
        self.assertEqual(res['comments'][0]['user_id'], '100')

    def test_empty_text_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.add_news_comment('p1', backend.NewsCommentBody(text='   '), user=WORKER_A)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_author_can_delete_own(self):
        backend.add_news_comment('p1', backend.NewsCommentBody(text='mine'), user=WORKER_A)
        cid = backend._load_news_comments()['p1'][0]['id']
        res = backend.delete_news_comment('p1', cid, user=WORKER_A, role='worker')
        self.assertEqual(len(res['comments']), 0)

    def test_other_worker_cannot_delete(self):
        backend.add_news_comment('p1', backend.NewsCommentBody(text='mine'), user=WORKER_A)
        cid = backend._load_news_comments()['p1'][0]['id']
        with self.assertRaises(HTTPException) as ctx:
            backend.delete_news_comment('p1', cid, user=WORKER_B, role='worker')
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_can_delete_any(self):
        backend.add_news_comment('p1', backend.NewsCommentBody(text='mine'), user=WORKER_A)
        cid = backend._load_news_comments()['p1'][0]['id']
        res = backend.delete_news_comment('p1', cid, user=OWNER, role='owner')
        self.assertEqual(len(res['comments']), 0)

    def test_reply_to_stored(self):
        backend.add_news_comment('p1', backend.NewsCommentBody(text='a'), user=WORKER_A)
        first = backend._load_news_comments()['p1'][0]['id']
        backend.add_news_comment('p1', backend.NewsCommentBody(text='b', reply_to=first), user=WORKER_B)
        comments = backend._load_news_comments()['p1']
        self.assertEqual(comments[1]['reply_to'], first)


class FeedUnreadTests(unittest.TestCase):
    def setUp(self):
        _reset()
        # Изолированный NEWS_FEED_FILE (иначе читается реальный prod-файл).
        self._orig_feed = backend.NEWS_FEED_FILE
        fd, self._tmp = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        with open(self._tmp, 'w', encoding='utf-8') as f:
            json.dump([{'id': 'p1', 'created': 100, 'category': 'X'}], f)
        backend.NEWS_FEED_FILE = self._tmp

    def tearDown(self):
        backend.NEWS_FEED_FILE = self._orig_feed
        if os.path.exists(self._tmp):
            os.remove(self._tmp)

    def test_new_publication_is_unread(self):
        # Отметка старше публикации -> непрочитано.
        backend._save_feed_reads({'100': {'last_news_read_at': 50}})
        res = backend.get_feed_unread(user=WORKER_A)
        self.assertEqual(res['news'], 1)

    def test_read_marker_clears_unread(self):
        backend._save_feed_reads({'100': {'last_news_read_at': 200}})
        res = backend.get_feed_unread(user=WORKER_A)
        self.assertEqual(res['news'], 0)

    def test_new_comment_reopens_unread(self):
        backend._save_feed_reads({'100': {'last_news_read_at': 200}})
        # Комментарий новее отметки -> новость снова непрочитана.
        backend._save_news_comments({'p1': [{'id': 'c1', 'user_id': '9', 'text': 'x', 'ts': 300}]})
        res = backend.get_feed_unread(user=WORKER_A)
        self.assertEqual(res['news'], 1)

    def test_mark_feed_read_writes_marker(self):
        out = backend.mark_feed_read(backend.FeedReadBody(tab='news'), user=WORKER_A)
        self.assertTrue(out['ok'])
        reads = backend._load_feed_reads()
        self.assertIn('last_news_read_at', reads['100'])

    def test_mark_feed_read_bad_tab(self):
        with self.assertRaises(HTTPException) as ctx:
            backend.mark_feed_read(backend.FeedReadBody(tab='bogus'), user=WORKER_A)
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == '__main__':
    unittest.main()
