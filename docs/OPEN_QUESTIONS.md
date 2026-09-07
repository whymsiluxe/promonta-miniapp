# Open Questions — Production Control Program

> Per AUTONOMOUS_EXECUTION_RULES.md: real architectural forks go here with full context.
> The pipeline does NOT stop waiting for answers — a provisional conservative decision
> is made and clearly noted. Owner reviews and corrects if needed.

---

## Q1 — Drive OAuth scope (BLOCKED sub-feature)

**What**: Does `.sheets.json` (the existing Google credential) carry Drive read scope?
The file stores only `client_id, client_secret, refresh_token` — no scope metadata.

**Why it matters**: Contract ingestion (Round 5) needs Drive read access to a specific
folder. If the scope is missing, reauthorizing would change the stored refresh token.

**Provisional decision**: Mark contract ingestion as `DRIVE_SCOPE_REQUIRED / BLOCKED`.
Build Rounds 1-4, 6-7 completely independently of Drive. Round 5 builds stub endpoints
gated on `CONTRACTS_DRIVE_FOLDER_ID` env var. Owner must verify scope and provide a
`CONTRACTS_DRIVE_FOLDER_ID` value before Round 5 can go live.

**Unblocks**: All rounds except Drive-dependent parts of Round 5.

**Owner action needed**: Check whether the credential has Drive scope. Command to verify
scope without printing the token:
```bash
python3 -c "
import json, urllib.request, urllib.parse
c = json.load(open('/home/promonta/agent/.sheets.json'))
b = urllib.parse.urlencode({'client_id': c['client_id'], 'client_secret': c['client_secret'],
  'refresh_token': c['refresh_token'], 'grant_type': 'refresh_token'}).encode()
r = json.load(urllib.request.urlopen('https://oauth2.googleapis.com/token', b, timeout=20))
tok = r['access_token']
info = json.load(urllib.request.urlopen('https://www.googleapis.com/oauth2/v3/tokeninfo?access_token=' + tok, timeout=10))
print('SCOPES:', info.get('scope', 'NOT FOUND'))
"
```

---

## Q2 — Нормы работ: where to store production norms?

**What**: The spec requires a `Нормы_работ` Sheets tab with baseline productivity rates
per work type. These serve as priors for planning. However, populating real German
construction norms (VOB/DIN-based) requires verified sources — the spec explicitly
prohibits AI-invented norms.

**Provisional decision**: Create the `Нормы_работ` tab schema but leave all rows empty
with `norm_verified=false`. The owner fills in real rates from their experience or
verified sources. The planning system uses `requires_owner_input=true` for any stage
where no verified norm exists.

**Owner action needed**: For each work type the owner wants to plan, provide:
- `baseline_rate` (unit/person-hour, e.g. 5 m²/h for Malerei 1 coat)
- `unit` (м², lm, Stück, etc.)
- Source (own experience, VOB-Referenz, etc.)

---

## Q3 — Working calendar: weekdays assumption

**What**: The spec requires a working calendar (not just Mon-Fri). Do objects have fixed
working weekdays, or is it always Mon-Fri + specific holiday exceptions?

**Provisional decision**: Default to Mon-Fri working days, Germany public holidays
for Sachsen excluded. Store as `work_calendar.json` with `{default_working_days:
[1,2,3,4,5], holiday_exceptions: [], extra_workdays: []}`. Owner can override per
object or globally.

**Owner action needed**: Confirm if workers sometimes work on Saturdays, and if so,
whether it's per-object or global.

---

## Q4 — Sheets tab creation: which spreadsheet?

**What**: 5 new tabs (`План_этапов`, `План_дня`, `Нормы_работ`, `Факт_дня`,
`Производительность`) must be added to the existing spreadsheet. The existing
SHEET_ID in `objekte_lib.py` is `14CXpSaW9ErmViK09zAh09X52EUmEJjnkxGUSmW3Z9sA`.

**Provisional decision**: Add all 5 tabs to the same spreadsheet (same ID). This keeps
all Promonta operational data in one place. The plan_sync.py worker uses this same
SHEET_ID.

**Risk**: If the spreadsheet is shared with external parties (clients/partners), adding
plan/fact/productivity tabs exposes operational data. Check before creating tabs in prod.

**Owner action needed**: Confirm it's OK to add 5 new tabs to the existing spreadsheet,
or provide a separate SHEET_ID for the production-control data.

---

## Q5 — plan_sync.py systemd timer vs cron

**What**: Should the plan_sync.py worker run as a systemd timer or as a cron job?

**Context**: `news_pipeline.py` uses cron; most other periodic scripts use systemd
timers. The spec says 60s interval. systemd timers provide better restart/failure
handling and journal logging.

**Provisional decision**: systemd timer (like `digest.py`, `followup.py`, etc.).
Create `promonta-plan-sync.service` + `promonta-plan-sync.timer`. Owner must activate
after reviewing.

---

## Q6 — Failure modes: expected behavior

Per the spec, explicit expected behavior for all 16 failure modes:

1. **Sheet offline**: `plan_sync.py` logs error, uses cached local state, does not clear
   existing plan data. Workers see the last synced plan. Alert fires if sync has failed
   for >5 min.

2. **Sheet changed mid-shift**: Pre-acceptance: version bump, worker sees "план обновлён"
   on next poll. Post-acceptance-pre-Start: re-acceptance required, Amendment created.
   Post-Start: tracked Amendment, worker acknowledges separately.

