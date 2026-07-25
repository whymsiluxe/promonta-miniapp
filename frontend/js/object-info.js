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
  const statusEditorHtml = currentRole === 'owner' ? `
    <div class="obj-info-section">
      <div class="obj-info-section-title">Статус объекта</div>
      <div class="status-switch" id="obj-detail-status-switch" data-current="${esc(_objDetailCurrentStatus)}">
        ${['В работе', 'Пауза', 'Завершён'].map(s =>
          `<div class="status-opt${s === _objDetailCurrentStatus ? ' active' : ''}" data-status="${s}">${s}</div>`
        ).join('')}
      </div>
    </div>` : '';

  panel.innerHTML = `
    ${statusEditorHtml}
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
      <div class="obj-info-section-title">Этапы</div>
      <div id="obj-info-stages-summary"></div>
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
  `;

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

  await Promise.all([
    _renderObjDescriptionSection(objectId),
    _renderObjWorksVolumesSection(objectId),
    _renderObjWorksTasksSection(objectId),
    _renderObjStagesSummary(objectId),
    _renderObjDefectsSummary(objectId),
    _renderObjDocsSummary(objectId),
  ]);
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
  await loadTasks(objectId, listEl, null);
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
        await loadTasks(objectId, listEl, null);
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
      }
    });
  }
}

// ── Этапы (компактная сводка, полный roadmap живёт по клику -- переиспользует
// renderObjectStagesTab-логику, просто рендерит в новый контейнер) ──
async function _renderObjStagesSummary(objectId) {
  const wrap = document.getElementById('obj-info-stages-summary');
  if (!wrap) return;
  wrap.innerHTML = `<div id="obj-stages-roadmap" class="obj-stages-roadmap"></div>`;
  await _loadObjStages(objectId);
  if (currentRole !== 'owner' && typeof _openCheckinStatusScreen === 'function') {
    _appendCheckinShortcut(wrap, objectId);
  }
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
  return `
  <div class="obj-info-item-row">
    <span class="obj-info-item-text">${esc(n.title || '')}</span>
    <span class="obj-info-item-qty">${esc(n.status || 'открыто')}</span>
  </div>`;
}

async function renderObjectNeedsTab(objectId) {
  const panel = document.getElementById('obj-detail-panel-needs');
  panel.innerHTML = `
    <div id="obj-needs-list" class="obj-info-items-list"></div>
    ${currentRole !== 'owner' ? `
    <div class="obj-info-add-row">
      <input type="text" id="obj-needs-new-text" class="obj-info-input" placeholder="Например: нужен перфоратор">
      <button id="obj-needs-add-btn" class="obj-info-add-btn" type="button">+</button>
    </div>` : ''}
  `;
  await _loadObjNeeds(objectId);

  const addBtn = document.getElementById('obj-needs-add-btn');
  if (addBtn) {
    addBtn.addEventListener('click', async () => {
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
}

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
      wrap.innerHTML = `<div class="obj-info-empty">Этапов пока нет</div>`;
      return;
    }
    const currentIdx = stages.findIndex(s => s['Статус'] === 'в процессе');
    wrap.innerHTML = stages.map((s, i) => _renderStageRoadmapNode(s, i, stages.length, i === currentIdx)).join('');
    _attachObjStagesHandlers(objectId, stages);
  } catch (e) {
    wrap.innerHTML = `<div class="obj-info-empty">Ошибка: ${esc(e.message)}</div>`;
  }
}

function _renderStageRoadmapNode(s, idx, total, isCurrent) {
  const status = s['Статус'] || 'предстоит';
  const dotClass = status === 'готово' ? 'done' : status === 'в процессе' ? 'active' : '';
  const canMoveUp = currentRole === 'owner' && idx > 0;
  const canMoveDown = currentRole === 'owner' && idx < total - 1;
  const canWorkerComplete = currentRole !== 'owner' && isCurrent;
  return `
  <div class="obj-stage-node" data-row="${s['_row']}" data-num="${s['№ этапа']}">
    <div class="obj-stage-line">
      <div class="obj-stage-dot ${dotClass}"></div>
      ${idx < total - 1 ? '<div class="obj-stage-connector"></div>' : ''}
    </div>
    <div class="obj-stage-body">
      <div class="obj-stage-name">${esc(s['Название этапа'] || '')}</div>
      <div class="obj-stage-status-label obj-stage-status-${status.replace(/\s/g, '-')}">${OBJ_STAGE_STATUS_LABEL[status] || status}</div>
      ${canWorkerComplete ? `<button class="obj-stage-complete-btn" data-row="${s['_row']}" type="button">Готово</button>` : ''}
    </div>
    ${currentRole === 'owner' ? `
    <div class="obj-stage-move-col">
      <button class="obj-stage-move-btn" data-dir="up" data-row="${s['_row']}" type="button" ${canMoveUp ? '' : 'disabled'}>▲</button>
      <button class="obj-stage-move-btn" data-dir="down" data-row="${s['_row']}" type="button" ${canMoveDown ? '' : 'disabled'}>▼</button>
    </div>` : ''}
  </div>`;
}

