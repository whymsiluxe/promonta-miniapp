// Abwesenheit — month-grid календарь отсутствий работников (Фаза 5).
// Референс "Daily Journal": числа месяца ячейками, маркер на занятых днях, тап по ячейке → форма причины.

let _abwCurrentMonth = new Date();
let _abwSelectedDate = null;
let _abwEntries = [];
let _pendingAbwesenheitFocusId = null; // 10.28: переход из алерта — id заявки, диапазон подсветить
let _abwFocusHighlightId = null; // держится дольше — подсветка диапазона видна пока месяц открыт
let _abwSelectedProfileId = ''; // 10.30: owner выбрал профиль worker'а — availability-режим
let _abwAvailability = { unavailable_dates: [], worked_dates: [] };

// Раунд 6 §2: период-пикер + статистика за период.
let _abwPeriod = 'month';   // week | month | 3months | custom (default Месяц)
let _abwPeriodFrom = '';    // YYYY-MM-DD, свой период
let _abwPeriodTo = '';
let _abwPeriodStats = null; // последние успешно загруженные — не теряем при ошибке
let _abwPeriodBusy = false; // двойной tap не дублирует запрос

const ABW_MONTH_NAMES = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

function _abwFormatDate(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function _abwDateInRange(dateStr, entry) {
  return dateStr >= entry.date_from && dateStr <= entry.date_to;
}

async function loadAbwesenheit() {
  try {
    // 28.07: /all теперь доступен любой роли (view-only) -- воркер тоже видит общий
    // календарь команды, не только свои записи, когда выбрал коллегу в селекторе.
    const res = await api('/api/abwesenheit/all');
    _abwEntries = res.entries || [];
  } catch (e) {
    // 31.07 (UX-аудит): было -- при реальной ошибке API молча показывался пустой
    // календарь, неотличимо от "никто не отсутствует". Toast делает ошибку видимой,
    // не ломая остальной рендер календаря (тот уже строится независимо от entries).
    _abwEntries = [];
    showToast('Не удалось загрузить календарь отсутствий', 'error');
  }
  if (_pendingAbwesenheitFocusId) {
    const entry = _abwEntries.find(e => e.id === _pendingAbwesenheitFocusId);
    if (entry) {
      const [y, m] = entry.date_from.split('-').map(Number);
      _abwCurrentMonth = new Date(y, m - 1, 1);
    }
    _abwFocusHighlightId = _pendingAbwesenheitFocusId;
  }
  renderAbwesenheitMonth();
  renderAbwesenheitList();
  if (_pendingAbwesenheitFocusId) {
    const targetId = _pendingAbwesenheitFocusId;
    _pendingAbwesenheitFocusId = null;
    setTimeout(() => _scrollToAbwesenheitEntry(targetId), 150);
  }
}

function _scrollToAbwesenheitEntry(entryId) {
  const card = document.querySelector(`.abw-day-card[data-entry-id="${entryId}"]`);
  if (card) {
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.classList.add('abw-day-card-focus');
    setTimeout(() => card.classList.remove('abw-day-card-focus'), 2200);
  }
}

function renderAbwesenheitMonth() {
  const y = _abwCurrentMonth.getFullYear();
  const m = _abwCurrentMonth.getMonth();
  document.getElementById('abw-month-label').textContent = `${ABW_MONTH_NAMES[m]} ${y}`;

  const firstDay = new Date(y, m, 1);
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  // ISO: понедельник = 0
  const startOffset = (firstDay.getDay() + 6) % 7;

  const todayStr = _abwFormatDate(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());
  const grid = document.getElementById('abw-month-grid');
  let html = '';
  for (let i = 0; i < startOffset; i++) html += '<div class="heatmap-cell" style="visibility:hidden;"></div>';
  const focusEntry = _abwFocusHighlightId ? _abwEntries.find(e => e.id === _abwFocusHighlightId) : null;
  // 21.07 + 22.07: единая система 4 состояний для ЛЮБОГО режима (owner смотрит любого, worker смотрит себя) —
  // зелёный=доступен, серый=отработал (день уже прошёл — важнее прочего), красный=недоступен
  // (одобренный отпуск, теперь физически блокирует новое назначение — см. assign_user backend),
  // синий=назначен на объект в эти даты. Приоритет: отработал > недоступен > назначен > доступен.
  const unavailableSet = new Set(_abwAvailability.unavailable_dates || []);
  const workedSet = new Set(_abwAvailability.worked_dates || []);
  const assignedSet = new Set(_abwAvailability.assigned_dates || []);
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = _abwFormatDate(y, m, d);
    const isToday = dateStr === todayStr;
    const isWorked = workedSet.has(dateStr);
    const isUnavailable = unavailableSet.has(dateStr);
    const isAssigned = assignedSet.has(dateStr);
    const stateCls = isWorked ? 'abw-state-worked' : isUnavailable ? 'abw-state-unavailable' : isAssigned ? 'abw-state-assigned' : 'abw-state-available';
    const inFocusRange = focusEntry && _abwDateInRange(dateStr, focusEntry);
    const cls = ['heatmap-cell', 'abw-avail-cell', stateCls, isToday ? 'today' : '', inFocusRange ? 'focus-range' : '']
      .filter(Boolean).join(' ');
    html += `<div class="${cls}" data-date="${dateStr}">${d}</div>`;
  }
  grid.innerHTML = html;

  grid.querySelectorAll('.heatmap-cell[data-date]').forEach(cell => {
    if (_abwSelectedProfileId) return; // просмотр чужой доступности — не форма создания
    cell.addEventListener('click', () => _openAbwReasonForm(cell.dataset.date));
  });
}

