from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

FINISH_WIZARD = ROOT / "frontend" / "js" / "finish-wizard.js"
SHARED = ROOT / "frontend" / "js" / "shared.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_photo_step_does_not_skip_required_summary_step():
    src = _source(FINISH_WIZARD)
    start = src.index("function _fwWireStep1()")
    end = src.index("// ---------- Step 2:", start)
    step1 = src[start:end]

    assert step1.count("_fwNavNext();") == 1
    assert "if (_fwPhotos.length < 2) return;" in step1


def test_finish_wizard_requires_written_or_voice_summary():
    src = _source(FINISH_WIZARD)

    assert "fw-summary-error" in src
    assert "Заполни, что сделано за смену" in src
    assert "if (!_fwWorkSummary.trim())" in src


def test_finish_wizard_has_navigation_overlay_lifecycle():
    src = _source(FINISH_WIZARD)

    assert "NavigationManager.registerOverlay" in src
    assert "function _fwCloseWizardInternal()" in src
    assert "function _fwCloseWizardAfterSuccess()" in src


def test_shared_voice_input_reads_transcribe_raw_transcript():
    src = _source(SHARED)

    assert "data.raw_transcript || data.transcript" in src
