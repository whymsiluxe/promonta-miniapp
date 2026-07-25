// HomeRadioPlayer + RadioMiniPlayer (25.07 v2) -- заменяют старый radio.js floating orb.
// Оба компонента подписаны на один RadioController (radio-controller.js), не создают
// собственных Audio-элементов. HomeRadioPlayer рендерится статично внутри Home dashboard
// (home.js вызывает renderHomeRadioPlayer() один раз), RadioMiniPlayer -- глобальный
// singleton-узел в <body>, видимый только когда играет/на паузе и мы не на Home.

const RADIO_ICON_PREV = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M18 6L9 12l9 6V6z" fill="currentColor"/><rect x="5" y="6" width="2" height="12" fill="currentColor"/></svg>';
const RADIO_ICON_NEXT = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M6 6l9 6-9 6V6z" fill="currentColor"/><rect x="17" y="6" width="2" height="12" fill="currentColor"/></svg>';
const RADIO_ICON_PLAY = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none"><path d="M7 5.5v13l11-6.5-11-6.5z" fill="currentColor"/></svg>';
const RADIO_ICON_PAUSE = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none"><rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor"/><rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor"/></svg>';
const RADIO_ICON_CLOSE = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M5 5l14 14M19 5L5 19" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
const RADIO_ICON_WAVE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><rect x="4" y="10" width="2.5" height="4" fill="currentColor"><animate attributeName="height" values="4;12;4" dur="0.9s" repeatCount="indefinite"/><animate attributeName="y" values="10;6;10" dur="0.9s" repeatCount="indefinite"/></rect><rect x="10.5" y="7" width="2.5" height="10" fill="currentColor"><animate attributeName="height" values="10;16;10" dur="0.9s" begin="0.15s" repeatCount="indefinite"/><animate attributeName="y" values="7;4;7" dur="0.9s" begin="0.15s" repeatCount="indefinite"/></rect><rect x="17" y="9" width="2.5" height="6" fill="currentColor"><animate attributeName="height" values="6;14;6" dur="0.9s" begin="0.3s" repeatCount="indefinite"/><animate attributeName="y" values="9;5;9" dur="0.9s" begin="0.3s" repeatCount="indefinite"/></rect></svg>';

function _radioStateLabel(s) {
  if (s.state === 'LOADING') return 'Подключение…';
  if (s.state === 'BUFFERING') return 'Буферизация…';
  if (s.state === 'ERROR') return 'Не удалось запустить радио';
  if (s.state === 'OFFLINE') return 'Нет подключения к интернету';
  if (s.state === 'PLAYING') return 'В эфире';
  if (s.state === 'PAUSED') return 'На паузе';
  return 'Выберите станцию';
}

// ── HomeRadioPlayer ──
// Worker Home перерисовывает весь dashboard-slot на каждый заход (initWorkerHomeView,
// без lazy-init guard, т.к. статус смены должен быть свежим) -- без unsubscribe тут
// плодились бы новые RadioController-подписки на каждый визит на Home.
let _homeRadioUnsubscribe = null;

function renderHomeRadioPlayer() {
  const mount = document.getElementById('home-radio-player-mount');
  if (!mount) return;
  if (_homeRadioUnsubscribe) { _homeRadioUnsubscribe(); _homeRadioUnsubscribe = null; }
  mount.innerHTML = `
    <div class="home-radio-player" id="home-radio-player">
      <div class="home-radio-glow"></div>
      <div class="home-radio-top">
        <div class="home-radio-title" id="home-radio-title">PROMONTA RADIO</div>
        <div class="home-radio-sub" id="home-radio-sub">Выберите станцию</div>
      </div>
      <div class="home-radio-controls">
        <button class="home-radio-ctrl-btn" id="home-radio-prev" type="button" aria-label="Предыдущая станция">${RADIO_ICON_PREV}</button>
        <button class="home-radio-play-btn" id="home-radio-playpause" type="button" aria-label="Воспроизвести">${RADIO_ICON_PLAY}</button>
        <button class="home-radio-ctrl-btn" id="home-radio-next" type="button" aria-label="Следующая станция">${RADIO_ICON_NEXT}</button>
      </div>
      <div class="home-radio-stations" id="home-radio-stations" aria-live="off">
        ${RadioController.stations.map((s, i) => `<button class="home-radio-station-chip" type="button" data-station-idx="${i}">${esc(s.name)}</button>`).join('')}
      </div>
      <div class="home-radio-status-row">
        <span class="home-radio-live-dot" id="home-radio-live-dot" style="display:none;"></span>
        <span id="home-radio-status" aria-live="polite">Выберите станцию</span>
      </div>
    </div>
  `;

  document.getElementById('home-radio-playpause').addEventListener('click', () => {
    const s = RadioController.getState();
    if (s.state === 'PLAYING' || s.state === 'BUFFERING' || s.state === 'LOADING') {
      RadioController.pause();
    } else if (s.state === 'PAUSED') {
      RadioController.resume();
    } else if (s.state === 'ERROR' || s.state === 'OFFLINE') {
      RadioController.retry();
    } else {
      RadioController.play(0);
    }
    hapticImpact('light');
  });
  document.getElementById('home-radio-prev').addEventListener('click', () => { RadioController.previous(); hapticImpact('light'); });
  document.getElementById('home-radio-next').addEventListener('click', () => { RadioController.next(); hapticImpact('light'); });
  document.getElementById('home-radio-stations').addEventListener('click', (e) => {
    const btn = e.target.closest('.home-radio-station-chip');
    if (!btn) return;
    RadioController.play(Number(btn.dataset.stationIdx));
    hapticImpact('light');
  });

  _homeRadioUnsubscribe = RadioController.subscribe(_updateHomeRadioUi);
  _updateHomeRadioUi(RadioController.getState());
}

