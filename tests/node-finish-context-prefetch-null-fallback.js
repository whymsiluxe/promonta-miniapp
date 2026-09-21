// Runtime regression test (Node, no browser needed) for a P0 found in round-4
// owner review of the fix-shift-start merge: _prefetchFinishContextAfterStart()
// checked mere field PRESENCE (Object.prototype.hasOwnProperty) instead of
// whether the field is non-null. checkin_start()'s own best-effort try/except
// around _build_finish_context() can legitimately send back
// `finish_context: null` if that call raised server-side -- hasOwnProperty()
// is still true for a null value, so the function returned early without ever
// attempting the live-GET fallback, silently leaving no offline cache at all.
//
// Runs via plain `node`, no framework -- consistent with this repo's other
// node-*.js runtime scripts. Exits 0 on pass, 1 on failure with the failing
// assertion printed.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'finish-wizard.js'), 'utf-8');

function makeLocalStorage() {
  const store = {};
  return {
    getItem(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
    setItem(k, v) { store[k] = String(v); },
    removeItem(k) { delete store[k]; },
  };
}

async function runScenario({ label, startResponse, apiShouldBeCalled, apiResponse, apiThrows, assert }) {
  let apiCalled = false;
  const localStorage = makeLocalStorage();
  const sandbox = {
    localStorage,
    api: async (url) => {
      apiCalled = true;
      if (apiThrows) throw new Error(apiThrows);
      return apiResponse;
    },
    console,
    esc: (s) => s,
    // finish-wizard.js has module-level side effects (window.addEventListener
    // for online/offline outbox retry) unrelated to the function under test --
    // stub just enough of `window` for the script to evaluate without a DOM.
    window: { addEventListener: () => {}, removeEventListener: () => {} },
    document: { getElementById: () => null, addEventListener: () => {} },
    navigator: { onLine: true },
    setTimeout, clearTimeout, setInterval, clearInterval,
  };
  vm.createContext(sandbox);
  vm.runInContext(
    SRC + '\nthis._prefetchFinishContextAfterStart = _prefetchFinishContextAfterStart; this._fwFinishContextCacheKey = _fwFinishContextCacheKey;',
    sandbox,
    { filename: 'finish-wizard.js' }
  );

  await sandbox._prefetchFinishContextAfterStart('sess-1', startResponse);

  try {
    if (apiShouldBeCalled !== undefined) {
      if (apiShouldBeCalled && !apiCalled) throw new Error('expected the live GET fallback to be called, it was not');
      if (!apiShouldBeCalled && apiCalled) throw new Error('expected the live GET fallback NOT to be called, it was');
    }
    const cached = localStorage.getItem(sandbox._fwFinishContextCacheKey('sess-1'));
    assert(cached ? JSON.parse(cached) : null);
    console.log(`PASS: ${label}`);
    return true;
  } catch (e) {
    console.error(`FAIL: ${label}`);
    console.error(`  ${e.message}`);
    return false;
  }
}

async function main() {
  let allPassed = true;

  allPassed = await runScenario({
    label: 'finish_context: null in Start response falls back to a live GET, not silently skipped',
    startResponse: { id: 'sess-1', finish_context: null },
    apiShouldBeCalled: true,
    apiResponse: { has_plan: true, plan: { id: 'p1', version: 1, items: [{ id: 'i1' }] } },
    assert: (cached) => {
      if (!cached || !cached.has_plan) throw new Error('expected the fallback GET response to be cached, got: ' + JSON.stringify(cached));
    },
  }) && allPassed;

  allPassed = await runScenario({
    label: 'finish_context field absent entirely also falls back to a live GET (pre-existing behavior, still correct)',
    startResponse: { id: 'sess-1' },
    apiShouldBeCalled: true,
    apiResponse: { has_plan: true, plan: { id: 'p1', version: 1, items: [{ id: 'i1' }] } },
    assert: (cached) => {
      if (!cached || !cached.has_plan) throw new Error('expected the fallback GET response to be cached, got: ' + JSON.stringify(cached));
    },
  }) && allPassed;

  allPassed = await runScenario({
    label: 'finish_context populated and has_plan:true is cached directly, no live GET needed',
    startResponse: { id: 'sess-1', finish_context: { has_plan: true, plan: { id: 'p1', version: 1, items: [{ id: 'i1' }] } } },
    apiShouldBeCalled: false,
    assert: (cached) => {
      if (!cached || !cached.has_plan) throw new Error('expected the embedded response to be cached directly, got: ' + JSON.stringify(cached));
    },
  }) && allPassed;

  allPassed = await runScenario({
    label: 'finish_context populated with has_plan:false is NOT cached (matches existing "nothing to cache" behavior) and skips the live GET',
    startResponse: { id: 'sess-1', finish_context: { has_plan: false } },
    apiShouldBeCalled: false,
    assert: (cached) => {
      if (cached !== null) throw new Error('expected nothing cached for a plan-less shift, got: ' + JSON.stringify(cached));
    },
  }) && allPassed;

  process.exit(allPassed ? 0 : 1);
}

main();
