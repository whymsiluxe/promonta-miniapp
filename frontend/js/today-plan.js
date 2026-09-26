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
let _tomorrowPlanState = null; // last GET /api/daily-plan/today?day=tomorrow result (18.09 preview)
let _planPollInterval = null;
let _planScreenOpen = false;
let _planScreenDay = 'today'; // which tab the open screen currently shows

// ── IndexedDB cache (offline fallback) ───────────────────────────────────────

const _TP_DB_NAME = 'grandmont-group-today-plan';
// Grandmont Group rebrand (26.09): pre-rebrand cache DB name, read once as a fallback
// so an offline worker right after the deploy still sees the last accepted plan.
const _TP_LEGACY_DB_NAME = 'promonta-today-plan';
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
    if (result !== null) return result;
    return await _tpLegacyDbLoadAndMigrate();
  } catch (_) {
    return null;
  }
}

async function _tpLegacyDbLoadAndMigrate() {
  if (typeof _openLegacyIdbIfExists !== 'function') return null;
  const legacy = await _openLegacyIdbIfExists(_TP_LEGACY_DB_NAME);
  if (!legacy) return null;
  let result = null;
  try {
    if (legacy.objectStoreNames.contains(_TP_STORE)) {
      result = await new Promise((resolve, reject) => {
        const req = legacy.transaction(_TP_STORE, 'readonly').objectStore(_TP_STORE).get(_TP_KEY);
        req.onsuccess = e => resolve(e.target.result ?? null);
        req.onerror   = e => reject(e.target.error);
      });
    }
  } finally {
    legacy.close();
  }
  if (result !== null) await _tpDbSave(result);
  indexedDB.deleteDatabase(_TP_LEGACY_DB_NAME);
  return result;
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
    // 17.09 (audit finding #3, P0): _dailyPlanCheckinFields used to be populated
    // ONLY inside the accept-button click handler -- if the worker accepted the
    // plan, closed the app, and reopened later (a very normal Telegram usage
    // pattern), this went back to null on the fresh load even though the plan
    // was still accepted server-side. Start would then silently proceed WITHOUT
    // DailyPlan linkage (the backend treats it as optional), losing the
    // connection between an actually-accepted plan and the shift session.
    // Restore it here on every load whenever the server confirms an acceptance,
    // not just at the moment acceptance happens client-side.
    if (data.has_plan && data.acceptance) {
      window._dailyPlanCheckinFields = {
        daily_plan_id: data.plan.id,
        daily_plan_version: String(data.plan.version),
        daily_plan_acceptance_id: data.acceptance.id,
      };
    }
    if (data.acceptance) _tpDbSave(data); // persist for offline fallback
    _updateWorkerDailyPlanSurfaces(data);
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
        // Same restoration as the online path above -- offline cache also
        // carries a real server-confirmed acceptance, must not be lost either.
        if (cached.has_plan && cached.plan) {
          window._dailyPlanCheckinFields = {
            daily_plan_id: cached.plan.id,
            daily_plan_version: String(cached.plan.version),
            daily_plan_acceptance_id: cached.acceptance.id,
          };
        }
        _updateWorkerDailyPlanSurfaces(_todayPlanState);
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
  // If THIS worker has pending amendments they haven't acked yet, always show
  // the screen regardless of their acceptance state (a prior acceptance is stale
  // vs. the new plan version and must not gate the amendment screen away).
  if ((data.pending_amendments || []).length > 0) return true;
  // 'accepted'/'in_progress' included: on a multi-worker plan another worker may
  // have already accepted (status -> accepted) or even finished their own part
  // (status -> in_progress, set by apply_daily_execution) before THIS worker got
  // to accept. THIS worker's own acceptance (data.acceptance) is what actually
  // gates the screen, not the shared plan status.
  return (status === 'published' || status === 'amendment_pending' || status === 'accepted' || status === 'in_progress') && !accepted;
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
      _updateWorkerDailyPlanSurfaces(data);
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
// mandatory=false: has close button (tapping bar) + Сегодня/Завтра tab switcher
// day: which tab is being rendered ('today' or 'tomorrow') -- tomorrow is always
// non-mandatory (18.09, owner request: worker previews/accepts tomorrow's plan
// early to prepare tools/materials; it must never gate today's shift start).
function _openTodayPlanScreen(data, { mandatory = true, day = 'today' } = {}) {
  return new Promise(resolve => {
    const screen = document.getElementById('today-plan-screen');
    if (!screen) { resolve(); return; }

    _planScreenOpen = true;
    _planScreenDay = day;
    screen.innerHTML = _renderScreenHTML(data, mandatory, day);
    screen.style.display = 'flex';
    _resolveAmendmentFieldNames(screen);

    const plan = data.plan;
    const accepted = !!data.acceptance;

    // Close button (non-mandatory view)
    screen.querySelector('#tp-close-btn')?.addEventListener('click', () => {
      _closeTodayPlanScreen();
      resolve();
    });

    // Сегодня/Завтра tab switcher (non-mandatory view only)
    screen.querySelector('#tp-tab-today')?.addEventListener('click', async () => {
      if (day === 'today') return;
      resolve();
      _openPlanCard();
    });
    screen.querySelector('#tp-tab-tomorrow')?.addEventListener('click', async () => {
      if (day === 'tomorrow') return;
      resolve();
      await _openTomorrowPlanCard();
    });

    // Amendment acknowledgement CTA (takes priority over plain acceptance)
    const amendAckBtn = screen.querySelector('#tp-amend-ack-btn');
    if (amendAckBtn && plan) {
      amendAckBtn.addEventListener('click', async () => {
        amendAckBtn.disabled = true;
        amendAckBtn.textContent = 'Принимаю…';
        const planId = amendAckBtn.dataset.planId;
        const amendmentId = amendAckBtn.dataset.amendmentId;
        try {
          await api(`/api/daily-plan/${planId}/amendments/${amendmentId}/accept`, { method: 'POST' });
          hapticImpact('medium');
          // Re-fetch plan state so other pending amendments (if any) are surfaced
          const freshData = await api('/api/daily-plan/today');
          _todayPlanState = freshData; window._todayPlanState = freshData;
          if (freshData.acceptance) _tpDbSave(freshData);
          _updateWorkerDailyPlanSurfaces(freshData);
          if ((freshData.pending_amendments || []).length > 0) {
            // More amendments for this worker — re-render the screen
            screen.innerHTML = _renderScreenHTML(freshData, mandatory);
            _resolveAmendmentFieldNames(screen);
          } else {
            _closeTodayPlanScreen();
            resolve();
          }
        } catch (e) {
          showToast('Не удалось принять изменения: ' + e.message, 'error');
          amendAckBtn.disabled = false;
          amendAckBtn.textContent = 'ПОНЯТНО — ПРИНЯТЬ ИЗМЕНЕНИЯ';
        }
      });
    }

    // Acceptance CTA
    const acceptBtn = screen.querySelector('#tp-accept-btn');
    if (acceptBtn && plan && !accepted) {
      acceptBtn.addEventListener('click', async () => {
        acceptBtn.disabled = true;
        acceptBtn.textContent = 'Принимаю…';
        try {
          const result = await api(`/api/daily-plan/${plan.id}/accept`, { method: 'POST' });
          const newAcceptance = result.acceptance;

          if (day === 'tomorrow') {
            // Tomorrow-preview accept: record acceptance for its own tab state only.
            // Must NOT touch window._dailyPlanCheckinFields (that is read by
            // checkin.js at Start and must only ever reflect TODAY's plan) and
            // must NOT morph into "НАЧАТЬ СМЕНУ" -- the shift for this plan's
            // date hasn't started yet.
            _tomorrowPlanState = { ..._tomorrowPlanState, acceptance: newAcceptance };
            hapticImpact('medium');
            acceptBtn.textContent = 'План принят';
            acceptBtn.disabled = true;
            acceptBtn.classList.add('tp-accept-btn-done');
            screen.querySelector('#tp-blocker-btn')?.remove();
            return;
          }

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
          _updateWorkerDailyPlanSurfaces(_todayPlanState);
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

function _renderScreenHTML(data, mandatory, day = 'today') {
  const plan = data?.plan;
  const accepted = !!(data?.acceptance);
  const hasPlan = !!(data?.has_plan && plan);
  const isOffline = !!(data?._offline);
  const closeBtn = mandatory ? '' : '<button class="tp-close-btn" id="tp-close-btn" type="button" aria-label="Закрыть">✕</button>';
  const offlineBanner = isOffline
    ? '<div class="tp-offline-banner">Офлайн · показан последний принятый план</div>'
    : '';
  // Tab switcher only makes sense outside the mandatory today-screen -- mandatory
  // means the worker must resolve today's plan right now, a tab away from it
  // would let them dodge that gate via the tomorrow tab.
  const tabSwitcher = mandatory ? '' : `
    <div class="tp-tabs">
      <button class="tp-tab${day === 'today' ? ' tp-tab-active' : ''}" id="tp-tab-today" type="button">Сегодня</button>
      <button class="tp-tab${day === 'tomorrow' ? ' tp-tab-active' : ''}" id="tp-tab-tomorrow" type="button">Завтра</button>
    </div>`;

  if (!hasPlan) {
    // No plan published — worker assigned but no plan yet
    const noPlanFooter = day === 'tomorrow'
      ? '<div class="tp-no-plan-text" style="text-align:center;color:var(--text-light)">План на завтра ещё не опубликован</div>'
      : `<button class="tp-noplan-btn" id="tp-noplan-start-btn" type="button"${isOffline ? ' disabled' : ''}>Начать смену без плана</button>`;
    return `
      <div class="tp-inner">
        <div class="tp-header">
          ${closeBtn}
          ${tabSwitcher}
          ${offlineBanner}
          <div class="tp-date">${esc(data?.date || '')}</div>
          <div class="tp-object-name">—</div>
        </div>
        <div class="tp-body">
          <div class="tp-no-plan-msg">
            <div class="tp-no-plan-icon">📋</div>
            <div class="tp-no-plan-text">${day === 'tomorrow' ? 'План на завтра ещё не опубликован руководителем' : 'План дня ещё не опубликован руководителем'}</div>
          </div>
        </div>
        <div class="tp-footer">
          ${noPlanFooter}
        </div>
      </div>`;
  }

  const status = plan.status;
  const items = plan.items || [];
  const carryovers = data.carryovers || [];
  const done = items.filter(i => i.status === 'done').length;
  const total = items.length;

  const pendingAmendments = data.pending_amendments || [];
  const hasPendingAmendment = pendingAmendments.length > 0;

  // Status badge text
  let statusBadge = '';
  if (hasPendingAmendment) {
    statusBadge = '<span class="tp-status-badge tp-status-amend">Изменения от руководителя</span>';
  } else if (!accepted) {
    statusBadge = '<span class="tp-status-badge tp-status-pending">Ожидает принятия</span>';
  } else {
    statusBadge = '<span class="tp-status-badge tp-status-accepted">План принят</span>';
  }

  const planBody = renderDailyPlan(data, 'worker');

  // Amendment diff block — rendered when THIS worker has unacknowledged amendments
  let amendmentHtml = '';
  if (hasPendingAmendment) {
    amendmentHtml = pendingAmendments.map(amend => {
      const diff = amend.diff || {};
      const added = diff.added || [];
      const removed = diff.removed || [];
      const changed = diff.changed || [];
      const fieldChanges = diff.field_changes || {};
      let diffLines = '';
      if (changed.length) diffLines += `<div class="tp-diff-section"><div class="tp-diff-label">БЫЛО → СТАЛО</div>${changed.map(c => `<div class="tp-diff-row tp-diff-changed"><span class="tp-diff-old">${esc(c.old && c.old.title || JSON.stringify(c.old))}</span><span class="tp-diff-arrow">→</span><span class="tp-diff-new">${esc(c.new && c.new.title || JSON.stringify(c.new))}</span></div>`).join('')}</div>`;
      if (added.length)   diffLines += `<div class="tp-diff-section"><div class="tp-diff-label">ДОБАВЛЕНО</div>${added.map(i => `<div class="tp-diff-row tp-diff-added">+ ${esc(i.title || JSON.stringify(i))}</div>`).join('')}</div>`;
      if (removed.length) diffLines += `<div class="tp-diff-section"><div class="tp-diff-label">УДАЛЕНО</div>${removed.map(i => `<div class="tp-diff-row tp-diff-removed">− ${esc(i.title || JSON.stringify(i))}</div>`).join('')}</div>`;
      // Round 1.2 #1: field_changes (object_id/date/assigned_worker_ids/stage_key)
      // -- IDs shown first, resolved to real names async by _resolveAmendmentFieldNames()
      // right after render (same pattern as _resolveBarObjectName for the plan bar).
      diffLines += _renderFieldChangesHtml(fieldChanges);
      if (!diffLines) diffLines = '<div class="tp-diff-row">Нет деталей изменений</div>';
      return `<div class="tp-amendment-block" data-amendment-id="${esc(amend.id)}">
        <div class="tp-amend-title">Изменение плана</div>${diffLines}
      </div>`;
    }).join('');
  }

  // Footer CTAs — all interactive actions disabled when offline (read-only fallback)
  let footerHtml = '';
  if (isOffline) {
    footerHtml = '<div class="tp-offline-footer">Действия недоступны офлайн</div>';
  } else if (hasPendingAmendment) {
    // Amendment acknowledgement takes priority — even over first-time acceptance
    const amendId = pendingAmendments[0].id;
    footerHtml = `
      <button class="tp-cta-btn tp-accept-btn" id="tp-amend-ack-btn"
              type="button" data-plan-id="${esc(plan.id)}" data-amendment-id="${esc(amendId)}">
        ПОНЯТНО — ПРИНЯТЬ ИЗМЕНЕНИЯ
      </button>`;
  } else if (!accepted) {
    footerHtml = `
      <button class="tp-cta-btn tp-accept-btn" id="tp-accept-btn" type="button">
        ПЛАН ПОНЯТЕН — БЕРУ В РАБОТУ
      </button>
      <button class="tp-blocker-btn" id="tp-blocker-btn" type="button">
        ЕСТЬ ПРЕПЯТСТВИЕ
      </button>`;
  } else if (day === 'tomorrow') {
    // Preview tab, already accepted -- no "НАЧАТЬ СМЕНУ" here, the shift for
    // this plan's date can only start once that date actually arrives (via
    // today's own tab, which will show this same plan once it becomes "today").
    footerHtml = '';
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
        ${tabSwitcher}
        ${offlineBanner}
        <div class="tp-date">${esc(plan.date || data?.date || '')}</div>
        <div class="tp-object-name" id="tp-object-name-el">${esc(plan.object_id || '')}</div>
        ${statusBadge}
        ${total > 0 ? `<div class="tp-item-count">${total} ${_pluralRu(total, 'задание', 'задания', 'заданий')}</div>` : ''}
      </div>
      <div class="tp-body">
        ${amendmentHtml}
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
  if (typeof openWorkerShiftFlow === 'function') {
    openWorkerShiftFlow({
      objectId: plan?.object_id || null,
      entryPoint: 'daily-plan',
    });
  } else if (plan?.object_id && typeof _openStagePickerThenStart === 'function') {
    _openStagePickerThenStart(plan.object_id);
  } else if (typeof _openWorkerObjectPicker === 'function') {
    _openWorkerObjectPicker();
  }
}

// ── Persistent bar ────────────────────────────────────────────────────────────

// Worker UX V2, Этап 5: Today (view-home) уже shows the same plan status inside
// its own compact DailyPlan card -- showing the persistent bar there too would
// be a visible duplicate on the same screen. Called from switchView() on every
// tab switch; re-runs _updateTodayPlanBar() with the last known data to restore
// the bar's normal display when leaving Home, so this never fights the bar's
// own display:none/flex logic with a separate CSS override.
function _syncTodayPlanBarForView(viewName) {
  const bar = document.getElementById('today-plan-bar');
  if (!bar) return;
  if (viewName === 'home') {
    bar.style.display = 'none';
    return;
  }
  if (_todayPlanState) _updateTodayPlanBar(_todayPlanState);
}

// 21.09 (P1, owner review finding): _updateTodayPlanBar() used to
// unconditionally set display:flex whenever called with plan data -- the
// ONLY thing suppressing it on Home was _syncTodayPlanBarForView('home') on
// tab-switch. Both the 60s poll (_startTodayPlanPolling) and the amendment-
// accept flow call _updateTodayPlanBar() directly, bypassing that check, so
// a worker who stayed on Home past one poll tick got the bar back alongside
// the Home card showing the exact same status -- the duplicate this branch's
// Today redesign was specifically built to remove. Checking the DOM here
// (not a tracked "current view" variable -- none exists globally, see
// switchView() in app.html) keeps this self-contained without threading
// view state through every _updateTodayPlanBar() call site.
function _isHomeViewCurrentlyActive() {
  const homeView = document.getElementById('view-home');
  return !!homeView && homeView.classList.contains('active');
}

// 21.09 (P1, owner review finding): single entry point for "plan data
// changed, refresh everywhere it's displayed" -- the 60s poll and the
// amendment-accept flow used to call _updateTodayPlanBar(data) directly and
// nothing else, so home.js's _renderWorkerDailyPlanCard() (Today's compact
// DailyPlan card) kept showing stale data (e.g. an old item count) until the
// worker left and re-entered Home. _todayPlanState/window._todayPlanState
// are set by the caller before this runs (same as before), this only adds
// the two renders that were missing.
function _updateWorkerDailyPlanSurfaces(data) {
  _updateTodayPlanBar(data);
  if (typeof _renderWorkerDailyPlanCard === 'function') _renderWorkerDailyPlanCard();
}

function _updateTodayPlanBar(data) {
  const bar = document.getElementById('today-plan-bar');
  if (!bar) return;

  if (_isHomeViewCurrentlyActive()) {
    bar.style.display = 'none';
    document.body.classList.remove('today-plan-bar-visible');
    return;
  }

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

// Round 1.2 #1: human-readable labels for update_plan_fields()-generated
// amendments (object/date/worker/stage changes, distinct from item add/remove/
// change diffs which were already rendered). IDs are shown immediately; real
// names are resolved async and swapped in via data-amend-field markers, same
// two-step pattern as _resolveBarObjectName below.
const FIELD_CHANGE_LABELS = {
  object_id: 'ОБЪЕКТ',
  date: 'ДАТА',
  assigned_worker_ids: 'РАБОТНИКИ',
  stage_key: 'ЭТАП',
};

function _renderFieldChangesHtml(fieldChanges) {
  const keys = Object.keys(fieldChanges || {}).filter(k => FIELD_CHANGE_LABELS[k]);
  if (!keys.length) return '';
  return keys.map(key => {
    const { old: oldVal, new: newVal } = fieldChanges[key];
    const oldText = _formatFieldChangeValue(key, oldVal);
    const newText = _formatFieldChangeValue(key, newVal);
    return `<div class="tp-diff-section" data-amend-field="${esc(key)}">
      <div class="tp-diff-label">${FIELD_CHANGE_LABELS[key]}</div>
      <div class="tp-diff-row tp-diff-changed">
        <span class="tp-diff-old" data-amend-field-old="${esc(key)}">${esc(oldText)}</span>
        <span class="tp-diff-arrow">→</span>
        <span class="tp-diff-new" data-amend-field-new="${esc(key)}">${esc(newText)}</span>
      </div>
    </div>`;
  }).join('');
}

function _formatFieldChangeValue(key, value) {
  if (key === 'date' && value) {
    try { return fmtDateHuman(value); } catch (_) { return value; }
  }
  if (key === 'assigned_worker_ids' && Array.isArray(value)) {
    return value.length ? value.join(', ') : '—';
  }
  return value != null && value !== '' ? String(value) : '—';
}

// Resolves object_id/assigned_worker_ids raw IDs in already-rendered amendment
// field_changes to real names -- best-effort, IDs stay visible on failure.
async function _resolveAmendmentFieldNames(screen) {
  const objectEls = screen.querySelectorAll('[data-amend-field="object_id"] [data-amend-field-old], [data-amend-field="object_id"] [data-amend-field-new]');
  const workerEls = screen.querySelectorAll('[data-amend-field="assigned_worker_ids"] [data-amend-field-old], [data-amend-field="assigned_worker_ids"] [data-amend-field-new]');
  if (!objectEls.length && !workerEls.length) return;

  try {
    if (objectEls.length) {
      const data = await api('/api/objects');
      const objects = data.objects || [];
      objectEls.forEach(el => {
        const obj = objects.find(o => o['ID объекта'] === el.textContent);
        if (obj?.['Объект']) el.textContent = obj['Объект'];
      });
    }
  } catch (_) { /* IDs stay visible */ }

  try {
    if (workerEls.length) {
      const data = await api('/api/workers');
      const workers = data.workers || [];
      workerEls.forEach(el => {
        const ids = el.textContent.split(',').map(s => s.trim()).filter(Boolean);
        if (!ids.length) return;
        const names = ids.map(id => {
          const w = workers.find(w => String(w.user_id) === id);
          return w?.name || id;
        });
        el.textContent = names.join(', ');
      });
    }
  } catch (_) { /* IDs stay visible */ }
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
  _openTodayPlanScreen(_todayPlanState, { mandatory: false, day: 'today' });
}

// 18.09: tomorrow-preview tab -- always re-fetches so the switcher shows the
// latest published state, not a possibly-stale cache from app launch.
async function _openTomorrowPlanCard() {
  try {
    const data = await api('/api/daily-plan/today?day=tomorrow');
    _tomorrowPlanState = data;
    await _openTodayPlanScreen(data, { mandatory: false, day: 'tomorrow' });
  } catch (e) {
    showToast('Не удалось загрузить план на завтра: ' + e.message, 'error');
  }
}
