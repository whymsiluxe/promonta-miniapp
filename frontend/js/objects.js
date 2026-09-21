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
  // Раунд 4: жара приоритетнее кода погоды -- при tmax>=30 показываем Жарко/Сильная/Экстремальная.
  const heatLabel = (typeof weatherHeatLabel === 'function') ? weatherHeatLabel(today.tmax) : null;
  const heatKind = (typeof weatherHeatKind === 'function') ? weatherHeatKind(today.tmax) : null;
  const cond = heatLabel || (code >= 61 ? 'Дождь' : code >= 45 ? 'Туман' : code >= 2 ? 'Облачно' : 'Ясно');
  const heatCls = heatKind ? ` obj-weather-island-${heatKind}` : '';
  return `<div class="obj-weather-island${heatCls}"><b>${tmax}°C</b><span>${cond}</span></div>`;
}

// Раунд 4: понятный блок этапов вместо цепочки ✓●○→. Заголовок + счётчик + progress
// bar + % + Сейчас/Далее. Состояния: есть current / ничего не начато / всё готово /
// нет этапов / приостановлено (blocker в stage_summary, если данные есть).
function _objStageBlockHtml(obj, oid) {
  const summary = obj.stage_summary;
  const objName = esc(obj['Объект']) || '';
  const attrs = `data-object-id="${oid}" data-object-name="${objName}"`;
  if (!summary || !summary.total) {
    return `<div class="obj-stage-block stage-clickable" ${attrs} role="button" tabindex="0" aria-label="Открыть план работ">
      <div class="obj-stage-head"><span class="obj-stage-title">Этапы</span></div>
      <div class="obj-stage-empty">План работ не создан</div>
    </div>`;
  }
  const total = summary.total;
  const done = summary.completed_count || 0;
  const pct = Math.round(done / total * 100);
  const allDone = done >= total;

  let lines;
  if (summary.blocker) {
    lines = `<div class="obj-stage-line"><span class="obj-stage-line-label">Приостановлено:</span> ${esc(summary.blocker)}</div>`;
  } else if (allDone) {
    lines = `<div class="obj-stage-line obj-stage-line-done">Все работы завершены</div>`;
  } else if (summary.current) {
    const next = summary.next
      ? `<div class="obj-stage-line"><span class="obj-stage-line-label">Далее:</span> ${esc(summary.next)}</div>` : '';
    lines = `<div class="obj-stage-line"><span class="obj-stage-line-label">Сейчас:</span> ${esc(summary.current)}</div>${next}`;
  } else {
    // Ничего не начато -- показываем следующий (первый незавершённый) этап.
    lines = `<div class="obj-stage-line"><span class="obj-stage-line-label">Следующий:</span> ${esc(summary.next || '—')}</div>`;
  }

  return `<div class="obj-stage-block stage-clickable" ${attrs} role="button" tabindex="0" aria-label="Открыть план работ">
    <div class="obj-stage-head">
      <span class="obj-stage-title">Этапы</span>
      <span class="obj-stage-count">${done} из ${total}</span>
    </div>
    <div class="obj-stage-progrow">
      <div class="obj-stage-bar"><div class="obj-stage-bar-fill" style="width:${pct}%"></div></div>
      <span class="obj-stage-pct">${pct}%</span>
    </div>
    ${lines}
  </div>`;
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
  // 28.07 v2: расширено до carousel из нескольких фото (PHASE F спека) -- если owner
  // загрузил хотя бы одно реальное фото, рендерим slide-слои + dots (свайп/тап), иначе
  // fallback остаётся единственным статичным слоем без dots (нет смысла крутить одно
  // и то же stock-фото).
  // 28.07 v3 (fix, real bug found by ChatGPT audit): protected endpoint requires
  // X-Telegram-Init-Data header -- a plain CSS background:url() can never send it,
  // so every uploaded photo silently 401'd and rendered nothing. Slides now render
  // empty with a data-auth-object-photo URL; _loadAuthObjectPhotos() (below) fetches
  // each one with the auth header via the existing authBgImage() helper and sets the
  // background only once the blob is actually available.
  const photoCount = obj.photo_count || 0;
  const heroSlidesHtml = photoCount > 0
    ? Array.from({ length: photoCount }, (_, i) =>
        `<div class="obj-hero-slide${i === 0 ? ' active' : ''}" data-auth-object-photo="/api/objects/${encodeURIComponent(oid)}/image/file?index=${i}"></div>`
      ).join('')
    : `<div class="obj-hero-slide active" style="background:url('/media/objects/${hero.photo}.jpg') center/cover no-repeat"></div>`;
  const heroDotsHtml = photoCount > 1
    ? `<div class="obj-hero-dots">${Array.from({ length: photoCount }, (_, i) => `<span class="obj-hero-dot${i === 0 ? ' active' : ''}" data-slide-idx="${i}"></span>`).join('')}</div>`
    : '';

  // Worker avatars -- overlap-композиция снизу-слева (первый крупнее), макс 3 + "+N".
  // 28.07 (ТЗ п.21): реальное фото профиля вместо только инициалов, если work загрузил
  // avatar (has_avatar с backend). Инициалы остаются как fallback -- видны сразу, фото
  // подгружается асинхронно поверх через session-level Blob URL кэш (_avatarBlobCache,
  // см. attachObjectsHandlers) -- один и тот же работник назначен на несколько объектов
  // не должен грузить свою аватарку заново на каждой карточке.
  const assignedUsers = obj.assigned_users || [];
  const visibleUsers = assignedUsers.slice(0, 3);
  const peopleDots = visibleUsers.map((u, i) => {
    const initials = (u.name || '?').split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase();
    const size = i === 0 ? 56 : 46;
    const avatarAttr = u.has_avatar ? `data-auth-avatar="${esc(u.user_id)}"` : '';
    return `<div class="obj-people-dot${i === 0 ? ' obj-people-dot-first' : ''}" ${avatarAttr} style="width:${size}px;height:${size}px;margin-left:${i > 0 ? '-14px' : '0'};z-index:${5 - i}" title="${esc(u.name)}" onclick="event.stopPropagation();openUserCard('${u.user_id}')">${esc(initials)}</div>`;
  }).join('');
  // "+N" открывает Object Detail (полный список команды -- отдельный team-sheet
  // не строим, это редкий edge case при 4+ работниках на одном объекте).
  const extraDots = assignedUsers.length > 3
    ? `<div class="obj-people-dot obj-people-more obj-extra-dots-btn" data-object-id="${esc(oid)}" data-object-name="${esc(obj['Объект']||'')}" style="margin-left:-14px;">+${assignedUsers.length - 3}</div>` : '';
  // 04.08 (Раунд 2): настоящая <button> вместо div -- отдельный touch target,
  // не сливается с аватарами (нет margin-left:-14px, свой z-index), человек-с-плюсом
  // SVG вместо голого "+", вызывает единый openAssignmentSheet (см. attachObjectsHandlers).
  // objectName передаём из obj -- не делаем лишний GET /api/objects ради имени.
  const addBtn = currentRole === 'owner'
    ? `<button type="button" class="obj-add-worker-btn" data-object-id="${esc(oid)}" data-object-name="${esc(obj['Объект']||oid)}" aria-label="Добавить работника" title="Добавить работника"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3"></circle><path d="M3.5 19c.8-3.4 3-5 5.5-5s4.7 1.6 5.5 5"></path><path d="M18 7v6M15 10h6"></path></svg></button>` : '';

  const startDateLabel = _objStartDateLabel(obj);
  const mapsUrl = obj['Адрес'] ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(obj['Адрес'])}` : '';

  const stagesStripHtml = _objStageBlockHtml(obj, oid);

  return `
  <div class="card obj-card-v2" data-id="${oid}" data-status="${esc(obj['Статус'] || '')}">
    <div class="obj-card-hero">
      <div class="obj-hero-slides" data-photo-count="${photoCount}">${heroSlidesHtml}</div>
      ${heroDotsHtml}
      ${_objWeatherIslandHtml(obj)}
      <div class="obj-hero-people">${peopleDots}${extraDots}${addBtn}</div>
      <div class="obj-hero-status-pill" style="--pill-accent:${statusMeta.color}">${esc(statusMeta.label)}</div>
    </div>
    <div class="obj-card-body">
      <div class="obj-card-title">${esc(obj['Объект']) || ''}</div>
      <div class="obj-card-address obj-address-link" data-url="${esc(mapsUrl)}">
        <svg class="obj-address-pin" viewBox="0 0 24 24" width="14" height="14" fill="none"><path d="M12 2C7.58 2 4 5.58 4 10c0 5.25 7 12 8 12s8-6.75 8-12c0-4.42-3.58-8-8-8z" fill="currentColor"/><circle cx="12" cy="10" r="2.5" fill="var(--bg-card)"/></svg>
        ${esc(obj['Адрес']) || 'Адрес не указан'}
      </div>
      ${startDateLabel ? `<div class="obj-card-startdate">${esc(startDateLabel)}</div>` : ''}
    </div>
    ${stagesStripHtml}
    ${currentRole === 'owner' ? `
    <div class="metrics">
      <div class="metric">
        <div class="metric-row"><span>Бюджет использован</span><b style="color:${bColor}">${budgetPct}%</b></div>
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

async function loadObjectWorkTasks(objectId, listEl, countEl) {
  // 31.07 (UX-аудит): было -- список выглядел пустым/сломанным пока запрос в
  // полёте, не отличить от "Задач нет".
  listEl.innerHTML = '<div style="padding:0.3rem 0;color:var(--text-light);font-size:0.85rem">Загрузка…</div>';
  try {
    const data = await api(`/api/objects/${objectId}/tasks`);
    if (!data.tasks.length) {
      listEl.innerHTML = '<div style="padding:0.3rem 0;color:var(--text-light);font-size:0.85rem">Задач нет</div>';
    } else {
      listEl.innerHTML = data.tasks.map(renderTaskRow).join('');
    }
    if (countEl) countEl.textContent = `(${data.tasks.length})`;
    attachTaskHandlers(listEl, objectId, countEl);
  } catch (e) {
    listEl.innerHTML = `<div style="padding:0.3rem 0;color:var(--red);font-size:0.85rem">Ошибка: ${esc(e.message)}</div>`;
  }
}

// Item 8 fix: countEl is now passed through explicitly instead of re-derived
// via listEl.closest('.card').querySelector('.tasks-count') -- that lookup
// assumed a '.card' ancestor that only exists in the Objects-list context.
// Object Info's tasks section (object-info.js) wraps this same list in a bare
// <div>, so .closest('.card') returned null and .querySelector on it crashed
// with "null is not an object (evaluating 'card.querySelector')".
function attachTaskHandlers(listEl, objectId, countEl) {
  listEl.querySelectorAll('.checkbox:not(.disabled)').forEach(box => {
    box.addEventListener('click', async () => {
      const taskId = box.closest('.task-row').dataset.taskId;
      box.classList.add('disabled');
      try {
        await api(`/api/tasks/${taskId}/complete`, { method: 'PATCH' });
        await loadObjectWorkTasks(objectId, listEl, countEl);
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

// 28.07 v3: lazy-load + auth для carousel-фото (см. heroSlidesHtml комментарий выше).
// Один IntersectionObserver на все карточки -- не пересоздаём его на каждый рендер,
// disconnect предыдущего перед новым, чтобы не копить наблюдателей на устаревших DOM-узлах.
let _objPhotoObserver = null;

function _loadAuthObjectPhoto(el) {
  const url = el.dataset.authObjectPhoto;
  if (!url || el.dataset.authLoaded) return;
  el.dataset.authLoaded = '1'; // не грузить второй раз, даже если IntersectionObserver сработает повторно
  el.classList.add('obj-hero-slide-loading');
  authBgImage(el, url).then(() => {
    el.classList.remove('obj-hero-slide-loading');
    if (!el.style.backgroundImage) {
      // authBgImage тихо глотает ошибку (catch пустой) -- если backgroundImage не
      // выставился, значит fetch/decode упал; помечаем состояние явно вместо пустого
      // чёрного hero.
      el.classList.add('obj-hero-slide-error');
    }
  });
}

// 28.07 (ТЗ п.21): session-level кэш userId -> Blob URL для worker-аватарок на карточках
// объектов. Один и тот же работник может быть назначен на несколько объектов -- без
// кэша каждая карточка грузила бы его фото заново. Кэш живёт на весь сеанс приложения
// (не revoke при обычном re-render списка объектов), только реальный upload новой
// аватарки инвалидирует конкретную запись (см. profile.js avatar upload flow -- вне
// скоупа этой правки, аватарки на карточках объекта обновятся при следующей полной
// перезагрузке приложения, что приемлемо для этого некритичного визуального элемента).
const _avatarBlobCache = new Map(); // userId -> Promise<string|null> (Blob URL или null при ошибке)

function _loadAuthAvatar(el) {
  const uid = el.dataset.authAvatar;
  if (!uid) return;
  if (!_avatarBlobCache.has(uid)) {
    _avatarBlobCache.set(uid, authImageUrl(`/api/profile/${encodeURIComponent(uid)}/avatar`).catch(() => null));
  }
  _avatarBlobCache.get(uid).then(blobUrl => {
    if (!blobUrl) return; // fetch упал -- инициалы остаются как fallback, тихо
    el.style.backgroundImage = `url('${blobUrl}')`;
    el.style.backgroundSize = 'cover';
    el.style.backgroundPosition = 'center';
    el.classList.add('obj-people-dot-has-photo'); // скрывает текст инициалов через CSS, фото не перекрывается
  });
}

function _initObjPhotoLazyLoad() {
  if (_objPhotoObserver) _objPhotoObserver.disconnect();
  if (!window.IntersectionObserver) {
    // Без IntersectionObserver (маловероятно в Telegram WebView, но защитный fallback) --
    // грузим только первый (активный) слайд каждой карточки сразу, не все восемь разом.
    document.querySelectorAll('#objects-cards .obj-hero-slide.active[data-auth-object-photo]').forEach(_loadAuthObjectPhoto);
    return;
  }
  _objPhotoObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const hero = entry.target;
      const activeSlide = hero.querySelector('.obj-hero-slide.active[data-auth-object-photo]');
      if (activeSlide) _loadAuthObjectPhoto(activeSlide);
      _objPhotoObserver.unobserve(hero);
    });
  }, { rootMargin: '200px 0px' }); // немного заранее, чтобы не было видимой задержки при обычном скролле
  document.querySelectorAll('#objects-cards .obj-card-hero').forEach(hero => _objPhotoObserver.observe(hero));
}

function attachObjectsHandlers() {
  attachObjectsDragHandlers();
  _initObjPhotoLazyLoad();
  // Аватарки маленькие и немного на карточку -- грузим сразу, IntersectionObserver
  // тут был бы лишней сложностью ради небольшого выигрыша (в отличие от 8-фото carousel).
  document.querySelectorAll('#objects-cards [data-auth-avatar]').forEach(_loadAuthAvatar);

  document.querySelectorAll('#objects-cards .metric-fill').forEach(fill => {
    const target = fill.style.width;
    fill.style.width = '0%';
    requestAnimationFrame(() => requestAnimationFrame(() => fill.style.width = target));
  });

  // 03.08 (ТЗ Задача 6b): было inline onclick="...openExternalLink('${mapsUrl}')" --
  // адрес объекта интерполировался в JS-строку без экранирования кавычек, так что
  // адрес, содержащий одинарную кавычку (реальный сценарий для немецких адресов вида
  // "Bäcker's Weg"), ломал сгенерированный onclick целиком (SyntaxError в атрибуте,
  // клик молча ничего не делал). data-url + delegated listener, тот же паттерн, что
  // остальные card-level обработчики в этой функции -- значение идёт через esc() в
  // HTML-атрибут (уже безопасно для кавычек), не через JS string literal.
  document.querySelectorAll('#objects-cards .obj-address-link').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      const url = el.dataset.url;
      if (url) openExternalLink(url);
    });
  });

  document.querySelectorAll('#objects-cards .stage-clickable').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation(); // не даём всплыть до card-level клика ниже -- открылось бы дважды/на неверный таб
      openObjectDetail(el.dataset.objectId, el.dataset.objectName, 'stages', el.closest('.card')?.dataset.status);
    });
  });

  // 28.07: тап по dots переключает слайд фото-carousel, не открывает Object Detail.
  document.querySelectorAll('#objects-cards .obj-hero-dot').forEach(dot => {
    dot.addEventListener('click', (e) => {
      e.stopPropagation();
      const hero = dot.closest('.obj-card-hero');
      const idx = Number(dot.dataset.slideIdx);
      hero.querySelectorAll('.obj-hero-slide').forEach((s, i) => {
        s.classList.toggle('active', i === idx);
        if (i === idx) _loadAuthObjectPhoto(s); // 28.07: подгружаем неактивный слайд только когда реально показывается
      });
      hero.querySelectorAll('.obj-hero-dot').forEach((d, i) => d.classList.toggle('active', i === idx));
    });
  });
  // Свайп по самому фото тоже листает carousel (не только тап по dots) -- тот же
  // жест, что юзер уже ожидает от галерей/сторис. stopPropagation чтобы не триггерить
  // card-level клик (открытие Object Detail) или global tab-swipe.
  document.querySelectorAll('#objects-cards .obj-hero-slides[data-photo-count]').forEach(slidesEl => {
    const photoCount = Number(slidesEl.dataset.photoCount);
    if (photoCount < 2) return;
    let startX = 0;
    slidesEl.addEventListener('touchstart', (e) => { startX = e.touches[0].clientX; }, { passive: true });
    slidesEl.addEventListener('touchend', (e) => {
      const dx = e.changedTouches[0].clientX - startX;
      if (Math.abs(dx) < 40) return;
      const hero = slidesEl.closest('.obj-card-hero');
      const slides = Array.from(hero.querySelectorAll('.obj-hero-slide'));
      const dots = Array.from(hero.querySelectorAll('.obj-hero-dot'));
      const currentIdx = slides.findIndex(s => s.classList.contains('active'));
      const nextIdx = dx < 0
        ? Math.min(currentIdx + 1, slides.length - 1)
        : Math.max(currentIdx - 1, 0);
      slides.forEach((s, i) => {
        s.classList.toggle('active', i === nextIdx);
        if (i === nextIdx) _loadAuthObjectPhoto(s);
      });
      dots.forEach((d, i) => d.classList.toggle('active', i === nextIdx));
    }, { passive: true });
  });

  document.querySelectorAll('#objects-cards .obj-extra-dots-btn').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      openObjectDetail(el.dataset.objectId, el.dataset.objectName, 'chat');
    });
  });

  // 04.08 (Раунд 2): делегирование на контейнере вместо per-button listener --
  // loadObjects() пере-рендерит карточки и заново зовёт attachObjectsHandlers(),
  // при прямом binding это добавляло бы дубли listener'ов. dataset.bound -- guard,
  // чтобы навесить делегат ровно один раз на живой контейнер.
  const objCardsContainer = document.getElementById('objects-cards');
  if (objCardsContainer && objCardsContainer.dataset.addWorkerBound !== '1') {
    objCardsContainer.dataset.addWorkerBound = '1';
    objCardsContainer.addEventListener('click', (e) => {
      const btn = e.target.closest('.obj-add-worker-btn');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      if (typeof openAssignmentSheet !== 'function') {
        showToast('Форма назначения недоступна', 'error');
        console.error('openAssignmentSheet is not loaded');
        return;
      }
      // disabled на время открытия -- двойной тап не создаёт два sheet.
      if (btn.disabled) return;
      btn.disabled = true;
      setTimeout(() => { btn.disabled = false; }, 600);
      openAssignmentSheet({ objectId: btn.dataset.objectId, objectName: btn.dataset.objectName || btn.dataset.objectId });
    });
  }

  // 24.07: клик по всей карточке объекта -> новый 6-таб экран (было доступно только
  // через узкую строку "Текущий этап"). Исключаем интерактивные элементы внутри карточки
  // (тот же exclusion-list что у drag touchstart выше) + сам drag/long-press не должен
  // триггерить открытие -- card.dataset.wasDragged ставится в endObjectDrag().
  document.querySelectorAll('#objects-cards .card').forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.status-switch, .take-btn, .checkbox, .add-task, .tasks-label, .obj-add-worker-btn, .obj-people-add, .obj-people-more, .obj-address-link, .obj-mangel-link, .stage-clickable, .stage-edit-icon')) return;
      if (card.dataset.wasDragged === '1') { card.dataset.wasDragged = ''; return; }
      openObjectDetail(card.dataset.id, card.querySelector('.obj-card-title')?.textContent || '', 'chat', card.dataset.status);
    });
  });

}

// 28.07 (Phase 04 remainder, item 5): "Новый объект" -- управляемый bottom sheet поверх
// списка (objects-list-view больше не прячется) вместо полноэкранной формы в произвольном
// месте. Зарегистрирован в NavigationManager.overlayStack тем же паттерном, что
// photo-comments-modal в feed.js -- иначе Telegram BackButton не закроет sheet, а провалится
// на предыдущий route.
let _newObjSheetOverlayUnregister = null;

function openNewObjectView() {
  document.getElementById('new-obj-error').innerHTML = '';
  ['new-obj-name', 'new-obj-adresse', 'new-obj-budget', 'new-obj-start', 'new-obj-end'].forEach(id => {
    document.getElementById(id).value = '';
  });
  const sheet = document.getElementById('new-object-sheet');
  sheet.style.display = 'flex';
  requestAnimationFrame(() => sheet.classList.add('open'));
  if (typeof NavigationManager !== 'undefined' && !_newObjSheetOverlayUnregister) {
    _newObjSheetOverlayUnregister = NavigationManager.registerOverlay(() => _closeNewObjectViewInternal());
  }
  refreshObjectsFabVisibility();
}

// Общая анимация закрытия -- вызывается и вручную (крестик/тап по фону), и из
// NavigationManager (overlay уже popped на этот момент).
function _animateCloseNewObjectSheet() {
  const sheet = document.getElementById('new-object-sheet');
  sheet.classList.remove('open');
  setTimeout(() => { sheet.style.display = 'none'; }, 240);
  refreshObjectsFabVisibility();
}

// Вызывается ТОЛЬКО из NavigationManager (top.close()) — overlay уже popped, повторный
// unregister тут не нужен (тот же паттерн что _closePhotoCommentsInternal в feed.js).
function _closeNewObjectViewInternal() {
  _newObjSheetOverlayUnregister = null;
  _animateCloseNewObjectSheet();
}

// Вызывается при ручном закрытии (крестик/тап по фону/после submit) — overlay ещё
// в стеке, нужно явно снять, иначе следующий Back попытается закрыть уже закрытый sheet.
function closeNewObjectView() {
  if (_newObjSheetOverlayUnregister) { _newObjSheetOverlayUnregister(); _newObjSheetOverlayUnregister = null; }
  _animateCloseNewObjectSheet();
}

// 28.07 v2 (real bug found by external audit): listVisible проверял только
// #objects-list-view.style.display, но open sheet (#new-object-sheet) -- ОТДЕЛЬНЫЙ
// DOM-узел, список объектов позади него display'а не меняет. FAB оставался visible
// поверх открытой формы. Теперь проверяем явно каждое известное overlay-состояние,
// не полагаясь на один CSS-класс где-то в DOM.
function refreshObjectsFabVisibility() {
  const fab = document.getElementById('add-object');
  if (!fab) return;
  const objectsActive = document.getElementById('view-objects')?.classList.contains('active');
  const listVisible = document.getElementById('objects-list-view')?.style.display !== 'none';
  const newObjectSheetOpen = document.getElementById('new-object-sheet')?.classList.contains('open');
  const objectDetailOpen = document.getElementById('view-object-detail')?.style.display !== 'none';
  const stagesViewOpen = document.getElementById('stages-view')?.classList.contains('open');
  const keyboardOpen = document.body.classList.contains('keyboard-open');
  const fabVisible = !!(
    objectsActive && listVisible && currentRole === 'owner'
    && !newObjectSheetOpen && !objectDetailOpen && !stagesViewOpen && !keyboardOpen
  );
  fab.classList.toggle('visible', fabVisible);
  fab.setAttribute('aria-hidden', fabVisible ? 'false' : 'true');
  fab.tabIndex = fabVisible ? 0 : -1;
  if (!fabVisible && document.activeElement === fab) fab.blur();
  // 28.07: radio-mini-player перекрывал этот FAB (оба в правом углу над nav) -- сужаем
  // mini-player только пока FAB реально виден, см. `.radio-mini-player` CSS.
  document.body.classList.toggle('view-objects-active', fabVisible);
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

// 30.07 (аудит): только 3 канонических статуса, feature freeze -- review/rework
// workflow отменён. _normalizeStageStatus() сводит любые легаси/экспериментальные
// значения (готово к началу/заблокирован/на проверке/на доработке и англ. эквиваленты)
// к одному из трёх при ЧТЕНИИ -- Sheets не мигрируются массово, только отображение.
const STAGE_STATUS_LABEL = { 'предстоит': 'Предстоит', 'в процессе': 'В работе', 'готово': 'Завершён' };
const STAGE_STATUS_CYCLE = ['предстоит', 'в процессе', 'готово'];
const _STAGE_STATUS_COMPAT = {
  'не начат': 'предстоит', 'not_started': 'предстоит', 'ready': 'предстоит',
  'ready_to_start': 'предстоит', 'готово к началу': 'предстоит',
  'in_progress': 'в процессе', 'blocked': 'в процессе', 'заблокирован': 'в процессе',
  'pending_review': 'в процессе', 'review': 'в процессе', 'на проверке': 'в процессе',
  'rework': 'в процессе', 'на доработке': 'в процессе',
  'completed': 'готово', 'done': 'готово',
};
function _normalizeStageStatus(raw) {
  if (raw in STAGE_STATUS_LABEL) return raw;
  return _STAGE_STATUS_COMPAT[raw] || 'предстоит';
}
let _stagesCurrentObjectId = null;

function renderStageRow(stage) {
  const status = _normalizeStageStatus(stage['Статус'] || 'предстоит');
  const isOwner = currentRole === 'owner';
  // CSS class -- whitelist, не просто esc(): статус из Sheets, произвольный текст
  // не должен становиться частью class list. Только буквы/цифры/дефис проходят,
  // всё остальное схлопывается в один безопасный fallback-класс.
  const statusSlug = /^[a-zA-Zа-яА-Я0-9\-]+$/.test(status.replace(/\s/g, '-'))
    ? status.replace(/\s/g, '-') : 'unknown';
  return `
  <div class="stage-row" data-num="${esc(stage['№ этапа'])}">
    <div class="stage-row-name">${esc(stage['Название этапа'])}</div>
    <div class="stage-row-status stage-status-${statusSlug} stage-row-status-readonly" data-status="${esc(status)}">${esc(STAGE_STATUS_LABEL[status] || status)}</div>
    ${isOwner ? `<button class="stage-row-delete" data-num="${esc(stage['№ этапа'])}">×</button>` : ''}
  </div>`;
}

function attachStagesRowHandlers(stages) {
  if (currentRole !== 'owner') return;
  // 30.07 (feature freeze): click-to-cycle статуса убран -- этот старый экран
  // использовал прямой PATCH /stages/{row} в обход текущей логики. Статус
  // read-only здесь; реальный переход в "готово" -- только через Объект → План
  // работ (object-info.js: кнопка "Готово" + отдельный blocker badge).
  // Старый цикл оставлен закомментированным для отката, если понадобится:
  //
  // document.querySelectorAll('.stage-row-status').forEach(el => {
  //   el.addEventListener('click', async () => {
  //     const stageNum = el.closest('.stage-row').dataset.num;
  //     const rowNum = _stageRowIndexMap[stageNum];
  //     const current = el.dataset.status;
  //     const idx = STAGE_STATUS_CYCLE.indexOf(current);
  //     const next = STAGE_STATUS_CYCLE[(idx + 1) % STAGE_STATUS_CYCLE.length];
  //     try {
  //       await api(`/api/objects/${_stagesCurrentObjectId}/stages/${rowNum}`, { method: 'PATCH', body: JSON.stringify({ status: next }) });
  //       hapticImpact('light');
  //       await loadStagesWithRowNumbers();
  //     } catch (e) {
  //       showToast('Ошибка: ' + e.message, 'error');
  //     }
  //   });
  // });

  document.querySelectorAll('.stage-row-delete').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!await promontaConfirm('Удалить этап?', { danger: true })) return;
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
  refreshObjectsFabVisibility();
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
  refreshObjectsFabVisibility();
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
  document.getElementById('add-object').addEventListener('click', () => {
    if (currentRole !== 'owner') return;
    openNewObjectView();
  });
  document.getElementById('new-obj-back').addEventListener('click', closeNewObjectView);
  document.getElementById('new-object-sheet').addEventListener('click', (e) => {
    if (e.target.id === 'new-object-sheet') closeNewObjectView(); // тап по фону закрывает
  });
  document.getElementById('new-obj-submit').addEventListener('click', submitNewObject);
  document.getElementById('stages-back').addEventListener('click', closeStagesView);
  document.getElementById('add-stage-btn').addEventListener('click', addNewStage);
  initObjectsToolbar();
  refreshObjectsFabVisibility();
  loadObjects();
}


// ═══════════ Детали объекта — 6-таб экран (24.07, Step 1: shell + lazy tab init) ═══════════
// Каждая вкладка лениво инициализируется при первом открытии (тот же паттерн, что
// loadedViews в switchView() app.html) -- не грузим все 6 источников данных разом.
let _objDetailCurrentId = null;
let _objDetailCurrentName = '';
let _objDetailCurrentStatus = '';
const _objDetailLoadedTabs = new Set();

// 29.07: owner report (Symptom B) -- Objects list found squished/dimmed with body.view-locked
// stuck. Root cause: #view-object-detail is NOT a .view and was never pushed into
// NavigationManager's stack (unlike every other pushed screen) -- opened/closed only via direct
// openObjectDetail()/closeObjectDetail() calls. Telegram's native BackButton and Android
// hardware/gesture back both route through NavigationManager.back(), which had no idea Object
// Detail was open: with stack depth still 1 ('objects'), back() fell into its "at root" branch
// and called switchView('home'). switchView() DOES call unembedObjectChat() (clears view-locked,
// body.style.top, scroll restore) as its first line -- but it only ever toggles elements queried
// via document.querySelectorAll('.view'), and #view-object-detail deliberately has no .view class
// (see comment at openObjectDetail below), so it never got hidden. Net result after a hardware-back
// out of the embedded chat tab: view-locked/body.style.top were cleaned up correctly, but
// #view-object-detail (display:block, no longer chat-embedded) stayed visually stacked in front of
// whatever switchView('home') activated underneath -- consistent with the owner's screenshot of a
// dimmed/squished Objects screen sitting behind something still on top.
// Fix: register Object Detail as a NavigationManager overlay (same registerOverlay pattern already
// used for new-object-sheet/photo-comments-modal) so BackButton/hardware-back calls
// closeObjectDetail() directly instead of falling through to the "no idea this exists" branch.
let _objDetailOverlayUnregister = null;

function openObjectDetail(objectId, objectName, initialTab, objectStatus) {
  _objDetailCurrentId = objectId;
  _objDetailCurrentName = objectName || objectId;
  _objDetailCurrentStatus = objectStatus || '';
  _objDetailLoadedTabs.clear();
  document.getElementById('objects-list-view').style.display = 'none';
  refreshObjectsFabVisibility();
  const view = document.getElementById('view-object-detail');
  view.style.display = 'block';
  document.getElementById('obj-detail-title').textContent = _objDetailCurrentName;

  if (typeof NavigationManager !== 'undefined' && !_objDetailOverlayUnregister) {
    _objDetailOverlayUnregister = NavigationManager.registerOverlay(() => _closeObjectDetailInternal());
  }

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
  // 17.09 (same class of bug as Календарь -- owner report): .obj-detail-panel
  // toggles via display:none<->block, which does not reset scrollTop. Switching
  // to План работ (stages tab) after scrolling down in a previous tab (e.g.
  // Инфо) kept the stale scroll position, showing the new panel already
  // scrolled past its own header. Reset the actual scrolling ancestor -- this
  // screen's own container, not just window/document -- on every tab switch.
  const detailView = document.getElementById('view-object-detail');
  if (detailView) detailView.scrollTop = 0;
  window.scrollTo(0, 0);
  if (document.scrollingElement) document.scrollingElement.scrollTop = 0;
  _initObjDetailTab(tab);
}

// Вызывается ТОЛЬКО из NavigationManager (top.close(), т.е. BackButton/hardware-back) --
// overlay уже popped на этот момент, повторный unregister не нужен (тот же паттерн что
// _closeNewObjectViewInternal). Это путь, которого раньше не было вообще для Object Detail --
// без него hardware/gesture back проваливался в NavigationManager.back()'s root-branch,
// которая ничего не знала про #view-object-detail (см. комментарий у openObjectDetail).
function _closeObjectDetailInternal() {
  _objDetailOverlayUnregister = null;
  if (typeof unembedObjectChat === 'function') unembedObjectChat();
  document.getElementById('view-object-detail').style.display = 'none';
  document.getElementById('objects-list-view').style.display = '';
  refreshObjectsFabVisibility();
  _objDetailCurrentId = null;
  loadObjects();
}

// Вызывается при ручном закрытии (тап по #obj-detail-back) -- overlay ещё в стеке,
// нужно явно снять, иначе следующий Back попытается закрыть уже закрытый экран.
function closeObjectDetail() {
  if (_objDetailOverlayUnregister) { _objDetailOverlayUnregister(); _objDetailOverlayUnregister = null; }
  if (typeof unembedObjectChat === 'function') unembedObjectChat();
  document.getElementById('view-object-detail').style.display = 'none';
  document.getElementById('objects-list-view').style.display = '';
  refreshObjectsFabVisibility();
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
    // 29.07 v2: Инфо рендерит всю сводку (статус/описание/работы/дефекты/документы/
    // потребности) одним вызовом -- Потребности перенесены сюда из бывшей 4-й вкладки.
    Promise.resolve(renderObjectInfoTab(_objDetailCurrentId))
      .then(() => renderObjectBudgetSection(_objDetailCurrentId))
      .then(() => renderObjectTaskKanbanSection(_objDetailCurrentId))
      .then(() => renderObjectHistorySection(_objDetailCurrentId))
      .catch(e => {
        const panel = document.getElementById('obj-detail-panel-info');
        if (panel) panel.insertAdjacentHTML('beforeend', `<div class="obj-info-empty">Ошибка истории: ${esc(e.message)}</div>`);
      });
    return;
  }
  if (tab === 'stages') {
    renderObjectStagesTab(_objDetailCurrentId);
    return;
  }
  panel.innerHTML = `<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Загрузка…</div>`;
}

// ── Object Detail V2 (Этап 7, step 1) — internal zone routing layer ────────────
//
// docs/OBJECT_DETAIL_V2_IMPLEMENTATION_PLAN.md's corrected migration order: this
// architecture is added BEFORE the visible tab bar changes, not the other way
// around -- #obj-detail-tabs/_objDetailTabClick above still drive the production
// chat/info/stages UI unchanged. ZONE_RENDERERS and _renderObjectDetailZone() are
// not called from anywhere yet; they exist so the eventual "switch the visible
// tab bar to Обзор|Работа|Медиа|Чат" commit is a routing change, not a rewrite.
//
// 'work' maps to the EXISTING renderObjectStagesTab -- Работа does not get its
// own stage-list implementation, it reuses the live one (see the migration doc's
// "reuse, don't duplicate" findings for Start/Finish/stage-list). 'chat' maps to
// the existing embedObjectChat, same reasoning. 'overview' and 'media' are real
// panel containers (see app.html's obj-detail-panel-overview/-media) but have no
// content yet -- they are not populated until steps 4-5 of the migration order,
// and the tab bar switch does not happen until they do.
// Lazy-resolved (not bound directly to the function references at module-parse
// time) -- objects.js loads BEFORE object-info.js (see app.html's script order),
// so renderObjectStagesTab/embedObjectChat don't exist yet when this file itself
// is first parsed. Same defensive pattern as the rest of this codebase's
// typeof X === 'function' cross-file calls.
const ZONE_RENDERERS = {
  overview: null, // populated in migration step 5 (Обзор) -- see plan doc
  work: (objectId) => (typeof renderObjectStagesTab === 'function' ? renderObjectStagesTab(objectId) : null),
  media: null, // populated in migration step 4 (Медиа) -- see plan doc
  chat: (objectId, objectName) => (typeof embedObjectChat === 'function' ? embedObjectChat(objectId, objectName) : null),
};

function _renderObjectDetailZone(zone) {
  const renderer = ZONE_RENDERERS[zone];
  if (typeof renderer !== 'function') return;
  renderer(_objDetailCurrentId, _objDetailCurrentName);
}

function _objectHistoryTimeLabel(at) {
  if (!at) return '';
  const d = new Date(String(at).endsWith('Z') ? at : at + 'Z');
  if (Number.isNaN(d.getTime())) return '';
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function _objectHistoryKindLabel(kind) {
  const labels = {
    object_status_changed: 'Статус',
    worker_assigned: 'Команда',
    stage_status_changed: 'План',
    stage_completed: 'План',
    document_uploaded: 'Документ',
    defect_created: 'Дефект',
    finish_submitted: 'Смена',
    broadcast_sent: 'Объявление',
  };
  return labels[kind] || 'Событие';
}

function _objectBudgetAmount(raw) {
  if (raw === null || raw === undefined) return null;
  let cleaned = String(raw)
    .replace(/[^\d,.-]/g, '')
    .trim();
  const lastComma = cleaned.lastIndexOf(',');
  const lastDot = cleaned.lastIndexOf('.');
  if (lastComma >= 0 && lastDot >= 0) {
    cleaned = lastComma > lastDot
      ? cleaned.replace(/\./g, '').replace(',', '.')
      : cleaned.replace(/,/g, '');
  } else if (lastComma >= 0) {
    cleaned = cleaned.length - lastComma - 1 === 3
      ? cleaned.replace(/,/g, '')
      : cleaned.replace(',', '.');
  } else if (lastDot >= 0 && cleaned.length - lastDot - 1 === 3) {
    cleaned = cleaned.replace(/\./g, '');
  }
  const value = Number.parseFloat(cleaned);
  return Number.isFinite(value) ? value : null;
}

function _objectBudgetPercent(obj, budget, spent) {
  const keys = ['потрачено в % от бюджета', '% бюджета', 'Потрачено %'];
  for (const key of keys) {
    const value = _objectBudgetAmount(obj?.[key]);
    if (value !== null) return value;
  }
  return budget && spent !== null ? (spent / budget) * 100 : 0;
}

function _objectBudgetMoney(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value);
}

function _objectBudgetRisk(pct, budget) {
  if (!budget) return { key: 'muted', label: 'Нет бюджета' };
  if (pct >= 90) return { key: 'danger', label: 'Красный риск' };
  if (pct >= 60) return { key: 'warn', label: 'Жёлтый риск' };
  return { key: 'ok', label: 'Норма' };
}

async function _objectBudgetLoadObject(objectId) {
  const local = (_allObjects || []).find(o => String(o['ID объекта']) === String(objectId));
  if (local && Object.prototype.hasOwnProperty.call(local, 'Бюджет (EUR)')) return local;
  const data = await api('/api/objects');
  _allObjects = data.objects || [];
  return _allObjects.find(o => String(o['ID объекта']) === String(objectId)) || null;
}

async function renderObjectBudgetSection(objectId) {
  if (currentRole !== 'owner') return;
  const panel = document.getElementById('obj-detail-panel-info');
  if (!panel || !objectId) return;

  let section = document.getElementById('obj-budget-section');
  if (!section) {
    const html = `
      <div class="obj-info-section obj-budget-section" id="obj-budget-section">
        <div id="obj-budget-dashboard" class="obj-budget-dashboard">
          <div class="js-skeleton-line" style="width:68%"></div>
          <div class="js-skeleton-line" style="width:46%"></div>
        </div>
      </div>`;
    const controlSection = panel.querySelector('.obj-control-section');
    if (controlSection) controlSection.insertAdjacentHTML('afterend', html);
    else panel.insertAdjacentHTML('afterbegin', html);
    section = document.getElementById('obj-budget-section');
  }
  const dashboard = document.getElementById('obj-budget-dashboard');
  if (!dashboard) return;

  try {
    const obj = await _objectBudgetLoadObject(objectId);
    if (!obj || !Object.prototype.hasOwnProperty.call(obj, 'Бюджет (EUR)')) {
      section.remove();
      return;
    }
    const budget = _objectBudgetAmount(obj['Бюджет (EUR)']);
    const spent = _objectBudgetAmount(obj['Потрачено (EUR)']) || 0;
    const remaining = budget !== null ? budget - spent : null;
    const pct = Math.max(0, _objectBudgetPercent(obj, budget, spent));
    const risk = _objectBudgetRisk(pct, budget);
    const meterPct = Math.min(100, Math.round(pct));
    const overrun = budget && spent > budget ? spent - budget : 0;

    dashboard.innerHTML = `
      <div class="obj-budget-head">
        <div>
          <div class="obj-budget-title">Бюджет</div>
          <div class="obj-budget-sub">${budget ? `${Math.round(pct)}% использовано` : 'Бюджет не задан'}</div>
        </div>
        <span class="obj-budget-risk obj-budget-risk-${risk.key}">${esc(risk.label)}</span>
      </div>
      <div class="obj-budget-meter" aria-label="Использовано бюджета ${Math.round(pct)}%">
        <div class="obj-budget-meter-fill obj-budget-meter-${risk.key}" style="width:${meterPct}%"></div>
      </div>
      <div class="obj-budget-stats">
        <div class="obj-budget-stat"><span>Бюджет</span><b>${esc(_objectBudgetMoney(budget))}</b></div>
        <div class="obj-budget-stat"><span>Потрачено</span><b>${esc(_objectBudgetMoney(spent))}</b></div>
        <div class="obj-budget-stat"><span>${overrun ? 'Перерасход' : 'Остаток'}</span><b>${esc(_objectBudgetMoney(overrun || Math.max(0, remaining || 0)))}</b></div>
      </div>
      ${overrun ? `<div class="obj-budget-note">Превышение бюджета на ${esc(_objectBudgetMoney(overrun))}</div>` : ''}
    `;
  } catch (e) {
    dashboard.innerHTML = `<div class="obj-info-empty-row"><span>Бюджет недоступен</span><button type="button" class="obj-info-empty-action" id="obj-budget-retry">Повторить</button></div>`;
    document.getElementById('obj-budget-retry')?.addEventListener('click', () => renderObjectBudgetSection(objectId));
  }
}

function _objectTaskKanbanStage(status) {
  if (typeof taskStage === 'function') return taskStage(status);
  if (status === 'закрыто' || status === 'выдано' || status === 'отклонено') return 'done';
  if (status === 'в работе' || status === 'принято' || status === 'заказано') return 'accepted';
  return 'new';
}

function _objectTaskKanbanStatusFor(stage) {
  if (stage === 'accepted') return 'в работе';
  if (stage === 'done') return 'закрыто';
  return 'открыто';
}

function _objectTaskKanbanLabel(status) {
  return (typeof taskStatusLabel === 'function') ? taskStatusLabel(status) : (status || 'Новая');
}

function _objectTaskKanbanCategory(task) {
  return (typeof taskCategoryLabel === 'function') ? taskCategoryLabel(task.category) : (task.category || 'Другое');
}

function _objectTaskKanbanWhen(ts) {
  if (!ts) return '';
  try {
    const d = new Date(Number(ts) * 1000);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
  } catch (e) { return ''; }
}

function _objectTaskKanbanDue(task) {
  if (!task.due_at) return '';
  const overdue = _objectTaskKanbanStage(task.status) !== 'done' && Number(task.due_at) < Math.floor(Date.now() / 1000);
  const label = (typeof _taskDueLabel === 'function') ? _taskDueLabel(task.due_at) : _objectTaskKanbanWhen(task.due_at);
  return `<div class="obj-task-kanban-due${overdue ? ' obj-task-kanban-overdue' : ''}">${overdue ? 'Просрочено' : 'Срок'}: ${esc(label)}</div>`;
}

function _objectTaskKanbanCard(task) {
  const stage = _objectTaskKanbanStage(task.status);
  const isOwner = currentRole === 'owner';
  const primary = stage === 'new'
    ? { label: 'В работу', status: 'в работе' }
    : stage === 'accepted'
      ? { label: 'Готово', status: 'закрыто' }
      : { label: 'Вернуть', status: 'открыто' };
  const pillClass = stage === 'new' ? 'task-pill-new' : stage === 'accepted' ? 'task-pill-accepted' : 'task-pill-done';
  const created = _objectTaskKanbanWhen(task.created_at);
  return `
    <article class="obj-task-kanban-card" data-kanban-task-id="${esc(task.id)}" data-kanban-stage="${stage}" ${isOwner ? 'draggable="true"' : ''}>
      <div class="obj-task-kanban-card-head">
        <div class="obj-task-kanban-card-title">${esc(task.title || '')}</div>
        ${task.priority === 'срочно' ? '<span class="obj-task-kanban-urgent">Срочно</span>' : ''}
      </div>
      <div class="obj-task-kanban-meta">${esc(_objectTaskKanbanCategory(task))}${created ? ` · ${esc(created)}` : ''}</div>
      <div class="obj-task-kanban-meta">Запросил: ${esc(task.from_name || task.from_user_id || '—')}</div>
      ${_objectTaskKanbanDue(task)}
      <div class="obj-task-kanban-card-actions">
        <span class="task-status-pill ios-status-pill ${pillClass}">${esc(_objectTaskKanbanLabel(task.status))}</span>
        <div class="obj-task-kanban-card-buttons">
          ${isOwner ? `<button class="obj-task-kanban-action ios-action-button" data-kanban-set-status="${esc(primary.status)}" data-kanban-task="${esc(task.id)}" type="button">${esc(primary.label)}</button>` : ''}
          <button class="obj-task-kanban-chat ios-icon-button" data-kanban-chat="${esc(task.id)}" data-kanban-title="${esc(task.title || '')}" type="button" aria-label="Чат">
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v7A2.5 2.5 0 0 1 17.5 15H9l-5 5V5.5Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>
          </button>
        </div>
      </div>
    </article>`;
}

function _objectTaskKanbanColumn(col, tasks) {
  const cards = tasks.length
    ? tasks.map(_objectTaskKanbanCard).join('')
    : '<div class="obj-task-kanban-empty">Нет задач</div>';
  return `
    <section class="obj-task-kanban-column obj-task-kanban-column-${col.key}" data-kanban-column="${col.key}">
      <div class="obj-task-kanban-column-head">
        <span>${esc(col.title)}</span>
        <b>${tasks.length}</b>
      </div>
      <div class="obj-task-kanban-lane" data-kanban-stage="${col.key}">${cards}</div>
    </section>`;
}

async function _objectTaskKanbanSetStatus(taskId, status, objectId, btn) {
  if (btn && btn.disabled) return;
  const orig = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    await api(`/api/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify({ status }) });
    hapticImpact('light');
    await renderObjectTaskKanbanSection(objectId);
    if (typeof _refreshObjInfoNeeds === 'function') _refreshObjInfoNeeds();
    if (typeof refreshTasksBadge === 'function') refreshTasksBadge();
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
    if (btn) { btn.disabled = false; btn.textContent = orig; }
  }
}

