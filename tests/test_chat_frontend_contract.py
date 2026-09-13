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
    assert "chat-quick-reactions" in html
    assert "chat-quick-reaction-hit" in html
    assert "chat-delete-confirm-title" in html
    assert "bottom: 0 !important" in html
    assert "_chatThreadLoadSeq" in js
    assert "_prepareChatThreadSurface(title)" in js
    assert "_isCurrentChatRequest(requestSeq, requestUser, requestKey)" in js
    assert "messagesEl.innerHTML = '<div class=\"chat-empty\">Загрузка...</div>'" in js
    assert "CHAT_REACTION_OPTIONS = ['❤️', '🙌', '🔥', '👏', '🥲', '😍', '😮', '😂']" in js
    assert "menu.className = 'chat-bubble-menu chat-action-sheet'" in js
    assert "modal.className = 'chat-forward-modal chat-forward-sheet'" in js
    assert "_bindChatQuickEmojiRow()" in js
    assert "_openChatConfirmSheet" in js
    assert "window.confirm" not in js
    assert "confirm(" not in js
    assert "canDelete = _chatIsOwner || Number(bubble.dataset.uid) === _chatMyId" in js


def test_chat_list_ios_search_and_stale_load_contract():
    html = _source(APP_HTML)
    js = _source(CHAT_JS)

    assert 'class="chat-inline-search"' in html
    assert 'id="chat-worker-strip" class="chat-worker-strip"' in html
    assert "#view-chat .chat-inline-search .chat-search-circle" in html
    assert "#view-chat .chat-thread-list" in html
    assert "border-radius: var(--ios-radius-card, 12px)" in html
    assert "font-size: 36px" in html
    assert "chat-load-error" in html
    assert "#chat-retry-load" in html

    assert "function _isCurrentChatRequest(requestSeq, requestUser, requestKey)" in js
    assert "function _setChatThreadLoading(isLoading)" in js
    assert "function _renderChatLoadError(message)" in js
    assert "_setChatThreadLoading(true)" in js
    assert "_setChatThreadLoading(false)" in js
    assert "if (!_isCurrentChatRequest(requestSeq, requestUser, requestKey)) return;" in js
    assert "showBlockingError = document.body.classList.contains('chat-thread-loading')" in js
    assert "messagesEl.innerHTML = '<div class=\"chat-empty\">Загрузка...</div>'" in js
    assert "strip.classList.toggle('search-active', expanded && !inline)" in js
    assert "circle.classList.toggle('has-query', hasQuery)" in js
