// Таб "Инструмент": каталог, поиск/фильтры, выдача/возврат, история движений.

let TOOLS = [];
let TOOLS_ACTIVE_OBJECTS = []; // 30.07: реальные объекты вместо хардкода, грузятся один раз (см. loadToolsObjects)
const PERSONAL_USE = 'Личное пользование';

const STATUS_LABEL = { free: 'Свободен', 'in-use': 'На объекте', reserved: 'Зарезервирован', repair: 'В ремонте', missing: 'Не найден' };
const RAW_STATUS_MAP = { 'на объекте': 'in-use', 'зарезервирован': 'reserved', 'в ремонте': 'repair', 'не найден': 'missing' };

function mapToolStatus(raw) {
  const r = (raw || '').trim().toLowerCase();
  return RAW_STATUS_MAP[r] || 'free';
}

function mapTool(raw) {
  return {
    id: raw['Серийный #'],
    name: raw['Название Инструмента'],
    category: raw['Категория'],
    status: mapToolStatus(raw['Статус']),
    holder: raw['Кто взял'] || null,
    holderId: raw['ID держателя'] || null,
    object: raw['Обьект/Адрес'] || null,
    history: []
  };
}

// Эмодзи-иконки по категории инструмента
const TOOL_CATEGORY_ICON = {
  'Электроинструмент': '⚡', 'Ручной инструмент': '🔧', 'Измерение': '📐',
  'Леса': '🏗️', 'Транспорт': '🚛', 'Прочее': '🛠️'
};
function _toolIcon(cat) {
  return TOOL_CATEGORY_ICON[cat] || '🛠️';
}

// 3D объёмная иконка по названию/категории инструмента (Фаза 10.26) — распознаём
// конкретный тип по name (дрель/молоток/ключ/пила/лестница/уровень), иначе
// универсальный ti-default значок.
const TOOL_ICON_PARTS = {
  drill: '<div class="ti-grip ti-body"></div><div class="ti-housing ti-body"></div><div class="ti-bit ti-body"></div><div class="ti-battery ti-body"></div>',
  hammer: '<div class="ti-handle ti-body"></div><div class="ti-head ti-body"></div>',
  wrench: '<div class="ti-shaft ti-body"></div><div class="ti-jaw-top ti-body"></div><div class="ti-jaw-bottom ti-body"></div>',
  saw: '<div class="ti-blade ti-body"></div><div class="ti-teeth ti-body"></div><div class="ti-handle ti-body"></div>',
  ladder: '<div class="ti-rail-l ti-body"></div><div class="ti-rail-r ti-body"></div><div class="ti-rung ti-body"></div><div class="ti-rung ti-body"></div><div class="ti-rung ti-body"></div>',
  level: '<div class="ti-bar ti-body"></div><div class="ti-bubble ti-body"></div>',
  default: '<div class="ti-a ti-body"></div><div class="ti-b ti-body"></div>',
};

function _toolIcon3dVariant(tool) {
  const n = (tool.name || '').toLowerCase();
  if (n.includes('дрел') || n.includes('шуруповёрт') || n.includes('шуруповерт') || n.includes('перфоратор')) return 'drill';
  if (n.includes('молот')) return 'hammer';
  if (n.includes('ключ') || n.includes('гаечн')) return 'wrench';
  if (n.includes('пила') || n.includes('болгарк')) return 'saw';
  if (n.includes('лестниц') || n.includes('леса') || n.includes('стремянк')) return 'ladder';
  if (n.includes('уровень')) return 'level';
  return 'default';
}

function _toolIcon3d(tool) {
  // 22.07: реальное фото инструмента вместо CSS-заглушки (7 категорий, сгенерировано заранее,
  // /media/tools/*.jpg) — выглядит дорого и понятно что за инструмент, не абстрактная форма.
  const variant = _toolIcon3dVariant(tool);
  return `<img class="tool-photo" src="/media/tools/${variant}.jpg" alt="${esc(tool.category || '')}" loading="lazy">`;
}

// Градиент фона карточки инструмента по статусу
function _toolHeroStyle(tool) {
  if (tool.status === 'repair') return 'linear-gradient(135deg,#1f1512 0%,#3a2420 100%)';
  if (tool.status === 'missing') return 'linear-gradient(135deg,#1a1a1a 0%,#2A2A2A 100%)';
  if (tool.status === 'in-use') return 'linear-gradient(135deg,#161d18 0%,#233029 100%)';
  if (tool.status === 'reserved') return 'linear-gradient(135deg,#241f10 0%,#3d3420 100%)';
  return 'linear-gradient(135deg,#0F1F17 0%,#173627 100%)';
}

