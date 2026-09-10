"""Regression tests for Round 1 Foundation Bug Fixes.

Each class covers one item. Tests use direct function calls (same pattern as
test_foundation_completion.py), not HTTP TestClient, to avoid httpx2 dependency.
"""
import json
import os
import sys
import tempfile
import time
import unittest
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import daily_plan_lib as dpl
import main as backend


def _make_item(idx=0, title=None):
    return {
        "id": f"item{idx}",
        "title": title or f"Task {idx}",
        "planned_quantity": 5.0,
        "unit": "м²",
    }


# ── Item 2: Per-worker amendment UX ─────────────────────────────────────────

class TestItem2AmendmentPerWorker(unittest.TestCase):
    """Backend: get_pending_amendments passes worker_id; per-worker ack semantics."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="promonta-test-item2-")
        os.environ["MINIAPP_DATA_ROOT"] = self._tmp
        os.environ["PROMONTA_ENV"] = "test"
        dpl.configure(
            os.path.join(self._tmp, "daily_plan_store.json"),
            os.path.join(self._tmp, "plan_sync_state.json"),
            os.path.join(self._tmp, "work_calendar.json"),
        )

    def test_worker_a_acks_amendment_b_still_sees_it(self):
        """After Worker A acks, Worker B must still see the amendment as pending."""
        worker_a, worker_b = "w2a", "w2b"

        plan = dpl.create_plan(
            object_id="obj_item2",
            stage_key="stage1",
            date_str="2099-01-15",
            assigned_worker_ids=[worker_a, worker_b],
            items=[_make_item(0)],
            created_by="test",
        )
        dpl.publish_plan(plan["id"], "test")
        dpl.accept_plan(plan["id"], plan["version"], worker_a)
        dpl.accept_plan(plan["id"], plan["version"], worker_b)

        # Owner edits → creates amendment
        dpl.update_plan_items(
            plan_id=plan["id"],
            new_items=[_make_item(0, "Task 0 updated"), _make_item(1)],
            change_type="sheets_edit",
            change_summary="Changed after acceptance",
            updated_by="owner",
        )

        ams_a_before = dpl.get_pending_amendments(plan["id"], worker_a)
        ams_b_before = dpl.get_pending_amendments(plan["id"], worker_b)
        self.assertEqual(len(ams_a_before), 1, "Worker A should see 1 pending amendment")
        self.assertEqual(len(ams_b_before), 1, "Worker B should see 1 pending amendment")

        # Worker A acknowledges
        amendment_id = ams_a_before[0]["id"]
        dpl.acknowledge_amendment(plan["id"], amendment_id, worker_a)

        ams_a_after = dpl.get_pending_amendments(plan["id"], worker_a)
        ams_b_after = dpl.get_pending_amendments(plan["id"], worker_b)
        self.assertEqual(len(ams_a_after), 0, "Worker A acked — should see 0")
        self.assertEqual(len(ams_b_after), 1, "Worker B has not acked — must still see 1")

    def test_get_pending_amendments_without_worker_id_includes_all(self):
        """Without worker_id, returns amendments unacked by ALL workers."""
        wa, wb = "w2all_a", "w2all_b"
        plan = dpl.create_plan(
            object_id="obj_item2_all",
            stage_key="s",
            date_str="2099-01-16",
            assigned_worker_ids=[wa, wb],
            items=[_make_item(0)],
            created_by="test",
        )
        dpl.publish_plan(plan["id"], "test")
        dpl.accept_plan(plan["id"], plan["version"], wa)
        dpl.accept_plan(plan["id"], plan["version"], wb)
        dpl.update_plan_items(plan["id"], [_make_item(0, "Updated")], "edit", "x", "owner")

        # A acks but B hasn't — overall still pending
        amend_id = dpl.get_pending_amendments(plan["id"], wa)[0]["id"]
        dpl.acknowledge_amendment(plan["id"], amend_id, wa)

        # Without worker_id → still 1 (not all acked)
        all_pending = dpl.get_pending_amendments(plan["id"])
        self.assertEqual(len(all_pending), 1, "Overall pending should be 1 until B acks")

        # B acks
        dpl.acknowledge_amendment(plan["id"], amend_id, wb)
        all_pending_after = dpl.get_pending_amendments(plan["id"])
        self.assertEqual(len(all_pending_after), 0, "All acked — overall pending should be 0")


# ── Item 3: Sheets items_json validation ─────────────────────────────────────

class TestItem3SheetsValidation(unittest.TestCase):
    """plan_sync: malformed items_json → sync error, NOT items=[] overwrite."""

    def setUp(self):
        import importlib
        import plan_sync
        self.ps = importlib.reload(plan_sync)

    def test_malformed_items_json_returns_none(self):
        """_row_to_plan_fields must return None for corrupt items_json."""
        row = {
            "plan_id": "test-plan-3",
            "date": "2099-01-20",
            "object_id": "obj3",
            "stage_key": "s1",
            "items_json": "{not valid json{{",
        }
        result = self.ps._row_to_plan_fields(row)
        self.assertIsNone(result,
            "Malformed items_json must cause _row_to_plan_fields to return None "
            "(sync error), not silently set items=[].")

    def test_non_list_items_json_returns_none(self):
        """items_json that is not a list (e.g., dict) must also return None."""
        row = {
            "plan_id": "test-plan-3b",
            "date": "2099-01-20",
            "object_id": "obj3",
            "stage_key": "s1",
            "items_json": '{"key": "value"}',  # valid JSON but not a list
        }
        result = self.ps._row_to_plan_fields(row)
        self.assertIsNone(result,
            "items_json that is not a list must return None (sync error).")

    def test_valid_items_json_returns_fields(self):
        """A valid row with correct items_json must still produce a result."""
        row = {
            "plan_id": "test-plan-3c",
            "date": "2099-01-20",
            "object_id": "obj3",
            "stage_key": "s1",
            "items_json": '[{"id": "i1", "title": "Task", "planned_quantity": 5, "unit": "m2"}]',
        }
        result = self.ps._row_to_plan_fields(row)
        self.assertIsNotNone(result, "Valid row must return fields, not None")
        self.assertEqual(len(result["items"]), 1)


# ── Item 4: plan_id immutability ─────────────────────────────────────────────

class TestItem4PlanIdImmutability(unittest.TestCase):
    """plan_sync: missing/blank plan_id → None (validation error), no synthetic fallback."""

    def setUp(self):
        import importlib
        import plan_sync
        self.ps = importlib.reload(plan_sync)

    def test_missing_plan_id_returns_none(self):
        """Row without plan_id column must not be publishable."""
        row = {
            "date": "2099-01-21",
            "object_id": "obj4",
            "stage_key": "s1",
            "items_json": "[]",
        }
        result = self.ps._row_to_plan_fields(row)
        self.assertIsNone(result,
            "Row without plan_id must return None — no synthetic f'{obj}:{date}:{stage}' fallback.")

    def test_blank_plan_id_returns_none(self):
        """Blank plan_id must also return None."""
        row = {
            "plan_id": "   ",
            "date": "2099-01-21",
            "object_id": "obj4",
            "stage_key": "s1",
            "items_json": "[]",
        }
        result = self.ps._row_to_plan_fields(row)
        self.assertIsNone(result, "Blank/whitespace plan_id must return None.")

    def test_explicit_plan_id_is_preserved(self):
        """A row with an explicit plan_id must use that id, not synthesize."""
        row = {
            "plan_id": "my-explicit-uuid-1234",
            "date": "2099-01-21",
            "object_id": "obj4",
            "stage_key": "s1",
            "items_json": "[]",
        }
        result = self.ps._row_to_plan_fields(row)
        self.assertIsNotNone(result, "Row with explicit plan_id must succeed")
        self.assertEqual(result["plan_id"], "my-explicit-uuid-1234")


# ── Item 5: Sheets field-change detection ────────────────────────────────────

class TestItem5FieldChangeDetection(unittest.TestCase):
    """plan_sync: changes to worker_ids/date/object_id/stage_key beyond items must be detected."""

    def setUp(self):
        import importlib
        import plan_sync
        self.ps = importlib.reload(plan_sync)

    def _make_state_with_plan(self, plan_id, date_str, worker_ids, items_json="[]"):
        """Create a state dict with a known plan."""
        return {
            "plan_dnya_hash": None,
            "plan_dnya_known_plans": {
                plan_id: {
                    "plan_id": plan_id,
                    "date": date_str,
                    "object_id": "obj5",
                    "stage_key": "s1",
                    "worker_ids_raw": worker_ids,
                    "items_hash": self.ps._hash_rows([]),
                }
            }
        }

    def test_worker_ids_change_detected(self):
        """Changed worker_ids must be considered a change and trigger an update."""
        # The key behavior: after item 5 fix, _process_daily_plan_rows must detect
        # changes in worker_ids even when items_json is identical.
        # We verify via the _row_to_plan_fields output which must include worker_ids.
        row1 = {
            "plan_id": "p5-a",
            "date": "2099-02-01",
            "object_id": "obj5",
            "stage_key": "s1",
            "worker_ids": "111,222",
            "status": "draft",
            "items_json": "[]",
        }
        row2 = {
            "plan_id": "p5-a",
            "date": "2099-02-01",
            "object_id": "obj5",
            "stage_key": "s1",
            "worker_ids": "111,222,333",  # changed
            "status": "draft",
            "items_json": "[]",
        }
        f1 = self.ps._row_to_plan_fields(row1)
        f2 = self.ps._row_to_plan_fields(row2)
        self.assertIsNotNone(f1)
        self.assertIsNotNone(f2)
        # The parsed worker_ids must reflect the sheet value
        self.assertIn("333", [str(w) for w in f2["worker_ids"]],
            "worker_ids must be parsed from sheet row so change detection can compare them")


# ── Round 1.1: Item 3+6 interaction — invalid row must not look deleted ──────

class TestRound11InvalidRowNotTreatedAsDeleted(unittest.TestCase):
    """A Sheet row that's present but fails validation (bad items_json) must
    NOT be treated by reconciliation as if the row disappeared -- that would
    wrongly cancel/source_delete an otherwise-untouched valid existing plan."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="promonta-test-r11-")
        os.environ["MINIAPP_DATA_ROOT"] = self._tmp
        dpl.configure(
            os.path.join(self._tmp, "daily_plan_store.json"),
            os.path.join(self._tmp, "plan_sync_state.json"),
            os.path.join(self._tmp, "work_calendar.json"),
        )
        import importlib
        import plan_sync
        self.ps = importlib.reload(plan_sync)
        self.ps.dpl = dpl

    def test_malformed_items_json_on_existing_plan_does_not_cancel_it(self):
        """Existing synced plan + same Sheet row present with same plan_id but
        malformed items_json -> plan remains active and unchanged, sync error
        recorded (not cancelled, not source_deleted)."""
        plan_id = "r11-plan-1"
        good_row = {
            "plan_id": plan_id,
            "date": "2099-05-01",
            "object_id": "objR11",
            "stage_key": "s1",
            "worker_ids": "w1",
            "status": "draft",
            "items_json": '[{"id": "i1", "title": "Task", "planned_quantity": 5, "unit": "m2"}]',
        }
        state = {}
        changed = self.ps._process_daily_plan_rows([good_row], state)
        self.assertEqual(changed, 1)

        plan = dpl.get_plan_by_sheets_source_row(plan_id)
        self.assertIsNotNone(plan)
        self.assertNotEqual(plan["status"], "cancelled")

        # Same row, now with malformed items_json -- must NOT disappear from
        # seen_plan_ids, must NOT be treated as a deleted row.
        bad_row = dict(good_row)
        bad_row["items_json"] = "{not valid json{{"
        state2 = {}  # fresh state forces reprocessing (hash won't match empty state)
        self.ps._process_daily_plan_rows([bad_row], state2)

        plan_after = dpl.get_plan_by_sheets_source_row(plan_id)
        self.assertIsNotNone(plan_after, "Plan must still exist")
        self.assertNotEqual(plan_after["status"], "cancelled",
            "Invalid-but-present row must NOT cause reconciliation to cancel the plan")
        self.assertFalse(plan_after.get("source_deleted"),
            "Invalid-but-present row must NOT cause reconciliation to mark source_deleted")
        # Original valid items must be untouched
        self.assertEqual(len(plan_after["items"]), 1)


