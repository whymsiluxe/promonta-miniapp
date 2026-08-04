// Mängelmanagement — Kanban дефектов (Фаза 3, real drag-and-drop добавлен 21.07).
// 3 колонки: gemeldet → in Bearbeitung → behoben. Смена статуса — реальный pointer-based
// drag карточки между колонками (тот же паттерн что bubble-assign.js) + tap-to-cycle как fallback
// внутри модалки тикета (для случаев когда drag неудобен/долго тапать одной рукой).
//
// 04.08 (Раунд 3): backend знает 5 статусов (gemeldet/in Bearbeitung/needs_review/behoben/
// rejected). Kanban остаётся 3-колоночным (не большой рефактор): needs_review визуально
// живёт в колонке "В работе", rejected — в "Устранено", но точный русский статус всегда
// виден на карточке через mangelStatusLabel(). Контекстные действия в модалке умеют
// выставлять все 5 значений; тикет при этом не пропадает из Kanban.

const MANGEL_STATUS_ORDER = ['gemeldet', 'in Bearbeitung', 'behoben']; // колонки Kanban
const MANGEL_STATUS_LABEL = { 'gemeldet': 'gemeldet', 'in Bearbeitung': 'in-bearbeitung', 'behoben': 'behoben' };

// 04.08 (Раунд 3, задача 2): единый резолвер русских подписей статусов дефекта.
// Backend-значения (включая немецкие) НЕ мигрируем — переводим только на показ.
const MANGEL_STATUS_LABEL_RU = {
  'gemeldet': 'Новая',
  'in Bearbeitung': 'В работе',
  'needs_review': 'На проверке',
  'behoben': 'Устранено',
  'rejected': 'Отклонено',
};
function mangelStatusLabel(status) {
  return MANGEL_STATUS_LABEL_RU[status] || status;
}
// В какую из 3 колонок Kanban попадает тикет (needs_review→«В работе», rejected→«Устранено»).
function _mangelColumnFor(status) {
  if (status === 'needs_review') return 'in Bearbeitung';
  if (status === 'rejected') return 'behoben';
  return status;
}

let _mangelPhotoFile = null;
let _mangelTickets = [];
let _mangelWorkers = [];        // 04.08 (1.1): кэш /api/workers, чтобы перестраивать optgroup без повторного GET
let _mangelObjectsCache = [];   // 04.08 (1.1): кэш /api/objects (owner видит assigned_users)

// Drag state
let _mangelDragEl = null;
let _mangelDragTicketId = null;
let _mangelDragOffX = 0;
let _mangelDragOffY = 0;
let _mangelDragStartX = 0;
let _mangelDragStartY = 0;
let _mangelDragStarted = false; // отличаем drag от обычного тапа (открыть модалку)
const MANGEL_DRAG_THRESHOLD = 8; // px — минимальное смещение чтобы засчитать как drag, не тап

function _mangelStatusColId(status) {
  return `mangel-col-${MANGEL_STATUS_LABEL[status].replace(/\s/g, '-')}`;
}

function _mangelCountId(status) {
  return `mangel-count-${MANGEL_STATUS_LABEL[status].replace(/\s/g, '-')}`;
}

