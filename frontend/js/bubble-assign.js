// Floating-bubble drag&drop назначение работников на этапы объекта (Фаза 2d).
// Аватарки всех работников плавают как bubbles; skill-matched — крупнее/ярче.
// Drag via pointer-events (не HTML5 DnD — плохо работает на iOS touch).

let _bubblePanel = null;
let _bubbleObjectId = null;
let _bubbleStage = null;
let _bubbleDragEl = null;
let _bubbleDragOffX = 0;
let _bubbleDragOffY = 0;
let _bubbleDragStartX = 0;
let _bubbleDragStartY = 0;
let _bubbleDragMoved = false;
const BUBBLE_TAP_THRESHOLD_PX = 6; // 28.07 (Phase 05): движение меньше этого = тап, не drag

// Skill ↔ stage keyword mapping
const SKILL_STAGE_MAP = {
  'Штукатурка': ['штукатур', 'stucco', 'putz', 'шпакл', 'spachtel'],
  'Малярные работы': ['малярн', 'maler', 'краск', 'покраск'],
  'Электрика': ['электр', 'elektr'],
  'Кровля': ['кровл', 'dach', 'roof'],
  'Фасад': ['фасад', 'fassade', 'wdvs', 'dämmung', 'утеплен'],
  'Сантехника': ['санте', 'sanit', 'труб'],
  'Плитка': ['плитк', 'fliesen', 'tile'],
  'Демонтаж': ['демонт', 'abriss', 'abbruch', 'снос'],
};

function _isSkillMatch(skills, stageName) {
  const stageLower = (stageName || '').toLowerCase();
  return skills.some(skill => {
    const keywords = SKILL_STAGE_MAP[skill] || [];
    return keywords.some(kw => stageLower.includes(kw));
  });
}

function _makeAvatarText(name) {
  const parts = (name || '?').split(' ').filter(Boolean);
  return parts.length >= 2
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : (parts[0] || '?').slice(0, 2).toUpperCase();
}

// workers: [{user_id, name, skills:[...]}]
async function openBubbleAssign(objectId, stageName, dropZoneEl) {
  _bubbleObjectId = objectId;
  _bubbleStage = stageName;

  // 10.31 (Fable-аудит): раньше список строился только из уже назначенных на
  // другие объекты + текущего юзера, у остальных worker'ов skills всегда было [] —
  // авто-матч по навыкам почти никогда не срабатывал. /api/workers уже отдаёт
  // реальные skills из онбординг-квиза каждого — используем его напрямую.
  let workers = [];
  try {
    const data = await api('/api/workers');
    workers = (data.workers || [])
      .filter(w => w.role === 'worker')
      .map(w => ({ user_id: w.user_id, name: w.name, skills: w.skills || [] }));
  } catch (e) {
    console.warn('bubble-assign: worker load failed', e);
    return;
  }

  if (!workers.length) return;

  // Build panel
  const panel = document.createElement('div');
  panel.id = 'bubble-panel';
  panel.innerHTML = `
    <div class="bubble-panel-header">
      <span class="bubble-panel-title">Назначить на этап</span>
      <span class="bubble-panel-stage">${esc(stageName || '')}</span>
      <button class="bubble-panel-close" onclick="_closeBubblePanel()">✕</button>
    </div>
    <!-- 28.07: owner request -- read-only "Просмотр" режим, чтобы посмотреть занятость
       команды не рискуя случайно кого-то назначить тапом/drag. Тот же паттерн переключателя,
       что уже используют другие doc-type-switch экраны в приложении. -->
    <div class="bubble-mode-switch" id="bubble-mode-switch">
      <div class="bubble-mode-opt active" data-bubble-mode="assign">Распределение</div>
      <div class="bubble-mode-opt" data-bubble-mode="view">Просмотр</div>
    </div>
    <div class="bubble-panel-hint" id="bubble-panel-hint">Перетащите работника на зону этапа или просто тапните по нему</div>
    <div id="bubble-drop-zone" class="bubble-drop-zone">
      <div class="bubble-drop-label">⬆ Перетащить сюда</div>
    </div>
    <div id="bubble-arena" class="bubble-arena">
      ${workers.map((w, i) => {
        const matched = _isSkillMatch(w.skills || [], stageName);
        const delay = (i * 0.37).toFixed(2);
        const dur = (2.2 + Math.abs(((i * 17) % 10) / 10)).toFixed(2);
        // 28.07: owner request -- кружки были маленькие, увеличены; добавлена подпись
        // имени под кругом (раньше видно было только на title-tooltip при hover,
        // на touch-устройстве недоступном вообще).
        const size = matched ? 101 : 78;
        const opacity = matched ? '1' : '0.55';
        const glow = matched ? 'box-shadow:0 0 12px 3px var(--accent);border:2px solid var(--accent);' : 'border:2px solid var(--border-color);';
        // 28.07 v2: drag двигает именно .bubble напрямую (position:fixed + left/top
        // в px, см. _bubbleDragMove) -- подпись имени должна ехать вместе с кругом при
        // перетаскивании, поэтому она ВНУТРИ .bubble (overflow:visible), не в отдельном
        // родительском wrap, который остался бы на месте пока круг летит к drop-зоне.
        return `<div class="bubble"
          data-uid="${esc(w.user_id)}" data-name="${esc(w.name)}"
          style="width:${size}px;height:${size}px;opacity:${opacity};${glow}
            animation:bubbleFloat ${dur}s ease-in-out ${delay}s infinite alternate;
            left:${10 + ((i * 73) % 75)}%;top:${15 + ((i * 41) % 45)}%;"
          title="${esc(w.name)}">
          <span class="bubble-avatar">${esc(_makeAvatarText(w.name))}</span>
          ${matched ? '<span class="bubble-glow-ring"></span>' : ''}
          <span class="bubble-name-label">${esc(w.name.split(' ')[0])}</span>
        </div>`;
      }).join('')}
    </div>
  `;
  document.body.appendChild(panel);
  _bubblePanel = panel;
  _bubbleMode = 'assign';
  _bubbleWorkers = workers;

  // Attach pointer drag events -- сохраняем handler-ссылку на элементе, чтобы можно
  // было снять/вернуть при переключении режима без пересоздания разметки.
  panel.querySelectorAll('.bubble').forEach(el => {
    el.addEventListener('pointerdown', _bubbleDragStart, { passive: false });
  });

  panel.querySelectorAll('#bubble-mode-switch [data-bubble-mode]').forEach(opt => {
    opt.addEventListener('click', () => _setBubbleMode(opt.dataset.bubbleMode));
  });
}