3. **Duplicate Finish**: Idempotency key on `checkin_finish`. Second call with same key
   returns cached result without re-projecting.

4. **Retried Finish**: Same idempotency key — safe via existing idempotency mechanism.
   `apply_daily_execution(session_id)` is idempotent via `execution:<session_id>` key.

5. **Worker offline**: App shows last-loaded plan. Acceptance/Start/Finish queue
   client-side and retry on reconnect (existing behavior, no new offline queue).

6. **Worker started without a plan**: checkin_start succeeds (plan not required).
   A "started_without_plan" flag is set in checkin_meta. Owner alert fires.

7. **Plan deleted after acceptance**: The accepted snapshot (DailyPlanAcceptance record)
   is permanent — deletion from Sheets does not erase it. Worker's today-screen shows
   the accepted snapshot. plan_sync raises a "plan deleted after acceptance" alert.

8. **Two workers on one task**: Team output is a crew_observation, not auto-split.
   Both acceptance records exist independently. Individual rate only updated from
   solo work or with explicit `contribution_weight`.

9. **Carryover applied twice**: Idempotency key `carryover:<source_plan_id>:<date>`.
   Second application returns existing carryover without re-appending to next plan.

10. **Contract re-uploaded**: `contract_ingest_state.json` keyed by `(file_id, hash)`.
    Re-upload of identical content → no-op. Changed content → new `ContractDocument`
    version; existing approved plan is NOT auto-superseded (owner explicitly re-reviews).

11. **Contract changed after ingestion**: The ingested text snapshot is immutable once
    status=ingested. A change to the Drive file creates a new version. Owner sees
    "contract updated" alert and must re-review/re-approve the affected ProjectPlanDraft.

12. **AI returns invalid JSON**: Claude extraction output validated via structured schema.
    If invalid: `status=extraction_failed`, `error` field logged, retried once. If still
    invalid: `status=needs_manual_review`, owner notified.

13. **Missing quantity**: Field set to `null`, `requires_owner_input=true`,
    `MISSING_DATA` reason. Stage gets no auto-planned quantity. Norm calc skipped.

14. **Missing norm**: `norm_check_required=true`. Stage item shows estimated time as null.
    Owner fills norm in `Нормы_работ` → sync recalculates.

15. **Blocked stage**: DailyPlan item `status=blocked`, `reason_code` required. Carried
    forward. Owner alert. Replan Engine flags if blocking critical path.

16. **No next working day defined**: Carryover scheduled for next working day per
    `work_calendar.json`. If calendar has no defined next day (e.g. indefinite pause),
    carryover is created with `target_date=null, status=pending_scheduling`. Owner alert.

---

## Q7 — Worker Card tab back-stack

**What**: The spec says "back from Worker Card returns to exact originating screen state."
The current `closeWorkerCard()` does NOT navigate back — it just removes the overlay and
resets `_profileMode` to 'owner-self'. It doesn't use `returnCtx` at all.

**Finding**: `_profileReturnView` is set from `returnCtx` but `closeWorkerCard()` never
reads it. The back navigation actually works via `NavigationManager.registerOverlay` —
when the back button is pressed, `NavigationManager.back()` calls `closeWorkerCard()` via
the overlay stack, and the underlying view is still there (overlays don't navigate away
from the current view, they layer on top). So the "return to originating screen" behavior
already works naturally — closing the overlay reveals the view underneath.

**Provisional decision**: No change needed for basic back-stack behavior. The `returnCtx`
parameter is vestigial for navigation purposes (could be used for analytics or initial-tab
selection). Round 4 can use `returnCtx.initialTab` to set which tab opens by default.

---

## Q8 — initialTab logic for Worker Card

**What**: The spec says default tab should be "Сегодня" when the worker has activity today.

**Provisional decision**: `openWorkerCard(uid, {initialTab: 'today'})` is the new call
signature from Round 4 entry points. When `returnCtx.initialTab` is set, that tab opens.
When not set (existing callers), default to 'today' if the worker has any DailyPlan or
active checkin today, else fall back to the existing period-stats view (now renamed
'productivity' tab).

---

## Q9 — Existing failing tests

**Pre-existing at run start (do not fix unless they block new tests)**:
1. `test_worker_cannot_fetch_other_threads_chat_attachment`
2. `test_active_worker_reads_object_tasks`
3. `test_active_worker_creates_task`

These are pre-existing access-control gaps, unrelated to the production-control program.
They should not be introduced as regressions by Round 1-7 code, but fixing them is
explicitly out of scope for this run.

---

## Owner answers (2026-09-07, 19:20 CEST)

- **Q1 (Drive scope)**: Deferred. Continue all rounds without Drive; Round 5 stays stubbed/blocked as planned.
- **Q2 (Нормы работ real rates)**: Deferred. Continue with norm_verified=false rows as planned.
- **Q3 (weekend work)**: Confirmed — Mon-Fri default is correct, no Saturday work. No change needed.
- **Q4 (Sheets tabs location)**: Confirmed — same spreadsheet as Объекты/Этапы (SHEET_ID 14CXpSaW9ErmViK09zAh09X52EUmEJjnkxGUSmW3Z9sA). Proceed with tab creation there.

All provisional decisions in Q1-Q9 above are CONFIRMED. Continue Round 2 onward with no further blocking on these.