function renderMangelTicketCard(ticket) {
  const photoThumb = ticket.photo_paths?.length
    ? `<div class="mangel-card-photo" data-auth-bg="/api/mangel/photos/${ticket.photo_paths[0]}/file"></div>`
    : '';
  const commentCount = ticket.comments?.length || 0;
  // 21.07: stat-chip паттерн (тот же что rich-card объектов/инструментов, obj-stat-chip) —
  // единый визуальный язык вместо отдельного простого meta-текста.
  const chips = [
    { label: esc(ticket.object_id) || '—', sub: 'объект', color: 'var(--text-light)' },
  ];
  // 28.07: owner request -- "фиксация кто добавил дефект" видна теперь и в UI, не
  // только в данных (created_by_name резолвится бэкендом).
  if (ticket.created_by_name) chips.push({ label: esc(ticket.created_by_name), sub: 'добавил', color: 'var(--text-light)' });
  if (commentCount) chips.push({ label: `💬 ${commentCount}`, sub: 'комментарии', color: 'var(--text-light)' });
  const chipsHtml = chips.map(c =>
    `<div class="obj-stat-chip"><span class="obj-chip-val" style="color:${c.color}">${c.label}</span><span class="obj-chip-sub">${c.sub}</span></div>`
  ).join('');
  // 04.08 (задача 2): точный русский статус пилюлей на карточке — важно для
  // needs_review/rejected, которые лежат в чужой колонке.
  const statusPill = `<span class="mangel-card-status-pill" data-mst="${esc(ticket.status)}">${esc(mangelStatusLabel(ticket.status))}</span>`;
  return `
  <div class="mangel-card" data-ticket-id="${ticket.id}" data-status="${esc(ticket.status)}">
    ${photoThumb}
    <div class="mangel-card-desc">${esc(ticket.description)}</div>
    ${statusPill}
    <div class="obj-chips-row">${chipsHtml}</div>
  </div>`;
}

async function loadMangelTickets() {
  try {
    const res = await api('/api/mangel');
    _mangelTickets = res.tickets || [];
    renderMangelKanban();
  } catch (e) {
    // 31.07 (UX-аудит): было только console.error -- при реальной ошибке API
    // 3 колонки Kanban оставались пустыми точно как "дефектов нет", разницы
    // юзер увидеть не мог. Показываем явный error-текст в каждой колонке.
    console.error('Ошибка загрузки Mängel-тикетов:', e.message);
    MANGEL_STATUS_ORDER.forEach(status => {
      const col = document.getElementById(_mangelStatusColId(status));
      if (col) col.innerHTML = '<div class="js-error-state">Ошибка загрузки</div>';
    });
  }
}

function renderMangelKanban() {
  // 22.07: фильтр по объекту при переходе с карточки объекта ("🚩 Дефекты объекта") —
  // флаг разовый, применяется один раз и сбрасывается, чтобы не залипал при обычном открытии Дефектов.
  const objectFilter = window._pendingMangelObjectFilter || null;
  window._pendingMangelObjectFilter = null;
  MANGEL_STATUS_ORDER.forEach(colStatus => {
    const col = document.getElementById(_mangelStatusColId(colStatus));
    const countEl = document.getElementById(_mangelCountId(colStatus));
    let tickets = _mangelTickets.filter(t => _mangelColumnFor(t.status) === colStatus);
    if (objectFilter) tickets = tickets.filter(t => t.object_id === objectFilter);
    if (col) col.innerHTML = tickets.map(renderMangelTicketCard).join('') ||
      '<div style="padding:1rem 0;text-align:center;color:var(--text-light);font-size:0.85rem">Пусто</div>';
    if (countEl) countEl.textContent = tickets.length;
  });
  document.querySelectorAll('[data-auth-bg]').forEach(el => authBgImage(el, el.dataset.authBg));
  document.querySelectorAll('.mangel-card').forEach(card => {
    card.addEventListener('pointerdown', _mangelDragPointerDown, { passive: false });
  });
}

function _mangelDragPointerDown(e) {
  _mangelDragEl = e.currentTarget;
  _mangelDragTicketId = _mangelDragEl.dataset.ticketId;
  _mangelDragStarted = false;
  const rect = _mangelDragEl.getBoundingClientRect();
  _mangelDragOffX = e.clientX - rect.left;
  _mangelDragOffY = e.clientY - rect.top;
  _mangelDragStartX = e.clientX;
  _mangelDragStartY = e.clientY;
  _mangelDragEl.setPointerCapture(e.pointerId);
  _mangelDragEl.addEventListener('pointermove', _mangelDragPointerMove, { passive: false });
  _mangelDragEl.addEventListener('pointerup', _mangelDragPointerUp);
}