let _bubbleMode = 'assign';
let _bubbleWorkers = [];

async function _setBubbleMode(mode) {
  if (_bubbleMode === mode) return;
  _bubbleMode = mode;
  const panel = _bubblePanel;
  if (!panel) return;

  panel.querySelectorAll('#bubble-mode-switch [data-bubble-mode]').forEach(opt => {
    opt.classList.toggle('active', opt.dataset.bubbleMode === mode);
  });
  const hint = document.getElementById('bubble-panel-hint');
  const dropZone = document.getElementById('bubble-drop-zone');

  if (mode === 'view') {
    if (hint) hint.textContent = 'Занятость команды на эту неделю — тап/перетаскивание отключены';
    if (dropZone) dropZone.style.display = 'none';
    panel.querySelectorAll('.bubble').forEach(el => {
      el.removeEventListener('pointerdown', _bubbleDragStart);
      el.style.cursor = 'default';
      el.style.touchAction = 'auto';
    });
    await _loadBubbleOccupancyThisWeek();
  } else {
    if (hint) hint.textContent = 'Перетащите работника на зону этапа или просто тапните по нему';
    if (dropZone) dropZone.style.display = '';
    panel.querySelectorAll('.bubble').forEach(el => {
      el.addEventListener('pointerdown', _bubbleDragStart, { passive: false });
      el.style.cursor = 'grab';
      el.style.touchAction = 'none';
      el.classList.remove('bubble-busy', 'bubble-free');
      el.querySelector('.bubble-occupancy-label')?.remove();
    });
  }
}

// 28.07: занятость на ТЕКУЩУЮ неделю -- проще и достаточно для "посмотреть картину",
// не привязано к датам этапа (те выбираются только ПОСЛЕ тапа на работника, в
// confirm-попапе, недоступны на этом экране панели вообще).
function _currentWeekDates() {
  const now = new Date();
  const day = (now.getDay() + 6) % 7; // ISO: понедельник = 0
  const monday = new Date(now);
  monday.setDate(now.getDate() - day);
  const dates = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    dates.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
  }
  return dates;
}

