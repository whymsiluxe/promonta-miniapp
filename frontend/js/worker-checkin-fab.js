// Центральная кнопка Старт/Финиш смены в worker nav (Фаза 10.14).
// Переиспользует существующий checkin-flow (checkin.js, _stagesCurrentObjectId,
// _checkinPendingAction, #checkin-photo-input) — просто даёт worker'у выбрать
// объект без захода в детейл-страницу объекта.

let _workerCheckinObjectId = null;

// 18.09 (audit finding): neither picker was registered with NavigationManager,
// so Telegram BackButton/hardware-back didn't know to close the picker first --
// same class of bug already fixed elsewhere via registerOverlay() (see
// object-info.js's _openAddStageSheet). One unregister-holder per modal;
// cleared whenever that modal closes through ANY path (✕/item click/skip/
// tab-switch), never left dangling for a second open to silently double-up.
let _workerObjectPickerUnregisterOverlay = null;
let _workerStagePickerUnregisterOverlay = null;

function closeWorkerShiftPickers() {
  document.getElementById('worker-object-picker-modal')?.remove();
  document.getElementById('worker-stage-picker-modal')?.remove();
  if (_workerObjectPickerUnregisterOverlay) { _workerObjectPickerUnregisterOverlay(); _workerObjectPickerUnregisterOverlay = null; }
  if (_workerStagePickerUnregisterOverlay) { _workerStagePickerUnregisterOverlay(); _workerStagePickerUnregisterOverlay = null; }
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
  await _openCheckinStatusScreen();
}

async function _openCheckinStatusScreen() {
  const activeObjectId = await _findActiveWorkerCheckinObjectId();
  if (activeObjectId) {
    let objectName = activeObjectId;
    try {
      const data = await api('/api/objects');
      const obj = (data.objects || []).find(o => o['ID объекта'] === activeObjectId);
      if (obj) objectName = obj['Объект'] || activeObjectId;
    } catch (e) {}
    switchView('objects');
    if (typeof openStagesView === 'function') openStagesView(activeObjectId, objectName);
    return;
  }
  await _openWorkerObjectPicker();
}

// 24.07: сервер как источник истины (не localStorage — нестабилен в Telegram WebView
// между открытием разных экранов, подтверждённый живой баг: FAB показывал "активная
// смена", но stages-view той же сессии её не видел). Синхронизирует localStorage
// заодно, чтобы synchronous-читатели (_getActiveCheckinSession) не расходились.
async function _findActiveWorkerCheckinObjectId() {
  try {
    const data = await api('/api/checkin');
    // 24.07: не фильтровать по дате — сервер (Europe/Berlin) и клиент (UTC) расходятся
    // на границе полуночи CEST, ложно скрывая только что открытую смену. "Открыта"
    // определяется исключительно finish_at.
    const open = (data.sessions || []).find(s => s.finish_at === null || s.finish_at === undefined);
    if (open) {
      _setActiveCheckinSession(open.object_id, { id: open.id, finished: false });
      return open.object_id;
    }
    return null;
  } catch (e) {
    // сеть недоступна — локальный fallback, лучше устаревший статус чем никакой
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key || !key.startsWith('checkin_session_')) continue;
      try {
        const session = JSON.parse(localStorage.getItem(key));
        if (session && !session.finished) {
          return key.replace('checkin_session_', '');
        }
      } catch (e2) {}
    }
    return null;
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
        <button class="worker-picker-close" id="worker-object-picker-close-btn">✕</button>
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

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    modal.remove();
    if (_workerObjectPickerUnregisterOverlay) { _workerObjectPickerUnregisterOverlay(); _workerObjectPickerUnregisterOverlay = null; }
  };
  if (typeof NavigationManager !== 'undefined') {
    _workerObjectPickerUnregisterOverlay = NavigationManager.registerOverlay(close);
  }

  modal.querySelector('#worker-object-picker-close-btn').addEventListener('click', close);
  modal.querySelectorAll('.worker-picker-item').forEach(item => {
    item.addEventListener('click', () => {
      close();
      _openStagePickerThenStart(item.dataset.oid);
    });
  });
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
// 18.09 (audit finding): registerOverlay() only on the FIRST render, not on every
// re-render after adding a stage -- re-rendering removes+recreates the DOM node but
// must keep the SAME overlay-stack entry, otherwise re-registering on every add-stage
// submit would pile up duplicate Back-stack entries. The registered close callback
// looks up #worker-stage-picker-modal BY ID each time it runs (not a closure over the
// specific `modal` element created THIS render) -- otherwise a Telegram Back press
// after a re-render would call a stale close() bound to an already-removed element and
// silently do nothing visible while still unregistering the overlay.
function _renderStagePickerModal(objectId, stages) {
  const isFirstOpen = !_workerStagePickerUnregisterOverlay;
  const existing = document.getElementById('worker-stage-picker-modal');
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

  const close = () => {
    document.getElementById('worker-stage-picker-modal')?.remove();
    if (_workerStagePickerUnregisterOverlay) { _workerStagePickerUnregisterOverlay(); _workerStagePickerUnregisterOverlay = null; }
  };
  if (isFirstOpen && typeof NavigationManager !== 'undefined') {
    _workerStagePickerUnregisterOverlay = NavigationManager.registerOverlay(close);
  }

  modal.querySelector('[data-stage-skip]').addEventListener('click', () => {
    close();
    _startWorkerCheckin(objectId, null);
  });
  modal.querySelectorAll('.worker-picker-item').forEach(item => {
    item.addEventListener('click', () => {
      close();
      _startWorkerCheckin(objectId, item.dataset.stageName);
    });
  });
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
  const active = await _findActiveWorkerCheckinObjectId();
  icon.textContent = active ? '■' : '▶';
  fab.classList.toggle('active-session', !!active);
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