function _mangelDragPointerMove(e) {
  if (!_mangelDragEl) return;
  const dx = e.clientX - _mangelDragStartX;
  const dy = e.clientY - _mangelDragStartY;
  if (!_mangelDragStarted) {
    if (Math.abs(dx) < MANGEL_DRAG_THRESHOLD && Math.abs(dy) < MANGEL_DRAG_THRESHOLD) return;
    // Порог превышен — это реальный drag, не тап. Переключаем карточку в fixed-режим перетаскивания.
    _mangelDragStarted = true;
    const rect = _mangelDragEl.getBoundingClientRect();
    _mangelDragEl.style.position = 'fixed';
    _mangelDragEl.style.width = rect.width + 'px';
    _mangelDragEl.style.zIndex = '9999';
    _mangelDragEl.style.pointerEvents = 'none';
    _mangelDragEl.classList.add('mangel-card-dragging');
    hapticImpact('light');
  }
  e.preventDefault();
  _mangelDragEl.style.left = (e.clientX - _mangelDragOffX) + 'px';
  _mangelDragEl.style.top = (e.clientY - _mangelDragOffY) + 'px';

  document.querySelectorAll('.mangel-column-body').forEach(col => {
    const r = col.getBoundingClientRect();
    const over = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
    col.classList.toggle('mangel-drop-zone-active', over);
  });
}

async function _mangelDragPointerUp(e) {
  if (!_mangelDragEl) return;
  _mangelDragEl.removeEventListener('pointermove', _mangelDragPointerMove);
  _mangelDragEl.removeEventListener('pointerup', _mangelDragPointerUp);
  document.querySelectorAll('.mangel-column-body').forEach(col => col.classList.remove('mangel-drop-zone-active'));

  if (!_mangelDragStarted) {
    // Обычный тап без движения — не drag, оставить карточку как есть, дать сработать click-хендлеру модалки.
    _mangelDragEl = null;
    return;
  }

  let droppedStatus = null;
  document.querySelectorAll('.mangel-column-body').forEach(col => {
    const r = col.getBoundingClientRect();
    if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) {
      droppedStatus = MANGEL_STATUS_ORDER.find(s => _mangelStatusColId(s) === col.id);
    }
  });

  const ticketId = _mangelDragTicketId;
  const ticket = _mangelTickets.find(t => t.id === ticketId);
  _mangelDragEl.style.position = '';
  _mangelDragEl.style.left = '';
  _mangelDragEl.style.top = '';
  _mangelDragEl.style.width = '';
  _mangelDragEl.style.zIndex = '';
  _mangelDragEl.style.pointerEvents = '';
  _mangelDragEl.classList.remove('mangel-card-dragging');
  _mangelDragEl = null;

  // Сравниваем по колонке, а не по сырому статусу: тащить needs_review-тикет в
  // колонку «В работе» не должно триггерить бессмысленный PATCH.
  if (droppedStatus && ticket && droppedStatus !== _mangelColumnFor(ticket.status)) {
    try {
      await api(`/api/mangel/${ticketId}/status`, { method: 'PATCH', body: JSON.stringify({ status: droppedStatus }) });
      hapticImpact('medium');
      await loadMangelTickets();
    } catch (e) {
      showToast('Ошибка смены статуса: ' + e.message, 'error');
      renderMangelKanban(); // откатить визуал к последнему известному состоянию с сервера
    }
  } else {
    renderMangelKanban(); // не сброшено в другую колонку — просто перерисовать на исходное место
  }

  // Оставляем _mangelDragStarted=true до следующего pointerdown, чтобы click-хендлер не открыл модалку сразу после drop
  setTimeout(() => { _mangelDragStarted = false; }, 50);
}