async function _loadBubbleOccupancyThisWeek() {
  const weekDates = _currentWeekDates();
  const monthsNeeded = new Set(weekDates.map(d => d.slice(0, 7))); // "YYYY-MM", неделя может пересекать границу месяца

  await Promise.all(_bubbleWorkers.map(async w => {
    const el = _bubblePanel?.querySelector(`.bubble[data-uid="${w.user_id}"]`);
    if (!el) return;
    let busyDates = new Set();
    try {
      for (const monthKey of monthsNeeded) {
        const [y, m] = monthKey.split('-').map(Number);
        const data = await api(`/api/workers/${w.user_id}/calendar?year=${y}&month=${m}`);
        (data.unavailable_dates || []).forEach(d => busyDates.add(d));
        (data.assigned_dates || []).forEach(d => busyDates.add(d));
      }
    } catch (e) {
      return; // тихо -- один упавший запрос не должен ломать всю картину занятости
    }
    const busyDaysThisWeek = weekDates.filter(d => busyDates.has(d)).length;
    const isBusy = busyDaysThisWeek > 0;
    el.classList.toggle('bubble-busy', isBusy);
    el.classList.toggle('bubble-free', !isBusy);
    const label = document.createElement('span');
    label.className = 'bubble-occupancy-label';
    label.textContent = isBusy ? `занят ${busyDaysThisWeek}/7` : 'свободен';
    el.appendChild(label);
  }));
}

function _closeBubblePanel() {
  if (_bubblePanel) { _bubblePanel.remove(); _bubblePanel = null; }
  _closeBubbleConfirmPopup();
  _bubbleDragEl = null;
}

// Список видов работ — зеркалит SKILL_OPTIONS в main.py (профиль/онбординг).
const BUBBLE_STAGE_OPTIONS = [
  "Штукатурка", "Малярные работы", "Электрика", "Кровля", "Фасад",
  "Сантехника", "Плитка", "Демонтаж", "Гипсокартон (сухая стройка)",
  "Стяжка пола / бетонные работы", "Утепление / изоляция", "Каменная кладка",
  "Столярные / плотницкие работы", "Сварочные работы", "Отопление / вентиляция",
  "Ландшафт / благоустройство территории", "Малярные работы фасада",
  "Монтаж окон и дверей", "Кровельная жесть / водостоки", "Строительные леса",
];

let _bubbleConfirmPopup = null;
let _bubbleConfirmDragEl = null;

function _openBubbleConfirmPopup(dragEl) {
  _bubbleConfirmDragEl = dragEl;
  dragEl.style.display = 'none'; // прячем bubble в арене на время попапа

  const currentStage = _bubbleStage || '';
  const popup = document.createElement('div');
  popup.id = 'bubble-confirm-popup';
  popup.innerHTML = `
    <div class="bubble-confirm-inner">
      <div class="bubble-confirm-title">Назначить ${esc(dragEl.dataset.name)}</div>
      <label class="bubble-confirm-label">Вид работ</label>
      <select id="bubble-confirm-stage" class="bubble-confirm-select">
        ${BUBBLE_STAGE_OPTIONS.map(s => `<option value="${esc(s)}" ${s === currentStage ? 'selected' : ''}>${esc(s)}</option>`).join('')}
      </select>
      <label class="bubble-confirm-label">Период (необязательно)</label>
      <div class="bubble-confirm-dates">
        <input type="date" id="bubble-confirm-from" class="bubble-confirm-date">
        <span>—</span>
        <input type="date" id="bubble-confirm-to" class="bubble-confirm-date">
      </div>
      <div class="bubble-confirm-actions">
        <button class="bubble-confirm-cancel" id="bubble-confirm-cancel-btn">Отмена</button>
        <button class="bubble-confirm-ok" id="bubble-confirm-ok-btn">Назначить</button>
      </div>
    </div>`;
  document.body.appendChild(popup);
  _bubbleConfirmPopup = popup;

  document.getElementById('bubble-confirm-cancel-btn').addEventListener('click', () => {
    _closeBubbleConfirmPopup();
    _returnBubbleToArena(dragEl);
  });
  document.getElementById('bubble-confirm-ok-btn').addEventListener('click', _confirmBubbleAssign);
}

function _closeBubbleConfirmPopup() {
  if (_bubbleConfirmPopup) { _bubbleConfirmPopup.remove(); _bubbleConfirmPopup = null; }
}

function _returnBubbleToArena(dragEl) {
  dragEl.style.display = '';
  dragEl.style.transform = '';
  dragEl.style.animation = '';
  dragEl.style.animationPlayState = '';
  dragEl.style.position = '';
  dragEl.style.left = '';
  dragEl.style.top = '';
  dragEl.style.zIndex = '';
}

