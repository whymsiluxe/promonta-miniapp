// today-plan.js — Round 2: Worker "Сегодня" UX, persistent bar, checkin link.
//
// Public surface:
//   checkAndShowTodayPlan()  — called from initApp() after auth+profile, worker-only
//   renderDailyPlan(data, viewerRole) — reusable renderer used by Round 4 Worker Card
//
// Integration hook:
//   window._dailyPlanCheckinFields — set after acceptance, consumed by checkin.js on start
//
// Offline: when fetch fails and navigator.onLine === false, loads last accepted plan from
// IndexedDB and shows it with an offline banner. Plan is read-only offline.

let _todayPlanState = null;   // last GET /api/daily-plan/today result
let _planPollInterval = null;
let _planScreenOpen = false;

// ── IndexedDB cache (offline fallback) ───────────────────────────────────────

const _TP_DB_NAME = 'promonta-today-plan';
const _TP_DB_VER  = 1;
const _TP_STORE   = 'cache';
const _TP_KEY     = 'lastAcceptedPlan';

function _tpDbOpen() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(_TP_DB_NAME, _TP_DB_VER);
    req.onupgradeneeded = e => e.target.result.createObjectStore(_TP_STORE);
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}

async function _tpDbSave(data) {
  try {
    const db = await _tpDbOpen();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(_TP_STORE, 'readwrite');
      tx.objectStore(_TP_STORE).put(data, _TP_KEY);
      tx.oncomplete = resolve;
      tx.onerror    = e => reject(e.target.error);
    });
    db.close();
  } catch (_) { /* non-fatal — cache write failure does not affect live flow */ }
}

async function _tpDbLoad() {
  try {
    const db = await _tpDbOpen();
    const result = await new Promise((resolve, reject) => {
      const tx  = db.transaction(_TP_STORE, 'readonly');
      const req = tx.objectStore(_TP_STORE).get(_TP_KEY);
      req.onsuccess = e => resolve(e.target.result ?? null);
      req.onerror   = e => reject(e.target.error);
    });
    db.close();
    return result;
  } catch (_) {
    return null;
  }
}

// Plan fields passed to checkin_start after acceptance (consumed once, then cleared)
window._dailyPlanCheckinFields = null;
// Exposed for finish-wizard.js to read plan items
window._todayPlanState = null;

const _TP_BLOCKER_REASONS = [
  { code: 'material_missing',    label: 'Нет материалов' },
  { code: 'tool_missing',        label: 'Нет инструмента' },
  { code: 'access_denied',       label: 'Нет доступа на объект' },
  { code: 'safety_concern',      label: 'Проблема безопасности' },
  { code: 'weather',             label: 'Погодные условия' },
  { code: 'coordinator_missing', label: 'Нет ответственного лица' },
  { code: 'other',               label: 'Другое' },
];

// ── Public API ────────────────────────────────────────────────────────────────

async function checkAndShowTodayPlan() {
  if (currentRole !== 'worker') return;
  try {
    const data = await api('/api/daily-plan/today');
    _todayPlanState = data; window._todayPlanState = data;
    if (data.acceptance) _tpDbSave(data); // persist for offline fallback
    _updateTodayPlanBar(data);
    if (_shouldShowPlanScreen(data)) {
      await _openTodayPlanScreen(data, { mandatory: true });
    }
  } catch (e) {
    // Network error — try offline fallback if no connectivity
    if (!navigator.onLine) {
      const cached = await _tpDbLoad();
      if (cached && cached.acceptance) {
        _todayPlanState = { ...cached, _offline: true };
        window._todayPlanState = _todayPlanState;
        _updateTodayPlanBar(_todayPlanState);
      }
    }
    // else: server error while online — skip silently, don't block app launch
  }
  _startTodayPlanPolling();
}