// 04.08 (задача 4): контекстные действия по статусу — вместо сырого "Далее →".
// Возвращает список { label, status } возможных переходов для текущего статуса.
// Только owner может менять статус (backend require_owner), поэтому вызывается под гейтом роли.
function _mangelContextActions(status) {
  switch (status) {
    case 'gemeldet':        return [{ label: 'Взять в работу', status: 'in Bearbeitung' }, { label: 'Отклонить', status: 'rejected' }];
    case 'in Bearbeitung':  return [{ label: 'Отправить на проверку', status: 'needs_review' }, { label: 'Отметить устранённым', status: 'behoben' }, { label: 'Вернуть в новые', status: 'gemeldet' }];
    case 'needs_review':    return [{ label: 'Отметить устранённым', status: 'behoben' }, { label: 'Вернуть в работу', status: 'in Bearbeitung' }];
    case 'behoben':         return [{ label: 'Вернуть в работу', status: 'in Bearbeitung' }];
    case 'rejected':        return [{ label: 'Вернуть в новые', status: 'gemeldet' }];
    default:                return [];
  }
}

async function _setMangelStatus(ticketId, status) {
  try {
    await api(`/api/mangel/${ticketId}/status`, { method: 'PATCH', body: JSON.stringify({ status }) });
    hapticImpact('light');
    await loadMangelTickets();
    return true;
  } catch (e) {
    showToast('Ошибка смены статуса: ' + e.message, 'error');
    return false;
  }
}

