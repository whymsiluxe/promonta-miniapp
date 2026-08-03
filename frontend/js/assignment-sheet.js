// Единый Assignment Sheet -- заменяет отдельные независимые интерфейсы назначения
// (старый bubble-drag flow в bubble-assign.js, отдельная форма из профиля Worker).
// Все точки входа открывают ОДИН этот компонент:
//   - Объект → Инфо → Команда и смены → + Добавить (openAssignmentSheet({objectId, objectName}))
//   - кнопка добавления Worker на карточке объекта (openBubbleAssign -- сохранён как
//     тонкая обёртка над openAssignmentSheet для обратной совместимости вызывающего кода)
//   - назначение из профиля Worker (openAssignFromProfile -- то же самое, тонкая обёртка)
//
// 01.08: единый источник данных (/api/work-types, /api/assignment-candidates),
// единый submit (POST /api/objects/{id}/assignments/batch), единая бизнес-логика --
// не оставляем отдельные списки работ и отдельные submit-функции в разных файлах
// (спека п.6).

let _asState = null; // текущее состояние открытого sheet, null если закрыт

/**
 * openAssignmentSheet(opts)
 *   opts.objectId, opts.objectName -- режим "из объекта" (object_id уже известен)
 *   opts.userId, opts.userName -- режим "из профиля Worker" (user_id уже известен)
 *   Ровно один из двух режимов должен быть передан.
 */
async function openAssignmentSheet(opts = {}) {
  if (_asState) return; // уже открыт
  _asState = {
    mode: opts.objectId ? 'from_object' : 'from_worker',
    objectId: opts.objectId || '',
    objectName: opts.objectName || '',
    userIds: opts.userId ? [String(opts.userId)] : [],
    userNames: opts.userId ? { [String(opts.userId)]: opts.userName || '' } : {},
    workTypeId: '',
    workTypeName: '',
    dateFrom: '',
    dateTo: '',
    taskNote: '',
    step: _asState_initialStep(opts),
  };
  _asRender();
}

function _asState_initialStep(opts) {
  // из объекта -- ещё нет ни вида работ, ни периода, ни работников: начинаем с работы.
  // из профиля -- user уже известен, но нужен объект: начинаем тоже с работы
  // (объект выбирается на том же экране, что и вид работ -- проще один экран, чем два).
  return 'work_type';
}

function _asClose() {
  document.getElementById('assignment-sheet-overlay')?.remove();
  document.body.style.overflow = '';
  _asUnregisterOverlay?.();
  _asUnregisterOverlay = null;
  _asState = null;
}

let _asUnregisterOverlay = null;

function _asRender() {
  let existing = document.getElementById('assignment-sheet-overlay');
  if (!existing) {
    existing = document.createElement('div');
    existing.id = 'assignment-sheet-overlay';
    existing.className = 'bottom-sheet-overlay open';
    document.body.appendChild(existing);
    document.body.style.overflow = 'hidden';
    if (typeof NavigationManager !== 'undefined') {
      _asUnregisterOverlay = NavigationManager.registerOverlay(_asClose);
    }
  }
  const step = _asState.step;
  let bodyHtml = '';
  if (step === 'work_type') bodyHtml = _asWorkTypeStepHtml();
  else if (step === 'period') bodyHtml = _asPeriodStepHtml();
  else if (step === 'workers') bodyHtml = _asWorkersStepHtml();
  else if (step === 'task_note') bodyHtml = _asTaskNoteStepHtml();
  else if (step === 'confirm') bodyHtml = _asConfirmStepHtml();

  existing.innerHTML = `
    <div class="bottom-sheet-panel assignment-sheet-panel">
      <div class="bottom-sheet-handle"></div>
      <div class="form-header">
        <span>Назначение</span>
        <button type="button" class="obj-stage-add-sheet-close" id="as-close-btn">✕</button>
      </div>
      <div class="assignment-sheet-body" id="as-body">${bodyHtml}</div>
    </div>
  `;
  document.getElementById('as-close-btn').addEventListener('click', _asClose);
  _asBindStepHandlers(step);
}