// ═══════════ Назначить на объект -- entry point из профиля работника (25.07) ═══════════
// Обратный поток к drag-and-drop: тут уже известен работник, выбирается объект (select,
// не drag-зона -- на этом экране нет карты объектов чтобы перетаскивать). Переиспользует
// тот же confirm-flow/тот же POST /api/objects/{id}/assign, что и bubble-drag путь.
async function openAssignFromProfile(userId, userName) {
  let objects = [];
  try {
    const data = await api('/api/objects');
    objects = (data.objects || []).filter(o => (o['Статус'] || '') !== 'Завершён');
  } catch (e) {
    showToast('Не удалось загрузить объекты: ' + e.message, 'error');
    return;
  }
  if (!objects.length) {
    showToast('Нет доступных объектов', 'error');
    return;
  }

  const popup = document.createElement('div');
  popup.id = 'bubble-confirm-popup';
  popup.innerHTML = `
    <div class="bubble-confirm-inner">
      <div class="bubble-confirm-title">Назначить ${esc(userName)} на объект</div>
      <label class="bubble-confirm-label">Объект</label>
      <select id="assign-profile-object" class="bubble-confirm-select">
        ${objects.map(o => `<option value="${esc(o['ID объекта'])}">${esc(o['Объект'])}</option>`).join('')}
      </select>
      <label class="bubble-confirm-label">Вид работ</label>
      <select id="bubble-confirm-stage" class="bubble-confirm-select">
        ${BUBBLE_STAGE_OPTIONS.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('')}
      </select>
      <label class="bubble-confirm-label">Период (необязательно)</label>
      <div class="bubble-confirm-dates">
        <input type="date" id="bubble-confirm-from" class="bubble-confirm-date">
        <span>—</span>
        <input type="date" id="bubble-confirm-to" class="bubble-confirm-date">
      </div>
      <div class="bubble-confirm-actions">
        <button class="bubble-confirm-cancel" id="bubble-confirm-cancel-btn">Отмена</button>
        <button class="bubble-confirm-ok" id="assign-profile-ok-btn">Назначить</button>
      </div>
    </div>`;
  document.body.appendChild(popup);
  _bubbleConfirmPopup = popup;

  document.getElementById('bubble-confirm-cancel-btn').addEventListener('click', _closeBubbleConfirmPopup);
  document.getElementById('assign-profile-ok-btn').addEventListener('click', async () => {
    const objectId = document.getElementById('assign-profile-object').value;
    const stageId = document.getElementById('bubble-confirm-stage').value;
    const dateFrom = document.getElementById('bubble-confirm-from').value;
    const dateTo = document.getElementById('bubble-confirm-to').value;
    const okBtn = document.getElementById('assign-profile-ok-btn');
    okBtn.disabled = true;
    okBtn.textContent = 'Назначаю…';
    try {
      await api(`/api/objects/${objectId}/assign`, {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, stage_id: stageId, date_from: dateFrom, date_to: dateTo })
      });
      hapticImpact('medium');
      showToast('Назначено', 'success');
      _closeBubbleConfirmPopup();
    } catch (err) {
      showToast('Ошибка назначения: ' + err.message, 'error');
      okBtn.disabled = false;
      okBtn.textContent = 'Назначить';
    }
  });
}


