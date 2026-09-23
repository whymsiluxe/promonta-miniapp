"""23.09 (owner P0, confirmed live on production) — create_task() and
update_task_status() used a nested, non-reentrant lock:

    with _lock_for(TASKS_FILE):
        items = _load_tasks()
        ...
        _save_tasks(items)   # -> _atomic_write_json() -> with _lock_for(TASKS_FILE)

_lock_for() caches ONE plain threading.Lock per file path (backend/core/
storage.py). threading.Lock is not reentrant -- the SAME thread trying to
acquire it a second time, from inside the first `with` block, blocks
forever. This is not a concurrency-only bug: it deadlocks on the very FIRST
call, unconditionally, with zero other requests involved. Confirmed against
the exact code deployed on production (same nested pattern) before this fix.

The regression test below proves this deterministically using a real
subprocess with a hard timeout -- NOT a mock of _save_tasks (mocking it would
hide the real storage-layer nesting the bug lives in), and NOT a bare
in-process call (a genuine deadlock would hang pytest itself forever with no
mock in the way). If the nested-lock bug ever comes back, this test times
out and fails loudly instead of hanging CI.

Fix: both endpoints now go through update_json_transaction(TASKS_FILE, ...),
which does the read+mutate+write under ONE lock acquisition -- same pattern
already used for critical_alerts.json/roles.json/birthday_alerts.json this
session.
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT, 'backend')

# Deterministic timeout for the subprocess probes below. Generous enough to
# never false-positive-fail on a loaded CI box, short enough that a real
# deadlock doesn't stall the suite for long.
PROBE_TIMEOUT_SECONDS = 15


def _run_probe(script: str, data_root: str) -> subprocess.CompletedProcess:
    # The required test environment is already initialized by
    # tests/conftest.py before any test module is imported (and by CI's
    # job-level env) -- inherit os.environ as-is rather than re-declaring it.
    env = os.environ.copy()
    env['MINIAPP_DATA_ROOT'] = data_root
    return subprocess.run(
        [sys.executable, '-c', script],
        capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECONDS, env=env,
    )


_PROBE_PRELUDE = textwrap.dedent(f"""
    import sys
    sys.path.insert(0, {BACKEND_DIR!r})
    import main as backend

    backend._save_roles({{'1': 'owner', '100': 'worker'}})
    backend._save_worker_profiles({{'100': {{'name': 'Worker'}}}})
    backend.has_active_object_access = lambda *a, **k: True

    class Body:
        title = 'probe task'
        object_id = 'OBJ-1'
        priority = ''
        category = ''
        due_at = None
        description = 'probe description'
""")


class TasksDeadlockFixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='tasks-deadlock-')

    def test_create_task_completes_without_hanging_real_storage_path(self):
        # No mock of _save_tasks/_load_tasks/update_json_transaction -- this
        # exercises the exact code path a real request takes.
        script = _PROBE_PRELUDE + textwrap.dedent("""
            result = backend.create_task(Body(), user={'id': 100}, role='worker')
            print('OK', result['id'], result['object_id'])
        """)
        proc = _run_probe(script, self.tmp)
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        self.assertIn('OK', proc.stdout)

    def test_update_task_status_completes_without_hanging_real_storage_path(self):
        script = _PROBE_PRELUDE + textwrap.dedent("""
            task = backend.create_task(Body(), user={'id': 100}, role='worker')
            result = backend.update_task_status(
                task['id'], backend.TaskStatusBody(status='закрыто'),
                user={'id': 1}, _=None,
            )
            print('OK', result['status'], result['closed_at'] is not None)
        """)
        proc = _run_probe(script, self.tmp)
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        self.assertIn('OK закрыто True', proc.stdout)

    def test_concurrent_create_calls_do_not_lose_either_task(self):
        # 23.09 (owner review correction): the FIRST version of this test used
        # two separate subprocess.Popen processes -- that simulates
        # CROSS-PROCESS contention, which update_json_transaction's
        # threading.Lock was never claimed to solve (_lock_for()'s lock is
        # process-local, same documented caveat as
        # cleanup_legacy_critical_alert_duplicates.py's rollout note). It
        # correctly failed intermittently (~40% of runs), proving it was
        # testing the wrong concurrency model, not that the fix is wrong.
        # Production runs ONE uvicorn process (no --workers N, confirmed
        # against the live systemd unit) -- concurrent requests are two
        # THREADS in that one process's sync-handler thread pool, which is
        # exactly what update_json_transaction's in-process lock protects.
        # This test now matches that real topology.
        import threading

        # The required test environment is already initialized by
        # tests/conftest.py -- this test runs in-process (real threads, not
        # a subprocess), so it inherits the same os.environ conftest already
        # prepared; no need to touch it.
        os.environ['MINIAPP_DATA_ROOT'] = self.tmp
        sys.path.insert(0, BACKEND_DIR)
        import main as backend  # noqa: E402  (deliberately late -- isolated per-test data root)
        backend.TASKS_FILE = os.path.join(self.tmp, 'tasks.json')
        backend._save_roles({'1': 'owner', '100': 'worker'})
        backend._save_worker_profiles({'100': {'name': 'Worker'}})
        backend.has_active_object_access = lambda *a, **k: True

        class Body:
            title = 'probe task'
            object_id = 'OBJ-1'
            priority = ''
            category = ''
            due_at = None
            description = 'probe description'

        results = []
        errors = []
        barrier = threading.Barrier(2)

        def _create():
            try:
                barrier.wait(timeout=5)
                results.append(backend.create_task(Body(), user={'id': 100}, role='worker'))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=_create) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=PROBE_TIMEOUT_SECONDS)

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)

        with open(backend.TASKS_FILE, encoding='utf-8') as f:
            stored = json.load(f)
        self.assertEqual(len(stored), 2, "both concurrent create_task calls must survive -- neither lost")
        self.assertEqual(len({t['id'] for t in stored}), 2, "both tasks must have distinct ids")


if __name__ == '__main__':
    unittest.main()
