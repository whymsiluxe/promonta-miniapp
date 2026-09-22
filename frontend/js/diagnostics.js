// Phase 7: owner-only system diagnostics view.
// Fetches /api/diagnostics and renders a status table — no deps beyond shared api().

function initDiagnosticsView() {
  const content = document.getElementById('diag-content');
  const backBtn = document.getElementById('diag-back-btn');
  const refreshBtn = document.getElementById('diag-refresh-btn');

  backBtn?.addEventListener('click', () => {
    if (typeof NavigationManager !== 'undefined') NavigationManager.back();
    else if (typeof switchView === 'function') switchView('profile', { isTabSwitch: true });
  });

  refreshBtn?.addEventListener('click', () => _loadDiagnostics(content));

  _loadDiagnostics(content);
}

async function _loadDiagnostics(content) {
  if (!content) return;
  content.innerHTML = '<div style="color:var(--text-light);font-size:0.9rem;text-align:center;padding:2rem 0">Загрузка…</div>';
  try {
    const d = await api('/api/diagnostics');
    content.innerHTML = _renderDiagnostics(d);
  } catch (e) {
    content.innerHTML = `<div class="js-error-state" style="padding:1rem">Ошибка загрузки: ${e.message || 'network error'}</div>`;
  }
}

// 22.09 (iPhone screenshot audit): raw backend status tokens localized for
// display -- a real device showed untranslated values like "not_configured"
// and "4 objects" directly in the owner-facing UI.
const DIAG_VALUE_LABELS = {
  ok: 'ОК', configured: 'Настроено', not_configured: 'Не настроено',
  not_loaded: 'Не загружено', missing: 'Отсутствует', degraded: 'Ошибка',
  stale: 'Устарело', file_exists_no_sync: 'Файл есть, синхронизации не было',
  red: 'Есть проблема',
};

function _localizeDiagValue(value) {
  if (value == null) return '—';
  if (DIAG_VALUE_LABELS[value]) return DIAG_VALUE_LABELS[value];
  const objMatch = typeof value === 'string' && value.match(/^(\d+) objects$/);
  if (objMatch) return `${objMatch[1]} ${_pluralizeObjects(Number(objMatch[1]))}`;
  return String(value);
}

function _pluralizeObjects(n) {
  const mod100 = n % 100, mod10 = n % 10;
  if (mod100 >= 11 && mod100 <= 14) return 'объектов';
  if (mod10 === 1) return 'объект';
  if (mod10 >= 2 && mod10 <= 4) return 'объекта';
  return 'объектов';
}

function _renderDiagnostics(d) {
  const icon = v => {
    if (v === 'ok' || v === 'configured' || (typeof v === 'string' && v.match(/^\d+ objects$/))) return '✅';
    if (v === 'not_configured' || v === 'not_loaded' || v === 'file_exists_no_sync') return '⚠️';
    if (!v || v === 'missing' || v === 'degraded' || v === 'red') return '❌';
    return '⚠️';
  };

  const row = (label, value, detail) => `
    <div class="diag-row">
      <span class="diag-icon">${icon(value)}</span>
      <span class="diag-label">${label}</span>
      <span class="diag-value">${_fmtDiagValue(value, detail)}</span>
    </div>`;

  const sheetsAge = d.sheets_last_read_s != null ? ` (${_fmtAge(d.sheets_last_read_s)} назад)` : '';
  const syncAge = d.dailyplan_sync_age_s != null ? ` (${_fmtAge(d.dailyplan_sync_age_s)} назад)` : '';
  // 22.09 (iPhone screenshot audit): build_sha and build_version were the
  // SAME underlying commit SHA (this repo has no separate "version" concept
  // from the deploy commit) -- rendering both produced a visibly duplicated
  // "c28ff97 · c28ff97" (or, if the two ever drifted apart in an odd deploy,
  // an equally confusing "c23894d4 · vc23894d"). Show the SHA once; only add
  // a second value if build_version is genuinely a DIFFERENT string.
  const shaShort = d.build_sha && d.build_sha !== 'unknown' ? d.build_sha.slice(0, 7) : d.build_sha || '—';
  const versionDiffersFromSha = d.build_version && d.build_version !== 'unknown' && d.build_version !== d.build_sha && d.build_version !== shaShort;

  // 22.09 (iPhone screenshot audit): `overall` is now ok/warning/error (see
  // system_status.diagnostics_response) -- a real device showed a green
  // "✅ Все системы работают" headline directly above yellow warning rows
  // for fields the old binary ok/degraded check never looked at, visibly
  // contradicting itself. Headline text now matches what's actually below it.
  const overallLabel = {
    ok: '✅ Все системы работают',
    warning: '⚠️ Основные системы работают · есть предупреждения',
    error: '❌ Есть проблемы с ключевыми системами',
  }[d.overall] || '⚠️ Есть проблемы';
  const overallClass = d.overall === 'ok' ? 'ok' : d.overall === 'error' ? 'error' : 'warn';

  return `
    <div class="diag-overall diag-overall-${overallClass}">
      ${overallLabel}
    </div>
    <div class="diag-table">
      ${row('Backend', d.backend)}
      ${row('Google Sheets', d.sheets, sheetsAge)}
      ${row('Объекты', d.objects)}
      ${row('Лента / Алерты', d.feed)}
      ${row('Чат', d.chat)}
      ${row('DailyPlan-sync', d.dailyplan_sync, syncAge)}
      ${row('Drive / Договоры', d.drive_contracts, d.contracts_ingested != null ? ` · ${d.contracts_ingested} договоров` : '')}
      ${row('Build SHA', shaShort, versionDiffersFromSha ? ` · v${d.build_version}` : '')}
    </div>
    <div style="font-size:0.78rem;color:var(--text-light);text-align:center;margin-top:0.75rem">
      Данные актуальны на момент запроса.<br>Sheets-статус — из кэша процесса (нет live API-вызовов).
    </div>
  `;
}

function _fmtDiagValue(value, extra) {
  const label = _localizeDiagValue(value);
  return `${label}${extra || ''}`;
}

function _fmtAge(seconds) {
  if (seconds < 60) return `${seconds}с`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}м`;
  return `${Math.round(seconds / 3600)}ч`;
}
