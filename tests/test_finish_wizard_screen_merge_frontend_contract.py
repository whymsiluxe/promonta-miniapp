"""Worker UX V2, Этап 8 (remainder) — merge summary+plan-fact and
extra+needs+tomorrow-prep into single screens.

Brings the wizard to the plan's target of a small, fixed number of screens
(4: Фото -> Что сделано/план-факт -> Проблемы и завтра -> Сводка) regardless
of whether a DailyPlan exists, instead of 6/8 steps depending on branch.
Every sub-block kept its original markup ids/validation -- only the screen
containers and their single "Далее" handler were merged, per this repo's
source-assertion contract-test style.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINISH_WIZARD = ROOT / "frontend" / "js" / "finish-wizard.js"


def _source() -> str:
    return FINISH_WIZARD.read_text(encoding="utf-8")


def _fn(src: str, signature: str) -> str:
    start = src.index(signature)
    depth = 0
    i = src.index("{", start)
    j = i
    while True:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1


def test_wizard_is_exactly_four_screens_regardless_of_daily_plan():
    src = _source()
    body = _fn(src, "function _fwStepSequence(")

    assert "['photo', 'summary', 'extra', 'review']" in body
    assert body.count("['photo', 'summary', 'extra', 'review']") == 2
    assert "'plan-fact'" not in body
    assert "'needs'" not in body
    assert "'tomorrow-prep'" not in body


def test_summary_screen_renders_plan_fact_items_when_plan_exists():
    body = _fn(_source(), "function _fwRenderStepSummaryPlanFact(")

    assert "fw-work-summary" in body
    assert "_fwDailyPlanItems.length ? `" in body
    assert "fw-status-btn" in body
    assert "fw-plan-items" in body


def test_summary_screen_single_next_button_validates_both_summary_and_plan_fact():
    body = _fn(_source(), "function _fwWireStepSummaryPlanFact(")

    assert body.count("id=\"fw-next-summary\"") == 0  # id lives in render, not wire
    assert "fw-next-summary" in body
    assert "Заполни, что сделано за смену" in body
    assert "Отметь выполнение каждого пункта плана" in body
    # Single _fwNavNext() call, not one per merged sub-screen
    assert body.count("_fwNavNext();") == 1


def test_extra_screen_renders_all_three_merged_subsections():
    body = _fn(_source(), "function _fwRenderStep3(")

    assert "Были ли доп. работы вне плана?" in body
    assert "Что мешало работе или что нужно?" in body
    assert "Дефекты, которые заметил:" in body
    assert "_fwDailyPlanItems.length ? `" in body
    assert "fw-issue-btns" in body


def test_extra_screen_single_next_button_snapshots_all_three_drafts():
    body = _fn(_source(), "function _fwWireStep3(")

    assert "saveExtraDraft();" in body
    assert "_fwPendingNeedCategory" in body
    assert "defectText" in body
    assert "_fwTomorrowIssues.forEach" in body
    # Single _fwNavNext() call at the end, not one per merged sub-screen
    assert body.count("_fwNavNext();") == 1


def test_tomorrow_prep_content_stays_conditional_on_daily_plan_existing():
    # Originally 'tomorrow-prep' only existed in the WITH-plan branch of
    # _fwStepSequence -- merging it into 'extra' must not make it
    # unconditionally visible when there's no DailyPlan for the shift.
    body = _fn(_source(), "function _fwRenderStep3(")
    guard_idx = body.index("${_fwDailyPlanItems.length ? `")
    tomorrow_idx = body.index("Отметь проблемы с готовностью на завтра")
    assert guard_idx < tomorrow_idx
    # No unrelated ternary-close/re-open between the guard and the content
    assert "` : ''}" not in body[guard_idx:tomorrow_idx]


def test_no_dangling_references_to_removed_screen_functions():
    src = _source()
    for removed in ("_fwRenderStep2(", "_fwWireStep2(", "_fwRenderStepPlanFact(",
                    "_fwWireStepPlanFact(", "_fwRenderStep4(", "_fwWireStep4(",
                    "_fwRenderStepTomorrowPrep(", "_fwWireStepTomorrowPrep("):
        assert f"function {removed}" not in src, f"{removed} should have been removed, not left dangling"
        assert f" {removed[:-1]}();" not in src, f"a call site for removed {removed} still exists"
