from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
CHAT_JS = ROOT / "frontend" / "js" / "chat.js"
OBJECT_INFO_JS = ROOT / "frontend" / "js" / "object-info.js"


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
    # 17.09: chat list header used to have its own 36px/800 override
    # (#view-chat .chat-list-header h1) -- removed as a duplicate of the
    # canonical top-level page-title size, which now lives ONLY on the base
    # `header h1` rule (28px/800, see that rule's own comment) so every
    # top-level screen inherits one definition instead of N copies that can
    # drift out of sync (36px overflowed the header's centered column on
    # real iPhone -- "Календарь" truncated to "Календа..."). Assert the
    # canonical size directly instead of the removed duplicate.
    assert "font-weight: 800;" in html
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


def test_chat_owner_broadcast_controls_contract():
    html = _source(APP_HTML)
    js = _source(CHAT_JS)

    assert 'id="chat-broadcast-btn"' in html
    assert "chat-broadcast-btn" in html
    assert "chat-broadcast-sheet" in html
    assert "chat-broadcast-label" in html

    assert "function _openChatBroadcastSheet()" in js
    assert "function _bindChatBroadcastButton()" in js
    assert "_bindChatBroadcastButton()" in js
    assert "btn.style.display = _chatIsOwner ? 'inline-flex' : 'none'" in js
    assert "data-broadcast-scope=\"company\"" in js
    assert "data-broadcast-scope=\"object\"" in js
    assert "api('/api/manager/broadcast'" in js
    assert "JSON.stringify({ scope, text, object_id: scope === 'object' ? objectId : null })" in js
    assert "msg.broadcast" in js


def test_chat_thread_skin_is_bound_to_reusable_detail_view():
    html = _source(APP_HTML)
    object_info_js = _source(OBJECT_INFO_JS)

    assert "#obj-detail-panel-chat.obj-chat-active #chat-thread-detail-view" in html
    assert "panel.appendChild(chatView)" in object_info_js
    for selector in (
        "#chat-thread-detail-view .chat-bubble",
        "#chat-thread-detail-view .chat-bubble-own",
        "#chat-thread-detail-view .chat-bubble-other",
        "#chat-thread-detail-view .chat-input-bar",
        "#chat-thread-detail-view .chat-quick-reactions",
        "#chat-thread-detail-view .chat-send-btn",
    ):
        assert selector in html


def test_close_chat_thread_cancels_active_voice_recording_without_sending():
    js = _source(CHAT_JS)
    start = js.index("function closeChatThread()")
    end = js.index("\n// 04.08", start)
    close_block = js[start:end]
    stop_start = js.index("function _stopVoiceRecording(send)")
    stop_end = js.index("\nasync function _sendVoiceMessage", stop_start)
    stop_block = js[stop_start:stop_end]

    assert "_stopVoiceRecording(false);" in close_block
    assert close_block.index("_stopVoiceRecording(false);") < close_block.index("_chatActiveThread = null;")
    assert "recorder.stream.getTracks().forEach(t => t.stop());" in stop_block
    assert "if (!send) { recorder.stop(); return; }" in stop_block
    assert "await _sendVoiceMessage(blob);" in stop_block


def test_chat_hub_lists_accessible_empty_entity_threads_for_workers():
    js = _source(CHAT_JS)

    assert "let _chatMangelCache = [];" in js
    assert "let _chatTasksCache = [];" in js
    assert "function _loadChatMangelTickets()" in js
    assert "function _loadChatTasks()" in js
    assert "const res = await api('/api/mangel');" in js
    assert "const res = await api('/api/tasks');" in js
    assert "api(`/api/tasks?object_id=${encodeURIComponent(oid)}`)" in js
    assert "await Promise.all([_loadChatMangelTickets(), _loadChatTasks()]);" in js
    assert "const key = `mangel:${ticket.id}`;" in js
    assert "const key = `task:${task.id}`;" in js
    assert "Object.values(threadsByKey).forEach(thread => {" in js