// ---------- Шаг: вид работ ----------
function _asWorkTypeStepHtml() {
  return `
    <div id="as-worktype-picker"></div>
    <div class="form-submit-bar">
      <button type="button" class="submit-btn" id="as-worktype-next" disabled>Продолжить</button>
    </div>
  `;
}

async function _asBindWorkTypeStep() {
  const container = document.getElementById('as-worktype-picker');
  const nextBtn = document.getElementById('as-worktype-next');
  let selectedId = _asState.workTypeId;
  // 03.08: singleSelect -- Assignment Sheet выбирает ОДИН вид работ на назначение.
  // Раньше это имитировалось вручную (selected.clear()+picker.destroy()+пересоздание
  // на каждый второй тап), теперь встроенный режим picker'а.
  await createSkillPicker(container, {
    initialSelected: selectedId ? new Set([selectedId]) : new Set(),
    singleSelect: true,
    onChange: (selected) => {
      selectedId = Array.from(selected)[0] || '';
      nextBtn.disabled = !selectedId;
    },
  });
  nextBtn.disabled = !selectedId;
  nextBtn.addEventListener('click', async () => {
    if (!selectedId) return;
    _asState.workTypeId = selectedId;
    try {
      const catalog = await api('/api/work-types');
      const all = [...catalog.featured, ...catalog.groups.flatMap(g => g.items)];
      const found = all.find(w => w.id === selectedId);
      _asState.workTypeName = found ? found.name : selectedId;
    } catch (e) { /* оставляем как есть */ }
    _asState.step = _asState.mode === 'from_object' ? 'period' : 'period';
    _asRender();
  });
}

// ---------- Шаг: период ----------
function _asPeriodStepHtml() {
  return `
    <div class="assignment-sheet-quick-dates">
      <button type="button" class="as-quick-date-btn" data-quick="today">Сегодня</button>
      <button type="button" class="as-quick-date-btn" data-quick="tomorrow">Завтра</button>
      <button type="button" class="as-quick-date-btn" data-quick="custom">Выбрать период</button>
    </div>
    <div class="assignment-sheet-date-inputs" id="as-date-inputs" style="display:none">
      <label>С <input type="date" id="as-date-from"></label>
      <label>По <input type="date" id="as-date-to"></label>
    </div>
    <div class="assignment-sheet-period-summary" id="as-period-summary"></div>
    <div class="assignment-sheet-error" id="as-period-error" style="display:none"></div>
    <div class="form-submit-bar">
      <button type="button" class="submit-btn" id="as-period-next" disabled>Продолжить</button>
    </div>
  `;
}

// 01.08 (доп.раунд П7): вынесено в shared.js как todayBerlin()/tomorrowBerlin() --
// единая точка для всего frontend, не дублировать логику по файлам.

