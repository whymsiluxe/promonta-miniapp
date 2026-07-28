// ═══════════ Инфо объекта — 6-таб экран, Step 3 (24.07) ═══════════
// Work-items (текст+кол-во) + документы (upload/просмотр). Данные per-object,
// backend: /api/objects/{id}/info-items, /api/objects/{id}/documents.

// 25.07 v3: полная реструктуризация Инфо-таба -- владелец явно попросил свести
// 6 плоских табов (Чат/Инфо/Задачи/Потребности/Дефекты/Этапы) до 2 (Чат/Инфо),
// а Инфо превратить в рабочую сводку объекта: статус -> описание -> работы
// (Объёмы|Задачи toggle) -> этапы -> дефекты (сводка) -> документы (сводка).
// Пустые состояния -- компактная строка с кнопкой действия, не большая надпись
// "пока нет данных" (owner explicitly called this out as looking unfinished).
async function renderObjectInfoTab(objectId) {
  const panel = document.getElementById('obj-detail-panel-info');
  // 28.07: owner request -- не было способа загрузить реальное фото объекта, карточка
  // всегда показывала stock-фото fallback. Owner-only, тот же upload-паттерн что уже
  // используется для документов/дефектов (sniff_image валидация на бэкенде).
  const photoUploadHtml = currentRole === 'owner' ? `
    <div class="obj-info-section">
      <div class="obj-info-section-title">Фото объекта</div>
      <input type="file" id="obj-info-photo-input" accept="image/*" style="display:none;">
      <button class="obj-info-empty-action" id="obj-info-photo-upload-btn" type="button">+ Загрузить фото</button>
    </div>` : '';
  const statusEditorHtml = currentRole === 'owner' ? `
    <div class="obj-info-section">
      <div class="obj-info-section-title">Статус объекта</div>
      <div class="status-switch" id="obj-detail-status-switch" data-current="${esc(_objDetailCurrentStatus)}">
        ${['В работе', 'Пауза', 'Завершён'].map(s =>
          `<div class="status-opt${s === _objDetailCurrentStatus ? ' active' : ''}" data-status="${s}">${s}</div>`
        ).join('')}
      </div>
    </div>` : '';

  const teamShiftsHtml = currentRole === 'owner' ? `
    <div class="obj-info-section">
      <div class="obj-info-section-title">Команда и смены</div>
      <div id="obj-info-team"></div>
      <div id="obj-info-shifts-today"></div>
    </div>` : '';

  panel.innerHTML = `
    ${photoUploadHtml}
    ${statusEditorHtml}
    ${teamShiftsHtml}
    <div class="obj-info-section">
      <div class="obj-info-section-title">Описание</div>
      <div id="obj-info-description-view"></div>
    </div>
    <div class="obj-info-section">
      <div class="obj-info-section-title-row">
        <span class="obj-info-section-title" style="margin-bottom:0;">Работы</span>
        <div class="doc-type-switch obj-info-subtabs" id="obj-works-subtabs">
          <div class="doc-type-opt active" data-works-tab="volumes">Объёмы</div>
          <div class="doc-type-opt" data-works-tab="tasks">Задачи</div>
        </div>
      </div>
      <div id="obj-works-panel-volumes"></div>
      <div id="obj-works-panel-tasks" style="display:none;"></div>
    </div>
    <div class="obj-info-section">
      <div class="obj-info-section-title-row">
        <span class="obj-info-section-title" style="margin-bottom:0;">Дефекты</span>
        <span id="obj-info-defects-count" class="obj-info-count-badge"></span>
      </div>
      <div id="obj-info-defects-summary"></div>
    </div>
    <div class="obj-info-section">
      <div class="obj-info-section-title-row">
        <span class="obj-info-section-title" style="margin-bottom:0;">Документы</span>
        <span id="obj-info-docs-count" class="obj-info-count-badge"></span>
      </div>
      <div id="obj-info-docs-summary"></div>
    </div>
    <!-- 29.07 v2: Потребности перенесены сюда из отдельной 4-й вкладки (owner ТЗ: финальная
         структура Object Detail -- ровно 3 таба Чат/Инфо/План работ, без отдельной вкладки
         Потребности). Разметка и вся логика ниже (_loadObjNeeds/_renderNeedRow) перенесены
         без изменений из бывшего renderObjectNeedsTab, только id панели/списка сменился. -->
    <div class="obj-info-section">
      <div class="obj-info-section-title">Потребности</div>
      <div id="obj-needs-list" class="obj-info-items-list"></div>
      ${currentRole !== 'owner' ? `
      <div class="obj-info-add-row">
        <input type="text" id="obj-needs-new-text" class="obj-info-input" placeholder="Например: нужен перфоратор">
        <button id="obj-needs-add-btn" class="obj-info-add-btn" type="button">+</button>
      </div>` : ''}
    </div>
  `;

  const photoUploadBtn = document.getElementById('obj-info-photo-upload-btn');
  const photoInput = document.getElementById('obj-info-photo-input');
  if (photoUploadBtn && photoInput) {
    photoUploadBtn.addEventListener('click', () => photoInput.click());
    photoInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      e.target.value = '';
      if (!file) return;
      photoUploadBtn.disabled = true;
      photoUploadBtn.textContent = 'Загрузка…';
      try {
        const fd = new FormData();
        fd.append('file', file);
        await fetch(`${API_BASE}/api/objects/${encodeURIComponent(objectId)}/image`, {
          method: 'POST',
          headers: { 'X-Telegram-Init-Data': initData },
          body: fd,
        }).then(async r => {
          if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
        });
        hapticImpact('medium');
        showToast('Фото обновлено', 'success');
        if (typeof loadObjects === 'function') loadObjects();
      } catch (err) {
        showToast('Ошибка: ' + err.message, 'error');
      } finally {
        photoUploadBtn.disabled = false;
        photoUploadBtn.textContent = '+ Загрузить фото';
      }
    });
  }

  const statusSwitch = document.getElementById('obj-detail-status-switch');
  if (statusSwitch) {
    statusSwitch.querySelectorAll('.status-opt').forEach(opt => {
      opt.addEventListener('click', async () => {
        const next = opt.dataset.status;
        const prev = statusSwitch.dataset.current;
        if (next === prev) return;
        statusSwitch.dataset.current = next;
        statusSwitch.querySelectorAll('.status-opt').forEach(o => o.classList.toggle('active', o.dataset.status === next));
        hapticImpact('light');
        try {
          await api(`/api/objects/${objectId}/status`, { method: 'PATCH', body: JSON.stringify({ status: next }) });
          _objDetailCurrentStatus = next;
        } catch (e) {
          statusSwitch.dataset.current = prev;
          statusSwitch.querySelectorAll('.status-opt').forEach(o => o.classList.toggle('active', o.dataset.status === prev));
          showToast('Ошибка: ' + e.message, 'error');
        }
      });
    });
  }

  document.getElementById('obj-works-subtabs').querySelectorAll('.doc-type-opt').forEach(opt => {
    opt.addEventListener('click', () => {
      const tab = opt.dataset.worksTab;
      document.getElementById('obj-works-subtabs').querySelectorAll('.doc-type-opt').forEach(o => o.classList.toggle('active', o === opt));
      document.getElementById('obj-works-panel-volumes').style.display = tab === 'volumes' ? 'block' : 'none';
      document.getElementById('obj-works-panel-tasks').style.display = tab === 'tasks' ? 'block' : 'none';
    });
  });

  const needsAddBtn = document.getElementById('obj-needs-add-btn');
  if (needsAddBtn) {
    needsAddBtn.addEventListener('click', async () => {
      const textEl = document.getElementById('obj-needs-new-text');
      const text = textEl.value.trim();
      if (!text) return;
      try {
        await api('/api/tasks', { method: 'POST', body: JSON.stringify({ title: text, object_id: objectId }) });
        textEl.value = '';
        hapticImpact('light');
        await _loadObjNeeds(objectId);
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
      }
    });
  }

  const promises = [
    _renderObjDescriptionSection(objectId),
    _renderObjWorksVolumesSection(objectId),
    _renderObjWorksTasksSection(objectId),
    _renderObjDefectsSummary(objectId),
    _renderObjDocsSummary(objectId),
    _loadObjNeeds(objectId),
  ];
  if (currentRole === 'owner') promises.push(_renderObjTeamAndShifts(objectId));
  await Promise.all(promises);
}