// 30.07 (Инструменты-редизайн): карточка компактнее -- фото/название/категория+№/статус/
// объект+держатель (только если заполнены)/одна кнопка. Убраны 3 одинаковых stat chips
// и раскрывающаяся история (теперь только в подробностях по tap, см. openToolDetail).
function _toolMainActionLabel(tool) {
  if (currentRole === 'owner') return 'Управление';
  if (tool.status === 'free') return 'Взять';
  if (tool.status === 'in-use' && String(tool.holderId || '') === String(currentUserId)) return 'Вернуть';
  return '';
}

function renderToolCard(tool) {
  const statusColor = tool.status === 'free' ? 'var(--accent)' : tool.status === 'in-use' ? 'var(--warning)' : 'var(--red)';
  const icon3d = _toolIcon3d(tool);
  const heroStyle = `background:${_toolHeroStyle(tool)}`;

  const holderDot = tool.holder
    ? (tool.holderId
        ? `<div class="obj-people-dot" style="cursor:pointer" title="${esc(tool.holder)}" onclick="event.stopPropagation();openUserCard('${esc(tool.holderId)}')">${esc((tool.holder[0] || '?').toUpperCase())}</div>`
        : `<div class="obj-people-dot" title="${esc(tool.holder)}">${esc((tool.holder[0] || '?').toUpperCase())}</div>`)
    : '';

  const metaLine = [tool.holder ? `Выдан · ${esc(tool.holder)}` : '', tool.object ? esc(tool.object) : ''].filter(Boolean);
  const actionLabel = _toolMainActionLabel(tool);
  const actionBtn = actionLabel
    ? `<button class="take-btn tool-card-action-btn" data-id="${esc(tool.id)}" data-action="${actionLabel === 'Управление' ? 'manage' : (actionLabel === 'Вернуть' ? 'return' : 'take')}">${actionLabel}</button>`
    : '';

  return `
  <div class="card tool-card obj-card-v2" data-id="${esc(tool.id)}" data-status="${esc(tool.status)}" data-search="${esc([tool.id, tool.name, tool.category, tool.holder, tool.object].filter(Boolean).join(' ').toLowerCase())}">
    <div class="obj-card-hero" style="${heroStyle}">
      ${icon3d}
      <div class="obj-hero-live-pill" style="background:${statusColor}22;color:${statusColor};border:1px solid ${statusColor}44">
        <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${statusColor};margin-right:4px;vertical-align:middle"></span>${STATUS_LABEL[tool.status]}
      </div>
      <div class="obj-hero-people">${holderDot}</div>
    </div>
    <div class="obj-card-body">
      <div class="obj-card-title">${esc(tool.name)}</div>
      <div class="obj-card-address">${esc(tool.category)} · №${esc(tool.id)}</div>
      ${metaLine.length ? `<div class="tool-card-meta">${metaLine.join(' · ')}</div>` : ''}
    </div>
    ${actionBtn}
  </div>`;
}

