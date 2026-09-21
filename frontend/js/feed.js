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
  const text = String(riskText || '').toLowerCase();
  if (text.includes('жар')) return 'heat';
  if (text.includes('заморозки') || text.includes('мороз')) return 'frost';
  if (text.includes('дождь') || text.includes('ливень') || text.includes('осад')) return 'rain';
  if (text.includes('ветер') || text.includes('шторм')) return 'wind';
  if (text.includes('холодно') || text.includes('холод')) return 'cold';
  return 'warn';
}

// Доминантный тип: жару по tmax, остальное по тексту. Экстр.жара>ветер>мороз>жара>дождь>холод.
function _dominantWxType(entry) {
  const forecast = Array.isArray(entry.forecast) ? entry.forecast : [];
  const wave = Array.isArray(entry.wave) ? entry.wave : [];
  const all = forecast.flatMap(d => d.risks || []).map(_riskType);
  const tmax = wave.length ? Math.max(...wave.map(d => d.tmax).filter(v => typeof v === 'number')) : null;
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

const IG_ICONS = {
  heart: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.8 4.6c-1.7-1.7-4.4-1.7-6.1 0L12 7.3 9.3 4.6C7.6 2.9 4.9 2.9 3.2 4.6s-1.7 4.4 0 6.1L12 19.5l8.8-8.8c1.7-1.7 1.7-4.4 0-6.1Z"/></svg>',
  comment: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5 8.7 8.7 0 0 1-3.8-.9L3 21l1.9-5.7A8.4 8.4 0 0 1 4 11.5 8.5 8.5 0 0 1 12.5 3 8.5 8.5 0 0 1 21 11.5Z"/></svg>',
  share: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7Z"/></svg>',
  bookmark: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1Z"/></svg>',
  thumbsUp: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10v12M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z"/></svg>',
  thumbsDown: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 14V2M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z"/></svg>',
};

const FEED_SAVED_FILTERS = { photos: 'all', news: 'all' };

function resetFeedViewScroll() {
  window.scrollTo(0, 0);
  if (document.scrollingElement) document.scrollingElement.scrollTop = 0;
  ['feed-swipe-area', 'feed-photo-grid', 'feed-news-list', 'feed-list'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.scrollTop = 0;
  });
}

function _feedJsString(value) {
  return JSON.stringify(String(value == null ? '' : value));
}

function _feedKindForSaveType(itemType) {
  if (itemType === 'photo') return 'photos';
  return itemType;
}