function _asBindPeriodStep() {
  const inputsWrap = document.getElementById('as-date-inputs');
  const fromInput = document.getElementById('as-date-from');
  const toInput = document.getElementById('as-date-to');
  const summaryEl = document.getElementById('as-period-summary');
  const errEl = document.getElementById('as-period-error');
  const nextBtn = document.getElementById('as-period-next');

  function updateSummary() {
    if (_asState.dateFrom && _asState.dateTo) {
      summaryEl.textContent = _asState.dateFrom === _asState.dateTo
        ? `Период: ${_asState.dateFrom}`
        : `Период: ${_asState.dateFrom} — ${_asState.dateTo}`;
      nextBtn.disabled = false;
    } else {
      summaryEl.textContent = '';
      nextBtn.disabled = true;
    }
  }

  document.querySelectorAll('.as-quick-date-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.as-quick-date-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      const quick = btn.dataset.quick;
      if (quick === 'today') {
        const t = todayBerlin();
        _asState.dateFrom = t; _asState.dateTo = t;
        inputsWrap.style.display = 'none';
        errEl.style.display = 'none';
      } else if (quick === 'tomorrow') {
        const t = tomorrowBerlin();
        _asState.dateFrom = t; _asState.dateTo = t;
        inputsWrap.style.display = 'none';
        errEl.style.display = 'none';
      } else {
        inputsWrap.style.display = 'flex';
        fromInput.value = _asState.dateFrom || '';
        toInput.value = _asState.dateTo || '';
      }
      updateSummary();
    });
  });

  const onCustomChange = () => {
    errEl.style.display = 'none';
    _asState.dateFrom = fromInput.value;
    _asState.dateTo = toInput.value;
    if (_asState.dateFrom && _asState.dateTo && _asState.dateFrom > _asState.dateTo) {
      errEl.textContent = 'Дата начала не может быть позже даты окончания';
      errEl.style.display = 'block';
      nextBtn.disabled = true;
      return;
    }
    updateSummary();
  };
  fromInput.addEventListener('change', onCustomChange);
  toInput.addEventListener('change', onCustomChange);

  updateSummary();
  nextBtn.addEventListener('click', () => {
    if (!_asState.dateFrom || !_asState.dateTo) return;
    _asState.step = 'workers';
    _asRender();
  });
}

// ---------- Шаг: работники ----------
function _asWorkersStepHtml() {
  if (_asState.mode === 'from_worker') {
    // user_id уже известен -- но нужен объект. Простой select объектов.
    return `
      <div class="assignment-sheet-object-picker" id="as-object-picker">Загрузка объектов...</div>
      <div class="form-submit-bar">
        <button type="button" class="submit-btn" id="as-workers-next" disabled>Продолжить</button>
      </div>
    `;
  }
  return `
    <div class="assignment-sheet-candidates" id="as-candidates-list">Загрузка кандидатов...</div>
    <div class="form-submit-bar">
      <button type="button" class="submit-btn" id="as-workers-next" disabled>Продолжить</button>
    </div>
  `;
}

