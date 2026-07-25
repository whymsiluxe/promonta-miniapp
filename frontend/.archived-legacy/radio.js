// Radio Record — floating mini-player поверх всего приложения (DESIGN_REFS batch 13).
// Тап по кнопке → открывает/закрывает список станций. Тап по станции в списке → играет.
// Тап по станции, которая уже играет (в списке или через ✕) → стоп.
// У Radio Record нет канала «Шансон» — ближайший по жанру «Гоп FM» (см. HANDOFF).

const RADIO_STREAMS = [
  { name: 'Techno', url: 'https://radiorecord.hostingradio.ru/techno96.aacp' },
  { name: 'Гоп FM', url: 'https://radiorecord.hostingradio.ru/gop96.aacp' },
  { name: 'Rap', url: 'https://radiorecord.hostingradio.ru/rap96.aacp' },
  { name: 'Deep', url: 'https://radiorecord.hostingradio.ru/deep96.aacp' },
];

let _radioAudio = null;
let _radioIdx = -1; // -1 = выключено
let _radioMenuOpen = false;

function initRadioPlayer() {
  if (document.getElementById('radio-fab')) return;
  const fab = document.createElement('div');
  fab.id = 'radio-fab';
  fab.innerHTML = `
    <div class="radio-fab-menu" id="radio-fab-menu" style="display:none">
      ${RADIO_STREAMS.map((s, i) => `
        <button class="radio-fab-menu-item" type="button" data-idx="${i}">${s.name}</button>
      `).join('')}
    </div>
    <div class="radio-fab-row">
      <button class="radio-fab-btn" id="radio-fab-btn" type="button" aria-label="Радио">
        <span class="radio-fab-icon" id="radio-fab-icon">📻</span>
      </button>
      <span class="radio-fab-label" id="radio-fab-label" style="display:none"></span>
      <button class="radio-fab-stop" id="radio-fab-stop" type="button" aria-label="Стоп" style="display:none">✕</button>
    </div>
  `;
  document.body.appendChild(fab);
  document.getElementById('radio-fab-btn').addEventListener('click', _radioToggleMenu);
  document.getElementById('radio-fab-stop').addEventListener('click', _radioStop);
  document.getElementById('radio-fab-menu').addEventListener('click', _radioMenuTap);
  document.addEventListener('click', (e) => {
    if (_radioMenuOpen && !fab.contains(e.target)) _radioCloseMenu();
  });
}

function _radioToggleMenu(e) {
  e.stopPropagation();
  if (_radioMenuOpen) {
    _radioCloseMenu();
  } else {
    _radioOpenMenu();
  }
}

function _radioOpenMenu() {
  _radioMenuOpen = true;
  const menu = document.getElementById('radio-fab-menu');
  menu.style.display = 'flex';
  menu.querySelectorAll('.radio-fab-menu-item').forEach((btn) => {
    const idx = Number(btn.dataset.idx);
    btn.classList.toggle('playing', idx === _radioIdx);
  });
  hapticImpact('light');
}

function _radioCloseMenu() {
  _radioMenuOpen = false;
  document.getElementById('radio-fab-menu').style.display = 'none';
}

function _radioMenuTap(e) {
  const btn = e.target.closest('.radio-fab-menu-item');
  if (!btn) return;
  const idx = Number(btn.dataset.idx);
  if (idx === _radioIdx) {
    _radioStop();
  } else {
    _radioPlay(idx);
  }
  _radioCloseMenu();
}

function _radioPlay(idx) {
  const stream = RADIO_STREAMS[idx];
  _radioIdx = idx;
  if (!_radioAudio) {
    _radioAudio = new Audio();
    _radioAudio.preload = 'none';
  }
  _radioAudio.src = stream.url;
  _radioAudio.play().catch(() => {
    _radioUi(false);
    _radioIdx = -1;
    showToast('Поток радио недоступен', 'error');
  });
  _radioUi(true, stream.name);
  hapticImpact('light');
}

function _radioStop(e) {
  if (e) e.stopPropagation();
  if (_radioAudio) {
    _radioAudio.pause();
    _radioAudio.src = '';
  }
  _radioIdx = -1;
  _radioUi(false);
  hapticImpact('light');
}

function _radioUi(playing, name) {
  const btn = document.getElementById('radio-fab-btn');
  const icon = document.getElementById('radio-fab-icon');
  const label = document.getElementById('radio-fab-label');
  const stop = document.getElementById('radio-fab-stop');
  btn.classList.toggle('playing', playing);
  icon.textContent = playing ? '🎵' : '📻';
  label.style.display = playing ? 'inline-flex' : 'none';
  label.textContent = playing ? name : '';
  stop.style.display = playing ? 'flex' : 'none';
}

document.addEventListener('DOMContentLoaded', initRadioPlayer);
