// Центральная кнопка Старт/Финиш смены в worker nav (Фаза 10.14).
// Переиспользует существующий checkin-flow (checkin.js, _stagesCurrentObjectId,
// _checkinPendingAction, #checkin-photo-input) — просто даёт worker'у выбрать
// объект без захода в детейл-страницу объекта.

let _workerCheckinObjectId = null;
let _workerShiftStatusOverlayUnregister = null;
let _workerObjectPickerOverlayUnregister = null;
let _workerStagePickerOverlayUnregister = null;

function closeWorkerShiftPickers() {
  document.getElementById('worker-object-picker-modal')?.remove();
  if (_workerObjectPickerOverlayUnregister) { _workerObjectPickerOverlayUnregister(); _workerObjectPickerOverlayUnregister = null; }
  document.getElementById('worker-stage-picker-modal')?.remove();
  if (_workerStagePickerOverlayUnregister) { _workerStagePickerOverlayUnregister(); _workerStagePickerOverlayUnregister = null; }
  closeWorkerShiftStatusSheet();
}

function initWorkerCheckinFab() {
  const fab = document.getElementById('nav-checkin-btn');
  if (!fab || fab.dataset.wired) return;
  fab.dataset.wired = '1';
  fab.addEventListener('click', _workerCheckinTap);
  // 10.31: preview-modal кнопки (checkin-start-btn/finish-btn/preview-*) навешивались
  // только когда worker открывал детейл объекта (objects.js вызывает initCheckinControls) —
  // если он стартует смену через FAB, не заходя в объект, обработчики отсутствовали.
  if (typeof initCheckinControls === 'function') initCheckinControls();
  _refreshWorkerCheckinFabIcon();
}

// 22.07: FAB изначально открывал промежуточный "статус смены" экран, не сразу камеру.
// 18.09 (audit finding, Shift Flow unification #3): активная смена уже вела на реальный
// stages-view/#active-shift-panel (17.09 fix), а idle-случай всё ещё строил отдельную
// одноразовую модалку "Смена не начата" -> кнопка "Старт смены" -> и ТОЛЬКО ПОТОМ
// _openWorkerObjectPicker() -- лишний промежуточный экран без функции: Home CTA уже вёл
// в тот же picker напрямую. FAB idle-tap (и вызов из Object Detail stages-tab через
// object-info.js::_appendCheckinShortcut, тот же _openCheckinStatusScreen) теперь тоже
// идёт прямо в picker, никакой промежуточной модалки не остаётся: Home Start == FAB Start
// == Object Detail Start (все три -> _openWorkerObjectPicker()/_openStagePickerThenStart()),
// не разная длина пути к одному и тому же экрану. Имя функции сохранено (не переименовано
// в _workerCheckinTap), потому что object-info.js вызывает её напрямую по имени, не только
// через тап по FAB.
async function _workerCheckinTap() {
  if (currentRole !== 'worker') return;
  await openWorkerShiftFlow({ entryPoint: 'fab' });
}

async function _openCheckinStatusScreen() {
  await openWorkerShiftFlow({ entryPoint: 'status' });
}

async function openWorkerShiftFlow({ objectId = null, entryPoint = 'fab' } = {}) {
  const shiftState = typeof resolveWorkerShiftState === 'function'
    ? await resolveWorkerShiftState()
    : { state: null };

  if (workerShiftStateHasActiveSession?.(shiftState)) {
    await _openWorkerShiftObject(shiftState.objectId);
    return;
  }

  if (workerShiftStateIsPending?.(shiftState) || shiftState.state === WORKER_SHIFT_STATE.SYNC_ERROR) {
    openWorkerShiftStatusSheet(shiftState);
    return;
  }

  if (objectId) {
    _openStagePickerThenStart(objectId);
    return;
  }

  await _openWorkerObjectPicker();
}

// 24.07: сервер как источник истины (не localStorage — нестабилен в Telegram WebView
// между открытием разных экранов, подтверждённый живой баг: FAB показывал "активная
// смена", но stages-view той же сессии её не видел). Синхронизирует localStorage
// заодно, чтобы synchronous-читатели (_getActiveCheckinSession) не расходились.
async function _findActiveWorkerCheckinObjectId() {
  const shiftState = typeof resolveWorkerShiftState === 'function'
    ? await resolveWorkerShiftState()
    : null;
  return workerShiftStateHasActiveSession?.(shiftState) ? shiftState.objectId : null;
}