// Подробная карточка -- модалка/bottom sheet, открывается tap-ом по свободному месту
// карточки (не по кнопке действия -- та использует event.stopPropagation()).
async function openToolDetail(toolId) {
  const tool = TOOLS.find(t => t.id === toolId);
  if (!tool) return;

  const statusColor = tool.status === 'free' ? 'var(--accent)' : tool.status === 'in-use' ? 'var(--warning)' : 'var(--red)';
  const icon3d = _toolIcon3d(tool);
  const holderRow = tool.holder ? `
    <div class="modal-label">Держатель</div>
    <div class="tool-detail-row${tool.holderId ? ' tool-detail-row-clickable' : ''}" ${tool.holderId ? `onclick="openUserCard('${esc(tool.holderId)}')"` : ''}>${esc(tool.holder)}</div>` : '';
  const objectRow = tool.object ? `<div class="modal-label">Объект</div><div class="tool-detail-row">${esc(tool.object)}</div>` : '';
  const actionLabel = _toolMainActionLabel(tool);
  const actionAttr = actionLabel === 'Управление' ? 'manage' : (actionLabel === 'Вернуть' ? 'return' : 'take');

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal tool-detail-modal">
      <div class="tool-detail-hero" style="background:${_toolHeroStyle(tool)}">${icon3d}</div>
      <div class="modal-title">${esc(tool.name)}</div>
      <div class="modal-label">Категория</div>
      <div class="tool-detail-row">${esc(tool.category)}</div>
      <div class="modal-label">Серийный номер</div>
      <div class="tool-detail-row">№${esc(tool.id)}</div>
      <div class="modal-label">Статус</div>
      <div class="tool-detail-row" style="color:${statusColor}">${esc(STATUS_LABEL[tool.status] || tool.status)}</div>
      ${objectRow}
      ${holderRow}
      <div class="modal-label">История движений</div>
      <div id="tool-detail-history" class="tool-detail-history">Загрузка истории…</div>
      ${actionLabel ? `<div class="modal-actions"><button class="modal-btn primary" id="tool-detail-action-btn" data-action="${actionAttr}">${actionLabel}</button></div>` : ''}
    </div>`;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

  overlay.querySelector('#tool-detail-action-btn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    overlay.remove();
    if (actionAttr === 'manage') openManageModal(tool.id);
    else if (actionAttr === 'return') _returnTool(tool.id);
    else _takeToolQuick(tool.id);
  });

  try {
    const data = await api(`/api/tools/${toolId}/history`);
    const body = overlay.querySelector('#tool-detail-history');
    if (!body) return;
    body.innerHTML = data.history.length
      ? data.history.map(h => `<div class="history-row"><span class="h-date">${h.date.split(' ')[0]}</span><span class="h-text">${h.text}</span></div>`).join('')
      : `<div class="history-empty">Движений пока не было</div>`;
  } catch (e) {
    const body = overlay.querySelector('#tool-detail-history');
    if (body) body.innerHTML = `<div class="history-empty">Ошибка загрузки истории</div>`;
  }
}

// Worker берёт свободный инструмент -- выбирает только объект. Имя держателя больше
// НЕ вводится вручную (баг: Worker мог вписать чужое имя -- "Кто взял" и "ID держателя"
// относились бы к разным людям): backend сам определяет holder_name из авторизованного
// Telegram user (см. checkout_tool в main.py), frontend отправляет только object_name.
function _takeToolQuick(toolId) {
  const tool = TOOLS.find(t => t.id === toolId);
  if (!tool) return;
  const objectOptions = TOOLS_ACTIVE_OBJECTS.map(o =>
    `<option value="${esc(o)}">${esc(o)}</option>`).join('');

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-title">Взять «${esc(tool.name)}»</div>
      <label class="modal-label">Объект</label>
      <select class="modal-select" id="modal-object">
        <option value="">— не выбрано —</option>
        ${objectOptions}
        <option value="${PERSONAL_USE}">${PERSONAL_USE}</option>
      </select>
      <div class="modal-actions">
        <button class="modal-btn secondary" id="modal-cancel">Отмена</button>
        <button class="modal-btn primary" id="modal-save">Взять</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  overlay.querySelector('#modal-cancel').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

  overlay.querySelector('#modal-save').addEventListener('click', async () => {
    const object = overlay.querySelector('#modal-object').value;
    const saveBtn = overlay.querySelector('#modal-save');
    if (!object) {
      showToast('Укажи объект.', 'error');
      return;
    }
    saveBtn.disabled = true;
    saveBtn.textContent = 'Сохранение...';
    try {
      await api(`/api/tools/${toolId}/checkout`, { method: 'PATCH', body: JSON.stringify({ object_name: object }) });
      overlay.remove();
      hapticImpact('medium');
      showToast('Инструмент взят', 'success');
      await loadTools();
    } catch (e) {
      showToast('Ошибка: ' + e.message, 'error');
      saveBtn.disabled = false;
      saveBtn.textContent = 'Взять';
    }
  });
}

// Worker возвращает СВОЙ инструмент (holderId === currentUserId, проверено до вызова
// в _toolMainActionLabel) -- настоящий /return endpoint, НЕ /checkout с пустыми полями
// (тот всё равно писал бы holder_id текущего юзера на свободный инструмент).
async function _returnTool(toolId) {
  try {
    await api(`/api/tools/${toolId}/return`, { method: 'PATCH' });
    hapticImpact('light');
    showToast('Инструмент возвращён', 'success');
    await loadTools();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

// Owner: "Управление" -- select работника из /api/workers вместо ручного ввода имени
// (п.7 спека). "Другое лицо" оставляет текстовое поле для случаев вне списка работников.
async function openManageModal(toolId) {
  const tool = TOOLS.find(t => t.id === toolId);
  if (!tool) return;

  let workers = [];
  try {
    const data = await api('/api/workers');
    workers = (data.workers || []).filter(w => w.role === 'worker');
  } catch (e) { /* тихо -- select всё равно предложит "Другое лицо"/"Никто" */ }

  const objectOptions = TOOLS_ACTIVE_OBJECTS.map(o =>
    `<option value="${esc(o)}" ${tool.object === o ? 'selected' : ''}>${esc(o)}</option>`).join('');
  const currentHolderMode = tool.holderId ? `worker:${tool.holderId}` : (tool.holder ? 'other' : 'none');
  const workerOptions = workers.map(w =>
    `<option value="worker:${esc(w.user_id)}" ${currentHolderMode === `worker:${w.user_id}` ? 'selected' : ''}>${esc(w.name)}</option>`).join('');

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-title">${esc(tool.name)}</div>
      <label class="modal-label">Статус</label>
      <select class="modal-select" id="modal-status">
        <option value="На объекте" ${tool.status === 'in-use' ? 'selected' : ''}>На объекте</option>
        <option value="" ${tool.status === 'free' ? 'selected' : ''}>Свободен</option>
        <option value="Зарезервирован" ${tool.status === 'reserved' ? 'selected' : ''}>Зарезервирован</option>
        <option value="В ремонте" ${tool.status === 'repair' ? 'selected' : ''}>В ремонте</option>
        <option value="Не найден" ${tool.status === 'missing' ? 'selected' : ''}>Не найден</option>
      </select>
      <label class="modal-label">Объект</label>
      <select class="modal-select" id="modal-object">
        <option value="">— не выбрано —</option>
        ${objectOptions}
        <option value="${PERSONAL_USE}" ${tool.object === PERSONAL_USE ? 'selected' : ''}>${PERSONAL_USE}</option>
      </select>
      <label class="modal-label">Держатель</label>
      <select class="modal-select" id="modal-holder-mode">
        ${workerOptions}
        <option value="other" ${currentHolderMode === 'other' ? 'selected' : ''}>Другое лицо</option>
        <option value="none" ${currentHolderMode === 'none' ? 'selected' : ''}>Никто</option>
      </select>
      <input class="modal-input" id="modal-holder-other" type="text" placeholder="Имя" value="${esc(currentHolderMode === 'other' ? (tool.holder || '') : '')}" style="${currentHolderMode === 'other' ? '' : 'display:none'}">
      <div class="modal-actions">
        <button class="modal-btn secondary" id="modal-cancel">Отмена</button>
        <button class="modal-btn primary" id="modal-save">Сохранить</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const holderModeSelect = overlay.querySelector('#modal-holder-mode');
  const holderOtherInput = overlay.querySelector('#modal-holder-other');
  holderModeSelect.addEventListener('change', () => {
    holderOtherInput.style.display = holderModeSelect.value === 'other' ? '' : 'none';
  });

  overlay.querySelector('#modal-cancel').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

  overlay.querySelector('#modal-save').addEventListener('click', async () => {
    const status = overlay.querySelector('#modal-status').value;
    const object = overlay.querySelector('#modal-object').value;
    const holderMode = holderModeSelect.value;
    const saveBtn = overlay.querySelector('#modal-save');

    let holder = '', holderId = '', objectName = object;
    if (holderMode === 'other') {
      holder = holderOtherInput.value.trim();
    } else if (holderMode.startsWith('worker:')) {
      const wid = holderMode.slice('worker:'.length);
      const w = workers.find(w => String(w.user_id) === wid);
      holder = w ? w.name : '';
      holderId = wid;
    }
    // "Никто" -- holder/holderId остаются пустыми. Статус "Свободен" (пустая строка в select)
    // тоже обязан очистить holder/holderId/object -- иначе получится противоречивое состояние
    // "свободный инструмент с держателем".
    if (holderMode === 'none' || status === '') {
      holder = ''; holderId = ''; objectName = '';
    }

    saveBtn.disabled = true;
    saveBtn.textContent = 'Сохранение...';
    try {
      await api(`/api/tools/${tool.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status, holder, object_name: objectName, holder_id: holderId }),
      });
      overlay.remove();
      hapticImpact('medium');
      showToast('Сохранено', 'success');
      await loadTools();
    } catch (e) {
      showToast('Ошибка: ' + e.message, 'error');
      saveBtn.disabled = false;
      saveBtn.textContent = 'Сохранить';
    }
  });
}

