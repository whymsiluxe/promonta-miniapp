from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKIN_JS = ROOT / "frontend" / "js" / "checkin.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_checkin_local_session_cache_handles_corrupt_json():
    src = _source(CHECKIN_JS)

    assert "const key = _checkinSessionKey(objectId)" in src
    assert "const raw = localStorage.getItem(key)" in src
    assert "return JSON.parse(raw)" in src
    assert "localStorage.removeItem(key)" in src
    assert "return null;" in src