async function _openWorkerShiftObject(objectId) {
  if (!objectId) return;
  let objectName = objectId;
  try {
    const data = await api('/api/objects');
    const obj = (data.objects || []).find(o => String(o['ID объекта']) === String(objectId));
    if (obj) objectName = obj['Объект'] || objectId;
  } catch (e) {}
  switchView('objects');
  if (typeof openStagesView === 'function') openStagesView(objectId, objectName);
}

function _workerShiftStatusCopy(shiftState) {
  if (shiftState?.state === WORKER_SHIFT_STATE.START_PENDING_SYNC) {
    return {
      title: 'Начало смены ожидает синхронизации',
      body: 'Старт уже сохранён в очереди. Когда связь вернётся, он отправится автоматически.',
      action: 'Открыть объект',
    };
  }
  if (shiftState?.state === WORKER_SHIFT_STATE.FINISH_PENDING_SYNC) {
    return {
      title: 'Завершение смены ожидает синхронизации',
      body: 'Финиш уже сохранён в очереди. Повторно завершать смену не нужно.',
      action: 'Открыть объект',
    };
  }
  return {
    title: 'Нужна ручная синхронизация',
    body: shiftState?.error || 'Последняя отправка не прошла. Можно запустить повтор вручную.',
    action: 'Повторить',
  };
}

function closeWorkerShiftStatusSheet() {
  const modal = document.getElementById('worker-shift-status-modal');
  if (modal) modal.remove();
  if (_workerShiftStatusOverlayUnregister) {
    _workerShiftStatusOverlayUnregister();
    _workerShiftStatusOverlayUnregister = null;
  }
}

function _closeWorkerShiftStatusSheetInternal() {
  document.getElementById('worker-shift-status-modal')?.remove();
  _workerShiftStatusOverlayUnregister = null;
}

function openWorkerShiftStatusSheet(shiftState) {
  closeWorkerShiftStatusSheet();
  const copy = _workerShiftStatusCopy(shiftState);
  const canRetry = shiftState?.state === WORKER_SHIFT_STATE.SYNC_ERROR && shiftState.outboxRecord?.id;
  const modal = document.createElement('div');
  modal.id = 'worker-shift-status-modal';
  modal.dataset.noSwipe = '1';
  modal.innerHTML = `
    <div class="worker-picker-inner">
      <div class="worker-picker-header">
        <span class="worker-picker-title">${esc(copy.title)}</span>
        <button class="worker-picker-close" data-shift-status-close type="button">✕</button>
      </div>
      <div class="worker-picker-list">
        <div class="worker-picker-item" style="display:block;">
          <span class="worker-picker-item-stage">${esc(copy.body)}</span>
        </div>
      </div>
      <div class="worker-picker-add-row">
        <button class="form-submit-btn" data-shift-status-primary type="button">${esc(copy.action)}</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  modal.querySelector('[data-shift-status-close]')?.addEventListener('click', closeWorkerShiftStatusSheet);
  modal.querySelector('[data-shift-status-primary]')?.addEventListener('click', async () => {
    if (canRetry) {
      await promontaOutboxManualRetry(shiftState.outboxRecord.id);
      if (shiftState.outboxRecord.kind === WORKER_SHIFT_OUTBOX_KIND_FINISH && typeof _retryFinishOutboxRecords === 'function') {
        await _retryFinishOutboxRecords();
      } else if (typeof _retryCheckinOutbox === 'function') {
        await _retryCheckinOutbox();
      }
      closeWorkerShiftStatusSheet();
      showToast('Повтор синхронизации запущен', 'success');
      await _refreshWorkerCheckinFabIcon();
      if (typeof _loadWorkerShiftCta === 'function' && document.getElementById('worker-shift-cta')) _loadWorkerShiftCta();
      return;
    }
    closeWorkerShiftStatusSheet();
    if (shiftState?.objectId) await _openWorkerShiftObject(shiftState.objectId);
  });
  if (typeof NavigationManager !== 'undefined') {
    _workerShiftStatusOverlayUnregister = NavigationManager.registerOverlay(() => _closeWorkerShiftStatusSheetInternal());
  }
}

async function _openWorkerObjectPicker() {
  let objects = [];
  try {
    const data = await api('/api/objects');
    objects = (data.objects || []).filter(o =>
      (o.assigned_users || []).some(u => String(u.user_id) === String(currentUserId))
    );
  } catch (e) {
    showToast('Не удалось загрузить объекты: ' + e.message, 'error');
    return;
  }

  if (!objects.length) {
    showToast('Нет назначенных объектов. Обратитесь к руководителю.', 'error');
    return;
  }

  if (objects.length === 1) {
    _openStagePickerThenStart(objects[0]['ID объекта']);
    return;
  }

  const modal = document.createElement('div');
  modal.id = 'worker-object-picker-modal';
  modal.dataset.noSwipe = '1';
  modal.innerHTML = `
    <div class="worker-picker-inner">
      <div class="worker-picker-header">
        <span class="worker-picker-title">Выберите объект</span>
        <button class="worker-picker-close" data-object-picker-close type="button">✕</button>
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
  const _closeObjectPicker = () => {
    modal.remove();
    if (_workerObjectPickerOverlayUnregister) { _workerObjectPickerOverlayUnregister(); _workerObjectPickerOverlayUnregister = null; }
  };
  modal.querySelector('[data-object-picker-close]')?.addEventListener('click', _closeObjectPicker);
  modal.querySelectorAll('.worker-picker-item').forEach(item => {
    item.addEventListener('click', () => {
      _closeObjectPicker();
      _openStagePickerThenStart(item.dataset.oid);
    });
  });
  if (typeof NavigationManager !== 'undefined') {
    _workerObjectPickerOverlayUnregister = NavigationManager.registerOverlay(_closeObjectPicker);
  }
}