// ── Команда и смены (owner-only, B6, 27.07) ──
// Собирает назначенных workers + сегодняшние смены прямо в детальной карточке
// объекта -- владелец не должен искать эту информацию отдельно на Home/Objects.
async function _renderObjTeamAndShifts(objectId) {
  const teamEl = document.getElementById('obj-info-team');
  const shiftsEl = document.getElementById('obj-info-shifts-today');
  if (!teamEl || !shiftsEl) return;
  try {
    const [objData, checkinData] = await Promise.all([
      api('/api/objects'),
      api(`/api/checkin?object_id=${encodeURIComponent(objectId)}`),
    ]);
    const obj = (objData.objects || []).find(o => String(o['ID объекта']) === String(objectId));
    const team = obj?.assigned_users || [];
    teamEl.innerHTML = team.length
      ? `<div class="obj-info-team-row">${team.map(u => `
          <div class="obj-info-team-chip" data-uid="${esc(u.user_id)}" title="${esc(u.name)}">
            ${esc((u.name || '?').split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase())}
          </div>`).join('')}</div>`
      : '<div class="obj-info-empty-row"><span>Никто не назначен</span></div>';
    teamEl.querySelectorAll('.obj-info-team-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        if (typeof openUserCard === 'function') openUserCard(chip.dataset.uid);
      });
    });

    const today = new Date().toISOString().slice(0, 10);
    const todaySessions = (checkinData.sessions || []).filter(s => s.date === today);
    if (!todaySessions.length) {
      shiftsEl.innerHTML = '<div class="obj-info-empty-row"><span>Сегодня смен не было</span></div>';
    } else {
      shiftsEl.innerHTML = todaySessions.map(s => {
        const worker = team.find(u => String(u.user_id) === String(s.user_id));
        const name = worker ? worker.name : s.user_id;
        const status = s.finish_at ? 'завершена' : 'идёт';
        // 28.07: owner report -- сводка смены была почти пустой (только имя+статус),
        // хотя worker заполняет "что сделано" (текст) и опционально голосовое через
        // finish-wizard. Оба теперь видны прямо тут, без отдельного клика/экрана.
        const summaryHtml = s.done_summary
          ? `<div class="obj-info-shift-summary">${esc(s.done_summary)}</div>` : '';
        const audioHtml = s.voice_note_audio_url
          ? `<audio class="obj-info-shift-audio" controls preload="none" src="${esc(API_BASE + s.voice_note_audio_url)}"></audio>` : '';
        return `<div class="obj-info-item-row obj-info-shift-row">
          <div class="obj-info-shift-row-top">
            <span class="obj-info-item-text">${esc(name)}</span>
            <span class="obj-info-item-qty">${esc(status)}</span>
          </div>
          ${summaryHtml}
          ${audioHtml}
        </div>`;
      }).join('');
    }
  } catch (e) {
    teamEl.innerHTML = `<div class="obj-info-empty-row"><span>Ошибка: ${esc(e.message)}</span></div>`;
  }
}

// ── Описание объекта ──
async function _renderObjDescriptionSection(objectId) {
  const wrap = document.getElementById('obj-info-description-view');
  if (!wrap) return;
  let description = '';
  try {
    const res = await api(`/api/objects/${objectId}/description`);
    description = res.description || '';
  } catch (e) { /* тихо -- секция просто покажет пустое состояние */ }

  if (!description && currentRole !== 'owner') {
    wrap.innerHTML = '';
    return;
  }
  if (!description) {
    wrap.innerHTML = `<div class="obj-info-empty-row"><span>Описание не добавлено</span><button class="obj-info-empty-action" id="obj-desc-add-btn" type="button">+ Добавить описание</button></div>`;
    document.getElementById('obj-desc-add-btn').addEventListener('click', () => _openObjDescriptionEditor(objectId, ''));
    return;
  }
  wrap.innerHTML = `<div class="obj-info-description-text" id="obj-desc-text">${esc(description).replace(/\n/g, '<br>')}</div>`;
  if (currentRole === 'owner') {
    wrap.innerHTML += `<button class="obj-info-empty-action" id="obj-desc-edit-btn" type="button" style="margin-top:0.5rem;">Изменить</button>`;
    document.getElementById('obj-desc-edit-btn').addEventListener('click', () => _openObjDescriptionEditor(objectId, description));
  }
}

function _openObjDescriptionEditor(objectId, current) {
  const text = prompt('Описание объекта:', current);
  if (text === null) return;
  api(`/api/objects/${objectId}/description`, { method: 'PATCH', body: JSON.stringify({ description: text }) })
    .then(() => { hapticImpact('light'); _renderObjDescriptionSection(objectId); })
    .catch(e => showToast('Ошибка: ' + e.message, 'error'));
}

