from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
CHAT_JS = ROOT / "frontend" / "js" / "chat.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_chat_message_actions_match_comment_bottom_sheet_contract():
    html = _source(APP_HTML)
    js = _source(CHAT_JS)

    assert "chat-action-sheet" in html
    assert "chat-action-sheet-handle" in html
    assert "chat-forward-sheet" in html
    assert "bottom: 0 !important" in html
    assert "CHAT_REACTION_OPTIONS = ['❤️', '🙌', '🔥', '👏', '🥲', '😍', '😮', '😂']" in js
    assert "menu.className = 'chat-bubble-menu chat-action-sheet'" in js
    assert "modal.className = 'chat-forward-modal chat-forward-sheet'" in js
    assert "canDelete = _chatIsOwner || Number(bubble.dataset.uid) === _chatMyId" in js
