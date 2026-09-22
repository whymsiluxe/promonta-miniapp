"""22.09 iPhone screenshot audit, item found live: /api/diagnostics's `overall`
field only checked backend/sheets/chat, silently ignoring dailyplan_sync/
drive_contracts/finish_outbox entirely -- a real device showed a green
"✅ Все системы работают" headline directly above three yellow warning rows
for exactly those ignored fields, visibly contradicting itself.

New severity model: ok/warning/error.
  - required (backend/sheets/chat) genuinely broken -> error
  - optional integrations (dailyplan_sync/drive_contracts) legitimately
    not_configured, or finish_outbox has a dead-letter record -> warning
    (core is still fine, but there IS something worth a heads-up)
  - everything fine -> ok
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import system_status  # noqa: E402


def _diagnostics(**overrides):
    kwargs = dict(
        data_root='/tmp',
        roles_file='/tmp/roles.json',
        sheets_cache={},
        sheets_cache_ttl=300,
        activity_alerts_file='/tmp/alerts.json',
        news_feed_file='/tmp/news.json',
        chat_file='/tmp/chat.json',
        plan_sync_state_file='/tmp/plan_sync_state.json',
        contract_ingest_state_file='/tmp/contract_ingest.json',
        contracts_drive_folder_id='',
        app_version_file='/tmp/version.json',
        safe_load_json=lambda path, default: default,
        outbox_dead_letter_count=lambda: 0,
    )
    kwargs.update(overrides)
    return kwargs


class DiagnosticsSeverityModelTests(unittest.TestCase):
    def setUp(self):
        import tempfile, json
        self.tmp = tempfile.mkdtemp(prefix='diag-severity-')
        self.roles_file = os.path.join(self.tmp, 'roles.json')
        with open(self.roles_file, 'w') as f:
            json.dump({}, f)
        # chat_file must exist too -- it's a REQUIRED field in the severity
        # model, a fixture missing it would spuriously fail every "healthy"
        # scenario below via required_failed, unrelated to what each test
        # actually means to exercise.
        self.chat_file = os.path.join(self.tmp, 'chat.json')
        with open(self.chat_file, 'w') as f:
            json.dump([], f)

    def _healthy_kwargs(self, **overrides):
        return _diagnostics(
            data_root=self.tmp, roles_file=self.roles_file, chat_file=self.chat_file,
            sheets_cache={'Объекты': (0, [['h'], ['1']])},
            **overrides,
        )

    def test_all_required_ok_and_optional_integrations_configured_is_overall_ok(self):
        result = system_status.diagnostics_response(**self._healthy_kwargs(
            contracts_drive_folder_id='some-folder-id',
            safe_load_json=lambda path, default: {'last_sync_at': __import__('time').time()},
        ))
        self.assertEqual(result['dailyplan_sync'], 'ok')
        self.assertEqual(result['drive_contracts'], 'configured')
        self.assertEqual(result['overall'], 'ok')
        self.assertEqual(result['overall_required_failed'], [])
        self.assertEqual(result['overall_warnings'], [])
        self.assertEqual(result['overall_not_configured'], [])

    def test_optional_integration_not_configured_stays_warning_not_error(self):
        # dailyplan_sync/drive_contracts absent is a NORMAL, expected state --
        # must not drag the headline down to "error", but should be visible.
        result = system_status.diagnostics_response(**self._healthy_kwargs())
        self.assertEqual(result['dailyplan_sync'], 'not_configured')
        self.assertEqual(result['drive_contracts'], 'not_configured')
        self.assertEqual(result['overall'], 'warning')
        self.assertIn('dailyplan_sync', result['overall_not_configured'])
        self.assertIn('drive_contracts', result['overall_not_configured'])

    def test_required_backend_failure_is_overall_error(self):
        result = system_status.diagnostics_response(**_diagnostics(
            data_root='/nonexistent-path-xyz', roles_file='/nonexistent-roles.json',
            chat_file=self.chat_file,
        ))
        self.assertEqual(result['backend'], 'degraded')
        self.assertEqual(result['overall'], 'error')
        self.assertIn('backend', result['overall_required_failed'])

    def test_finish_outbox_dead_letter_is_warning_not_silently_ok(self):
        result = system_status.diagnostics_response(**self._healthy_kwargs(
            outbox_dead_letter_count=lambda: 1,
        ))
        self.assertEqual(result['finish_outbox'], 'red')
        self.assertEqual(result['overall'], 'warning')
        self.assertIn('finish_outbox', result['overall_warnings'])

    def test_error_takes_priority_over_warning(self):
        result = system_status.diagnostics_response(**_diagnostics(
            data_root='/nonexistent-path-xyz', roles_file='/nonexistent-roles.json',
            chat_file=self.chat_file,
            outbox_dead_letter_count=lambda: 1,
        ))
        self.assertEqual(result['overall'], 'error')

    def test_build_sha_and_build_version_fields_still_present_for_frontend_dedup_logic(self):
        # This test file covers the backend severity model; the frontend's
        # own dedup of these two fields (when they're the same underlying
        # value) is covered by test_diagnostics_frontend_contract.py.
        result = system_status.diagnostics_response(**self._healthy_kwargs())
        self.assertIn('build_sha', result)
        self.assertIn('build_version', result)


if __name__ == '__main__':
    unittest.main()