function _attachObjectTaskKanbanHandlers(section, objectId) {
  section.querySelectorAll('[data-kanban-set-status]').forEach(btn => {
    btn.addEventListener('click', () => _objectTaskKanbanSetStatus(btn.dataset.kanbanTask, btn.dataset.kanbanSetStatus, objectId, btn));
  });
  section.querySelectorAll('[data-kanban-chat]').forEach(btn => {
    btn.addEventListener('click', () => {
      if (typeof openObjectOrMangelChat === 'function') {
        openObjectOrMangelChat(`task:${btn.dataset.kanbanChat}`, `Потребность: ${btn.dataset.kanbanTitle}`, { view: 'object-detail', objectId, taskId: btn.dataset.kanbanChat });
      }
    });
  });
  if (currentRole !== 'owner') return;

  section.querySelectorAll('.obj-task-kanban-card[draggable="true"]').forEach(card => {
    card.addEventListener('dragstart', e => {
      card.classList.add('obj-task-kanban-dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', card.dataset.kanbanTaskId);
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('obj-task-kanban-dragging');
      section.querySelectorAll('.obj-task-kanban-drop-active').forEach(el => el.classList.remove('obj-task-kanban-drop-active'));
    });
  });
  section.querySelectorAll('.obj-task-kanban-lane').forEach(lane => {
    lane.addEventListener('dragover', e => {
      e.preventDefault();
      lane.classList.add('obj-task-kanban-drop-active');
      e.dataTransfer.dropEffect = 'move';
    });
    lane.addEventListener('dragleave', () => lane.classList.remove('obj-task-kanban-drop-active'));
    lane.addEventListener('drop', e => {
      e.preventDefault();
      lane.classList.remove('obj-task-kanban-drop-active');
      const taskId = e.dataTransfer.getData('text/plain');
      const targetStage = lane.dataset.kanbanStage;
      const card = Array.from(section.querySelectorAll('.obj-task-kanban-card'))
        .find(node => node.dataset.kanbanTaskId === taskId);
      if (!taskId || !targetStage || card?.dataset.kanbanStage === targetStage) return;
      _objectTaskKanbanSetStatus(taskId, _objectTaskKanbanStatusFor(targetStage), objectId, null);
    });
  });
}