// Основная подпись поста: при жаре -- температурная, иначе первый risk или label типа.
function _wxPrimaryLabel(entry) {
  const type = _dominantWxType(entry);
  if (type === 'heat' || type === 'extreme_heat') {
    const tmax = (entry.wave && entry.wave.length) ? Math.max(...entry.wave.map(d => d.tmax)) : null;
    return weatherHeatLabel(tmax) || WX_TYPES[type].label;
  }
  const firstRiskDay = (entry.forecast || []).find(d => d.risks && d.risks.length);
  return (firstRiskDay && firstRiskDay.risks[0]) || WX_TYPES[type].label;
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
        <span class="wx-heart">${IG_ICONS.heart}</span>
        <span class="wx-like-count">${entry.likes > 0 ? entry.likes : ''}</span>
      </button>
      <button class="wx-act" type="button" onclick="switchView('chat')" aria-label="Комментарии">${IG_ICONS.comment}</button>
      <button class="wx-act" type="button" onclick="shareWxPost(_wxEntries[${idx}])" aria-label="Поделиться">${IG_ICONS.share}</button>
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

function _wxWaveValue(wave, field, mode) {
  const values = (wave || []).map(d => d && d[field]).filter(v => typeof v === 'number' && !isNaN(v));
  if (!values.length) return null;
  return mode === 'min' ? Math.min(...values) : Math.max(...values);
}

function _wxAlertForecastDay(entry, kind) {
  const forecast = Array.isArray(entry.forecast) ? entry.forecast : [];
  if (!forecast.length) return null;
  if (kind === 'heat' || kind === 'extreme_heat') {
    const tmax = _wxWaveValue(entry.wave || [], 'tmax', 'max');
    const day = (entry.wave || []).find(d => d.tmax === tmax);
    return forecast.find(f => f.date === day?.date) || forecast[0];
  }
  return forecast.find(day => (day.risks || []).some(r => _riskType(r) === kind)) ||
    forecast.find(day => day.risks && day.risks.length) ||
    forecast[0];
}

function _wxWaveForDate(entry, date) {
  const wave = Array.isArray(entry.wave) ? entry.wave : [];
  return wave.find(d => d.date === date) || wave[0] || null;
}

function _wxAlertSummary(entry) {
  const kind = _dominantWxType(entry);
  const type = WX_TYPES[kind] || WX_TYPES.warn;
  const wave = Array.isArray(entry.wave) ? entry.wave : [];
  const alertDay = _wxAlertForecastDay(entry, kind);
  const alertWave = _wxWaveForDate(entry, alertDay?.date);
  const tmax = _wxWaveValue(wave, 'tmax', 'max');
  const tmin = _wxWaveValue(wave, 'tmin', 'min');
  const precip = alertWave && typeof alertWave.precip_prob === 'number'
    ? alertWave.precip_prob
    : _wxWaveValue(wave, 'precip_prob', 'max');
  const wind = alertWave && typeof alertWave.wind === 'number'
    ? alertWave.wind
    : _wxWaveValue(wave, 'wind', 'max');
  const risks = alertDay && alertDay.risks && alertDay.risks.length ? alertDay.risks : [];
  const rawDetail = risks[0] || _wxPrimaryLabel(entry);
  const title = (kind === 'heat' || kind === 'extreme_heat')
    ? (weatherHeatLabel(tmax) || type.label)
    : type.label;
  let metric = '';
  if (kind === 'rain') metric = precip !== null ? `${Math.round(precip)}% дождя` : 'Осадки';
  else if (kind === 'wind') metric = wind !== null ? `${Math.round(wind)} км/ч` : 'Порывы';
  else if (kind === 'cold' || kind === 'frost') metric = tmin !== null ? `до ${Math.round(tmin)}°` : 'Температура';
  else if (kind === 'heat' || kind === 'extreme_heat') metric = tmax !== null ? `до ${Math.round(tmax)}°` : 'Температура';
  else metric = rawDetail && rawDetail !== title ? rawDetail : '';
  const tempLabel = alertWave && typeof alertWave.tmax === 'number' ? `${Math.round(alertWave.tmax)}°` : '';
  return {
    kind,
    type,
    title,
    metric,
    detail: rawDetail,
    dateLabel: alertDay ? fmtForecastDay(alertDay.date, alertDay.day_offset) : '',
    tempLabel,
  };
}

function _renderCompactWeatherRow(entry, idx) {
  const summary = _wxAlertSummary(entry);
  const expanded = _wxExpandedIdx === idx;
  return `
  <div class="wx-compact-row wx-risk-${summary.kind} ${expanded ? 'expanded' : ''}" data-wx-idx="${idx}" style="--wx-hue:${summary.type.hue}">
    <div class="wx-compact-head">
      <span class="wx-compact-icon" aria-hidden="true">${summary.type.icon}</span>
      <div class="wx-compact-body">
        <div class="wx-compact-primary">
          <span class="wx-compact-risk-title">${esc(summary.title)}</span>
          ${summary.metric ? `<span class="wx-compact-metric">${esc(summary.metric)}</span>` : ''}
        </div>
        <div class="wx-compact-risk-detail">${esc(summary.detail)}</div>
        <div class="wx-compact-meta">
          <span class="wx-compact-object">${esc(entry.object)}</span>
          ${summary.dateLabel ? `<span>${esc(summary.dateLabel)}</span>` : ''}
          ${entry.created ? `<span>${fmtFeedDate(entry.created)}</span>` : ''}
        </div>
      </div>
      ${summary.tempLabel ? `<span class="wx-compact-temp">${esc(summary.tempLabel)}</span>` : ''}
    </div>
    ${expanded ? `<div class="wx-compact-detail">${renderFeedCard(entry, idx)}</div>` : ''}
  </div>`;
}

function _renderActiveWeatherCard() {
  const container = document.getElementById('feed-list');
  if (!_wxEntries.length) {
    if (container) {
      container.innerHTML = '<div class="empty-state">Погодных рисков не обнаружено. Проверка каждый день в 18:00 и 6:30.</div>';
    }
    return;
  }
  // Раунд 5 §12: группировка Инфо-ленты по серьёзности (Критично/Предупреждения/
  // Информация). Секция рендерится только если в ней есть объекты; исходный индекс
  // сохраняется для expand-логики, чтобы клик по строке разворачивал нужную запись.
  const indexed = _wxEntries
    .map((e, i) => ({ e, i, level: weatherSeverityLevel(e) }));
  if (!indexed.length) {
    container.innerHTML = '<div class="empty-state">Погодных рисков не обнаружено. Проверка каждый день в 18:00 и 6:30.</div>';
    return;
  }
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
      _wxEntries = [];
      _renderActiveWeatherCard();
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
      const soon = b.date === todayBerlin();
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

function _feedPhotoInitials(name) {
  const clean = String(name || '').trim();
  if (!clean) return 'P';
  return clean.split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase();
}

function renderPhotoItem(p) {
  const author = p.name || 'Сотрудник';
  const objectLabel = p.object_id || '';
  const caption = (p.caption || '').trim();
  const fileCount = (p.files || []).length;
  const liked = !!p.liked_by_me;
  const saved = !!p.saved_by_me;
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
  <article class="feed-photo-post" data-photo-id="${p.id}">
    <div class="feed-photo-post-header">
      <div class="feed-photo-avatar">${esc(_feedPhotoInitials(author))}</div>
      <div class="feed-photo-post-author">
        <div class="feed-photo-author-name">${esc(author)}</div>
        <div class="feed-photo-post-subtitle">${objectLabel ? esc(objectLabel) : 'Фотоотчёт'}</div>
      </div>
      <time class="feed-photo-time">${fmtPhotoTime(p.ts)}</time>
    </div>
    <div class="feed-photo-img-wrap" data-file-count="${fileCount}">
      ${imgs}
      ${fileCount > 1 ? `<span class="feed-photo-count-badge">1/${fileCount}</span>` : ''}
      ${dots}
      <div class="feed-photo-img-error" aria-hidden="true">Фото недоступно</div>
    </div>
    <div class="feed-photo-action-row">
      <div class="feed-photo-action-left">
        <button class="feed-photo-icon-action feed-photo-like-action ${liked ? 'liked' : ''}" type="button" onclick="event.stopPropagation(); togglePhotoLike(this, '${p.id}')" aria-label="Нравится">
          ${IG_ICONS.heart}
          <span class="feed-photo-like-count">${p.likes > 0 ? p.likes : ''}</span>
        </button>
        <button class="feed-photo-icon-action feed-photo-comment-action" type="button" onclick="event.stopPropagation(); openPhotoComments('${p.id}', ${fileCount})" aria-label="Комментарии">
          ${IG_ICONS.comment}
          <span>${p.comment_count || 0}</span>
        </button>
        <button class="feed-photo-icon-action" type="button" onclick="event.stopPropagation(); sharePhotoPost('${p.id}')" aria-label="Поделиться">
          ${IG_ICONS.share}
        </button>
      </div>
      <button class="feed-photo-icon-action feed-photo-save-action ${saved ? 'saved' : ''}" type="button"
        onclick="event.stopPropagation(); toggleFeedSave(this, 'photo', ${_feedJsString(p.id)})"
        aria-label="${saved ? 'Убрать из сохранённых' : 'Сохранить'}" aria-pressed="${saved ? 'true' : 'false'}">
        ${IG_ICONS.bookmark}
      </button>
    </div>
    <div class="feed-photo-caption">
      <b>${esc(author)}</b>${caption ? ` ${esc(caption)}` : (objectLabel ? ` Фото по объекту ${esc(objectLabel)}` : ' Добавил фото')}
    </div>
  </article>`;
}

async function togglePhotoLike(btn, photoId) {
  const post = _feedPhotosCache.find(p => p.id === photoId);
  if (!post || btn.disabled) return;
  const nextLiked = !post.liked_by_me;
  btn.disabled = true;
  try {
    const res = await api(`/api/feed/photos/${encodeURIComponent(photoId)}/react`, {
      method: 'POST',
      body: JSON.stringify({ liked: nextLiked }),
    });
    post.liked_by_me = res.liked_by_me;
    post.likes = res.likes;
    btn.classList.toggle('liked', res.liked_by_me);
    const count = btn.querySelector('.feed-photo-like-count');
    if (count) count.textContent = res.likes > 0 ? res.likes : '';
    hapticImpact('light');
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

function sharePhotoPost(photoId) {
  const post = _feedPhotosCache.find(p => p.id === photoId);
  if (!post) return;
  const text = `${post.name || 'Promonta'}: ${post.caption || (post.object_id ? `Фото по объекту ${post.object_id}` : 'Фотоотчёт')}`;
  try {
    if (navigator.share) { navigator.share({ text }); return; }
  } catch (e) {}
  try { navigator.clipboard.writeText(text); showToast('Скопировано', 'success'); } catch (e) {}
}

function _findFeedSavedItem(itemType, itemId) {
  if (itemType === 'photo') return _feedPhotosCache.find(p => String(p.id) === String(itemId));
  if (itemType === 'news') return _newsItems.find(n => String(n.id) === String(itemId));
  return null;
}

function _rerenderFeedKind(kind) {
  if (kind === 'photos') _renderFeedPhotosFromCache();
  else if (kind === 'news') _renderNewsFromCache();
  else if (kind === 'weather') _renderActiveWeatherCard();
}

function _refreshFeedSavedCounts() {
  _updateFeedSavedCount('photos', _feedPhotosCache.filter(p => p.saved_by_me).length);
  _updateFeedSavedCount('news', _newsItems.filter(n => n.saved_by_me).length);
}

async function toggleFeedSave(btn, itemType, itemId) {
  if (!itemId || (btn && btn.disabled)) return;
  let item = null;
  let previousSaved = !!btn?.classList.contains('saved');
  let nextSaved = !previousSaved;
  if (btn) btn.disabled = true;
  try {
    item = _findFeedSavedItem(itemType, itemId);
    previousSaved = item ? !!item.saved_by_me : !!btn?.classList.contains('saved');
    nextSaved = !previousSaved;
    if (item) item.saved_by_me = nextSaved;
    if (btn) {
      btn.classList.toggle('saved', nextSaved);
      btn.setAttribute('aria-pressed', nextSaved ? 'true' : 'false');
      btn.setAttribute('aria-label', nextSaved ? 'Убрать из сохранённых' : 'Сохранить');
    }
    _refreshFeedSavedCounts();
    const res = await api('/api/feed/saved', {
      method: 'POST',
      body: JSON.stringify({ item_type: itemType, item_id: String(itemId), saved: nextSaved }),
    });
    if (item) item.saved_by_me = !!res.saved_by_me;
    if (btn) {
      btn.classList.toggle('saved', !!res.saved_by_me);
      btn.setAttribute('aria-pressed', res.saved_by_me ? 'true' : 'false');
      btn.setAttribute('aria-label', res.saved_by_me ? 'Убрать из сохранённых' : 'Сохранить');
    }
    hapticImpact('light');
    const kind = _feedKindForSaveType(itemType);
    _refreshFeedSavedCounts();
    if (FEED_SAVED_FILTERS[kind] === 'saved') _rerenderFeedKind(kind);
  } catch (e) {
    if (item) item.saved_by_me = previousSaved;
    if (btn) {
      btn.classList.toggle('saved', previousSaved);
      btn.setAttribute('aria-pressed', previousSaved ? 'true' : 'false');
      btn.setAttribute('aria-label', previousSaved ? 'Убрать из сохранённых' : 'Сохранить');
    }
    _refreshFeedSavedCounts();
    showToast('Ошибка сохранения: ' + e.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
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

function _updateFeedSavedCount(kind, count) {
  const el = document.getElementById(`feed-saved-count-${kind}`);
  if (!el) return;
  el.textContent = count > 99 ? '99+' : count;
  el.style.display = count > 0 ? 'inline-flex' : 'none';
}

function _renderFeedPhotosFromCache() {
  const grid = document.getElementById('feed-photo-grid');
  if (!grid) return;
  const savedCount = _feedPhotosCache.filter(p => p.saved_by_me).length;
  _updateFeedSavedCount('photos', savedCount);
  const photos = FEED_SAVED_FILTERS.photos === 'saved'
    ? _feedPhotosCache.filter(p => p.saved_by_me)
    : _feedPhotosCache;
  _revokeFeedBlobUrls(grid);
  if (!photos.length) {
    grid.innerHTML = FEED_SAVED_FILTERS.photos === 'saved'
      ? '<div class="empty-state">Сохранённых фото пока нет</div>'
      : '<div class="empty-state">Фото пока нет. Загрузите первым 📷</div>';
    return;
  }
  grid.innerHTML = photos.map(renderPhotoItem).join('');
  _lazyLoadAuthImages([...grid.querySelectorAll('img[data-auth-src]')]);
  _initFeedPhotoSwipeDots(grid);
}

// Lazy-load auth images using IntersectionObserver — avoids fetching all blob URLs at once.
// Falls back to immediate load if IntersectionObserver is unavailable.
function _lazyLoadAuthImages(imgs) {
  if (!('IntersectionObserver' in window)) {
    imgs.forEach(img => authImg(img, img.dataset.authSrc));
    return;
  }
  const observer = new IntersectionObserver((entries, obs) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      obs.unobserve(entry.target);
      authImg(entry.target, entry.target.dataset.authSrc);
    }
  }, { rootMargin: '200px' });
  imgs.forEach(img => observer.observe(img));
}

// Revoke all blob URLs currently set on imgs inside a container (called before innerHTML replace).
function _revokeFeedBlobUrls(container) {
  container.querySelectorAll('img[src^="blob:"]').forEach(img => {
    try { URL.revokeObjectURL(img.src); } catch (_) {}
  });
}

async function loadFeedPhotos() {
  const grid = document.getElementById('feed-photo-grid');
  try {
    const data = await api('/api/feed/photos');
    _feedPhotosCache = data.photos || [];
    _renderFeedPhotosFromCache();
    _markFeedRead('photos');
  } catch (e) {
    grid.innerHTML = `<div class="empty-state" style="color:var(--red)">Ошибка загрузки: ${esc(e.message)}</div>`;
  }
}

async function _uploadFeedPhoto(files, objectId) {
  const formData = new FormData();
  for (const f of files) formData.append('files', f);
  // 21.09 (Worker UX V2, Этап 6): backend уже принимал object_id (main.py
  // upload_feed_photo), фронт его никогда не передавал -- нужно для quick-action
  // "Фото", привязывающего снимок к контекстно резолвленному объекту.
  if (objectId) formData.append('object_id', objectId);
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

const FEED_TABS = ['photos', 'news', 'weather'];

// Returns the feed view root element. After Phase 3, the feed lives in #view-feed;
// #view-home fallback keeps this safe if DOM is partially loaded.
function getFeedRoot() {
  return document.getElementById('view-feed') || document.getElementById('view-home');
}

function _setFeedSavedFilter(kind, filter) {
  FEED_SAVED_FILTERS[kind] = filter === 'saved' ? 'saved' : 'all';
  const row = document.querySelector(`.feed-saved-switch[data-feed-saved-kind="${kind}"]`);
  row?.querySelectorAll('.feed-saved-opt').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.feedSavedFilter === FEED_SAVED_FILTERS[kind]);
  });
  _rerenderFeedKind(kind);
  hapticImpact('light');
}

function _initFeedSavedFilters() {
  document.querySelectorAll('.feed-saved-switch[data-feed-saved-kind]').forEach(row => {
    if (row.dataset.wired) return;
    row.dataset.wired = '1';
    row.addEventListener('click', (e) => {
      const target = e.target instanceof Element ? e.target : null;
      const btn = target?.closest('.feed-saved-opt');
      if (!btn) return;
      _setFeedSavedFilter(row.dataset.feedSavedKind, btn.dataset.feedSavedFilter || 'all');
    });
  });
}

function _selectFeedTab(which, opts = {}) {
  const { silent } = opts;
  const root = getFeedRoot();
  resetFeedViewScroll();
  root.querySelectorAll('.doc-type-opt[data-feed]').forEach(o => o.classList.toggle('active', o.dataset.feed === which));
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
let _newsCategoryFilter = 'all';

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
  const saved = !!n.saved_by_me;
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
      <button class="news-react-btn news-comment-btn" data-news-action="comment" onclick="event.stopPropagation();openNewsComments('${n.id}')">${IG_ICONS.comment} <span>${cc}</span></button>
      <button class="news-react-btn news-like-btn ${likeActive}" data-news-reaction="like" onclick="event.stopPropagation();reactNews('${n.id}','like',this)">${IG_ICONS.heart} <span>${n.likes || 0}</span></button>
      ${n.url ? `<button class="news-react-btn" data-news-action="share" onclick="event.stopPropagation();shareNewsLink(${i})">${IG_ICONS.share}</button>` : ''}
      <button class="news-react-btn news-save-btn ${saved ? 'saved' : ''}" data-news-action="save"
        onclick="event.stopPropagation();toggleFeedSave(this, 'news', ${_feedJsString(n.id)})"
        aria-label="${saved ? 'Убрать из сохранённых' : 'Сохранить'}" aria-pressed="${saved ? 'true' : 'false'}">${IG_ICONS.bookmark}</button>
    </div>
  </div>`;
}

function _newsCategoryLabel(n) {
  return (n?.category || 'Другое').trim() || 'Другое';
}

function _renderNewsCategoryFilters() {
  const root = document.getElementById('feed-news-category-filters');
  if (!root) return;
  const counts = {};
  _newsItems.forEach(n => {
    const cat = _newsCategoryLabel(n);
    counts[cat] = (counts[cat] || 0) + 1;
  });
  const cats = Object.keys(counts).sort((a, b) => a.localeCompare(b, 'ru'));
  if (!cats.length) {
    root.innerHTML = '';
    return;
  }
  if (_newsCategoryFilter !== 'all' && !counts[_newsCategoryFilter]) _newsCategoryFilter = 'all';
  root.innerHTML = [
    `<button type="button" class="feed-news-category-chip ${_newsCategoryFilter === 'all' ? 'active' : ''}" data-news-category="all">Все</button>`,
    ...cats.map(cat => `<button type="button" class="feed-news-category-chip ${_newsCategoryFilter === cat ? 'active' : ''}" data-news-category="${esc(cat)}">${esc(cat)} ${counts[cat]}</button>`),
  ].join('');
  root.querySelectorAll('.feed-news-category-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      _newsCategoryFilter = btn.dataset.newsCategory || 'all';
      hapticImpact('light');
      _renderNewsFromCache();
      resetFeedViewScroll();
    });
  });
}

