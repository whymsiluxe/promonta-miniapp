// Worker UX V2, Этап 6 — contextual quick actions: Фото, Потребность, Дефект, Чат.
// Живёт в Today/Active Shift/Object как общая группа, не отдельная Camera tab
// (центр bottom-nav занят Shift FAB, Chat уже top-level).
//
// Context resolution (план, "без молчаливого прикрепления к неоднозначному объекту"):
//   1. active shift object (resolveWorkerShiftState)
//   2. current Object Detail object (_stagesCurrentObjectId, objects.js)
//   3. single eligible assignment (ровно один назначенный объект)
//   4. иначе — object picker (переиспользует worker-checkin-fab.js's picker)
//
// Каждое действие вызывает уже существующий canonical flow -- не строит вторую
// реализацию форм Потребности/Дефекта/Фото/Чата.

// 21.09 (P0, owner review finding): _stagesCurrentObjectId (objects.js) is
// set by openStagesView() but never cleared by closeStagesView() -- it stays
// set to whatever object the worker last looked at, indefinitely. A worker
// who opened OBJECT-A's stages, left, and later tapped a quick action from
// Today with no active shift would get silently attributed to OBJECT-A
// again, even though they're nowhere near that screen anymore. The real
// signal for "is Object Detail actually the current screen" is the
// stages-view DOM element's own 'open' class (same pattern objects.js itself
// already uses elsewhere, see the stagesViewOpen check in loadObjects()),
// not the stale variable's mere existence.
function _workerActionCurrentObjectDetailId() {
  const stagesView = document.getElementById('stages-view');
  if (!stagesView || !stagesView.classList.contains('open')) return null;
  if (typeof _stagesCurrentObjectId === 'undefined' || !_stagesCurrentObjectId) return null;
  return _stagesCurrentObjectId;
}

async function resolveWorkerActionObject() {
  try {
    const shiftState = typeof resolveWorkerShiftState === 'function'
      ? await resolveWorkerShiftState()
      : null;
    if (shiftState && typeof workerShiftStateHasActiveSession === 'function'
      && workerShiftStateHasActiveSession(shiftState) && shiftState.objectId) {
      return { objectId: String(shiftState.objectId), source: 'active_shift' };
    }
  } catch (e) {}

  const detailObjectId = _workerActionCurrentObjectDetailId();
  if (detailObjectId) {
    return { objectId: String(detailObjectId), source: 'object_detail' };
  }

  try {
    const data = await api('/api/objects');
    const eligible = (data.objects || []).filter(o =>
      (o.assigned_users || []).some(u => String(u.user_id) === String(currentUserId)));
    if (eligible.length === 1) {
      const id = eligible[0]['ID объекта'];
      return { objectId: String(id), source: 'single_assignment' };
    }
  } catch (e) {}

  return { objectId: null, source: 'ambiguous' };
}

// Общая точка входа: резолвит объект, затем либо сразу выполняет action(objectId),
// либо (source === 'ambiguous') открывает picker и ждёт выбора.
//
// Не переиспользует _openWorkerObjectPicker() (worker-checkin-fab.js) -- та функция
// жёстко ведёт к _openStagePickerThenStart() (shift-start flow), не принимает
// произвольный callback. Тот же markup/CSS-паттерн (.worker-picker-*), свой callback.
async function runWorkerQuickAction(action) {
  const ctx = await resolveWorkerActionObject();
  if (ctx.objectId) {
    action(ctx.objectId);
    return;
  }
  await _openWorkerQuickActionObjectPicker(action);
}

let _workerQuickActionPickerOverlayUnregister = null;

