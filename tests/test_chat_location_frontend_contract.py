from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAT_JS = ROOT / "frontend" / "js" / "chat.js"
APP_HTML = ROOT / "frontend" / "app.html"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_chat_location_button_has_sending_state():
    src = _source(CHAT_JS)

    assert "function _setChatLocationSending(isSending)" in src
    assert "chat-attach-btn-loading" in src
    assert "aria-busy" in src
    assert "_setChatLocationSending(true)" in src
    assert "_setChatLocationSending(false)" in src


def test_chat_location_errors_are_user_readable():
    src = _source(CHAT_JS)

    assert "function _chatLocationErrorMessage(err)" in src
    assert "разреши доступ к геолокации" in src
    assert "геолокация не ответила за 10 секунд" in src
    assert "не удалось определить координаты" in src


def test_chat_location_loading_style_exists():
    src = _source(APP_HTML)

    assert ".chat-attach-btn-loading" in src
    assert "@keyframes chatSpin" in src
