from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
AI_JS = ROOT / "frontend" / "js" / "ai.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ai_manager_command_entry_is_compact_and_voice_enabled():
    html = _source(APP_HTML)
    js = _source(AI_JS)

    assert 'id="ai-manager-command-btn"' in html
    assert "ai-manager-command-sheet" in html
    assert "ai-manager-command-draft" in html

    assert "function _openAiManagerCommandSheet()" in js
    assert "function _bindAiManagerCommandEntry()" in js
    assert "_bindAiManagerCommandEntry();" in js
    assert "attachVoiceInputButton(voiceBtn" in js
    assert "api('/api/manager/command/parse'" in js
    assert "requires_confirmation" in js
    assert "Черновик команды" in js
    assert "нужно подтвердить" in js