async function reactNews(postId, reaction, btnEl) {
  if (reaction !== 'like') return;
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
    post.my_reaction = res.my_reaction;
    const card = btnEl.closest('.news-card');
    const likeBtn = card.querySelector('[data-news-reaction="like"]');
    if (likeBtn) {
      likeBtn.querySelector('span').textContent = post.likes || 0;
      likeBtn.classList.toggle('active', post.my_reaction === 'like');
    }
  } catch (e) {
    showToast('Ошибка: ' + e.message, 'error');
  }
}

function _visibleNewsEntries() {
  return _newsItems
    .map((n, index) => ({ n, index }))
    .filter(x => FEED_SAVED_FILTERS.news !== 'saved' || x.n.saved_by_me)
    .filter(x => _newsCategoryFilter === 'all' || _newsCategoryLabel(x.n) === _newsCategoryFilter);
}

function _renderMoreNews() {
  const list = document.getElementById('feed-news-list');
  const visible = _visibleNewsEntries();
  const nextBatch = visible.slice(_newsRenderedCount, _newsRenderedCount + NEWS_PAGE_SIZE);
  const html = nextBatch.map(x => _newsCardHtml(x.n, x.index)).join('');
  const moreEl = document.getElementById('news-load-more');
  if (moreEl) moreEl.insertAdjacentHTML('beforebegin', html);
  else list.insertAdjacentHTML('beforeend', html);
  _newsRenderedCount += nextBatch.length;
  if (moreEl) moreEl.style.display = _newsRenderedCount < visible.length ? 'block' : 'none';
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
      if (_newsRenderedCount < _visibleNewsEntries().length) _renderMoreNews();
    }
  });
}

