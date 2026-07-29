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
    // 29.07 ТЗ п.9: назначение теперь требует подтверждения worker'а -- pending
    // показывает Принять/Не могу выйти вместо кнопки чата, declined -- причину отказа
    // как есть (owner уже видел её сам факт отказа, тут просто прозрачность для worker'а).
    // 29.07 (аудит): data-my-task-id -- assignment_id, устраняет неоднозначность "первый
    // pending" при нескольких назначениях одного worker'а на один объект.
    list.innerHTML = items.map(a => `
      <div class="my-task-card${a.status === 'pending' ? ' my-task-card-pending' : ''}" style="margin-bottom:0.6rem;">
        <div class="my-task-card-body">
          <div class="my-task-card-title">${esc(a.object_name)}</div>
          ${a.stage_id ? `<div class="my-task-card-stage">${esc(a.stage_id)}</div>` : ''}
          ${(a.date_from || a.date_to) ? `<div class="my-task-card-dates">${esc(a.date_from)} — ${esc(a.date_to)}</div>` : ''}
          ${a.task_note ? `<div class="my-task-card-note">${esc(a.task_note)}</div>` : ''}
          ${a.status === 'pending' ? `<div class="my-task-card-badge my-task-badge-pending">Ожидает подтверждения</div>` : ''}
          ${a.status === 'declined' ? `<div class="my-task-card-badge my-task-badge-declined">Отклонено${a.decline_reason ? `: ${esc(a.decline_reason)}` : ''}</div>` : ''}
        </div>
        ${a.status === 'pending' ? `
        <div class="my-task-card-actions">
          <button type="button" class="my-task-decline-btn" data-my-task-object="${esc(a.object_id)}" data-my-task-id="${esc(a.id)}" data-my-task-object-name="${esc(a.object_name)}" data-my-task-stage="${esc(a.stage_id || '')}" data-my-task-from="${esc(a.date_from || '')}" data-my-task-to="${esc(a.date_to || '')}" data-my-task-note="${esc(a.task_note || '')}">Не могу выйти</button>
          <button type="button" class="my-task-accept-btn" data-my-task-object="${esc(a.object_id)}" data-my-task-id="${esc(a.id)}">Принять</button>
        </div>` : `
        <button type="button" class="my-task-chat-btn" data-my-task-chat="${esc(a.object_id)}" data-my-task-title="${esc(a.object_name)}" aria-label="Чат по объекту">
          ${MY_TASK_CHAT_ICON}
        </button>`}
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

    list.querySelectorAll('.my-task-accept-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        btn.disabled = true;
        try {
          await api(`/api/objects/${btn.dataset.myTaskObject}/assign/${currentUserId}/respond`, {
            method: 'POST',
            body: JSON.stringify({ accept: true, assignment_id: btn.dataset.myTaskId || '' }),
          });
          hapticImpact('light');
          initMyTasksView();
        } catch (e) {
          showToast('Ошибка: ' + e.message, 'error');
          btn.disabled = false;
        }
      });
    });

    // 29.07 (аудит): заменили prompt() на keyboard-safe bottom sheet -- тот же
    // header/body/sticky-footer паттерн, что и Add Stage/Blocker sheets.
    list.querySelectorAll('.my-task-decline-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        _openDeclineAssignmentSheet(btn.dataset.myTaskObject, btn.dataset.myTaskId, btn, {
          objectName: btn.dataset.myTaskObjectName, stage: btn.dataset.myTaskStage,
          dateFrom: btn.dataset.myTaskFrom, dateTo: btn.dataset.myTaskTo, note: btn.dataset.myTaskNote,
        });
      });
    });
  } catch (e) {
    list.innerHTML = `<div style="padding:2rem 0;text-align:center;color:var(--red)">Ошибка: ${esc(e.message)}</div>`;
  }
}

// 29.07 (аудит) -- decline sheet: keyboard-safe замена prompt(), тот же паттерн
// header/body/sticky-footer + NavigationManager overlay + focus restore, что и
// Add Stage/Blocker sheets в object-info.js. Причина обязательна (тот же backend
// contract -- respond отклоняет пустой decline_reason).
let _declineSheetUnregisterOverlay = null;

function _openDeclineAssignmentSheet(objectId, assignmentId, triggerEl, ctx = {}) {
  document.getElementById('my-task-decline-sheet')?.remove();
  if (_declineSheetUnregisterOverlay) { _declineSheetUnregisterOverlay(); _declineSheetUnregisterOverlay = null; }

  const summaryLines = [];
  if (ctx.objectName) summaryLines.push(esc(ctx.objectName));
  if (ctx.stage) summaryLines.push(esc(ctx.stage));
  if (ctx.dateFrom || ctx.dateTo) summaryLines.push(`${esc(ctx.dateFrom || '')} — ${esc(ctx.dateTo || '')}`);
  if (ctx.note) summaryLines.push(esc(ctx.note));

  const sheet = document.createElement('div');
  sheet.id = 'my-task-decline-sheet';
  sheet.className = 'obj-stage-add-sheet';
  sheet.setAttribute('role', 'dialog');
  sheet.setAttribute('aria-modal', 'true');
  sheet.innerHTML = `
    <div class="obj-stage-add-sheet-backdrop"></div>
    <div class="obj-stage-add-sheet-inner">
      <div class="obj-stage-add-sheet-handle"></div>
      <div class="obj-stage-add-sheet-header">
        <div class="obj-stage-add-sheet-title">Не могу выйти</div>
        <div class="obj-stage-add-sheet-close" id="my-task-decline-close-btn" role="button" aria-label="Закрыть" tabindex="0">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M1 1L15 15M15 1L1 15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
        </div>
      </div>
      <div class="obj-stage-add-sheet-body">
        ${summaryLines.length ? `<div class="my-task-decline-summary">${summaryLines.join('<br>')}</div>` : ''}
        <div class="obj-stage-field">
          <label class="obj-stage-field-label" for="my-task-decline-reason">Причина</label>
          <textarea id="my-task-decline-reason" placeholder="Почему вы не можете выйти на этот объект" maxlength="500"></textarea>
          <div class="obj-stage-field-error" id="my-task-decline-error" style="display:none;">Укажите причину</div>
        </div>
        <div class="obj-stage-add-sheet-network-error" id="my-task-decline-network-error" style="display:none;">
          <strong>Не удалось отправить</strong>
          <span>Введённый текст сохранён</span>
          <button class="obj-stage-add-retry-btn" id="my-task-decline-retry-btn" type="button">Повторить</button>
        </div>
      </div>
      <div class="obj-stage-add-sheet-footer">
        <button class="obj-confirm-cancel" id="my-task-decline-cancel-btn" type="button">Отмена</button>
        <button class="obj-confirm-ok" id="my-task-decline-ok-btn" type="button">Отправить</button>
      </div>
    </div>`;
  document.body.appendChild(sheet);

  const textarea = document.getElementById('my-task-decline-reason');
  const errorEl = document.getElementById('my-task-decline-error');
  const networkErrorEl = document.getElementById('my-task-decline-network-error');
  const okBtn = document.getElementById('my-task-decline-ok-btn');

  textarea.addEventListener('input', () => {
    if (textarea.value.trim()) errorEl.style.display = 'none';
  });

  const prevBodyOverflow = document.body.style.overflow;
  document.body.style.overflow = 'hidden';

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    sheet.remove();
    document.body.style.overflow = prevBodyOverflow;
    document.removeEventListener('keydown', onKeydown);
    if (_declineSheetUnregisterOverlay) { _declineSheetUnregisterOverlay(); _declineSheetUnregisterOverlay = null; }
    if (triggerEl && typeof triggerEl.focus === 'function') triggerEl.focus();
  };
  const onKeydown = (e) => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', onKeydown);
  if (typeof NavigationManager !== 'undefined') {
    _declineSheetUnregisterOverlay = NavigationManager.registerOverlay(close);
  }

  sheet.querySelector('.obj-stage-add-sheet-backdrop').addEventListener('click', close);
  document.getElementById('my-task-decline-cancel-btn').addEventListener('click', close);
  document.getElementById('my-task-decline-close-btn').addEventListener('click', close);

  const submit = async () => {
    const reason = textarea.value.trim();
    if (!reason) {
      errorEl.style.display = 'block';
      return;
    }
    networkErrorEl.style.display = 'none';
    okBtn.disabled = true;
    okBtn.textContent = 'Отправляю…';
    try {
      await api(`/api/objects/${objectId}/assign/${currentUserId}/respond`, {
        method: 'POST',
        body: JSON.stringify({ accept: false, decline_reason: reason, assignment_id: assignmentId || '' }),
      });
      hapticImpact('light');
      close();
      initMyTasksView();
    } catch (e) {
      networkErrorEl.style.display = 'block';
      okBtn.disabled = false;
      okBtn.textContent = 'Отправить';
    }
  };
  okBtn.addEventListener('click', submit);
  document.getElementById('my-task-decline-retry-btn').addEventListener('click', submit);
}
