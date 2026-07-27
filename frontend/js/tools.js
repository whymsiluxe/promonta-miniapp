// Таб "Инструмент": каталог, поиск/фильтры, выдача/возврат, история движений.

let TOOLS = [];

const TOOLS_OBJECTS = ['Дом Мюллер', 'Офис Санация', 'Квартира Вебер'];
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

function renderToolCard(tool) {
  const statusColor = tool.status === 'free' ? 'var(--accent)' : tool.status === 'in-use' ? 'var(--warning)' : 'var(--red)';
  const icon = _toolIcon(tool.category);
  const icon3d = _toolIcon3d(tool);
  const heroStyle = `background:${_toolHeroStyle(tool)}`;

  // Holder avatar — кликабелен только если есть holderId (worker сам оформил checkout).
  // Owner может вписать имя вручную без реального user_id — тогда avatar остаётся non-clickable.
  const holderDot = tool.holder
    ? (tool.holderId
        ? `<div class="obj-people-dot" style="cursor:pointer" title="${esc(tool.holder)}" onclick="event.stopPropagation();openUserCard('${esc(tool.holderId)}')">${esc((tool.holder[0] || '?').toUpperCase())}</div>`
        : `<div class="obj-people-dot" title="${esc(tool.holder)}">${esc((tool.holder[0] || '?').toUpperCase())}</div>`)
    : '';

  // Stat chips: серийный номер · статус · объект
  const chips = [
    { label: `№${tool.id}`, sub: 'серийный', color: 'var(--text-light)' },
    { label: esc(STATUS_LABEL[tool.status] || tool.status), sub: 'статус', color: statusColor },
    { label: esc(tool.object ? (tool.object.length > 12 ? tool.object.slice(0,11)+'…' : tool.object) : '—'), sub: 'объект', color: 'var(--text-light)' },
  ];
  const chipsHtml = chips.map(c =>
    `<div class="obj-stat-chip"><span class="obj-chip-val" style="color:${c.color}">${c.label}</span><span class="obj-chip-sub">${c.sub}</span></div>`
  ).join('');

  let actionBtn = '';
  if (currentRole === 'owner') {
    actionBtn = `<button class="take-btn" data-id="${tool.id}">Изменить</button>`;
  } else if (tool.status === 'free') {
    actionBtn = `<button class="take-btn" data-id="${tool.id}">Взять</button>`;
  }

  return `
  <div class="card tool-card obj-card-v2" data-id="${esc(tool.id)}" data-status="${esc(tool.status)}" data-search="${esc((String(tool.id) + ' ' + tool.name + ' ' + tool.category).toLowerCase())}">
    <div class="obj-card-hero" style="${heroStyle}">
      ${icon3d}
      <div class="obj-hero-live-pill" style="background:${statusColor}22;color:${statusColor};border:1px solid ${statusColor}44">
        <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${statusColor};margin-right:4px;vertical-align:middle"></span>${STATUS_LABEL[tool.status]}
      </div>
      <div class="obj-hero-people">${holderDot}</div>
    </div>
    <div class="obj-card-body">
      <div class="obj-card-title">${esc(tool.name)}</div>
      <div class="obj-card-address">${esc(tool.category)}</div>
      <div class="obj-chips-row">${chipsHtml}</div>
    </div>
    ${actionBtn}
    <div class="history-label collapsed"><span class="chevron">▾</span>История движений</div>
    <div class="history-body collapsed"><div class="history-empty">Загрузка...</div></div>
  </div>`;
}

