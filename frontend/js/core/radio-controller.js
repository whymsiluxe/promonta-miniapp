// RadioController — единственный источник состояния воспроизведения радио (25.07 v2).
// Заменяет старую radio.js (глобальный floating orb) полностью: один Audio-элемент,
// один набор listeners (не пересоздаются при повторном заходе на Home), состояние
// читают HomeRadioPlayer (внутри Home) и RadioMiniPlayer (над bottom-nav на остальных
// экранах, пока играет). Реальные станции -- поток Radio Record (Techno/Гоп FM/Rap/Deep),
// все live-стримы без duration/seek -- только LIVE-режим, TRACK-режим (progress bar с
// current/duration) в этом контроллере не нужен, добавлять его без реального трек-источника
// с длительностью означало бы fake progress (явно запрещено).

const RADIO_STATIONS = [
  { id: 'techno', name: 'Techno', url: 'https://radiorecord.hostingradio.ru/techno96.aacp' },
  { id: 'gop', name: 'Гоп FM', url: 'https://radiorecord.hostingradio.ru/gop96.aacp' },
  { id: 'rap', name: 'Rap', url: 'https://radiorecord.hostingradio.ru/rap96.aacp' },
  { id: 'deep', name: 'Deep', url: 'https://radiorecord.hostingradio.ru/deep96.aacp' },
];

const RadioController = (() => {
  let audio = null;
  let stationIdx = -1; // -1 = ничего не выбрано
  let state = 'IDLE'; // IDLE | LOADING | PLAYING | PAUSED | BUFFERING | ERROR | OFFLINE
  const listeners = new Set();

  function _emit() {
    listeners.forEach(fn => { try { fn(getState()); } catch (e) {} });
  }

  function getState() {
    return {
      state,
      station: stationIdx >= 0 ? RADIO_STATIONS[stationIdx] : null,
      stationIdx,
    };
  }

  function subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  function _ensureAudio() {
    if (audio) return audio;
    audio = new Audio();
    audio.preload = 'none';
    audio.addEventListener('waiting', () => { state = 'BUFFERING'; _emit(); });
    audio.addEventListener('playing', () => { state = 'PLAYING'; _emit(); });
    audio.addEventListener('pause', () => {
      // pause() тоже стреляет на audio.src='' (stop) -- не путаем со state PAUSED,
      // тот ставится явно из pause()-обёртки контроллера, не отсюда.
    });
    audio.addEventListener('error', () => {
      state = 'ERROR';
      _emit();
    });
    return audio;
  }

  function play(idx) {
    if (!navigator.onLine) { state = 'OFFLINE'; _emit(); return; }
    const station = RADIO_STATIONS[idx];
    if (!station) return;
    stationIdx = idx;
    state = 'LOADING';
    _emit();
    const a = _ensureAudio();
    a.src = station.url;
    a.play().then(() => {
      state = 'PLAYING';
      _emit();
    }).catch(() => {
      state = 'ERROR';
      _emit();
    });
  }

  function pause() {
    if (!audio) return;
    audio.pause();
    state = 'PAUSED';
    _emit();
  }

  function resume() {
    if (!audio || stationIdx < 0) return;
    state = 'LOADING';
    _emit();
    audio.play().then(() => { state = 'PLAYING'; _emit(); }).catch(() => { state = 'ERROR'; _emit(); });
  }

  function stop() {
    if (audio) {
      audio.pause();
      audio.src = '';
    }
    stationIdx = -1;
    state = 'IDLE';
    _emit();
  }

  function next() {
    if (RADIO_STATIONS.length < 2) return;
    const idx = stationIdx < 0 ? 0 : (stationIdx + 1) % RADIO_STATIONS.length;
    play(idx);
  }

  function previous() {
    if (RADIO_STATIONS.length < 2) return;
    const idx = stationIdx < 0 ? 0 : (stationIdx - 1 + RADIO_STATIONS.length) % RADIO_STATIONS.length;
    play(idx);
  }

  function retry() {
    if (stationIdx >= 0) play(stationIdx);
  }

  window.addEventListener('offline', () => {
    if (state === 'PLAYING' || state === 'LOADING' || state === 'BUFFERING') {
      state = 'OFFLINE';
      _emit();
    }
  });
  window.addEventListener('online', () => {
    if (state === 'OFFLINE' && stationIdx >= 0) retry();
  });

  return { getState, subscribe, play, pause, resume, stop, next, previous, retry, stations: RADIO_STATIONS };
})();