// Reusable plan renderer — parameterized by role (worker vs owner/card view).
// Returns HTML string. The callers must wire button events.
function renderDailyPlan(data, viewerRole) {
  if (!data || !data.has_plan) {
    return '<div class="tp-no-plan">На сегодня план не опубликован</div>';
  }
  const plan = data.plan;
  const accepted = !!data.acceptance;
  const carryovers = data.carryovers || [];

  let html = '';

  // Carryover banner
  if (carryovers.length) {
    html += `<div class="tp-carryover-banner">
      <div class="tp-carryover-title">СНАЧАЛА ЗАКОНЧИТЬ СО ВЧЕРА</div>
      <ul class="tp-carryover-list">
        ${carryovers.map(co => `
          <li class="tp-carryover-item">
            <span class="tp-co-title">${esc(co.item_title || '—')}</span>
            ${co.remaining_quantity != null ? `<span class="tp-co-qty">${esc(String(co.remaining_quantity))} ${esc(co.unit || '')}</span>` : ''}
            ${co.reason_code ? `<span class="tp-co-reason">${esc(co.reason_code)}</span>` : ''}
          </li>
        `).join('')}
      </ul>
    </div>`;
  }

  // Plan items list
  const items = plan.items || [];
  if (items.length) {
    html += `<ol class="tp-action-list">
      ${items.map((item, idx) => {
        const statusClass = item.status && item.status !== 'pending'
          ? ` tp-item-${esc(item.status)}` : '';
        return `<li class="tp-action-item${statusClass}">
          <span class="tp-item-num">${idx + 1}</span>
          <div class="tp-item-body">
            <div class="tp-item-title">${esc(item.title || '—')}</div>
            ${item.objective ? `<div class="tp-item-obj">${esc(item.objective)}</div>` : ''}
            <div class="tp-item-meta">
              ${item.planned_quantity != null ? `<span class="tp-meta-qty">${esc(String(item.planned_quantity))} ${esc(item.unit || '')}</span>` : ''}
              ${item.estimated_hours != null ? `<span class="tp-meta-time">${esc(String(item.estimated_hours))} ч</span>` : ''}
            </div>
          </div>
        </li>`;
      }).join('')}
    </ol>`;
  } else {
    html += '<div class="tp-no-items">Список работ пуст</div>';
  }

  return html;
}

// ── Private helpers ───────────────────────────────────────────────────────────

function _shouldShowPlanScreen(data) {
  if (!data || !data.has_plan || !data.plan) return false;
  const status = data.plan.status;
  const accepted = !!data.acceptance;
  return (status === 'published' || status === 'amendment_pending') && !accepted;
}

function _startTodayPlanPolling() {
  if (_planPollInterval) return;
  _planPollInterval = setInterval(async () => {
    if (currentRole !== 'worker') return;
    try {
      const data = await api('/api/daily-plan/today');
      const prev = _todayPlanState;
      _todayPlanState = data; window._todayPlanState = data;
      if (data.acceptance) _tpDbSave(data);
      // Clear offline flag if we just came back online
      _updateTodayPlanBar(data);
      // Show screen if a new plan just appeared or version bumped (and screen is not open)
      if (!_planScreenOpen && _shouldShowPlanScreen(data)) {
        const prevVersion = prev?.plan?.version;
        const newVersion = data.plan?.version;
        if (!prev?.has_plan || prevVersion !== newVersion) {
          _openTodayPlanScreen(data, { mandatory: false });
        }
      }
    } catch (e) { /* ignore poll errors — offline state persists until next success */ }
  }, 60000);
}