function _updateHomeRadioUi(s) {
  const root = document.getElementById('home-radio-player');
  if (!root) return; // ушли с Home, mount уже не в DOM -- подписка просто no-op'ит
  const sub = document.getElementById('home-radio-sub');
  const playBtn = document.getElementById('home-radio-playpause');
  const statusEl = document.getElementById('home-radio-status');
  const liveDot = document.getElementById('home-radio-live-dot');
  const playing = s.state === 'PLAYING' || s.state === 'BUFFERING' || s.state === 'LOADING';

  sub.textContent = s.station ? s.station.name : 'Выберите станцию ниже';
  playBtn.innerHTML = playing ? RADIO_ICON_PAUSE : RADIO_ICON_PLAY;
  playBtn.setAttribute('aria-label', playing ? 'Пауза' : 'Воспроизвести');
  playBtn.classList.toggle('is-loading', s.state === 'LOADING' || s.state === 'BUFFERING');
  statusEl.textContent = _radioStateLabel(s);
  liveDot.style.display = s.state === 'PLAYING' ? 'inline-block' : 'none';
  root.classList.toggle('is-error', s.state === 'ERROR' || s.state === 'OFFLINE');

  document.querySelectorAll('.home-radio-station-chip').forEach((chip, i) => {
    chip.classList.toggle('active', i === s.stationIdx);
  });
}

// ── RadioMiniPlayer ── глобальный singleton, виден над bottom-nav только пока
// играет/на паузе и мы не на Home (там уже виден большой HomeRadioPlayer).
function initRadioMiniPlayer() {
  if (document.getElementById('radio-mini-player')) return;
  const el = document.createElement('div');
  el.id = 'radio-mini-player';
  el.className = 'radio-mini-player';
  el.style.display = 'none';
  el.innerHTML = `
    <span class="radio-mini-wave">${RADIO_ICON_WAVE}</span>
    <span class="radio-mini-title" id="radio-mini-title"></span>
    <button class="radio-mini-btn" id="radio-mini-playpause" type="button" aria-label="Пауза">${RADIO_ICON_PAUSE}</button>
    <button class="radio-mini-btn" id="radio-mini-close" type="button" aria-label="Закрыть">${RADIO_ICON_CLOSE}</button>
  `;
  document.body.appendChild(el);

  document.getElementById('radio-mini-playpause').addEventListener('click', () => {
    const s = RadioController.getState();
    if (s.state === 'PLAYING' || s.state === 'BUFFERING' || s.state === 'LOADING') RadioController.pause();
    else RadioController.resume();
    hapticImpact('light');
  });
  document.getElementById('radio-mini-close').addEventListener('click', () => {
    RadioController.stop();
    hapticImpact('light');
  });

  RadioController.subscribe(_updateRadioMiniPlayer);
  _updateRadioMiniPlayer(RadioController.getState());
}

function _updateRadioMiniPlayer(s) {
  const el = document.getElementById('radio-mini-player');
  if (!el) return;
  const onHome = document.getElementById('view-home')?.classList.contains('active');
  const shouldShow = s.state !== 'IDLE' && !onHome && !document.body.classList.contains('keyboard-open')
    && !document.body.classList.contains('chat-dialog-open');
  el.style.display = shouldShow ? 'flex' : 'none';
  if (!shouldShow) return;

  document.getElementById('radio-mini-title').textContent = s.station ? s.station.name : '';
  const playBtn = document.getElementById('radio-mini-playpause');
  const playing = s.state === 'PLAYING' || s.state === 'BUFFERING' || s.state === 'LOADING';
  playBtn.innerHTML = playing ? RADIO_ICON_PAUSE : RADIO_ICON_PLAY;
  playBtn.setAttribute('aria-label', playing ? 'Пауза' : 'Воспроизвести');
}

// switchView() (app.html) должен дёргать это при каждой смене экрана, чтобы mini-player
// появлялся/скрывался корректно (Home <-> остальные, модалки/keyboard уже проверяются
// внутри _updateRadioMiniPlayer через body-классы).
function refreshRadioMiniPlayerVisibility() {
  _updateRadioMiniPlayer(RadioController.getState());
}

document.addEventListener('DOMContentLoaded', initRadioMiniPlayer);