function _renderNewsFromCache() {
  const list = document.getElementById('feed-news-list');
  if (!list) return;
  _updateFeedSavedCount('news', _newsItems.filter(n => n.saved_by_me).length);
  _renderNewsCategoryFilters();
  const visible = _visibleNewsEntries();
  _newsRenderedCount = 0;
  if (!visible.length) {
    list.innerHTML = FEED_SAVED_FILTERS.news === 'saved'
      ? '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Сохранённых новостей пока нет</div>'
      : (_newsCategoryFilter === 'all'
        ? '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">Сводка новостей появится в течение дня</div>'
        : '<div style="padding:2rem 0;text-align:center;color:var(--text-light)">В этой категории новостей пока нет</div>');
    return;
  }
  list.innerHTML = (FEED_SAVED_FILTERS.news === 'saved' ? '' : _renderDiscussingSection()) +
    '<div class="news-load-more" id="news-load-more" style="display:none">Загрузка…</div>';
  _renderMoreNews();
}

async function loadNewsFeed() {
  const list = document.getElementById('feed-news-list');
  try {
    const res = await api('/api/feed/news');
    _newsItems = res?.feed || [];
    _renderNewsFromCache();
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
    .filter(x => _newsCategoryFilter === 'all' || _newsCategoryLabel(x.n) === _newsCategoryFilter)
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
let _ncReplyTo = null; // Раунд 6 §5.1: "Ответить" в меню комментария (news поддерживает reply_to)
let _ncLoadSeq = 0;

function _commentInitials(name) {
  const clean = String(name || '').trim();
  if (!clean) return 'P';
  return clean.split(/\s+/).slice(0, 2).map(p => p[0]).join('').toUpperCase();
}

function _commentTime(c) {
  if (c.ts) return _fmtPhotoCommentTime(c.ts * 1000);
  return _fmtPhotoCommentTime(c.at);
}

function _renderUnifiedFeedComment(c, byId = {}) {
  const author = c.name || c.user_id || 'Сотрудник';
  const replyTo = c.reply_to ? byId[c.reply_to] : null;
  const replyName = c.reply_to_name || replyTo?.name || replyTo?.user_id || '';
  const replyPreview = replyTo?.text ? ` · ${String(replyTo.text).slice(0, 80)}` : '';
  return `<div class="pc-comment" data-comment-id="${c.id || ''}">
    <div class="pc-comment-avatar">${esc(_commentInitials(author))}</div>
    <div class="pc-comment-body">
      <div class="pc-comment-head"><b>${esc(author)}</b><span class="pc-comment-time">${_commentTime(c)}</span></div>
      ${replyName ? `<div class="pc-comment-reply">@${esc(replyName)}${esc(replyPreview)}</div>` : ''}
      <div class="pc-comment-text">${esc(c.text)}</div>
      <div class="pc-comment-footer">
        ${c.id ? `<button class="pc-comment-reply-btn" data-reply-comment="${c.id}" type="button">Ответить</button>` : ''}
      </div>
    </div>
    ${c.id ? `<button class="pc-comment-menu" data-menu-comment="${c.id}" type="button" aria-label="Действия">⋯</button>` : ''}
  </div>`;
}

function _commentPrefix(kind) {
  return kind === 'news' ? 'nc' : 'pc';
}

function _setFeedCommentReply(kind, comment) {
  if (kind === 'news') _ncReplyTo = comment.id;
  else _pcReplyTo = comment.id;
  const prefix = _commentPrefix(kind);
  const bar = document.getElementById(`${prefix}-reply-bar`);
  const input = document.getElementById(`${prefix}-comment-input`);
  if (bar) {
    bar.style.display = 'flex';
    bar.innerHTML = `<span class="pc-reply-bar-text">Ответ <b>${esc(comment.name || comment.user_id || 'Сотрудник')}</b>: ${esc(comment.text || '').slice(0, 90)}</span><button type="button" class="pc-reply-cancel" aria-label="Отменить ответ">×</button>`;
    bar.querySelector('.pc-reply-cancel')?.addEventListener('click', () => _clearFeedCommentReply(kind));
  }
  if (input) {
    input.placeholder = `Ответ ${comment.name || 'сотруднику'}…`;
    input.focus({ preventScroll: true });
  }
}

function _clearFeedCommentReply(kind) {
  if (kind === 'news') _ncReplyTo = null;
  else _pcReplyTo = null;
  const prefix = _commentPrefix(kind);
  const bar = document.getElementById(`${prefix}-reply-bar`);
  const input = document.getElementById(`${prefix}-comment-input`);
  if (bar) {
    bar.style.display = 'none';
    bar.innerHTML = '';
  }
  if (input) input.placeholder = 'Добавить комментарий…';
}

function _insertFeedQuickReaction(kind, emoji, btn) {
  const prefix = _commentPrefix(kind);
  const input = document.getElementById(`${prefix}-comment-input`);
  if (!input || !emoji) return;

  const start = typeof input.selectionStart === 'number' ? input.selectionStart : input.value.length;
  const end = typeof input.selectionEnd === 'number' ? input.selectionEnd : start;
  const before = input.value.slice(0, start);
  const after = input.value.slice(end);
  const leftGap = before && !/\s$/.test(before) ? ' ' : '';
  const rightGap = after && !/^\s/.test(after) ? ' ' : '';
  const insert = `${leftGap}${emoji}${rightGap}`;

  input.value = before + insert + after;
  const cursor = before.length + insert.length;
  input.focus({ preventScroll: true });
  input.dispatchEvent(new Event('input', { bubbles: true }));
  requestAnimationFrame(() => {
    try { input.setSelectionRange(cursor, cursor); } catch (e) {}
  });
  if (btn) {
    btn.classList.add('pc-quick-reaction-hit');
    setTimeout(() => btn.classList.remove('pc-quick-reaction-hit'), 160);
  }
  hapticImpact('light');
}

function _openFeedCommentModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return null;
  modal.classList.remove('pc-modal-open');
  modal.style.display = 'flex';
  document.documentElement.style.setProperty('--comment-keyboard-inset', '0px');
  requestAnimationFrame(() => {
    if (modal.style.display !== 'none') modal.classList.add('pc-modal-open');
  });
  return modal;
}

function _hideFeedCommentModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.classList.remove('pc-modal-open');
  document.documentElement.style.setProperty('--comment-keyboard-inset', '0px');
  setTimeout(() => {
    if (!modal.classList.contains('pc-modal-open')) modal.style.display = 'none';
  }, 180);
}

