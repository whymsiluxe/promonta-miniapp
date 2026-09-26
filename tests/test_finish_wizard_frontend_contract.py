from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

FINISH_WIZARD = ROOT / "frontend" / "js" / "finish-wizard.js"
CHECKIN = ROOT / "frontend" / "js" / "checkin.js"
APP_HTML = ROOT / "frontend" / "app.html"
SHARED = ROOT / "frontend" / "js" / "shared.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_photo_step_does_not_skip_required_summary_step():
    src = _source(FINISH_WIZARD)
    start = src.index("function _fwWireStep1()")
    end = src.index('// ---------- Step "summary":', start)
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


def test_legacy_finish_survey_removed_from_start_preview_flow():
    checkin_src = _source(CHECKIN)
    html_src = _source(APP_HTML)

    assert "checkin-finish-survey" not in html_src
    assert "checkin-survey-" not in html_src
    assert "_checkinSurveyPause" not in checkin_src
    assert "/finish" not in checkin_src


def test_start_photo_preview_reuses_and_revokes_object_urls():
    src = _source(CHECKIN)

    assert "function _getCheckinPreviewPhotoUrl(file)" in src
    assert "URL.revokeObjectURL(url)" in src
    assert "function _clearCheckinPreviewPhotoUrls()" in src
    assert "const [removed] = _checkinPreviewFiles.splice" in src


def test_checkin_start_sends_geo_accuracy_metadata():
    src = _source(CHECKIN)

    assert "accuracy: coords.accuracy == null ? '' : String(Math.round(coords.accuracy))" in src
    assert "timestamp: pos.timestamp ? String(Math.round(pos.timestamp)) : String(Date.now())" in src
    assert "function _checkinEventTimestamp()" in src
    assert "formData.append('accuracy', geo.accuracy)" in src
    assert "formData.append('geo_timestamp', geo.timestamp)" in src
    assert "formData.append('occurred_at', occurredAt || _checkinEventTimestamp())" in src


def test_finish_wizard_sends_geo_accuracy_metadata():
    src = _source(FINISH_WIZARD)

    assert "let _fwFinishGeo = null; // {lat, lon, accuracy, timestamp}" in src
    assert "let _fwOccurredAt = '';" in src
    assert "_fwOccurredAt = _fwOccurredAt || String(Date.now());" in src
    assert "occurred_at: occurredAt" in src
    assert "if (_fwFinishGeo.accuracy) fields.accuracy = _fwFinishGeo.accuracy;" in src
    assert "if (_fwFinishGeo.timestamp) fields.geo_timestamp = _fwFinishGeo.timestamp;" in src
    assert "Object.entries(record.fields || {}).forEach(([key, value]) => formData.append(key, value || ''))" in src


def test_finish_post_tickets_must_succeed_before_outbox_delete():
    src = _source(FINISH_WIZARD)
    start = src.index("async function _fwCreatePostFinishTickets")
    end = src.index("// 18.09 (audit finding):", start)
    helper = src[start:end]
    send_start = src.index("async function _fwSendFinishOutboxRecord")
    send_end = src.index("async function _fwQueueFinishOutbox", send_start)
    sender = src[send_start:send_end]

    assert "const failures = []" in helper
    assert "catch (e) { console.warn('need creation failed'" not in helper
    assert "if (!res.ok)" in helper
    assert "throw err;" in helper
    assert "Не удалось создать записи после финиша" in helper
    assert sender.index("await _fwCreatePostFinishTickets") < sender.index("if (fromOutbox) await appOutboxDelete")


def test_finish_wizard_loads_frozen_finish_context_before_plan_fact():
    src = _source(FINISH_WIZARD)

    assert "`/api/checkin/${sessionId}/finish-context`" in src
    assert "let _fwContextState = 'idle';" in src
    # 21.09 (owner review finding): context-loading is no longer a full-screen
    # gate before the first render -- Photos never needed daily-plan items,
    # only the 'summary' step's plan-fact section does, and that renders
    # gracefully with an empty list while the fetch is still in flight. Only a
    # genuine terminal failure with no usable cache still gets special
    # handling, and even that no longer blocks the wizard (see
    # test_finish_wizard_screen_merge_frontend_contract.py).
    assert "if (_fwContextState === 'loading') return ['context-loading'];" not in src
    assert "function _fwReadCachedFinishContext(sessionId)" in src
    assert "_fwApplyFinishContext(cached, 'offline_cached')" in src
    assert "const planState = window._todayPlanState" not in src
    assert "_fwDailyPlanItems = planState.plan.items" not in src
