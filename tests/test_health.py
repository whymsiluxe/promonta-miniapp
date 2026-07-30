"""Backend tests for versioned health/readiness endpoints (Release-аудит Этап 6):
/api/health (liveness, unauthenticated, no secrets) and /api/health/ready
(owner-only readiness with real cheap filesystem checks).

Same plain stdlib unittest approach as tests/test_tools.py.

Run:
    cd miniapp-repo && python3 -m unittest tests.test_health -v
"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi import HTTPException  # noqa: E402
import main as backend  # noqa: E402


class HealthEndpointTests(unittest.TestCase):
    def test_health_returns_ok_status(self):
        result = backend.health()
        self.assertEqual(result['status'], 'ok')

    def test_health_has_required_fields(self):
        result = backend.health()
        for field in ('status', 'service', 'version', 'commit', 'time'):
            self.assertIn(field, result)
        self.assertEqual(result['service'], 'promonta-miniapp')

    def test_health_does_not_leak_secrets(self):
        result = backend.health()
        serialized = json.dumps(result)
        self.assertNotIn(backend.BOT_TOKEN, serialized)
        # Не должно быть абсолютных путей к credentials/секретным конфигам.
        self.assertNotIn('.sheets.json', serialized)
        self.assertNotIn('roles.json', serialized)

    def test_health_reads_version_from_file_when_present(self):
        original = backend.APP_VERSION_FILE
        with tempfile.TemporaryDirectory() as tmp:
            version_path = os.path.join(tmp, 'VERSION')
            with open(version_path, 'w', encoding='utf-8') as f:
                json.dump({'version': '0.9.0-rc1', 'commit': 'abc1234'}, f)
            backend.APP_VERSION_FILE = version_path
            try:
                result = backend.health()
                self.assertEqual(result['version'], '0.9.0-rc1')
                self.assertEqual(result['commit'], 'abc1234')
            finally:
                backend.APP_VERSION_FILE = original

    def test_health_falls_back_gracefully_without_version_file(self):
        original = backend.APP_VERSION_FILE
        backend.APP_VERSION_FILE = '/nonexistent/path/VERSION'
        try:
            result = backend.health()
            self.assertEqual(result['version'], 'unknown')
            self.assertEqual(result['commit'], 'unknown')
        finally:
            backend.APP_VERSION_FILE = original

    def test_health_survives_corrupt_version_file(self):
        original = backend.APP_VERSION_FILE
        with tempfile.TemporaryDirectory() as tmp:
            version_path = os.path.join(tmp, 'VERSION')
            with open(version_path, 'w', encoding='utf-8') as f:
                f.write('{not valid json')
            backend.APP_VERSION_FILE = version_path
            try:
                result = backend.health()
                self.assertEqual(result['version'], 'unknown')
            finally:
                backend.APP_VERSION_FILE = original

    def test_health_route_is_unauthenticated(self):
        import inspect
        sig = inspect.signature(backend.health)
        self.assertEqual(len(sig.parameters), 0, "health() must not require auth")


class HealthReadyEndpointTests(unittest.TestCase):
    """/api/health/ready -- owner-only, дешёвые filesystem-проверки, не сетевые."""

    def test_ready_requires_owner_role(self):
        import inspect
        sig = inspect.signature(backend.health_ready)
        # require_owner подключён через Depends -- проверяем что зависимость есть.
        self.assertIn('_', sig.parameters)

    def test_ready_reports_ok_when_dirs_exist_and_writable(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo_dir = os.path.join(tmp, 'object_photos')
            chat_dir = os.path.join(tmp, 'chat_attachments')
            os.makedirs(photo_dir)
            os.makedirs(chat_dir)
            with patch.object(backend, 'OBJECT_PHOTO_DIR', photo_dir), \
                 patch.object(backend, 'CHAT_ATTACH_DIR', chat_dir), \
                 patch.object(backend, 'TOOLS_LIB_PATH', backend.TOOLS_LIB_PATH), \
                 patch.object(backend, 'MANGEL_LIB_PATH', backend.MANGEL_LIB_PATH):
                result = backend.health_ready(user={'id': 1}, _=None)
            self.assertEqual(result['checks']['storage'], 'ok')
            self.assertEqual(result['checks']['uploads'], 'ok')
            # Не должно остаться пробного файла после проверки.
            self.assertEqual(os.listdir(photo_dir), [])

    def test_ready_reports_missing_when_storage_dir_absent(self):
        with patch.object(backend, 'OBJECT_PHOTO_DIR', '/nonexistent/dir/xyz'):
            result = backend.health_ready(user={'id': 1}, _=None)
        self.assertEqual(result['checks']['storage'], 'error')
        self.assertEqual(result['status'], 'degraded')

    def test_ready_reports_tools_lib_and_mangel_lib_presence(self):
        result = backend.health_ready(user={'id': 1}, _=None)
        # Оба файла реально в репо (см. предыдущие 2 коммита) -- должны быть 'ok'.
        self.assertEqual(result['checks']['tools_lib'], 'ok')
        self.assertEqual(result['checks']['mangel_lib'], 'ok')

    def test_ready_does_not_leak_secrets(self):
        result = backend.health_ready(user={'id': 1}, _=None)
        serialized = json.dumps(result)
        self.assertNotIn(backend.BOT_TOKEN, serialized)


if __name__ == '__main__':
    unittest.main()