async function renderObjectTaskKanbanSection(objectId) {
  const panel = document.getElementById('obj-detail-panel-info');
  if (!panel || !objectId) return;

  let section = document.getElementById('obj-task-kanban-section');
  if (!section) {
    const html = `
      <div class="obj-info-section obj-task-kanban-section" id="obj-task-kanban-section">
        <div id="obj-task-kanban-board" class="obj-task-kanban-board">
          <div class="js-skeleton-line" style="width:58%"></div>
          <div class="js-skeleton-line" style="width:72%"></div>
        </div>
      </div>`;
    const budgetSection = document.getElementById('obj-budget-section');
    const controlSection = panel.querySelector('.obj-control-section');
    if (budgetSection) budgetSection.insertAdjacentHTML('afterend', html);
    else if (controlSection) controlSection.insertAdjacentHTML('afterend', html);
    else panel.insertAdjacentHTML('afterbegin', html);
    section = document.getElementById('obj-task-kanban-section');
  }
  const board = document.getElementById('obj-task-kanban-board');
  if (!board) return;

  try {
    const { tasks } = await api(`/api/tasks?object_id=${encodeURIComponent(objectId)}`);
    const groups = { new: [], accepted: [], done: [] };
    (tasks || []).forEach(task => {
      const stage = _objectTaskKanbanStage(task.status);
      (groups[stage] || groups.new).push(task);
    });
    const totalCount = (tasks || []).length;
    const activeCount = groups.new.length + groups.accepted.length;
    const columns = [
      { key: 'new', title: 'Нужно' },
      { key: 'accepted', title: 'В работе' },
      { key: 'done', title: 'Готово' },
    ];
    board.innerHTML = `
      <div class="obj-task-kanban-head">
        <div>
          <div class="obj-task-kanban-title">Задачи объекта</div>
          <div class="obj-task-kanban-sub">${activeCount ? `${activeCount} активн.` : totalCount ? 'Всё закрыто' : 'Задач нет'}</div>
        </div>
      </div>
      <div class="obj-task-kanban-columns">
        ${columns.map(col => _objectTaskKanbanColumn(col, groups[col.key])).join('')}
      </div>
    `;
    _attachObjectTaskKanbanHandlers(section, objectId);
  } catch (e) {
    board.innerHTML = `<div class="obj-info-empty-row"><span>Задачи недоступны</span><button type="button" class="obj-info-empty-action" id="obj-task-kanban-retry">Повторить</button></div>`;
    document.getElementById('obj-task-kanban-retry')?.addEventListener('click', () => renderObjectTaskKanbanSection(objectId));
  }
}