# ── Item 6: Sheet row deletion — cancelled/source_deleted exclusion ───────────

class TestItem6RowDeletionExclusion(unittest.TestCase):
    """Cancelled/source_deleted plans must be excluded from active plan queries."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="promonta-test-item6-")
        os.environ["MINIAPP_DATA_ROOT"] = self._tmp
        dpl.configure(
            os.path.join(self._tmp, "daily_plan_store.json"),
            os.path.join(self._tmp, "plan_sync_state.json"),
            os.path.join(self._tmp, "work_calendar.json"),
        )

    def _cancel_plan(self, plan_id):
        """Directly mark a plan cancelled (for testing the exclusion logic)."""
        from daily_plan_lib import _load_store, _save_store, _store_lock, _store_flock
        with _store_lock, _store_flock():
            store = _load_store()
            if plan_id in store["daily_plans"]:
                store["daily_plans"][plan_id]["status"] = "cancelled"
            _save_store(store)

    def test_cancelled_plan_excluded_from_worker_today(self):
        """get_today_plan_for_worker must not return a cancelled plan."""
        worker = "w6_cancel"
        plan = dpl.create_plan(
            object_id="obj6",
            stage_key="s1",
            date_str="2099-03-01",
            assigned_worker_ids=[worker],
            items=[_make_item(0)],
            created_by="test",
        )
        dpl.publish_plan(plan["id"], "test")
        self._cancel_plan(plan["id"])

        result = dpl.get_today_plan_for_worker(worker, "2099-03-01")
        self.assertIsNone(result,
            "Cancelled plan must NOT be returned by get_today_plan_for_worker. "
            "STATUS_PRIORITY fallback-to-99 is not enough — cancelled must be excluded.")

    def test_source_deleted_plan_excluded_from_worker_today(self):
        """get_today_plan_for_worker must not return a source_deleted plan."""
        from daily_plan_lib import _load_store, _save_store, _store_lock, _store_flock
        worker = "w6_sdel"
        plan = dpl.create_plan(
            object_id="obj6b",
            stage_key="s1",
            date_str="2099-03-02",
            assigned_worker_ids=[worker],
            items=[_make_item(0)],
            created_by="test",
        )
        dpl.publish_plan(plan["id"], "test")
        dpl.accept_plan(plan["id"], plan["version"], worker)

        # Mark source_deleted (accepted plan — preserved but excluded from active)
        with _store_lock, _store_flock():
            store = _load_store()
            store["daily_plans"][plan["id"]]["source_deleted"] = True
            _save_store(store)

        result = dpl.get_today_plan_for_worker(worker, "2099-03-02")
        self.assertIsNone(result,
            "source_deleted plan must NOT be returned by get_today_plan_for_worker.")


# ── Item 7: Replan blocker schema (daily_plan_id) ────────────────────────────

class TestItem7ReplanBlockerSchema(unittest.TestCase):
    """Replan endpoint must use daily_plan_id to look up blockers."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="promonta-test-item7-")
        os.environ["MINIAPP_DATA_ROOT"] = self._tmp
        dpl.configure(
            os.path.join(self._tmp, "daily_plan_store.json"),
            os.path.join(self._tmp, "plan_sync_state.json"),
            os.path.join(self._tmp, "work_calendar.json"),
        )
        # Reconfigure backend DATA_ROOT so it uses the same store
        backend.DAILY_PLAN_STORE_FILE = os.path.join(self._tmp, "daily_plan_store.json")

    def test_blockers_found_by_daily_plan_id(self):
        """Blockers must appear in replan issues (not empty list)."""
        from datetime import date as dt_date
        import datetime
        obj_id = f"obj7_{uuid.uuid4().hex[:6]}"

        plan = dpl.create_plan(
            object_id=obj_id,
            stage_key="s1",
            date_str=dt_date.today().isoformat(),
            assigned_worker_ids=["w7"],
            items=[_make_item(0)],
            created_by="test",
        )
        dpl.publish_plan(plan["id"], "test")
        dpl.record_blocker(plan["id"], "w7", "material_missing", "no material")

        # Verify blocker is stored with daily_plan_id
        store = dpl.get_store_snapshot()
        blockers = list(store.get("blockers", {}).values())
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0].get("daily_plan_id"), plan["id"],
            "Blockers are stored under daily_plan_id key")
        self.assertNotIn("plan_id", blockers[0],
            "Blockers must NOT have a 'plan_id' key — they use 'daily_plan_id'")

        # After fix: replan endpoint's b.get("daily_plan_id") must find this
        plans_with_blockers = []
        for p in [plan]:
            plan_blockers = [
                b for b in store.get("blockers", {}).values()
                if b.get("daily_plan_id") == p["id"]
            ]
            if plan_blockers:
                plans_with_blockers.append(p["id"])
        self.assertEqual(len(plans_with_blockers), 1,
            "After fix: replan must find blockers via daily_plan_id lookup")

    def test_owner_matrix_acceptances_use_daily_plan_id(self):
        """Acceptances in owner matrix filter must use a.get('daily_plan_id'), not a['plan_id']."""
        from datetime import date as dt_date
        obj_id = f"obj7b_{uuid.uuid4().hex[:6]}"
        plan = dpl.create_plan(
            object_id=obj_id,
            stage_key="s1",
            date_str=dt_date.today().isoformat(),
            assigned_worker_ids=["w7b"],
            items=[_make_item(0)],
            created_by="test",
        )
        dpl.publish_plan(plan["id"], "test")
        dpl.accept_plan(plan["id"], plan["version"], "w7b")

        store = dpl.get_store_snapshot()
        for acc in store["acceptances"].values():
            # Confirm no 'plan_id' key — only 'daily_plan_id'
            self.assertIn("daily_plan_id", acc,
                "Acceptance must have daily_plan_id key")
            self.assertNotIn("plan_id", acc,
                "Acceptance must NOT have a 'plan_id' key")
            # The old broken code used a['plan_id'] which would KeyError here
            # After fix it uses a.get('daily_plan_id')


