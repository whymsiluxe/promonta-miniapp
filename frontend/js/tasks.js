// Потребности (10.33) — worker → owner список запросов (инструмент/материалы/защита).
// Собственный экран view-tasks (24.07: выделен из общего с Дефектами).
//
// 04.08 (Раунд 3, задача 5): нормальный workflow. Backend-значения открыто/в работе/
// закрыто НЕ мигрируются; UI показывает Новая/Принята/Выполнена. Owner-действия
// контекстны: Новая→«Принять заявку», Принята→«Отметить выполненной», Выполнена→нет
// главной кнопки. Экран получил счётчики, фильтры (по умолчанию Активные) и сортировку.

// Легаси-значения (принято/заказано/выдано/отклонено) сведены к трём стадиям UI.
const TASK_STATUS_LABEL = {
  'открыто': 'Новая', 'в работе': 'Принята', 'закрыто': 'Выполнена',
  'принято': 'Принята', 'заказано': 'Принята', 'выдано': 'Выполнена', 'отклонено': 'Отклонена',
};
function taskStatusLabel(status) { return TASK_STATUS_LABEL[status] || status; }
function taskStage(status) {
  if (status === 'закрыто' || status === 'выдано') return 'done';
  if (status === 'в работе' || status === 'принято' || status === 'заказано') return 'accepted';
  if (status === 'отклонено') return 'done';
  return 'new'; // открыто и всё прочее
}

const TASK_CATEGORY_LABEL = { materials: 'Материалы', tool: 'Инструмент', ppe: 'СИЗ', access: 'Доступ', other: 'Другое' };
function taskCategoryLabel(c) { return TASK_CATEGORY_LABEL[c] || 'Другое'; }

let _tasksList = [];
let _tasksObjectNames = {}; // object_id -> имя (для показа объекта по имени, не ID)
let _tasksFilter = 'active'; // active | new | accepted | done

function _taskWhen(created_at) {
  if (!created_at) return '';
  const d = new Date(created_at * 1000);
  const now = new Date();
  const hhmm = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return `сегодня, ${hhmm}`;
  return `${d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}, ${hhmm}`;
}

function _taskObjectName(objectId) {
  return _tasksObjectNames[objectId] || objectId || '';
}

// Главное действие owner по стадии (или null для «Выполнена»).
function _taskPrimaryAction(status) {
  const st = taskStage(status);
  if (st === 'new') return { label: 'Принять заявку', status: 'в работе' };
  if (st === 'accepted') return { label: 'Отметить выполненной', status: 'закрыто' };
  return null;
}

function renderTaskCard(task) {
  const isOwner = currentRole === 'owner';
  const st = taskStage(task.status);
  const urgent = task.priority === 'срочно';
  const primary = isOwner ? _taskPrimaryAction(task.status) : null;
  const pillClass = st === 'new' ? 'task-pill-new' : st === 'accepted' ? 'task-pill-accepted' : 'task-pill-done';
  return `
  <div class="task-card" data-task-id="${task.id}">
    <div class="task-card-head">
      <div class="task-card-title">${esc(task.title)}</div>
      ${urgent ? '<span class="task-urgent">Срочно</span>' : ''}
    </div>
    <div class="task-card-meta">${esc(taskCategoryLabel(task.category))} · ${esc(_taskObjectName(task.object_id))}</div>
    <div class="task-card-sub">Запросил: ${esc(task.from_name || task.from_user_id || '—')} · ${esc(_taskWhen(task.created_at))}</div>
    <div class="task-card-actions">
      <span class="task-status-pill ${pillClass}">${esc(taskStatusLabel(task.status))}</span>
      <div class="task-card-btns">
        ${primary ? `<button class="submit-btn task-primary-btn" data-task-advance="${task.id}" data-next-status="${esc(primary.status)}" type="button">${esc(primary.label)}</button>` : ''}
        <button class="task-chat-btn" data-task-open-chat="${task.id}" data-task-title="${esc(task.title)}" type="button">Открыть чат</button>
        ${isOwner ? `<button class="task-menu-btn" data-task-menu="${task.id}" type="button" aria-label="Ещё">⋯</button>` : ''}
      </div>
    </div>
  </div>`;
}

function _filteredSortedTasks() {
  const stageRank = { new: 0, accepted: 1, done: 2 };
  let items = _tasksList.slice();
  if (_tasksFilter === 'active') items = items.filter(t => taskStage(t.status) !== 'done');
  else if (_tasksFilter === 'new') items = items.filter(t => taskStage(t.status) === 'new');
  else if (_tasksFilter === 'accepted') items = items.filter(t => taskStage(t.status) === 'accepted');
  else if (_tasksFilter === 'done') items = items.filter(t => taskStage(t.status) === 'done');
  // сортировка: срочные новые → остальные новые → принятые → выполненные (по дате убыв.)
  items.sort((a, b) => {
    const ra = stageRank[taskStage(a.status)], rb = stageRank[taskStage(b.status)];
    if (ra !== rb) return ra - rb;
    if (ra === 0) { // новые: срочные первыми
      const ua = a.priority === 'срочно' ? 0 : 1, ub = b.priority === 'срочно' ? 0 : 1;
      if (ua !== ub) return ua - ub;
    }
    return (b.created_at || 0) - (a.created_at || 0);
  });
  return items;
}