function _bindFeedCommentBackdropClose(modalId, closeFn) {
  const modal = document.getElementById(modalId);
  if (!modal || modal.dataset.backdropCloseWired) return;
  modal.dataset.backdropCloseWired = '1';

  let tapStart = null;
  let lastPointerCloseAt = 0;
  modal.addEventListener('pointerdown', (e) => {
    const target = e.target instanceof Element ? e.target : null;
    if (!target || target.closest('.pc-sheet, .pc-photo-nav')) {
      tapStart = null;
      return;
    }
    tapStart = { id: e.pointerId, x: e.clientX, y: e.clientY };
  });
  modal.addEventListener('pointerup', (e) => {
    if (!tapStart || tapStart.id !== e.pointerId) return;
    const moved = Math.abs(e.clientX - tapStart.x) + Math.abs(e.clientY - tapStart.y);
    tapStart = null;
    if (moved > 12) return;
    e.preventDefault();
    lastPointerCloseAt = Date.now();
    closeFn();
  });
  modal.addEventListener('click', (e) => {
    if (Date.now() - lastPointerCloseAt < 350) return;
    const target = e.target instanceof Element ? e.target : null;
    if (!target || target.closest('.pc-sheet, .pc-photo-nav')) return;
    e.preventDefault();
    closeFn();
  });
  modal.addEventListener('pointercancel', () => { tapStart = null; });
  modal.querySelector('.pc-sheet')?.addEventListener('pointerdown', e => e.stopPropagation());
}