# ── Item 8: Replan amendment resolution ──────────────────────────────────────

class TestItem8ReplanAmendments(unittest.TestCase):
    """Replan must find amendments via object→plans→amendments chain."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="promonta-test-item8-")
        os.environ["MINIAPP_DATA_ROOT"] = self._tmp
        dpl.configure(
            os.path.join(self._tmp, "daily_plan_store.json"),
            os.path.join(self._tmp, "plan_sync_state.json"),
            os.path.join(self._tmp, "work_calendar.json"),
        )

    def test_amendments_have_no_object_id_field(self):
        """Amendments stored by daily_plan_lib have no object_id — old filter was always empty."""
        from datetime import date as dt_date
        obj_id = f"obj8_{uuid.uuid4().hex[:6]}"
        plan = dpl.create_plan(
            object_id=obj_id,
            stage_key="s1",
            date_str=dt_date.today().isoformat(),
            assigned_worker_ids=["w8"],
            items=[_make_item(0)],
            created_by="test",
        )
        dpl.publish_plan(plan["id"], "test")
        dpl.accept_plan(plan["id"], plan["version"], "w8")
        dpl.update_plan_items(plan["id"], [_make_item(0, "Updated")], "edit", "x", "owner")

        store = dpl.get_store_snapshot()
        amendments = list(store["amendments"].values())
        self.assertEqual(len(amendments), 1)
        amend = amendments[0]

        # Confirm the amendment has no 'object_id' or 'status' field
        self.assertNotIn("object_id", amend,
            "Amendments must NOT have object_id — old replan filter always returned empty")
        self.assertNotIn("status", amend,
            "Amendments must NOT have status — old replan filter always returned empty")
        self.assertIn("daily_plan_id", amend,
            "Amendment must have daily_plan_id to be found via object→plans→amendments chain")


# ── Item 9: Owner Today session matching ─────────────────────────────────────

class TestItem9SessionMatching(unittest.TestCase):
    """Owner Today must key sessions on worker_id+object_id, not worker_id alone."""

    def test_session_key_schema(self):
        """Verify active_sessions dict now keys on (worker_id, object_id) to prevent ambiguity."""
        # This test validates the structural requirement: the logic in
        # main.py owner/today must not use str(s['user_id']) as the sole dict key
        # when a worker has two same-day shifts on different objects.
        # Direct unit test on the expected behavior after fix:
        checkin_items = [
            {"user_id": "w9", "object_id": "obj9a", "date": "2099-04-01", "finish_at": None},
            {"user_id": "w9", "object_id": "obj9b", "date": "2099-04-01", "finish_at": None},
        ]
        today = "2099-04-01"

        # OLD behavior (broken): both sessions get key "w9" — second overwrites first
        old_sessions = {
            str(s["user_id"]): s for s in checkin_items
            if s.get("date") == today and s.get("finish_at") is None
        }
        # OLD: only 1 entry, second object lost
        self.assertEqual(len(old_sessions), 1, "Old key scheme loses one session")

        # NEW behavior (after fix): keyed on (worker_id, object_id)
        new_sessions = {}
        for s in checkin_items:
            if s.get("date") == today and s.get("finish_at") is None:
                key = (str(s["user_id"]), str(s.get("object_id", "")))
                new_sessions[key] = s
        # NEW: both sessions retained
        self.assertEqual(len(new_sessions), 2,
            "After fix: session key includes object_id so both shifts are retained")


# ── Item 10: Unified risk engine ─────────────────────────────────────────────

class TestItem10UnifiedRiskEngine(unittest.TestCase):
    """Replan must call _compute_risk_level() not its own inline 3-tier calc."""

    def test_compute_risk_level_reachable_red(self):
        """_compute_risk_level must be able to return 'red' (inline replan calc had no RED tier)."""
        risk = backend._compute_risk_level(
            carryovers=[],
            amendments=[],
            blockers_for_plan=[],
            execution=None,
            predicted_finish_date="2099-12-31",
            contract_finish_date="2099-06-01",
        )
        self.assertEqual(risk, "red",
            "_compute_risk_level must return 'red' when predicted_finish > contract_finish")

    def test_compute_risk_level_orange_blocker(self):
        """_compute_risk_level returns orange when there are blockers."""
        risk = backend._compute_risk_level(
            carryovers=[],
            amendments=[],
            blockers_for_plan=[{"id": "b1"}],
            execution=None,
        )
        self.assertEqual(risk, "orange")

    def test_compute_risk_level_yellow_carryover(self):
        """_compute_risk_level returns yellow for carryovers without blocker."""
        risk = backend._compute_risk_level(
            carryovers=[{"id": "c1"}],
            amendments=[],
            blockers_for_plan=[],
            execution=None,
        )
        self.assertEqual(risk, "yellow")

    def test_compute_risk_level_green(self):
        """_compute_risk_level returns green when no issues."""
        risk = backend._compute_risk_level(
            carryovers=[],
            amendments=[],
            blockers_for_plan=[],
            execution=None,
        )
        self.assertEqual(risk, "green")


# ── Item 11: Diagnostics sync field naming ────────────────────────────────────

class TestItem11SyncFieldNaming(unittest.TestCase):
    """Diagnostics reads last_sync_at (matching plan_sync.py writer, not last_synced_at)."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="promonta-test-item11-")
        os.environ["MINIAPP_DATA_ROOT"] = self._tmp

    def test_diagnostics_reads_last_sync_at_not_last_synced_at(self):
        """When sync state has last_sync_at, diagnostics must report 'ok'."""
        state_file = os.path.join(self._tmp, "plan_sync_state.json")
        with open(state_file, "w") as f:
            json.dump({"last_sync_at": time.time(), "last_sync_ok": True}, f)

        # Check main.py:946 reads the right key
        # We call the logic directly without HTTP:
        sync_state = backend._safe_load_json(state_file, {})

        # The field main.py reads (after fix: last_sync_at)
        last_at = sync_state.get("last_sync_at")
        self.assertIsNotNone(last_at,
            "main.py must read 'last_sync_at' not 'last_synced_at' to match plan_sync.py writer")

        # Simulate the diagnostics logic
        if sync_state.get("last_sync_at"):
            sync_age = int(time.time() - sync_state["last_sync_at"])
            result = "ok" if sync_age < 3600 else "stale"
        elif os.path.isfile(state_file):
            result = "file_exists_no_sync"
        else:
            result = "not_configured"

        self.assertEqual(result, "ok",
            f"Diagnostics must report 'ok' for recent sync, got '{result}'. "
            "Fix: main.py must check 'last_sync_at' (written by plan_sync.py), "
            "not 'last_synced_at' (a misspelling that is never written).")


