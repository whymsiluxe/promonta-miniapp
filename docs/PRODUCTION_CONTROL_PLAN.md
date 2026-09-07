# Context

Owner wants two things:

1. Deep analysis of the current Promonta miniapp — bottlenecks, risks, what to improve.
2. A production-control layer: contract → day-by-day plan → worker daily checklist with morning acceptance → shift finish with fact-reporting → automatic carryover → owner risk dashboard → real worker productivity, replacing guesswork with contract-driven, norm-based planning.

Requirements arrived in three rounds — an initial scoped Q&A, one linking clarification, a large unstructured addendum, and finally a complete architecture spec the owner obtained from ChatGPT. **The ChatGPT spec is materially more rigorous than my own first draft** (correct source-of-truth split between Sheets and local store, versioned plan acceptance instead of a boolean, carryover as remaining-quantity instead of vague rollover, contract-date vs internal-target risk separation, a dedicated sync worker instead of per-request Sheets polling, explicit security/ACL and idempotency rules) — it supersedes my draft's architecture. This plan adopts it as the primary spec, keeps my earlier standalone analysis (Section I) and the memory-process fix (Section K) since those aren't superseded by anything in the ChatGPT doc, and discards my draft's naming/architecture (`day_plans.json`, ad-hoc rollover) in favor of the spec's `DailyPlan`/`Carryover`/versioned-acceptance model throughout.

**Confirmed discovery so far**: the owner's memory of "a productivity indicator that used to exist, from photo analysis" maps to Phase 4b (deployed 2026-07-12, `main.py`, `analyze-progress`/`analyze-materials`/`analyze-defects`, GLM vision) — it produces a narrative text, surfaced today as raw text in `work_speed` on `/api/profile/stats`. **This is very likely the "existing numeric KPI" the ChatGPT spec asks Round 0 to hunt for and prove/disprove — but per the spec's own instruction, this must be re-verified freshly against the live repo, not assumed from this session's earlier memory-search finding**, since the spec explicitly warns not to assume `work_speed` is a real rate without checking the actual implementation.

---

# Scope of THIS session: Round 0 only

Per the owner-provided spec's own gating rule: **execute only Round 0 (Discovery / Architecture Freeze) now**. No functional code changes, no new Sheets tabs, no Drive changes, no deploys. The one exception carried over from the spec: a markdown discovery report is fine to write if useful. Round 1 onward (listed in full at the bottom of this plan for context) requires an explicit separate "GO" from the owner after Round 0's report is reviewed.

This also matches plan-mode's own constraints for this conversation — Round 0 is inherently read-only investigation, which is what plan mode can safely execute end-to-end; Round 1+ is real implementation work for a future session.

---

# I. Analysis of Current Miniapp — Weak Spots (prioritized, from initial investigation)

## Critical
1. **Single point of failure — one owner, no manager/deputy role.** Every `require_owner` action blocks if the owner is unavailable; this program adds more owner-gated actions (plan approval, amendments) on top.
2. **No staging environment.** All changes land directly on production JSON + Sheets with no rehearsal space — directly relevant since this program is the largest schema/architecture change the app has seen.
3. **`main.py` at ~7000+ lines, undecomposed into routers.** Round 0 must map exactly which functions/routes this program touches so Round 1's diffs stay reviewable.

## High
4. **JSON-file storage concurrency**, now explicitly addressed by the spec's own design (single `daily_plan_store.json` with atomic writes/lock/corrupt-quarantine, added to `CRITICAL_JSON_PATHS`) — flagging here only because Round 0 must confirm that pattern actually exists today under that name and find the real critical-store convention to match.
5. **Google Sheets API quota**, addressed by the spec's own design (dedicated `plan_sync.py` worker on a 60s timer, not per-request polling) — Round 0 must confirm no such worker/timer infra exists yet (matches earlier finding: no APScheduler/cron in this codebase today) so Round 1 knows it's building this from scratch.
6. **Claude API cost/failure handling for contract parsing** — unbounded without caps; the spec's provenance/confidence fields help auditability but don't inherently cap cost. Flag for Round 1.
7. **Bad AI-generated plan risk** — mitigated by the spec's mandatory owner Approve step and `requires_owner_input` for missing data, but only as strong as the review UI actually surfacing those flags prominently.
8. **Dormant/undiscoverable feature risk — already happened once.** Phase 4b was built and shipped, then genuinely lost to memory search until a full session-history dig surfaced it. Round 0's productivity-field hunt is a direct re-run of exactly this problem — see Section K for the process fix.