function _refreshObjTaskKanban() {
  if (typeof _objDetailCurrentId !== 'undefined' && _objDetailCurrentId && document.getElementById('obj-task-kanban-section')) {
    renderObjectTaskKanbanSection(_objDetailCurrentId);
  }
}

async function renderObjectHistorySection(objectId) {
  const panel = document.getElementById('obj-detail-panel-info');
  if (!panel || !objectId) return;
  let section = document.getElementById('obj-history-section');
  if (!section) {
    panel.insertAdjacentHTML('beforeend', `
      <div class="obj-info-section obj-history-section" id="obj-history-section">
        <div class="obj-info-section-title-row">
          <span class="obj-info-section-title" style="margin-bottom:0;">История</span>
          <span id="obj-history-count" class="obj-info-count-badge"></span>
        </div>
        <div id="obj-history-list" class="obj-history-list"></div>
      </div>`);
    section = document.getElementById('obj-history-section');
  }
  const list = document.getElementById('obj-history-list');
  const countEl = document.getElementById('obj-history-count');
  if (!list) return;
  list.innerHTML = '<div class="obj-info-empty-row"><span>Загрузка истории...</span></div>';
  try {
    const data = await api(`/api/objects/${encodeURIComponent(objectId)}/history?limit=12`);
    const history = data.history || [];
    if (countEl) countEl.textContent = history.length ? String(history.length) : '';
    if (!history.length) {
      list.innerHTML = '<div class="obj-info-empty-row"><span>История пока пустая</span></div>';
      return;
    }
    list.innerHTML = history.map(event => `
      <div class="obj-history-row" data-history-kind="${esc(event.kind || '')}">
        <span class="obj-history-dot"></span>
        <div class="obj-history-main">
          <div class="obj-history-title">${esc(event.title || _objectHistoryKindLabel(event.kind))}</div>
          <div class="obj-history-sub">${[event.subtitle, event.actor_name].filter(Boolean).map(esc).join(' · ')}</div>
        </div>
        <span class="obj-history-meta">${esc(_objectHistoryKindLabel(event.kind))}${_objectHistoryTimeLabel(event.at) ? ' · ' + esc(_objectHistoryTimeLabel(event.at)) : ''}</span>
      </div>`).join('');
  } catch (e) {
    list.innerHTML = `<div class="obj-info-empty-row"><span>История недоступна</span><button type="button" class="obj-info-empty-action" id="obj-history-retry">Повторить</button></div>`;
    document.getElementById('obj-history-retry')?.addEventListener('click', () => renderObjectHistorySection(objectId));
  }
}