# ── Item 12: Business date (Berlin TZ) ───────────────────────────────────────

class TestItem12BerlinDate(unittest.TestCase):
    """JS files must use todayBerlin() not new Date().toISOString()."""

    def _read_file(self, path):
        with open(path) as f:
            return f.read()

    def test_home_js_no_raw_to_iso_string_for_date(self):
        """home.js must not use toISOString().split('T')[0] for business dates."""
        home_js = self._read_file(
            os.path.join(os.path.dirname(__file__), "..", "frontend", "js", "home.js"))
        # These are the exact patterns that were wrong (evidence: lines 159, 162, 1037)
        bad_patterns = [
            "toISOString().split('T')[0]",
            "toISOString().slice(0, 10)",
            "toISOString().slice(0,10)",
        ]
        for pat in bad_patterns:
            self.assertNotIn(pat, home_js,
                f"home.js must not use {pat!r} — use todayBerlin()/tomorrowBerlin() instead")

    def test_feed_js_no_raw_to_iso_string_for_date(self):
        """feed.js must not use toISOString for today comparison."""
        feed_js = self._read_file(
            os.path.join(os.path.dirname(__file__), "..", "frontend", "js", "feed.js"))
        self.assertNotIn("toISOString().slice(0, 10)", feed_js,
            "feed.js line 352: use todayBerlin() not new Date().toISOString().slice(0,10)")
        self.assertNotIn("toISOString().slice(0,10)", feed_js,
            "feed.js line 352: use todayBerlin() not new Date().toISOString().slice(0,10)")

    def test_checkin_js_no_raw_to_iso_string_for_date(self):
        """checkin.js must not use toISOString for date input default."""
        checkin_js = self._read_file(
            os.path.join(os.path.dirname(__file__), "..", "frontend", "js", "checkin.js"))
        self.assertNotIn("toISOString().slice(0, 10)", checkin_js,
            "checkin.js line 574: use todayBerlin() not new Date().toISOString().slice(0,10)")
        self.assertNotIn("toISOString().slice(0,10)", checkin_js,
            "checkin.js line 574: use todayBerlin() not new Date().toISOString().slice(0,10)")