// Full-screen today plan overlay.
// mandatory=true: no close button, user must interact (acceptance or blocker or noplan-start)
// mandatory=false: has close button (tapping bar)
function _openTodayPlanScreen(data, { mandatory = true } = {}) {
  return new Promise(resolve => {
    const screen = document.getElementById('today-plan-screen');
    if (!screen) { resolve(); return; }

    _planScreenOpen = true;
    screen.innerHTML = _renderScreenHTML(data, mandatory);
    screen.style.display = 'flex';

    const plan = data.plan;
    const accepted = !!data.acceptance;

    // Close button (non-mandatory view)
    screen.querySelector('#tp-close-btn')?.addEventListener('click', () => {
      _closeTodayPlanScreen();
      resolve();
    });

    // Acceptance CTA
    const acceptBtn = screen.querySelector('#tp-accept-btn');
    if (acceptBtn && plan && !accepted) {
      acceptBtn.addEventListener('click', async () => {
        acceptBtn.disabled = true;
        acceptBtn.textContent = 'Принимаю…';
        try {
          const result = await api(`/api/daily-plan/${plan.id}/accept`, { method: 'POST' });
          const newAcceptance = result.acceptance;
          _todayPlanState = { ..._todayPlanState, acceptance: newAcceptance };
          window._todayPlanState = _todayPlanState;
          window._dailyPlanCheckinFields = {
            daily_plan_id: plan.id,
            daily_plan_version: String(plan.version),
            daily_plan_acceptance_id: newAcceptance.id,
          };
          hapticImpact('medium');
          // Morph button into "НАЧАТЬ СМЕНУ"
          acceptBtn.textContent = '▶ НАЧАТЬ СМЕНУ';
          acceptBtn.disabled = false;
          acceptBtn.id = 'tp-start-btn-post-accept';
          acceptBtn.className = 'tp-cta-btn tp-start-btn';
          acceptBtn.replaceWith(acceptBtn.cloneNode(true)); // remove old listener
          document.getElementById('tp-start-btn-post-accept')?.addEventListener('click', () => {
            _closeTodayPlanScreen();
            resolve();
            _startShiftFromPlan(plan);
          });
          // Hide blocker btn after acceptance
          screen.querySelector('#tp-blocker-btn')?.remove();
          _updateTodayPlanBar(_todayPlanState);
        } catch (e) {
          showToast('Не удалось принять план: ' + e.message, 'error');
          acceptBtn.disabled = false;
          acceptBtn.textContent = 'ПЛАН ПОНЯТЕН — БЕРУ В РАБОТУ';
        }
      });
    }

    // "Start shift" button (if plan already accepted, shown on bar-tap)
    screen.querySelector('#tp-start-btn')?.addEventListener('click', () => {
      _closeTodayPlanScreen();
      resolve();
      if (plan) _startShiftFromPlan(plan);
    });

    // Blocker CTA
    screen.querySelector('#tp-blocker-btn')?.addEventListener('click', () => {
      _showBlockerForm(plan.id, () => {
        _closeTodayPlanScreen();
        resolve();
      });
    });

    // No-plan start (when plan is not published yet but worker is assigned)
    screen.querySelector('#tp-noplan-start-btn')?.addEventListener('click', () => {
      _closeTodayPlanScreen();
      resolve();
    });
  });
}

function _closeTodayPlanScreen() {
  const screen = document.getElementById('today-plan-screen');
  if (screen) screen.style.display = 'none';
  _planScreenOpen = false;
}