async function _openWorkerQuickActionObjectPicker(action) {
  let objects = [];
  try {
    const data = await api('/api/objects');
    objects = (data.objects || []).filter(o =>
      (o.assigned_users || []).some(u => String(u.user_id) === String(currentUserId)));
  } catch (e) {
    showToast('Не удалось загрузить объекты: ' + e.message, 'error');
    return;
  }

  if (!objects.length) {
    showToast('Нет назначенных объектов. Обратитесь к руководителю.', 'error');
    return;
  }

  const modal = document.createElement('div');
  modal.id = 'worker-quick-action-picker-modal';
  modal.dataset.noSwipe = '1';
  modal.innerHTML = `
    <div class="worker-picker-inner">
      <div class="worker-picker-header">
        <span class="worker-picker-title">Выберите объект</span>
        <button class="worker-picker-close" data-qa-picker-close type="button">✕</button>
      </div>
      <div class="worker-picker-list">
        ${objects.map(o => `
          <div class="worker-picker-item" data-oid="${esc(o['ID объекта'])}">
            <span class="worker-picker-item-name">${esc(o['Объект'] || o['ID объекта'])}</span>
            <span class="worker-picker-item-stage">${esc(o['Текущий этап'] || '')}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  const _closePicker = () => {
    modal.remove();
    if (_workerQuickActionPickerOverlayUnregister) { _workerQuickActionPickerOverlayUnregister(); _workerQuickActionPickerOverlayUnregister = null; }
  };
  modal.querySelector('[data-qa-picker-close]')?.addEventListener('click', _closePicker);
  modal.querySelectorAll('.worker-picker-item').forEach(item => {
    item.addEventListener('click', () => {
      _closePicker();
      action(item.dataset.oid);
    });
  });
  if (typeof NavigationManager !== 'undefined') {
    _workerQuickActionPickerOverlayUnregister = NavigationManager.registerOverlay(_closePicker);
  }
}

// ── Фото ── переиспользует существующий /api/feed/photos + _uploadFeedPhoto
// (feed.js), но с привязкой к разрешённому объекту через FormData object_id
// (backend уже принимал это поле, _uploadFeedPhoto его никогда не передавал).
function _workerQuickActionPhoto() {
  runWorkerQuickAction((objectId) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.capture = 'environment';
    input.style.display = 'none';
    document.body.appendChild(input);
    input.addEventListener('change', () => {
      if (input.files && input.files.length && typeof _uploadFeedPhoto === 'function') {
        _uploadFeedPhoto(Array.from(input.files), objectId);
      }
      input.remove();
    }, { once: true });
    input.click();
  });
}

// ── Потребность ── переиспользует существующий view-tasks форму (tasks.js),
// не дублирует создание/валидацию/отправку.
function _workerQuickActionNeed() {
  runWorkerQuickAction(async (objectId) => {
    switchView('tasks');
    if (typeof _populateTasksObjectSelect === 'function') await _populateTasksObjectSelect();
    const select = document.getElementById('tasks-object-select');
    if (select) select.value = objectId;
    document.getElementById('tasks-new-btn')?.click();
  });
}

// ── Дефект ── переиспользует существующий view-mangel форму (mangel.js).
function _workerQuickActionDefect() {
  runWorkerQuickAction(async (objectId) => {
    switchView('mangel');
    if (typeof _populateMangelObjectSelect === 'function') await _populateMangelObjectSelect();
    const select = document.getElementById('mangel-object-select');
    if (select) select.value = objectId;
    if (typeof _openMangelForm === 'function') _openMangelForm();
  });
}

// ── Чат ── переиспользует существующий object-chat open path (тот же, что
// используется из stages-view "Чат объекта" -- не новый канал/поток).
function _workerQuickActionChat() {
  runWorkerQuickAction(async (objectId) => {
    let title = objectId;
    try {
      const data = await api('/api/objects');
      const obj = (data.objects || []).find(o => String(o['ID объекта']) === String(objectId));
      if (obj) title = obj['Объект'] || objectId;
    } catch (e) {}
    if (typeof openObjectOrMangelChat === 'function') {
      openObjectOrMangelChat(`obj:${objectId}`, `Чат: ${title}`, 'objects');
    } else {
      switchView('chat');
    }
  });
}
