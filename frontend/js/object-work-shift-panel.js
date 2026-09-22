// Object Detail V2 (Этап 7), migration step 2 — reusable shift panels for the
// future "Работа" zone (obj-detail-panel-work).
//
// Per docs/OBJECT_DETAIL_V2_IMPLEMENTATION_PLAN.md's corrected migration order:
// this ports ONLY the genuinely-missing pieces of #stages-view (shift timer/GPS
// status, pause/resume, manual time entry) -- NOT Start/Finish (already covered
// by object-info.js's _appendCheckinShortcut via the canonical
// resolveWorkerShiftState()/openWorkerShiftFlow() flow) and NOT the stage list
// (already covered by renderObjectStagesTab). Quick actions
// (Фото/Потребность/Дефект/Чат) are NOT ported either -- #stages-view's local
// 3-button active-shift-qa-* row is a duplicate of worker-quick-actions.js
// (Этап 6), which already generalizes this across 3 rounds of hardening; this
// panel does not reimplement it.
//
// New DOM ids throughout (wp-* prefix), deliberately NOT reusing #stages-view's
// ids (active-shift-timer, checkin-pause-toggle-btn, checkin-manual-form, etc.)
// -- those stay wired to checkin.js's initCheckinControls()/refreshCheckinButtons()
// for #stages-view, which is not retired yet (step 3). Two DOM trees, one
// architecture: both this panel and #stages-view read shift state via
// resolveWorkerShiftState(), neither maintains its own polling/state machine.
//
// This panel is not called from anywhere in production yet -- ZONE_RENDERERS.work
// (objects.js, step 1) still points at renderObjectStagesTab only. Wiring this in
// is part of step 3 (retiring #stages-view), once this panel is proven functional.

let _wpTimerInterval = null;
let _wpStartAt = null;
let _wpPauseStartedAt = null;
let _wpPauseAccumulated = 0;
let _wpManualPauseMinutes = 0;
let _wpCurrentObjectId = null;

function _wpStopTimer() {
  if (_wpTimerInterval) {
    clearInterval(_wpTimerInterval);
    _wpTimerInterval = null;
  }
}

