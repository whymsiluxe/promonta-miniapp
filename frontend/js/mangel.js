// Mängelmanagement — Kanban дефектов (Фаза 3, real drag-and-drop добавлен 21.07).
// 3 колонки: gemeldet → in Bearbeitung → behoben. Смена статуса — реальный pointer-based
// drag карточки между колонками (тот же паттерн что bubble-assign.js) + tap-to-cycle как fallback
// внутри модалки тикета (для случаев когда drag неудобен/долго тапать одной рукой).

const MANGEL_STATUS_ORDER = ['gemeldet', 'in Bearbeitung', 'behoben'];
const MANGEL_STATUS_LABEL = { 'gemeldet': 'gemeldet', 'in Bearbeitung': 'in-bearbeitung', 'behoben': 'behoben' };
const MANGEL_STATUS_LABEL_RU = { 'gemeldet': 'Новая', 'in Bearbeitung': 'В работе', 'behoben': 'Устранено' };
let _mangelPhotoFile = null;
let _mangelTickets = [];

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
  return `
  <div class="mangel-card" data-ticket-id="${ticket.id}" data-status="${esc(ticket.status)}">
    ${photoThumb}
    <div class="mangel-card-desc">${esc(ticket.description)}</div>
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
  MANGEL_STATUS_ORDER.forEach(status => {
    const col = document.getElementById(_mangelStatusColId(status));
    const countEl = document.getElementById(_mangelCountId(status));
    let tickets = _mangelTickets.filter(t => t.status === status);
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

  if (droppedStatus && ticket && droppedStatus !== ticket.status) {
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

function _mangelNextStatus(current) {
  const idx = MANGEL_STATUS_ORDER.indexOf(current);
  return MANGEL_STATUS_ORDER[Math.min(idx + 1, MANGEL_STATUS_ORDER.length - 1)];
}

async function cycleMangelStatus(ticketId) {
  const ticket = _mangelTickets.find(t => t.id === ticketId);
  if (!ticket) return;
  const next = _mangelNextStatus(ticket.status);
  if (next === ticket.status) return; // уже в конечном статусе behoben
  try {
    await api(`/api/mangel/${ticketId}/status`, { method: 'PATCH', body: JSON.stringify({ status: next }) });
    hapticImpact('light');
    await loadMangelTickets();
  } catch (e) {
    showToast('Ошибка смены статуса: ' + e.message, 'error');
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
  body.innerHTML = `
    ${photoBlock}
    <div class="mangel-modal-desc">${esc(ticket.description)}</div>
    <div class="mangel-modal-status">Статус: <b>${esc(MANGEL_STATUS_LABEL_RU[ticket.status] || ticket.status)}</b> <button class="submit-btn" id="mangel-modal-cycle-btn" type="button" style="display:inline-block;padding:0.3rem 0.8rem;">Далее →</button></div>
    <div class="mangel-comments-list">${commentsHtml || '<div style="color:var(--text-light);font-size:0.85rem">Комментариев нет</div>'}</div>
    <div class="mangel-comment-input-row">
      <input type="text" id="mangel-comment-input" placeholder="Комментарий…" class="mangel-select">
      <button class="submit-btn" id="mangel-comment-send-btn" type="button" style="padding:0.5rem 1rem;">➤</button>
    </div>
    <button class="submit-btn" id="mangel-open-chat-btn" type="button" style="margin-top:0.6rem;background:var(--bg-card-raised);color:var(--text-main);">💬 Полный чат по тикету</button>
  `;
  body.querySelectorAll('[data-auth-bg]').forEach(el => authBgImage(el, el.dataset.authBg));
  document.getElementById('mangel-open-chat-btn').addEventListener('click', () => {
    if (typeof openObjectOrMangelChat === 'function') {
      document.getElementById('mangel-ticket-modal').style.display = 'none';
      openObjectOrMangelChat(`mangel:${ticketId}`, `Тикет: ${ticket.object_id || ticketId}`, 'mangel');
    }
  });
  document.getElementById('mangel-modal-cycle-btn').addEventListener('click', async () => {
    await cycleMangelStatus(ticketId);
    openMangelTicketModal(ticketId);
  });
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
}

async function _populateMangelObjectSelect() {
  const select = document.getElementById('mangel-object-select');
  if (select.dataset.populated) return;
  try {
    const res = await api('/api/objects');
    (res.objects || []).forEach(obj => {
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

async function _populateMangelWorkerSelect() {
  const select = document.getElementById('mangel-worker-select');
  if (currentRole !== 'owner') { select.style.display = 'none'; return; }
  select.style.display = 'block';
  if (select.dataset.populated) return;
  try {
    const res = await api('/api/workers');
    (res.workers || []).filter(w => w.role === 'worker').forEach(w => {
      const opt = document.createElement('option');
      opt.value = w.user_id;
      opt.textContent = w.name;
      select.appendChild(opt);
    });
    select.dataset.populated = '1';
  } catch (e) {}
}

async function submitMangelTicket() {
  const objectId = document.getElementById('mangel-object-select').value;
  const description = document.getElementById('mangel-description').value.trim();
  if (!description) { showToast('Опишите дефект'); return; }

  const workerSelect = document.getElementById('mangel-worker-select');
  const assignedWorkerId = (currentRole === 'owner' && workerSelect) ? workerSelect.value : '';

  const formData = new FormData();
  formData.append('object_id', objectId);
  formData.append('description', description);
  if (assignedWorkerId) formData.append('assigned_worker_id', assignedWorkerId);
  if (_mangelPhotoFile) formData.append('file', _mangelPhotoFile);

  try {
    await fetch(`${API_BASE}/api/mangel`, {
      method: 'POST',
      headers: { 'X-Telegram-Init-Data': initData },
      body: formData,
    }).then(async res => {
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
      return res.json();
    });
    hapticImpact('light');
    _closeMangelForm();
    await loadMangelTickets();
  } catch (e) {
    showToast('Ошибка создания тикета: ' + e.message, 'error');
  }
}

function _closeMangelForm() {
  document.getElementById('mangel-form').style.display = 'none';
  document.getElementById('mangel-description').value = '';
  document.getElementById('mangel-photo-preview').style.display = 'none';
  document.getElementById('mangel-photo-preview').innerHTML = '';
  document.getElementById('mangel-photo-input').value = '';
  _mangelPhotoFile = null;
}

function initMangelView() {
  loadMangelTickets();
  _populateMangelObjectSelect();
  _populateMangelWorkerSelect();

  document.getElementById('mangel-new-btn').addEventListener('click', () => {
    document.getElementById('mangel-form').style.display = 'block';
    hapticImpact('light');
  });
  document.getElementById('mangel-cancel-btn').addEventListener('click', _closeMangelForm);
  document.getElementById('mangel-submit-btn').addEventListener('click', submitMangelTicket);
  attachVoiceInputButton(document.getElementById('mangel-voice-btn'), transcript => {
    const input = document.getElementById('mangel-description');
    input.value = input.value ? `${input.value} ${transcript}` : transcript;
  });

  document.getElementById('mangel-photo-input').addEventListener('change', e => {
    const file = e.target.files[0];
    if (!file) return;
    _mangelPhotoFile = file;
    const preview = document.getElementById('mangel-photo-preview');
    preview.style.display = 'block';
    preview.style.backgroundImage = `url('${URL.createObjectURL(file)}')`;
  });

  document.querySelector('.mangel-kanban').addEventListener('click', e => {
    if (_mangelDragStarted) return; // клик после реального drag — игнорировать, иначе модалка откроется вдобавок к DnD
    const card = e.target.closest('.mangel-card');
    if (card) openMangelTicketModal(card.dataset.ticketId);
  });

  document.getElementById('mangel-modal-close-btn').addEventListener('click', () => {
    document.getElementById('mangel-ticket-modal').style.display = 'none';
  });
}