function _renderScreenHTML(data, mandatory) {
  const plan = data?.plan;
  const accepted = !!(data?.acceptance);
  const hasPlan = !!(data?.has_plan && plan);
  const isOffline = !!(data?._offline);
  const closeBtn = mandatory ? '' : '<button class="tp-close-btn" id="tp-close-btn" type="button" aria-label="Закрыть">✕</button>';
  const offlineBanner = isOffline
    ? '<div class="tp-offline-banner">Офлайн · показан последний принятый план</div>'
    : '';

  if (!hasPlan) {
    // No plan published — worker assigned but no plan yet
    return `
      <div class="tp-inner">
        <div class="tp-header">
          ${closeBtn}
          ${offlineBanner}
          <div class="tp-date">${esc(data?.date || '')}</div>
          <div class="tp-object-name">—</div>
        </div>
        <div class="tp-body">
          <div class="tp-no-plan-msg">
            <div class="tp-no-plan-icon">📋</div>
            <div class="tp-no-plan-text">План дня ещё не опубликован руководителем</div>
          </div>
        </div>
        <div class="tp-footer">
          <button class="tp-noplan-btn" id="tp-noplan-start-btn" type="button"${isOffline ? ' disabled' : ''}>Начать смену без плана</button>
        </div>
      </div>`;
  }

  const status = plan.status;
  const items = plan.items || [];
  const carryovers = data.carryovers || [];
  const done = items.filter(i => i.status === 'done').length;
  const total = items.length;

  // Status badge text
  let statusBadge = '';
  if (!accepted) {
    statusBadge = '<span class="tp-status-badge tp-status-pending">Ожидает принятия</span>';
  } else if (status === 'amendment_pending') {
    statusBadge = '<span class="tp-status-badge tp-status-amend">Изменения от руководителя</span>';
  } else {
    statusBadge = '<span class="tp-status-badge tp-status-accepted">План принят</span>';
  }

  const planBody = renderDailyPlan(data, 'worker');

  // Footer CTAs — all interactive actions disabled when offline (read-only fallback)
  let footerHtml = '';
  if (isOffline) {
    footerHtml = '<div class="tp-offline-footer">Действия недоступны офлайн</div>';
  } else if (!accepted) {
    footerHtml = `
      <button class="tp-cta-btn tp-accept-btn" id="tp-accept-btn" type="button">
        ПЛАН ПОНЯТЕН — БЕРУ В РАБОТУ
      </button>
      <button class="tp-blocker-btn" id="tp-blocker-btn" type="button">
        ЕСТЬ ПРЕПЯТСТВИЕ
      </button>`;
  } else {
    footerHtml = `
      <button class="tp-cta-btn tp-start-btn" id="tp-start-btn" type="button">
        ▶ НАЧАТЬ СМЕНУ
      </button>`;
  }

  return `
    <div class="tp-inner">
      <div class="tp-header">
        ${closeBtn}
        ${offlineBanner}
        <div class="tp-date">${esc(plan.date || data?.date || '')}</div>
        <div class="tp-object-name" id="tp-object-name-el">${esc(plan.object_id || '')}</div>
        ${statusBadge}
        ${total > 0 ? `<div class="tp-item-count">${total} ${_pluralRu(total, 'задание', 'задания', 'заданий')}</div>` : ''}
      </div>
      <div class="tp-body">
        ${planBody}
      </div>
      <div class="tp-footer">
        ${footerHtml}
      </div>
    </div>`;
}

function _pluralRu(n, f1, f2, f5) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return f5;
  if (mod10 === 1) return f1;
  if (mod10 >= 2 && mod10 <= 4) return f2;
  return f5;
}

// Blocker reason picker + comment
function _showBlockerForm(planId, onDone) {
  const screen = document.getElementById('today-plan-screen');
  if (!screen) return;

  screen.innerHTML = `
    <div class="tp-inner">
      <div class="tp-header">
        <div class="tp-date" style="margin-bottom:0.5rem">Причина препятствия</div>
      </div>
      <div class="tp-body">
        <div class="tp-blocker-reasons">
          ${_TP_BLOCKER_REASONS.map(r => `
            <label class="tp-blocker-reason-item">
              <input type="radio" name="blocker-reason" value="${esc(r.code)}">
              <span>${esc(r.label)}</span>
            </label>
          `).join('')}
        </div>
        <textarea class="tp-blocker-comment" id="tp-blocker-comment"
          placeholder="Подробнее (необязательно)…" rows="3" maxlength="500"></textarea>
      </div>
      <div class="tp-footer">
        <button class="tp-cta-btn tp-blocker-send-btn" id="tp-blocker-send-btn" type="button">
          Отправить руководителю
        </button>
        <button class="tp-noplan-btn" id="tp-blocker-cancel-btn" type="button">
          Отмена
        </button>
      </div>
    </div>`;

  screen.querySelector('#tp-blocker-cancel-btn')?.addEventListener('click', () => {
    // Go back to plan screen
    if (_todayPlanState) _openTodayPlanScreen(_todayPlanState, { mandatory: false });
  });

  screen.querySelector('#tp-blocker-send-btn')?.addEventListener('click', async () => {
    const checkedEl = screen.querySelector('input[name="blocker-reason"]:checked');
    if (!checkedEl) {
      showToast('Выберите причину', 'error');
      return;
    }
    const sendBtn = screen.querySelector('#tp-blocker-send-btn');
    sendBtn.disabled = true;
    sendBtn.textContent = 'Отправка…';
    try {
      await api(`/api/daily-plan/${planId}/blocker`, {
        method: 'POST',
        body: JSON.stringify({
          reason_code: checkedEl.value,
          comment: (screen.querySelector('#tp-blocker-comment')?.value || '').trim(),
        }),
      });
      hapticImpact('light');
      screen.innerHTML = `
        <div class="tp-inner">
          <div class="tp-body" style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1rem">
            <div style="font-size:2.5rem">✅</div>
            <div class="tp-no-plan-text">Руководитель уведомлён</div>
            <div style="color:var(--text-light);font-size:0.9rem">Ожидайте звонка или сообщения</div>
          </div>
          <div class="tp-footer">
            <button class="tp-noplan-btn" id="tp-blocker-done-btn" type="button">
              Начать смену без плана
            </button>
          </div>
        </div>`;
      screen.querySelector('#tp-blocker-done-btn')?.addEventListener('click', () => {
        _closeTodayPlanScreen();
        onDone();
      });
    } catch (e) {
      showToast('Не удалось отправить: ' + e.message, 'error');
      sendBtn.disabled = false;
      sendBtn.textContent = 'Отправить руководителю';
    }
  });
}