// 27.07: перед стартом смены worker явно указывает, над каким этапом объекта
// работает сегодня (опционально -- если этапов нет или запрос не удался, просто
// стартуем без stage_name, не блокируем смену из-за второстепенного поля).
async function _openStagePickerThenStart(objectId) {
  let stages = [];
  try {
    const data = await api(`/api/objects/${objectId}/stages`);
    stages = data.stages || [];
  } catch (e) { /* тихо -- отсутствие этапов не должно блокировать старт смены */ }

  // 28.07: owner request -- picker показывается ВСЕГДА (не только если уже есть этапы),
  // чтобы можно было добавить первый этап на объекте с чистого листа тоже, не только
  // выбрать существующий.
  _renderStagePickerModal(objectId, stages);
}

// 28.07: owner request -- добавление нового этапа прямо из picker'а (не только выбор
// существующего), внизу списка. Отдельная функция, чтобы после создания этапа можно
// было перерисовать тот же picker с обновлённым списком без дублирования разметки.
function _renderStagePickerModal(objectId, stages) {
  const existing = document.getElementById('worker-stage-picker-modal');
  const isFirstRender = !existing;
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'worker-stage-picker-modal';
  modal.dataset.noSwipe = '1';
  modal.innerHTML = `
    <div class="worker-picker-inner">
      <div class="worker-picker-header">
        <span class="worker-picker-title">Какой этап сегодня?</span>
        <button class="worker-picker-close" data-stage-skip type="button">Пропустить</button>
      </div>
      <div class="worker-picker-list">
        ${stages.map(s => `
          <div class="worker-picker-item" data-stage-name="${esc(s['Название этапа'] || '')}">
            <span class="worker-picker-item-name">${esc(s['Название этапа'] || '')}</span>
            <span class="worker-picker-item-stage">${esc(s['Статус'] || '')}</span>
          </div>
        `).join('')}
      </div>
      <div class="worker-picker-add-row">
        <input type="text" class="mangel-select" id="worker-picker-new-stage-name" placeholder="напр. Фасад, Стяжка пола">
        <button class="form-submit-btn" id="worker-picker-add-stage-btn" type="button">+ Добавить этап</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  const _closeStagePicker = () => {
    modal.remove();
    if (_workerStagePickerOverlayUnregister) { _workerStagePickerOverlayUnregister(); _workerStagePickerOverlayUnregister = null; }
  };
  modal.querySelector('[data-stage-skip]').addEventListener('click', () => {
    _closeStagePicker();
    _startWorkerCheckin(objectId, null);
  });
  modal.querySelectorAll('.worker-picker-item').forEach(item => {
    item.addEventListener('click', () => {
      _closeStagePicker();
      _startWorkerCheckin(objectId, item.dataset.stageName);
    });
  });
  if (isFirstRender && typeof NavigationManager !== 'undefined') {
    _workerStagePickerOverlayUnregister = NavigationManager.registerOverlay(_closeStagePicker);
  }
  modal.querySelector('#worker-picker-add-stage-btn').addEventListener('click', async () => {
    const input = modal.querySelector('#worker-picker-new-stage-name');
    const name = input.value.trim();
    if (!name) return;
    try {
      await api(`/api/objects/${objectId}/stages`, { method: 'POST', body: JSON.stringify({ name }) });
      const data = await api(`/api/objects/${objectId}/stages`);
      _renderStagePickerModal(objectId, data.stages || []);
      hapticImpact('light');
    } catch (e) {
      showToast('Не удалось добавить этап: ' + e.message, 'error');
    }
  });
}

function _startWorkerCheckin(objectId, stageName) {
  _stagesCurrentObjectId = objectId;
  _checkinPendingAction = 'start';
  _checkinSelectedStageName = stageName || null;
  document.getElementById('checkin-photo-input').click();
}

async function _refreshWorkerCheckinFabIcon() {
  const icon = document.getElementById('nav-start-fab-icon');
  const fab = document.getElementById('nav-start-fab');
  if (!icon || !fab) return;
  const shiftState = typeof resolveWorkerShiftState === 'function'
    ? await resolveWorkerShiftState()
    : null;
  const active = workerShiftStateHasActiveSession?.(shiftState);
  const pending = workerShiftStateIsPending?.(shiftState);
  icon.textContent = pending ? '…' : (active ? '■' : '▶');
  fab.classList.toggle('active-session', !!active || !!pending);
}

// checkin.js вызывает refreshCheckinButtons() после успешного старта/финиша —
// синхронизируем иконку центральной кнопки тем же хуком.
//
// 24.07: БАГ — "const _origRefreshCheckinButtons = ... refreshCheckinButtons ..." читалось
// как "захватить оригинал ИЗ checkin.js", но function-декларации хоистятся целиком (с телом)
// в начало исполнения файла. К моменту выполнения этой строки глобальный refreshCheckinButtons
// УЖЕ был переписан на хоистнутую версию ИЗ ЭТОГО ЖЕ файла (объявленную чуть ниже как
// "async function refreshCheckinButtons()") — _origRefreshCheckinButtons ссылалась сама на себя.
// Результат: await _origRefreshCheckinButtons() внутри обёртки вызывал саму обёртку —
// бесконечная рекурсия без условия выхода, каждый виток дополнительно бил
// GET /api/checkin через _refreshWorkerCheckinFabIcon() (подтверждено живым логом: 2500+
// запросов/мин на один клиент, воспроизведено в изоляции — стектрейс показал цепочку
// refreshCheckinButtons → refreshCheckinButtons → refreshCheckinButtons...).
// Фикс: обёртка здесь больше НЕ объявлена как "function refreshCheckinButtons" (что
// хоистилось бы под тем же именем и снова себя перезаписывало) — она объявлена под
// другим именем (_refreshCheckinButtonsWithFabIcon), поэтому строка ниже, читающая
// глобальный refreshCheckinButtons, гарантированно видит ещё не тронутый оригинал
// из checkin.js. Глобальная refreshCheckinButtons переопределяется ПОСЛЕ, обычным
// присваиванием (не декларацией) — присваивания не хоистятся, порядок исполнения
// строго сверху вниз.
const _origRefreshCheckinButtons = typeof refreshCheckinButtons === 'function' ? refreshCheckinButtons : null;
async function _refreshCheckinButtonsWithFabIcon() {
  // Оригинал трогает #checkin-start-btn/#checkin-finish-btn из stages-view — они существуют,
  // только если worker уже открывал детейл объекта. Если он стартовал смену через FAB,
  // не заходя в объект, эти элементы отсутствуют — оригинал должен молча пропустить это, не упасть.
  if (_origRefreshCheckinButtons) {
    try { await _origRefreshCheckinButtons(); } catch (e) {}
  }
  await _refreshWorkerCheckinFabIcon();
}
// Переопределяем глобальную refreshCheckinButtons ПОСЛЕ того как оригинал уже захвачен
// в замыкание выше — присваивание (не декларация) не хоистится, поэтому порядок здесь
// гарантирован и не может повторить тот же баг.
refreshCheckinButtons = _refreshCheckinButtonsWithFabIcon;
