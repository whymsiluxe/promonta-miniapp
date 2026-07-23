// Потребности (10.33) — worker → owner список запросов (инструмент/материалы/защита).
// Переключатель внутри экрана Дефекты (doc-type-opt[data-mangel-tab]). Второе направление
// (owner → worker "задачи") отложено — см. TODO в плане.

const TASK_STATUS_LABEL = { 'открыто': 'Открыто', 'в работе': 'В работе', 'закрыто': 'Закрыто' };
let _tasksList = [];
let _mangelActiveTab = 'tasks';

function renderTaskCard(task) {
  const isOwner = currentRole === 'owner';
  const statusColor = task.status === 'открыто' ? 'var(--warning)' : task.status === 'в работе' ? 'var(--accent)' : 'var(--text-light)';
  const nextStatus = task.status === 'открыто' ? 'в работе' : task.status === 'в работе' ? 'закрыто' : null;
  return `
  <div class="mangel-card" data-task-id="${task.id}">
    <div class="mangel-card-desc"><b>${esc(task.title)}</b>${task.description ? `<div style="margin-top:0.3rem;font-size:0.85rem;color:var(--text-light)">${esc(task.description)}</div>` : ''}</div>
    <div class="mangel-card-meta">
      <span>${esc(task.from_name || task.from_user_id)}</span>
      ${task.object_id ? `<span>${esc(task.object_id)}</span>` : ''}
      <span style="color:${statusColor}">${TASK_STATUS_LABEL[task.status] || task.status}</span>
    </div>
    ${isOwner && nextStatus ? `<button class="submit-btn" data-task-advance="${task.id}" data-next-status="${nextStatus}" style="margin-top:0.5rem;padding:0.4rem 0.8rem;font-size:0.8rem;">${nextStatus === 'закрыто' ? 'Закрыть' : 'Взять в работу'}</button>` : ''}
    <button class="chat-extract-task-btn" data-task-open-chat="${task.id}" data-task-title="${esc(task.title)}" type="button" style="margin-top:0.5rem;">💬 Чат по потребности</button>
  </div>`;
}

async function loadTasks() {
  const list = document.getElementById('tasks-list');
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
          openObjectOrMangelChat(`task:${btn.dataset.taskOpenChat}`, `Потребность: ${btn.dataset.taskTitle}`, 'mangel');
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

function _closeTasksForm() {
  document.getElementById('tasks-form').style.display = 'none';
  document.getElementById('tasks-title-input').value = '';
  document.getElementById('tasks-object-select').value = '';
}

async function submitTask() {
  const title = document.getElementById('tasks-title-input').value.trim();
  if (!title) { showToast('Укажите, что нужно'); return; }
  const objectId = document.getElementById('tasks-object-select').value;
  try {
    await api('/api/tasks', { method: 'POST', body: JSON.stringify({ title, object_id: objectId }) });
    hapticImpact('light');
    _closeTasksForm();
    await loadTasks();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

function _selectMangelTab(tab) {
  _mangelActiveTab = tab;
  document.querySelectorAll('#view-mangel .doc-type-opt[data-mangel-tab]').forEach(o => o.classList.toggle('active', o.dataset.mangelTab === tab));
  document.getElementById('mangel-tab-content').style.display = tab === 'defects' ? 'block' : 'none';
  document.getElementById('tasks-tab-content').style.display = tab === 'tasks' ? 'block' : 'none';
  document.getElementById('mangel-new-btn').style.display = currentRole === 'owner' && tab === 'tasks' ? 'none' : 'flex';
  if (tab === 'tasks') loadTasks();
}

function initTasksView() {
  document.querySelectorAll('#view-mangel .doc-type-opt[data-mangel-tab]').forEach(tab => {
    tab.addEventListener('click', () => {
      _selectMangelTab(tab.dataset.mangelTab);
      hapticImpact('light');
    });
  });

  if (currentRole !== 'owner') {
    _populateTasksObjectSelect();
    document.getElementById('tasks-cancel-btn').addEventListener('click', _closeTasksForm);
    document.getElementById('tasks-submit-btn').addEventListener('click', submitTask);
    attachVoiceInputButton(document.getElementById('tasks-voice-btn'), transcript => {
      const input = document.getElementById('tasks-title-input');
      input.value = input.value ? `${input.value} ${transcript}` : transcript;
    });
  }

  _selectMangelTab(window._pendingMangelTab || 'tasks');
  window._pendingMangelTab = null;
}