function openTakeModal(toolId) {
  const tool = TOOLS.find(t => t.id === toolId);
  if (!tool) return;

  const isOwnerEdit = currentRole === 'owner';
  const objectOptions = TOOLS_OBJECTS.map(o =>
    `<option value="${esc(o)}" ${tool.object === o ? 'selected' : ''}>${esc(o)}</option>`).join('');

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-title">${esc(tool.name)}</div>
      <label class="modal-label">Объект</label>
      <select class="modal-select" id="modal-object">
        <option value="">— не выбрано —</option>
        ${objectOptions}
        <option value="${PERSONAL_USE}" ${tool.object === PERSONAL_USE ? 'selected' : ''}>${PERSONAL_USE}</option>
      </select>
      <label class="modal-label">Кто взял</label>
      <input class="modal-input" id="modal-holder" type="text" placeholder="Имя" value="${esc(isOwnerEdit ? (tool.holder || '') : '')}" ${isOwnerEdit ? '' : 'readonly'}>
      ${isOwnerEdit ? `
      <label class="modal-label">Статус</label>
      <select class="modal-select" id="modal-status">
        <option value="На объекте" ${tool.status === 'in-use' ? 'selected' : ''}>На объекте</option>
        <option value="" ${tool.status === 'free' ? 'selected' : ''}>Свободен</option>
        <option value="Зарезервирован" ${tool.status === 'reserved' ? 'selected' : ''}>Зарезервирован</option>
        <option value="В ремонте" ${tool.status === 'repair' ? 'selected' : ''}>В ремонте</option>
        <option value="Не найден" ${tool.status === 'missing' ? 'selected' : ''}>Не найден</option>
      </select>` : ''}
      <div class="modal-actions">
        <button class="modal-btn secondary" id="modal-cancel">Отмена</button>
        <button class="modal-btn primary" id="modal-save">Сохранить</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  overlay.querySelector('#modal-cancel').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

  overlay.querySelector('#modal-save').addEventListener('click', async () => {
    const object = overlay.querySelector('#modal-object').value;
    const holder = overlay.querySelector('#modal-holder').value.trim();
    const saveBtn = overlay.querySelector('#modal-save');

    if (!isOwnerEdit && (!holder || !object)) {
      showToast('Укажи объект и кто взял.', 'error');
      return;
    }

    saveBtn.disabled = true;
    saveBtn.textContent = 'Сохранение...';
    try {
      if (isOwnerEdit) {
        const status = overlay.querySelector('#modal-status').value;
        await api(`/api/tools/${tool.id}`, { method: 'PATCH', body: JSON.stringify({ status, holder, object_name: object }) });
      } else {
        await api(`/api/tools/${tool.id}/checkout`, { method: 'PATCH', body: JSON.stringify({ holder, object_name: object }) });
      }
      overlay.remove();
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

async function openToolHistory(toolId) {
  const label = document.querySelector(`#tools-cards .card[data-id="${toolId}"] .history-label`);
  const body = label.nextElementSibling;
  const willOpen = label.classList.contains('collapsed');
  label.classList.toggle('collapsed');
  body.classList.toggle('collapsed');
  if (!willOpen || body.dataset.loaded) return;

  try {
    const data = await api(`/api/tools/${toolId}/history`);
    body.dataset.loaded = '1';
    body.innerHTML = data.history.length
      ? data.history.map(h => `<div class="history-row"><span class="h-date">${h.date.split(' ')[0]}</span><span class="h-text">${h.text}</span></div>`).join('')
      : `<div class="history-empty">Движений не было</div>`;
  } catch (e) {
    body.innerHTML = `<div class="history-empty">Ошибка загрузки истории</div>`;
  }
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
  document.querySelectorAll('#tools-cards .history-label').forEach(label => {
    const card = label.closest('.card');
    label.addEventListener('click', () => openToolHistory(card.dataset.id));
  });

  document.querySelectorAll('#tools-cards .take-btn').forEach(btn => {
    btn.addEventListener('click', () => openTakeModal(btn.dataset.id));
  });
}

let toolsActiveFilter = 'all';

function applyToolsFilters() {
  const q = document.getElementById('tools-search').value.trim().toLowerCase();
  const filtered = TOOLS.filter(t => {
    const matchesFilter = toolsActiveFilter === 'all' || t.status === toolsActiveFilter;
    const matchesSearch = !q || (String(t.id) + ' ' + t.name + ' ' + t.category).toLowerCase().includes(q);
    return matchesFilter && matchesSearch;
  });
  renderAllTools(filtered);
}

async function loadTools() {
  const container = document.getElementById('tools-cards');
  try {
    const data = await api('/api/tools');
    TOOLS = data.tools.map(mapTool);
    applyToolsFilters();
  } catch (e) {
    container.innerHTML = `<div class="empty-state">Ошибка загрузки: ${esc(e.message)}</div>`;
  }
}

function initToolsView() {
  document.getElementById('add-tool').style.display = currentRole === 'owner' ? 'flex' : 'none';
  document.getElementById('add-tool').addEventListener('click', () => {
    if (currentRole !== 'owner') return;
    openNewToolModal();
  });

  document.getElementById('tools-search').addEventListener('input', applyToolsFilters);

  document.getElementById('tools-filters').addEventListener('click', (e) => {
    const chip = e.target.closest('.filter-chip');
    if (!chip) return;
    document.querySelectorAll('#tools-filters .filter-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    toolsActiveFilter = chip.dataset.filter;
    applyToolsFilters();
  });

  loadTools();
}
