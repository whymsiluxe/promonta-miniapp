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
  const addBtn = currentRole === 'owner'
    ? `<div class="obj-people-add obj-add-worker-btn" data-object-id="${esc(oid)}" data-stage="${esc(stage||'')}" title="Назначить"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="#000" stroke-width="2.5" stroke-linecap="round"/></svg></div>` : '';

  const startDateLabel = _objStartDateLabel(obj);
  const mapsUrl = obj['Адрес'] ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(obj['Адрес'])}` : '';

  // 28.07 (external audit ТЗ п.20): краткий roadmap вместо одной строки текущего этапа --
  // stage_summary приходит батчем с backend (list_objects читает всю таблицу Этапы один
  // раз, не N+1 запрос на карточку). completed показываем только последний завершённый
  // (не весь список -- на узкой карточке место ограничено), current + next для контекста.
  const summary = obj.stage_summary;
  let stagesStripHtml;
  if (summary && summary.total > 0) {
    const parts = [];
    if (summary.completed_count > 0) {
      const lastCompleted = summary.completed[summary.completed.length - 1];
      parts.push(`<span class="obj-stage-strip-item obj-stage-strip-done">✓ ${esc(lastCompleted)}</span>`);
    }
    if (summary.current) {
      parts.push(`<span class="obj-stage-strip-item obj-stage-strip-active">● ${esc(summary.current)}</span>`);
    }
    if (summary.next) {
      parts.push(`<span class="obj-stage-strip-item obj-stage-strip-next">○ ${esc(summary.next)}</span>`);
    }
    if (!parts.length) {
      // Все этапы "предстоит", ни один не в процессе/готово -- показываем первый как next.
      parts.push(`<span class="obj-stage-strip-item obj-stage-strip-next">○ ${esc(summary.completed[0] || '')}</span>`);
    }
    stagesStripHtml = `<div class="obj-stage-strip obj-stage-strip-roadmap stage-clickable" data-object-id="${oid}" data-object-name="${esc(obj['Объект']) || ''}">${parts.join('<span class="obj-stage-strip-arrow">→</span>')}</div>`;
  } else {
    stagesStripHtml = `<div class="obj-stage-strip stage-clickable" data-object-id="${oid}" data-object-name="${esc(obj['Объект']) || ''}"><span style="color:var(--text-light)">Этапы не добавлены</span></div>`;
  }

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

async function loadObjectWorkTasks(objectId, listEl, countEl) {
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
    renderObjectInfoTab(_objDetailCurrentId);
    return;
  }
  if (tab === 'stages') {
    renderObjectStagesTab(_objDetailCurrentId);
    return;
  }
  panel.innerHTML = `<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Загрузка…</div>`;
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
  return !!target.closest?.('#obj-detail-tabs, .chat-messages, .chat-input-bar, .obj-stage-header, .obj-stage-drag-handle, .obj-stages-roadmap, .obj-info-doc-viewer, #obj-info-doc-viewer, input, textarea');
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