function _renderTasksScreen() {
  const list = document.getElementById('tasks-list');
  // счётчики непрочитанного не нужны — здесь общие количества по стадиям
  const counts = { new: 0, accepted: 0, done: 0 };
  _tasksList.forEach(t => { counts[taskStage(t.status)]++; });
  const countersEl = document.getElementById('tasks-counters');
  if (countersEl) countersEl.innerHTML =
    `<span>Новые <b>${counts.new}</b></span><span>Приняты <b>${counts.accepted}</b></span><span>Выполнены <b>${counts.done}</b></span>`;
  document.querySelectorAll('#tasks-filters .tasks-filter-chip').forEach(c =>
    c.classList.toggle('active', c.dataset.filter === _tasksFilter));

  const items = _filteredSortedTasks();
  if (!items.length) {
    list.innerHTML = '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Ничего нет в этом фильтре</div>';
  } else {
    list.innerHTML = items.map(renderTaskCard).join('');
  }
  _wireTaskCardHandlers(list);

  const badge = document.getElementById('tasks-tab-badge');
  if (badge) {
    const openCount = _tasksList.filter(t => taskStage(t.status) !== 'done').length;
    badge.textContent = openCount;
    badge.style.display = openCount > 0 ? 'flex' : 'none';
  }
}

function _wireTaskCardHandlers(scope) {
  scope.querySelectorAll('[data-task-advance]').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (btn.disabled) return;
      btn.disabled = true;
      const orig = btn.textContent; btn.textContent = '…';
      try {
        await api(`/api/tasks/${btn.dataset.taskAdvance}`, { method: 'PATCH', body: JSON.stringify({ status: btn.dataset.nextStatus }) });
        hapticImpact('light');
        await loadTasks();
        _syncTasksElsewhere();
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
        btn.disabled = false; btn.textContent = orig;
      }
    });
  });
  scope.querySelectorAll('[data-task-open-chat]').forEach(btn => {
    btn.addEventListener('click', () => {
      if (typeof openObjectOrMangelChat === 'function')
        openObjectOrMangelChat(`task:${btn.dataset.taskOpenChat}`, `Потребность: ${btn.dataset.taskTitle}`, { view: 'tasks', taskId: btn.dataset.taskOpenChat });
    });
  });
  scope.querySelectorAll('[data-task-menu]').forEach(btn => {
    btn.addEventListener('click', e => { e.stopPropagation(); openTaskActionMenu(btn.dataset.taskMenu); });
  });
}

function _syncTasksElsewhere() {
  // синхронизировать Object Info и Dashboard-счётчик после изменения статуса
  if (typeof _refreshObjInfoNeeds === 'function') _refreshObjInfoNeeds();
  if (typeof refreshTasksBadge === 'function') refreshTasksBadge();
}