function _scrollFeedCommentsToBottom(listId) {
  const list = document.getElementById(listId);
  if (!list) return;
  const scroll = () => { list.scrollTop = list.scrollHeight; };
  requestAnimationFrame(() => requestAnimationFrame(scroll));
  setTimeout(scroll, 140);
  setTimeout(scroll, 320);
  setTimeout(scroll, 700);
}

function _renderFeedCommentList(kind, comments) {
  const list = document.getElementById(kind === 'news' ? 'nc-list' : 'pc-list');
  if (!list) return;
  const byId = {};
  (comments || []).forEach(c => { byId[c.id] = c; });
  (comments || []).forEach(c => { if (c.reply_to && byId[c.reply_to]) c.reply_to_name = byId[c.reply_to].name; });
  const emptyColor = kind === 'news' ? 'var(--text-light)' : 'rgba(255,255,255,0.58)';
  list.innerHTML = (comments || []).map(c => _renderUnifiedFeedComment(c, byId)).join('') ||
    `<div style="color:${emptyColor};font-size:0.95rem;padding:1rem 0">Пока нет комментариев. Будьте первым.</div>`;
  list.querySelectorAll('[data-reply-comment]').forEach(btn => {
    btn.addEventListener('click', () => {
      const c = byId[btn.dataset.replyComment];
      if (c) _setFeedCommentReply(kind, c);
    });
  });
  list.querySelectorAll('[data-menu-comment]').forEach(btn => {
    btn.addEventListener('click', () => {
      const c = byId[btn.dataset.menuComment];
      if (!c) return;
      _openCommentActions({
        sourceType: kind, sourceId: kind === 'news' ? _ncCurrentPostId : _pcCurrentPhotoId, comment: c,
        canDelete: String(c.user_id) === String(_feedMyId) || currentRole === 'owner',
        onDelete: () => kind === 'news' ? _deleteNewsComment(c.id) : _deletePhotoComment(c.id),
        onReply: () => _setFeedCommentReply(kind, c),
        inputId: kind === 'news' ? 'nc-comment-input' : 'pc-comment-input',
      });
    });
  });
}

async function _renderNewsCommentsList(expectedPostId = _ncCurrentPostId, expectedSeq = _ncLoadSeq) {
  const data = await api(`/api/feed/news/${expectedPostId}/comments`);
  if (expectedSeq !== _ncLoadSeq || _ncCurrentPostId !== expectedPostId) return;
  _renderFeedCommentList('news', data.comments || []);
}

async function _deleteNewsComment(commentId) {
  if (!_ncCurrentPostId) return;
  const postId = _ncCurrentPostId;
  const seq = _ncLoadSeq;
  try {
    await api(`/api/feed/news/${postId}/comments/${commentId}`, { method: 'DELETE' });
    hapticImpact('light');
    await _renderNewsCommentsList(postId, seq);
  } catch (e) {
    showToast('Ошибка удаления: ' + e.message, 'error');
  }
}

async function openNewsComments(postId) {
  const seq = ++_ncLoadSeq;
  _ncCurrentPostId = postId;
  _clearFeedCommentReply('news');
  _markCommentActivityRead('news_comment', postId); // §5.2/§5.3: открытие обсуждения = прочитано
  const post = _newsItems.find(n => n.id === postId);
  document.getElementById('nc-title').textContent = post ? post.title : 'Обсуждение';
  const list = document.getElementById('nc-list');
  list.innerHTML = '<div style="padding:1rem;color:var(--text-light);text-align:center">Загрузка...</div>';
  const input = document.getElementById('nc-comment-input');
  if (input) input.value = '';
  const modal = _openFeedCommentModal('news-comments-modal');
  if (typeof NavigationManager !== 'undefined' && !_ncOverlayUnregister) {
    _ncOverlayUnregister = NavigationManager.registerOverlay(() => _closeNewsCommentsInternal());
  }
  try {
    await _ensureFeedMyId();
    if (seq !== _ncLoadSeq || _ncCurrentPostId !== postId) return;
    await _renderNewsCommentsList(postId, seq);
  } catch (e) {
    if (seq !== _ncLoadSeq || _ncCurrentPostId !== postId) return;
    list.innerHTML = `<div style="color:var(--red)">Ошибка: ${esc(e.message)}</div>`;
  }
}

function _closeNewsCommentsInternal() {
  _ncLoadSeq++;
  _hideFeedCommentModal('news-comments-modal');
  _ncCurrentPostId = null;
  _clearFeedCommentReply('news');
  _ncOverlayUnregister = null;
}

function closeNewsComments() {
  _ncLoadSeq++;
  if (_ncOverlayUnregister) { _ncOverlayUnregister(); _ncOverlayUnregister = null; }
  _hideFeedCommentModal('news-comments-modal');
  _ncCurrentPostId = null;
  _clearFeedCommentReply('news');
}