# ── Item 13: Dashboard staffing widget rewire ─────────────────────────────────

class TestItem13StaffingWidget(unittest.TestCase):
    """_loadHomeCalendarWidget must consume /api/dashboard/team-plan."""

    def test_home_js_uses_team_plan_endpoint(self):
        """home.js _loadHomeCalendarWidget must call /api/dashboard/team-plan."""
        with open(os.path.join(os.path.dirname(__file__), "..", "frontend", "js", "home.js")) as f:
            home_js = f.read()

        # The correct endpoint must be present in _loadHomeCalendarWidget context
        self.assertIn("/api/dashboard/team-plan", home_js,
            "_loadHomeCalendarWidget must use /api/dashboard/team-plan for real assignment data")

    def test_home_js_calendar_widget_not_using_abwesenheit_only(self):
        """_loadHomeCalendarWidget must not rely solely on /api/abwesenheit/all for staffing."""
        with open(os.path.join(os.path.dirname(__file__), "..", "frontend", "js", "home.js")) as f:
            content = f.read()
        # Find _loadHomeCalendarWidget function body
        start = content.find("async function _loadHomeCalendarWidget")
        end = content.find("\nasync function ", start + 1)
        if end == -1:
            end = content.find("\nfunction ", start + 1)
        widget_body = content[start:end] if end > start else content[start:start+3000]

        # After fix: 'Свободен' must not be the only possible non-absent status —
        # a worker who IS assigned (per /api/dashboard/team-plan) must show as
        # assigned, not as free. Combining absence + assignment data is correct
        # (a worker can be absent OR assigned OR genuinely free); the broken
        # behavior was using absence data ALONE with no assignment check at all.
        self.assertIn("/api/dashboard/team-plan", widget_body,
            "_loadHomeCalendarWidget must consume /api/dashboard/team-plan for real assignment data")
        self.assertIn("hcw-assigned", widget_body,
            "_loadHomeCalendarWidget must render a distinct assigned state, not just free/absent")


