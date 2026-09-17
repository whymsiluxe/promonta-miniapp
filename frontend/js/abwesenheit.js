// Abwesenheit — month-grid календарь отсутствий работников (Фаза 5).
// Референс "Daily Journal": числа месяца ячейками, маркер на занятых днях, тап по ячейке → форма причины.

let _abwCurrentMonth = new Date();
let _abwSelectedDate = null;
let _abwEntries = [];
let _pendingAbwesenheitFocusId = null; // 10.28: переход из алерта — id заявки, диапазон подсветить
let _abwFocusHighlightId = null; // держится дольше — подсветка диапазона видна пока месяц открыт
let _abwSelectedProfileId = ''; // 10.30: owner выбрал профиль worker'а — availability-режим
let _abwAvailability = { unavailable_dates: [], worked_dates: [] };
let _abwViewMode = 'month'; // week | month | year
let _abwDragEntryId = '';

// Раунд 6 §2: период-пикер + статистика за период.
let _abwPeriod = 'month';   // week | month | 3months | custom (default Месяц)
let _abwPeriodFrom = '';    // YYYY-MM-DD, свой период
let _abwPeriodTo = '';
let _abwPeriodStats = null; // последние успешно загруженные — не теряем при ошибке
let _abwPeriodBusy = false; // двойной tap не дублирует запрос

