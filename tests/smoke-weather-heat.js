// Раунд 4 smoke-тест (без фреймворка, как tests/smoke-nav-fab.js): чистая логика
// классификации погоды (жара) + разбивка резюме новостей на абзацы.
//
// Функции weatherHeatKind/weatherRiskSeverity/_dominantWxType/_renderNewsSummary
// объявлены в frontend/js/feed.js и home.js (vanilla, общий global scope). Здесь мы
// грузим оба файла в изолированный vm-контекст с permissive-стабами браузерных
// глобалов, затем дёргаем функции напрямую и проверяем требуемые кейсы из ТЗ.
//
// Запуск:  node tests/smoke-weather-heat.js   (exit 0 = все проверки прошли)

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const jsDir = path.join(__dirname, '..', 'frontend', 'js');

// Permissive-стаб: любое чтение неизвестного свойства -> функция-заглушка/undefined,
// чтобы top-level код файлов (навешивание слушателей и т.п.) не падал при загрузке.
function permissive() {
  const fn = function () { return undefined; };
  return new Proxy(fn, {
    get(t, prop) {
      if (prop === Symbol.toPrimitive) return () => '';
      if (prop in t) return t[prop];
      return permissive();
    },
    apply() { return permissive(); },
    construct() { return permissive(); },
  });
}

const sandbox = {
  console,
  esc: (s) => (s == null ? '' : String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;')),
  document: permissive(),
  window: permissive(),
  localStorage: permissive(),
  navigator: permissive(),
  Telegram: permissive(),
  setTimeout: () => 0,
  setInterval: () => 0,
  fetch: () => Promise.resolve(permissive()),
  api: () => Promise.resolve({}),
};
sandbox.window = sandbox;
const ctx = vm.createContext(sandbox);

for (const f of ['feed.js', 'home.js']) {
  const code = fs.readFileSync(path.join(jsDir, f), 'utf8');
  try {
    vm.runInContext(code, ctx, { filename: f });
  } catch (e) {
    console.error(`FAIL loading ${f}: ${e.message}`);
    process.exit(1);
  }
}

let failed = 0;
function check(name, cond) {
  if (cond) { console.log(`  ok  ${name}`); }
  else { console.error(`FAIL  ${name}`); failed++; }
}

const wave = (tmax, extra = {}) => Object.assign({ tmax, tmin: tmax - 8, precip_prob: 0, wind: 5 }, extra);

// --- Weather severity (home.js) ---
const sev = (w, risks) => ctx.weatherRiskSeverity(w, risks);

// 29°C + дождь -> дождь (жара не срабатывает <30)
let r = sev(wave(29, { precip_prob: 70 }), ['возможен дождь']);
check('29C+rain -> rain', r.kind === 'rain');

// 31°C без других рисков -> жара (heat)
r = sev(wave(31), []);
check('31C -> heat', r.kind === 'heat');
check('31C label = Жарко', ctx._weatherKindLabel('heat', wave(31)) === 'Жарко');

// 34°C + слабый дождь -> сильная жара главный, дождь вторичный
r = sev(wave(34, { precip_prob: 40 }), ['возможен дождь']);
check('34C+weak rain -> heat main', r.kind === 'heat');
check('34C label = Сильная жара', ctx._weatherKindLabel('heat', wave(34)) === 'Сильная жара');
check('34C rain is secondary', r.secondary.some(s => s.includes('дожд')));

// 36°C + дождь -> экстремальная жара главный
r = sev(wave(36, { precip_prob: 65 }), ['возможен дождь']);
check('36C+rain -> extreme_heat main', r.kind === 'extreme_heat');
check('36C label = Экстремальная жара', ctx._weatherKindLabel('extreme_heat', wave(36)) === 'Экстремальная жара');

// 36°C + сильная гроза -> severity order: экстремальная жара выше грозы
r = sev(wave(36), ['сильная гроза']);
check('36C+storm -> extreme_heat main', r.kind === 'extreme_heat');
check('36C+storm storm secondary', r.secondary.includes('гроза'));

// ветер выше порога -> ветер (без жары)
r = sev(wave(20, { wind: 45 }), ['сильный ветер']);
check('wind over threshold -> wind', r.kind === 'wind');

// storm выше жары при нормальной температуре
r = sev(wave(31), ['гроза']);
check('31C+storm -> storm (storm>heat)', r.kind === 'storm');

// --- Dominant type (feed.js) ---
const entry = (tmax, risks) => ({ wave: [wave(tmax)], forecast: [{ risks }] });
check('feed 36C -> extreme_heat', ctx._dominantWxType(entry(36, ['дождь'])) === 'extreme_heat');
check('feed 31C -> heat', ctx._dominantWxType(entry(31, ['дождь'])) === 'heat');
check('feed 29C+rain -> rain', ctx._dominantWxType(entry(29, ['дождь'])) === 'rain');
check('feed primary label heat', ctx._wxPrimaryLabel(entry(36, ['дождь'])) === 'Экстремальная жара');

// --- News summary paragraphs (feed.js) ---
const shortSum = ctx._renderNewsSummary({ summary: 'Одно короткое предложение.' }, 0);
check('short summary: no more-btn', !shortSum.includes('news-more-btn'));

const longSum = ctx._renderNewsSummary({
  summary: 'Абзац первый '.repeat(20).trim() + '\n\n' + 'Абзац второй '.repeat(20).trim() + '\n\n' + 'Абзац третий '.repeat(20).trim(),
}, 1);
check('long summary: has more-btn', longSum.includes('news-more-btn'));
check('long summary: has hidden tail', longSum.includes('news-summary-tail" hidden'));
check('long summary: paragraphs wrapped in <p>', (longSum.match(/<p>/g) || []).length >= 2);

const xss = ctx._renderNewsSummary({ summary: '<script>alert(1)</script>\n\n' + 'x'.repeat(700) }, 2);
check('news summary escapes HTML', !xss.includes('<script>alert'));

if (failed) { console.error(`\n${failed} check(s) FAILED`); process.exit(1); }
console.log('\nAll weather/news smoke checks passed.');
