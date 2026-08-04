// Таб "Лента": погодные алерты по объектам (позже — другие типы событий).

// Instagram-style weather-alert посты: 3D-иконка по типу погоды (CSS-заглушка
// до генерации арта, как splash), prognosis-волна (SVG по wave-данным weather_check.py),
// лайк (localStorage) / коммент (ведёт в чат) / share.

// Единые температурные пороги жары (Раунд 4). Объявлены ЗДЕСЬ один раз.
const WEATHER_HEAT_THRESHOLD = 30;
const WEATHER_HIGH_HEAT_THRESHOLD = 33;
const WEATHER_EXTREME_HEAT_THRESHOLD = 35;

// Тип жары по tmax (не по тексту risks).
function weatherHeatKind(tmax) {
  if (typeof tmax !== 'number' || isNaN(tmax)) return null;
  if (tmax >= WEATHER_EXTREME_HEAT_THRESHOLD) return 'extreme_heat';
  if (tmax >= WEATHER_HEAT_THRESHOLD) return 'heat';
  return null;
}

// Русская подпись жары по tmax (30-32 Жарко, 33-34 Сильная жара, 35+ Экстремальная).
function weatherHeatLabel(tmax) {
  if (typeof tmax !== 'number' || isNaN(tmax)) return null;
  if (tmax >= WEATHER_EXTREME_HEAT_THRESHOLD) return 'Экстремальная жара';
  if (tmax >= WEATHER_HIGH_HEAT_THRESHOLD) return 'Сильная жара';
  if (tmax >= WEATHER_HEAT_THRESHOLD) return 'Жарко';
  return null;
}

const WX_TYPES = {
  extreme_heat: { icon: '\uD83C\uDF21\uFE0F', label: 'Экстремальная жара', grad: 'linear-gradient(160deg,#7c2d12 0%,#b91c1c 55%,#431407 100%)', hue: '#f97316' },
  heat:  { icon: '\uD83C\uDF21\uFE0F', label: 'Жара', grad: 'linear-gradient(160deg,#7c4a0f 0%,#b45309 55%,#3a1d04 100%)', hue: '#f59e0b' },
  frost: { icon: '\u2744\uFE0F', label: 'Мороз', grad: 'linear-gradient(160deg,#274060 0%,#0d1b2a 100%)', hue: '#7dd3fc' },
  rain:  { icon: '\uD83C\uDF27\uFE0F', label: 'Дождь', grad: 'linear-gradient(160deg,#1e3a5f 0%,#0f1f33 100%)', hue: '#60a5fa' },
  wind:  { icon: '\uD83D\uDCA8', label: 'Ветер', grad: 'linear-gradient(160deg,#2f4f4f 0%,#101820 100%)', hue: '#a7f3d0' },
  cold:  { icon: '\uD83E\uDD76', label: 'Холод', grad: 'linear-gradient(160deg,#1c2e4a 0%,#0d1420 100%)', hue: '#93c5fd' },
  warn:  { icon: '\u26A0\uFE0F', label: 'Риск', grad: 'linear-gradient(160deg,#3f3320 0%,#141005 100%)', hue: '#fbbf24' },
};

function pickWeatherIcon(riskText) {
  return (WX_TYPES[_riskType(riskText)] || WX_TYPES.warn).icon;
}

function _riskType(riskText) {
  if (riskText.includes('жар')) return 'heat';
  if (riskText.includes('заморозки')) return 'frost';
  if (riskText.includes('дождь')) return 'rain';
  if (riskText.includes('ветер')) return 'wind';
  if (riskText.includes('холодно')) return 'cold';
  return 'warn';
}

// Доминантный тип: жару по tmax, остальное по тексту. Экстр.жара>ветер>мороз>жара>дождь>холод.
function _dominantWxType(entry) {
  const all = entry.forecast.flatMap(d => d.risks).map(_riskType);
  const tmax = (entry.wave && entry.wave.length) ? Math.max(...entry.wave.map(d => d.tmax)) : null;
  if (weatherHeatKind(tmax) === 'extreme_heat') return 'extreme_heat';
  if (all.includes('wind')) return 'wind';
  if (all.includes('frost')) return 'frost';
  if (weatherHeatKind(tmax) === 'heat' || all.includes('heat')) return 'heat';
  if (all.includes('rain')) return 'rain';
  if (all.includes('cold')) return 'cold';
  return 'warn';
}

// Раунд 5 §7/§12: уровень серьёзности для группировки Инфо-ленты и цвета алерта.
// Красный (critical) только для действительно критичного (экстремальная жара, шторм);
// warning — сильная жара/ветер/мороз; info — обычные/лёгкие условия. Не «первое слово».
function weatherSeverityLevel(entry) {
  const type = _dominantWxType(entry);
  // Критично только для действительно критичного: экстремальная жара, шторм/ураган/гроза.
  // Сильная жара (33-34°C) — предупреждение, не критично (см. §7 уровни алерта).
  if (type === 'extreme_heat') return 'critical';
  const risksText = (entry.forecast || []).flatMap(d => d.risks || []).join(' ');
  if (/шторм|ураган|гроза|гололёд|гололед/i.test(risksText)) return 'critical';
  if (type === 'heat' || type === 'wind' || type === 'frost') return 'warning';
  if (type === 'rain' || type === 'cold') return 'warning';
  return 'info';
}

const WX_SEVERITY_SECTIONS = [
  { level: 'critical', label: 'Критично' },
  { level: 'warning', label: 'Предупреждения' },
  { level: 'info', label: 'Информация' },
];

// Основная подпись поста: при жаре -- температурная, иначе первый risk или label типа.
function _wxPrimaryLabel(entry) {
  const type = _dominantWxType(entry);
  if (type === 'heat' || type === 'extreme_heat') {
    const tmax = (entry.wave && entry.wave.length) ? Math.max(...entry.wave.map(d => d.tmax)) : null;
    return weatherHeatLabel(tmax) || WX_TYPES[type].label;
  }
  return (entry.forecast[0] && entry.forecast[0].risks[0]) || WX_TYPES[type].label;
}

function fmtFeedDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

