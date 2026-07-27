// Таб "Объекты": список карточек, задачи, статус, drag&drop сортировка, создание объекта.

function budgetColor(pct) {
  if (pct >= 90) return 'red';
  if (pct >= 60) return 'yellow';
  return 'green';
}

function statusClass(status) {
  if (status === 'Пауза') return 'paused';
  if (status === 'Завершён') return 'done';
  return 'active';
}

// 22.07: реальные AI-фото по типу работ (/media/objects/*.jpg) вместо CSS-градиента —
// выглядит дорого и кинематографично, не абстрактный цвет+эмодзи. object_image_path
// (реальное фото КОНКРЕТНОГО объекта, если задано) остаётся приоритетнее — см. renderObjectCard.
function _objHeroGradient(obj) {
  const name = ((obj['Объект'] || '') + ' ' + (obj['Текущий этап'] || '')).toLowerCase();
  if (name.includes('фасад') || name.includes('wdvs') || name.includes('dämmung')) {
    return { photo: 'facade', icon: '🏗️' };
  } else if (name.includes('кров') || name.includes('dach')) {
    return { photo: 'roof', icon: '🏚️' };
  } else if (name.includes('малярн') || name.includes('maler') || name.includes('краск')) {
    return { photo: 'paint', icon: '🎨' };
  } else if (name.includes('плитк') || name.includes('fliesen')) {
    return { photo: 'tile', icon: '🔲' };
  } else if (name.includes('демонт') || name.includes('abbruch')) {
    return { photo: 'demolition', icon: '🔨' };
  }
  return { photo: 'default', icon: '🏢' };
}

// 25.07 v2: полная пересборка карточки объекта по референсу (composition:
// hero photo -> weather island (top-center) + worker avatars (bottom-left) +
// status pill (bottom-right) -> title -> clickable address -> start date ->
// stage summary strip). Реализовано как одна функция (не отдельный JS-модуль
// с DTO-слоем -- при no-build-step vanilla JS архитектуре этого проекта
// создание отдельного adapter/component файла ради одной функции добавило
// бы больше сложности чем пользы; данные уже приходят из GET /api/objects
// без Google Sheets raw column names, просто читаются напрямую).
const OBJ_STATUS_META = {
  'В работе': { color: 'var(--c-accent, var(--accent))', label: 'В работе' },
  'Пауза': { color: 'var(--c-brass, var(--accent-gold))', label: 'Пауза' },
  'Завершён': { color: 'var(--text-light)', label: 'Завершён' },
};

function _objStatusMeta(status) {
  return OBJ_STATUS_META[status] || { color: 'var(--text-light)', label: status || '—' };
}

function _objStartDateLabel(obj) {
  const raw = obj['Дата старта'];
  if (!raw) return '';
  try {
    const d = new Date(raw);
    if (isNaN(d.getTime())) return '';
    return 'Начало: ' + d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' });
  } catch (e) { return ''; }
}

// Погода объекта -- переиспользуем уже загружаемый общий weather-фид (не
// делаем per-card API запрос, N+1 было бы дорого на списке из 10+ объектов).
// _objWeatherByName заполняется один раз при первой загрузке списка объектов.
let _objWeatherByName = null;
async function _ensureObjWeatherLoaded() {
  if (_objWeatherByName) return;
  _objWeatherByName = {};
  try {
    const res = await api('/api/feed/weather');
    (res.entries || res.feed || res.items || []).forEach(e => {
      if (e.object) _objWeatherByName[e.object] = e;
    });
  } catch (e) { /* погода необязательна -- карточка работает и без неё */ }
}

function _objWeatherIslandHtml(obj) {
  const entry = _objWeatherByName && _objWeatherByName[obj['Объект']];
  const today = entry && entry.wave && entry.wave[0];
  if (!today) return '';
  const tmax = Math.round(today.tmax);
  const code = today.hourly && today.hourly[3] ? today.hourly[3].weather_code : 0;
  const cond = code >= 61 ? 'Дождь' : code >= 45 ? 'Туман' : code >= 2 ? 'Облачно' : 'Ясно';
  return `<div class="obj-weather-island"><b>${tmax}°C</b><span>${cond}</span></div>`;
}

