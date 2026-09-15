from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_HTML = ROOT / "frontend" / "app.html"
OBJECTS_JS = ROOT / "frontend" / "js" / "objects.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_object_info_tab_appends_human_readable_history():
    html = _source(APP_HTML)
    js = _source(OBJECTS_JS)

    assert "renderObjectHistorySection(_objDetailCurrentId)" in js
    assert "async function renderObjectHistorySection(objectId)" in js
    assert "/api/objects/${encodeURIComponent(objectId)}/history?limit=12" in js
    assert 'id="obj-history-section"' in js
    assert "obj-history-row" in js
    assert "broadcast_sent" in js
    assert "finish_submitted" in js
    assert "obj-history-retry" in js

    assert ".obj-history-list" in html
    assert ".obj-history-row" in html
    assert ".obj-history-dot" in html
    assert ".obj-history-meta" in html