// ── Работы -> Объёмы ── (переиспользует существующий /api/objects/{id}/info-items store)
async function _renderObjWorksVolumesSection(objectId) {
  const wrap = document.getElementById('obj-works-panel-volumes');
  if (!wrap) return;
  wrap.innerHTML = `
    <div id="obj-info-items-list" class="obj-info-items-list"></div>
    ${currentRole === 'owner' ? `
    <div class="obj-info-add-row">
      <input type="text" id="obj-info-item-text" class="obj-info-input" placeholder="Например: Штукатурка">
      <input type="text" id="obj-info-item-qty" class="obj-info-input obj-info-input-qty" placeholder="100м²">
      <button id="obj-info-item-add" class="obj-info-add-btn" type="button">+</button>
    </div>` : ''}
  `;
  document.getElementById('obj-info-item-add')?.addEventListener('click', () => _addObjInfoItem(objectId));
  await _loadObjInfoItems(objectId);
}

// ── Работы -> Задачи ── (переиспользует существующий рендер задач)
async function _renderObjWorksTasksSection(objectId) {
  const wrap = document.getElementById('obj-works-panel-tasks');
  if (!wrap) return;
  wrap.innerHTML = `
    <div id="obj-tasks-list" class="obj-info-items-list"></div>
    ${currentRole === 'owner' ? `
    <div class="obj-info-add-row">
      <input type="text" id="obj-tasks-new-text" class="obj-info-input" placeholder="Новая задача">
      <button id="obj-tasks-add-btn" class="obj-info-add-btn" type="button">+</button>
    </div>` : ''}
  `;
  const listEl = document.getElementById('obj-tasks-list');
  await loadObjectWorkTasks(objectId, listEl, null);
  const addBtn = document.getElementById('obj-tasks-add-btn');
  if (addBtn) {
    addBtn.addEventListener('click', async () => {
      const textEl = document.getElementById('obj-tasks-new-text');
      const text = textEl.value.trim();
      if (!text) return;
      try {
        await api(`/api/objects/${objectId}/tasks`, { method: 'POST', body: JSON.stringify({ text }) });
        textEl.value = '';
        hapticImpact('light');
        await loadObjectWorkTasks(objectId, listEl, null);
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
      }
    });
  }
}

// ── Этапы (компактная сводка, полный roadmap живёт по клику -- переиспользует
// renderObjectStagesTab-логику, просто рендерит в новый контейнер) ──
// 28.07: owner request -- Этапы был "кнопкой в никуда" (stage-strip на карточке
// объекта уже открывал Object Detail с initialTab='stages', но такого таба физически
// не существовало -- только секция внутри Инфо). Теперь полноценный отдельный таб,
// секция из Инфо убрана (не дублируем), переиспользует тот же _loadObjStages/roadmap
// рендер, что раньше жил внутри Инфо.
// 29.07 v2: "Добавить этап" больше не постоянно открытый input+большая кнопка (owner
// screenshot report: "Этапов пока нет" в чёрной карточке + вечно видимая форма добавления
// доминировали над экраном). Компактная кнопка-триггер открывает bottom sheet с полем ввода --
// тот же паттерн, что уже использует остальное приложение (Stage Editor, Add Defect и т.п.).
async function renderObjectStagesTab(objectId) {
  const panel = document.getElementById('obj-detail-panel-stages');
  if (!panel) return;
  panel.innerHTML = `
    <div id="obj-stages-roadmap" class="obj-stages-roadmap"></div>
    <button class="obj-stage-add-trigger" id="obj-stages-tab-add-trigger" type="button">+ Добавить этап</button>
  `;
  await _loadObjStages(objectId);
  if (currentRole !== 'owner' && typeof _openCheckinStatusScreen === 'function') {
    _appendCheckinShortcut(panel, objectId);
  }
  document.getElementById('obj-stages-tab-add-trigger')?.addEventListener('click', () => _openAddStageSheet(objectId));
}

function _openAddStageSheet(objectId) {
  const existing = document.getElementById('obj-stage-add-sheet');
  if (existing) existing.remove();
  const sheet = document.createElement('div');
  sheet.id = 'obj-stage-add-sheet';
  sheet.className = 'obj-stage-add-sheet';
  sheet.innerHTML = `
    <div class="obj-stage-add-sheet-backdrop"></div>
    <div class="obj-stage-add-sheet-inner">
      <div class="obj-stage-add-sheet-title">Добавить этап</div>
      <input type="text" id="obj-stages-tab-new-name" class="obj-info-input" placeholder="напр. Фасад, Стяжка пола" autofocus>
      <div class="obj-stage-add-sheet-actions">
        <button class="obj-confirm-cancel" id="obj-stage-add-cancel-btn" type="button">Отмена</button>
        <button class="obj-confirm-ok" id="obj-stage-add-ok-btn" type="button">Добавить</button>
      </div>
    </div>`;
  document.body.appendChild(sheet);
  const close = () => sheet.remove();
  sheet.querySelector('.obj-stage-add-sheet-backdrop').addEventListener('click', close);
  document.getElementById('obj-stage-add-cancel-btn').addEventListener('click', close);
  document.getElementById('obj-stages-tab-new-name').focus();
  document.getElementById('obj-stage-add-ok-btn').addEventListener('click', async () => {
    const input = document.getElementById('obj-stages-tab-new-name');
    const name = input.value.trim();
    if (!name) return;
    const okBtn = document.getElementById('obj-stage-add-ok-btn');
    okBtn.disabled = true;
    try {
      await api(`/api/objects/${objectId}/stages`, { method: 'POST', body: JSON.stringify({ name }) });
      hapticImpact('light');
      close();
      await _loadObjStages(objectId);
    } catch (e) {
      showToast('Ошибка: ' + e.message, 'error');
      okBtn.disabled = false;
    }
  });
}

// ── Дефекты (компактная сводка) ──
async function _renderObjDefectsSummary(objectId) {
  const wrap = document.getElementById('obj-info-defects-summary');
  const countEl = document.getElementById('obj-info-defects-count');
  if (!wrap) return;
  try {
    const { tickets } = await api(`/api/mangel?object_id=${encodeURIComponent(objectId)}`);
    const open = tickets.filter(t => t.status !== 'закрыт');
    if (countEl) countEl.textContent = open.length ? `${open.length} открытых` : '';
    if (!tickets.length) {
      wrap.innerHTML = `<div class="obj-info-empty-row"><span>Дефектов нет</span><button class="obj-info-empty-action" id="obj-defect-add-btn" type="button">+ Создать</button></div>`;
    } else {
      const preview = open.slice(0, 3);
      wrap.innerHTML = preview.map(t => `
        <div class="obj-info-item-row" data-ticket-id="${t.id}" style="cursor:pointer;">
          <span class="obj-info-item-text">${esc(t.title || t.description || '')}</span>
          <span class="obj-info-item-qty">${esc(t.status || '')}</span>
        </div>`).join('')
        + `<div class="obj-info-actions-row">
             <button class="obj-info-empty-action" id="obj-defects-all-btn" type="button">Все дефекты</button>
             <button class="obj-info-empty-action" id="obj-defect-add-btn" type="button">+ Добавить дефект</button>
           </div>`;
      wrap.querySelectorAll('[data-ticket-id]').forEach(row => {
        row.addEventListener('click', () => openMangelTicketModal(row.dataset.ticketId));
      });
    }
    document.getElementById('obj-defects-all-btn')?.addEventListener('click', () => {
      window._pendingMangelObjectFilter = objectId;
      switchView('mangel');
    });
    document.getElementById('obj-defect-add-btn')?.addEventListener('click', () => {
      // Переиспользуем существующую кнопку создания дефекта на экране Дефекты --
      // programmatic click вместо дублирования её open-form логики здесь.
      window._pendingMangelObjectFilter = objectId;
      switchView('mangel');
      setTimeout(() => document.getElementById('mangel-new-btn')?.click(), 150);
    });
  } catch (e) {
    wrap.innerHTML = `<div class="obj-info-empty-row"><span>Ошибка: ${esc(e.message)}</span></div>`;
  }
}

