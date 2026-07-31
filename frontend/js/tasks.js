// Потребности (10.33) — worker → owner список запросов (инструмент/материалы/защита).
// Собственный экран view-tasks (24.07: выделен из общего с Дефектами). Второе направление
// (owner → worker "задачи") отложено — см. TODO в плане.

const TASK_STATUS_LABEL = { 'открыто': 'Открыто', 'в работе': 'В работе', 'закрыто': 'Закрыто' };
let _tasksList = [];

function renderTaskCard(task) {
  const isOwner = currentRole === 'owner';
  const statusColor = task.status === 'открыто' ? 'var(--warning)' : task.status === 'в работе' ? 'var(--accent)' : 'var(--text-light)';
  const nextStatus = task.status === 'открыто' ? 'в работе' : task.status === 'в работе' ? 'закрыто' : null;
  return `
  <div class="mangel-card" data-task-id="${task.id}" style="${task.priority === 'срочно' ? 'border-left:3px solid var(--red);' : ''}">
    <div class="mangel-card-desc">${task.priority === 'срочно' ? '🔴 ' : ''}<b>${esc(task.title)}</b>${task.description ? `<div style="margin-top:0.3rem;font-size:0.85rem;color:var(--text-light)">${esc(task.description)}</div>` : ''}</div>
    <div class="mangel-card-meta">
      <span>${esc(task.from_name || task.from_user_id)}</span>
      ${task.object_id ? `<span>${esc(task.object_id)}</span>` : ''}
      <span style="color:${statusColor}">${esc(TASK_STATUS_LABEL[task.status] || task.status)}</span>
    </div>
    ${isOwner && nextStatus ? `<button class="submit-btn" data-task-advance="${task.id}" data-next-status="${nextStatus}" style="margin-top:0.5rem;padding:0.4rem 0.8rem;font-size:0.8rem;">${nextStatus === 'закрыто' ? 'Закрыть' : 'Взять в работу'}</button>` : ''}
    <button class="chat-extract-task-btn" data-task-open-chat="${task.id}" data-task-title="${esc(task.title)}" type="button" style="margin-top:0.5rem;">💬 Чат по потребности</button>
  </div>`;
}

async function loadTasks() {
  const list = document.getElementById('tasks-list');
  // 31.07 (UX-аудит): было -- экран выглядел пустым/сломанным пока запрос в
  // полёте, разницы с "потребностей нет" не было видно.
  list.innerHTML = '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Загрузка…</div>';
  try {
    const res = await api('/api/tasks');
    _tasksList = res.tasks || [];
    if (!_tasksList.length) {
      list.innerHTML = '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Потребностей пока нет</div>';
    } else {
      list.innerHTML = _tasksList.map(renderTaskCard).join('');
    }
    list.querySelectorAll('[data-task-advance]').forEach(btn => {
      btn.addEventListener('click', async () => {
        try {
          await api(`/api/tasks/${btn.dataset.taskAdvance}`, { method: 'PATCH', body: JSON.stringify({ status: btn.dataset.nextStatus }) });
          hapticImpact('light');
          await loadTasks();
        } catch (e) {
          showToast('Ошибка: ' + e.message, 'error');
        }
      });
    });
    list.querySelectorAll('[data-task-open-chat]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (typeof openObjectOrMangelChat === 'function') {
          openObjectOrMangelChat(`task:${btn.dataset.taskOpenChat}`, `Потребность: ${btn.dataset.taskTitle}`, 'tasks');
        }
      });
    });
    const badge = document.getElementById('tasks-tab-badge');
    if (badge) {
      const openCount = _tasksList.filter(t => t.status !== 'закрыто').length;
      badge.textContent = openCount;
      badge.style.display = openCount > 0 ? 'flex' : 'none';
    }
  } catch (e) {
    list.innerHTML = `<div style="padding:2rem 0;text-align:center;color:var(--red)">Ошибка: ${esc(e.message)}</div>`;
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
  const title = document.getElementById('tasks-title-input').value.trim();
  if (!title) { showToast('Укажите, что нужно'); return; }
  const objectId = document.getElementById('tasks-object-select').value;
  if (!objectId) { showToast('Выберите объект'); return; }
  try {
    await api('/api/tasks', { method: 'POST', body: JSON.stringify({ title, object_id: objectId, priority: _taskPriority, category: _taskCategory }) });
    hapticImpact('light');
    _closeTasksForm();
    await loadTasks();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

function initTasksView() {
  document.getElementById('tasks-new-btn').style.display = currentRole === 'owner' ? 'none' : 'flex';

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