async function _confirmBubbleAssign() {
  const dragEl = _bubbleConfirmDragEl;
  if (!dragEl || !_bubbleObjectId) return;
  const stageId = document.getElementById('bubble-confirm-stage').value;
  const dateFrom = document.getElementById('bubble-confirm-from').value;
  const dateTo = document.getElementById('bubble-confirm-to').value;
  const userId = dragEl.dataset.uid;

  const okBtn = document.getElementById('bubble-confirm-ok-btn');
  okBtn.disabled = true;
  okBtn.textContent = 'Назначаю…';
  try {
    await api(`/api/objects/${_bubbleObjectId}/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, stage_id: stageId, date_from: dateFrom, date_to: dateTo })
    });
    hapticImpact('medium');
    _closeBubbleConfirmPopup();
    _closeBubblePanel();
    // 28.07: owner request -- undo-после-назначения. unassign_user endpoint уже
    // существовал (owner использует его для явного снятия воркера), просто не был
    // подключён к этому конкретному success-пути. Action-toast с окном 6 сек --
    // назначение УЖЕ физически произошло на сервере, undo это отдельный DELETE-вызов,
    // не отмена ещё не отправленного действия.
    _showBubbleUndoToast(_bubbleObjectId, userId);
    if (typeof initObjectsView === 'function' && document.getElementById('view-objects')?.classList.contains('active')) {
      loadedViews.delete('objects');
      initObjectsView();
    }
  } catch (err) {
    showToast('Ошибка назначения: ' + err.message, 'error');
    okBtn.disabled = false;
    okBtn.textContent = 'Назначить';
  }
}

function _bubbleDragStart(e) {
  e.preventDefault();
  _bubbleDragEl = e.currentTarget;
  const rect = _bubbleDragEl.getBoundingClientRect();
  _bubbleDragOffX = e.clientX - rect.left;
  _bubbleDragOffY = e.clientY - rect.top;
  _bubbleDragStartX = e.clientX;
  _bubbleDragStartY = e.clientY;
  _bubbleDragMoved = false;
  _bubbleDragEl.style.position = 'fixed';
  _bubbleDragEl.style.zIndex = '9999';
  _bubbleDragEl.style.animationPlayState = 'paused';
  _bubbleDragEl.style.transition = 'transform 0.1s';
  _bubbleDragEl.setPointerCapture(e.pointerId);
  _bubbleDragEl.addEventListener('pointermove', _bubbleDragMove, { passive: false });
  _bubbleDragEl.addEventListener('pointerup', _bubbleDragEnd);
}

function _bubbleDragMove(e) {
  if (!_bubbleDragEl) return;
  e.preventDefault();
  if (Math.abs(e.clientX - _bubbleDragStartX) > BUBBLE_TAP_THRESHOLD_PX || Math.abs(e.clientY - _bubbleDragStartY) > BUBBLE_TAP_THRESHOLD_PX) {
    _bubbleDragMoved = true;
  }
  _bubbleDragEl.style.left = (e.clientX - _bubbleDragOffX) + 'px';
  _bubbleDragEl.style.top = (e.clientY - _bubbleDragOffY) + 'px';

  // Visual highlight of drop zone
  const dropZone = document.getElementById('bubble-drop-zone');
  if (dropZone) {
    const dz = dropZone.getBoundingClientRect();
    const over = e.clientX >= dz.left && e.clientX <= dz.right && e.clientY >= dz.top && e.clientY <= dz.bottom;
    dropZone.classList.toggle('bubble-drop-zone-active', over);
  }
}

async function _bubbleDragEnd(e) {
  if (!_bubbleDragEl) return;
  _bubbleDragEl.removeEventListener('pointermove', _bubbleDragMove);
  _bubbleDragEl.removeEventListener('pointerup', _bubbleDragEnd);

  // 28.07 (Phase 05, "Drag — не единственный способ"): панель всегда открыта для ОДНОГО
  // конкретного этапа (нет выбора зоны при тапе) -- тап без значимого движения однозначно
  // эквивалентен перетаскиванию в единственную drop-зону, ведёт в тот же confirm-popup.
  if (!_bubbleDragMoved) {
    const tappedEl = _bubbleDragEl;
    _bubbleDragEl = null;
    if (_bubbleObjectId) {
      _openBubbleConfirmPopup(tappedEl);
    } else {
      _returnBubbleToArena(tappedEl);
    }
    return;
  }

  const dropZone = document.getElementById('bubble-drop-zone');
  let dropped = false;
  if (dropZone) {
    const dz = dropZone.getBoundingClientRect();
    dropped = e.clientX >= dz.left && e.clientX <= dz.right && e.clientY >= dz.top && e.clientY <= dz.bottom;
    dropZone.classList.remove('bubble-drop-zone-active');
  }

  if (dropped && _bubbleObjectId) {
    _openBubbleConfirmPopup(_bubbleDragEl);
  } else {
    // Return to arena
    _bubbleDragEl.style.position = '';
    _bubbleDragEl.style.left = '';
    _bubbleDragEl.style.top = '';
    _bubbleDragEl.style.zIndex = '';
    _bubbleDragEl.style.animationPlayState = '';
  }
  _bubbleDragEl = null;
}

function _showBubbleUndoToast(objectId, userId) {
  const existing = document.getElementById('bubble-undo-toast');
  if (existing) existing.remove();
  const el = document.createElement('div');
  el.id = 'bubble-undo-toast';
  el.className = 'bubble-undo-toast';
  el.innerHTML = `<span>Работник назначен</span><button type="button" id="bubble-undo-btn">Отменить</button>`;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add('bubble-undo-toast-show'));
  const timer = setTimeout(() => el.remove(), 6000);
  document.getElementById('bubble-undo-btn').addEventListener('click', async () => {
    clearTimeout(timer);
    el.remove();
    try {
      await api(`/api/objects/${objectId}/assign/${userId}`, { method: 'DELETE' });
      hapticImpact('light');
      showToast('Назначение отменено', 'success');
      if (typeof initObjectsView === 'function' && document.getElementById('view-objects')?.classList.contains('active')) {
        loadedViews.delete('objects');
        initObjectsView();
      }
    } catch (err) {
      showToast('Не удалось отменить: ' + err.message, 'error');
    }
  });
}