async function _asBindWorkersStep() {
  const nextBtn = document.getElementById('as-workers-next');

  if (_asState.mode === 'from_worker') {
    const objPicker = document.getElementById('as-object-picker');
    try {
      const data = await api('/api/objects');
      // 01.08 (доп.раунд П5, реальный найденный баг): /api/objects отдаёт сырые
      // Sheets-строки (obj['Статус']/obj['ID объекта']/obj['Объект']), не
      // status/id/name -- фильтр по o.status и рендер o.id/o.name всегда были
      // undefined, отправлялся undefined как object_id. normalizeObjectDto() единая точка.
      const objects = (data.objects || []).map(normalizeObjectDto).filter(o => o.status !== 'Завершён');
      objPicker.innerHTML = `
        <select id="as-object-select" class="mangel-select">
          <option value="">Выбери объект</option>
          ${objects.map(o => `<option value="${esc(o.id)}">${esc(o.name || o.address || o.id)}</option>`).join('')}
        </select>
      `;
      const select = document.getElementById('as-object-select');
      select.addEventListener('change', () => {
        _asState.objectId = select.value;
        const opt = objects.find(o => String(o.id) === select.value);
        _asState.objectName = opt ? (opt.name || opt.address || opt.id) : '';
        nextBtn.disabled = !_asState.objectId;
      });
    } catch (e) {
      objPicker.innerHTML = `<div class="assignment-sheet-error">Не удалось загрузить объекты: ${esc(e.message)}</div>`;
    }
    nextBtn.addEventListener('click', () => {
      if (!_asState.objectId) return;
      _asState.step = 'task_note';
      _asRender();
    });
    return;
  }

  // mode === from_object -- загрузить кандидатов
  const listEl = document.getElementById('as-candidates-list');
  try {
    const params = new URLSearchParams({
      object_id: _asState.objectId, work_type_id: _asState.workTypeId,
      date_from: _asState.dateFrom, date_to: _asState.dateTo,
    });
    const data = await api(`/api/assignment-candidates?${params.toString()}`);
    const selected = new Set(_asState.userIds);

    function renderList() {
      const section = (title, items, dimmed) => items.length ? `
        <div class="assignment-sheet-candidate-section-title">${title}</div>
        ${items.map(c => `
          <label class="assignment-sheet-candidate-row${dimmed ? ' dimmed' : ''}${selected.has(c.user_id) ? ' selected' : ''}">
            <input type="checkbox" data-uid="${esc(c.user_id)}" ${selected.has(c.user_id) ? 'checked' : ''} ${dimmed ? 'disabled' : ''}>
            <span class="assignment-sheet-candidate-avatar">${c.has_avatar ? '' : (c.name || '?')[0].toUpperCase()}</span>
            <span class="assignment-sheet-candidate-name">${esc(c.name)}</span>
            ${c.skill_level ? `<span class="assignment-sheet-candidate-level">${esc(c.skill_level)}${c.skill_verified ? ' ✓' : ''}</span>` : ''}
            ${dimmed ? `<span class="assignment-sheet-candidate-reason">${esc(c.reason)}</span>` : ''}
          </label>
        `).join('')}
      ` : '';
      listEl.innerHTML =
        section('Подходят лучше всего', data.recommended, false) +
        section('Другие доступные', data.available, false) +
        section('Недоступны', data.unavailable, true);
      listEl.querySelectorAll('input[type=checkbox]:not(:disabled)').forEach(cb => {
        cb.addEventListener('change', () => {
          const uid = cb.dataset.uid;
          if (cb.checked) selected.add(uid); else selected.delete(uid);
          nextBtn.disabled = selected.size === 0;
          cb.closest('.assignment-sheet-candidate-row').classList.toggle('selected', cb.checked);
        });
      });
    }
    renderList();
    _asState._candidatesData = data; // для сводки на confirm-шаге (имена)
    nextBtn.disabled = selected.size === 0;
    nextBtn.addEventListener('click', () => {
      if (selected.size === 0) return;
      _asState.userIds = Array.from(selected);
      const all = [...data.recommended, ...data.available, ...data.unavailable];
      _asState.userNames = {};
      all.forEach(c => { _asState.userNames[c.user_id] = c.name; });
      _asState.step = 'task_note';
      _asRender();
    });
  } catch (e) {
    listEl.innerHTML = `<div class="assignment-sheet-error">Не удалось загрузить кандидатов: ${esc(e.message)}</div>`;
  }
}

// ---------- Шаг: задача (необязательно) ----------
function _asTaskNoteStepHtml() {
  return `
    <label class="assignment-sheet-tasknote-label">Что должен сделать работник? (необязательно)</label>
    <textarea id="as-tasknote-input" maxlength="500" placeholder="Собрать кухню, установить шкафы и подогнать столешницу.">${esc(_asState.taskNote)}</textarea>
    <div class="form-submit-bar">
      <button type="button" class="submit-btn" id="as-tasknote-next">Продолжить</button>
    </div>
  `;
}

function _asBindTaskNoteStep() {
  const input = document.getElementById('as-tasknote-input');
  document.getElementById('as-tasknote-next').addEventListener('click', () => {
    _asState.taskNote = input.value.trim().slice(0, 500);
    _asState.step = 'confirm';
    _asRender();
  });
}

// ---------- Шаг: подтверждение ----------
function _asConfirmStepHtml() {
  const names = _asState.userIds.map(uid => _asState.userNames[uid] || uid).join(', ');
  const periodText = _asState.dateFrom === _asState.dateTo
    ? _asState.dateFrom
    : `${_asState.dateFrom}–${_asState.dateTo}`;
  return `
    <div class="assignment-sheet-summary">
      <div><b>Объект:</b> ${esc(_asState.objectName || _asState.objectId)}</div>
      <div><b>Работа:</b> ${esc(_asState.workTypeName)}</div>
      <div><b>Период:</b> ${esc(periodText)}</div>
      <div><b>Работники:</b> ${esc(names)}</div>
      ${_asState.taskNote ? `<div><b>Задача:</b> ${esc(_asState.taskNote)}</div>` : ''}
    </div>
    <div class="assignment-sheet-error" id="as-confirm-error" style="display:none"></div>
    <div class="form-submit-bar">
      <button type="button" class="submit-btn" id="as-confirm-submit">Назначить ${_asState.userIds.length} работник${_asState.userIds.length === 1 ? 'а' : 'ов'}</button>
    </div>
  `;
}