// ── контекстное меню потребности (owner) ──
let _taskMenuEl = null, _taskMenuUnreg = null;
function closeTaskActionMenu() {
  if (_taskMenuEl) { _taskMenuEl.remove(); _taskMenuEl = null; }
  if (_taskMenuUnreg) { _taskMenuUnreg(); _taskMenuUnreg = null; }
}
function openTaskActionMenu(taskId, opts = {}) {
  if (_taskMenuEl) return;
  const task = (opts.task) || _tasksList.find(t => t.id === taskId);
  if (!task || currentRole !== 'owner') return;
  hapticImpact('light');
  const chatReturn = opts.chatReturn || { view: 'tasks', taskId };
  const st = taskStage(task.status);
  const items = [];
  items.push({ label: 'Открыть чат', act: () => {
    closeTaskActionMenu();
    if (typeof openObjectOrMangelChat === 'function')
      openObjectOrMangelChat(`task:${taskId}`, `Потребность: ${task.title}`, chatReturn);
  }});
  if (st !== 'new') items.push({ label: 'Вернуть в новые', act: () => _taskMenuSet(taskId, 'открыто', opts) });
  if (st !== 'done') items.push({ label: 'Отметить выполненной', act: () => _taskMenuSet(taskId, 'закрыто', opts) });

  const overlay = document.createElement('div');
  overlay.className = 'mangel-action-menu-overlay';
  overlay.innerHTML = `<div class="mangel-action-menu-sheet">
    <div class="mangel-action-menu-title">${esc(task.title || 'Потребность').slice(0, 60)}</div>
    ${items.map((it, i) => `<button type="button" class="mangel-action-menu-item" data-idx="${i}">${esc(it.label)}</button>`).join('')}
  </div>`;
  document.body.appendChild(overlay);
  _taskMenuEl = overlay;
  _taskMenuUnreg = (typeof NavigationManager !== 'undefined') ? NavigationManager.registerOverlay(closeTaskActionMenu) : null;
  overlay.addEventListener('click', e => { if (e.target === overlay) closeTaskActionMenu(); });
  overlay.querySelectorAll('.mangel-action-menu-item').forEach(btn => btn.addEventListener('click', () => items[+btn.dataset.idx].act()));
}
async function _taskMenuSet(taskId, status, opts) {
  closeTaskActionMenu();
  try {
    await api(`/api/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify({ status }) });
    hapticImpact('light');
    await loadTasks();
    _syncTasksElsewhere();
    if (opts && opts.onChange) opts.onChange();
  } catch (e) { showToast('Ошибка: ' + e.message, 'error'); }
}

async function loadTasks() {
  const list = document.getElementById('tasks-list');
  list.innerHTML = '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Загрузка…</div>';
  try {
    // объекты — чтобы показывать имя, а не ID (переиспользуем один GET, кэш имён)
    if (!Object.keys(_tasksObjectNames).length) {
      try {
        const objs = await api('/api/objects');
        (objs.objects || []).forEach(o => { const id = o['ID объекта'] || o['Объект']; if (id) _tasksObjectNames[id] = o['Объект'] || id; });
      } catch (e) {}
    }
    const res = await api('/api/tasks');
    _tasksList = res.tasks || [];
    _renderTasksScreen();
  } catch (e) {
    list.innerHTML = `<div style="padding:2rem 0;text-align:center;color:var(--red)">Ошибка: ${esc(e.message)} <button class="wo-retry-btn" type="button" onclick="loadTasks()">Повторить</button></div>`;
  }
}

async function _populateTasksObjectSelect() {
  const select = document.getElementById('tasks-object-select');
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

let _taskPriority = 'обычная';
let _taskCategory = 'materials'; // 27.07 (B7): категория запроса, см. backend TASK_CATEGORIES

function _closeTasksForm() {
  document.getElementById('tasks-form').style.display = 'none';
  document.getElementById('tasks-title-input').value = '';
  document.getElementById('tasks-object-select').value = '';
  _taskPriority = 'обычная';
  _taskCategory = 'materials';
  document.querySelectorAll('#tasks-form .doc-type-opt').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.priority === 'обычная');
  });
  document.querySelectorAll('#tasks-category-row .fw-cat-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.category === 'materials');
  });
}

async function submitTask() {
  const btn = document.getElementById('tasks-submit-btn');
  if (btn.disabled) return;
  const title = document.getElementById('tasks-title-input').value.trim();
  if (!title) { showToast('Укажите, что нужно'); return; }
  const objectId = document.getElementById('tasks-object-select').value;
  if (!objectId) { showToast('Выберите объект'); return; }
  const orig = btn.textContent; btn.disabled = true; btn.textContent = 'Отправка…';
  try {
    await api('/api/tasks', { method: 'POST', body: JSON.stringify({ title, object_id: objectId, priority: _taskPriority, category: _taskCategory }) });
    hapticImpact('light');
    _closeTasksForm();
    await loadTasks();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = orig;
  }
}

function initTasksView() {
  document.getElementById('tasks-new-btn').style.display = currentRole === 'owner' ? 'none' : 'flex';

  document.querySelectorAll('#tasks-filters .tasks-filter-chip').forEach(chip => {
    chip.addEventListener('click', () => { _tasksFilter = chip.dataset.filter; _renderTasksScreen(); hapticImpact('light'); });
  });

  if (currentRole !== 'owner') {
    _populateTasksObjectSelect();
    document.getElementById('tasks-new-btn').addEventListener('click', () => {
      document.getElementById('tasks-form').style.display = 'block';
      hapticImpact('light');
    });
    document.getElementById('tasks-cancel-btn').addEventListener('click', _closeTasksForm);
    document.getElementById('tasks-submit-btn').addEventListener('click', submitTask);
    document.querySelectorAll('#tasks-form .doc-type-opt').forEach(btn => {
      btn.addEventListener('click', () => {
        _taskPriority = btn.dataset.priority;
        document.querySelectorAll('#tasks-form .doc-type-opt').forEach(b => b.classList.toggle('active', b === btn));
        hapticImpact('light');
      });
    });
    document.querySelectorAll('#tasks-category-row .fw-cat-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        _taskCategory = btn.dataset.category;
        document.querySelectorAll('#tasks-category-row .fw-cat-btn').forEach(b => b.classList.toggle('active', b === btn));
        hapticImpact('light');
      });
    });
    attachVoiceInputButton(document.getElementById('tasks-voice-btn'), transcript => {
      const input = document.getElementById('tasks-title-input');
      input.value = input.value ? `${input.value} ${transcript}` : transcript;
    });
  }

  loadTasks();
}