## Medium
9. **144 stale `.bak` files + dead `WIP_phase2` skeleton** — repo hygiene debt, raises odds of editing the wrong near-duplicate file during Round 0/1 investigation.
10. **Public GitHub repo** — this program adds business-sensitive data (contract text, pricing/norm inferences) flowing through the same codebase; confirm contract storage paths are git-excluded before Round 1 ships anything.
11. **Frontend `loadedViews`-once-init pattern** — the new "Сегодня" screen and persistent day-plan bar must each expose explicit refresh functions (for the 60s poll / update-indicator behavior the spec requires) or they'll show stale state.
12. **No background scheduler infrastructure** — confirmed gap; Round 1 needs to decide systemd timer vs. other mechanism for `plan_sync.py` and `contract_ingest.py`.

---

# II. Production Control Program — Architecture (per owner-approved spec)

## Non-negotiable principles (carried verbatim from the spec, do not relitigate in Round 0)

- No second stage system — Sheets `Этапы` stays master identity/status/order; `stage_key` format (`{object_id}-S{n}`) stays permanent.
- No second check-in system — Start/Pause/Finish/GPS/photo/`checkin_meta` stay as-is; DailyPlan attaches to the existing session, doesn't replace it.
- No second assignment system — reuse `object_assignments.json`, `/api/assignment-candidates`, Assignment Sheet, `skills_v2`, `work_type_id`.
- No second work-type catalog — `backend/work_types.py` stays the only one.
- No second notification system — reuse the existing Alerts/critical-alerts mechanism for all new alert types (plan not accepted, worker started without plan, blocker, plan changed, stage overdue, material shortage, delay forecast, contract deadline at risk).
- No duplication of Roadmap — it stays the master per-stage checklist (categories/items/required/safety_critical/weight/assigned_user_id/open-done/notes/blockers); the new layer references it, doesn't reimplement it.
- The new layer is called **DailyPlan** — it connects Roadmap + Assignment + Check-in + Needs + Alerts + Productivity. This replaces my draft's `day_plans.json`/rollover naming entirely.
- Bottom navigation is not touched. The "Сегодня" (Today) screen is a full-screen auto-opening view on app launch when an unaccepted plan exists for the worker that day — not a 6th tab.
- Do NOT build now (explicit no-list from the spec): React, Postgres migration, Manager/Bauleiter role, payroll, new chat backend, new Assignment Sheet, new Roadmap, new Check-in, bottom-nav changes, global redesign, autonomous worker reassignment, AI auto-publish, AI-generated DIN references without verified source. **Also explicitly prohibited** (reiterated in the Owner-Daily-Control/Worker-Card addendum, because it's an easy trap when a feature touches an existing overlay): a second Worker Card, a second calendar inside Worker Card, a second Check-in, or a second parallel DailyPlan representation for the owner — Worker and Owner always view different *presentations* of the same underlying DailyPlan data, never two independently-modeled copies of it.

## Source-of-truth split (the key correction versus my draft)

- **Google Sheets = source of truth for the plan** (future/editable: stage list, day items, quantities, dates, assignments, tools/materials, sequencing). Owner can edit Sheets directly and it should propagate to the app and to the worker's Today screen — this was an explicit, repeated owner requirement my first draft did not fully support.
- **Local critical store = source of truth for historical fact** (what a worker actually accepted, actually did, Finish reports, historical KPI). A manual Sheets edit can never rewrite what was already accepted/executed/finished — past is immutable regardless of later spreadsheet edits.

## Worker flow (replaces my draft's Sections C/G.1 entirely)

**Morning**: app open → after bootstrap, backend checks today's DailyPlan. If unaccepted plan exists, "Сегодня" opens full-screen automatically (not a nav tab). Screen is a job-card, not a form — large type (title 28-30px down to metadata 15px minimum, touch targets 48-52px minimum), numbered action list with objective, quantity, time estimate per step. Primary CTA: **"ПЛАН ПОНЯТЕН — БЕРУ В РАБОТУ"** (not a generic "OK/Accepted") — records `daily_plan_id`, `plan_version`, `worker_id`, `accepted_at`, `accepted_snapshot_hash`. CTA then becomes **"НАЧАТЬ СМЕНУ"**, invoking the existing Check-in Start. Secondary action **"ЕСТЬ ПРЕПЯТСТВИЕ"** (blocker reasons list + comment/photo) alerts the owner before a work day is lost. If no plan is published yet but the worker is assigned today: don't block time tracking — show "План дня ещё не опубликован" + "Начать смену без плана", which still fires an owner alert.

**During the day**: worker is not required to tick boxes live; Today is a quick-reference card, tap "Подробнее" for full detail per step. A compact persistent bar ("Сегодня · Объект · 3 из 6 · Открыть план") stays reachable from anywhere in the app without adding nav.

**Shift finish (the corrected flow)**: existing "Завершить смену" opens a wizard before the actual Finish call:
1. **Fact step** — same action list as the morning, each marked done/partial/not_done/blocked; quantity fields show planned vs. actual where applicable. Non-done statuses require a `reason_code` (from a fixed Russian-labeled list) + mandatory comment for `other` + suggested photo for `technical_problem`/`blocked`.
2. **Tomorrow-prep step** — shows next day's plan-derived tool/material checklist (from work template + next DailyPlan, not worker-recalled), two required yes/no questions (enough material? tools ready?); "no" answers auto-create a Need, idempotent per `(object_id, next_date, worker_id, tool/material id)`.
3. **Final Finish** — existing Check-in Finish is extended with an optional `daily_plan_report` JSON form field, so the fact-report becomes part of the same authoritative session record instead of a second parallel write that can desync from "shift is closed." An idempotent projector (`apply_daily_execution(session_id)`, idempotency key `execution:<session_id>`) then fans this out into DailyPlan execution/carryover/productivity/Sheets `Факт_дня` — if the projector fails, the check-in itself is never lost; a retry job re-applies the projection safely.

**Carryover**: done → closed. partial → `remaining_quantity` computed and carried. not_done → full remaining carried. blocked → carried as a blocked item. Next working day's Today screen shows "СНАЧАЛА ЗАКОНЧИТЬ СО ВЧЕРА" ahead of the fresh plan — carryover never silently deletes tomorrow's planned items, it prepends. If `carryover_hours + tomorrow_hours > crew capacity`, a Replan Engine flags overload and produces a recommendation for the owner to review — it never auto-reassigns workers across objects without explicit owner approval.

## Risk model (replaces my draft's simpler alert logic)

Separate `contract_finish_date` from `internal_target_date` — never conflate them. GREEN (on track) / YELLOW (carryover exists, internal buffer intact) / ORANGE (internal target at risk) / RED (predicted finish exceeds the *contractual* date) — red alerts are reserved for genuine contractual risk, not every internal slip, to avoid alert fatigue.

## Owner views (replaces my draft's Section F)

- **All-objects matrix** (owner-only screen reached from Объекты/План, not a new bottom-nav tab): sticky object-name column, dates horizontally, colored state cells; tap a cell for plan/fact/workers/hours/carryover/blockers detail.
- **Single-object day-by-day**: stages as sticky rows, days as scrollable columns, status glyphs plus completion %.

## Google Sheets — new tabs (replaces my draft's single "Контроль" tab)

Five new tabs, each with the spec's full column list (see owner's message for exact columns — carried forward verbatim, not re-derived): `План_этапов` (editable plan, keyed by `stage_key`), `План_дня` (editable day items, owner can hand-edit), `Нормы_работ` (work-type productivity norms — baseline rate, crew factors, default steps/tools/materials, **verified-source gating**: AI may only cite a norm if `norm_verified=true`, otherwise the stage gets `norm_check_required=true` and no invented DIN/VOB references), `Факт_дня` (app-generated, append-only mirror of executed fact — Sheets is explicitly NOT the source of truth for this tab, local store is), `Производительность` (aggregated owner-facing productivity view, computed columns app-managed, `manual_baseline_factor` owner-editable as a prior).