function openNewToolModal() {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-title">Новый инструмент</div>
      <label class="modal-label">Название</label>
      <input class="modal-input" id="new-name" type="text" placeholder="напр. Bosch дрель">
      <label class="modal-label">Категория</label>
      <input class="modal-input" id="new-category" type="text" placeholder="напр. Дрель">
      <div class="modal-actions">
        <button class="modal-btn secondary" id="modal-cancel">Отмена</button>
        <button class="modal-btn primary" id="modal-save">Добавить</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  overlay.querySelector('#modal-cancel').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

  overlay.querySelector('#modal-save').addEventListener('click', async () => {
    const name = overlay.querySelector('#new-name').value.trim();
    const category = overlay.querySelector('#new-category').value.trim();
    const saveBtn = overlay.querySelector('#modal-save');

    if (!name || !category) {
      showToast('Укажи название и категорию.', 'error');
      return;
    }

    saveBtn.disabled = true;
    saveBtn.textContent = 'Добавление...';
    try {
      await api('/api/tools', { method: 'POST', body: JSON.stringify({ name, category }) });
      overlay.remove();
      await loadTools();
    } catch (e) {
      showToast('Ошибка: ' + e.message, 'error');
      saveBtn.disabled = false;
      saveBtn.textContent = 'Добавить';
    }
  });
}