function _asBindConfirmStep() {
  const btn = document.getElementById('as-confirm-submit');
  const errEl = document.getElementById('as-confirm-error');
  let submitting = false; // защита от двойного тапа
  btn.addEventListener('click', async () => {
    if (submitting) return;
    submitting = true;
    btn.disabled = true;
    btn.textContent = 'Назначаю...';
    try {
      const result = await api(`/api/objects/${_asState.objectId}/assignments/batch`, {
        method: 'POST',
        body: JSON.stringify({
          user_ids: _asState.userIds,
          work_type_id: _asState.workTypeId,
          date_from: _asState.dateFrom,
          date_to: _asState.dateTo,
          task_note: _asState.taskNote,
        }),
      });
      hapticImpact('light');
      if (result.skipped && result.skipped.length) {
        const skippedNames = result.skipped.map(s => _asState.userNames[s.user_id] || s.user_id).join(', ');
        showToast(`Назначено: ${result.created.length}. Пропущено (уже занят/недоступен): ${skippedNames}`, 'warn');
      } else {
        showToast('Назначение создано');
      }
      // 01.08 (доп.раунд П5, реальный найденный баг): _asClose() обнуляет _asState --
      // сохраняем objectId ДО закрытия, иначе следующая строка всегда видела
      // _asState === null и refresh никогда не вызывался. Заодно: refreshObjectDetail
      // никогда не существовал ни в одном файле проекта (мёртвый вызов, typeof-guard
      // просто тихо съедал ошибку) -- реальная функция обновления секции "Команда и
      // смены" это _renderObjTeamAndShifts() в object-info.js.
      const closedObjectId = _asState.objectId;
      _asClose();
      if (closedObjectId && typeof _renderObjTeamAndShifts === 'function') {
        _renderObjTeamAndShifts(closedObjectId);
      }
    } catch (e) {
      errEl.textContent = 'Ошибка: ' + e.message;
      errEl.style.display = 'block';
      submitting = false;
      btn.disabled = false;
      btn.textContent = `Назначить ${_asState.userIds.length} работник${_asState.userIds.length === 1 ? 'а' : 'ов'}`;
    }
  });
}

function _asBindStepHandlers(step) {
  if (step === 'work_type') _asBindWorkTypeStep();
  else if (step === 'period') _asBindPeriodStep();
  else if (step === 'workers') _asBindWorkersStep();
  else if (step === 'task_note') _asBindTaskNoteStep();
  else if (step === 'confirm') _asBindConfirmStep();
}

// ---------- Обратная совместимость: старые точки входа теперь открывают Assignment Sheet ----------
// bubble-assign.js оставлен как файл, но его bubble-drag UI больше не используется --
// эти две функции (те же имена, что вызывающий код уже знает) переопределяются здесь
// и полностью заменяют старую реализацию. Старый вызов передавал stageName (имя этапа,
// НЕ объекта) как 2-й аргумент -- Assignment Sheet сам подтягивает имя объекта из
// /api/objects по id, так что stageName больше не нужен и игнорируется.
async function openBubbleAssign(objectId, stageName, dropZoneEl) {
  let objectName = '';
  try {
    const data = await api('/api/objects');
    const obj = (data.objects || []).map(normalizeObjectDto).find(o => String(o.id) === String(objectId));
    objectName = obj ? (obj.name || obj.address || objectId) : objectId;
  } catch (e) {
    objectName = objectId;
  }
  openAssignmentSheet({ objectId, objectName });
}

function openAssignFromProfile(userId, userName, initialDate = '') {
  openAssignmentSheet({ userId, userName });
}