async function openMangelTicketModal(ticketId) {
  const ticket = _mangelTickets.find(t => t.id === ticketId);
  if (!ticket) return;
  document.getElementById('mangel-modal-title').textContent = ticket.object_id || 'Тикет';
  const body = document.getElementById('mangel-modal-body');
  const photoBlock = ticket.photo_paths?.length
    ? `<div class="mangel-modal-photo" data-auth-bg="/api/mangel/photos/${ticket.photo_paths[0]}/file"></div>` : '';
  const commentsHtml = (ticket.comments || []).map(c =>
    `<div class="mangel-comment"><b>${esc(c.name || c.user_id)}</b><div>${esc(c.text)}</div></div>`).join('');

  const isOwner = currentRole === 'owner';
  const actions = isOwner ? _mangelContextActions(ticket.status) : [];
  // Первое действие — главная кнопка, остальные — вторичные.
  const primary = actions[0];
  const secondary = actions.slice(1);
  const primaryHtml = primary
    ? `<button class="submit-btn" id="mangel-modal-primary-action" type="button" data-next="${esc(primary.status)}" style="margin-top:0.5rem;">${esc(primary.label)}</button>`
    : '';
  const secondaryHtml = secondary.length
    ? `<div class="mangel-modal-secondary-actions">${secondary.map(a =>
        `<button class="mangel-modal-secondary-btn" type="button" data-next="${esc(a.status)}">${esc(a.label)}</button>`).join('')}</div>`
    : '';
  const deleteHtml = isOwner
    ? `<button class="mangel-modal-delete-btn" id="mangel-modal-delete-btn" type="button">Удалить дефект</button>`
    : '';

  body.innerHTML = `
    ${photoBlock}
    <div class="mangel-modal-desc">${esc(ticket.description)}</div>
    <div class="mangel-modal-detail-grid">
      <div class="mangel-modal-detail-row"><span>Статус</span><b>${esc(mangelStatusLabel(ticket.status))}</b></div>
      <div class="mangel-modal-detail-row"><span>Ответственный</span><b>${ticket.assigned_worker_name ? esc(ticket.assigned_worker_name) : (ticket.created_by_name ? esc(ticket.created_by_name) : 'Нет ответственного')}</b></div>
      <div class="mangel-modal-detail-row"><span>Объект</span><b>${esc(ticket.object_id || '—')}</b></div>
      ${ticket.created_by_name ? `<div class="mangel-modal-detail-row"><span>Создал</span><b>${esc(ticket.created_by_name)}</b></div>` : ''}
    </div>
    ${primaryHtml}
    ${secondaryHtml}
    <div class="mangel-comments-list">${commentsHtml || '<div style="color:var(--text-light);font-size:0.85rem">Комментариев нет</div>'}</div>
    <div class="mangel-comment-input-row">
      <input type="text" id="mangel-comment-input" placeholder="Комментарий…" class="mangel-select">
      <button class="submit-btn" id="mangel-comment-send-btn" type="button" style="padding:0.5rem 1rem;">➤</button>
    </div>
    <button class="submit-btn" id="mangel-open-chat-btn" type="button" style="margin-top:0.6rem;background:var(--bg-card-raised);color:var(--text-main);">Открыть чат</button>
    ${deleteHtml}
  `;
  body.querySelectorAll('[data-auth-bg]').forEach(el => authBgImage(el, el.dataset.authBg));

  document.getElementById('mangel-open-chat-btn').addEventListener('click', () => {
    if (typeof openObjectOrMangelChat === 'function') {
      document.getElementById('mangel-ticket-modal').style.display = 'none';
      // 04.08 (задача 6): структурированный контекст возврата — назад в этот тикет.
      openObjectOrMangelChat(`mangel:${ticketId}`, `Тикет: ${ticket.object_id || ticketId}`, { view: 'mangel', ticketId });
    }
  });

  document.getElementById('mangel-modal-primary-action')?.addEventListener('click', async (e) => {
    if (await _setMangelStatus(ticketId, e.currentTarget.dataset.next)) openMangelTicketModal(ticketId);
  });
  body.querySelectorAll('.mangel-modal-secondary-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (await _setMangelStatus(ticketId, btn.dataset.next)) openMangelTicketModal(ticketId);
    });
  });
  document.getElementById('mangel-modal-delete-btn')?.addEventListener('click', () => _deleteMangelTicket(ticketId));

  document.getElementById('mangel-comment-send-btn').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const input = document.getElementById('mangel-comment-input');
    if (!input.value.trim() || btn.disabled) return;
    // 31.07 (UX-аудит): без disable быстрый двойной тап отправлял 2 одинаковых
    // комментария до возврата первого ответа.
    btn.disabled = true;
    try {
      await api(`/api/mangel/${ticketId}/comments`, { method: 'POST', body: JSON.stringify({ text: input.value.trim() }) });
      input.value = '';
      await loadMangelTickets();
      openMangelTicketModal(ticketId);
    } catch (e) {
      showToast('Ошибка отправки комментария: ' + e.message, 'error');
    } finally {
      btn.disabled = false;
    }
  });
  document.getElementById('mangel-ticket-modal').style.display = 'flex';
  _updateMangelFab();
}