const ABW_MONTH_NAMES = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const ABW_ICONS = {
  chat: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v7A2.5 2.5 0 0 1 17.5 15H9l-5 5V5.5Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
  calendar: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true"><rect x="3.5" y="4.5" width="17" height="16" rx="2.5" stroke="currentColor" stroke-width="2"/><path d="M8 2.5v4M16 2.5v4M4 9h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  clock: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="2"/><path d="M12 7.5v5l3.2 2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  move: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true"><path d="M12 3v18M3 12h18M7 7l-4 5 4 5M17 7l4 5-4 5M7 7l5-4 5 4M7 17l5 4 5-4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

function _abwFormatDate(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function _abwDateInRange(dateStr, entry) {
  return dateStr >= entry.date_from && dateStr <= entry.date_to;
}

function _abwIsoToUtcDate(iso) {
  const [y, m, d] = String(iso || '').split('-').map(Number);
  return new Date(Date.UTC(y, (m || 1) - 1, d || 1, 12));
}

function _abwIsoDaySpan(dateFrom, dateTo) {
  const start = _abwIsoToUtcDate(dateFrom);
  const end = _abwIsoToUtcDate(dateTo || dateFrom);
  return Math.max(0, Math.round((end - start) / 86400000));
}

function _abwEntryOverlapsMonth(entry, year, monthIndex) {
  const monthStart = `${year}-${String(monthIndex + 1).padStart(2, '0')}-01`;
  const monthEnd = _abwFormatDate(year, monthIndex, new Date(year, monthIndex + 1, 0).getDate());
  return entry.date_from <= monthEnd && entry.date_to >= monthStart;
}

function _abwEntriesForCurrentCalendar() {
  if (_abwSelectedProfileId) {
    return _abwEntries.filter(e => String(e.user_id) === String(_abwSelectedProfileId));
  }
  if (currentRole === 'owner') return _abwEntries;
  return _abwEntries.filter(e => String(e.user_id) === String(currentUserId));
}

function _abwEntriesForDate(dateStr) {
  return _abwEntriesForCurrentCalendar().filter(e => e.date_from && e.date_to && _abwDateInRange(dateStr, e));
}

function _abwCanMoveEntry(entry) {
  if (!entry || !entry.id) return false;
  return currentRole === 'owner' || String(entry.user_id) === String(currentUserId);
}

function _abwAvailabilityState(dateStr) {
  const unavailableSet = new Set(_abwAvailability.unavailable_dates || []);
  const workedSet = new Set(_abwAvailability.worked_dates || []);
  const assignedSet = new Set(_abwAvailability.assigned_dates || []);
  if (workedSet.has(dateStr)) return { key: 'worked', label: 'Отработал' };
  if (unavailableSet.has(dateStr)) return { key: 'unavailable', label: 'Не может работать' };
  if (assignedSet.has(dateStr)) return { key: 'assigned', label: 'Назначен' };
  return { key: 'available', label: 'Доступен' };
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

function _abwWeekDates() {
  // Monday-start week containing _abwCurrentMonth's anchor date (day-of-month
  // preserved by _shiftAbwWeek/_shiftAbwMonth, see below).
  const anchor = _abwCurrentMonth;
  const dow = (anchor.getDay() + 6) % 7; // ISO: понедельник = 0
  const monday = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate() - dow);
  const dates = [];
  for (let i = 0; i < 7; i++) {
    dates.push(new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i));
  }
  return dates;
}

function _abwRenderDayCells(dates, focusEntry, todayStr, unavailableSet, workedSet, assignedSet) {
  return dates.map(dt => {
    const dateStr = _abwFormatDate(dt.getFullYear(), dt.getMonth(), dt.getDate());
    const isToday = dateStr === todayStr;
    const isWorked = workedSet.has(dateStr);
    const isUnavailable = unavailableSet.has(dateStr);
    const isAssigned = assignedSet.has(dateStr);
    const stateCls = isWorked ? 'abw-state-worked' : isUnavailable ? 'abw-state-unavailable' : isAssigned ? 'abw-state-assigned' : 'abw-state-available';
    const inFocusRange = focusEntry && _abwDateInRange(dateStr, focusEntry);
    const entryCount = _abwEntriesForDate(dateStr).length;
    const cls = ['heatmap-cell', 'abw-avail-cell', stateCls, isToday ? 'today' : '', inFocusRange ? 'focus-range' : '']
      .filter(Boolean).join(' ');
    return `<div class="${cls}" data-date="${dateStr}" data-drop-date="${dateStr}">
      <span class="abw-day-num">${dt.getDate()}</span>
      ${entryCount ? `<span class="abw-day-count">${entryCount}</span>` : ''}
    </div>`;
  }).join('');
}

function _abwRenderYearView(grid) {
  const y = _abwCurrentMonth.getFullYear();
  const entries = _abwEntriesForCurrentCalendar();
  document.getElementById('abw-month-label').textContent = `${y}`;
  grid.innerHTML = ABW_MONTH_NAMES.map((name, index) => {
    const monthEntries = entries.filter(e => e.date_from && e.date_to && _abwEntryOverlapsMonth(e, y, index));
    const approved = monthEntries.filter(e => (e.status || 'pending') === 'approved').length;
    const pending = monthEntries.filter(e => (e.status || 'pending') === 'pending').length;
    const rejected = monthEntries.filter(e => (e.status || 'pending') === 'rejected').length;
    const counts = [
      approved ? `<span class="abw-year-count abw-year-count-approved">${approved} одобр.</span>` : '',
      pending ? `<span class="abw-year-count abw-year-count-pending">${pending} ожид.</span>` : '',
      rejected ? `<span class="abw-year-count abw-year-count-rejected">${rejected} откл.</span>` : '',
    ].filter(Boolean).join('');
    const total = monthEntries.length;
    return `<button type="button" class="abw-year-card" data-abw-year-month="${index}">
      <span class="abw-year-title">${esc(name)}</span>
      <span class="abw-year-total">${total ? `${total} заявок` : 'Нет заявок'}</span>
      <span class="abw-year-counts">${counts}</span>
    </button>`;
  }).join('');
  grid.querySelectorAll('[data-abw-year-month]').forEach(btn => {
    btn.addEventListener('click', async () => {
      _abwCurrentMonth = new Date(y, Number(btn.dataset.abwYearMonth), 1);
      await _setAbwViewMode('month', { syncPeriod: true });
    });
  });
}

function renderAbwesenheitMonth() {
  const grid = document.getElementById('abw-month-grid');
  const view = document.getElementById('view-abwesenheit');
  const todayStr = _abwFormatDate(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());
  const focusEntry = _abwFocusHighlightId ? _abwEntries.find(e => e.id === _abwFocusHighlightId) : null;
  // 21.07 + 22.07: единая система 4 состояний для ЛЮБОГО режима (owner смотрит любого, worker смотрит себя) —
  // зелёный=доступен, серый=отработал (день уже прошёл — важнее прочего), красный=недоступен
  // (одобренный отпуск, теперь физически блокирует новое назначение — см. assign_user backend),
  // синий=назначен на объект в эти даты. Приоритет: отработал > недоступен > назначен > доступен.
  const unavailableSet = new Set(_abwAvailability.unavailable_dates || []);
  const workedSet = new Set(_abwAvailability.worked_dates || []);
  const assignedSet = new Set(_abwAvailability.assigned_dates || []);
  if (view) view.classList.toggle('abw-year-mode', _abwViewMode === 'year');
  grid.classList.toggle('abw-year-grid', _abwViewMode === 'year');

  let html = '';
  if (_abwViewMode === 'year') {
    _abwRenderYearView(grid);
    return;
  }
  if (_abwViewMode === 'week') {
    // 17.09: week view -- реиспользует ту же 4-состояние заливку и клик-обработчик,
    // просто сужает диапазон до 7 дней текущей ISO-недели вместо полного месяца.
    const dates = _abwWeekDates();
    const first = dates[0], last = dates[6];
    const sameMonth = first.getMonth() === last.getMonth();
    const label = sameMonth
      ? `${first.getDate()}–${last.getDate()} ${ABW_MONTH_NAMES[first.getMonth()]} ${first.getFullYear()}`
      : `${first.getDate()} ${ABW_MONTH_NAMES[first.getMonth()]} – ${last.getDate()} ${ABW_MONTH_NAMES[last.getMonth()]} ${last.getFullYear()}`;
    document.getElementById('abw-month-label').textContent = label;
    html = _abwRenderDayCells(dates, focusEntry, todayStr, unavailableSet, workedSet, assignedSet);
  } else {
    const y = _abwCurrentMonth.getFullYear();
    const m = _abwCurrentMonth.getMonth();
    document.getElementById('abw-month-label').textContent = `${ABW_MONTH_NAMES[m]} ${y}`;
    const firstDay = new Date(y, m, 1);
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const startOffset = (firstDay.getDay() + 6) % 7;
    for (let i = 0; i < startOffset; i++) html += '<div class="heatmap-cell" style="visibility:hidden;"></div>';
    const dates = [];
    for (let d = 1; d <= daysInMonth; d++) dates.push(new Date(y, m, d));
    html += _abwRenderDayCells(dates, focusEntry, todayStr, unavailableSet, workedSet, assignedSet);
  }
  grid.innerHTML = html;

  grid.querySelectorAll('.heatmap-cell[data-date]').forEach(cell => {
    cell.addEventListener('click', () => _openAbwReasonForm(cell.dataset.date, { readOnly: Boolean(_abwSelectedProfileId) }));
    cell.addEventListener('dragover', (e) => {
      if (!_abwDragEntryId) return;
      e.preventDefault();
      cell.classList.add('abw-drop-target');
    });
    cell.addEventListener('dragleave', () => cell.classList.remove('abw-drop-target'));
    cell.addEventListener('drop', (e) => {
      const entryId = _abwDragEntryId || e.dataTransfer?.getData('text/plain') || '';
      if (!entryId) return;
      e.preventDefault();
      cell.classList.remove('abw-drop-target');
      _moveAbwesenheitEntry(entryId, cell.dataset.date);
    });
  });
}

const ABW_REASON_LABEL = { Krankheit: 'Болезнь', Urlaub: 'Отпуск', Sonstiges: 'Другое' };

const ABW_STATUS_LABEL = { pending: 'На рассмотрении', approved: 'Одобрено', rejected: 'Не одобрено' };
const ABW_STATUS_COLOR = { pending: 'var(--warning)', approved: 'var(--accent)', rejected: 'var(--red)' };

function renderAbwesenheitList() {
  const y = _abwCurrentMonth.getFullYear();
  const m = _abwCurrentMonth.getMonth();
  // 28.07: /api/abwesenheit/all теперь доступен и worker'у (для dropdown "чей календарь
  // смотреть"), но список заявок ("Никто не отмечен" / карточки) должен по умолчанию
  // показывать только свои записи воркеру -- иначе он видит заявки всех коллег всегда,
  // не только когда явно выбрал кого-то в селекторе (тот выбор влияет на availability
  // heatmap, не на этот список).
  const scopedEntries = currentRole === 'owner' ? _abwEntries : _abwEntries.filter(e => String(e.user_id) === String(currentUserId));
  const entriesThisMonth = scopedEntries.filter(e => _abwEntryOverlapsMonth(e, y, m));

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
    const canMove = _abwCanMoveEntry(e);

    return `
    <div class="abw-request-card${canMove ? ' abw-request-movable' : ''}" data-entry-id="${esc(e.id)}" ${canMove ? 'draggable="true" title="Перенести дату"' : ''}>
      <div class="abw-request-top">
        <div class="abw-request-avatar">${esc((e.name || '?')[0].toUpperCase())}</div>
        <div class="abw-request-who">
          <div class="abw-request-name">${esc(e.name || e.user_id)}</div>
          <div class="abw-request-status" style="color:${ABW_STATUS_COLOR[status]}">${esc(ABW_STATUS_LABEL[status] || status)}</div>
        </div>
        ${canMove ? `<span class="abw-request-move-handle" aria-hidden="true">${ABW_ICONS.move}</span>` : ''}
        ${showChatIcon ? `<button class="abw-request-chat-btn abw-open-chat-btn" data-user-id="${esc(e.user_id)}" data-user-name="${esc(e.name || e.user_id)}" title="Написать в чат" aria-label="Написать в чат">${ABW_ICONS.chat}</button>` : ''}
      </div>

      <div class="abw-request-body">
        <div class="abw-request-range">
          <span class="abw-request-range-icon">${ABW_ICONS.calendar}</span>
          ${fmtDateRangeHuman(e.date_from, e.date_to)}${e.open_ended ? '<span class="abw-request-openbadge">открыто</span>' : ''}
        </div>
        ${timeStr ? `<div class="abw-request-time"><span class="abw-request-range-icon">${ABW_ICONS.clock}</span>${timeStr}</div>` : ''}
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
  listEl.querySelectorAll('.abw-request-card[draggable="true"]').forEach(card => {
    card.addEventListener('dragstart', (e) => {
      _abwDragEntryId = card.dataset.entryId || '';
      e.dataTransfer?.setData('text/plain', _abwDragEntryId);
      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
      card.classList.add('abw-request-dragging');
      document.getElementById('abw-month-grid')?.classList.add('abw-grid-dragging');
    });
    card.addEventListener('dragend', () => {
      _abwDragEntryId = '';
      card.classList.remove('abw-request-dragging');
      document.getElementById('abw-month-grid')?.classList.remove('abw-grid-dragging');
      document.querySelectorAll('#abw-month-grid .abw-drop-target').forEach(cell => cell.classList.remove('abw-drop-target'));
    });
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

function _renderAbwDaySummary(dateStr, readOnly) {
  const box = document.getElementById('abw-day-summary');
  if (!box) return;
  const state = _abwAvailabilityState(dateStr);
  const entries = _abwEntriesForDate(dateStr);
  const cards = entries.length ? entries.map(e => {
    const status = e.status || 'pending';
    return `<div class="abw-day-summary-entry">
      <div class="abw-day-summary-entry-title">${esc(e.name || e.user_id || 'Сотрудник')}</div>
      <div class="abw-day-summary-entry-meta">
        ${esc(ABW_REASON_LABEL[e.reason] || 'Отсутствие')} · ${fmtDateRangeHuman(e.date_from, e.date_to)}
      </div>
      <span class="abw-day-summary-status" style="color:${ABW_STATUS_COLOR[status]}">${esc(ABW_STATUS_LABEL[status] || status)}</span>
    </div>`;
  }).join('') : '<div class="abw-day-summary-empty">Заявок нет</div>';
  box.innerHTML = `
    <div class="abw-day-summary-card abw-day-summary-${state.key}">
      <div class="abw-day-summary-top">
        <span class="abw-day-summary-kicker">Статус дня</span>
        <span class="abw-day-summary-pill">${esc(state.label)}</span>
      </div>
      <div class="abw-day-summary-list">${cards}</div>
      ${readOnly ? '<div class="abw-day-summary-readonly">Просмотр календаря сотрудника</div>' : ''}
    </div>`;
}

function _openAbwReasonForm(dateStr, opts = {}) {
  _abwSelectedDate = dateStr;
  document.getElementById('abw-selected-date').textContent = typeof fmtDateHuman === 'function' ? fmtDateHuman(dateStr) : dateStr;
  const readOnly = Boolean(opts.readOnly);
  _renderAbwDaySummary(dateStr, readOnly);
  const form = document.getElementById('abw-reason-form');
  if (form) form.style.display = readOnly ? 'none' : '';
  const dateToInput = document.getElementById('abw-date-to-input');
  if (dateToInput) dateToInput.min = dateStr;
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

async function _moveAbwesenheitEntry(entryId, newDateFrom) {
  const entry = _abwEntries.find(e => e.id === entryId);
  if (!entry || !_abwCanMoveEntry(entry)) return;
  const payload = { date_from: newDateFrom };
  if (!entry.open_ended) {
    payload.date_to = _abwShiftIso(newDateFrom, _abwIsoDaySpan(entry.date_from, entry.date_to));
  }
  try {
    await api(`/api/abwesenheit/${entryId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    _abwFocusHighlightId = entryId;
    hapticImpact('light');
    showToast('Дата перенесена', 'success');
    await _loadAbwAvailability();
    await loadAbwesenheit();
  } catch (e) {
    showToast('Ошибка переноса: ' + e.message, 'error');
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
    opt.textContent = 'Работники недоступны — попробуй позже';
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

function _abwSyncViewModeSwitch() {
  const switcher = document.getElementById('abw-view-mode-switch');
  if (!switcher) return;
  switcher.querySelectorAll('[data-abw-view]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.abwView === _abwViewMode);
  });
}

function _abwSyncPeriodPills() {
  const pills = document.getElementById('abw-period-pills');
  if (!pills) return;
  pills.querySelectorAll('.abw-period-pill').forEach(p => p.classList.toggle('active', p.dataset.period === _abwPeriod));
  const custom = document.getElementById('abw-period-custom');
  if (custom) custom.style.display = (_abwPeriod === 'custom') ? 'flex' : 'none';
}

async function _setAbwViewMode(mode, opts = {}) {
  if (!['week', 'month', 'year'].includes(mode)) return;
  _abwViewMode = mode;
  if (opts.syncPeriod && (mode === 'week' || mode === 'month')) {
    _abwPeriod = mode;
    _abwSyncPeriodPills();
  }
  _abwSyncViewModeSwitch();
  await _loadAbwAvailability();
  renderAbwesenheitMonth();
  renderAbwesenheitList();
}

function _initAbwViewModeSwitch() {
  const switcher = document.getElementById('abw-view-mode-switch');
  if (!switcher || switcher.dataset.wired) return;
  switcher.dataset.wired = '1';
  _abwSyncViewModeSwitch();
  switcher.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-abw-view]');
    if (!btn) return;
    _setAbwViewMode(btn.dataset.abwView, { syncPeriod: true });
    if (btn.dataset.abwView === 'week' || btn.dataset.abwView === 'month') _loadAbwPeriodStats();
  });
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
    _abwSyncPeriodPills();
    // 17.09: отдельный переключатель вида календаря добавил год; старые stats-пилюли
    // для недели/месяца продолжают синхронизировать сам календарь.
    if (_abwPeriod === 'week' || _abwPeriod === 'month') _setAbwViewMode(_abwPeriod, { syncPeriod: false });
    if (_abwPeriod !== 'custom') _loadAbwPeriodStats();
  });
  document.getElementById('abw-period-apply')?.addEventListener('click', () => {
    _abwPeriodFrom = (fromEl?.value || '').trim();
    _abwPeriodTo = (toEl?.value || '').trim();
    _loadAbwPeriodStats();
  });
}