// 25.07: свайп-переключение между табами объекта (тот же UX, что юзер уже одобрил
// в подвкладках Чата) -- жест ловится на весь #view-object-detail, но глушится над
// зонами со своим горизонтальным/вертикальным взаимодействием (сама строка табов уже
// скроллится тапом -- не нужно вдобавок дёргать её свайпом; чат-композер/сообщения,
// roadmap move-кнопки -- те же exclusion-соображения что у глобального swipe-nav.js).
// 29.07 v2: 'needs' убран -- Потребности больше не отдельный таб (перенесены в Инфо).
const OBJ_DETAIL_TAB_ORDER = ['chat', 'info', 'stages'];
let _objTabSwipeStartX = 0;
let _objTabSwipeStartY = 0;
let _objTabSwipeExcluded = false;
const OBJ_TAB_SWIPE_THRESHOLD = 50;

function _isObjTabSwipeExcluded(target) {
  // 28.07: .obj-stage-move-col удалён (заменён drag-handle), новые классы аккордеона/drag
  // добавлены -- без этого глобальный tab-swipe перехватывал тап по заголовку этапа
  // (не давая аккордеону открыться) и конфликтовал с drag-перетаскиванием.
  // 17.09 (owner report): .obj-task-kanban-section добавлен -- Object Task Kanban
  // (P2 backlog item, added after this exclusion list was last touched) has no
  // horizontal swipe gesture of its own, but a horizontal swipe over its cards/lanes
  // was still being read by THIS tab-switch handler and flipping the whole Object
  // Detail screen to the next tab (Инфо/План работ/Дефекты/...) instead of doing
  // nothing -- the same class of bug the 28.07 comment above already fixed once for
  // stages, just never swept to this newer section.
  return !!target.closest?.('#obj-detail-tabs, .chat-messages, .chat-input-bar, .obj-stage-header, .obj-stage-drag-handle, .obj-stages-roadmap, .obj-info-doc-viewer, #obj-info-doc-viewer, .obj-task-kanban-section, input, textarea');
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