// ── Документы (компактная сводка) ──
async function _renderObjDocsSummary(objectId) {
  const wrap = document.getElementById('obj-info-docs-summary');
  const countEl = document.getElementById('obj-info-docs-count');
  if (!wrap) return;
  wrap.innerHTML = `<div id="obj-info-docs-list" class="obj-info-docs-list"></div>
    <input type="file" id="obj-info-doc-file" accept="image/*,.pdf" style="display:none;">`;
  document.getElementById('obj-info-doc-file').addEventListener('change', (e) => {
    if (e.target.files[0]) _uploadObjInfoDoc(objectId, e.target.files[0]);
  });
  await _loadObjInfoDocs(objectId, countEl);
}

async function _loadObjInfoItems(objectId) {
  const list = document.getElementById('obj-info-items-list');
  if (!list) return;
  try {
    const { items } = await api(`/api/objects/${objectId}/info-items`);
    if (!items.length) {
      list.innerHTML = `<div class="obj-info-empty-row"><span>Работы 0</span></div>`;
      return;
    }
    list.innerHTML = items.map(i => `
      <div class="obj-info-item-row" data-item-id="${i.id}">
        <span class="obj-info-item-text">${esc(i.text)}</span>
        ${i.qty ? `<span class="obj-info-item-qty">${esc(i.qty)}</span>` : ''}
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<div class="obj-info-empty">Ошибка: ${esc(e.message)}</div>`;
  }
}

async function _addObjInfoItem(objectId) {
  const textEl = document.getElementById('obj-info-item-text');
  const qtyEl = document.getElementById('obj-info-item-qty');
  const text = textEl.value.trim();
  if (!text) return;
  try {
    await api(`/api/objects/${objectId}/info-items`, {
      method: 'POST',
      body: JSON.stringify({ text, qty: qtyEl.value.trim() }),
    });
    textEl.value = '';
    qtyEl.value = '';
    hapticImpact('light');
    await _loadObjInfoItems(objectId);
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

function _objInfoDocIcon(contentType) {
  if ((contentType || '').startsWith('image/')) {
    return `<svg viewBox="0 0 24 24" width="20" height="20"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5z"/><circle cx="8.5" cy="8.5" r="1.5"/><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M21 15l-5-5L5 21"/></svg>`;
  }
  return `<svg viewBox="0 0 24 24" width="20" height="20"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M14 2v6h6"/></svg>`;
}

async function _loadObjInfoDocs(objectId, countEl) {
  const list = document.getElementById('obj-info-docs-list');
  if (!list) return;
  try {
    const { documents } = await api(`/api/objects/${objectId}/documents`);
    if (countEl) countEl.textContent = documents.length || '';
    if (!documents.length) {
      list.innerHTML = `<div class="obj-info-empty-row"><span>Документы 0</span><button class="obj-info-empty-action" id="obj-doc-add-empty-btn" type="button">+ Прикрепить</button></div>`;
      document.getElementById('obj-doc-add-empty-btn')?.addEventListener('click', () => document.getElementById('obj-info-doc-file').click());
      return;
    }
    list.innerHTML = documents.map(d => `
      <div class="obj-info-doc-row" data-doc-id="${d.id}" data-doc-file="${esc(d.file)}" data-doc-type="${esc(d.content_type)}" data-doc-name="${esc(d.name)}">
        <span class="obj-info-doc-icon">${_objInfoDocIcon(d.content_type)}</span>
        <span class="obj-info-doc-name">${esc(d.name)}</span>
      </div>
    `).join('') + `<button class="obj-info-empty-action" id="obj-doc-add-more-btn" type="button" style="margin-top:0.4rem;">+ Прикрепить</button>`;
    list.querySelectorAll('.obj-info-doc-row').forEach(row => {
      row.addEventListener('click', () => _openObjInfoDocViewer(objectId, row.dataset.docFile, row.dataset.docType, row.dataset.docName));
    });
    document.getElementById('obj-doc-add-more-btn')?.addEventListener('click', () => document.getElementById('obj-info-doc-file').click());
  } catch (e) {
    list.innerHTML = `<div class="obj-info-empty-row"><span>Ошибка: ${esc(e.message)}</span></div>`;
  }
}

async function _uploadObjInfoDoc(objectId, file) {
  const btn = document.getElementById('obj-info-doc-add');
  if (btn) { btn.disabled = true; btn.textContent = 'Загрузка…'; }
  try {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/objects/${objectId}/documents`, {
      method: 'POST',
      headers: { 'X-Telegram-Init-Data': initData },
      body: formData,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    hapticImpact('light');
    await _loadObjInfoDocs(objectId);
  } catch (e) {
    showToast('Ошибка загрузки: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '+ Прикрепить файл'; }
    document.getElementById('obj-info-doc-file').value = '';
  }
}

// Viewer -- полноэкранный, back возвращает ровно на Инфо-таб этого объекта (не reload, не
// switchView -- та же логика что чат-таб в object-detail: не .view-элемент, отдельный overlay).
function _openObjInfoDocViewer(objectId, fname, contentType, name) {
  let viewer = document.getElementById('obj-info-doc-viewer');
  if (!viewer) {
    viewer = document.createElement('div');
    viewer.id = 'obj-info-doc-viewer';
    document.body.appendChild(viewer);
  }
  const src = `${API_BASE}/api/objects/${objectId}/documents/${fname}/file`;
  const isImage = (contentType || '').startsWith('image/');
  viewer.innerHTML = `
    <div class="obj-doc-viewer-header">
      <button id="obj-doc-viewer-back" class="chat-back-btn" type="button" aria-label="Назад">←</button>
      <h1>${esc(name)}</h1>
    </div>
    <div class="obj-doc-viewer-body">
      ${isImage
        ? `<img src="${src}" alt="${esc(name)}">`
        : `<iframe src="${src}" title="${esc(name)}"></iframe>`}
    </div>
  `;
  viewer.style.display = 'flex';
  document.getElementById('obj-doc-viewer-back').addEventListener('click', _closeObjInfoDocViewer);
}

function _closeObjInfoDocViewer() {
  const viewer = document.getElementById('obj-info-doc-viewer');
  if (viewer) viewer.style.display = 'none';
}

// 25.07 v3: Задачи объекта и Дефекты (список) теперь рендерятся внутри Инфо
// (см. _renderObjWorksTasksSection/_renderObjDefectsSummary выше). Потребности
// остаются отдельным object-scoped табом (owner передумал после первого прохода --
// хотел сначала убрать в Инфо, затем явно попросил вернуть как полноценный
// top-level таб наравне с Чат/Инфо, доступный и owner и worker).
function _renderNeedRow(n) {
  // 28.07: owner request -- вкладка Потребности была read-only списком (текст+статус,
  // без действий). Owner теперь может продвигать статус (тот же open->в работе->закрыто
  // паттерн, что уже есть в tasks.js), и обе роли могут открыть чат с другой стороной
  // заявки прямо отсюда, не переходя в общий Чат вручную.
  const status = n.status || 'открыто';
  const nextStatus = status === 'открыто' ? 'в работе' : status === 'в работе' ? 'закрыто' : null;
  const advanceBtn = (currentRole === 'owner' && nextStatus)
    ? `<button class="obj-info-empty-action" data-need-advance="${n.id}" data-next-status="${nextStatus}" type="button">${nextStatus === 'закрыто' ? 'Закрыть' : 'Взять в работу'}</button>`
    : '';
  // Owner видит кнопку "Чат" к заявителю (from_user_id), worker -- к owner (from_user_id
  // это сам worker, ему нужен чат с to_user_id = owner).
  const chatTargetId = currentRole === 'owner' ? n.from_user_id : n.to_user_id;
  const chatTargetName = currentRole === 'owner' ? (n.from_name || n.from_user_id) : 'Владелец';
  const chatBtn = chatTargetId
    ? `<button class="obj-info-empty-action" data-need-chat="${esc(chatTargetId)}" data-chat-name="${esc(chatTargetName)}" type="button">💬 Чат</button>`
    : '';
  return `
  <div class="obj-info-item-row" style="flex-direction:column;align-items:stretch;gap:0.4rem;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <span class="obj-info-item-text">${esc(n.title || '')}</span>
      <span class="obj-info-item-qty">${esc(status)}</span>
    </div>
    ${(advanceBtn || chatBtn) ? `<div class="obj-info-actions-row">${advanceBtn}${chatBtn}</div>` : ''}
  </div>`;
}

// 29.07 v2: renderObjectNeedsTab() удалена -- Потребности больше не отдельная вкладка,
// разметка+обработчики теперь инлайн внутри renderObjectInfoTab() выше. _loadObjNeeds()
// остаётся отдельной функцией (переиспользуется add-handler'ом для перерисовки после add).
async function _loadObjNeeds(objectId) {
  const list = document.getElementById('obj-needs-list');
  if (!list) return;
  try {
    const { tasks } = await api(`/api/tasks?object_id=${encodeURIComponent(objectId)}`);
    if (!tasks.length) {
      list.innerHTML = `<div class="obj-info-empty-row"><span>Потребностей нет</span></div>`;
      return;
    }
    list.innerHTML = tasks.map(_renderNeedRow).join('');
    list.querySelectorAll('[data-need-advance]').forEach(btn => {
      btn.addEventListener('click', async () => {
        try {
          await api(`/api/tasks/${btn.dataset.needAdvance}`, { method: 'PATCH', body: JSON.stringify({ status: btn.dataset.nextStatus }) });
          hapticImpact('light');
          await _loadObjNeeds(objectId);
        } catch (e) {
          showToast('Ошибка: ' + e.message, 'error');
        }
      });
    });
    list.querySelectorAll('[data-need-chat]').forEach(btn => {
      btn.addEventListener('click', () => {
        // switchView первым -- openChatThread сам не переключает таб, юзер остался бы
        // на экране Объекта с чат-view открытым позади него, невидимо.
        switchView('chat');
        if (typeof openChatThread === 'function') openChatThread(btn.dataset.needChat, btn.dataset.chatName);
      });
    });
  } catch (e) {
    list.innerHTML = `<div class="obj-info-empty-row"><span>Ошибка: ${esc(e.message)}</span></div>`;
  }
}

// ═══════════ Этапы объекта — Step 6 (roadmap) ═══════════
// Reorder = up/down-кнопки, не drag -- порядок хранится как число '№ этапа' в Google
// Sheets, нет физической перестановки строк, только swap двух значений (backend
// swap_stage_order). Полноценный touch drag на этом сторе рискованнее, чем стоит
// (per plan: "decide after a quick spike" -- спайк показал, что Sheets-swap безопаснее
// как two-button move, не drag). Worker видит кнопку "Готово" только на своём текущем
// этапе (backend worker_complete_stage сам это перепроверяет, фронт не единственная защита).
const OBJ_STAGE_STATUS_LABEL = { 'предстоит': 'Предстоит', 'в процессе': 'В процессе', 'готово': 'Готово' };


async function _appendCheckinShortcut(panel, objectId) {
  const wrap = document.createElement('div');
  wrap.style.cssText = 'padding:1rem 0 0.5rem;border-top:1px solid var(--border-color);margin-top:1.25rem;';
  wrap.innerHTML = `<div style="font-size:0.82rem;color:var(--text-light);text-align:center;margin-bottom:0.6rem;">Учёт рабочего времени</div>
    <button id="obj-stages-checkin-btn" class="submit-btn" style="width:100%">…</button>`;
  panel.appendChild(wrap);

  let activeObjectId = null;
  try { activeObjectId = await _findActiveWorkerCheckinObjectId(); } catch (e) {}

  const btn = document.getElementById('obj-stages-checkin-btn');
  if (!btn) return;
  if (activeObjectId) {
    btn.textContent = '■ Завершить смену';
    btn.style.background = 'var(--red)';
  } else {
    btn.textContent = '▶ Начать смену';
  }
  btn.addEventListener('click', () => {
    // 25.07: БАГ был тут -- всегда брали objectId текущего ЭКРАНА, а не объект, на
    // котором смена реально открыта (activeObjectId, уже вычислен выше через
    // _findActiveWorkerCheckinObjectId, который читает /api/checkin и знает правду).
    // Если юзер начал смену на объекте А (например через FAB), а зашёл завершать
    // с экрана объекта Б -- _getActiveCheckinSession(Б) не находил сессию, finish
    // уходил с неверным/пустым session.id, смена оставалась "идёт" на бэкенде,
    // хотя фото уже успевали куда-то загрузиться отдельным запросом.
    _stagesCurrentObjectId = activeObjectId || objectId;
    _openCheckinStatusScreen();
  });
}

async function _loadObjStages(objectId) {
  const wrap = document.getElementById('obj-stages-roadmap');
  if (!wrap) return;
  try {
    const { stages } = await api(`/api/objects/${objectId}/stages`);
    if (!stages.length) {
      wrap.innerHTML = `<div class="obj-stages-empty">План работ ещё не создан</div>`;
      return;
    }
    const currentIdx = stages.findIndex(s => s['Статус'] === 'в процессе');
    wrap.innerHTML = stages.map((s, i) => _renderStageRoadmapNode(s, i, stages.length, i === currentIdx)).join('');
    _attachObjStagesHandlers(objectId, stages);
    // 28.07: лёгкий stagger fade-in на первую отрисовку списка -- та же "красивая
    // анимация" просьба, что уже применена в других местах приложения (bubble float,
    // radio carousel dots), не тяжёлый JS-animation-engine.
    wrap.querySelectorAll('.obj-stage-node').forEach((node, i) => {
      node.style.animationDelay = `${i * 60}ms`;
      node.classList.add('obj-stage-node-enter');
    });
  } catch (e) {
    wrap.innerHTML = `<div class="obj-info-empty">Ошибка: ${esc(e.message)}</div>`;
  }
}

// 28.07: owner request -- roadmap, каждый этап раскрывается (аккордеон), внутри --
// текстовое описание того что делать ("заклеить опасные места, подготовить под
// демонтаж, взять инструмент, обрезать металл" и т.п.), можно отметить выполненным.
function _renderStageRoadmapNode(s, idx, total, isCurrent) {
  const status = s['Статус'] || 'предстоит';
  const dotClass = status === 'готово' ? 'done' : status === 'в процессе' ? 'active' : '';
  // CSS class -- whitelist, не просто esc(): статус из Sheets, произвольный текст
  // не должен становиться частью class list (та же логика что renderStageRow в objects.js).
  const statusSlug = /^[a-zA-Zа-яА-Я0-9\-]+$/.test(status.replace(/\s/g, '-'))
    ? status.replace(/\s/g, '-') : 'unknown';
  const canWorkerComplete = currentRole !== 'owner' && isCurrent;
  const description = s['Описание'] || '';
  const canEditDescription = currentRole === 'owner';
  // 29.07 v2: owner screenshot report -- textarea была ПОСТОЯННО видна в режиме просмотра
  // (canEditDescription всегда true для owner), placeholder-текст выглядел как реальные
  // данные этапа. Read/edit теперь явно разделены: по умолчанию всегда read-mode текст
  // (или "Описание пока не добавлено"), owner получает кнопку "Редактировать" -- editor
  // (textarea+Сохранить) появляется только после явного тапа, не по умолчанию.
  return `
  <div class="obj-stage-node" data-row="${s['_row']}" data-num="${s['№ этапа']}" draggable="false">
    <div class="obj-stage-drag-handle" title="Перетащить для смены порядка">⠿</div>
    <div class="obj-stage-line">
      <div class="obj-stage-dot ${dotClass}"></div>
      ${idx < total - 1 ? '<div class="obj-stage-connector"></div>' : ''}
    </div>
    <div class="obj-stage-body">
      <div class="obj-stage-header" data-toggle-row="${s['_row']}">
        <div class="obj-stage-name">${esc(s['Название этапа'] || '')}</div>
        <div class="obj-stage-status-label obj-stage-status-${statusSlug}">${esc(OBJ_STAGE_STATUS_LABEL[status] || status)}</div>
        <span class="obj-stage-chevron">▾</span>
      </div>
      <div class="obj-stage-description-wrap" id="obj-stage-desc-${s['_row']}">
        <div class="obj-stage-description-read" data-row="${s['_row']}">
          <div class="obj-stage-description-text${description ? '' : ' obj-stage-description-empty'}">${description ? esc(description) : 'Описание пока не добавлено'}</div>
          ${canEditDescription ? `<button class="obj-stage-description-edit-btn" data-row="${s['_row']}" type="button">Редактировать</button>` : ''}
        </div>
        ${canEditDescription ? `
        <div class="obj-stage-description-editor" data-row="${s['_row']}" style="display:none;">
          <textarea class="obj-stage-description-input" data-row="${s['_row']}" placeholder="Что нужно сделать на этом этапе: например, заклеить опасные места, подготовить под демонтаж, взять нужный инструмент…">${esc(description)}</textarea>
          <div class="obj-stage-description-editor-actions">
            <button class="obj-stage-description-cancel" data-row="${s['_row']}" type="button">Отмена</button>
            <button class="obj-stage-description-save" data-row="${s['_row']}" type="button">Сохранить</button>
          </div>
        </div>` : ''}
        ${canWorkerComplete ? `<button class="obj-stage-complete-btn" data-row="${s['_row']}" type="button">Готово</button>` : ''}
      </div>
    </div>
  </div>`;
}

function _attachObjStagesHandlers(objectId, stages) {
  // 28.07: аккордеон -- тап по заголовку этапа раскрывает/сворачивает описание.
  // max-height transition вместо display:none/block -- плавная анимация без JS-таймера.
  document.querySelectorAll('.obj-stage-header[data-toggle-row]').forEach(header => {
    header.addEventListener('click', (e) => {
      if (e.target.closest('.obj-stage-description-input, .obj-stage-description-edit-btn, .obj-stage-description-save, .obj-stage-description-cancel')) return;
      const node = header.closest('.obj-stage-node');
      node.classList.toggle('expanded');
    });
  });

  // 29.07 v2: read/edit split -- "Редактировать" переключает read-блок на editor
  // (textarea+Сохранить/Отмена), textarea больше не видна по умолчанию.
  document.querySelectorAll('.obj-stage-description-edit-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const row = btn.dataset.row;
      document.querySelector(`.obj-stage-description-read[data-row="${row}"]`).style.display = 'none';
      const editor = document.querySelector(`.obj-stage-description-editor[data-row="${row}"]`);
      editor.style.display = 'block';
      editor.querySelector('.obj-stage-description-input')?.focus();
    });
  });

  document.querySelectorAll('.obj-stage-description-input').forEach(textarea => {
    // Не закрывать аккордеон тапом внутри textarea.
    textarea.addEventListener('click', (e) => e.stopPropagation());
  });

  document.querySelectorAll('.obj-stage-description-cancel').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const row = btn.dataset.row;
      const editor = document.querySelector(`.obj-stage-description-editor[data-row="${row}"]`);
      const original = document.querySelector(`.obj-stage-description-read[data-row="${row}"] .obj-stage-description-text`)?.textContent || '';
      const textarea = editor.querySelector('.obj-stage-description-input');
      if (textarea) textarea.value = original === 'Описание пока не добавлено' ? '' : original;
      editor.style.display = 'none';
      document.querySelector(`.obj-stage-description-read[data-row="${row}"]`).style.display = '';
    });
  });

  document.querySelectorAll('.obj-stage-description-save').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const row = btn.dataset.row;
      const textarea = document.querySelector(`.obj-stage-description-input[data-row="${row}"]`);
      btn.disabled = true;
      btn.textContent = 'Сохраняю…';
      try {
        await api(`/api/objects/${objectId}/stages/${row}/description`, {
          method: 'PATCH',
          body: JSON.stringify({ description: textarea.value }),
        });
        hapticImpact('light');
        // Обновляем read-блок текстом без полной перерисовки этапа (не теряем expanded-state).
        const readWrap = document.querySelector(`.obj-stage-description-read[data-row="${row}"]`);
        const readText = readWrap.querySelector('.obj-stage-description-text');
        const val = textarea.value.trim();
        readText.textContent = val || 'Описание пока не добавлено';
        readText.classList.toggle('obj-stage-description-empty', !val);
        document.querySelector(`.obj-stage-description-editor[data-row="${row}"]`).style.display = 'none';
        readWrap.style.display = '';
      } catch (err) {
        showToast('Ошибка: ' + err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Сохранить';
      }
    });
  });

  document.querySelectorAll('.obj-stage-complete-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm('Отметить этап завершённым?')) return;
      btn.disabled = true;
      try {
        await api(`/api/objects/${objectId}/stages/${btn.dataset.row}/complete`, { method: 'POST' });
        hapticImpact('medium');
        await _loadObjStages(objectId);
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
        btn.disabled = false;
      }
    });
  });

  // 28.07: заменили up/down-кнопки на реальный touch drag (owner request) -- тот же
  // pointerdown/pointermove/pointerup паттерн, что уже проверен в bubble-assign.js,
  // только вертикальная ось и swap с соседом по позиции курсора вместо drop-зоны.
  if (currentRole === 'owner') _attachStageDragHandlers(objectId, stages);
}

let _stageDragEl = null;
let _stageDragStartY = 0;
let _stageDragStartTop = 0;

function _attachStageDragHandlers(objectId, stages) {
  document.querySelectorAll('.obj-stage-drag-handle').forEach(handle => {
    handle.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      const node = handle.closest('.obj-stage-node');
      _stageDragEl = node;
      _stageDragStartY = e.clientY;
      _stageDragStartTop = node.offsetTop;
      node.classList.add('obj-stage-dragging');
      node.style.zIndex = '10';
      node.setPointerCapture(e.pointerId);
      node.addEventListener('pointermove', _stageDragMove);
      node.addEventListener('pointerup', () => _stageDragEnd(objectId, stages));
    });
  });
}

function _stageDragMove(e) {
  if (!_stageDragEl) return;
  const dy = e.clientY - _stageDragStartY;
  _stageDragEl.style.transform = `translateY(${dy}px)`;
  _stageDragEl.style.transition = 'none';

  // Определяем, над каким соседним узлом сейчас находится курсор -- визуальная
  // подсказка (highlight), реальный swap считается на pointerup по финальной позиции.
  const wrap = document.getElementById('obj-stages-roadmap');
  const nodes = Array.from(wrap.querySelectorAll('.obj-stage-node'));
  const draggedRect = _stageDragEl.getBoundingClientRect();
  const draggedMidY = draggedRect.top + draggedRect.height / 2;
  nodes.forEach(n => n.classList.remove('obj-stage-drop-target'));
  for (const n of nodes) {
    if (n === _stageDragEl) continue;
    const r = n.getBoundingClientRect();
    if (draggedMidY >= r.top && draggedMidY <= r.bottom) {
      n.classList.add('obj-stage-drop-target');
      break;
    }
  }
}

async function _stageDragEnd(objectId, stages) {
  if (!_stageDragEl) return;
  const draggedEl = _stageDragEl;
  const wrap = document.getElementById('obj-stages-roadmap');
  const target = wrap.querySelector('.obj-stage-drop-target');
  draggedEl.removeEventListener('pointermove', _stageDragMove);
  draggedEl.classList.remove('obj-stage-dragging');
  draggedEl.style.zIndex = '';
  draggedEl.style.transform = '';
  draggedEl.style.transition = '';
  wrap.querySelectorAll('.obj-stage-drop-target').forEach(n => n.classList.remove('obj-stage-drop-target'));
  _stageDragEl = null;

  if (!target) return; // отпустили на своём же месте -- ничего не меняем

  const rowA = parseInt(draggedEl.dataset.row, 10);
  const rowB = parseInt(target.dataset.row, 10);
  if (rowA === rowB) return;

  try {
    await api(`/api/objects/${objectId}/stages/${rowA}/swap`, { method: 'PATCH', body: JSON.stringify({ row_num_b: rowB }) });
    hapticImpact('medium');
    await _loadObjStages(objectId);
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
    await _loadObjStages(objectId); // откат визуального состояния к реальным данным с сервера
  }
}

// ═══════════ Встроенный чат объекта — Step 2 v2 (24.07), layout rebuild (29.07 v3) ═══════════
// Физически переносит #chat-thread-detail-view DOM-узел (со всей его viewport/composer
// логикой нетронутой) из его обычного места внутри #view-chat в панель этого таба, и
// возвращает обратно при выходе -- не дублируем chat.js, не строим параллельный рендер.
//
// 29.07 v3: JS-измеренный top (--obj-detail-chat-offset через ResizeObserver+rAF) снят
// целиком -- три попытки (rAF, reorder, view-locked+scrollY save/restore) не решили owner
// report "composer посреди экрана". Новый подход копирует единственный в проекте паттерн,
// который реально надёжен (#view-chat.active/.photo-comments-modal): inset:0 + var(--tg-vp-height),
// НИКАКОГО JS-измерения чужого DOM. Панель чата физически переносит к себе ещё и
// .form-header+#obj-detail-tabs (не клонирует -- один DOM-узел, одни и те же обработчики
// кликов таба продолжают работать), так что заголовок объекта и переключатель вкладок
// остаются видны поверх fullscreen чата без пересчёта чьей-либо позиции.
let _objChatHomeParent = null;
let _objChatHomeNextSibling = null;
let _objChatHeaderHomeParent = null;
let _objChatHeaderHomeNextSibling = null;

async function embedObjectChat(objectId, objectName) {
  const panel = document.getElementById('obj-detail-panel-chat');
  const chatView = document.getElementById('chat-thread-detail-view');
  // 29.07 v4: real bug found via Playwright (not guessed) -- calling embedObjectChat() a
  // second time while it's already active (e.g. re-tapping the "Чат" tab, or any code path
  // that re-runs _initObjDetailTab('chat')) queried '#view-object-detail > .form-header',
  // but the FIRST call already physically moved .form-header out of #view-object-detail and
  // into #obj-chat-embed-header -- the selector no longer matched anything, formHeader/tabs
  // came back null, the embed header was created empty (0 height), and the chat view's flex
  // sibling got a wrong, too-small height. This is exactly the "composer sits high, huge gap
  // below" symptom the owner reported and screenshotted -- reproduced and confirmed visually
  // via a headless Playwright run against the live server with a real signed initData.
  // Fix: if already embedded, look for the header INSIDE #obj-chat-embed-header instead of
  // assuming it's still a direct child of #view-object-detail.
  const alreadyEmbedded = panel?.classList.contains('obj-chat-active');
  const formHeader = alreadyEmbedded
    ? document.getElementById('obj-chat-embed-header')?.querySelector('.form-header')
    : document.querySelector('#view-object-detail > .form-header');
  const tabs = document.getElementById('obj-detail-tabs');
  if (!panel || !chatView) return;
  // Re-entering an already-active embed (same thread) -- nothing structural to redo, just
  // refresh messages. Avoids re-running the DOM-move logic against a panel that's already
  // in its embedded shape.
  if (alreadyEmbedded && _chatActiveThreadKey === `obj:${objectId}`) {
    // 29.07 v4: this early-return path must ALSO clear the inline style="display:block" --
    // _objDetailTabClick() re-sets panel.style.display='block' on every tab click, including
    // re-clicking the already-active "Чат" tab, which lands here. Found via Playwright: the
    // panel's inline style beats the #obj-detail-panel-chat.obj-chat-active{display:flex}
    // CSS rule regardless of which code path set it, so skipping this line here silently
    // reintroduced the exact same "flex container never applies" bug as the direct-DOM-move
    // fix below, just via a different call path.
    panel.style.display = '';
    await _loadChatMessages(true);
    markChatRead(null, `obj:${objectId}`);
    return;
  }

  if (!_objChatHomeParent) {
    _objChatHomeParent = chatView.parentElement;
    _objChatHomeNextSibling = chatView.nextElementSibling;
  }
  panel.innerHTML = '';
  const embedHeader = document.createElement('div');
  embedHeader.id = 'obj-chat-embed-header';
  panel.appendChild(embedHeader);
  if (formHeader && tabs) {
    if (!_objChatHeaderHomeParent) {
      _objChatHeaderHomeParent = formHeader.parentElement;
      _objChatHeaderHomeNextSibling = tabs.nextElementSibling;
    }
    embedHeader.appendChild(formHeader);
    embedHeader.appendChild(tabs);
  }
  panel.appendChild(chatView);
  panel.classList.add('obj-chat-active');
  // 29.07 v4: real bug #2 found via Playwright computed-style dump -- app.html's markup has
  // <div id="obj-detail-panel-chat" class="obj-detail-panel" style="display:block;">. That
  // INLINE style always wins over the #obj-detail-panel-chat.obj-chat-active{display:flex}
  // CSS rule (inline style has higher specificity than any selector, full stop), so the panel
  // stayed display:block even after .obj-chat-active was added -- #chat-thread-detail-view's
  // flex:1 had no flex CONTAINER to size itself against, so it fell back to intrinsic content
  // height instead of filling the remaining viewport. This alone explains the "composer high,
  // huge empty gap below" symptom independent of bug #1 above. Clearing the inline style lets
  // the CSS class rule take over.
  panel.style.display = '';
  chatView.style.display = 'flex';

  // Переиспользуем chat.js внутреннее состояние напрямую -- не switchView('chat'),
  // не openObjectOrMangelChat (та тянет за собой fullscreen header объекта, не нужный
  // тут). nav-hide (chat-dialog-open) добавлен отдельно (25.07) -- composer иначе делил
  // экран с bottom-nav, юзер явно попросил единообразие с обычным полноэкранным чатом.
  document.body.classList.add('chat-dialog-open');
  // 29.07 v3: view-locked/scrollY save-restore больше не нужны -- панель теперь inset:0
  // full-viewport оверлей поверх ВСЕГО #view-object-detail (включая перенесённый сюда
  // header+tabs), а не "плавающий" элемент, чья позиция зависела от текущего scroll
  // родительского документа. Document ниже может оставаться как есть, оверлей его
  // полностью перекрывает независимо от scrollY.
  _chatActiveThread = null;
  _chatActiveThreadKey = `obj:${objectId}`;
  _chatReturnToView = null;
  document.getElementById('chat-close-thread-btn').style.display = 'none';
  _chatLastTs = 0;
  // 29.07: _chatLastRenderSig (chat.js) was never reset here. _renderChatMessages() no-ops
  // when the freshly-fetched signature matches the last one it wrote -- correct for polling
  // the SAME thread, but embedObjectChat() switches _chatActiveThreadKey to a DIFFERENT
  // thread (obj:${objectId}) while the in-memory sig from whatever was rendered before this
  // embed (root chat, a DM, a different object) is still sitting in _chatLastRenderSig. If
  // this object's thread happens to render to an identical signature string (e.g. this
  // object's chat was already viewed earlier this session and nothing changed since), the
  // real fetch succeeds but _renderChatMessages() returns before touching #chat-messages,
  // leaving whatever was in the DOM node when it got moved into this panel -- on a true
  // first-ever open in the session this is the static "Загрузка..." placeholder from
  // app.html, since nothing has written into #chat-messages yet. Resetting to null here
  // guarantees the first render after every embed always writes real content once the
  // fetch resolves, regardless of what was rendered before this thread became active.
  _chatLastRenderSig = null;
  await _loadChatMessages(true);
  markChatRead(null, `obj:${objectId}`);
}

function unembedObjectChat() {
  document.body.classList.remove('chat-dialog-open');
  const panel = document.getElementById('obj-detail-panel-chat');
  const chatView = document.getElementById('chat-thread-detail-view');
  const formHeader = document.getElementById('obj-chat-embed-header')?.querySelector('.form-header');
  const tabs = document.getElementById('obj-detail-tabs');
  if (formHeader && tabs && _objChatHeaderHomeParent) {
    if (_objChatHeaderHomeNextSibling) {
      _objChatHeaderHomeParent.insertBefore(formHeader, _objChatHeaderHomeNextSibling);
      _objChatHeaderHomeParent.insertBefore(tabs, _objChatHeaderHomeNextSibling);
    } else {
      _objChatHeaderHomeParent.appendChild(formHeader);
      _objChatHeaderHomeParent.appendChild(tabs);
    }
  }
  if (!panel || !chatView || !_objChatHomeParent) return;
  panel.classList.remove('obj-chat-active');
  chatView.style.display = 'none';
  if (_objChatHomeNextSibling) {
    _objChatHomeParent.insertBefore(chatView, _objChatHomeNextSibling);
  } else {
    _objChatHomeParent.appendChild(chatView);
  }
}