function _wpFormatDuration(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

function _wpTickTimer() {
  const timerEl = document.getElementById('wp-shift-timer');
  if (!timerEl || !_wpStartAt) return;
  const now = Math.floor(Date.now() / 1000);
  let pauseSeconds = _wpPauseAccumulated;
  if (_wpPauseStartedAt) pauseSeconds += now - _wpPauseStartedAt;
  timerEl.textContent = _wpFormatDuration(now - _wpStartAt - pauseSeconds);
}

function _wpGpsStatusText(accuracy) {
  if (accuracy == null || Number.isNaN(accuracy)) {
    return { text: '📍 Местоположение записано', color: '' };
  }
  if (accuracy > 100) {
    return { text: `⚠️ Низкая точность · ±${Math.round(accuracy)} м`, color: 'var(--red)' };
  }
  return { text: `📍 Местоположение · ±${Math.round(accuracy)} м`, color: '' };
}

function _wpRenderActivePanel(shiftState) {
  const session = shiftState.session || {};
  const startAccuracy = session.start_accuracy ?? session.startAccuracy ?? null;
  const isPaused = shiftState.state === WORKER_SHIFT_STATE.PAUSED;
  const gps = _wpGpsStatusText(startAccuracy != null ? Number(startAccuracy) : null);

  return `
    <div class="active-shift-panel" id="wp-active-shift-panel">
      <div class="active-shift-top">
        <div class="active-shift-timer" id="wp-shift-timer">00:00</div>
        <div class="active-shift-gps" id="wp-shift-gps-status" style="color:${gps.color};">${gps.text}</div>
      </div>
      <div class="active-shift-main-actions">
        <button class="submit-btn checkin-btn" id="wp-pause-toggle-btn" type="button" style="background:var(--bg-card-raised);color:var(--text-main);">
          ${isPaused ? '▶ Продолжить' : '⏸ Пауза'}
        </button>
      </div>
    </div>
  `;
}

function _wpSeedTimerState(shiftState) {
  const session = shiftState.session || {};
  const startAt = session.start_at ?? session.startAt;
  const pauseStartedAt = session.pause_started_at ?? session.pauseStartedAt ?? null;
  const pauseAccumulated = session.pause_accumulated_seconds ?? session.pauseAccumulatedSeconds ?? 0;

  _wpStartAt = startAt ? Number(startAt) : null;
  _wpPauseStartedAt = pauseStartedAt ? Number(pauseStartedAt) : null;
  _wpPauseAccumulated = Number(pauseAccumulated) || 0;
  _wpTickTimer();
  _wpStopTimer();
  _wpTimerInterval = setInterval(_wpTickTimer, 1000);
}

async function renderWorkShiftPanel(objectId) {
  _wpCurrentObjectId = objectId;
  const container = document.getElementById('wp-shift-panel-slot');
  if (!container) return;

  _wpStopTimer();

  let shiftState = null;
  try {
    shiftState = typeof resolveWorkerShiftState === 'function'
      ? await resolveWorkerShiftState({ objectId })
      : null;
  } catch (e) {}

  if (_wpCurrentObjectId !== objectId) return; // stale response guard, same pattern as elsewhere in this codebase

  const hasActive = typeof workerShiftStateHasActiveSession === 'function' && workerShiftStateHasActiveSession(shiftState);
  if (!hasActive || !shiftState) {
    container.innerHTML = '';
    _wpStopTimer();
    _wpRenderManualEntry(objectId);
    return;
  }

  container.innerHTML = _wpRenderActivePanel(shiftState);
  _wpSeedTimerState(shiftState);

  document.getElementById('wp-pause-toggle-btn')?.addEventListener('click', () => _wpTogglePause(objectId, shiftState));

  _wpRenderManualEntry(objectId);
}

async function _wpTogglePause(objectId, shiftState) {
  const sessionId = shiftState.sessionId || shiftState.session?.id;
  if (!sessionId) return;
  const btn = document.getElementById('wp-pause-toggle-btn');
  if (btn) btn.disabled = true;
  try {
    await api(`/api/checkin/${sessionId}/pause`, { method: 'POST' });
    hapticImpact('light');
    await renderWorkShiftPanel(objectId);
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
    if (btn) btn.disabled = false;
  }
}

// ── Manual time entry ────────────────────────────────────────────────────────
// Same /api/checkin/manual endpoint #stages-view's checkin-manual-form already
// uses (backend/main.py's checkin_manual) -- new DOM ids/markup, not a new
// backend contract.

function _wpRenderManualEntry(objectId) {
  const slot = document.getElementById('wp-manual-entry-slot');
  if (!slot) return;
  slot.innerHTML = `
    <button class="checkin-manual-link" id="wp-manual-link-btn" type="button">Внести время вручную</button>
    <div id="wp-manual-form" class="mangel-form" style="display:none;">
      <select id="wp-manual-art-select" class="mangel-select">
        <option value="Arbeitszeit">🔧 Рабочее время</option>
        <option value="Fahrzeit">🚗 Время в пути</option>
        <option value="Wartezeit">⏳ Время ожидания</option>
      </select>
      <input type="date" id="wp-manual-date-input" class="mangel-select">
      <div style="display:flex;gap:0.5rem;">
        <input type="time" id="wp-manual-start-time-input" class="mangel-select" style="flex:1;">
        <input type="time" id="wp-manual-end-time-input" class="mangel-select" style="flex:1;">
      </div>
      <div class="checkin-pause-row">
        <span>Пауза</span>
        <button type="button" id="wp-manual-pause-minus" class="checkin-pause-btn">−</button>
        <span id="wp-manual-pause-value">0 мин.</span>
        <button type="button" id="wp-manual-pause-plus" class="checkin-pause-btn">+</button>
      </div>
      <textarea id="wp-manual-description" class="mangel-textarea" placeholder="Что сделано, материалы…" rows="2"></textarea>
      <div class="mangel-form-actions">
        <button class="submit-btn" id="wp-manual-cancel-btn" type="button" style="background:var(--bg-card-raised);color:var(--text-main);">Отмена</button>
        <button class="submit-btn" id="wp-manual-save-btn" type="button">Сохранить</button>
      </div>
    </div>
  `;

  _wpManualPauseMinutes = 0;

  document.getElementById('wp-manual-link-btn')?.addEventListener('click', () => {
    const form = document.getElementById('wp-manual-form');
    if (!form) return;
    if (form.style.display === 'block') {
      form.style.display = 'none';
      return;
    }
    document.getElementById('wp-manual-date-input').value = typeof todayBerlin === 'function' ? todayBerlin() : '';
    form.style.display = 'block';
  });
  document.getElementById('wp-manual-cancel-btn')?.addEventListener('click', () => {
    const form = document.getElementById('wp-manual-form');
    if (form) form.style.display = 'none';
  });
  document.getElementById('wp-manual-pause-minus')?.addEventListener('click', () => {
    _wpManualPauseMinutes = Math.max(0, _wpManualPauseMinutes - 15);
    document.getElementById('wp-manual-pause-value').textContent = `${_wpManualPauseMinutes} мин.`;
  });
  document.getElementById('wp-manual-pause-plus')?.addEventListener('click', () => {
    _wpManualPauseMinutes += 15;
    document.getElementById('wp-manual-pause-value').textContent = `${_wpManualPauseMinutes} мин.`;
  });
  document.getElementById('wp-manual-save-btn')?.addEventListener('click', () => _wpSubmitManualEntry(objectId));
}

async function _wpSubmitManualEntry(objectId) {
  const date = document.getElementById('wp-manual-date-input')?.value;
  const startTime = document.getElementById('wp-manual-start-time-input')?.value;
  const endTime = document.getElementById('wp-manual-end-time-input')?.value;
  if (!date || !startTime || !endTime) { showToast('Заполните дату и время', 'error'); return; }

  try {
    await api('/api/checkin/manual', {
      method: 'POST',
      body: JSON.stringify({
        object_id: objectId,
        art: document.getElementById('wp-manual-art-select').value,
        date,
        start_time: startTime,
        end_time: endTime,
        pause_minutes: _wpManualPauseMinutes,
        description: document.getElementById('wp-manual-description').value,
      }),
    });
    hapticImpact('light');
    const form = document.getElementById('wp-manual-form');
    if (form) form.style.display = 'none';
    showToast('Время сохранено', 'success');
  } catch (e) {
    showToast('Ошибка сохранения: ' + e.message, 'error');
  }
}