function renderAllTools(list) {
  const container = document.getElementById('tools-cards');
  if (!list.length) {
    container.innerHTML = '<div class="empty-state">Ничего не найдено.</div>';
    return;
  }
  container.innerHTML = list.map(renderToolCard).join('');
  attachToolsHandlers();
}

function attachToolsHandlers() {
  // Tap по свободному месту карточки -- подробности; tap по кнопке действия --
  // своё действие с event.stopPropagation(), чтобы не открывать подробности заодно.
  document.querySelectorAll('#tools-cards .tool-card').forEach(card => {
    card.addEventListener('click', () => openToolDetail(card.dataset.id));
  });
  document.querySelectorAll('#tools-cards .tool-card-action-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const action = btn.dataset.action;
      if (action === 'manage') openManageModal(btn.dataset.id);
      else if (action === 'return') _returnTool(btn.dataset.id);
      else _takeToolQuick(btn.dataset.id);
    });
  });
}

let toolsActiveFilter = 'all';

function _updateToolsSummary() {
  const counts = {
    all: TOOLS.length,
    free: TOOLS.filter(t => t.status === 'free').length,
    'in-use': TOOLS.filter(t => t.status === 'in-use').length,
    repair: TOOLS.filter(t => t.status === 'repair').length,
  };
  document.getElementById('tools-summary-all').textContent = counts.all;
  document.getElementById('tools-summary-free').textContent = counts.free;
  document.getElementById('tools-summary-in-use').textContent = counts['in-use'];
  document.getElementById('tools-summary-repair').textContent = counts.repair;
}

// Поиск расширен (п.2 спека): серийный номер/название/категория/держатель/объект --
// не только название+категория как раньше.
function applyToolsFilters() {
  const q = document.getElementById('tools-search').value.trim().toLowerCase();
  const filtered = TOOLS.filter(t => {
    const matchesFilter = toolsActiveFilter === 'all' || t.status === toolsActiveFilter;
    const matchesSearch = !q || [t.id, t.name, t.category, t.holder, t.object].filter(Boolean).join(' ').toLowerCase().includes(q);
    return matchesFilter && matchesSearch;
  });
  renderAllTools(filtered);
}

async function loadTools() {
  const container = document.getElementById('tools-cards');
  try {
    const data = await api('/api/tools');
    TOOLS = data.tools.map(mapTool);
    _updateToolsSummary();
    applyToolsFilters();
  } catch (e) {
    container.innerHTML = `<div class="empty-state">Ошибка загрузки: ${esc(e.message)}</div>`;
  }
}

// Реальные объекты вместо TOOLS_OBJECTS-хардкода (п.6 спека) -- грузятся один раз,
// не по разу на каждую карточку/форму.
async function loadToolsObjects() {
  try {
    const data = await api('/api/objects');
    TOOLS_ACTIVE_OBJECTS = (data.objects || [])
      .filter(o => (o['Статус'] || '') !== 'Завершён')
      .map(o => o['Объект'] || '')
      .filter(Boolean);
  } catch (e) {
    TOOLS_ACTIVE_OBJECTS = [];
  }
}

function initToolsView() {
  document.getElementById('add-tool').style.display = currentRole === 'owner' ? 'flex' : 'none';
  document.getElementById('add-tool').addEventListener('click', () => {
    if (currentRole !== 'owner') return;
    openNewToolModal();
  });

  document.getElementById('tools-search').addEventListener('input', applyToolsFilters);

  document.getElementById('tools-summary-bar').addEventListener('click', (e) => {
    const tile = e.target.closest('.tools-summary-tile');
    if (!tile) return;
    document.querySelectorAll('#tools-summary-bar .tools-summary-tile').forEach(t => t.classList.remove('active'));
    tile.classList.add('active');
    toolsActiveFilter = tile.dataset.filter;
    applyToolsFilters();
  });

  loadToolsObjects();
  loadTools();
}