async function _sendNewsComment() {
  const input = document.getElementById('nc-comment-input');
  const btn = document.getElementById('nc-comment-send-btn');
  const text = input.value.trim();
  if (!text || !_ncCurrentPostId || (btn && btn.disabled)) return;
  const postId = _ncCurrentPostId;
  const seq = _ncLoadSeq;
  if (btn) btn.disabled = true;
  try {
    const data = await api(`/api/feed/news/${postId}/comments`, { method: 'POST', body: JSON.stringify({ text, reply_to: _ncReplyTo || undefined }) });
    if (seq !== _ncLoadSeq || _ncCurrentPostId !== postId) return;
    input.value = '';
    _clearFeedCommentReply('news');
    hapticImpact('light');
    _renderFeedCommentList('news', data.comments || []);
    _scrollFeedCommentsToBottom('nc-list');
    // обновить счётчик на карточке + «обсуждают» без перезагрузки всей ленты
    const post = _newsItems.find(n => n.id === postId);
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
  const root = getFeedRoot();
  const switcher = root.querySelector('.doc-type-opt[data-feed]');
  if (!switcher) return;
  root.querySelectorAll('.doc-type-opt[data-feed]').forEach(opt => {
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

    const current = getFeedRoot().querySelector('.doc-type-opt[data-feed].active')?.dataset.feed || 'photos';
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
  // Phase 3: default active sub-tab is Фото (first in FEED_TABS), sub-tabs live in #view-feed.
  // loadWeatherFeed() always runs for the weather widget; active content loads on demand.
  loadWeatherFeed();
  const active = getFeedRoot().querySelector('.doc-type-opt[data-feed].active')?.dataset.feed || 'photos';
  if (active === 'news') loadNewsFeed();
  if (active === 'photos') loadFeedPhotos();
  _initFeedSwitch();
  _initFeedSavedFilters();
  _initFeedSwipe();
  _loadFeedTabBadges();
}

// Public API: called by switchView('feed') in app.html.
function initFeedView() {
  resetFeedViewScroll();
  initFeedTabs();
  requestAnimationFrame(resetFeedViewScroll);
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
let _pcReplyTo = null;
let _pcLoadSeq = 0;

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

async function _deletePhotoComment(commentId) {
  if (!_pcCurrentPhotoId) return;
  const photoId = _pcCurrentPhotoId;
  const seq = _pcLoadSeq;
  try {
    await api(`/api/feed/photos/${photoId}/comments/${commentId}`, { method: 'DELETE' });
    hapticImpact('light');
    await _renderPhotoCommentsList(photoId, seq);
    loadFeedPhotos();
  } catch (e) {
    showToast('Ошибка удаления: ' + e.message, 'error');
  }
}

async function _renderPhotoCommentsList(expectedPhotoId = _pcCurrentPhotoId, expectedSeq = _pcLoadSeq) {
  const data = await api(`/api/feed/photos/${expectedPhotoId}/comments`);
  if (expectedSeq !== _pcLoadSeq || _pcCurrentPhotoId !== expectedPhotoId) return;
  _renderFeedCommentList('photo', data.comments || []);
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
  const seq = ++_pcLoadSeq;
  // 24.07: мультифото — fileCount передаётся с карточки ленты (renderPhotoItem уже
  // знает p.files.length); если вызвано без него (старый путь), считаем 1 фото.
  _pcCurrentPhotoId = photoId;
  _pcFileCount = fileCount || 1;
  _clearFeedCommentReply('photo');
  _markCommentActivityRead('photo_comment', photoId); // §5.2/§5.3
  const photo = document.getElementById('pc-photo');
  if (photo) photo.removeAttribute('src');
  const list = document.getElementById('pc-list');
  list.innerHTML = '<div style="padding:1rem;color:rgba(255,255,255,0.58);text-align:center">Загрузка...</div>';
  const input = document.getElementById('pc-comment-input');
  if (input) input.value = '';
  _pcRenderPhotoAt(0);
  const modal = _openFeedCommentModal('photo-comments-modal');
  // 25.07: модалка теперь зарегистрирована в NavigationManager.overlayStack -- раньше
  // Telegram BackButton её не видел (display-toggle вне навигации), при нажатии "назад"
  // NavigationManager.back() падал сразу на pop реального route-стека, закрывая не эту
  // модалку, а уводя на предыдущий экран (баг: Back из комментариев кидал в Профиль).
  if (typeof NavigationManager !== 'undefined' && !_pcOverlayUnregister) {
    _pcOverlayUnregister = NavigationManager.registerOverlay(() => _closePhotoCommentsInternal());
  }
  try {
    await _ensureFeedMyId();
    if (seq !== _pcLoadSeq || _pcCurrentPhotoId !== photoId) return;
    await _renderPhotoCommentsList(photoId, seq);
  } catch (e) {
    if (seq !== _pcLoadSeq || _pcCurrentPhotoId !== photoId) return;
    list.innerHTML = `<div style="color:var(--red)">Ошибка: ${esc(e.message)}</div>`;
  }
}

// Вызывается ТОЛЬКО из NavigationManager (top.close()) — модалка уже popped из
// overlayStack на этот момент, повторный unregister тут не нужен и не должен вызываться.
function _closePhotoCommentsInternal() {
  _pcLoadSeq++;
  _hideFeedCommentModal('photo-comments-modal');
  _pcCurrentPhotoId = null;
  _clearFeedCommentReply('photo');
  _pcOverlayUnregister = null;
}

// Вызывается при ручном закрытии (крестик/клик-вне) — модалка ещё в overlayStack,
// нужно явно её оттуда снять, иначе следующий Back попытается закрыть уже закрытую модалку.
function closePhotoComments() {
  _pcLoadSeq++;
  if (_pcOverlayUnregister) { _pcOverlayUnregister(); _pcOverlayUnregister = null; }
  _hideFeedCommentModal('photo-comments-modal');
  _pcCurrentPhotoId = null;
  _clearFeedCommentReply('photo');
}

async function _sendPhotoComment() {
  const input = document.getElementById('pc-comment-input');
  const btn = document.getElementById('pc-comment-send-btn');
  const text = input.value.trim();
  // 31.07 (UX-аудит): btn.disabled guard -- быстрый двойной тап отправлял 2
  // одинаковых комментария до возврата первого ответа.
  if (!text || !_pcCurrentPhotoId || (btn && btn.disabled)) return;
  const photoId = _pcCurrentPhotoId;
  const seq = _pcLoadSeq;
  if (btn) btn.disabled = true;
  try {
    const data = await api(`/api/feed/photos/${photoId}/comments`, { method: 'POST', body: JSON.stringify({ text, reply_to: _pcReplyTo || undefined }) });
    if (seq !== _pcLoadSeq || _pcCurrentPhotoId !== photoId) return;
    input.value = '';
    _clearFeedCommentReply('photo');
    hapticImpact('light');
    _renderFeedCommentList('photo', data.comments || []);
    _scrollFeedCommentsToBottom('pc-list');
    loadFeedPhotos().catch(() => {}); // обновить счётчик комментариев в ленте
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
  const pcSendBtn = document.getElementById('pc-comment-send-btn');
  const pcInput = document.getElementById('pc-comment-input');
  if (pcSendBtn && pcInput && typeof _bindTouchSafeSend === 'function') {
    _bindTouchSafeSend(pcSendBtn, pcInput, _sendPhotoComment);
  } else {
    pcSendBtn?.addEventListener('click', _sendPhotoComment);
  }
  document.getElementById('pc-photo-prev')?.addEventListener('click', _pcGoPrev);
  document.getElementById('pc-photo-next')?.addEventListener('click', _pcGoNext);
  _bindFeedCommentBackdropClose('photo-comments-modal', closePhotoComments);

  // Раунд 5 §8: комментарии к новости — те же обработчики (закрытие/отправка), что фото.
  document.getElementById('nc-back-btn')?.addEventListener('click', closeNewsComments);
  const ncSendBtn = document.getElementById('nc-comment-send-btn');
  const ncInput = document.getElementById('nc-comment-input');
  if (ncSendBtn && ncInput && typeof _bindTouchSafeSend === 'function') {
    _bindTouchSafeSend(ncSendBtn, ncInput, _sendNewsComment);
  } else {
    ncSendBtn?.addEventListener('click', _sendNewsComment);
  }
  _bindFeedCommentBackdropClose('news-comments-modal', closeNewsComments);
  document.querySelectorAll('.pc-quick-reactions').forEach(row => {
    row.addEventListener('pointerdown', e => e.preventDefault());
    row.addEventListener('click', (e) => {
      const target = e.target instanceof Element ? e.target : null;
      const btn = target?.closest('.pc-quick-reaction');
      if (!btn) return;
      _insertFeedQuickReaction(row.dataset.commentKind || 'photo', btn.dataset.emoji || btn.textContent.trim(), btn);
    });
  });

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

// ─────────────────── Раунд 6 §5.1: меню действий комментария + пересылка ───────────────────
// Меню: Ответить / Копировать / Переслать / Удалить (Удалить — только автор/Owner).
// Переслать открывает существующий список чатов (общий/личный/объект/дефект/потребность)
// и шлёт серверную карточку через /api/comments/forward (текст строится на backend).
let _commentActionOverlayUnregister = null;

function _closeCommentActionOverlay() {
  document.querySelectorAll('.comment-action-sheet, .comment-action-backdrop').forEach(el => el.remove());
  if (_commentActionOverlayUnregister) { const u = _commentActionOverlayUnregister; _commentActionOverlayUnregister = null; u(); }
}

function _openCommentActions({ sourceType, sourceId, comment, canDelete, onDelete, onReply, inputId }) {
  _closeCommentActionOverlay();
  const backdrop = document.createElement('div');
  backdrop.className = 'comment-action-backdrop';
  const sheet = document.createElement('div');
  sheet.className = 'comment-action-sheet';
  sheet.innerHTML = `
    <button type="button" class="comment-action-item" data-act="reply">Ответить</button>
    <button type="button" class="comment-action-item" data-act="copy">Копировать</button>
    <button type="button" class="comment-action-item" data-act="forward">Переслать</button>
    ${canDelete ? '<button type="button" class="comment-action-item comment-action-danger" data-act="delete">Удалить</button>' : ''}
    <button type="button" class="comment-action-item comment-action-cancel" data-act="cancel">Отмена</button>`;
  document.body.appendChild(backdrop);
  document.body.appendChild(sheet);

  const close = () => _closeCommentActionOverlay();
  if (typeof NavigationManager !== 'undefined') {
    _commentActionOverlayUnregister = NavigationManager.registerOverlay(() => {
      document.querySelectorAll('.comment-action-sheet, .comment-action-backdrop').forEach(el => el.remove());
      _commentActionOverlayUnregister = null;
    });
  }
  backdrop.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    close();
  });
  backdrop.addEventListener('click', close);
  sheet.addEventListener('pointerdown', e => e.stopPropagation());
  sheet.querySelectorAll('.comment-action-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const act = btn.dataset.act;
      close();
      if (act === 'reply') { if (onReply) onReply(); }
      else if (act === 'copy') {
        try { navigator.clipboard.writeText(comment.text || ''); showToast('Скопировано в буфер', 'success'); } catch (e) {}
      } else if (act === 'forward') {
        _openCommentForwardPicker(sourceType, sourceId, comment.id);
      } else if (act === 'delete') { if (onDelete) onDelete(); }
    });
  });
}

async function _openCommentForwardPicker(sourceType, sourceId, commentId) {
  _closeCommentActionOverlay();
  const backdrop = document.createElement('div');
  backdrop.className = 'comment-action-backdrop';
  const modal = document.createElement('div');
  modal.className = 'comment-action-sheet comment-forward-picker';
  modal.innerHTML = '<div class="comment-forward-title">Переслать в…</div><div class="comment-forward-list">Загрузка…</div>';
  document.body.appendChild(backdrop);
  document.body.appendChild(modal);

  let unregister = null;
  const close = () => {
    backdrop.remove(); modal.remove();
    if (unregister) { unregister(); unregister = null; }
  };
  if (typeof NavigationManager !== 'undefined') unregister = NavigationManager.registerOverlay(close);
  backdrop.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    close();
  });
  backdrop.addEventListener('click', close);
  modal.addEventListener('pointerdown', e => e.stopPropagation());

  const destinations = [{ id: null, thread_key: null, title: 'Общий чат' }];
  try {
    const threads = await api('/api/chat/threads');
    (threads.threads || []).forEach(t => {
      if (t.type === 'GENERAL') return;
      if (t.type === 'DIRECT') destinations.push({ id: t.id, thread_key: null, title: t.title });
      else destinations.push({ id: null, thread_key: t.id, title: t.title });
    });
  } catch (e) {
    showToast('Не удалось загрузить список чатов: ' + e.message, 'error');
  }

  const listEl = modal.querySelector('.comment-forward-list');
  listEl.innerHTML = destinations.map((d, i) => `<button type="button" class="comment-forward-dest" data-idx="${i}">${esc(d.title)}</button>`).join('');
  listEl.querySelectorAll('.comment-forward-dest').forEach(btn => {
    btn.addEventListener('click', async () => {
      const dest = destinations[Number(btn.dataset.idx)];
      close();
      try {
        await api('/api/comments/forward', {
          method: 'POST',
          body: JSON.stringify({
            source_type: sourceType, source_id: sourceId, comment_id: commentId,
            to_user_id: dest.id, thread_key: dest.thread_key,
          }),
        });
        showToast('Комментарий переслан', 'success');
        hapticImpact('light');
      } catch (e) {
        showToast('Ошибка пересылки: ' + e.message, 'error');
      }
    });
  });
}

// §5.2/§5.3: после реального открытия обсуждения помечаем activity-алерты прочитанными.
async function _markCommentActivityRead(kind, refId) {
  if (!refId) return;
  try {
    await api('/api/activity-alerts/read', { method: 'POST', body: JSON.stringify({ kind, ref_id: String(refId) }) });
    if (typeof _loadHomeAlerts === 'function') _loadHomeAlerts();
  } catch (e) { /* не критично */ }
}
