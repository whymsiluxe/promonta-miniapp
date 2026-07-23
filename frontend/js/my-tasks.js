// Мои задачи (24.07) — назначения текущего воркера (объект/этап/период), отдельный
// экран от общего списка Объекты. Раньше dashboard-плитка "Задачи" ошибочно вела на
// switchView('objects') — юзер запросил отдельный экран именно для своих назначений.

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
      <div class="mangel-card" style="margin-bottom:0.6rem;">
        <div class="mangel-card-desc"><b>${esc(a.object_name)}</b>${a.stage_id ? `<div style="margin-top:0.3rem;font-size:0.85rem;color:var(--text-light)">${esc(a.stage_id)}</div>` : ''}</div>
        ${(a.date_from || a.date_to) ? `<div style="margin-top:0.4rem;font-size:0.8rem;color:var(--text-light)">${esc(a.date_from)} — ${esc(a.date_to)}</div>` : ''}
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<div style="padding:2rem 0;text-align:center;color:var(--red)">Ошибка: ${esc(e.message)}</div>`;
  }
}
