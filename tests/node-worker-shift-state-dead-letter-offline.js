// Runtime regression test (Node, no browser needed) for a P0 found in round-3
// owner review of the fix-shift-start merge: resolveWorkerShiftState() checked
// dead_letter records AFTER the server, but BEFORE local state, on the branch
// where the server call itself failed (offline). Scenario this missed:
//   - worker is genuinely mid-shift on OBJECT-B (localStorage has the real
//     ACTIVE session)
//   - an unrelated dead_letter from OBJECT-A's already-finished, permanently-
//     failed Finish is still sitting in the outbox
//   - connectivity drops (server call throws)
// Expected: the resolver must return OBJECT-B's real ACTIVE state (optionally
// annotated with the stale dead_letter as a non-blocking syncWarning), not
// SYNC_ERROR -- the same "an unrelated dead_letter must never override a real
// session it doesn't belong to" invariant the original P0 fixed, just for the
// offline branch that fix didn't cover.
//
// Runs via plain `node`, no framework -- consistent with this repo's other
// node-* smoke scripts (see docs/TESTING.md). Exits 0 on pass, 1 on failure
// with the failing assertion printed.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'worker-shift-state.js'), 'utf-8');

function makeLocalStorage(initial) {
  const store = { ...initial };
  return {
    get length() { return Object.keys(store).length; },
    key(i) { return Object.keys(store)[i] ?? null; },
    getItem(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
    setItem(k, v) { store[k] = String(v); },
    removeItem(k) { delete store[k]; },
  };
}

async function runScenario({ label, localStorageData, outboxRecords, serverThrows, assert }) {
  const sandbox = {
    localStorage: makeLocalStorage(localStorageData),
    appOutboxList: async (kind) => (outboxRecords || []).filter(r => r.kind === kind),
    api: async () => { throw new Error(serverThrows || 'network down'); },
    _setActiveCheckinSession: () => {},
    console,
  };
  vm.createContext(sandbox);
  // SRC declares its exports as top-level `const`, which vm.runInContext does
  // NOT leak onto the sandbox object (unlike `var`) -- explicitly assign the
  // ones this test needs after evaluating the script in the same context.
  vm.runInContext(
    SRC + '\nthis.resolveWorkerShiftState = resolveWorkerShiftState; this.WORKER_SHIFT_STATE = WORKER_SHIFT_STATE;',
    sandbox,
    { filename: 'worker-shift-state.js' }
  );

  const result = await sandbox.resolveWorkerShiftState({ objectId: null });
  try {
    assert(result, sandbox);
    console.log(`PASS: ${label}`);
    return true;
  } catch (e) {
    console.error(`FAIL: ${label}`);
    console.error(`  ${e.message}`);
    console.error(`  actual result: ${JSON.stringify(result)}`);
    return false;
  }
}

async function main() {
  let allPassed = true;

  allPassed = await runScenario({
    label: 'server unavailable + local ACTIVE B + unrelated dead_letter A => ACTIVE B, not SYNC_ERROR',
    localStorageData: {
      checkin_session_OBJ_B: JSON.stringify({ id: 'sess-b', finished: false, pauseStartedAt: null }),
    },
    outboxRecords: [
      { kind: 'checkin-finish', objectId: 'OBJ_A', state: 'dead_letter', sessionId: 'sess-a-old', lastError: 'permanent fail' },
    ],
    assert: (result, sandbox) => {
      if (result.state !== sandbox.WORKER_SHIFT_STATE.ACTIVE) {
        throw new Error(`expected ACTIVE, got ${result.state}`);
      }
      if (String(result.objectId) !== 'OBJ_B') {
        throw new Error(`expected objectId OBJ_B, got ${result.objectId}`);
      }
    },
  }) && allPassed;

  allPassed = await runScenario({
    label: 'server unavailable + local PAUSED B + unrelated dead_letter A => PAUSED B with syncWarning, not SYNC_ERROR',
    localStorageData: {
      checkin_session_OBJ_B: JSON.stringify({ id: 'sess-b', finished: false, pauseStartedAt: 1700000000 }),
    },
    outboxRecords: [
      { kind: 'checkin-start', objectId: 'OBJ_A', state: 'dead_letter', lastError: 'permanent fail' },
    ],
    assert: (result, sandbox) => {
      if (result.state !== sandbox.WORKER_SHIFT_STATE.PAUSED) {
        throw new Error(`expected PAUSED, got ${result.state}`);
      }
      if (!result.syncWarning) {
        throw new Error('expected a syncWarning carrying the unrelated dead_letter, got none');
      }
      if (String(result.syncWarning.objectId) !== 'OBJ_A') {
        throw new Error(`expected syncWarning.objectId OBJ_A, got ${result.syncWarning.objectId}`);
      }
    },
  }) && allPassed;

  allPassed = await runScenario({
    label: 'server unavailable + NO local active session + dead_letter A => SYNC_ERROR (dead_letter still surfaces when there is nothing valid to protect)',
    localStorageData: {},
    outboxRecords: [
      { kind: 'checkin-finish', objectId: 'OBJ_A', state: 'dead_letter', sessionId: 'sess-a-old', lastError: 'permanent fail' },
    ],
    assert: (result, sandbox) => {
      if (result.state !== sandbox.WORKER_SHIFT_STATE.SYNC_ERROR) {
        throw new Error(`expected SYNC_ERROR (no valid local state to protect), got ${result.state}`);
      }
    },
  }) && allPassed;

  process.exit(allPassed ? 0 : 1);
}

main();