## Sync architecture (replaces my draft's inline-request Sheets calls)

Dedicated `scripts/plan_sync.py` (or service module + systemd timer), 60s interval, reads `План_этапов`/`План_дня`, computes stable content hashes, diffs against `plan_sync_state.json`, creates new plan versions, updates local cache, raises alerts on significant changes — not invoked synchronously inside FastAPI request handlers. Local state file follows the same atomic-write/lock/corrupt-quarantine convention as other critical stores (Round 0 must locate and match that exact existing convention).

**Conflict rule**: before worker acceptance, Sheets edits flow freely. After acceptance but before Start, a Sheets change surfaces as "ПЛАН ОБНОВЛЁН РУКОВОДИТЕЛЕМ" with an explicit +/−/~ diff, requiring re-acceptance. After Start, the accepted snapshot is never silently rewritten — changes become a tracked **Amendment** the worker must separately acknowledge; full version history is retained (plan v1 accepted, v2 amendment, amendment accepted, Finish — a real audit trail, not a boolean).

**Worker-side propagation**: `GET /api/daily-plan/today` polled ~60s while the app is open (foreground/resume-triggered), no WebSocket in v1; if the app is closed, the sync worker can raise a Telegram/critical notification instead.

## Google Drive contract ingestion (replaces my draft's Section B.1 Drive path)

