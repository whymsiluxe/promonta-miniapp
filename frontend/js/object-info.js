// ═══════════ Инфо объекта — 6-таб экран, Step 3 (24.07) ═══════════
// Work-items (текст+кол-во) + документы (upload/просмотр). Данные per-object,
// backend: /api/objects/{id}/info-items, /api/objects/{id}/documents.

async function renderObjectInfoTab(objectId) {
  const panel = document.getElementById('obj-detail-panel-info');
  panel.innerHTML = `
    <div class="obj-info-section">
      <div class="obj-info-section-title">Работы по объекту</div>
      <div id="obj-info-items-list" class="obj-info-items-list"></div>
      <div class="obj-info-add-row">
        <input type="text" id="obj-info-item-text" class="obj-info-input" placeholder="Например: Штукатурка">
        <input type="text" id="obj-info-item-qty" class="obj-info-input obj-info-input-qty" placeholder="100м²">
        <button id="obj-info-item-add" class="obj-info-add-btn" type="button">+</button>
      </div>
    </div>
    <div class="obj-info-section">
      <div class="obj-info-section-title">Документы</div>
      <div id="obj-info-docs-list" class="obj-info-docs-list"></div>
      <input type="file" id="obj-info-doc-file" accept="image/*,.pdf" style="display:none;">
      <button id="obj-info-doc-add" class="obj-info-add-doc-btn" type="button">+ Прикрепить файл</button>
    </div>
  `;

  document.getElementById('obj-info-item-add').addEventListener('click', () => _addObjInfoItem(objectId));
  document.getElementById('obj-info-doc-add').addEventListener('click', () => document.getElementById('obj-info-doc-file').click());
  document.getElementById('obj-info-doc-file').addEventListener('change', (e) => {
    if (e.target.files[0]) _uploadObjInfoDoc(objectId, e.target.files[0]);
  });

  await Promise.all([_loadObjInfoItems(objectId), _loadObjInfoDocs(objectId)]);
}

async function _loadObjInfoItems(objectId) {
  const list = document.getElementById('obj-info-items-list');
  if (!list) return;
  try {
    const { items } = await api(`/api/objects/${objectId}/info-items`);
    if (!items.length) {
      list.innerHTML = `<div class="obj-info-empty">Пока нет добавленных работ</div>`;
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

async function _loadObjInfoDocs(objectId) {
  const list = document.getElementById('obj-info-docs-list');
  if (!list) return;
  try {
    const { documents } = await api(`/api/objects/${objectId}/documents`);
    if (!documents.length) {
      list.innerHTML = `<div class="obj-info-empty">Нет прикреплённых файлов</div>`;
      return;
    }
    list.innerHTML = documents.map(d => `
      <div class="obj-info-doc-row" data-doc-id="${d.id}" data-doc-file="${esc(d.file)}" data-doc-type="${esc(d.content_type)}" data-doc-name="${esc(d.name)}">
        <span class="obj-info-doc-icon">${_objInfoDocIcon(d.content_type)}</span>
        <span class="obj-info-doc-name">${esc(d.name)}</span>
      </div>
    `).join('');
    list.querySelectorAll('.obj-info-doc-row').forEach(row => {
      row.addEventListener('click', () => _openObjInfoDocViewer(objectId, row.dataset.docFile, row.dataset.docType, row.dataset.docName));
    });
  } catch (e) {
    list.innerHTML = `<div class="obj-info-empty">Ошибка: ${esc(e.message)}</div>`;
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

// ═══════════ Задачи объекта — Step 4 ═══════════
// Owner -> worker, переиспользует loadTasks/attachTaskHandlers/renderTaskRow (objects.js),
// уже принимают произвольные listEl/countEl -- сюда встраиваются как есть, без дублирования.
async function renderObjectTasksTab(objectId) {
  const panel = document.getElementById('obj-detail-panel-tasks');
  panel.innerHTML = `
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

// ═══════════ Потребности объекта — Step 4 ═══════════
// Worker -> owner, глобальный /api/tasks с новым object_id-фильтром (backend Step 4).
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
      list.innerHTML = `<div class="obj-info-empty">Потребностей нет</div>`;
      return;
    }
    list.innerHTML = tasks.map(_renderNeedRow).join('');
  } catch (e) {
    list.innerHTML = `<div class="obj-info-empty">Ошибка: ${esc(e.message)}</div>`;
  }
}
