// Центральная кнопка Старт/Финиш смены в worker nav (Фаза 10.14).
// Переиспользует существующий checkin-flow (checkin.js, _stagesCurrentObjectId,
// _checkinPendingAction, #checkin-photo-input) — просто даёт worker'у выбрать
// объект без захода в детейл-страницу объекта.

let _workerCheckinObjectId = null;

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

  const closeBtn = document.getElementById('checkin-status-close-btn');
  if (closeBtn) closeBtn.addEventListener('click', () => {
    document.getElementById('checkin-status-modal').style.display = 'none';
  });
}

// 22.07: FAB теперь открывает промежуточный экран (статус смены + крупные кнопки
// Старт/Финиш), не сразу камеру — юзер попросил "отдельную вкладку" для check-in,
// без добавления 6-го таба в bottom-nav (принятое IA-решение — 5 табов).
async function _workerCheckinTap() {
  if (currentRole !== 'worker') return;
  await _openCheckinStatusScreen();
}

async function _openCheckinStatusScreen() {
  const activeObjectId = await _findActiveWorkerCheckinObjectId();
  const modal = document.getElementById('checkin-status-modal');
  const body = document.getElementById('checkin-status-body');
  if (!modal || !body) return;

  if (activeObjectId) {
    let objectName = activeObjectId;
    try {
      const data = await api('/api/objects');
      const obj = (data.objects || []).find(o => o['ID объекта'] === activeObjectId);
      if (obj) objectName = obj['Объект'] || activeObjectId;
    } catch (e) {}
    body.innerHTML = `
      <div class="checkin-status-active">
        <div class="checkin-status-label">Смена идёт</div>
        <div class="checkin-status-object">${esc(objectName)}</div>
      </div>
      <button class="submit-btn checkin-status-btn" style="background:var(--red)" id="checkin-status-finish-btn">■ Финиш смены</button>
    `;
    document.getElementById('checkin-status-finish-btn').addEventListener('click', () => {
      modal.style.display = 'none';
      _stagesCurrentObjectId = activeObjectId;
      _checkinPendingAction = 'finish';
      document.getElementById('checkin-photo-input').click();
    });
  } else {
    body.innerHTML = `
      <div class="checkin-status-active">
        <div class="checkin-status-label">Смена не начата</div>
      </div>
      <button class="submit-btn checkin-status-btn" id="checkin-status-start-btn">▶ Старт смены</button>
    `;
    document.getElementById('checkin-status-start-btn').addEventListener('click', async () => {
      modal.style.display = 'none';
      await _openWorkerObjectPicker();
    });
  }
  modal.style.display = 'flex';
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
    _startWorkerCheckin(objects[0]['ID объекта']);
    return;
  }

  const modal = document.createElement('div');
  modal.id = 'worker-object-picker-modal';
  modal.innerHTML = `
    <div class="worker-picker-inner">
      <div class="worker-picker-header">
        <span class="worker-picker-title">Выберите объект</span>
        <button class="worker-picker-close" onclick="document.getElementById('worker-object-picker-modal').remove()">✕</button>
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
  modal.querySelectorAll('.worker-picker-item').forEach(item => {
    item.addEventListener('click', () => {
      modal.remove();
      _startWorkerCheckin(item.dataset.oid);
    });
  });
}

function _startWorkerCheckin(objectId) {
  _stagesCurrentObjectId = objectId;
  _checkinPendingAction = 'start';
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