function fmtForecastDay(iso, offset) {
  if (offset === 0) return 'Сегодня';
  if (offset === 1) return 'Завтра';
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

// Prognosis-волна: сглаженная кривая tmax по дням прогноза (quadratic через середины).
function _buildWaveSvg(wave, hue) {
  if (!wave || wave.length < 2) return '';
  const W = 300, H = 64, padX = 26, padTop = 20, padBot = 16;
  const temps = wave.map(d => d.tmax);
  const min = Math.min(...temps), max = Math.max(...temps);
  const span = Math.max(1, max - min);
  const pts = wave.map((d, i) => ({
    x: padX + i * ((W - 2 * padX) / (wave.length - 1)),
    y: padTop + (1 - (d.tmax - min) / span) * (H - padTop - padBot),
    t: Math.round(d.tmax),
  }));
  let path = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) {
    const mx = (pts[i - 1].x + pts[i].x) / 2;
    const my = (pts[i - 1].y + pts[i].y) / 2;
    path += ` Q ${pts[i - 1].x} ${pts[i - 1].y} ${mx} ${my}`;
  }
  path += ` T ${pts[pts.length - 1].x} ${pts[pts.length - 1].y}`;
  const area = `${path} L ${pts[pts.length - 1].x} ${H} L ${pts[0].x} ${H} Z`;
  return `
    <svg class="wx-wave" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      <path d="${area}" fill="${hue}" opacity="0.13"/>
      <path d="${path}" fill="none" stroke="${hue}" stroke-width="2" stroke-linecap="round"/>
      ${pts.map(p => `<circle cx="${p.x}" cy="${p.y}" r="3" fill="${hue}"/>
        <text x="${p.x}" y="${p.y - 7}" text-anchor="middle" class="wx-wave-temp">${p.t}\u00B0</text>`).join('')}
    </svg>`;
}

