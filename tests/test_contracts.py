"""Tests for contract ingestion routes (Round 5 — Production Control Program).

Drive ingestion is DRIVE_SCOPE_REQUIRED — these tests only cover the state
management and API routes (list/get/approve/reject), not the Drive polling.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


class ContractRouteTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ['MINIAPP_DATA_ROOT'] = cls.tmp
        os.environ.setdefault('BOT_TOKEN', 'test')
        os.environ['CONTRACTS_DRIVE_FOLDER_ID'] = ''  # not configured
        import main as backend
        cls.backend = backend
        # Ensure state file path is correct for this tmp dir
        cls.state_file = os.path.join(cls.tmp, 'contract_ingest_state.json')
        cls.backend.CONTRACT_INGEST_STATE_FILE = cls.state_file

    def _write_state(self, contracts: dict) -> None:
        with open(self.state_file, 'w') as f:
            json.dump({"contracts": contracts}, f)

    def _sample_contract(self, cid='ct-1', status='ingested') -> dict:
        return {
            "id": cid,
            "file_id": f"drive-{cid}",
            "file_name": f"Vertrag_{cid}.pdf",
            "file_hash": "abc123",
            "modified_time": "2026-09-01T10:00:00Z",
            "status": status,
            "ingested_at": 1000000.0,
            "text_preview": "Leistungen: Trockenbau 200 m²",
            "extracted_facts": {
                "object_address": "Musterstraße 5, Chemnitz",
                "contract_finish_date": "2026-12-31",
                "positions": [{"title": "Trockenbau", "quantity": 200, "unit": "m²"}],
                "missing_data": [],
                "confidence": 0.85,
            },
            "project_plan_draft": {
                "status": "draft",
                "requires_owner_input": True,
                "missing_data": [],
                "positions": [{"title": "Trockenbau", "quantity": 200, "unit": "m²"}],
                "contract_finish_date": "2026-12-31",
                "confidence": 0.85,
            },
            "error": None,
            "approved_at": None,
            "approved_by": None,
            "rejected_at": None,
            "rejected_by": None,
            "review_notes": "",
        }

    def test_list_contracts_empty(self):
        self._write_state({})
        result = self.backend.list_contracts(_=None)
        self.assertEqual(result['total'], 0)
        self.assertFalse(result['drive_configured'])
        self.assertEqual(result['drive_scope_status'], 'DRIVE_SCOPE_REQUIRED')

    def test_list_contracts_shows_ingested(self):
        self._write_state({'ct-1': self._sample_contract('ct-1', 'ingested')})
        result = self.backend.list_contracts(_=None)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['contracts'][0]['status'], 'ingested')

    def test_get_contract_found(self):
        self._write_state({'ct-2': self._sample_contract('ct-2')})
        self.backend.CONTRACT_INGEST_STATE_FILE = self.state_file
        result = self.backend.get_contract('ct-2', _=None)
        self.assertEqual(result['id'], 'ct-2')
        self.assertIn('extracted_facts', result)

    def test_get_contract_not_found(self):
        self._write_state({})
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.backend.get_contract('nonexistent', _=None)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_approve_ingested_contract(self):
        self._write_state({'ct-3': self._sample_contract('ct-3', 'ingested')})
        self.backend.CONTRACT_INGEST_STATE_FILE = self.state_file
        result = self.backend.approve_contract(
            'ct-3',
            body=self.backend.ContractReviewBody(notes='Alles gut'),
            user={'id': 1},
            _=None,
        )
        self.assertEqual(result['status'], 'approved')
        state = self.backend._load_contract_store()
        ct = state['contracts']['ct-3']
        self.assertEqual(ct['status'], 'approved')
        self.assertIsNotNone(ct['approved_at'])
        self.assertEqual(ct['review_notes'], 'Alles gut')

    def test_approve_rejected_contract_fails(self):
        self._write_state({'ct-4': self._sample_contract('ct-4', 'rejected')})
        self.backend.CONTRACT_INGEST_STATE_FILE = self.state_file
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.backend.approve_contract('ct-4', body=self.backend.ContractReviewBody(), user={'id': 1}, _=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_approve_without_draft_fails(self):
        contract = self._sample_contract('ct-5', 'ingested')
        contract['project_plan_draft'] = None
        self._write_state({'ct-5': contract})
        self.backend.CONTRACT_INGEST_STATE_FILE = self.state_file
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.backend.approve_contract('ct-5', body=self.backend.ContractReviewBody(), user={'id': 1}, _=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_reject_ingested_contract(self):
        self._write_state({'ct-6': self._sample_contract('ct-6', 'ingested')})
        self.backend.CONTRACT_INGEST_STATE_FILE = self.state_file
        result = self.backend.reject_contract(
            'ct-6',
            body=self.backend.ContractReviewBody(notes='Daten fehlen'),
            user={'id': 1},
            _=None,
        )
        self.assertEqual(result['status'], 'rejected')
        state = self.backend._load_contract_store()
        self.assertEqual(state['contracts']['ct-6']['status'], 'rejected')

    def test_reject_approved_contract_fails(self):
        self._write_state({'ct-7': self._sample_contract('ct-7', 'approved')})
        self.backend.CONTRACT_INGEST_STATE_FILE = self.state_file
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.backend.reject_contract('ct-7', body=self.backend.ContractReviewBody(), user={'id': 1}, _=None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_ingest_trigger_blocked_without_folder_id(self):
        self.backend.CONTRACTS_DRIVE_FOLDER_ID = ''
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.backend.trigger_contract_ingest(_=None)
        self.assertEqual(ctx.exception.status_code, 503)

    def test_ingest_trigger_ok_with_folder_id(self):
        original = self.backend.CONTRACTS_DRIVE_FOLDER_ID
        self.backend.CONTRACTS_DRIVE_FOLDER_ID = 'fake-folder-id'
        try:
            result = self.backend.trigger_contract_ingest(_=None)
            self.assertEqual(result['status'], 'trigger_sent')
        finally:
            self.backend.CONTRACTS_DRIVE_FOLDER_ID = original


class ContractIngestScriptTests(unittest.TestCase):
    """Tests for scripts/contract_ingest.py helper functions."""

    def setUp(self):
        # Import the script module
        import importlib.util
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'contract_ingest.py'
        )
        spec = importlib.util.spec_from_file_location('contract_ingest', script_path)
        self.ci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ci)

    def test_sha256_deterministic(self):
        content = b'Vertrag Muster'
        h1 = self.ci._sha256(content)
        h2 = self.ci._sha256(content)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_extract_text_plain(self):
        text, status = self.ci._extract_text(b'Hallo Welt', 'text/plain')
        self.assertEqual(status, 'ok')
        self.assertIn('Hallo', text)

    def test_extract_text_unsupported_mime(self):
        text, status = self.ci._extract_text(b'binary', 'image/png')
        self.assertEqual(status, 'extraction_failed')
        self.assertIsNone(text)

    def test_run_once_exits_early_without_folder_id(self):
        self.ci.CONTRACTS_DRIVE_FOLDER_ID = ''
        state_before = {"contracts": {}}
        state_after = self.ci.run_once(state_before)
        # No change — no Drive call made
        self.assertEqual(state_after, state_before)

    def test_load_save_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.ci.STATE_FILE = os.path.join(tmp, 'contract_ingest_state.json')
            state = self.ci._load_state()
            self.assertEqual(state, {"contracts": {}})
            state['contracts']['x'] = {"id": "x"}
            self.ci._save_state(state)
            reloaded = self.ci._load_state()
            self.assertIn('x', reloaded['contracts'])


if __name__ == '__main__':
    unittest.main()
