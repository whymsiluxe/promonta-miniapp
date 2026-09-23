"""23.09 (owner review) — GET /api/critical-alerts/pending defensively collapses
legacy bare-uid birthday duplicates (see _is_legacy_bare_uid_birthday_ref() and
_supersede_legacy_siblings() in backend/main.py) down to ONE canonical record
per (kind, target_user_id, ref_id), read-side only, before returning. This is
a safety net for whatever the migration script + write-side supersede in
ack_critical_alert() haven't caught yet -- never a substitute for either.
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import main as backend  # noqa: E402

OWNER_ID = '1'
WORKER_ID = '555'


class PendingLegacyDedupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='critical-alerts-pending-legacy-')
        self._orig_file = backend.CRITICAL_ALERTS_FILE
        backend.CRITICAL_ALERTS_FILE = os.path.join(self.tmp, 'critical_alerts.json')

    def tearDown(self):
        backend.CRITICAL_ALERTS_FILE = self._orig_file

    def _legacy_birthday(self, id_, ref_id=WORKER_ID, created_at=100, acknowledged_at=None):
        return {
            'id': id_, 'target_user_id': OWNER_ID, 'kind': 'birthday', 'title': 't',
            'subtitle': '', 'ref_id': ref_id, 'created_at': created_at,
            'deadline_at': None, 'acknowledged_at': acknowledged_at, 'comment': None,
            'resolution': None, 'resolution_note': None, 'resolution_photos': [],
        }

    def test_pending_collapses_legacy_bare_uid_birthday_duplicates_to_one(self):
        backend._save_critical_alerts([
            self._legacy_birthday('a1', created_at=100),
            self._legacy_birthday('a2', created_at=300),
            self._legacy_birthday('a3', created_at=200),
        ])
        result = backend.list_pending_critical_alerts(user={'id': int(OWNER_ID)})
        alerts = result['alerts']
        self.assertEqual(len(alerts), 1)
        # Most recent by created_at is the one surfaced.
        self.assertEqual(alerts[0]['id'], 'a2')

    def test_pending_never_collapses_new_idem_shaped_birthday_alerts(self):
        idem_a = f'birthday:{WORKER_ID}:2027:3days'
        idem_b = f'birthday:{WORKER_ID}:2027:today'
        backend._save_critical_alerts([
            self._legacy_birthday('new1', ref_id=idem_a, created_at=100),
            self._legacy_birthday('new2', ref_id=idem_b, created_at=200),
        ])
        result = backend.list_pending_critical_alerts(user={'id': int(OWNER_ID)})
        self.assertEqual({a['id'] for a in result['alerts']}, {'new1', 'new2'})

    def test_pending_never_collapses_non_birthday_alerts_sharing_the_same_shape(self):
        backend._save_critical_alerts([
            {**self._legacy_birthday('a1', created_at=100), 'kind': 'plan_overdue'},
            {**self._legacy_birthday('a2', created_at=200), 'kind': 'plan_overdue'},
        ])
        result = backend.list_pending_critical_alerts(user={'id': int(OWNER_ID)})
        self.assertEqual({a['id'] for a in result['alerts']}, {'a1', 'a2'})

    def test_pending_never_returns_acknowledged_alerts_regardless_of_grouping(self):
        backend._save_critical_alerts([
            self._legacy_birthday('a1', created_at=100, acknowledged_at=999),
            self._legacy_birthday('a2', created_at=200),
        ])
        result = backend.list_pending_critical_alerts(user={'id': int(OWNER_ID)})
        self.assertEqual({a['id'] for a in result['alerts']}, {'a2'})

    def test_pending_scopes_to_the_requesting_user_only(self):
        other_user_alert = self._legacy_birthday('a1', created_at=100)
        other_user_alert['target_user_id'] = WORKER_ID
        backend._save_critical_alerts([
            other_user_alert,
            self._legacy_birthday('a2', created_at=200),
        ])
        result = backend.list_pending_critical_alerts(user={'id': int(OWNER_ID)})
        self.assertEqual({a['id'] for a in result['alerts']}, {'a2'})


if __name__ == '__main__':
    unittest.main()
