"""Concurrent-write test for update_json_transaction() (backend/main.py) -- external
audit's ТЗ п.5 explicitly asked for this: two parallel updates to the same JSON file,
both changes must survive, file stays valid JSON.

Run:
    cd miniapp-repo && python3 -m unittest tests.test_json_transaction -v
(same env requirements as the other test files: BOT_TOKEN in env, run with the
miniapp .venv's python3.)
"""
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402


class UpdateJsonTransactionConcurrencyTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        os.remove(self.path)  # start from "file doesn't exist yet" like a fresh store

    def tearDown(self):
        for p in (self.path, f'{self.path}.tmp-{os.getpid()}'):
            if os.path.exists(p):
                os.remove(p)

    def test_two_concurrent_appends_both_survive(self):
        # Simulates two parallel uploads to the same object_id -- the exact scenario
        # the audit flagged (both requests read the same "existing" list before either
        # writes, one silently overwrites the other's addition). update_json_transaction's
        # _lock_for(path) serializes the two threads -- that IS the fix, so we don't force
        # them to literally race inside the critical section (that would deadlock against
        # the same lock instead of testing anything); we fire them close together and
        # assert BOTH appends are present afterward, which is what the audit actually cares
        # about (no lost update), not exact interleaving timing.
        def _worker(value):
            def _mutator(data):
                data.setdefault('items', []).append(value)
            backend.update_json_transaction(self.path, {}, _mutator)

        t1 = threading.Thread(target=_worker, args=('a',))
        t2 = threading.Thread(target=_worker, args=('b',))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        with open(self.path, encoding='utf-8') as f:
            result = json.load(f)

        self.assertEqual(sorted(result.get('items', [])), ['a', 'b'])

    def test_many_concurrent_appends_none_lost(self):
        n = 20
        threads = []
        for i in range(n):
            def _mutator(data, i=i):
                data.setdefault('items', []).append(i)
            t = threading.Thread(target=lambda i=i: backend.update_json_transaction(
                self.path, {}, lambda data, i=i: data.setdefault('items', []).append(i)
            ))
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        with open(self.path, encoding='utf-8') as f:
            result = json.load(f)

        self.assertEqual(sorted(result.get('items', [])), list(range(n)))

    def test_mutator_exception_does_not_corrupt_file(self):
        def _seed(data):
            data['seeded'] = True
        backend.update_json_transaction(self.path, {}, _seed)

        def _bad_mutator(data):
            data['should_not_appear'] = True
            raise ValueError('boom')

        with self.assertRaises(ValueError):
            backend.update_json_transaction(self.path, {}, _bad_mutator)

        with open(self.path, encoding='utf-8') as f:
            result = json.load(f)
        # File must still be valid JSON with the pre-exception state, not a partial write.
        self.assertEqual(result, {'seeded': True})


if __name__ == '__main__':
    unittest.main()
