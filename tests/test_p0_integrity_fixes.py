"""Regression tests for the P0 DailyPlan acceptance/execution integrity fixes.

Covers three bugs found by owner review:
  P0-1: get_acceptance()/get_accepted_snapshot() returned the wrong (oldest)
        acceptance when a worker has multiple historical acceptances.
  P0-2: accept_plan() could create a "hybrid" acceptance record during a
        plan-version race (requested version's content mixed with the live,
        already-advanced plan's context).
  P0-3: startup reconciliation could resurrect an execution report that the
        normal Finish path's validation would have rejected.

Uses the same plain-function call pattern as tests/test_daily_plan.py (no
HTTP test client), MINIAPP_DATA_ROOT isolated to a temp dir per test.
"""
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def _make_item(idx=1) -> dict:
    return {
        "id": f"item-{idx}",
        "sequence": idx,
        "title": f"Шпаклевание зона {idx}",
        "objective": "Нанести шпаклёвку",
        "planned_quantity": 10.0,
        "unit": "м²",
        "time_estimate_hours": 2.0,
        "work_type_id": "filling_q1_q4",
        "required_tools": [],
        "required_materials": [],
    }


class P0_1_AcceptanceOrderingTests(unittest.TestCase):
    """Multiple acceptances must resolve deterministically to the latest one."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        import daily_plan_lib as dpl
        self.dpl = dpl
        store = os.path.join(self.tmp, 'daily_plan_store.json')
        sync = os.path.join(self.tmp, 'plan_sync_state.json')
        cal = os.path.join(self.tmp, 'work_calendar.json')
        dpl.configure(store, sync, cal)

    def _make_plan(self, workers=('42',), items=None):
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=list(workers), items=items or [_make_item()],
            created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        return plan

    def test_1_v1_then_amendment_v2_then_v2_accept_today_returns_v2(self):
        """v1 accept -> A1, owner amends -> v2, worker accepts v2 -> A2.
        get_acceptance/get_accepted_snapshot (no explicit id) must return A2/v2,
        not A1/v1 by dict-iteration-order."""
        plan = self._make_plan()
        a1 = self.dpl.accept_plan(plan['id'], 1, '42')

        items_v2 = [_make_item(1), _make_item(2)]
        self.dpl.update_plan_items(plan['id'], items_v2, 'sheets_edit', 'Added item', 'owner')
        a2 = self.dpl.accept_plan(plan['id'], 2, '42')

        self.assertNotEqual(a1['id'], a2['id'])

        latest = self.dpl.get_acceptance(plan['id'], '42')
        self.assertEqual(latest['id'], a2['id'])
        self.assertEqual(latest['plan_version'], 2)

        snap = self.dpl.get_accepted_snapshot(plan['id'], '42')
        self.assertEqual(len(snap), 2)  # v2's items (2 items), not v1's (1 item)

    def test_2_historical_v1_acceptance_still_retrievable_explicitly(self):
        """A1 must remain retrievable by its own acceptance_id even after A2 exists."""
        plan = self._make_plan()
        a1 = self.dpl.accept_plan(plan['id'], 1, '42')
        items_v2 = [_make_item(1), _make_item(2)]
        self.dpl.update_plan_items(plan['id'], items_v2, 'sheets_edit', 'Added item', 'owner')
        self.dpl.accept_plan(plan['id'], 2, '42')

        snap_v1 = self.dpl.get_accepted_snapshot(plan['id'], '42', acceptance_id=a1['id'])
        self.assertEqual(len(snap_v1), 1)  # explicit lookup still resolves v1

        store = self.dpl._load_store()
        self.assertIn(a1['id'], store['acceptances'])  # A1 never deleted/rewritten
        self.assertEqual(store['acceptances'][a1['id']]['plan_version'], 1)

    def test_3_worker_remains_bound_to_v1_until_v2_explicitly_accepted(self):
        """v1 accepted, v2 exists (amendment_pending) but worker has NOT accepted
        v2 yet -- current accepted snapshot stays v1, pending amendment visible,
        v2 must never be silently treated as accepted."""
        plan = self._make_plan()
        self.dpl.accept_plan(plan['id'], 1, '42')
        items_v2 = [_make_item(1), _make_item(2)]
        self.dpl.update_plan_items(plan['id'], items_v2, 'sheets_edit', 'Added item', 'owner')

        acceptance = self.dpl.get_acceptance(plan['id'], '42')
        self.assertEqual(acceptance['plan_version'], 1)  # still bound to v1

        snap = self.dpl.get_accepted_snapshot(plan['id'], '42')
        self.assertEqual(len(snap), 1)  # v1 items, not v2's

        pending = self.dpl.get_pending_amendments(plan['id'], '42')
        self.assertEqual(len(pending), 1)  # amendment visible, not auto-acked

        plan_after = self.dpl.get_plan(plan['id'])
        self.assertEqual(plan_after['status'], 'amendment_pending')  # not silently "accepted"

    def test_multi_worker_plan_each_gets_own_latest_acceptance(self):
        """Two workers on the same plan, each accepting different versions at
        different times -- each must independently resolve to their own latest,
        never cross-contaminate."""
        plan = self._make_plan(workers=('42', '99'))
        self.dpl.accept_plan(plan['id'], 1, '42')
        # 99 hasn't accepted yet.
        items_v2 = [_make_item(1), _make_item(2)]
        self.dpl.update_plan_items(plan['id'], items_v2, 'sheets_edit', 'Added item', 'owner')
        # 42 accepts the amendment (v2); 99 still on nothing.
        self.dpl.accept_plan(plan['id'], 2, '42')

        acc_42 = self.dpl.get_acceptance(plan['id'], '42')
        acc_99 = self.dpl.get_acceptance(plan['id'], '99')
        self.assertEqual(acc_42['plan_version'], 2)
        self.assertIsNone(acc_99)


class P0_2_VersionRaceTests(unittest.TestCase):
    """accept_plan() must never create a hybrid acceptance during a version race."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        import daily_plan_lib as dpl
        self.dpl = dpl
        store = os.path.join(self.tmp, 'daily_plan_store.json')
        sync = os.path.join(self.tmp, 'plan_sync_state.json')
        cal = os.path.join(self.tmp, 'work_calendar.json')
        dpl.configure(store, sync, cal)

    def _make_plan(self):
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[_make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        return plan

    def test_4_stale_version_accept_rejected_no_hybrid_created(self):
        """Simulates: route reads plan at v1, plan advances to v2 before the
        accept call reaches the lock -- accepting v1 against the now-v2 plan
        must be rejected, not create a hybrid record."""
        plan = self._make_plan()
        # Plan advances to v2 (simulating a concurrent Sheets edit/amendment)
        # before the worker's accept(v1) call is processed. No prior
        # acceptance of v1 exists, so this is a genuine stale-version race,
        # not an idempotent replay.
        self.dpl.update_plan_items(plan['id'], [_make_item(1), _make_item(2)],
                                    'sheets_edit', 'Added item', 'owner')

        with self.assertRaises(self.dpl.StaleAcceptanceError):
            self.dpl.accept_plan(plan['id'], 1, '42')

        store = self.dpl._load_store()
        plan_acceptances = [
            a for a in store['acceptances'].values()
            if a['daily_plan_id'] == plan['id'] and a['worker_id'] == '42'
        ]
        self.assertEqual(len(plan_acceptances), 0)  # no hybrid (or any) acceptance created

        # Worker can retry against the now-current version and succeed.
        acceptance = self.dpl.accept_plan(plan['id'], 2, '42')
        self.assertEqual(acceptance['plan_version'], 2)
        self.assertEqual(acceptance['accepted_context_snapshot']['plan_version'], 2)

    def test_5_retry_of_already_accepted_version_stays_idempotent(self):
        """If the worker genuinely accepted v1 BEFORE the plan changed, a retry
        of that same v1 acceptance must still succeed (idempotent), even
        though the plan has since moved on to v2."""
        plan = self._make_plan()
        a1 = self.dpl.accept_plan(plan['id'], 1, '42')  # accepted while plan is still v1

        self.dpl.update_plan_items(plan['id'], [_make_item(1), _make_item(2)],
                                    'sheets_edit', 'Added item', 'owner')  # plan -> v2

        # Retry of the SAME v1 acceptance (e.g. a duplicate request) must
        # return the existing record, not raise StaleAcceptanceError.
        a1_retry = self.dpl.accept_plan(plan['id'], 1, '42')
        self.assertEqual(a1['id'], a1_retry['id'])

    def test_no_hybrid_fields_possible_by_construction(self):
        """Direct check that a rejected stale accept never touches the store at
        all -- accepted_snapshot_hash/plan_version/accepted_context_snapshot
        must never end up describing different plan versions."""
        plan = self._make_plan()
        self.dpl.update_plan_items(plan['id'], [_make_item(1), _make_item(2)],
                                    'sheets_edit', 'Added item', 'owner')
        store_before = self.dpl._load_store()
        with self.assertRaises(self.dpl.StaleAcceptanceError):
            self.dpl.accept_plan(plan['id'], 1, '42')
        store_after = self.dpl._load_store()
        self.assertEqual(store_before['acceptances'], store_after['acceptances'])


class P0_3_ExecutionIntegrityTests(unittest.TestCase):
    """apply_daily_execution() must enforce the same invariants regardless of
    whether it's called from the normal Finish path or crash-recovery
    reconciliation/retry."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        import daily_plan_lib as dpl
        self.dpl = dpl
        store = os.path.join(self.tmp, 'daily_plan_store.json')
        sync = os.path.join(self.tmp, 'plan_sync_state.json')
        cal = os.path.join(self.tmp, 'work_calendar.json')
        dpl.configure(store, sync, cal)

    def _make_accepted_plan(self, workers=('42',), object_id='OBJ-1', date_str='2026-09-10'):
        plan = self.dpl.create_plan(
            object_id=object_id, stage_key='OBJ-1-S1', date_str=date_str,
            assigned_worker_ids=list(workers), items=[_make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        acceptance = self.dpl.accept_plan(plan['id'], 1, workers[0])
        return plan, acceptance

    def _valid_results(self):
        return [{"item_id": "item-1", "status": "done", "actual_quantity": 10.0}]

    def test_6_finish_valid_execution_against_exact_acceptance_succeeds(self):
        plan, acceptance = self._make_accepted_plan()
        execution = self.dpl.apply_daily_execution(
            session_id='sess-1', daily_plan_id=plan['id'], plan_version=1,
            worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
            item_results=self._valid_results(), acceptance_id=acceptance['id'],
        )
        self.assertEqual(execution['session_id'], 'sess-1')
        self.assertEqual(execution['acceptance_id'], acceptance['id'])

    def test_7_wrong_worker_rejected(self):
        plan, acceptance = self._make_accepted_plan()
        with self.assertRaises(self.dpl.ExecutionValidationError):
            self.dpl.apply_daily_execution(
                session_id='sess-2', daily_plan_id=plan['id'], plan_version=1,
                worker_id='99', date_str='2026-09-10', object_id='OBJ-1',
                item_results=self._valid_results(), acceptance_id=acceptance['id'],
            )

    def test_8_wrong_object_rejected(self):
        plan, acceptance = self._make_accepted_plan()
        with self.assertRaises(self.dpl.ExecutionValidationError):
            self.dpl.apply_daily_execution(
                session_id='sess-3', daily_plan_id=plan['id'], plan_version=1,
                worker_id='42', date_str='2026-09-10', object_id='OBJ-WRONG',
                item_results=self._valid_results(), acceptance_id=acceptance['id'],
            )

    def test_9_wrong_date_rejected(self):
        plan, acceptance = self._make_accepted_plan()
        with self.assertRaises(self.dpl.ExecutionValidationError):
            self.dpl.apply_daily_execution(
                session_id='sess-4', daily_plan_id=plan['id'], plan_version=1,
                worker_id='42', date_str='2026-09-11', object_id='OBJ-1',
                item_results=self._valid_results(), acceptance_id=acceptance['id'],
            )

    def test_10_wrong_plan_version_rejected(self):
        plan, acceptance = self._make_accepted_plan()
        with self.assertRaises(self.dpl.ExecutionValidationError):
            self.dpl.apply_daily_execution(
                session_id='sess-5', daily_plan_id=plan['id'], plan_version=99,
                worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
                item_results=self._valid_results(), acceptance_id=acceptance['id'],
            )

    def test_11_unknown_item_id_rejected(self):
        plan, acceptance = self._make_accepted_plan()
        bad_results = [{"item_id": "item-does-not-exist", "status": "done", "actual_quantity": 1.0}]
        with self.assertRaises(self.dpl.ExecutionValidationError):
            self.dpl.apply_daily_execution(
                session_id='sess-6', daily_plan_id=plan['id'], plan_version=1,
                worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
                item_results=bad_results, acceptance_id=acceptance['id'],
            )

    def test_11b_unsupported_status_rejected(self):
        plan, acceptance = self._make_accepted_plan()
        bad_results = [{"item_id": "item-1", "status": "definitely_not_a_real_status"}]
        with self.assertRaises(self.dpl.ExecutionValidationError):
            self.dpl.apply_daily_execution(
                session_id='sess-6b', daily_plan_id=plan['id'], plan_version=1,
                worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
                item_results=bad_results, acceptance_id=acceptance['id'],
            )

    def test_unknown_acceptance_id_rejected(self):
        plan, _ = self._make_accepted_plan()
        with self.assertRaises(self.dpl.ExecutionValidationError):
            self.dpl.apply_daily_execution(
                session_id='sess-6c', daily_plan_id=plan['id'], plan_version=1,
                worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
                item_results=self._valid_results(), acceptance_id='does-not-exist',
            )

    def test_nonexistent_plan_rejected(self):
        with self.assertRaises(self.dpl.ExecutionValidationError):
            self.dpl.apply_daily_execution(
                session_id='sess-6d', daily_plan_id='NONEXISTENT', plan_version=1,
                worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
                item_results=self._valid_results(), acceptance_id=None,
            )

    def test_12_restart_reconciliation_cannot_resurrect_rejected_execution(self):
        """The exact scenario from the bug report: a report that
        validate_execution_against_acceptance() would reject must be rejected
        identically whether called inline (Finish) or via the crash-recovery
        path -- simulated here by calling apply_daily_execution the same way
        _retry_pending_outbox_events() would (with acceptance_id carried
        through), proving the SAME validator gates both paths."""
        plan, acceptance = self._make_accepted_plan()
        # A "resurrected" report claiming a different object than what was
        # actually accepted -- this must be rejected exactly like it would be
        # inline in checkin_finish, not silently applied because it arrived
        # via a different call site.
        bad_results = self._valid_results()
        with self.assertRaises(self.dpl.ExecutionValidationError):
            self.dpl.apply_daily_execution(
                session_id='sess-resurrect', daily_plan_id=plan['id'], plan_version=1,
                worker_id='42', date_str='2026-09-10', object_id='OBJ-WRONG-RESURRECTED',
                item_results=bad_results, acceptance_id=acceptance['id'],
            )
        # And it must not have been applied as a side effect of raising.
        store = self.dpl._load_store()
        self.assertNotIn('sess-resurrect', store['executions'])

    def test_13_crash_after_apply_plus_retry_no_duplicate_execution(self):
        """apply_daily_execution must remain idempotent by session_id even
        when the acceptance_id path is used."""
        plan, acceptance = self._make_accepted_plan()
        e1 = self.dpl.apply_daily_execution(
            session_id='sess-idem', daily_plan_id=plan['id'], plan_version=1,
            worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
            item_results=self._valid_results(), acceptance_id=acceptance['id'],
        )
        e2 = self.dpl.apply_daily_execution(
            session_id='sess-idem', daily_plan_id=plan['id'], plan_version=1,
            worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
            item_results=self._valid_results(), acceptance_id=acceptance['id'],
        )
        self.assertEqual(e1, e2)
        store = self.dpl._load_store()
        self.assertEqual(len(store['executions']), 1)

    def test_14_carryover_remains_idempotent(self):
        plan, acceptance = self._make_accepted_plan()
        partial_results = [{"item_id": "item-1", "status": "partial", "actual_quantity": 4.0}]
        self.dpl.apply_daily_execution(
            session_id='sess-carry', daily_plan_id=plan['id'], plan_version=1,
            worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
            item_results=partial_results, acceptance_id=acceptance['id'],
        )
        store = self.dpl._load_store()
        carryovers = [c for c in store['carryovers'].values() if c['source_plan_id'] == plan['id']]
        self.assertEqual(len(carryovers), 1)
        self.assertEqual(carryovers[0]['remaining_quantity'], 6.0)

        # Idempotent retry (same session_id) must not double the carryover.
        self.dpl.apply_daily_execution(
            session_id='sess-carry', daily_plan_id=plan['id'], plan_version=1,
            worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
            item_results=partial_results, acceptance_id=acceptance['id'],
        )
        store2 = self.dpl._load_store()
        carryovers2 = [c for c in store2['carryovers'].values() if c['source_plan_id'] == plan['id']]
        self.assertEqual(len(carryovers2), 1)

    def test_15_multi_worker_plan_still_works(self):
        plan, acceptance_42 = self._make_accepted_plan(workers=('42', '99'))
        acceptance_99 = self.dpl.accept_plan(plan['id'], 1, '99')

        self.dpl.apply_daily_execution(
            session_id='sess-multi-42', daily_plan_id=plan['id'], plan_version=1,
            worker_id='42', date_str='2026-09-10', object_id='OBJ-1',
            item_results=self._valid_results(), acceptance_id=acceptance_42['id'],
        )
        plan_after_first = self.dpl.get_plan(plan['id'])
        self.assertEqual(plan_after_first['status'], 'in_progress')  # not yet completed

        self.dpl.apply_daily_execution(
            session_id='sess-multi-99', daily_plan_id=plan['id'], plan_version=1,
            worker_id='99', date_str='2026-09-10', object_id='OBJ-1',
            item_results=self._valid_results(), acceptance_id=acceptance_99['id'],
        )
        plan_after_both = self.dpl.get_plan(plan['id'])
        self.assertEqual(plan_after_both['status'], 'completed')

    def test_16_accepted_v3_owner_publishes_v4_worker_stays_on_v3(self):
        """Worker accepted v3; owner creates v4 (another amendment); worker
        remains bound to v3 until they explicitly accept/acknowledge v4."""
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[_make_item(1)], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')
        self.dpl.accept_plan(plan['id'], 1, '42')  # v1
        self.dpl.update_plan_items(plan['id'], [_make_item(1), _make_item(2)],
                                    'sheets_edit', 'v2', 'owner')
        self.dpl.accept_plan(plan['id'], 2, '42')  # v2
        self.dpl.update_plan_items(plan['id'], [_make_item(1), _make_item(2), _make_item(3)],
                                    'sheets_edit', 'v3', 'owner')
        acceptance_v3 = self.dpl.accept_plan(plan['id'], 3, '42')  # v3
        self.assertEqual(acceptance_v3['plan_version'], 3)

        # Owner publishes v4 (another amendment) -- worker has NOT acted on it.
        self.dpl.update_plan_items(
            plan['id'], [_make_item(1), _make_item(2), _make_item(3), _make_item(4)],
            'sheets_edit', 'v4', 'owner',
        )

        latest = self.dpl.get_acceptance(plan['id'], '42')
        self.assertEqual(latest['id'], acceptance_v3['id'])
        self.assertEqual(latest['plan_version'], 3)  # still bound to v3, not v4

        snap = self.dpl.get_accepted_snapshot(plan['id'], '42')
        self.assertEqual(len(snap), 3)  # v3's 3 items, not v4's 4


class P0_ConcurrencyTests(unittest.TestCase):
    """Concurrency-focused regression: the version-race window described in
    P0-2, exercised with real thread interleaving rather than a simulated
    sequential race."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        import daily_plan_lib as dpl
        self.dpl = dpl
        store = os.path.join(self.tmp, 'daily_plan_store.json')
        sync = os.path.join(self.tmp, 'plan_sync_state.json')
        cal = os.path.join(self.tmp, 'work_calendar.json')
        dpl.configure(store, sync, cal)

    def test_concurrent_stale_accept_and_amend_no_hybrid(self):
        """One thread tries to accept v1 while another concurrently amends the
        plan to v2 -- whichever lands first wins cleanly; the loser must see
        either a clean success (if its accept actually landed first) or a
        clean StaleAcceptanceError, never a corrupted/hybrid acceptance."""
        plan = self.dpl.create_plan(
            object_id='OBJ-1', stage_key='OBJ-1-S1', date_str='2026-09-10',
            assigned_worker_ids=['42'], items=[_make_item()], created_by='owner',
        )
        self.dpl.publish_plan(plan['id'], 'owner')

        results = []

        def do_accept():
            try:
                a = self.dpl.accept_plan(plan['id'], 1, '42')
                results.append(('accept', a))
            except self.dpl.StaleAcceptanceError as e:
                results.append(('stale', e))

        def do_amend():
            try:
                self.dpl.update_plan_items(plan['id'], [_make_item(1), _make_item(2)],
                                            'sheets_edit', 'race', 'owner')
                results.append(('amend', None))
            except Exception as e:
                results.append(('amend_error', e))

        threads = [threading.Thread(target=do_accept), threading.Thread(target=do_amend)]
        for t in threads: t.start()
        for t in threads: t.join()

        # Whatever happened, the store must never contain a hybrid record:
        # every stored acceptance's plan_version must match a real version
        # record's version number with a consistent content_hash.
        store = self.dpl._load_store()
        for acc in store['acceptances'].values():
            versions = store['versions'].get(acc['daily_plan_id'], [])
            matching = [v for v in versions if v['version'] == acc['plan_version']]
            self.assertEqual(len(matching), 1)
            self.assertEqual(acc['accepted_snapshot_hash'], matching[0]['content_hash'])
            self.assertEqual(acc['accepted_context_snapshot']['plan_version'], acc['plan_version'])


if __name__ == '__main__':
    unittest.main()
