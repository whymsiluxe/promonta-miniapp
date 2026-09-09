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

function _renderDiagnostics(d) {
  const icon = v => {
    if (v === 'ok' || v === 'configured' || (typeof v === 'string' && v.match(/^\d+ objects$/))) return '✅';
    if (v === 'not_configured' || v === 'not_loaded' || v === 'file_exists_no_sync') return '⚠️';
    if (!v || v === 'missing' || v === 'degraded') return '❌';
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
  const shaShort = d.build_sha && d.build_sha !== 'unknown' ? d.build_sha.slice(0, 8) : d.build_sha || '—';

  return `
    <div class="diag-overall diag-overall-${d.overall === 'ok' ? 'ok' : 'warn'}">
      ${d.overall === 'ok' ? '✅ Все системы работают' : '⚠️ Есть проблемы'}
    </div>
    <div class="diag-table">
      ${row('Backend', d.backend)}
      ${row('Google Sheets', d.sheets, sheetsAge)}
      ${row('Объекты', d.objects)}
      ${row('Лента / Алерты', d.feed)}
      ${row('Чат', d.chat)}
      ${row('DailyPlan-sync', d.dailyplan_sync, syncAge)}
      ${row('Drive / Договоры', d.drive_contracts, d.contracts_ingested != null ? ` · ${d.contracts_ingested} договоров` : '')}
      ${row('Build SHA', shaShort, d.build_version && d.build_version !== 'unknown' ? ` · v${d.build_version}` : '')}
    </div>
    <div style="font-size:0.78rem;color:var(--text-light);text-align:center;margin-top:0.75rem">
      Данные актуальны на момент запроса.<br>Sheets-статус — из кэша процесса (нет live API-вызовов).
    </div>
  `;
}

function _fmtDiagValue(value, extra) {
  const label = value == null ? '—' : String(value);
  return `${label}${extra || ''}`;
}

function _fmtAge(seconds) {
  if (seconds < 60) return `${seconds}с`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}м`;
  return `${Math.round(seconds / 3600)}ч`;
}