function renderObjectCard(obj) {
  const budgetPct = Math.round(parseFloat(obj['потрачено в % от бюджета']) || 0);
  const stage = obj['Текущий этап'] || '';
  const isWaiting = stage.toLowerCase().startsWith('ожидает');
  const stageLabel = isWaiting ? stage.replace(/^ожидает\s*/i, '') : stage;
  const oid = obj['ID объекта'];
  const bColor = budgetPct >= 90 ? 'var(--red)' : budgetPct >= 60 ? 'var(--warning)' : 'var(--accent)';
  const statusMeta = _objStatusMeta(obj['Статус']);

  const hero = _objHeroGradient(obj);
  const imgStyle = obj.image_path
    ? `background:url('/media/${obj.image_path}') center/cover no-repeat`
    : `background:url('/media/objects/${hero.photo}.jpg') center/cover no-repeat`;

  // Worker avatars -- overlap-композиция снизу-слева (первый крупнее), макс 3 + "+N".
  const assignedUsers = obj.assigned_users || [];
  const visibleUsers = assignedUsers.slice(0, 3);
  const peopleDots = visibleUsers.map((u, i) => {
    const initials = (u.name || '?').split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase();
    const size = i === 0 ? 56 : 46;
    return `<div class="obj-people-dot${i === 0 ? ' obj-people-dot-first' : ''}" style="width:${size}px;height:${size}px;margin-left:${i > 0 ? '-14px' : '0'};z-index:${5 - i}" title="${esc(u.name)}" onclick="event.stopPropagation();openUserCard('${u.user_id}')">${esc(initials)}</div>`;
  }).join('');
  // "+N" открывает Object Detail (полный список команды -- отдельный team-sheet
  // не строим, это редкий edge case при 4+ работниках на одном объекте).
  const extraDots = assignedUsers.length > 3
    ? `<div class="obj-people-dot obj-people-more obj-extra-dots-btn" data-object-id="${esc(oid)}" data-object-name="${esc(obj['Объект']||'')}" style="margin-left:-14px;">+${assignedUsers.length - 3}</div>` : '';
  const addBtn = currentRole === 'owner'
    ? `<div class="obj-people-add obj-add-worker-btn" data-object-id="${esc(oid)}" data-stage="${esc(stage||'')}" title="Назначить"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="#000" stroke-width="2.5" stroke-linecap="round"/></svg></div>` : '';

  const startDateLabel = _objStartDateLabel(obj);
  const mapsUrl = obj['Адрес'] ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(obj['Адрес'])}` : '';

  // Stage summary strip -- из списка объектов доступен только текущий этап строкой
  // (не полный timeline с DONE/ACTIVE/NEXT статусами -- это потребовало бы отдельного
  // /api/objects/{id}/stages запроса на каждую карточку, N+1 на списке). Показываем то,
  // что реально есть без лишних round-trip'ов; полный roadmap -- в Object Detail -> Этапы.
  const stagesStripHtml = stageLabel
    ? `<div class="obj-stage-strip stage-clickable" data-object-id="${oid}" data-object-name="${esc(obj['Объект']) || ''}">
         <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style="flex-shrink:0;"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="3.5" fill="currentColor"/></svg>
         <span>${isWaiting ? 'Ожидает: ' : ''}${esc(stageLabel)}</span>
       </div>`
    : `<div class="obj-stage-strip stage-clickable" data-object-id="${oid}" data-object-name="${esc(obj['Объект']) || ''}"><span style="color:var(--text-light)">Этапы не добавлены</span></div>`;

  return `
  <div class="card obj-card-v2" data-id="${oid}" data-status="${esc(obj['Статус'] || '')}">
    <div class="obj-card-hero" style="${imgStyle}">
      ${_objWeatherIslandHtml(obj)}
      <div class="obj-hero-people">${peopleDots}${extraDots}${addBtn}</div>
      <div class="obj-hero-status-pill" style="--pill-accent:${statusMeta.color}">${esc(statusMeta.label)}</div>
    </div>
    <div class="obj-card-body">
      <div class="obj-card-title">${esc(obj['Объект']) || ''}</div>
      <div class="obj-card-address obj-address-link" onclick="event.stopPropagation();${mapsUrl ? `openExternalLink('${mapsUrl}')` : ''}">
        <svg class="obj-address-pin" viewBox="0 0 24 24" width="14" height="14" fill="none"><path d="M12 2C7.58 2 4 5.58 4 10c0 5.25 7 12 8 12s8-6.75 8-12c0-4.42-3.58-8-8-8z" fill="currentColor"/><circle cx="12" cy="10" r="2.5" fill="var(--bg-card)"/></svg>
        ${esc(obj['Адрес']) || 'Адрес не указан'}
      </div>
      ${startDateLabel ? `<div class="obj-card-startdate">${esc(startDateLabel)}</div>` : ''}
    </div>
    ${stagesStripHtml}
    ${currentRole === 'owner' ? `
    <div class="metrics">
      <div class="metric">
        <div class="metric-row"><span>Бюджет</span><b style="color:${bColor}">${budgetPct}%</b></div>
        <div class="metric-bar"><div class="metric-fill ${budgetColor(budgetPct)}" style="width:${budgetPct}%"></div></div>
      </div>
    </div>` : ''}
  </div>`;
}

function renderTaskRow(t) {
  const done = t['Статус'] === 'erledigt';
  const canComplete = currentRole === 'owner' && !done;
  return `
  <div class="task-row ${done ? 'done' : ''}" data-task-id="${t['ID задачи']}">
    <div class="checkbox ${done ? 'done' : ''} ${canComplete ? '' : 'disabled'}">${done ? '✓' : ''}</div>
    <span>${esc(t['Текст'])}</span>
  </div>`;
}

async function loadTasks(objectId, listEl, countEl) {
  try {
    const data = await api(`/api/objects/${objectId}/tasks`);
    if (!data.tasks.length) {
      listEl.innerHTML = '<div style="padding:0.3rem 0;color:var(--text-light);font-size:0.85rem">Задач нет</div>';
    } else {
      listEl.innerHTML = data.tasks.map(renderTaskRow).join('');
    }
    if (countEl) countEl.textContent = `(${data.tasks.length})`;
    attachTaskHandlers(listEl, objectId);
  } catch (e) {
    listEl.innerHTML = `<div style="padding:0.3rem 0;color:var(--red);font-size:0.85rem">Ошибка: ${esc(e.message)}</div>`;
  }
}

function attachTaskHandlers(listEl, objectId) {
  listEl.querySelectorAll('.checkbox:not(.disabled)').forEach(box => {
    box.addEventListener('click', async () => {
      const taskId = box.closest('.task-row').dataset.taskId;
      box.classList.add('disabled');
      try {
        await api(`/api/tasks/${taskId}/complete`, { method: 'PATCH' });
        const card = listEl.closest('.card');
        const countEl = card.querySelector('.tasks-count');
        await loadTasks(objectId, listEl, countEl);
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
        box.classList.remove('disabled');
      }
    });
  });
}

const ORDER_KEY = 'promonta_objects_order';

function saveObjectsOrder() {
  const ids = Array.from(document.querySelectorAll('#objects-cards .card')).map(c => c.dataset.id);
  localStorage.setItem(ORDER_KEY, JSON.stringify(ids));
}

function applyObjectsOrder(objects) {
  let saved;
  try { saved = JSON.parse(localStorage.getItem(ORDER_KEY) || '[]'); } catch (e) { saved = []; }
  if (!saved.length) return objects;
  const byId = new Map(objects.map(o => [o['ID объекта'], o]));
  const ordered = [];
  saved.forEach(id => { if (byId.has(id)) { ordered.push(byId.get(id)); byId.delete(id); } });
  byId.forEach(o => ordered.push(o));
  return ordered;
}

let objDragState = null;

function attachObjectsDragHandlers() {
  const container = document.getElementById('objects-cards');
  let longPressTimer = null;

  container.querySelectorAll('.card').forEach(card => {
    card.addEventListener('touchstart', (e) => {
      if (e.target.closest('.status-switch, .take-btn, .checkbox, .add-task, .tasks-label')) return;
      longPressTimer = setTimeout(() => {
        startObjectDrag(card);
        hapticImpact('medium');
        playDragTickSound();
      }, 450);
    }, { passive: true });

    card.addEventListener('touchmove', (e) => {
      if (objDragState && objDragState.card === card) {
        e.preventDefault();
        handleObjectDragMove(e.touches[0].clientY);
      } else {
        clearTimeout(longPressTimer);
      }
    }, { passive: false });

    card.addEventListener('touchend', () => {
      clearTimeout(longPressTimer);
      if (objDragState) endObjectDrag();
    });
  });
}

function startObjectDrag(card) {
  objDragState = { card, container: document.getElementById('objects-cards') };
  card.classList.add('dragging');
}

function handleObjectDragMove(clientY) {
  if (!objDragState) return;
  const { card, container } = objDragState;
  const cards = Array.from(container.querySelectorAll('.card:not(.dragging)'));
  const target = cards.find(c => {
    const rect = c.getBoundingClientRect();
    return clientY < rect.top + rect.height / 2;
  });
  const before = card.nextElementSibling;
  if (target) {
    container.insertBefore(card, target);
  } else {
    container.appendChild(card);
  }
  if (card.nextElementSibling !== before) hapticImpact('light');
}

function endObjectDrag() {
  if (!objDragState) return;
  objDragState.card.classList.remove('dragging');
  objDragState.card.dataset.wasDragged = '1'; // подавляет click-open на этот тап (это был drag, не тап)
  hapticImpact('light');
  playDropSound();
  saveObjectsOrder();
  objDragState = null;
}

function attachObjectsHandlers() {
  attachObjectsDragHandlers();

  document.querySelectorAll('#objects-cards .metric-fill').forEach(fill => {
    const target = fill.style.width;
    fill.style.width = '0%';
    requestAnimationFrame(() => requestAnimationFrame(() => fill.style.width = target));
  });

  document.querySelectorAll('#objects-cards .stage-clickable').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation(); // не даём всплыть до card-level клика ниже -- открылось бы дважды/на неверный таб
      openObjectDetail(el.dataset.objectId, el.dataset.objectName, 'stages', el.closest('.card')?.dataset.status);
    });
  });

  document.querySelectorAll('#objects-cards .obj-extra-dots-btn').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      openObjectDetail(el.dataset.objectId, el.dataset.objectName, 'chat');
    });
  });

  document.querySelectorAll('#objects-cards .obj-add-worker-btn').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      openBubbleAssign(el.dataset.objectId, el.dataset.stage, el);
    });
  });

  // 24.07: клик по всей карточке объекта -> новый 6-таб экран (было доступно только
  // через узкую строку "Текущий этап"). Исключаем интерактивные элементы внутри карточки
  // (тот же exclusion-list что у drag touchstart выше) + сам drag/long-press не должен
  // триггерить открытие -- card.dataset.wasDragged ставится в endObjectDrag().
  document.querySelectorAll('#objects-cards .card').forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.status-switch, .take-btn, .checkbox, .add-task, .tasks-label, .obj-people-add, .obj-people-more, .obj-address-link, .obj-mangel-link, .stage-clickable, .stage-edit-icon')) return;
      if (card.dataset.wasDragged === '1') { card.dataset.wasDragged = ''; return; }
      openObjectDetail(card.dataset.id, card.querySelector('.obj-card-title')?.textContent || '', 'chat', card.dataset.status);
    });
  });

}

function openNewObjectView() {
  document.getElementById('objects-list-view').style.display = 'none';
  document.getElementById('new-object-view').classList.add('open');
  document.getElementById('new-obj-error').innerHTML = '';
  ['new-obj-name', 'new-obj-adresse', 'new-obj-budget', 'new-obj-start', 'new-obj-end'].forEach(id => {
    document.getElementById(id).value = '';
  });
}

function closeNewObjectView() {
  document.getElementById('new-object-view').classList.remove('open');
  document.getElementById('objects-list-view').style.display = '';
}

async function submitNewObject() {
  const errorEl = document.getElementById('new-obj-error');
  errorEl.innerHTML = '';

  const name = document.getElementById('new-obj-name').value.trim();
  const adresse = document.getElementById('new-obj-adresse').value.trim();
  const budget = document.getElementById('new-obj-budget').value.trim();
  const start = document.getElementById('new-obj-start').value;
  const end = document.getElementById('new-obj-end').value;

  if (!name || !adresse || !budget) {
    errorEl.innerHTML = '<div class="form-error">Заполни название, адрес и бюджет.</div>';
    return;
  }

  // Оптимистичный UI: закрываем форму и показываем карточку сразу,
  // не дожидаясь ответа сервера (Sheets API даёт заметную задержку).
  const tempId = 'pending-' + Date.now();
  const optimisticObj = {
    'ID объекта': tempId, 'Объект': name, 'Адрес': adresse, 'Статус': 'В работе',
    'потрачено в % от бюджета': '0', 'Текущий этап': ''
  };
  closeNewObjectView();
  const container = document.getElementById('objects-cards');
  container.insertAdjacentHTML('afterbegin', renderObjectCard(optimisticObj));
  const card = container.querySelector(`[data-id="${tempId}"]`);
  card.classList.add('pending');
  attachObjectsHandlers();

  try {
    const res = await api('/api/objects', { method: 'POST', body: JSON.stringify({ name, adresse, budget, start, end }) });
    card.dataset.id = res.object_id;
    card.classList.remove('pending');
    saveObjectsOrder();
  } catch (e) {
    card.remove();
    showToast('Не удалось создать объект: ' + e.message, 'error');
  }
}

let _allObjects = [];

async function loadObjects() {
  const container = document.getElementById('objects-cards');

  try {
    const data = await api('/api/objects');
    _allObjects = data.objects || [];
    if (_allObjects.length === 0) {
      container.innerHTML = '<div style="padding:2rem 1rem;color:var(--text-light)">Объектов пока нет.</div>';
      return;
    }
    _populateObjCityFilter(_allObjects);
    _renderFilteredObjects();
  } catch (e) {
    container.innerHTML = `<div style="padding:2rem 1rem;color:var(--red)">Ошибка загрузки: ${esc(e.message)}</div>`;
  }
}

function _objCity(obj) {
  const addr = obj['Адрес'] || '';
  const lastPart = addr.split(',').pop().trim();
  return lastPart.split(/\s+/).filter(w => !/^\d+$/.test(w)).join(' ') || '';
}

function _populateObjCityFilter(objects) {
  const sel = document.getElementById('obj-filter-city');
  if (!sel || sel.dataset.populated) return;
  const cities = [...new Set(objects.map(_objCity).filter(Boolean))].sort();
  cities.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c; opt.textContent = c;
    sel.appendChild(opt);
  });
  sel.dataset.populated = '1';
  // budget sort options are financial data, hide for worker
  if (currentRole !== 'owner') {
    document.querySelectorAll('#obj-sort option[value^="budget-"]').forEach(o => o.remove());
  }
}

function _renderFilteredObjects() {
  const container = document.getElementById('objects-cards');
  const q = (document.getElementById('obj-search')?.value || '').trim().toLowerCase();
  const cityFilter = document.getElementById('obj-filter-city')?.value || '';
  const statusFilter = document.getElementById('obj-filter-status')?.value || '';
  const sortMode = document.getElementById('obj-sort')?.value || 'order';

  let list = _allObjects.filter(obj => {
    if (q) {
      const hay = ((obj['Объект'] || '') + ' ' + (obj['Адрес'] || '')).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (cityFilter && _objCity(obj) !== cityFilter) return false;
    if (statusFilter && (obj['Статус'] || '') !== statusFilter) return false;
    return true;
  });

  if (sortMode === 'order') {
    list = applyObjectsOrder(list);
  } else {
    const pct = o => parseFloat(o['потрачено в % от бюджета']) || 0;
    const cmp = {
      'progress-desc': (a, b) => pct(b) - pct(a),
      'progress-asc': (a, b) => pct(a) - pct(b),
      'budget-desc': (a, b) => pct(b) - pct(a),
      'budget-asc': (a, b) => pct(a) - pct(b),
      'name-asc': (a, b) => (a['Объект'] || '').localeCompare(b['Объект'] || '', 'ru'),
    }[sortMode];
    if (cmp) list = [...list].sort(cmp);
  }

  if (list.length === 0) {
    container.innerHTML = '<div style="padding:2rem 1rem;color:var(--text-light)">Ничего не найдено.</div>';
    return;
  }
  container.innerHTML = list.map(renderObjectCard).join('');
  attachObjectsHandlers();
}

function _debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function initObjectsToolbar() {
  const search = document.getElementById('obj-search');
  const debouncedRender = _debounce(_renderFilteredObjects, 300);
  if (search) search.addEventListener('input', debouncedRender);
  ['obj-filter-city', 'obj-filter-status', 'obj-sort'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', _renderFilteredObjects);
  });
}

const STAGE_STATUS_LABEL = { 'предстоит': 'Предстоит', 'в процессе': 'В процессе', 'готово': 'Готово' };
const STAGE_STATUS_CYCLE = ['предстоит', 'в процессе', 'готово'];
let _stagesCurrentObjectId = null;

function renderStageRow(stage) {
  const status = stage['Статус'] || 'предстоит';
  const isOwner = currentRole === 'owner';
  // CSS class -- whitelist, не просто esc(): статус из Sheets, произвольный текст
  // не должен становиться частью class list. Только буквы/цифры/дефис проходят,
  // всё остальное схлопывается в один безопасный fallback-класс.
  const statusSlug = /^[a-zA-Zа-яА-Я0-9\-]+$/.test(status.replace(/\s/g, '-'))
    ? status.replace(/\s/g, '-') : 'unknown';
  return `
  <div class="stage-row" data-num="${esc(stage['№ этапа'])}">
    <div class="stage-row-name">${esc(stage['Название этапа'])}</div>
    <div class="stage-row-status stage-status-${statusSlug}${isOwner ? '' : ' stage-row-status-readonly'}" data-status="${esc(status)}">${esc(STAGE_STATUS_LABEL[status] || status)}</div>
    ${isOwner ? `<button class="stage-row-delete" data-num="${esc(stage['№ этапа'])}">×</button>` : ''}
  </div>`;
}

function attachStagesRowHandlers(stages) {
  if (currentRole !== 'owner') return;
  document.querySelectorAll('.stage-row-status').forEach(el => {
    el.addEventListener('click', async () => {
      const stageNum = el.closest('.stage-row').dataset.num;
      const rowNum = _stageRowIndexMap[stageNum];
      const current = el.dataset.status;
      const idx = STAGE_STATUS_CYCLE.indexOf(current);
      const next = STAGE_STATUS_CYCLE[(idx + 1) % STAGE_STATUS_CYCLE.length];
      try {
        await api(`/api/objects/${_stagesCurrentObjectId}/stages/${rowNum}`, { method: 'PATCH', body: JSON.stringify({ status: next }) });
        hapticImpact('light');
        await loadStagesWithRowNumbers();
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
      }
    });
  });

  document.querySelectorAll('.stage-row-delete').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Удалить этап?')) return;
      const stageNum = btn.dataset.num;
      const rowNum = _stageRowIndexMap[stageNum];
      try {
        await api(`/api/objects/${_stagesCurrentObjectId}/stages/${rowNum}`, { method: 'DELETE' });
        await loadStagesWithRowNumbers();
      } catch (e) {
        showToast('Ошибка: ' + e.message, 'error');
      }
    });
  });
}

let _stageRowIndexMap = {};
let _stagesCurrentObjectName = '';

async function openStagesView(objectId, objectName) {
  _stagesCurrentObjectId = objectId;
  _stagesCurrentObjectName = objectName || objectId;
  document.getElementById('objects-list-view').style.display = 'none';
  document.getElementById('stages-view').classList.add('open');
  await loadStagesWithRowNumbers();
  if (typeof initCheckinControls === 'function') initCheckinControls();
  const chatBtn = document.getElementById('object-chat-btn');
  if (chatBtn && !chatBtn.dataset.wired) {
    chatBtn.dataset.wired = '1';
    chatBtn.addEventListener('click', () => {
      if (typeof openObjectOrMangelChat === 'function') {
        openObjectOrMangelChat(`obj:${_stagesCurrentObjectId}`, `Чат: ${_stagesCurrentObjectName}`, 'objects');
      }
    });
  }
}

async function loadStagesWithRowNumbers() {
  const listEl = document.getElementById('stages-list');
  listEl.innerHTML = '<div style="padding:1rem;color:var(--text-light);text-align:center">Загрузка...</div>';
  try {
    const data = await api(`/api/objects/${_stagesCurrentObjectId}/stages`);
    if (!data.stages.length) {
      listEl.innerHTML = '<div class="empty-state">Этапов пока нет. Добавь первый ниже.</div>';
      _stageRowIndexMap = {};
      return;
    }
    _stageRowIndexMap = {};
    data.stages.forEach(s => { _stageRowIndexMap[s['№ этапа']] = s['_row']; });
    listEl.innerHTML = data.stages.map(renderStageRow).join('');
    attachStagesRowHandlers(data.stages);
  } catch (e) {
    listEl.innerHTML = `<div class="empty-state" style="color:var(--red)">Ошибка: ${esc(e.message)}</div>`;
  }
}

function closeStagesView() {
  document.getElementById('stages-view').classList.remove('open');
  document.getElementById('objects-list-view').style.display = '';
  loadObjects();
}

async function addNewStage() {
  const input = document.getElementById('new-stage-name');
  const name = input.value.trim();
  if (!name) return;
  const btn = document.getElementById('add-stage-btn');
  btn.disabled = true;
  try {
    await api(`/api/objects/${_stagesCurrentObjectId}/stages`, { method: 'POST', body: JSON.stringify({ name }) });
    input.value = '';
    await loadStagesWithRowNumbers();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

function initObjectsView() {
  document.getElementById('add-object').style.display = currentRole === 'owner' ? 'flex' : 'none';
  document.getElementById('add-object').addEventListener('click', () => {
    if (currentRole !== 'owner') return;
    openNewObjectView();
  });
  document.getElementById('new-obj-back').addEventListener('click', closeNewObjectView);
  document.getElementById('new-obj-submit').addEventListener('click', submitNewObject);
  document.getElementById('stages-back').addEventListener('click', closeStagesView);
  document.getElementById('add-stage-btn').addEventListener('click', addNewStage);
  initObjectsToolbar();
  loadObjects();
}


// ═══════════ Детали объекта — 6-таб экран (24.07, Step 1: shell + lazy tab init) ═══════════
// Каждая вкладка лениво инициализируется при первом открытии (тот же паттерн, что
// loadedViews в switchView() app.html) -- не грузим все 6 источников данных разом.
let _objDetailCurrentId = null;
let _objDetailCurrentName = '';
let _objDetailCurrentStatus = '';
const _objDetailLoadedTabs = new Set();

function openObjectDetail(objectId, objectName, initialTab, objectStatus) {
  _objDetailCurrentId = objectId;
  _objDetailCurrentName = objectName || objectId;
  _objDetailCurrentStatus = objectStatus || '';
  _objDetailLoadedTabs.clear();
  document.getElementById('objects-list-view').style.display = 'none';
  const view = document.getElementById('view-object-detail');
  view.style.display = 'block';
  document.getElementById('obj-detail-title').textContent = _objDetailCurrentName;

  const tab = initialTab || 'chat';
  document.querySelectorAll('#obj-detail-tabs .doc-type-opt').forEach(opt => {
    opt.classList.toggle('active', opt.dataset.objTab === tab);
  });
  document.querySelectorAll('.obj-detail-panel').forEach(p => { p.style.display = 'none'; });
  document.getElementById(`obj-detail-panel-${tab}`).style.display = 'block';
  _initObjDetailTab(tab);
}

function _objDetailTabClick(tab) {
  if (tab !== 'chat' && typeof unembedObjectChat === 'function') unembedObjectChat();
  document.querySelectorAll('#obj-detail-tabs .doc-type-opt').forEach(o => o.classList.toggle('active', o.dataset.objTab === tab));
  document.querySelectorAll('.obj-detail-panel').forEach(p => { p.style.display = 'none'; });
  document.getElementById(`obj-detail-panel-${tab}`).style.display = 'block';
  _initObjDetailTab(tab);
}

function closeObjectDetail() {
  if (typeof unembedObjectChat === 'function') unembedObjectChat();
  document.getElementById('view-object-detail').style.display = 'none';
  document.getElementById('objects-list-view').style.display = '';
  _objDetailCurrentId = null;
  loadObjects();
}

function _initObjDetailTab(tab) {
  if (_objDetailLoadedTabs.has(tab)) return;
  _objDetailLoadedTabs.add(tab);
  const panel = document.getElementById(`obj-detail-panel-${tab}`);
  if (tab === 'chat') {
    // 24.07 Step 2 v2: юзер явно потребовал ВСТРОЕННЫЙ чат (не отдельный fullscreen-экран,
    // который открывался поверх всего) -- реализовано физическим переносом существующего
    // #chat-thread-detail-view DOM-узла внутрь панели таба (embedObjectChat в object-info.js),
    // а не switchView('chat'). Переоткрывать можно каждый раз -- дешёвая операция, не
    // считается "загруженным" в obj detail lazy-init смысле.
    _objDetailLoadedTabs.delete(tab);
    embedObjectChat(_objDetailCurrentId, _objDetailCurrentName);
    return;
  }
  if (tab === 'info') {
    // 25.07 v3: Инфо рендерит всю сводку (статус/описание/работы/этапы/дефекты/документы)
    // одним вызовом. Потребности -- отдельный object-scoped таб (см. ниже), не часть Инфо.
    renderObjectInfoTab(_objDetailCurrentId);
    return;
  }
  if (tab === 'needs') {
    renderObjectNeedsTab(_objDetailCurrentId);
    return;
  }
  panel.innerHTML = `<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Загрузка…</div>`;
}

// 25.07: свайп-переключение между 6 табами объекта (тот же UX, что юзер уже одобрил
// в подвкладках Чата) -- жест ловится на весь #view-object-detail, но глушится над
// зонами со своим горизонтальным/вертикальным взаимодействием (сама строка табов уже
// скроллится тапом -- не нужно вдобавок дёргать её свайпом; чат-композер/сообщения,
// roadmap move-кнопки -- те же exclusion-соображения что у глобального swipe-nav.js).
const OBJ_DETAIL_TAB_ORDER = ['chat', 'info', 'needs'];
let _objTabSwipeStartX = 0;
let _objTabSwipeStartY = 0;
let _objTabSwipeExcluded = false;
const OBJ_TAB_SWIPE_THRESHOLD = 50;

function _isObjTabSwipeExcluded(target) {
  return !!target.closest?.('#obj-detail-tabs, .chat-messages, .chat-input-bar, .obj-stage-move-col, .obj-info-doc-viewer, #obj-info-doc-viewer, input, textarea');
}

function _currentObjDetailTab() {
  const active = document.querySelector('#obj-detail-tabs .doc-type-opt.active');
  return active ? active.dataset.objTab : 'chat';
}

document.addEventListener('DOMContentLoaded', () => {
  const backBtn = document.getElementById('obj-detail-back');
  if (backBtn) backBtn.addEventListener('click', closeObjectDetail);

  document.querySelectorAll('#obj-detail-tabs .doc-type-opt').forEach(opt => {
    opt.addEventListener('click', () => _objDetailTabClick(opt.dataset.objTab));
  });

  const detailView = document.getElementById('view-object-detail');
  if (detailView) {
    detailView.addEventListener('touchstart', (e) => {
      _objTabSwipeStartX = e.changedTouches[0].screenX;
      _objTabSwipeStartY = e.changedTouches[0].screenY;
      _objTabSwipeExcluded = _isObjTabSwipeExcluded(e.target);
    }, { passive: true });

    detailView.addEventListener('touchend', (e) => {
      if (_objTabSwipeExcluded) return;
      const diffX = e.changedTouches[0].screenX - _objTabSwipeStartX;
      const diffY = e.changedTouches[0].screenY - _objTabSwipeStartY;
      if (Math.abs(diffX) < OBJ_TAB_SWIPE_THRESHOLD) return;
      if (Math.abs(diffX) < Math.abs(diffY)) return; // вертикальный скролл контента -- не наш жест

      const curIdx = OBJ_DETAIL_TAB_ORDER.indexOf(_currentObjDetailTab());
      const nextIdx = diffX < 0 ? curIdx + 1 : curIdx - 1;
      if (nextIdx < 0 || nextIdx >= OBJ_DETAIL_TAB_ORDER.length) return;
      hapticImpact('light');
      _objDetailTabClick(OBJ_DETAIL_TAB_ORDER[nextIdx]);
    }, { passive: true });
  }
});