// 04.08 (задача 3.2): единое контекстное меню дефекта. Открывается и long-press,
// и кнопкой ⋯ на строке дефекта в Object Info. Одно меню одновременно; закрывается
// backdrop/Telegram Back (registerOverlay); z-index выше Object Detail.
let _mangelMenuEl = null;
let _mangelMenuUnreg = null;
function closeMangelActionMenu() {
  if (_mangelMenuEl) { _mangelMenuEl.remove(); _mangelMenuEl = null; }
  if (_mangelMenuUnreg) { _mangelMenuUnreg(); _mangelMenuUnreg = null; }
}
function openMangelActionMenu(ticketId, opts = {}) {
  if (_mangelMenuEl) return; // одно меню одновременно
  const ticket = (opts.ticket) || _mangelTickets.find(t => t.id === ticketId);
  if (!ticket) return;
  const isOwner = currentRole === 'owner';
  hapticImpact('light');

  const items = [];
  items.push({ label: 'Открыть', act: () => { closeMangelActionMenu(); openMangelTicketModal(ticketId); } });
  items.push({ label: 'Перейти в чат', act: () => {
    closeMangelActionMenu();
    if (typeof openObjectOrMangelChat === 'function')
      openObjectOrMangelChat(`mangel:${ticketId}`, `Тикет: ${ticket.object_id || ticketId}`, { view: 'mangel', ticketId });
  }});
  if (isOwner) {
    // Контекстные переходы по статусу — только осмысленные для текущего статуса.
    _mangelContextActions(ticket.status).forEach(a => {
      items.push({ label: a.label, act: async () => { closeMangelActionMenu(); if (await _setMangelStatus(ticketId, a.status) && opts.onChange) opts.onChange(); } });
    });
    items.push({ label: 'Удалить', danger: true, act: async () => { closeMangelActionMenu(); await _deleteMangelTicket(ticketId); if (opts.onChange) opts.onChange(); } });
  }

  const overlay = document.createElement('div');
  overlay.className = 'mangel-action-menu-overlay';
  overlay.innerHTML = `<div class="mangel-action-menu-sheet">
    <div class="mangel-action-menu-title">${esc(ticket.description || 'Дефект').slice(0, 60)}</div>
    ${items.map((it, i) => `<button type="button" class="mangel-action-menu-item${it.danger ? ' danger' : ''}" data-idx="${i}">${esc(it.label)}</button>`).join('')}
  </div>`;
  document.body.appendChild(overlay);
  _mangelMenuEl = overlay;
  _mangelMenuUnreg = (typeof NavigationManager !== 'undefined') ? NavigationManager.registerOverlay(closeMangelActionMenu) : null;
  overlay.addEventListener('click', e => { if (e.target === overlay) closeMangelActionMenu(); });
  overlay.querySelectorAll('.mangel-action-menu-item').forEach(btn => {
    btn.addEventListener('click', () => items[+btn.dataset.idx].act());
  });
}

// 04.08 (задача 3.3): Owner-only soft delete. Подтверждение обязательно.
async function _deleteMangelTicket(ticketId) {
  if (currentRole !== 'owner') return;
  if (!confirm('Удалить дефект? Дефект исчезнет из рабочих списков.')) return;
  try {
    await api(`/api/mangel/${ticketId}`, { method: 'DELETE' });
    hapticImpact('medium');
    document.getElementById('mangel-ticket-modal').style.display = 'none';
    await loadMangelTickets();
    // Синхронизируем Object Info, если оно открыто на этом объекте.
    if (typeof _refreshObjInfoDefects === 'function') _refreshObjInfoDefects();
    showToast('Дефект удалён', 'success');
  } catch (e) {
    showToast('Ошибка удаления: ' + e.message, 'error');
  }
}

async function _populateMangelObjectSelect() {
  const select = document.getElementById('mangel-object-select');
  if (select.dataset.populated) return;
  try {
    const res = await api('/api/objects');
    _mangelObjectsCache = res.objects || [];
    _mangelObjectsCache.forEach(obj => {
      const opt = document.createElement('option');
      opt.value = obj['ID объекта'] || obj['Объект'];
      opt.textContent = obj['Объект'] || opt.value;
      select.appendChild(opt);
    });
    select.dataset.populated = '1';
  } catch (e) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = '⚠️ Объекты недоступны — попробуй позже';
    opt.disabled = true;
    select.appendChild(opt);
  }
}

// 04.08 (задача 1.1): список работников с назначенными на объект первыми.
// Загружает /api/workers один раз в кэш, а optgroup-структуру перестраивает
// при каждой смене объекта (без повторного GET).
async function _populateMangelWorkerSelect() {
  const select = document.getElementById('mangel-worker-select');
  if (currentRole !== 'owner') { select.style.display = 'none'; return; }
  select.style.display = 'block';
  if (!_mangelWorkers.length) {
    try {
      const res = await api('/api/workers');
      _mangelWorkers = (res.workers || []).filter(w => w.role === 'worker');
    } catch (e) { _mangelWorkers = []; }
  }
  _rebuildMangelWorkerOptions(document.getElementById('mangel-object-select').value);
}