async function _shiftAbwMonth(delta) {
  if (_abwViewMode === 'week') {
    _abwCurrentMonth = new Date(_abwCurrentMonth.getFullYear(), _abwCurrentMonth.getMonth(), _abwCurrentMonth.getDate() + delta * 7);
  } else if (_abwViewMode === 'year') {
    _abwCurrentMonth = new Date(_abwCurrentMonth.getFullYear() + delta, _abwCurrentMonth.getMonth(), 1);
  } else {
    _abwCurrentMonth = new Date(_abwCurrentMonth.getFullYear(), _abwCurrentMonth.getMonth() + delta, 1);
  }
  await _loadAbwAvailability();
  renderAbwesenheitMonth();
  renderAbwesenheitList();
}

async function initAbwesenheitView() {
  // 17.09 (owner report, real iPhone Telegram): the calendar sometimes opened
  // mid-scroll -- header/title missing, the Неделя/Месяц/Год switch already
  // under the Telegram system UI. Root cause: #view-abwesenheit toggles via
  // display:none<->block (not removed from DOM), which does not reset
  // scrollTop -- if the document/root was scrolled from a PREVIOUS state of
  // this same view, it reopened at that stale position. Reset synchronously
  // BEFORE the async load/render below starts, not after -- doing it only
  // after data arrives would let the browser paint the stale scroll position
  // for one visible frame first. Skip the reset only when a deep-link/alert
  // navigation set _pendingAbwesenheitFocusId -- that flow's own
  // _scrollToAbwesenheitEntry() (called from loadAbwesenheit() below) owns
  // the scroll position in that case, don't fight it.
  if (!_pendingAbwesenheitFocusId) {
    if (document.scrollingElement) document.scrollingElement.scrollTop = 0;
    window.scrollTo(0, 0);
  }
  await _loadAbwAvailability();
  loadAbwesenheit();
  _initAbwProfileSelector();
  _initAbwViewModeSwitch();
  _initAbwPeriodPicker();
  _loadAbwPeriodStats(); // worker сразу видит свою статистику; owner — после выбора

  const prevBtn = document.getElementById('abw-prev-month');
  if (prevBtn && !prevBtn.dataset.wired) {
    prevBtn.dataset.wired = '1';
    prevBtn.addEventListener('click', () => _shiftAbwMonth(-1));
  }

  const nextBtn = document.getElementById('abw-next-month');
  if (nextBtn && !nextBtn.dataset.wired) {
    nextBtn.dataset.wired = '1';
    nextBtn.addEventListener('click', () => _shiftAbwMonth(1));
  }

  const cancelBtn = document.getElementById('abw-cancel-btn');
  if (cancelBtn && !cancelBtn.dataset.wired) {
    cancelBtn.dataset.wired = '1';
    cancelBtn.addEventListener('click', _closeAbwReasonForm);
  }

  const reasonSheet = document.getElementById('abw-reason-sheet');
  if (reasonSheet && !reasonSheet.dataset.wired) {
    reasonSheet.dataset.wired = '1';
    reasonSheet.addEventListener('click', (e) => {
      if (e.target.id === 'abw-reason-sheet') _closeAbwReasonForm(); // тап по фону закрывает
    });
  }

  const saveBtn = document.getElementById('abw-save-btn');
  if (saveBtn && !saveBtn.dataset.wired) {
    saveBtn.dataset.wired = '1';
    saveBtn.addEventListener('click', _saveAbwesenheit);
  }
}