// 21.07: \u0440\u0435\u0430\u043B\u044C\u043D\u044B\u0435 \u043B\u0430\u0439\u043A\u0438 \u0447\u0435\u0440\u0435\u0437 backend (\u0431\u044B\u043B\u0438 \u0434\u0435\u043A\u043E\u0440\u0430\u0442\u0438\u0432\u043D\u044B\u0435 localStorage-only) \u2014
// weather-\u0437\u0430\u043F\u0438\u0441\u0438 \u043D\u0435 \u0438\u043C\u0435\u044E\u0442 \u0441\u0432\u043E\u0435\u0433\u043E id, \u043A\u043B\u044E\u0447 \u043D\u0430 \u0431\u044D\u043A\u0435 \u2014 object+created.
async function toggleWxLike(btn, idx) {
  const entry = _wxEntries[idx];
  if (!entry) return;
  const wasLiked = !!entry.liked_by_me;
  btn.disabled = true;
  try {
    const res = await api('/api/feed/weather/react', {
      method: 'POST',
      body: JSON.stringify({ object: entry.object, created: entry.created, liked: !wasLiked }),
    });
    entry.liked_by_me = res.liked_by_me;
    entry.likes = res.likes;
    btn.querySelector('.wx-heart').textContent = res.liked_by_me ? '\u2764\uFE0F' : '\uD83E\uDD0D';
    btn.classList.toggle('liked', res.liked_by_me);
    const countEl = btn.querySelector('.wx-like-count');
    if (countEl) countEl.textContent = res.likes > 0 ? res.likes : '';
    hapticImpact('light');
  } catch (e) {
    showToast('\u041E\u0448\u0438\u0431\u043A\u0430: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

function shareWxPost(entry) {
  const text = `\u26A0 Погода на объекте «${entry.object}» — ${_wxPrimaryLabel(entry)}: ` +
    entry.forecast.map(d => `${fmtForecastDay(d.date, d.day_offset)} — ${d.risks.join('; ')}`).join(' | ');
  try {
    if (navigator.share) { navigator.share({ text }); return; }
  } catch (e) {}
  try { navigator.clipboard.writeText(text); showToast('Скопировано в буфер', 'success'); } catch (e) {}
}

let _wxEntries = [];

function renderFeedCard(entry, idx, isActive) {
  const type = WX_TYPES[_dominantWxType(entry)];
  const liked = !!entry.liked_by_me;
  const waveSvg = _buildWaveSvg(entry.wave, type.hue);

  // \u0420\u0435\u0444\u0435\u0440\u0435\u043D\u0441 "16\u00B0 / Stormy Monday": \u043A\u0440\u0443\u043F\u043D\u0430\u044F \u0442\u0435\u043C\u043F \u0441\u0435\u0433\u043E\u0434\u043D\u044F + \u0434\u0438\u0430\u043F\u0430\u0437\u043E\u043D \u043C\u0438\u043D/\u043C\u0430\u043A\u0441 + \u043D\u0430\u0437\u0432\u0430\u043D\u0438\u0435 \u0441\u043E\u0431\u044B\u0442\u0438\u044F.
  const today = entry.wave && entry.wave[0];
  const tempNow = today ? Math.round(today.tmax) : null;
  const tmin = entry.wave ? Math.round(Math.min(...entry.wave.map(d => d.tmin))) : null;
  const tmax = entry.wave ? Math.round(Math.max(...entry.wave.map(d => d.tmax))) : null;
  const eventName = _wxPrimaryLabel(entry).split('(')[0].trim();

  // \u0420\u0435\u0444\u0435\u0440\u0435\u043D\u0441 "Brooklyn": \u0433\u043E\u0440\u0438\u0437\u043E\u043D\u0442\u0430\u043B\u044C\u043D\u0430\u044F \u043F\u043E\u043B\u043E\u0441\u0430 \u0434\u043D\u0435\u0439 \u0441 \u043C\u0438\u043D\u0438-\u0438\u043A\u043E\u043D\u043A\u043E\u0439 + \u0442\u0435\u043C\u043F \u043F\u043E\u0434 prognosis-\u0432\u043E\u043B\u043D\u043E\u0439.
  const dayStrip = (entry.wave && entry.wave.length > 1)
    ? `<div class="wx-day-strip">${entry.wave.map((d, i) => `
        <div class="wx-day-strip-item">
          <span class="wx-day-strip-label">${fmtForecastDay(d.date, i)}</span>
          <span class="wx-day-strip-icon">${pickWeatherIcon((entry.forecast.find(f => f.date === d.date)?.risks[0]) || '')}</span>
          <span class="wx-day-strip-temp">${Math.round(d.tmax)}\u00B0</span>
        </div>`).join('')}</div>`
    : '';

  const caption = entry.forecast.map(day => `
    <div class="wx-caption-day">
      <span class="wx-caption-daylabel">${fmtForecastDay(day.date, day.day_offset)}</span>
      ${day.risks.map(r => `<div class="wx-caption-risk">${pickWeatherIcon(r)} ${esc(r)}</div>`).join('')}
    </div>`).join('');

  return `
  <div class="wx-post">
    <div class="wx-post-media" style="background:${type.grad}">
      <div class="wx-3d-wrap">
        <span class="wx-3d-icon">${type.icon}</span>
        <span class="wx-3d-glow" style="background:${type.hue}"></span>
      </div>
    </div>
    <div class="wx-post-stats">
      ${tempNow !== null ? `
      <div class="wx-post-temp-row">
        <span class="wx-post-temp-now">${tempNow}\u00B0</span>
        <span class="wx-post-temp-range">\u2193${tmin}\u00B0 \u2191${tmax}\u00B0</span>
      </div>` : ''}
      <div class="wx-post-eventname" style="color:${type.hue}">${esc(eventName)}</div>
    </div>
    ${waveSvg}
    ${dayStrip}
    <div class="wx-post-head">
      <div class="wx-post-headtext">
        <div class="wx-post-title">${esc(entry.object)}</div>
        <div class="wx-post-sub">${esc(entry.address)}</div>
      </div>
      <div class="wx-post-date">${fmtFeedDate(entry.created)}</div>
    </div>
    <div class="wx-post-actions">
      <button class="wx-act ${liked ? 'liked' : ''}" type="button"
        onclick="toggleWxLike(this, ${idx})">
        <span class="wx-heart">${liked ? '\u2764\uFE0F' : '\uD83E\uDD0D'}</span>
        <span class="wx-like-count">${entry.likes > 0 ? entry.likes : ''}</span>
      </button>
      <button class="wx-act" type="button" onclick="switchView('chat')">\uD83D\uDCAC</button>
      <button class="wx-act" type="button" onclick="shareWxPost(_wxEntries[${idx}])">\uD83D\uDCE4</button>
    </div>
    <div class="wx-post-caption">${caption}</div>
  </div>`;
}

// Город из немецкого адреса: "Straße 7, 01069 Dresden" -> "Dresden" (последнее слово после индекса).
function _wxCityFromAddress(address) {
  const m = (address || '').match(/\d{5}\s+(.+)$/);
  return m ? m[1].trim() : (address || '').split(',').pop().trim();
}

let _wxActiveCityIdx = 0;

function renderWeatherCityTabs() {
  if (_wxEntries.length <= 1) return '';
  return `<div class="wx-city-tabs">${_wxEntries.map((e, i) => `
    <span class="wx-city-tab${i === _wxActiveCityIdx ? ' active' : ''}" data-city-idx="${i}">${esc(_wxCityFromAddress(e.address))}</span>
  `).join('')}</div>`;
}

let _wxExpandedIdx = null;

function _renderCompactWeatherRow(entry, idx) {
  const type = WX_TYPES[_dominantWxType(entry)];
  const today = entry.wave && entry.wave[0];
  const tempNow = today ? Math.round(today.tmax) : null;
  const topRisk = _wxPrimaryLabel(entry);
  const expanded = _wxExpandedIdx === idx;
  return `
  <div class="wx-compact-row ${expanded ? 'expanded' : ''}" data-wx-idx="${idx}">
    <div class="wx-compact-head">
      <span class="wx-compact-icon">${type.icon}</span>
      <div class="wx-compact-text">
        <span class="wx-compact-object">${esc(entry.object)}</span>
        <span class="wx-compact-risk">${esc(topRisk)}</span>
      </div>
      ${tempNow !== null ? `<span class="wx-compact-temp">${tempNow}°</span>` : ''}
    </div>
    ${expanded ? `<div class="wx-compact-detail">${renderFeedCard(entry, idx)}</div>` : ''}
  </div>`;
}

function _renderActiveWeatherCard() {
  const container = document.getElementById('feed-list');
  if (!_wxEntries.length) return;
  // Раунд 5 §12: группировка Инфо-ленты по серьёзности (Критично/Предупреждения/
  // Информация). Секция рендерится только если в ней есть объекты; исходный индекс
  // сохраняется для expand-логики, чтобы клик по строке разворачивал нужную запись.
  const indexed = _wxEntries.map((e, i) => ({ e, i, level: weatherSeverityLevel(e) }));
  container.innerHTML = WX_SEVERITY_SECTIONS.map(sec => {
    const rows = indexed.filter(x => x.level === sec.level);
    if (!rows.length) return '';
    return `<div class="wx-sev-section wx-sev-${sec.level}">
      <div class="wx-sev-head">${sec.label}</div>
      ${rows.map(x => _renderCompactWeatherRow(x.e, x.i)).join('')}
    </div>`;
  }).join('');
  container.querySelectorAll('.wx-compact-head').forEach(head => {
    head.addEventListener('click', () => {
      const idx = parseInt(head.closest('.wx-compact-row').dataset.wxIdx, 10);
      _wxExpandedIdx = _wxExpandedIdx === idx ? null : idx;
      _renderActiveWeatherCard();
      hapticImpact('light');
    });
  });
}

// Свайп между городами внутри погодного блока — тот же приём различения направления,
// что и в swipe-nav.js/feed-суб-табах (доминанта |dx| над |dy|, иначе это вертикальный скролл).
function _initWeatherCitySwipe(container) {
  if (_wxEntries.length <= 1) return;
  let startX = 0, startY = 0;
  container.addEventListener('touchstart', e => {
    startX = e.changedTouches[0].screenX;
    startY = e.changedTouches[0].screenY;
  }, { passive: true });
  container.addEventListener('touchend', e => {
    const dx = e.changedTouches[0].screenX - startX;
    const dy = e.changedTouches[0].screenY - startY;
    if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy)) return;
    const dir = dx > 0 ? -1 : 1;
    const next = _wxActiveCityIdx + dir;
    if (next < 0 || next >= _wxEntries.length) return;
    _wxActiveCityIdx = next;
    _renderActiveWeatherCard();
    playSwipeSound(dir > 0 ? 'left' : 'right');
    hapticImpact('light');
  }, { passive: true });
}

async function loadWeatherFeed() {
  const container = document.getElementById('feed-list');
  _loadBirthdayBanner();
  try {
    const data = await api('/api/feed/weather');
    if (!data.feed || data.feed.length === 0) {
      container.innerHTML = '<div class="empty-state">Погодных рисков не обнаружено. Проверка каждый день в 18:00 и 6:30.</div>';
      return;
    }
    _wxEntries = data.feed;
    _wxActiveCityIdx = 0;
    _renderActiveWeatherCard();
  } catch (e) {
    container.innerHTML = `<div class="empty-state" style="color:var(--red)">Ошибка загрузки: ${esc(e.message)}</div>`;
  }
}

async function _loadBirthdayBanner() {
  const slot = document.getElementById('feed-birthdays');
  if (!slot) return;
  try {
    const data = await api('/api/feed/birthdays');
    const list = data.birthdays || [];
    if (!list.length) { slot.innerHTML = ''; return; }
    slot.innerHTML = list.map(b => {
      const soon = b.date === new Date().toISOString().slice(0, 10);
      return `<div class="feed-birthday-card">
        <span class="feed-birthday-icon">🎂</span>
        <span class="feed-birthday-text">У ${esc(b.name)} день рождения ${soon ? 'сегодня!' : new Date(b.date).toLocaleDateString('ru-RU', {day:'2-digit', month:'2-digit'})}</span>
      </div>`;
    }).join('');
  } catch (e) {
    slot.innerHTML = '';
  }
}

function fmtPhotoTime(ts) {
  const d = new Date(ts * 1000);
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const timeStr = pad(d.getHours()) + ':' + pad(d.getMinutes());
  if (d.toDateString() === now.toDateString()) return timeStr;
  return pad(d.getDate()) + '.' + pad(d.getMonth() + 1);
}

function renderPhotoItem(p) {
  const caption = p.object_id || p.caption
    ? `${esc(p.object_id) || ''}${p.object_id && p.caption ? ' — ' : ''}${esc(p.caption) || ''}`
    : esc(p.name);
  const fileCount = (p.files || []).length;
  // 24.07: мультифото — свайп прямо в карточке ленты (как в Инсте), не только в модалке.
  // img-wrap — горизонтальный scroll-snap контейнер со всеми фото поста; badge/dots
  // обновляются по scroll-позиции (см. _initFeedPhotoSwipeDots). Тап на карточку всё
  // ещё открывает модалку комментариев — браузер сам различает drag-scroll от click,
  // отдельная логика не нужна.
  const imgs = (fileCount ? Array.from({ length: fileCount }, (_, i) => i) : [0])
    .map(i => `<img data-auth-src="/api/feed/photos/${p.id}/file?index=${i}" loading="lazy" alt="">`).join('');
  const dots = fileCount > 1
    ? `<div class="feed-photo-item-dots">${Array.from({ length: fileCount }, (_, i) => `<span class="${i === 0 ? 'active' : ''}"></span>`).join('')}</div>`
    : '';
  return `
  <div class="feed-photo-item" data-photo-id="${p.id}" onclick="openPhotoComments('${p.id}', ${fileCount})">
    <div class="feed-photo-img-wrap" data-file-count="${fileCount}">
      ${imgs}
      ${fileCount > 1 ? `<span class="feed-photo-count-badge">1/${fileCount}</span>` : ''}
      ${dots}
    </div>
    <div class="feed-photo-meta">${caption}<div class="feed-photo-time">${fmtPhotoTime(p.ts)}</div></div>
    <div class="feed-photo-actions"><span class="feed-photo-comment-count">💬 ${p.comment_count || 0}</span></div>
  </div>`;
}

function _initFeedPhotoSwipeDots(grid) {
  grid.querySelectorAll('.feed-photo-img-wrap[data-file-count]').forEach(wrap => {
    const count = parseInt(wrap.dataset.fileCount, 10);
    if (count <= 1 || wrap.dataset.swipeWired) return;
    wrap.dataset.swipeWired = '1';
    const badge = wrap.querySelector('.feed-photo-count-badge');
    const dots = wrap.querySelectorAll('.feed-photo-item-dots span');
    wrap.addEventListener('scroll', () => {
      const idx = Math.round(wrap.scrollLeft / wrap.clientWidth);
      if (badge) badge.textContent = `${idx + 1}/${count}`;
      dots.forEach((d, i) => d.classList.toggle('active', i === idx));
    }, { passive: true });
  });
}

let _feedPhotosCache = [];

async function loadFeedPhotos() {
  const grid = document.getElementById('feed-photo-grid');
  try {
    const data = await api('/api/feed/photos');
    _feedPhotosCache = data.photos || [];
    if (!data.photos || data.photos.length === 0) {
      grid.innerHTML = '<div class="empty-state">Фото пока нет. Загрузите первым 📷</div>';
      return;
    }
    grid.innerHTML = data.photos.map(renderPhotoItem).join('');
    grid.querySelectorAll('img[data-auth-src]').forEach(img => authImg(img, img.dataset.authSrc));
    _initFeedPhotoSwipeDots(grid);
    _markFeedRead('photos');
  } catch (e) {
    grid.innerHTML = `<div class="empty-state" style="color:var(--red)">Ошибка загрузки: ${esc(e.message)}</div>`;
  }
}

async function _uploadFeedPhoto(files) {
  const formData = new FormData();
  for (const f of files) formData.append('files', f);
  try {
    await fetch(`${API_BASE}/api/feed/photos`, {
      method: 'POST',
      headers: { ..._authHeaders() },
      body: formData,
    }).then(async res => {
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
      return res.json();
    });
    hapticImpact('light');
    loadFeedPhotos();
  } catch (e) {
    showToast('Ошибка загрузки фото: ' + e.message, 'error');
  }
}

const FEED_TABS = ['news', 'photos', 'weather'];

function _selectFeedTab(which, opts = {}) {
  const { silent } = opts;
  document.querySelectorAll('#view-home .doc-type-opt[data-feed]').forEach(o => o.classList.toggle('active', o.dataset.feed === which));
  document.getElementById('feed-weather-content').style.display = which === 'weather' ? 'block' : 'none';
  document.getElementById('feed-photos-content').style.display = which === 'photos' ? 'block' : 'none';
  document.getElementById('feed-news-content').style.display = which === 'news' ? 'block' : 'none';
  if (which === 'photos') loadFeedPhotos();
  if (which === 'news') loadNewsFeed();
  // Инфо-лента уже загружена на init (виджет погоды на Home) — отмечаем прочтение здесь,
  // когда вкладка реально открыта пользователем (loadNewsFeed/loadFeedPhotos делают это сами).
  if (which === 'weather') _markFeedRead('info');
  if (!silent) hapticImpact('light');
}

// Новости (10.32): cron на VPS (news_pipeline.py) каждые 3-4ч добавляет пачку поверх
// старых (накопительная лента) → GLM-саммари → JSON. Фронт рендерит порциями с infinite scroll.
const NEWS_CAT_COLORS = { 'Украина': '#56768C', 'Германия': '#B38B4D', 'Технологии': '#1F7A5F' };
const NEWS_PAGE_SIZE = 10;
let _newsItems = [];
let _newsRenderedCount = 0;

function openNewsLink(idx) {
  const url = _newsItems[idx]?.url;
  if (!url) return;
  openExternalLink(url);
}

function shareNewsLink(idx) {
  const n = _newsItems[idx];
  if (!n?.url) return;
  const wa = window.Telegram?.WebApp;
  if (wa && typeof wa.shareURL === 'function') {
    wa.shareURL(n.url, n.title || '');
    return;
  }
  try {
    if (navigator.share) { navigator.share({ title: n.title, url: n.url }); return; }
  } catch (e) {}
  try { navigator.clipboard.writeText(n.url); showToast('Ссылка скопирована', 'success'); } catch (e) {}
}

// Раунд 4: резюме новости абзацами (split по пустой строке), esc() каждого абзаца.
// Длинное (>2 абзацев или >600 симв) сворачивается по абзацам с кнопкой "Читать полностью".
// Раскрывается только выбранная карточка; tap по раскрытию не открывает источник (stopPropagation).
function _renderNewsSummary(n, i) {
  const raw = (n.summary || '').trim();
  if (!raw) return '';
  const paras = raw.split(/\n{2,}/).map(p => p.trim()).filter(Boolean);
  if (paras.length <= 1 && raw.length <= 600) {
    return `<div class="news-summary">${esc(raw)}</div>`;
  }
  // Свёрнутое состояние: абзацы в пределах ~450 симв (минимум первый), остальное скрыто.
  let acc = 0, cut = 0;
  for (let k = 0; k < paras.length; k++) {
    if (k === 0 || acc + paras[k].length <= 450) { acc += paras[k].length; cut = k + 1; }
    else break;
  }
  const wrapP = arr => arr.map(p => `<p>${esc(p)}</p>`).join('');
  if (cut >= paras.length) {
    return `<div class="news-summary">${wrapP(paras)}</div>`;
  }
  return `<div class="news-summary" data-news-idx="${i}">
    <div class="news-summary-head">${wrapP(paras.slice(0, cut))}</div>
    <div class="news-summary-tail" hidden>${wrapP(paras.slice(cut))}</div>
    <button type="button" class="news-more-btn" onclick="event.stopPropagation();toggleNewsSummary(${i},this)">Читать полностью</button>
  </div>`;
}

function toggleNewsSummary(i, btn) {
  const wrap = btn.closest('.news-summary');
  if (!wrap) return;
  const tail = wrap.querySelector('.news-summary-tail');
  if (!tail) return;
  const expanded = !tail.hidden;
  tail.hidden = expanded;
  btn.textContent = expanded ? 'Читать полностью' : 'Свернуть';
}

function _newsCardHtml(n, i) {
  const catColor = NEWS_CAT_COLORS[n.category] || 'var(--accent)';
  const likeActive = n.my_reaction === 'like' ? 'active' : '';
  const dislikeActive = n.my_reaction === 'dislike' ? 'active' : '';
  const cc = n.comment_count || 0;
  const discussBadge = cc > 0 ? `<span class="news-discuss-badge">Обсуждают · ${cc}</span>` : '';
  return `
  <div class="news-card">
    <div onclick="openNewsLink(${i})">
      <div class="news-card-top">
        <span class="news-cat" style="color:${catColor};background:${catColor}1c">${esc(n.category) || 'Новости'}</span>
        <span class="news-src">${esc(n.source) || ''}${discussBadge}</span>
      </div>
      <div class="news-title">${esc(n.title)}</div>
      ${_renderNewsSummary(n, i)}
      <div class="news-foot">${esc(n.published_at) || ''}${n.url ? ' · Читать источник\u2197' : ''}</div>
    </div>
    <div class="news-actions">
      <button class="news-react-btn news-comment-btn" onclick="event.stopPropagation();openNewsComments('${n.id}')"><svg viewBox="0 0 24 24" width="16" height="16"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg> <span>${cc}</span></button>
      <button class="news-react-btn ${likeActive}" onclick="event.stopPropagation();reactNews('${n.id}','like',this)"><svg viewBox="0 0 24 24" width="16" height="16"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M7 10v12M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z"/></svg> <span>${n.likes || 0}</span></button>
      <button class="news-react-btn ${dislikeActive}" onclick="event.stopPropagation();reactNews('${n.id}','dislike',this)"><svg viewBox="0 0 24 24" width="16" height="16"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M17 14V2M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z"/></svg> <span>${n.dislikes || 0}</span></button>
      ${n.url ? `<button class="news-react-btn" onclick="event.stopPropagation();shareNewsLink(${i})"><svg viewBox="0 0 24 24" width="16" height="16"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8M16 6l-4-4-4 4M12 2v14"/></svg></button>` : ''}
    </div>
  </div>`;
}

async function reactNews(postId, reaction, btnEl) {
  const post = _newsItems.find(n => n.id === postId);
  if (!post) return;
  const wasActive = btnEl.classList.contains('active');
  const newReaction = wasActive ? 'none' : reaction;
  hapticImpact('light');
  try {
    const res = await api(`/api/feed/news/${postId}/react`, {
      method: 'POST',
      body: JSON.stringify({ reaction: newReaction }),
    });
    post.likes = res.likes;
    post.dislikes = res.dislikes;
    post.my_reaction = res.my_reaction;
    const card = btnEl.closest('.news-card');
    card.querySelector('.news-react-btn:nth-child(1) span').textContent = post.likes || 0;
    card.querySelector('.news-react-btn:nth-child(2) span').textContent = post.dislikes || 0;
    card.querySelectorAll('.news-react-btn').forEach(b => b.classList.remove('active'));
    if (post.my_reaction === 'like') card.querySelector('.news-react-btn:nth-child(1)').classList.add('active');
    if (post.my_reaction === 'dislike') card.querySelector('.news-react-btn:nth-child(2)').classList.add('active');
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

function _renderMoreNews() {
  const list = document.getElementById('feed-news-list');
  const nextBatch = _newsItems.slice(_newsRenderedCount, _newsRenderedCount + NEWS_PAGE_SIZE);
  const html = nextBatch.map((n, idx) => _newsCardHtml(n, _newsRenderedCount + idx)).join('');
  const moreEl = document.getElementById('news-load-more');
  if (moreEl) moreEl.insertAdjacentHTML('beforebegin', html);
  else list.insertAdjacentHTML('beforeend', html);
  _newsRenderedCount += nextBatch.length;
  if (moreEl) moreEl.style.display = _newsRenderedCount < _newsItems.length ? 'block' : 'none';
}

function _initNewsInfiniteScroll() {
  // #feed-news-list не имеет собственного overflow — скроллится документ/body,
  // поэтому слушаем window, а не сам список (иначе scroll-событие никогда не всплывёт).
  if (window._newsScrollBound) return;
  window._newsScrollBound = true;
  window.addEventListener('scroll', () => {
    const newsActive = document.getElementById('feed-news-content')?.style.display !== 'none';
    if (!newsActive) return;
    if (window.innerHeight + window.scrollY > document.body.scrollHeight - 400) {
      if (_newsRenderedCount < _newsItems.length) _renderMoreNews();
    }
  });
}

async function loadNewsFeed() {
  const list = document.getElementById('feed-news-list');
  try {
    const res = await api('/api/feed/news');
    _newsItems = res?.feed || [];
    _newsRenderedCount = 0;
    if (!_newsItems.length) {
      list.innerHTML = '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Сводка новостей появится в течение дня</div>';
      return;
    }
    list.innerHTML = _renderDiscussingSection() +
      '<div class="news-load-more" id="news-load-more" style="display:none">Загрузка…</div>';
    _renderMoreNews();
    _initNewsInfiniteScroll();
    _markFeedRead('news');
  } catch (e) {
    list.innerHTML = '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Не удалось загрузить новости</div>';
  }
}

// Раунд 5 §8: «Сейчас обсуждают» — макс 3 новости с новыми комментариями за 24ч,
// сортировка по last_comment_at убыв., счётчик комментариев. Основная лента остаётся
// по времени публикации (ниже), эта секция — отдельный блок сверху.
function _renderDiscussingSection() {
  const now = Math.floor(Date.now() / 1000);
  const discussing = _newsItems
    .map((n, idx) => ({ n, idx }))
    .filter(x => (x.n.comment_count || 0) > 0 && (x.n.last_comment_at || 0) > now - 86400)
    .sort((a, b) => (b.n.last_comment_at || 0) - (a.n.last_comment_at || 0))
    .slice(0, 3);
  if (!discussing.length) return '';
  return `<div class="news-discussing">
    <div class="news-discussing-head">Сейчас обсуждают</div>
    ${discussing.map(x => `<div class="news-discuss-item" onclick="openNewsComments('${x.n.id}')">
      <span class="news-discuss-item-title">${esc(x.n.title)}</span>
      <span class="news-discuss-item-count">${x.n.comment_count} 💬</span>
    </div>`).join('')}
  </div>`;
}

// ---- Комментарии к новости (Раунд 5 §8): тот же lifecycle/визуал, что фото-комментарии ----
let _ncCurrentPostId = null;
let _ncOverlayUnregister = null;

function _renderNewsComment(c) {
  const canDelete = String(c.user_id) === String(_feedMyId) || currentRole === 'owner';
  const reply = c.reply_to_name ? `<div class="pc-comment-reply">↳ ${esc(c.reply_to_name)}</div>` : '';
  return `<div class="pc-comment" data-comment-id="${c.id || ''}">
    ${reply}
    <div class="pc-comment-head"><b>${esc(c.name || c.user_id)}</b><span class="pc-comment-time">${_fmtPhotoCommentTime(c.ts ? c.ts * 1000 : c.at)}</span>${canDelete && c.id ? `<button class="pc-comment-del" data-del-comment="${c.id}" type="button">✕</button>` : ''}</div>
    <div class="pc-comment-text">${esc(c.text)}</div>
  </div>`;
}

async function _renderNewsCommentsList() {
  const list = document.getElementById('nc-list');
  const data = await api(`/api/feed/news/${_ncCurrentPostId}/comments`);
  const byId = {};
  (data.comments || []).forEach(c => { byId[c.id] = c; });
  (data.comments || []).forEach(c => { if (c.reply_to && byId[c.reply_to]) c.reply_to_name = byId[c.reply_to].name; });
  list.innerHTML = (data.comments || []).map(_renderNewsComment).join('') ||
    '<div style="color:var(--text-light);font-size:0.95rem;padding:1rem 0">Пока нет комментариев. Будьте первым.</div>';
  list.querySelectorAll('[data-del-comment]').forEach(btn => {
    btn.addEventListener('click', () => _deleteNewsComment(btn.dataset.delComment));
  });
}

async function _deleteNewsComment(commentId) {
  if (!_ncCurrentPostId) return;
  try {
    await api(`/api/feed/news/${_ncCurrentPostId}/comments/${commentId}`, { method: 'DELETE' });
    hapticImpact('light');
    await _renderNewsCommentsList();
  } catch (e) {
    showToast('Ошибка удаления: ' + e.message, 'error');
  }
}

async function openNewsComments(postId) {
  _ncCurrentPostId = postId;
  const modal = document.getElementById('news-comments-modal');
  modal.style.display = 'flex';
  const post = _newsItems.find(n => n.id === postId);
  document.getElementById('nc-title').textContent = post ? post.title : 'Обсуждение';
  if (typeof NavigationManager !== 'undefined' && !_ncOverlayUnregister) {
    _ncOverlayUnregister = NavigationManager.registerOverlay(() => _closeNewsCommentsInternal());
  }
  const list = document.getElementById('nc-list');
  list.innerHTML = '<div style="padding:1rem;color:var(--text-light);text-align:center">Загрузка...</div>';
  try {
    await _ensureFeedMyId();
    await _renderNewsCommentsList();
  } catch (e) {
    list.innerHTML = `<div style="color:var(--red)">Ошибка: ${esc(e.message)}</div>`;
  }
}

function _closeNewsCommentsInternal() {
  document.getElementById('news-comments-modal').style.display = 'none';
  _ncCurrentPostId = null;
  _ncOverlayUnregister = null;
}

function closeNewsComments() {
  if (_ncOverlayUnregister) { _ncOverlayUnregister(); _ncOverlayUnregister = null; }
  document.getElementById('news-comments-modal').style.display = 'none';
  _ncCurrentPostId = null;
}

async function _sendNewsComment() {
  const input = document.getElementById('nc-comment-input');
  const btn = document.getElementById('nc-comment-send-btn');
  const text = input.value.trim();
  if (!text || !_ncCurrentPostId || (btn && btn.disabled)) return;
  if (btn) btn.disabled = true;
  try {
    await api(`/api/feed/news/${_ncCurrentPostId}/comments`, { method: 'POST', body: JSON.stringify({ text }) });
    input.value = '';
    hapticImpact('light');
    await _renderNewsCommentsList();
    // обновить счётчик на карточке + «обсуждают» без перезагрузки всей ленты
    const post = _newsItems.find(n => n.id === _ncCurrentPostId);
    if (post) { post.comment_count = (post.comment_count || 0) + 1; post.last_comment_at = Math.floor(Date.now() / 1000); }
  } catch (e) {
    showToast('Ошибка отправки: ' + e.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ---- Непрочитанное: badge = кол-во непрочитанных публикаций/активностей (не общее) ----
// tab: 'news'|'photos'|'info'; вкладка Инфо в разметке зовётся 'weather'.
const _FEED_TAB_TO_BADGE = { news: 'news', photos: 'photos', info: 'weather' };

async function _markFeedRead(tab) {
  try {
    await api('/api/feed/read', { method: 'POST', body: JSON.stringify({ tab }) });
    // после прочтения — локально гасим badge этой вкладки (без ожидания следующего опроса)
    _setFeedBadge(_FEED_TAB_TO_BADGE[tab] || tab, 0);
  } catch (e) { /* не сбрасывать при ошибке API */ }
}

function _initFeedSwitch() {
  const switcher = document.querySelector('#view-home .doc-type-opt[data-feed]');
  if (!switcher) return;
  document.querySelectorAll('#view-home .doc-type-opt[data-feed]').forEach(opt => {
    opt.addEventListener('click', () => _selectFeedTab(opt.dataset.feed));
  });

  // 24.07: было capture=environment (только камера, галерея недоступна — двойная
  // жалоба юзера). Теперь два отдельных input: камера (оставляет capture) и галерея
  // (multiple, без capture) — переключаются через _openFeedPhotoSourceSheet().
  const cameraInput = document.getElementById('feed-photo-input-camera');
  const galleryInput = document.getElementById('feed-photo-input-gallery');
  const addBtn = document.getElementById('feed-add-photo-btn');
  if (addBtn) addBtn.addEventListener('click', _openFeedPhotoSourceSheet);
  if (cameraInput) {
    cameraInput.addEventListener('change', () => {
      if (cameraInput.files && cameraInput.files.length) _uploadFeedPhoto(Array.from(cameraInput.files));
      cameraInput.value = '';
    });
  }
  if (galleryInput) {
    galleryInput.addEventListener('change', () => {
      if (galleryInput.files && galleryInput.files.length) _uploadFeedPhoto(Array.from(galleryInput.files));
      galleryInput.value = '';
    });
  }
}

function _openFeedPhotoSourceSheet() {
  const sheet = document.getElementById('feed-photo-source-sheet');
  if (!sheet) return;
  sheet.style.display = 'flex';
}

function _closeFeedPhotoSourceSheet() {
  const sheet = document.getElementById('feed-photo-source-sheet');
  if (sheet) sheet.style.display = 'none';
}

// Свайп внутри Ленты переключает Инфо ↔ Фото (звук + вибрация).
// Событие гасится (stopPropagation), чтобы не сработал заодно глобальный
// свайп между вкладками Лента/Объекты/Чат из swipe-nav.js.
const FEED_SWIPE_THRESHOLD = 50;
let _feedTouchStartX = 0;
let _feedTouchStartY = 0;

function _initFeedSwipe() {
  const area = document.getElementById('feed-swipe-area');
  if (!area) return;

  area.addEventListener('touchstart', e => {
    _feedTouchStartX = e.changedTouches[0].screenX;
    _feedTouchStartY = e.changedTouches[0].screenY;
  }, { passive: true });

  area.addEventListener('touchend', e => {
    const endX = e.changedTouches[0].screenX;
    const endY = e.changedTouches[0].screenY;
    const diffX = endX - _feedTouchStartX;
    const diffY = endY - _feedTouchStartY;

    // Игнорируем вертикальные/диагональные свайпы (скролл ленты/фото-сетки).
    if (Math.abs(diffX) < FEED_SWIPE_THRESHOLD || Math.abs(diffX) < Math.abs(diffY)) return;

    const current = document.querySelector('#view-home .doc-type-opt[data-feed].active')?.dataset.feed || 'news';
    const idx = FEED_TABS.indexOf(current);
    const direction = diffX > 0 ? 'right' : 'left'; // свайп вправо = назад, влево = вперёд по FEED_TABS
    const nextIdx = direction === 'left' ? idx + 1 : idx - 1;

    if (nextIdx < 0 || nextIdx >= FEED_TABS.length) return; // на границе — пусть сработает глобальный свайп между вкладками

    e.stopPropagation();
    _selectFeedTab(FEED_TABS[nextIdx]);
    playSwipeSound(direction);
  }, { passive: true });
}

// Инициализация суб-табов Инфо/Фото/Новости. Вызывается из home.js initHomeView()
// (раньше эта функция сама называлась initHomeView и молча перекрывалась home.js —
// суб-табы и погодная лента не работали вовсе).
function initFeedTabs() {
  // 10.3: дефолтный активный суб-таб — Новости (первый в FEED_TABS), не Инфо.
  // loadWeatherFeed() всё равно нужен сразу — от него зависит виджет погоды на Home,
  // но контент активного суб-таба грузим по фактическому data-feed из разметки.
  loadWeatherFeed();
  const active = document.querySelector('#view-home .doc-type-opt[data-feed].active')?.dataset.feed || 'news';
  if (active === 'news') loadNewsFeed();
  if (active === 'photos') loadFeedPhotos();
  _initFeedSwitch();
  _initFeedSwipe();
  _loadFeedTabBadges();
}

function _setFeedBadge(tabKey, count) {
  const el = document.getElementById(`feed-badge-${tabKey}`);
  if (!el) return;
  el.textContent = count > 99 ? '99+' : count;
  el.style.display = count > 0 ? 'inline-flex' : 'none';
}

async function _loadFeedTabBadges() {
  // Раунд 5 §8/§15: badge = НЕПРОЧИТАННОЕ (не общее число постов). Источник — единый
  // per-user endpoint /api/feed/unread (публикации/активность новее отметки прочтения).
  try {
    const u = await api('/api/feed/unread');
    _setFeedBadge('news', u.news || 0);
    _setFeedBadge('photos', u.photos || 0);
    _setFeedBadge('weather', u.info || 0);
  } catch (e) { /* не сбрасывать badge при ошибке API */ }
}

// Комментарии к фото (Instagram-style, 10.4) — модалка на всю вкладку с фото сверху,
// списком комментариев и input снизу. Переиспользует authImg (X-Telegram-Init-Data не проходит
// через <img src> напрямую) и esc() (защита от XSS на свободном тексте комментария).
let _pcCurrentPhotoId = null;

function _fmtPhotoCommentTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, '0');
  return pad(d.getHours()) + ':' + pad(d.getMinutes());
}

let _feedMyId = null;

async function _ensureFeedMyId() {
  if (_feedMyId !== null) return _feedMyId;
  try {
    const me = await api('/api/me');
    _feedMyId = me.user_id;
  } catch (e) {}
  return _feedMyId;
}

function renderPhotoComment(c) {
  const canDelete = String(c.user_id) === String(_feedMyId) || currentRole === 'owner';
  return `<div class="pc-comment" data-comment-id="${c.id || ''}">
    <div class="pc-comment-head"><b>${esc(c.name || c.user_id)}</b><span class="pc-comment-time">${_fmtPhotoCommentTime(c.at)}</span>${canDelete && c.id ? `<button class="pc-comment-del" data-del-comment="${c.id}" type="button">✕</button>` : ''}</div>
    <div class="pc-comment-text">${esc(c.text)}</div>
  </div>`;
}

async function _deletePhotoComment(commentId) {
  if (!_pcCurrentPhotoId) return;
  try {
    await api(`/api/feed/photos/${_pcCurrentPhotoId}/comments/${commentId}`, { method: 'DELETE' });
    hapticImpact('light');
    await _renderPhotoCommentsList();
    loadFeedPhotos();
  } catch (e) {
    showToast('Ошибка удаления: ' + e.message, 'error');
  }
}

async function _renderPhotoCommentsList() {
  const list = document.getElementById('pc-list');
  const data = await api(`/api/feed/photos/${_pcCurrentPhotoId}/comments`);
  list.innerHTML = (data.comments || []).map(renderPhotoComment).join('') ||
    '<div style="color:var(--text-light);font-size:0.85rem">Комментариев нет</div>';
  list.querySelectorAll('[data-del-comment]').forEach(btn => {
    btn.addEventListener('click', () => _deletePhotoComment(btn.dataset.delComment));
  });
}

let _pcFileCount = 1;
let _pcPhotoIndex = 0;

function _pcRenderPhotoAt(index) {
  _pcPhotoIndex = index;
  authImg(document.getElementById('pc-photo'), `/api/feed/photos/${_pcCurrentPhotoId}/file?index=${index}`);
  const prevBtn = document.getElementById('pc-photo-prev');
  const nextBtn = document.getElementById('pc-photo-next');
  const dotsEl = document.getElementById('pc-photo-dots');
  const labelEl = document.getElementById('pc-photo-label');
  // 24.07: подпись "Начало смены · 09:12" / "Конец смены · 17:30" — для постов из
  // check-in (checkin_session_id), обычные загруженные фото labels не имеют.
  const post = _feedPhotosCache.find(p => p.id === _pcCurrentPhotoId);
  const label = post?.photo_labels?.[String(index)];
  if (labelEl) {
    if (label) { labelEl.textContent = label; labelEl.style.display = 'block'; }
    else { labelEl.style.display = 'none'; }
  }
  if (_pcFileCount > 1) {
    prevBtn.style.display = index > 0 ? 'flex' : 'none';
    nextBtn.style.display = index < _pcFileCount - 1 ? 'flex' : 'none';
    dotsEl.innerHTML = Array.from({ length: _pcFileCount }, (_, i) =>
      `<span class="pc-photo-dot${i === index ? ' active' : ''}"></span>`).join('');
  } else {
    prevBtn.style.display = 'none';
    nextBtn.style.display = 'none';
    dotsEl.innerHTML = '';
  }
}

let _pcOverlayUnregister = null;

async function openPhotoComments(photoId, fileCount) {
  // 24.07: мультифото — fileCount передаётся с карточки ленты (renderPhotoItem уже
  // знает p.files.length); если вызвано без него (старый путь), считаем 1 фото.
  _pcCurrentPhotoId = photoId;
  _pcFileCount = fileCount || 1;
  const modal = document.getElementById('photo-comments-modal');
  modal.style.display = 'flex';
  // 25.07: модалка теперь зарегистрирована в NavigationManager.overlayStack -- раньше
  // Telegram BackButton её не видел (display-toggle вне навигации), при нажатии "назад"
  // NavigationManager.back() падал сразу на pop реального route-стека, закрывая не эту
  // модалку, а уводя на предыдущий экран (баг: Back из комментариев кидал в Профиль).
  if (typeof NavigationManager !== 'undefined' && !_pcOverlayUnregister) {
    _pcOverlayUnregister = NavigationManager.registerOverlay(() => _closePhotoCommentsInternal());
  }
  _pcRenderPhotoAt(0);
  const list = document.getElementById('pc-list');
  list.innerHTML = '<div style="padding:1rem;color:var(--text-light);text-align:center">Загрузка...</div>';
  try {
    await _ensureFeedMyId();
    await _renderPhotoCommentsList();
  } catch (e) {
    list.innerHTML = `<div style="color:var(--red)">Ошибка: ${esc(e.message)}</div>`;
  }
}

// Вызывается ТОЛЬКО из NavigationManager (top.close()) — модалка уже popped из
// overlayStack на этот момент, повторный unregister тут не нужен и не должен вызываться.
function _closePhotoCommentsInternal() {
  document.getElementById('photo-comments-modal').style.display = 'none';
  _pcCurrentPhotoId = null;
  _pcOverlayUnregister = null;
}

// Вызывается при ручном закрытии (крестик/клик-вне) — модалка ещё в overlayStack,
// нужно явно её оттуда снять, иначе следующий Back попытается закрыть уже закрытую модалку.
function closePhotoComments() {
  if (_pcOverlayUnregister) { _pcOverlayUnregister(); _pcOverlayUnregister = null; }
  document.getElementById('photo-comments-modal').style.display = 'none';
  _pcCurrentPhotoId = null;
}

async function _sendPhotoComment() {
  const input = document.getElementById('pc-comment-input');
  const btn = document.getElementById('pc-comment-send-btn');
  const text = input.value.trim();
  // 31.07 (UX-аудит): btn.disabled guard -- быстрый двойной тап отправлял 2
  // одинаковых комментария до возврата первого ответа.
  if (!text || !_pcCurrentPhotoId || (btn && btn.disabled)) return;
  if (btn) btn.disabled = true;
  try {
    await api(`/api/feed/photos/${_pcCurrentPhotoId}/comments`, { method: 'POST', body: JSON.stringify({ text }) });
    input.value = '';
    hapticImpact('light');
    await _renderPhotoCommentsList();
    loadFeedPhotos(); // обновить счётчик комментариев в ленте
  } catch (e) {
    showToast('Ошибка отправки: ' + e.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function _pcGoPrev() {
  if (_pcPhotoIndex > 0) { _pcRenderPhotoAt(_pcPhotoIndex - 1); hapticImpact('light'); }
}
function _pcGoNext() {
  if (_pcPhotoIndex < _pcFileCount - 1) { _pcRenderPhotoAt(_pcPhotoIndex + 1); hapticImpact('light'); }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('pc-back-btn')?.addEventListener('click', closePhotoComments);
  document.getElementById('pc-comment-send-btn')?.addEventListener('click', _sendPhotoComment);
  document.getElementById('pc-photo-prev')?.addEventListener('click', _pcGoPrev);
  document.getElementById('pc-photo-next')?.addEventListener('click', _pcGoNext);

  // Раунд 5 §8: комментарии к новости — те же обработчики (закрытие/отправка), что фото.
  document.getElementById('nc-back-btn')?.addEventListener('click', closeNewsComments);
  document.getElementById('nc-comment-send-btn')?.addEventListener('click', _sendNewsComment);

  // 25.07: карусель показывала счётчик/точки/стрелки как настоящая карусель, но пальцем
  // не свайпалась вообще -- только click по стрелкам. Threshold-свайп поверх той же
  // _pcRenderPhotoAt/_pcGoPrev/_pcGoNext логики, стрелки остаются рабочим fallback.
  const pcWrap = document.getElementById('pc-photo-wrap');
  if (pcWrap) {
    let pcTouchStartX = 0, pcTouchStartY = 0, pcSwiping = false;
    const SWIPE_THRESHOLD = 40;
    pcWrap.addEventListener('touchstart', (e) => {
      if (_pcFileCount <= 1) return;
      pcTouchStartX = e.touches[0].clientX;
      pcTouchStartY = e.touches[0].clientY;
      pcSwiping = true;
    }, { passive: true });
    pcWrap.addEventListener('touchend', (e) => {
      if (!pcSwiping) return;
      pcSwiping = false;
      const dx = e.changedTouches[0].clientX - pcTouchStartX;
      const dy = e.changedTouches[0].clientY - pcTouchStartY;
      if (Math.abs(dx) < SWIPE_THRESHOLD || Math.abs(dx) < Math.abs(dy)) return; // вертикальный жест или слишком короткий -- не наш
      if (dx < 0) _pcGoNext(); else _pcGoPrev();
    }, { passive: true });
  }
});