function _rebuildMangelWorkerOptions(objectId) {
  const select = document.getElementById('mangel-worker-select');
  if (!select) return;
  const prev = select.value; // сохранить выбор если возможно (не сбрасывать без причины)
  // accepted-назначения на выбранный объект (owner /api/objects даёт assigned_users).
  let assignedIds = new Set();
  if (objectId) {
    const obj = _mangelObjectsCache.find(o => (o['ID объекта'] || o['Объект']) === objectId);
    (obj?.assigned_users || []).forEach(u => {
      if ((u.assignment_status || 'accepted') === 'accepted') assignedIds.add(String(u.user_id));
    });
  }
  const byName = (a, b) => (a.name || '').localeCompare(b.name || '', 'ru');
  const assigned = _mangelWorkers.filter(w => assignedIds.has(String(w.user_id))).sort(byName);
  const rest = _mangelWorkers.filter(w => !assignedIds.has(String(w.user_id))).sort(byName);

  const optHtml = w => `<option value="${esc(w.user_id)}">${esc(w.name || 'Сотрудник')}</option>`;
  let html = '<option value="">Назначить работника (необязательно)…</option>';
  if (objectId && assigned.length) {
    html += `<optgroup label="Назначены на объект">${assigned.map(optHtml).join('')}</optgroup>`;
    if (rest.length) html += `<optgroup label="Остальные сотрудники">${rest.map(optHtml).join('')}</optgroup>`;
  } else {
    // без объекта или без назначенных — обычный алфавитный список
    html += [...assigned, ...rest].sort(byName).map(optHtml).join('');
  }
  select.innerHTML = html;
  // восстановить прежний выбор, если работник ещё присутствует
  if (prev && select.querySelector(`option[value="${CSS.escape(prev)}"]`)) select.value = prev;
}

async function submitMangelTicket() {
  const submitBtn = document.getElementById('mangel-submit-btn');
  if (submitBtn.disabled) return; // 04.08 (1.4): двойной тап не создаёт два тикета
  const objectId = document.getElementById('mangel-object-select').value;
  const description = document.getElementById('mangel-description').value.trim();
  if (!objectId) { showToast('Выберите объект'); return; }
  if (!description) { showToast('Опишите дефект'); return; }

  const workerSelect = document.getElementById('mangel-worker-select');
  const assignedWorkerId = (currentRole === 'owner' && workerSelect) ? workerSelect.value : '';

  const formData = new FormData();
  formData.append('object_id', objectId);
  formData.append('description', description);
  if (assignedWorkerId) formData.append('assigned_worker_id', assignedWorkerId);
  if (_mangelPhotoFile) formData.append('file', _mangelPhotoFile);

  const origLabel = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = 'Создание…';
  try {
    await fetch(`${API_BASE}/api/mangel`, {
      method: 'POST',
      headers: { ..._authHeaders() },
      body: formData,
    }).then(async res => {
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
      return res.json();
    });
    hapticImpact('light');
    const returnObj = window._mangelReturnToObject || null;
    _closeMangelForm();
    await loadMangelTickets();
    showToast('Дефект создан', 'success');
    // 04.08 (1.4): если форму открыли из Object Info — вернуться туда и обновить секцию Дефекты.
    if (returnObj && typeof openObjectDetail === 'function') {
      window._mangelReturnToObject = null;
      openObjectDetail(returnObj.objectId, returnObj.objectName, 'info');
    }
  } catch (e) {
    // При ошибке НЕ очищаем поля/фото — юзер не теряет введённое.
    showToast('Ошибка создания тикета: ' + e.message, 'error');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = origLabel;
  }
}

function _openMangelForm() {
  document.getElementById('mangel-form').style.display = 'block';
  _updateMangelFab();
  hapticImpact('light');
}