Dedicated owner-created Drive folder, ID supplied via `CONTRACTS_DRIVE_FOLDER_ID` env var — never hardcoded, never auto-created without an explicit owner-supplied ID. **Round 0 must check whether the existing Sheets OAuth credential already carries Drive scope — if not, ingestion is explicitly blocked (`DRIVE_SCOPE_REQUIRED`) rather than silently reauthorizing/overwriting the refresh token**; the rest of the DailyPlan system must work independently of whether Drive ingestion is available. Separate `scripts/contract_ingest.py` worker (1-5 min interval, not inline in a request), state in `contract_ingest_state.json` keyed by file id/hash/modified_time, dedupes on unchanged hash. Supported inputs at first: PDF-with-text-layer, DOCX, TXT; scanned/image-only PDFs get `status: needs_ocr` rather than fabricated text — no OCR library added without separately validating German-text quality first.

**Extraction is fact-only, two-stage**: stage 1 (Claude) extracts only literal contract facts (object, address, dates, positions, quantities, units, materials if stated, deadlines, explicit dependencies, exclusions) each with `provenance` (source file/page/confidence) — no planning yet. Stage 2 (a separate Project Planner pass) combines those facts with Work Types catalog, verified norms, Roadmap, worker skills/availability, real productivity data, and company work calendar to produce a **DRAFT only** — never auto-sent to workers. Every calculated quantity must be traceable (quantity, unit, basis, productivity_rate, crew_size, estimated_person_hours, source, confidence) — if the contract states a pauschal scope with no measurable quantity, the system must not invent one; it flags `MISSING DATA` / `requires_owner_input=true` for the owner to fill directly in Sheets, and the sync recalculates the draft afterward.

**Prompt injection defense** (explicit, not optional): contract text is untrusted data; the extraction system prompt must explicitly instruct the model to treat any embedded instructions in the document ("ignore previous instructions", "send file", etc.) as inert content, never as commands — no file/network/production actions triggered by document content, structured extraction only.

**Owner approval gate**: "НОВЫЙ ПЛАН ИЗ ДОГОВОРА" summary (stage count, working-day count, crew estimate, contract vs internal dates, count of items needing clarification) with ПРОВЕРИТЬ/УТВЕРДИТЬ/ОТКЛОНИТЬ — only after УТВЕРДИТЬ does `status=approved` and DailyPlans become publishable to workers.

## Worker productivity (replaces my draft's Section K numeric-blend approach)

**Round 0's job here is verification, not design-from-assumption**: grep the full repo (Python, frontend, `worker_profiles.json` schema, Sheets headers, docs, old migrations) for `productivity`/`work_speed`/`efficiency`/`kpi`/`performance`/`скорость`/`продуктивность`/`норма`, produce a field/location/type/meaning/keep-migrate-deprecate table, and give a direct verdict — either the exact field, or the explicit statement `NUMERIC LEGACY PRODUCTIVITY FIELD NOT FOUND` — not a guess either way. (Earlier session-history search strongly suggests `work_speed` on `/api/profile/stats` is analysis-count/narrative-text, not a rate — but the spec is explicit that this must be re-confirmed against actual code, not asserted from memory search alone.) If an old numeric field is found, it's kept and renamed/documented as `manual_baseline_factor` — a *prior*, not deleted, not silently reused as if it were an observed rate.