// Start shift from plan — skip object picker if plan has object_id
function _startShiftFromPlan(plan) {
  if (plan?.object_id && typeof _openStagePickerThenStart === 'function') {
    _openStagePickerThenStart(plan.object_id);
  } else if (typeof _openWorkerObjectPicker === 'function') {
    _openWorkerObjectPicker();
  }
}

// ── Persistent bar ────────────────────────────────────────────────────────────

function _updateTodayPlanBar(data) {
  const bar = document.getElementById('today-plan-bar');
  if (!bar) return;

  if (!data || !data.has_plan || !data.plan) {
    bar.style.display = 'none';
    document.body.classList.remove('today-plan-bar-visible');
    return;
  }

  const plan = data.plan;
  const isOffline = !!(data._offline);
  // Only show bar for published/accepted plans (not drafts)
  if (plan.status === 'draft') {
    bar.style.display = 'none';
    document.body.classList.remove('today-plan-bar-visible');
    return;
  }

  const accepted = !!data.acceptance;
  const items = plan.items || [];
  const done = items.filter(i => i.status === 'done').length;
  const total = items.length;

  let statusChip = '';
  if (isOffline) {
    statusChip = '<span class="tp-bar-chip tp-bar-chip-offline">Офлайн</span>';
  } else if (!accepted) {
    statusChip = '<span class="tp-bar-chip tp-bar-chip-warn">Принять план</span>';
  } else if (done > 0) {
    statusChip = `<span class="tp-bar-chip">${done} из ${total}</span>`;
  }

  bar.style.display = 'flex';
  document.body.classList.add('today-plan-bar-visible');

  bar.innerHTML = `
    <div class="tp-bar-info" id="tp-bar-tap-zone">
      <span class="tp-bar-label">Сегодня</span>
      <span class="tp-bar-sep">·</span>
      <span class="tp-bar-obj" id="tp-bar-obj-name">${esc(plan.object_id || '—')}</span>
      ${statusChip}
    </div>
    <button class="tp-bar-open-btn" id="tp-bar-open-btn" type="button">Открыть →</button>
  `;

  // Load object name async
  _resolveBarObjectName(plan.object_id);

  // Tap on bar info or button → open plan card
  bar.querySelector('#tp-bar-tap-zone')?.addEventListener('click', _openPlanCard);
  bar.querySelector('#tp-bar-open-btn')?.addEventListener('click', _openPlanCard);
}

async function _resolveBarObjectName(objectId) {
  if (!objectId) return;
  try {
    const data = await api('/api/objects');
    const obj = (data.objects || []).find(o => o['ID объекта'] === objectId);
    const name = obj?.['Объект'] || objectId;
    const el = document.getElementById('tp-bar-obj-name');
    if (el) el.textContent = name;
  } catch (e) { /* fallback to object_id shown already */ }
}

function _openPlanCard() {
  if (!_todayPlanState) return;
  _openTodayPlanScreen(_todayPlanState, { mandatory: false });
}