function _closeMangelForm() {
  document.getElementById('mangel-form').style.display = 'none';
  document.getElementById('mangel-description').value = '';
  _clearMangelPhoto();
  _updateMangelFab();
}

function _clearMangelPhoto() {
  _mangelPhotoFile = null;
  const preview = document.getElementById('mangel-photo-preview');
  preview.style.display = 'none';
  preview.style.backgroundImage = '';
  preview.innerHTML = '';
  // сброс value обоих input, чтобы повторный выбор того же файла тоже сработал (change)
  const cam = document.getElementById('mangel-camera-input');
  const gal = document.getElementById('mangel-gallery-input');
  if (cam) cam.value = '';
  if (gal) gal.value = '';
}

function _showMangelPhotoPreview(file) {
  _mangelPhotoFile = file;
  const preview = document.getElementById('mangel-photo-preview');
  preview.style.display = 'block';
  preview.style.backgroundImage = `url('${URL.createObjectURL(file)}')`;
  preview.innerHTML = `
    <div class="mangel-photo-preview-actions">
      <button type="button" id="mangel-photo-replace" data-target="gallery">Заменить</button>
      <button type="button" id="mangel-photo-remove" class="danger">Удалить фото</button>
    </div>`;
  document.getElementById('mangel-photo-replace').addEventListener('click', () => {
    document.getElementById('mangel-gallery-input').click();
  });
  document.getElementById('mangel-photo-remove').addEventListener('click', _clearMangelPhoto);
}

// FAB виден только когда экран Дефекты активен, форма и модалка закрыты.
function _updateMangelFab() {
  const fab = document.getElementById('mangel-new-btn');
  if (!fab) return;
  const formOpen = document.getElementById('mangel-form')?.style.display === 'block';
  const modalOpen = document.getElementById('mangel-ticket-modal')?.style.display === 'flex';
  fab.classList.toggle('visible', !formOpen && !modalOpen);
}

function initMangelView() {
  loadMangelTickets();
  _populateMangelObjectSelect().then(() => _populateMangelWorkerSelect());
  _updateMangelFab();

  document.getElementById('mangel-new-btn').addEventListener('click', _openMangelForm);
  document.getElementById('mangel-cancel-btn').addEventListener('click', _closeMangelForm);
  document.getElementById('mangel-submit-btn').addEventListener('click', submitMangelTicket);
  attachVoiceInputButton(document.getElementById('mangel-voice-btn'), transcript => {
    const input = document.getElementById('mangel-description');
    input.value = input.value ? `${input.value} ${transcript}` : transcript;
  });

  // 04.08 (1.1): при смене объекта пересчитываем список работников (назначенные — первыми).
  document.getElementById('mangel-object-select').addEventListener('change', e => {
    _rebuildMangelWorkerOptions(e.target.value);
  });

  // 04.08 (1.3): две явные кнопки камера/галерея + preview с заменой/удалением.
  document.getElementById('mangel-camera-btn').addEventListener('click', () => document.getElementById('mangel-camera-input').click());
  document.getElementById('mangel-gallery-btn').addEventListener('click', () => document.getElementById('mangel-gallery-input').click());
  const onPhotoPicked = e => { const f = e.target.files[0]; if (f) _showMangelPhotoPreview(f); };
  document.getElementById('mangel-camera-input').addEventListener('change', onPhotoPicked);
  document.getElementById('mangel-gallery-input').addEventListener('change', onPhotoPicked);

  document.querySelector('.mangel-kanban').addEventListener('click', e => {
    if (_mangelDragStarted) return; // клик после реального drag — игнорировать, иначе модалка откроется вдобавок к DnD
    const card = e.target.closest('.mangel-card');
    if (card) openMangelTicketModal(card.dataset.ticketId);
  });

  document.getElementById('mangel-modal-close-btn').addEventListener('click', () => {
    document.getElementById('mangel-ticket-modal').style.display = 'none';
    _updateMangelFab();
  });
}