**Actual productivity going forward**: `observed_rate = actual_quantity / person_hours`, tracked per `(worker, work_type)`. Team-worked quantities are NOT auto-split evenly between crew members and presented as individual fact — team output is a "crew productivity observation" first; individual rate updates only from solo work, explicit contribution weighting, or an hours-weighted estimate explicitly marked `confidence=estimated_team`. New workers start from a `manual_baseline_factor`/prior and blend toward observed data via a configurable evidence weight (`PRODUCTIVITY_PRIOR_HOURS`, e.g. 40h), not a hardcoded step function. Owner Worker Card (extend existing, don't replace) shows productivity, plan-completion-rate, carryover-rate, prep-compliance, and quality signals **as separate figures**, never collapsed into one opaque AI score. Quality/defect signals only attribute to a worker when a defect has a genuine, responsible-worker-linked connection to their actual work_type/stage — never a blanket penalty. **Workers see only their own numbers, never teammates' — productivity analytics is owner-only.**

## Owner — "Контроль дня" (Daily Control), distinct from the multi-day matrix

A second owner-only screen, separate purpose from the all-objects matrix above: matrix answers "how is the whole object tracking against schedule," Контроль дня answers "what is happening **today**, right now" — who's been given a plan, who accepted it, who's working, who's finished, what actually got done, what carried over and why, is tomorrow's material/tool prep done, where are the blockers/risks — scannable in 10-20 seconds without opening each worker individually.

**Header**: date + clickable KPI strip (Планы сегодня / Приняли / Сейчас работают / Завершили / Есть переносы / Есть риски) that double as filters. Filter chips: Все / Не приняли / Работают / Завершили / С переносом / Проблемы, plus object/worker filters, default "Все."

**Row = one worker × one object × today.** Shows object, worker, plan summary (stage · action count), plan status, shift status, outcome (once finished), tomorrow-prep status, risk level.

**Plan status states**: `NO_PLAN` → "План не создан", `PUBLISHED`/`NOT_ACCEPTED` → "Ожидает принятия", `ACCEPTED` → "План принят", `AMENDMENT_PENDING` → "Изменения не подтверждены", `ACCEPTED_UPDATED` → "Обновлённый план принят" — shown with acceptance time and version (`v3`) as secondary text.

**Shift status reuses existing Check-in states as-is** (не начата/работает/пауза/завершена + a new "начал без плана" flag) — no second shift-status system.

**No fake progress during an active shift.** Since workers aren't required to tick boxes live, never show a computed "43% done" mid-shift from partial data — show "Работает" + the plan's action count only. A voluntarily-reported blocker can surface immediately. Real fact only appears after the Finish Wizard completes, at which point the row becomes: done/total, planned vs actual quantity, carryover count + reason, tomorrow material/tool readiness, risk delta.

**Detail view** (tap a row): object, worker, date, plan id/version, published/accepted/shift-start/shift-finish timestamps — critically, **shows the snapshot the worker actually accepted**, not just current Sheet rows (e.g. "v2 accepted 07:48 → Sheet edited 10:14 → amendment v3 created → worker confirmed v3 at 10:18" with an explicit diff, matching the versioning/amendment model above — history is never overwritten). Plan section shows each action with its done/partial/not_done status and reason. Prep-tomorrow section shows material/tool readiness and links any auto-created Need. Carryover section shows source date → target date, remaining quantity, reason.

**Alerts triggered from this screen's data** (reusing the existing alert mechanism, no new notification system): worker started without a DailyPlan; worker reported a blocker at morning acceptance; plan amended after acceptance but not yet re-confirmed; Finish contains `blocked`; Finish contains `material_missing`/`tool_missing`; carryover affects the internal target; predicted finish exceeds the contract date. **Explicit non-alert rule**: never alert "worker hasn't accepted by 08:00" unless a `planned_start_time` is actually configured for that object/worker — without one, show "Не принят" as a passive status in Контроль дня, not a red alert. Color rule: green = accepted/normal/fully closed; yellow = not yet accepted / minor carryover / needs attention; orange = blocker or material/tool missing or internal-target risk; red = contract-finish risk or critical blocker only — **never red for an ordinary unclosed checklist item**.

**Manager correction is additive, never silently overwriting the worker's report.** If a worker reports `35 m²` and the owner believes it's `38 m²`, the original `reported_by_worker=35` is retained; the correction is stored separately (`manager_corrected_quantity`, `manager_corrected_by`, `manager_corrected_at`, `manager_correction_reason`). Analytics may use the corrected value, but the audit trail keeps both — this is the same "never rewrite accepted/historical fact silently" principle applied to owner edits, not just Sheet edits. Historical `Факт_дня` is app-generated/mirror only; any manual correction to historical fact goes through this explicit audited-correction path, never a direct edit of `План_дня` (which is for future/current plan only).

**Object Detail gets a small "Сегодня" block** (team size, plans published/accepted, working/finished counts, link to Контроль дня) that becomes a same-day summary block after all shifts close (plan item count, done count, carryover count, hours, tomorrow material/tool readiness, delivery forecast delta, link to full day report).

**End-of-day object summary**: one aggregated message per object once all its active shifts close that day (who worked, plan/done/carryover counts, hours, tomorrow material/tool readiness, forecast delta) — not ten separate per-worker pings. Idempotency key `daily_object_summary:<object_id>:<date>` so it's never sent twice.

**Navigation link between the two owner views**: from Контроль дня, tap object → object's day report; tap worker → their DailyPlan detail; tap a risk indicator → jumps to the matrix at that object's delay point. They're connected, not duplicated.

**Unified DTO, not N+1 frontend calls.** `GET /api/daily-plan/owner/today` returns `{date, summary, rows[]}` where each row already carries plan status/timestamps, shift status/timestamps, planned/done/partial/not_done/blocked counts, planned vs actual quantity, carryover count, tomorrow material/tool readiness booleans, and risk level/reason — assembled server-side from the local DailyPlan store + Check-in + Needs + risk projection. The frontend must never reconstruct this by calling 8 separate endpoints per row.

## Owner — Worker Card, "Сегодня" tab (extends existing overlay, does not recreate it)

**Assumption to verify in Round 0, not yet confirmed**: the spec describes an existing Worker Card as a reusable `NavigationManager` overlay opened via `openWorkerCard(worker_id, returnContext, {initialTab})` from many entry points (Команда, active shifts, Object Detail, assignment, defect, Need, Контроль дня, access list). Round 0 must locate this component and confirm the call signature before Round 4 builds against it — if the real implementation differs (different function name, no shared overlay, per-screen modals instead), the plan below adapts to the real pattern rather than assuming this exact API exists.

**If confirmed**, extend it with 4 tabs: Сегодня, Производительность, Календарь, Профиль. Default tab is **Сегодня** whenever the worker has any activity today (DailyPlan, assignment, active or finished shift); otherwise fall back to last-used tab or Профиль. Every entry point opens the *same* overlay with `initialTab: 'today'` when activity exists — no per-screen duplicate worker modals.

**Сегодня tab, pre-shift state**: object + stage, plan status (ожидает принятия / принят + time + version), action count, planned quantity, estimated hours, "Открыть план" link to the full accepted snapshot (not live Sheet rows — same principle as Контроль дня's detail view: the owner sees what the worker actually accepted, not whatever the Sheet currently says).

**Active-shift state**: "Сейчас работает," start time, elapsed time, pause state if active. **Same no-fake-progress rule as Контроль дня**: never show a completion percentage while the shift is open — only after the Finish Wizard completes. A voluntarily-reported blocker surfaces immediately as a prominent block (type, comment, reported time, "Открыть"/"Написать Worker" actions); once resolved, it drops out of the live block and only shows in detail history — no lingering red state after resolution.

**Post-Finish state**: tab becomes the day's fact report — done/total, planned vs actual quantity, carryover count + reason, per-action breakdown (done/partial-with-remaining-quantity-and-reason/not_done), tomorrow-prep card (material/tool readiness, linked Need if created), and risk stated concretely (Норма / "Carry-over +2ч, срок не изменился" / "Внутренний срок под риском +1 день" / "Договорный срок под угрозой, прогноз +2 дня") — never red for an ordinary partial item, consistent with the color rule already defined for Контроль дня.

**Header quick actions unchanged** (Написать/Календарь/Назначить); Сегодня tab may additionally surface Открыть объект/План/Потребность/Blocker — no duplicate actions across tabs without reason.

**Производительность tab**: kept strictly separate from Сегодня — Сегодня is operational/live, Производительность is historical analytics fed incrementally by completed DailyPlan Finishes (plan completion, actual quantity, hours, carryover, prep-compliance, work_type productivity — same fields as Section II's productivity model above, just surfaced here per-worker instead of in the owner aggregate view).

**Календарь tab**: reuse the existing worker calendar as-is (hours/days/assignments/vacation/sick leave/CSV/date-range) — do not build a second calendar inside Worker Card.

**Профиль tab**: existing avatar/name/birthday(owner-only)/skills/clothing-size/work-data content only — today's shift and productivity numbers do not belong here, they live in their own tabs.

**Navigation**: Worker Card stays a single overlay; switching its internal tabs must not push a new overlay per tab. Back from Worker Card returns to the exact originating screen state (tab, object_id, scroll, filters) — including when opened from Object Detail specifically, back returns to Object Detail, not a generic default. Cross-links stay within the Owner control surfaces: Контроль дня → tap worker → Worker Card/Сегодня → full DailyPlan detail → back → Worker Card/Сегодня → back → Контроль дня. Never routes through Chat/Home as an intermediate stop.

**Single source of data across all three surfaces.** Worker's own "Сегодня" view, the owner's Контроль дня, and Worker Card's Сегодня tab are three *presentations* of the same underlying DailyPlan/Check-in/Needs/risk data — not three independently cached models. A manual Owner edit to `План_дня` in Sheets must propagate identically to all three (per the existing version/amendment rules: pre-acceptance edits just bump the version silently, post-acceptance-pre-Start edits require worker re-acceptance and show "Изменения ожидают подтверждения" in the owner's views, post-Start edits become a tracked Amendment with an explicit diff). Building a separate cache or model per UI surface is exactly the kind of drift this program is designed to eliminate — don't reintroduce it at the frontend layer.

**Shared rendering, not copy-pasted logic**: when Round 2 builds the worker-facing "Сегодня" plan renderer, design it as a reusable presentation function (e.g. `renderDailyPlan(...)`) parameterized for viewer role, so Round 4's Owner Worker-Card detail view reuses the same rendering/business logic instead of a second parallel implementation of the same day-plan display.

## Data model (Round 0 must produce final field-level schemas for)

`PlanStage`, `DailyPlan`, `DailyPlanVersion`, `DailyPlanAcceptance`, `PlanAmendment`, `DailyExecution`, `Carryover`, `ProductivityObservation`, `ProductivityAggregate`, `ContractDocument`, `ProjectPlanDraft` — one local critical store (`daily_plan_store.json`, shape: `{plans, versions, acceptances, amendments, executions, carryovers}`) rather than many scattered JSON files, added to whatever the codebase's real `CRITICAL_JSON_PATHS`-equivalent convention is (Round 0 confirms exact name/location).

## API surface (proposed, Round 0 must check against real existing routes first — do not duplicate)

`GET /api/daily-plan/today`, `POST /api/daily-plan/{plan_id}/accept`, `POST /api/daily-plan/{plan_id}/amendments/{id}/accept`, `GET /api/daily-plan/object/{object_id}?date_from=&date_to=`, `GET /api/daily-plan/owner/matrix?date_from=&date_to=`, `POST /api/daily-plan/replan/{object_id}`, `GET /api/productivity/workers/{user_id}`, `GET /api/productivity/object/{object_id}`. Check-in Start gets optional backward-compatible fields (`daily_plan_id`, `daily_plan_version`, `daily_plan_acceptance_id`) — old Start calls keep working unmodified. Check-in Finish gets the optional `daily_plan_report` multipart field described above, server-validated (never trusts client-supplied title/worker identity, always uses server snapshot).

## Security/ACL (explicit, non-negotiable)

Worker: `today` returns only their own plan; accept only their own plan; execution only against their own current plan — no cross-worker plan_id substitution to mark a colleague's work done. Owner: matrix + analytics access. Sheets sync and Drive credentials: server-side only, never exposed to frontend, OAuth tokens never sent client-side.

## Timezone / working-calendar

All business-date logic uses Europe/Berlin via existing helpers (`business_today`, `business_today_str`, or equivalent — Round 0 confirms exact names) — never frontend `new Date().toISOString()`. Working days are not assumed Mon-Fri/Sat-off automatically; an owner-controlled work calendar (minimally: default working weekdays + exceptions for holiday/workday/site_closed) is required, eventually as its own `Рабочий_календарь` Sheet tab.

## Failure modes Round 0 must explicitly address (one expected-behavior line each)

Sheet offline; Sheet changed mid-shift; duplicate Finish; retried Finish; worker offline; worker started without a plan; plan deleted after acceptance; two workers on one task; carryover applied twice; contract re-uploaded; contract changed after ingestion; AI returns invalid JSON; missing quantity; missing norm; blocked stage; no next working day defined.

---

# III. Round 0 — exact deliverable for this plan's execution

When this plan moves to execution, Round 0 must:

1. Run `git status`, `git branch --show-current`, `git rev-parse HEAD`, `git log --oneline -15` on the VPS repo — confirm working tree is clean and record the actual current SHA (do not trust `90fd59b` blindly, per the owner's own instruction).
2. Read and map: `backend/main.py`, `backend/objekte_lib.py`, `backend/roadmap_lib.py`, `backend/work_types.py`, `backend/assignment_matching.py`, `frontend/js/checkin.js`, `finish-wizard.js` (if it exists), `objects.js`, `object-info.js`, `profile.js`, `home.js`, `app.html`, plus any daily/plan/checklist-related routes not yet known. **Also locate the existing Worker Card overlay** referenced in the spec (`openWorkerCard(worker_id, returnContext, {...})`, a shared `NavigationManager`-style overlay opened from Команда/active shifts/Object Detail/assignment/defect/Need/access list) — confirm its real file, call signature, and tab-switching mechanism before Round 4 assumes this exact API; report the actual pattern found (or its absence) in the Round 0 report rather than assuming the spec's description is accurate as written.
3. Sheet discovery: read headers only (no writes) for Объекты, Этапы, Расходы, and any workers/roadmap/plan/checklist/hours-related tabs.
4. Productivity field hunt: full-repo grep per the table format specified above, with a direct found/not-found verdict — no invented field.
5. Sheets sync decision: confirm whether the 5 new tabs can be safely added to the existing spreadsheet (proposal only, do not create tabs in Round 0).
6. Drive OAuth check: confirm only whether the current credential has Drive scope; if not, report `DRIVE_SCOPE_REQUIRED` and stop there — no token changes, no listing personal files.
7. Produce final field-level schemas for the 11 data model entities listed above.
7a. Work out how `GET /api/daily-plan/owner/today` can be assembled **without N+1 Google Sheets calls per row** — specify exactly which fields come from the local DailyPlan store, which from Check-in, which from Needs, and which from the risk projection, so the unified-DTO requirement above is actually implementable against the real data layout, not just aspirational. Include this in the Round 0 report explicitly.
7b. Worker Card integration specifics (owner explicitly requires these 8 points answered in the Round 0 report, not deferred to Round 4): (i) exactly how `openWorkerCard` is currently invoked from every existing entry point (Команда, Часы команды, active shifts, Object Detail, worker-list-per-object, Assignment, Defect, Need, access list); (ii) how the 4 tabs (Сегодня/Производительность/Календарь/Профиль) can be added without duplicating the Worker Card; (iii) exact data needs for `GET /api/daily-plan/owner/today` (cross-reference with 7a); (iv) confirmed N+1-free assembly approach; (v) how Worker Card's Сегодня tab reads DailyPlan local cache + Check-in + blockers + carryover + Needs + risk projection specifically (not just the owner-matrix endpoint — the per-worker detail view may need a different query shape); (vi) how `NavigationManager` `returnContext` is actually preserved today, to confirm the back-stack behavior described above is achievable; (vii) what UI signal should set `initialTab='today'`; (viii) how the accepted-snapshot-vs-live-Sheets distinction will actually render to the owner after a manual Sheet edit. If `openWorkerCard`/`NavigationManager` turn out not to exist as described, report that plainly and propose the closest real equivalent — do not assume the spec's component names are accurate.
8. Walk through all ~16 failure modes listed above with expected behavior for each.
9. Note real system problems noticed incidentally during discovery, tagged P0 (data/security/release blocker) / P1 (reliability/business correctness) / P2 (UX/performance/tech debt) — do not fix unrelated issues now.
10. Final report per the owner's exact required structure: START SHA, working tree status, current architecture map (Roadmap/Stages/Assignment/Check-in/Needs/Alerts/Profiles/Sheets), exact DailyPlan insertion point, current Sheets schema, proposed Sheets schema, Drive OAuth status, existing productivity fields (found or not-found), proposed data models, API proposal, Finish integration proposal, plan versioning proposal, Sheet conflict proposal, carryover algorithm, risk algorithm proposal, contract ingestion proposal, productivity formula proposal, P0/P1/P2 findings, files that Round 1 will touch, Round 1 risks.
11. Final status line: **READY FOR ROUND 1**, **BLOCKED**, or **ARCHITECTURE CONFLICT FOUND**.
12. Stop. No Round 1 code, no Sheets tab creation, no Drive changes, no deploy, until the owner gives a separate explicit GO.

---

# K. Fixing the "we discussed this before and lost it" gap

Unchanged finding from earlier in this session: `capture-approach` (`~/.claude/skills/capture-approach/SKILL.md`) only triggers after a task is *solved*, with no trigger for an idea or requirement that surfaces mid-conversation without an immediate build — which is exactly how Phase 4b's productivity work went undiscovered until a full session-history dig, and exactly what's happening again in this session (a large unstructured addendum, then a full external spec, both landing mid-build).

**Action item, not part of Round 0's code-freeze** (this is a `~/.claude/skills/` edit, unrelated to the miniapp repo, safe to do independent of the GO gate above — first thing after this plan is approved, before or alongside Round 0): extend `capture-approach` or add a sibling `capture-idea` skill with a second trigger class — mid-conversation ideas/requirements mentioned but not immediately built, and end-of-planning-session capture of decisions *and rejected alternatives* into a `project_*.md` memory file, so future search surfaces it without a full transcript dig. This plan itself, once approved, should be captured as a memory pointing at the plan file and at this Round 0/production-control program by name.

---

**Обновление 07.09.2026: STOP-гейты между раундами отменены пользователем явно.** Ниже — исходный план с паузами между раундами (Round 1 требует отдельного "го" после Round 0 и т.д.). Пользователь прямо сказал выполнять всё автономно на сервере до конца без остановок. Единственное исключение — реальные развилки (архитектурный выбор, риск для продакшна, конфликт в брифе) выносятся в чат сразу, но НЕ останавливают остальную работу — см. `feedback_autonomous_server_execution.md` п.7a.

# Future rounds (listed for context only — NOT executed until separate owner GO after each)

- **Round 1** — DailyPlan backend core + versioning + Sheet schemas/sync.
- **Round 2** — Worker "Сегодня" UX + acceptance + persistent day-plan bar + Check-in Start link.
- **Round 3** — Finish integration + fact + carryover + tomorrow-prep + automatic Needs.
- **Round 4** — Owner matrix + plan/fact + risk/replan; plus: Контроль дня (daily control screen), Owner DailyPlan detail view, object daily summary, manager audited correction, plan/fact matrix, risk visualization, Worker Card "Сегодня"/"Производительность" tab extensions. Round 4 also ends with STOP.
- **Round 5** — Google Drive contracts + extraction + Draft Project Plan + Owner approval.
- **Round 6** — Productivity observations + effective rates + Worker Card analytics + planner feedback.
- **Round 7** — Hardening + full tests + real Telegram E2E checklist.

Each round ends with a STOP + report; no automatic progression to the next.

---

*End of plan.*
