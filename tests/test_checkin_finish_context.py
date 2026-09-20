import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import daily_plan_lib as dpl  # noqa: E402
import main as backend  # noqa: E402


WORKER = {'id': 42, 'first_name': 'Worker'}


def _item(idx=1):
    return {
        "id": f"item-{idx}",
        "sequence": idx,
        "title": f"Task {idx}",
        "objective": "Do work",
        "planned_quantity": 1,
        "unit": "pcs",
        "time_estimate_hours": 1,
        "work_type_id": "work",
        "required_tools": [],
        "required_materials": [],
    }


class CheckinFinishContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        dpl.configure(
            os.path.join(self.tmp, 'daily_plan_store.json'),
            os.path.join(self.tmp, 'plan_sync_state.json'),
            os.path.join(self.tmp, 'work_calendar.json'),
        )

    def test_finish_context_without_plan_is_explicit_no_plan(self):
        session = {'id': 'sess-no-plan', 'user_id': '42', 'object_id': 'OBJ-1'}
        with patch.object(backend, '_load_checkin_meta', return_value=[session]):
            result = backend.checkin_finish_context('sess-no-plan', user=WORKER, role='worker')

        self.assertFalse(result['has_plan'])
        self.assertEqual(result['object_id'], 'OBJ-1')

    def test_finish_context_returns_accepted_snapshot_items(self):
        plan = dpl.create_plan(
            object_id='OBJ-1',
            stage_key='stage-1',
            date_str='2026-09-21',
            assigned_worker_ids=['42'],
            items=[_item(1)],
            created_by='owner',
        )
        dpl.publish_plan(plan['id'], 'owner')
        acceptance = dpl.accept_plan(plan['id'], 1, '42')
        dpl.update_plan_items(plan['id'], [_item(1), _item(2)], 'sheets_edit', 'Added second item', 'owner')

        session = {
            'id': 'sess-plan',
            'user_id': '42',
            'object_id': 'OBJ-1',
            'daily_plan_id': plan['id'],
            'daily_plan_version': '1',
            'daily_plan_acceptance_id': acceptance['id'],
        }
        with patch.object(backend, '_load_checkin_meta', return_value=[session]):
            result = backend.checkin_finish_context('sess-plan', user=WORKER, role='worker')

        self.assertTrue(result['has_plan'])
        self.assertEqual(result['plan']['id'], plan['id'])
        self.assertEqual(result['plan']['version'], 1)
        self.assertEqual(len(result['plan']['items']), 1)
        self.assertEqual(result['plan']['items'][0]['id'], 'item-1')