function _attachObjStagesHandlers(objectId, stages) {
  document.querySelectorAll('.obj-stage-move-btn:not([disabled])').forEach(btn => {
    btn.addEventListener('click', async () => {
      const rowNum = parseInt(btn.dataset.row, 10);
      const idx = stages.findIndex(s => s['_row'] === rowNum);
      const targetIdx = btn.dataset.dir === 'up' ? idx - 1 : idx + 1;
      if (targetIdx < 0 || targetIdx >= stages.length) return;
      const rowNumB = stages[targetIdx]['_row'];
      try {
        await api(`/api/objects/${objectId}/stages/${rowNum}/swap`, { method: 'PATCH', body: JSON.stringify({ row_num_b: rowNumB }) });
        hapticImpact('light');
        await _loadObjStages(objectId);
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
      }
    });
  });

  document.querySelectorAll('.obj-stage-complete-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
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
}

// ═══════════ Встроенный чат объекта — Step 2 v2 (24.07) ═══════════
// Физически переносит #chat-thread-detail-view DOM-узел (со всей его viewport/composer
// логикой нетронутой) из его обычного места внутри #view-chat в панель этого таба, и
// возвращает обратно при выходе -- не дублируем chat.js, не строим параллельный рендер.
let _objChatHomeParent = null; // куда вернуть DOM при unembed
let _objChatHomeNextSibling = null;
let _objChatOffsetObserver = null;

function _updateObjChatOffset() {
  const tabs = document.getElementById('obj-detail-tabs');
  if (!tabs) return;
  const rect = tabs.getBoundingClientRect();
  document.documentElement.style.setProperty('--obj-detail-chat-offset', `${rect.bottom}px`);
}

async function embedObjectChat(objectId, objectName) {
  const panel = document.getElementById('obj-detail-panel-chat');
  const chatView = document.getElementById('chat-thread-detail-view');
  if (!panel || !chatView) return;

  if (!_objChatHomeParent) {
    _objChatHomeParent = chatView.parentElement;
    _objChatHomeNextSibling = chatView.nextElementSibling;
  }
  panel.innerHTML = '';
  panel.appendChild(chatView);
  panel.classList.add('obj-chat-active');
  chatView.style.display = 'flex';

  _updateObjChatOffset();
  if (!_objChatOffsetObserver && window.ResizeObserver) {
    _objChatOffsetObserver = new ResizeObserver(_updateObjChatOffset);
    _objChatOffsetObserver.observe(document.getElementById('obj-detail-tabs'));
  }

  // Переиспользуем chat.js внутреннее состояние напрямую -- не switchView('chat'),
  // не openObjectOrMangelChat (та тянет за собой fullscreen header объекта, не нужный
  // тут). nav-hide (chat-dialog-open) добавлен отдельно (25.07) -- composer иначе делил
  // экран с bottom-nav, юзер явно попросил единообразие с обычным полноэкранным чатом.
  document.body.classList.add('chat-dialog-open');
  _chatActiveThread = null;
  _chatActiveThreadKey = `obj:${objectId}`;
  _chatReturnToView = null;
  document.getElementById('chat-close-thread-btn').style.display = 'none';
  _chatLastTs = 0;
  await _loadChatMessages(true);
  markChatRead(null, `obj:${objectId}`);
}

function unembedObjectChat() {
  document.body.classList.remove('chat-dialog-open');
  const panel = document.getElementById('obj-detail-panel-chat');
  const chatView = document.getElementById('chat-thread-detail-view');
  if (!panel || !chatView || !_objChatHomeParent) return;
  panel.classList.remove('obj-chat-active');
  chatView.style.display = 'none';
  if (_objChatHomeNextSibling) {
    _objChatHomeParent.insertBefore(chatView, _objChatHomeNextSibling);
  } else {
    _objChatHomeParent.appendChild(chatView);
  }
  if (_objChatOffsetObserver) {
    _objChatOffsetObserver.disconnect();
    _objChatOffsetObserver = null;
  }
}
