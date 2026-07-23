// Canvas signature pad (Фаза 7) — переиспользуемая модалка для Angebot/Rechnung.
// Подпись опциональна: пользователь может пропустить и создать PDF без неё.
// Референс "Neue Zeit"-стиля пока не применялся визуально к самому canvas — заготовка
// под точную толщину линии/цвет, когда пользователь пришлёт образец подписи (открытый TODO).

let _sigCanvas = null;
let _sigCtx = null;
let _sigDrawing = false;
let _sigHasStrokes = false;
let _sigResolve = null;

function _sigGetPos(e, canvas) {
  const rect = canvas.getBoundingClientRect();
  const point = e.touches ? e.touches[0] : e;
  return { x: point.clientX - rect.left, y: point.clientY - rect.top };
}

function _sigInitCanvas() {
  _sigCanvas = document.getElementById('signature-canvas');
  _sigCtx = _sigCanvas.getContext('2d');
  _sigCtx.strokeStyle = '#000000';
  _sigCtx.lineWidth = 2.5;
  _sigCtx.lineCap = 'round';
  _sigCtx.lineJoin = 'round';

  const start = e => {
    _sigDrawing = true;
    _sigHasStrokes = true;
    const p = _sigGetPos(e, _sigCanvas);
    _sigCtx.beginPath();
    _sigCtx.moveTo(p.x, p.y);
    e.preventDefault();
  };
  const move = e => {
    if (!_sigDrawing) return;
    const p = _sigGetPos(e, _sigCanvas);
    _sigCtx.lineTo(p.x, p.y);
    _sigCtx.stroke();
    e.preventDefault();
  };
  const end = () => { _sigDrawing = false; };

  _sigCanvas.addEventListener('mousedown', start);
  _sigCanvas.addEventListener('mousemove', move);
  _sigCanvas.addEventListener('mouseup', end);
  _sigCanvas.addEventListener('mouseleave', end);
  _sigCanvas.addEventListener('touchstart', start, { passive: false });
  _sigCanvas.addEventListener('touchmove', move, { passive: false });
  _sigCanvas.addEventListener('touchend', end);
}

function _sigClear() {
  _sigCtx.clearRect(0, 0, _sigCanvas.width, _sigCanvas.height);
  _sigHasStrokes = false;
}

function _sigClose(result) {
  document.getElementById('signature-modal').style.display = 'none';
  if (_sigResolve) { _sigResolve(result); _sigResolve = null; }
}

// Возвращает Promise<string|null> — base64 PNG (без data:image/png;base64, префикса) или null если пропущено/пусто.
function openSignaturePad(title) {
  return new Promise(resolve => {
    _sigResolve = resolve;
    document.getElementById('signature-modal-title').textContent = title || 'Подпись';
    document.getElementById('signature-modal').style.display = 'flex';
    if (!_sigCanvas) _sigInitCanvas();
    _sigClear();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('signature-modal');
  if (!modal) return; // модалка не на этой странице (защита от повторной привязки)

  document.getElementById('signature-clear-btn').addEventListener('click', _sigClear);
  document.getElementById('signature-skip-btn').addEventListener('click', () => _sigClose(null));
  document.getElementById('signature-confirm-btn').addEventListener('click', () => {
    if (!_sigHasStrokes) { _sigClose(null); return; }
    const dataUrl = _sigCanvas.toDataURL('image/png');
    const base64 = dataUrl.split(',')[1];
    _sigClose(base64);
  });
});
