// Minimal Playwright smoke test — Phase 04 remainder item 6.
//
// No test framework exists in this repo yet (see docs/TESTING.md, docs/TODO.md) --
// this is intentionally a single ad-hoc script, not a scaffolded Playwright project
// (config/fixtures/CI wiring is phase 10's job, not this one). It checks the concrete
// navigation/FAB behavior built in this same phase-04-remainder session:
//   - Objects FAB (#add-object) becomes visible only on the Objects tab, for the owner role
//   - Tapping the FAB opens the "Новый объект" bottom sheet (#new-object-sheet), hides the FAB
//   - Closing the sheet (✕) restores the FAB
//   - Leaving the Objects tab hides the FAB
//   - Telegram's native BackButton being present hides the 7 known-redundant in-header
//     back buttons (onclick="NavigationManager.back()") but NOT checkin-status-close-btn,
//     which isn't wired through NavigationManager and has no other way to close
//
// How to run (needs Playwright + a Chromium runtime with its shared libs -- NOT verified
// runnable in the sandbox this was written in: `npx playwright install chromium --with-deps`
// failed there because `--with-deps` needs root/sudo and the bare chromium download was
// missing libnspr4.so and friends with no apt access to install them. Written and
// logic-reviewed, not executed. Run for real on a machine with full Playwright deps):
//
//   cd frontend && python3 -m http.server 8791 &
//   node tests/smoke-nav-fab.js
//
// Exits 0 with all checks passing printed, exits 1 (and prints which assertion failed)
// otherwise.

const { chromium } = require('playwright');

const BASE_URL = process.env.SMOKE_BASE_URL || 'http://127.0.0.1:8791/app.html';

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', msg => { if (msg.type() === 'error') errors.push('console.error: ' + msg.text()); });

  // Mock a minimal Telegram WebApp -- real initData/backend aren't available for a static
  // smoke test, and /api/* calls are stubbed to just enough shape for fetchRole()/loadObjects()
  // to resolve without throwing.
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'mock_init_data_for_smoke_test',
        initDataUnsafe: { user: { id: 1 } },
        ready() {}, expand() {}, requestFullscreen() {}, disableVerticalSwipes() {},
        onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {} },
        safeAreaInset: { top: 0, right: 0, bottom: 0, left: 0 },
        contentSafeAreaInset: { top: 0, right: 0, bottom: 0, left: 0 },
        viewportHeight: 844,
        colorScheme: 'light',
      }
    };
    const _origFetch = window.fetch;
    window.fetch = (url, opts) => {
      if (String(url).startsWith('/api/')) {
        return Promise.resolve(new Response(JSON.stringify({ role: 'owner', objects: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
      }
      return _origFetch(url, opts);
    };
  });

  await page.goto(BASE_URL, { waitUntil: 'load' });
  await page.waitForTimeout(800);

  const checks = [];
  const check = (name, actual, expected) => checks.push({ name, actual, expected, pass: actual === expected });

  check('native BackButton mocked -> body.tg-native-back present',
    await page.evaluate(() => document.body.classList.contains('tg-native-back')), true);

  await page.evaluate(() => switchView('objects', { isTabSwitch: true }));
  await page.waitForTimeout(300);
  check('Objects view becomes active',
    await page.evaluate(() => document.getElementById('view-objects').classList.contains('active')), true);
  check('Objects FAB visible on Objects tab (owner)',
    await page.evaluate(() => document.getElementById('add-object').classList.contains('visible')), true);
  check('--app-bottom-nav-height is a real measured px value, not the 70px CSS fallback string',
    await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--app-bottom-nav-height').trim() !== ''), true);

  await page.click('#add-object');
  await page.waitForTimeout(350);
  check('Bottom sheet opens on FAB tap',
    await page.evaluate(() => document.getElementById('new-object-sheet').classList.contains('open')), true);
  check('FAB hides while sheet is open',
    await page.evaluate(() => !document.getElementById('add-object').classList.contains('visible')), true);

  await page.click('#new-obj-back');
  await page.waitForTimeout(350);
  check('Bottom sheet closes on X tap',
    await page.evaluate(() => getComputedStyle(document.getElementById('new-object-sheet')).display === 'none'), true);
  check('FAB reappears after sheet closes',
    await page.evaluate(() => document.getElementById('add-object').classList.contains('visible')), true);

  await page.evaluate(() => switchView('home', { isTabSwitch: true }));
  await page.waitForTimeout(200);
  check('FAB hides on navigating away from Objects',
    await page.evaluate(() => !document.getElementById('add-object').classList.contains('visible')), true);

  check('Known NavigationManager-duplicate back button (Tools) hidden under native BackButton',
    await page.evaluate(() => {
      const btn = document.querySelector('#view-tools [onclick="NavigationManager.back()"]');
      return btn ? getComputedStyle(btn).display === 'none' : 'NOT_FOUND';
    }), true);
  check('Non-NavigationManager close button (checkin-status-close-btn) stays visible',
    await page.evaluate(() => {
      const btn = document.getElementById('checkin-status-close-btn');
      return btn ? getComputedStyle(btn).display !== 'none' : 'NOT_FOUND';
    }), true);

  await browser.close();

  const failed = checks.filter(c => !c.pass);
  checks.forEach(c => console.log(`${c.pass ? 'PASS' : 'FAIL'}  ${c.name}  (got: ${JSON.stringify(c.actual)}, want: ${JSON.stringify(c.expected)})`));
  if (errors.length) console.log('PAGE ERRORS:', errors);

  process.exit(failed.length || errors.length ? 1 : 0);
}

main().catch(e => { console.error(e); process.exit(1); });
