// Мои задачи (24.07) — назначения текущего воркера (объект/этап/период), отдельный
// экран от общего списка Объекты. Раньше dashboard-плитка "Задачи" ошибочно вела на
// switchView('objects') — юзер запросил отдельный экран именно для своих назначений.
// 24.07 (доп.): кнопка чата на карточке — открывает тред obj:{object_id}, тот же
// канал что и "Дефекты объекта"/чат объекта в целом, доступ уже проверен на backend
// (_check_thread_access — только участники объекта или owner).

const MY_TASK_CHAT_ICON = `<svg viewBox="0 0 24 24"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>`;

async function initMyTasksView() {
  const list = document.getElementById('my-tasks-list');
  list.innerHTML = '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Загрузка…</div>';
  try {
    const data = await api('/api/my-assignments');
    const items = data.assignments || [];
    if (!items.length) {
      list.innerHTML = '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Нет активных назначений</div>';
      return;
    }
    list.innerHTML = items.map(a => `
      <div class="my-task-card" style="margin-bottom:0.6rem;">
        <div class="my-task-card-body">
          <div class="my-task-card-title">${esc(a.object_name)}</div>
          ${a.stage_id ? `<div class="my-task-card-stage">${esc(a.stage_id)}</div>` : ''}
          ${(a.date_from || a.date_to) ? `<div class="my-task-card-dates">${esc(a.date_from)} — ${esc(a.date_to)}</div>` : ''}
        </div>
        <button type="button" class="my-task-chat-btn" data-my-task-chat="${esc(a.object_id)}" data-my-task-title="${esc(a.object_name)}" aria-label="Чат по объекту">
          ${MY_TASK_CHAT_ICON}
        </button>
      </div>
    `).join('');

    list.querySelectorAll('[data-my-task-chat]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (typeof openObjectOrMangelChat === 'function') {
          openObjectOrMangelChat(`obj:${btn.dataset.myTaskChat}`, `Чат: ${btn.dataset.myTaskTitle}`, 'my-tasks');
        }
        hapticImpact('light');
      });
    });
  } catch (e) {
    list.innerHTML = `<div style="padding:2rem 0;text-align:center;color:var(--red)">Ошибка: ${esc(e.message)}</div>`;
  }
}