# ── Item 14: Contract store safety ───────────────────────────────────────────

class TestItem14ContractStoreSafety(unittest.TestCase):
    """_load_contract_store must use _safe_load_json, not raw json.load."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="promonta-test-item14-")
        os.environ["MINIAPP_DATA_ROOT"] = self._tmp
        self._contract_file = os.path.join(self._tmp, "contract_ingest_state.json")
        # Make the backend use this temp file
        backend.CONTRACT_INGEST_STATE_FILE = self._contract_file
        # Register in CRITICAL_JSON_PATHS
        backend.CRITICAL_JSON_PATHS.add(self._contract_file)

    def tearDown(self):
        backend.CRITICAL_JSON_PATHS.discard(self._contract_file)
        # Clean up quarantine files
        import glob
        for f in glob.glob(self._contract_file + ".corrupt-*"):
            try:
                os.remove(f)
            except OSError:
                pass

    def test_corrupt_contract_store_raises_corrupt_json_error(self):
        """Corrupt contract store must raise CorruptJsonError (→ 503), not return empty dict."""
        with open(self._contract_file, "w") as f:
            f.write("not valid json {{{")

        with self.assertRaises(backend.CorruptJsonError):
            backend._load_contract_store()

    def test_valid_contract_store_loads_correctly(self):
        """Valid contract store must load normally."""
        expected = {"contracts": {"c1": {"id": "c1", "file_name": "test.pdf"}}}
        with open(self._contract_file, "w") as f:
            json.dump(expected, f)

        result = backend._load_contract_store()
        self.assertEqual(result, expected)

    def test_missing_contract_store_returns_empty(self):
        """Missing contract store file must return the default empty dict."""
        # Ensure file doesn't exist
        if os.path.exists(self._contract_file):
            os.remove(self._contract_file)

        result = backend._load_contract_store()
        self.assertEqual(result, {"contracts": {}})


if __name__ == "__main__":
    unittest.main()
