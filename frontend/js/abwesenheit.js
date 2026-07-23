// Abwesenheit — month-grid календарь отсутствий работников (Фаза 5).
// Референс "Daily Journal": числа месяца ячейками, маркер на занятых днях, тап по ячейке → форма причины.

let _abwCurrentMonth = new Date();
let _abwSelectedDate = null;
let _abwEntries = [];
let _pendingAbwesenheitFocusId = null; // 10.28: переход из алерта — id заявки, диапазон подсветить
let _abwFocusHighlightId = null; // держится дольше — подсветка диапазона видна пока месяц открыт
let _abwSelectedProfileId = ''; // 10.30: owner выбрал профиль worker'а — availability-режим
let _abwAvailability = { unavailable_dates: [], worked_dates: [] };

const ABW_MONTH_NAMES = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

function _abwFormatDate(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function _abwDateInRange(dateStr, entry) {
  return dateStr >= entry.date_from && dateStr <= entry.date_to;
}

async function loadAbwesenheit() {
  try {
    const res = currentRole === 'owner' ? await api('/api/abwesenheit/all') : await api('/api/abwesenheit');
    _abwEntries = res.entries || [];
  } catch (e) {
    _abwEntries = [];
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
  const entriesThisMonth = _abwEntries.filter(e => e.date_from.startsWith(monthPrefix) || e.date_to.startsWith(monthPrefix));

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
        <div class="abw-request-avatar">${(e.name || '?')[0].toUpperCase()}</div>
        <div class="abw-request-who">
          <div class="abw-request-name">${e.name || e.user_id}</div>
          <div class="abw-request-status" style="color:${ABW_STATUS_COLOR[status]}">${ABW_STATUS_LABEL[status]}</div>
        </div>
        ${showChatIcon ? `<button class="abw-request-chat-btn" onclick="_openAbwesenheitChat('${e.user_id}','${(e.name || e.user_id).replace(/'/g, "\\'")}')" title="Написать в чат">💬</button>` : ''}
      </div>

      <div class="abw-request-body">
        <div class="abw-request-range">
          <span class="abw-request-range-icon">📅</span>
          ${e.date_from} — ${e.date_to}${e.open_ended ? '<span class="abw-request-openbadge">открыто</span>' : ''}
        </div>
        ${timeStr ? `<div class="abw-request-time"><span class="abw-request-range-icon">🕐</span>${timeStr}</div>` : ''}
        <div class="abw-request-reason">${ABW_REASON_LABEL[e.reason] || e.reason}</div>
        ${e.note ? `<div class="abw-request-note">${e.note}</div>` : ''}
      </div>

      ${canDecide ? `
        <div class="abw-request-actions">
          <button class="abw-request-action-btn abw-request-reject" onclick="_decideAbwesenheit('${e.id}','rejected')">❌</button>
          <button class="abw-request-action-btn abw-request-approve" onclick="_decideAbwesenheit('${e.id}','approved')">✅</button>
        </div>` : ''}
      ${canClose ? `
        <div class="abw-request-actions">
          <button class="abw-decide-btn abw-decide-close" onclick="_closeOpenAbwesenheit('${e.id}')" style="width:100%;">✔️ Завершить сегодня</button>
        </div>` : ''}
    </div>`;
  }).join('');
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

function _openAbwReasonForm(dateStr) {
  _abwSelectedDate = dateStr;
  document.getElementById('abw-selected-date').textContent = dateStr;
  document.getElementById('abw-reason-form').style.display = 'block';
}

function _closeAbwReasonForm() {
  document.getElementById('abw-reason-form').style.display = 'none';
  document.getElementById('abw-note-input').value = '';
  document.getElementById('abw-date-to-input').value = '';
  document.getElementById('abw-start-time-input').value = '';
  document.getElementById('abw-end-time-input').value = '';
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
  if (currentRole !== 'owner') {
    wrap.style.display = 'none';
    document.getElementById('abw-availability-legend').style.display = 'flex'; // свой календарь — та же 3-состояния легенда
    return;
  }
  wrap.style.display = 'block';
  const select = document.getElementById('abw-profile-select');
  if (select.dataset.wired) return;
  select.dataset.wired = '1';

  try {
    const data = await api('/api/workers');
    const workers = (data.workers || []).filter(w => w.role === 'worker');
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

async function initAbwesenheitView() {
  await _loadAbwAvailability();
  loadAbwesenheit();
  _initAbwProfileSelector();
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
  document.getElementById('abw-save-btn').addEventListener('click', _saveAbwesenheit);
}
