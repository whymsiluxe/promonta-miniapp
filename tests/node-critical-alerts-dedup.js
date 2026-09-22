// Runtime regression test (Node, no browser needed) for a P0 found live on a
// real device during the 22.09 iPhone screenshot audit: critical-alerts.js's
// poll loop wholesale-replaced its local queue on every 15s tick with no
// id-based dedup, and closed/advanced the queue by ARRAY POSITION
// (queue.shift()), not by the id of the alert actually being closed. A device
// confirmed this produces stacked, near-identical alert popups.
//
// Runs via plain `node`, no framework -- consistent with this repo's other
// node-*.js runtime scripts. The ack-then-never-resurrected invariant (the
// other half of the owner's spec) is covered by
// test_critical_alerts_queue_frontend_contract.py as a source-assertion,
// since exercising the real network-backed _ackCriticalAlert() here would
// need a fetch/api mock deep enough to not really prove anything beyond what
// the source-assertion already locks in more directly.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'critical-alerts.js'), 'utf-8');

function makeSandbox() {
  const shownModals = [];

  const sandbox = {
    document: {
      getElementById: () => ({ addEventListener: () => {}, remove: () => {} }),
      createElement: () => ({ id: '', innerHTML: '', appendChild: () => {} }),
      body: { appendChild: () => {} },
      addEventListener: () => {},
    },
    api: async () => sandbox._nextApiResponse,
    hapticImpact: () => {},
    esc: (s) => s,
    showToast: () => {},
    setTimeout: (fn) => fn(),
    clearInterval: () => {},
    setInterval: () => 0,
    console,
    _shownModals: shownModals,
    _nextApiResponse: { alerts: [] },
  };

  // Record every alert _showCriticalAlertModal is asked to display -- this
  // test is about queue/dedup logic, not modal HTML/DOM structure.
  const patchedSrc = SRC.replace(
    'function _showCriticalAlertModal(alert) {',
    'function _showCriticalAlertModal(alert) { _shownModals.push(alert);'
  );

  vm.createContext(sandbox);
  vm.runInContext(
    patchedSrc + '\nthis._pollCriticalAlerts = _pollCriticalAlerts;',
    sandbox,
    { filename: 'critical-alerts.js' }
  );
  return sandbox;
}

async function main() {
  let allPassed = true;
  const sandbox = makeSandbox();
  const alertA = { id: 'alert-A', title: 'Test alert A', target_user_id: '1' };

  sandbox._nextApiResponse = { alerts: [alertA] };
  await sandbox._pollCriticalAlerts();
  await sandbox._pollCriticalAlerts();
  await sandbox._pollCriticalAlerts();

  try {
    if (sandbox._shownModals.length !== 1) {
      throw new Error(`expected exactly 1 modal shown across 3 polls returning the same alert, got ${sandbox._shownModals.length}`);
    }
    if (sandbox._shownModals[0].id !== 'alert-A') {
      throw new Error(`expected the shown modal to be alert-A, got ${JSON.stringify(sandbox._shownModals[0])}`);
    }
    console.log('PASS: same alert returned on 3 consecutive polls shows exactly 1 modal');
  } catch (e) {
    console.error('FAIL: same alert returned on 3 consecutive polls shows exactly 1 modal');
    console.error(`  ${e.message}`);
    allPassed = false;
  }

  process.exit(allPassed ? 0 : 1);
}

main();