const ABW_REASON_LABEL = { Krankheit: 'Болезнь', Urlaub: 'Отпуск', Sonstiges: 'Другое' };

const ABW_STATUS_LABEL = { pending: 'На рассмотрении', approved: 'Одобрено', rejected: 'Не одобрено' };
const ABW_STATUS_COLOR = { pending: 'var(--warning)', approved: 'var(--accent)', rejected: 'var(--red)' };

function renderAbwesenheitList() {
  const y = _abwCurrentMonth.getFullYear();
  const m = _abwCurrentMonth.getMonth();
  const monthPrefix = `${y}-${String(m + 1).padStart(2, '0')}`;
  // 28.07: /api/abwesenheit/all теперь доступен и worker'у (для dropdown "чей календарь
  // смотреть"), но список заявок ("Никто не отмечен" / карточки) должен по умолчанию
  // показывать только свои записи воркеру -- иначе он видит заявки всех коллег всегда,
  // не только когда явно выбрал кого-то в селекторе (тот выбор влияет на availability
  // heatmap, не на этот список).
  const scopedEntries = currentRole === 'owner' ? _abwEntries : _abwEntries.filter(e => String(e.user_id) === String(currentUserId));
  const entriesThisMonth = scopedEntries.filter(e => e.date_from.startsWith(monthPrefix) || e.date_to.startsWith(monthPrefix));

  const listEl = document.getElementById('abw-list');
  if (!entriesThisMonth.length) {
    listEl.innerHTML = '<div style="color:var(--text-light);font-size:0.85rem;">Никто не отмечен</div>';
    return;
  }
  listEl.innerHTML = entriesThisMonth.map(e => {
    const status = e.status || 'pending';
    const canDecide = currentRole === 'owner' && status === 'pending';
    const isMine = String(e.user_id) === String(currentUserId);
    const canClose = e.open_ended && (isMine || currentRole === 'owner');
    const timeStr = (e.start_time || e.end_time) ? `${e.start_time || ''}${e.end_time ? '–' + e.end_time : ''}` : '';
    const showChatIcon = currentRole === 'owner' && !isMine;

    return `
    <div class="abw-request-card" data-entry-id="${e.id}">
      <div class="abw-request-top">
        <div class="abw-request-avatar">${esc((e.name || '?')[0].toUpperCase())}</div>
        <div class="abw-request-who">
          <div class="abw-request-name">${esc(e.name || e.user_id)}</div>
          <div class="abw-request-status" style="color:${ABW_STATUS_COLOR[status]}">${esc(ABW_STATUS_LABEL[status] || status)}</div>
        </div>
        ${showChatIcon ? `<button class="abw-request-chat-btn abw-open-chat-btn" data-user-id="${esc(e.user_id)}" data-user-name="${esc(e.name || e.user_id)}" title="Написать в чат">💬</button>` : ''}
      </div>

      <div class="abw-request-body">
        <div class="abw-request-range">
          <span class="abw-request-range-icon">📅</span>
          ${fmtDateRangeHuman(e.date_from, e.date_to)}${e.open_ended ? '<span class="abw-request-openbadge">открыто</span>' : ''}
        </div>
        ${timeStr ? `<div class="abw-request-time"><span class="abw-request-range-icon"><svg viewBox="0 0 24 24" width="13" height="13"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M12 7v5l3 3"/></svg></span>${timeStr}</div>` : ''}
        <div class="abw-request-reason">${esc(ABW_REASON_LABEL[e.reason] || e.reason)}</div>
        ${e.note ? `<div class="abw-request-note">${esc(e.note)}</div>` : ''}
      </div>

      ${canDecide ? `
        <div class="abw-request-actions">
          <button class="abw-request-action-btn abw-request-reject" onclick="_decideAbwesenheit('${e.id}','rejected')"><svg viewBox="0 0 24 24" width="18" height="18"><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M18 6L6 18M6 6l12 12"/></svg></button>
          <button class="abw-request-action-btn abw-request-approve" onclick="_decideAbwesenheit('${e.id}','approved')"><svg viewBox="0 0 24 24" width="18" height="18"><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M20 6L9 17l-5-5"/></svg></button>
        </div>` : ''}
      ${canClose ? `
        <div class="abw-request-actions">
          <button class="abw-decide-btn abw-decide-close" onclick="_closeOpenAbwesenheit('${e.id}')" style="width:100%;"><svg viewBox="0 0 24 24" width="18" height="18"><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M20 6L9 17l-5-5"/></svg> Завершить сегодня</button>
        </div>` : ''}
    </div>`;
  }).join('');

  listEl.querySelectorAll('.abw-open-chat-btn').forEach(btn => {
    btn.addEventListener('click', () => _openAbwesenheitChat(btn.dataset.userId, btn.dataset.userName));
  });
}

function _openAbwesenheitChat(userId, name) {
  switchView('chat');
  setTimeout(() => {
    if (typeof openChatThread === 'function') openChatThread(userId, name);
  }, 250);
}

async function _decideAbwesenheit(entryId, status) {
  try {
    await api(`/api/abwesenheit/${entryId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
    hapticImpact('light');
    await loadAbwesenheit();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

// 28.07 (Phase 05, "day tap -> bottom sheet"): тот же управляемый-sheet паттерн, что
// new-object-sheet в objects.js -- overlay регистрируется в NavigationManager.overlayStack,
// Telegram BackButton закрывает корректно вместо провала на предыдущий route.
let _abwSheetOverlayUnregister = null;

function _openAbwReasonForm(dateStr) {
  _abwSelectedDate = dateStr;
  document.getElementById('abw-selected-date').textContent = typeof fmtDateHuman === 'function' ? fmtDateHuman(dateStr) : dateStr;
  const sheet = document.getElementById('abw-reason-sheet');
  sheet.style.display = 'flex';
  requestAnimationFrame(() => sheet.classList.add('open'));
  if (typeof NavigationManager !== 'undefined' && !_abwSheetOverlayUnregister) {
    _abwSheetOverlayUnregister = NavigationManager.registerOverlay(() => _closeAbwReasonFormInternal());
  }
}

function _animateCloseAbwReasonSheet() {
  const sheet = document.getElementById('abw-reason-sheet');
  sheet.classList.remove('open');
  setTimeout(() => { sheet.style.display = 'none'; }, 240);
  document.getElementById('abw-note-input').value = '';
  document.getElementById('abw-date-to-input').value = '';
  document.getElementById('abw-start-time-input').value = '';
  document.getElementById('abw-end-time-input').value = '';
}

// Вызывается ТОЛЬКО из NavigationManager (top.close()) — overlay уже popped.
function _closeAbwReasonFormInternal() {
  _abwSheetOverlayUnregister = null;
  _animateCloseAbwReasonSheet();
}

// Вызывается при ручном закрытии (✕/тап по фону/после сохранения) — overlay ещё в
// стеке, нужно явно снять.
function _closeAbwReasonForm() {
  if (_abwSheetOverlayUnregister) { _abwSheetOverlayUnregister(); _abwSheetOverlayUnregister = null; }
  _animateCloseAbwReasonSheet();
}

async function _saveAbwesenheit() {
  if (!_abwSelectedDate) return;
  const dateTo = document.getElementById('abw-date-to-input').value || null;
  const startTime = document.getElementById('abw-start-time-input').value || null;
  const endTime = document.getElementById('abw-end-time-input').value || null;
  try {
    await api('/api/abwesenheit', {
      method: 'POST',
      body: JSON.stringify({
        date_from: _abwSelectedDate,
        date_to: dateTo,
        reason: document.getElementById('abw-reason-select').value,
        note: document.getElementById('abw-note-input').value,
        start_time: startTime,
        end_time: endTime,
      }),
    });
    hapticImpact('light');
    _closeAbwReasonForm();
    await loadAbwesenheit();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

async function _closeOpenAbwesenheit(entryId) {
  try {
    await api(`/api/abwesenheit/${entryId}/close`, { method: 'PATCH' });
    hapticImpact('light');
    await loadAbwesenheit();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

async function _initAbwProfileSelector() {
  const wrap = document.getElementById('abw-profile-selector-wrap');
  // 28.07: owner request -- воркер тоже может переключаться на общий календарь команды
  // (тот же dropdown, что раньше был owner-only). Backend /api/abwesenheit/all и
  // /api/workers уже открыты для любой авторизованной роли (view-only), approve/reject
  // остаются отдельно защищены require_owner.
  wrap.style.display = 'block';
  const select = document.getElementById('abw-profile-select');
  if (select.dataset.wired) return;
  select.dataset.wired = '1';

  try {
    const data = await api('/api/workers');
    const workers = (data.workers || []).filter(w => w.role === 'worker' && String(w.user_id) !== String(currentUserId));
    workers.forEach(w => {
      const opt = document.createElement('option');
      opt.value = w.user_id;
      opt.textContent = w.name;
      select.appendChild(opt);
    });
  } catch (e) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = '⚠️ Работники недоступны — попробуй позже';
    opt.disabled = true;
    select.appendChild(opt);
  }

  select.addEventListener('change', async () => {
    _abwSelectedProfileId = select.value;
    document.getElementById('abw-availability-legend').style.display = _abwSelectedProfileId ? 'flex' : 'none';
    if (_abwSelectedProfileId) {
      await _loadAbwAvailability();
      await _loadAbwProfileMetrics();
    } else {
      _abwAvailability = { unavailable_dates: [], worked_dates: [] };
      document.getElementById('abw-profile-metrics').style.display = 'none';
    }
    renderAbwesenheitMonth();
    // Раунд 6 §2: при смене выбранного работника сбрасываем кэш периода и перезагружаем.
    _abwPeriodStats = null;
    _loadAbwPeriodStats();
  });
}

async function _loadAbwProfileMetrics() {
  const el = document.getElementById('abw-profile-metrics');
  if (!_abwSelectedProfileId) { el.style.display = 'none'; return; }
  try {
    const stats = await api(`/api/profile/stats?user_id=${_abwSelectedProfileId}`);
    const urlaub = stats.urlaub || { used: 0, remaining: 0, total: 0 };
    el.innerHTML = `
      <div class="abw-metric-chip">
        <div class="abw-metric-value">${stats.krankheit_days_this_year ?? 0}</div>
        <div class="abw-metric-label">дней болел (${new Date().getFullYear()})</div>
      </div>
      <div class="abw-metric-chip">
        <div class="abw-metric-value">${urlaub.remaining}/${urlaub.total}</div>
        <div class="abw-metric-label">отпуск осталось</div>
      </div>`;
    el.style.display = 'flex';
  } catch (e) {
    el.style.display = 'none';
  }
}

async function _loadAbwAvailability() {
  // 21.07: единая 3-состояния система (доступен/отработал/недоступен) для owner (любой выбранный
  // профиль) И для worker (свой собственный календарь) — не два разных визуальных режима.
  const targetId = _abwSelectedProfileId || (currentRole === 'worker' ? currentUserId : '');
  if (!targetId) { _abwAvailability = { unavailable_dates: [], worked_dates: [] }; return; }
  try {
    const y = _abwCurrentMonth.getFullYear();
    const m = _abwCurrentMonth.getMonth() + 1;
    _abwAvailability = await api(`/api/workers/${targetId}/calendar?year=${y}&month=${m}`);
  } catch (e) {
    _abwAvailability = { unavailable_dates: [], worked_dates: [] };
  }
}

// ---------- Раунд 6 §2: период-пикер + статистика за период ----------
// Статистику показываем только когда цель однозначна и разрешена backend'ом:
// Owner — выбранный worker; Worker — только СВОЙ календарь (calendar-stats self-only,
// иначе 403). Пустая строка => панель скрыта.
function _abwStatsTarget() {
  if (currentRole === 'owner') return _abwSelectedProfileId || '';
  return _abwSelectedProfileId ? '' : String(currentUserId);
}

// Сдвиг ISO-даты на N дней через UTC-полдень-якорь (без DST-скачков; чистая календарная арифметика).
function _abwShiftIso(iso, days) {
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d, 12));
  dt.setUTCDate(dt.getUTCDate() + days);
  const yy = dt.getUTCFullYear();
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(dt.getUTCDate()).padStart(2, '0');
  return `${yy}-${mm}-${dd}`;
}

// Диапазон включительно, Europe/Berlin (todayBerlin из shared.js — НЕ UTC toISOString).
// Правая граница пресетов не позже сегодня.
function _abwPeriodRange() {
  const today = todayBerlin();
  const [y, m, d] = today.split('-').map(Number);
  if (_abwPeriod === 'custom') {
    return { date_from: _abwPeriodFrom || today, date_to: _abwPeriodTo || today };
  }
  if (_abwPeriod === 'week') {
    const dow = (new Date(Date.UTC(y, m - 1, d, 12)).getUTCDay() + 6) % 7; // Пн=0
    return { date_from: _abwShiftIso(today, -dow), date_to: today };
  }
  if (_abwPeriod === '3months') {
    const dt = new Date(Date.UTC(y, m - 1 - 2, 1, 12));
    const iso = `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, '0')}-01`;
    return { date_from: iso, date_to: today };
  }
  return { date_from: `${y}-${String(m).padStart(2, '0')}-01`, date_to: today }; // month
}

function _abwFmtDmy(iso) {
  const mm = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
  return mm ? `${mm[3]}.${mm[2]}.${mm[1]}` : (iso || '');
}

async function _loadAbwPeriodStats() {
  const panel = document.getElementById('abw-period-panel');
  const box = document.getElementById('abw-period-stats');
  const target = _abwStatsTarget();
  if (!panel || !box) return;
  if (!target) { panel.style.display = 'none'; return; }
  panel.style.display = 'block';
  const { date_from, date_to } = _abwPeriodRange();
  if (date_from > date_to) {
    box.innerHTML = '<div class="abw-period-error">Дата «С» не может быть позже «По»</div>';
    return;
  }
  if (_abwPeriodBusy) return;
  _abwPeriodBusy = true;
  if (!_abwPeriodStats) box.innerHTML = '<div class="abw-period-loading">Загрузка…</div>';
  try {
    const stats = await api(`/api/workers/${encodeURIComponent(target)}/calendar-stats?date_from=${date_from}&date_to=${date_to}`);
    _abwPeriodStats = stats;
    _renderAbwPeriodStats(stats);
  } catch (e) {
    if (_abwPeriodStats) {
      _renderAbwPeriodStats(_abwPeriodStats); // старые данные не исчезают при кратком error
    } else {
      box.innerHTML = '<div class="abw-period-error">Не удалось загрузить статистику <button type="button" id="abw-period-retry" class="abw-period-retry">Повторить</button></div>';
      document.getElementById('abw-period-retry')?.addEventListener('click', _loadAbwPeriodStats);
    }
  } finally {
    _abwPeriodBusy = false;
  }
}

function _renderAbwPeriodStats(s) {
  const box = document.getElementById('abw-period-stats');
  if (!box) return;
  const hrs = (v) => (Number(v) || 0).toFixed(1).replace('.', ',');
  const range = `${_abwFmtDmy(s.date_from)} — ${_abwFmtDmy(s.date_to)}`;
  box.innerHTML = `
    <div class="abw-period-range">${esc(range)}</div>
    <div class="abw-period-grid">
      <div class="abw-period-row"><span>Отработано дней</span><b>${s.days_worked ?? 0}</b></div>
      <div class="abw-period-row"><span>Всего часов</span><b>${hrs(s.total_hours)} ч</b></div>
      <div class="abw-period-row"><span>Среднее за рабочий день</span><b>${hrs(s.avg_per_day)} ч</b></div>
      <div class="abw-period-row"><span>Больничных</span><b>${s.sick_days ?? 0} дн.</b></div>
      <div class="abw-period-row"><span>Отпуск</span><b>${s.vacation_days ?? 0} дн.</b></div>
    </div>
    <button type="button" id="abw-period-csv" class="submit-btn abw-period-csv-btn">Скачать табель CSV</button>`;
  document.getElementById('abw-period-csv')?.addEventListener('click', _downloadAbwPeriodCsv);
}

async function _downloadAbwPeriodCsv() {
  const target = _abwStatsTarget();
  if (!target) return;
  const btn = document.getElementById('abw-period-csv');
  const { date_from, date_to } = _abwPeriodRange();
  if (date_from > date_to) return;
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/api/checkin/stundenzettel?user_id=${encodeURIComponent(target)}&date_from=${date_from}&date_to=${date_to}`, { headers: { ..._authHeaders() } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const cd = res.headers.get('Content-Disposition') || '';
    const utf8 = cd.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
    a.download = (utf8 ? decodeURIComponent(utf8) : null) || cd.match(/filename="([^"]+)"/)?.[1] || 'Stundenzettel.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    hapticImpact('light');
  } catch (e) {
    showToast('Ошибка экспорта: ' + e.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function _initAbwPeriodPicker() {
  const pills = document.getElementById('abw-period-pills');
  if (!pills || pills.dataset.wired) return;
  pills.dataset.wired = '1';
  const today = todayBerlin();
  const fromEl = document.getElementById('abw-period-from');
  const toEl = document.getElementById('abw-period-to');
  if (fromEl) fromEl.max = today;
  if (toEl) { toEl.max = today; toEl.value = today; }
  pills.addEventListener('click', (e) => {
    const b = e.target.closest('.abw-period-pill');
    if (!b) return;
    _abwPeriod = b.dataset.period;
    pills.querySelectorAll('.abw-period-pill').forEach(p => p.classList.toggle('active', p === b));
    document.getElementById('abw-period-custom').style.display = (_abwPeriod === 'custom') ? 'flex' : 'none';
    if (_abwPeriod !== 'custom') _loadAbwPeriodStats();
  });
  document.getElementById('abw-period-apply')?.addEventListener('click', () => {
    _abwPeriodFrom = (fromEl?.value || '').trim();
    _abwPeriodTo = (toEl?.value || '').trim();
    _loadAbwPeriodStats();
  });
}

async function initAbwesenheitView() {
  await _loadAbwAvailability();
  loadAbwesenheit();
  _initAbwProfileSelector();
  _initAbwPeriodPicker();
  _loadAbwPeriodStats(); // worker сразу видит свою статистику; owner — после выбора
  document.getElementById('abw-prev-month').addEventListener('click', async () => {
    _abwCurrentMonth = new Date(_abwCurrentMonth.getFullYear(), _abwCurrentMonth.getMonth() - 1, 1);
    await _loadAbwAvailability();
    renderAbwesenheitMonth();
    renderAbwesenheitList();
  });
  document.getElementById('abw-next-month').addEventListener('click', async () => {
    _abwCurrentMonth = new Date(_abwCurrentMonth.getFullYear(), _abwCurrentMonth.getMonth() + 1, 1);
    await _loadAbwAvailability();
    renderAbwesenheitMonth();
    renderAbwesenheitList();
  });
  document.getElementById('abw-cancel-btn').addEventListener('click', _closeAbwReasonForm);
  document.getElementById('abw-reason-sheet').addEventListener('click', (e) => {
    if (e.target.id === 'abw-reason-sheet') _closeAbwReasonForm(); // тап по фону закрывает
  });
  document.getElementById('abw-save-btn').addEventListener('click', _saveAbwesenheit);
}
