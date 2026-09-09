# Autonomous Execution Rules — Recovery + Architecture + UX Round

You are executing the plan at `~/.claude/plans/fancy-booping-hammock.md` on the owner's Mac
(NOT in this repo — read it via the plan's full content, which has been copied into this
repo as `docs/EXECUTION_PLAN.md` for on-VPS reference). Read `docs/EXECUTION_PLAN.md` fully
first — it is the complete spec: Phase 0 through Phase 7, every finding, every owner
correction. This file adds only the operating rules for running unattended.

## Core mandate

Execute Phase 0 (incident root-cause fix + firewall) through Phase 7 (performance/observability),
in order, without stopping for a "GO" message between phases — EXCEPT the final deploy, which
is explicitly forbidden from this autonomous session (see "No production deployment" below).

## MANDATORY FIRST ACTIONS — before touching anything else

1. Read `docs/EXECUTION_PLAN.md` in full.
2. Read `docs/HANDOFF.md` for current status (if this is a resumed session, not a fresh start).
3. Check `docs/EXECUTION_STATE.txt`. If it is not `RUNNING`, STOP immediately — do not proceed,
   do not "fix" the state file, do not resume. A non-RUNNING state means either the work is
   done, deliberately stopped for review, or has permanently failed — in every case, the correct
   action is to do nothing and exit.
4. Check `docs/EXECUTION_RESTART_COUNT.txt`. If it is already `3` or higher, set
   `docs/EXECUTION_STATE.txt` to `FAILED`, write the reason to `docs/HANDOFF.md`, and STOP.
5. `git log --oneline -20` and `git status` — determine exactly which phases are already
   committed. **Never re-run a phase whose commit already exists** unless `docs/HANDOFF.md`
   explicitly says that phase's verification failed and needs redoing.
6. Before ANY pytest invocation, in this exact order:
   ```
   export PROMONTA_ENV=test
   export MINIAPP_DATA_ROOT=$(mktemp -d)
   test "$MINIAPP_DATA_ROOT" != "/home/promonta/agent/miniapp" || { echo "REFUSING: DATA_ROOT resolved to production"; exit 1; }
   ```
   This is required on every single pytest invocation, no exceptions, even after Phase 0's
   in-code firewall (0.10) is built — this is belt-and-suspenders, not a replacement for it.

## The one exception — real decision points, handled WITHOUT halting everything

If a genuine fork-in-the-road comes up — an architectural choice with several reasonable
options, something irreversible/risky to production, a real conflict between two parts of
the plan, a discovery that meaningfully changes scope (e.g. Phase 1's live Sheet header
check reveals something unexpected) — do this:

1. Write it into a running `docs/OPEN_QUESTIONS.md` with full context: what the question is,
   why it matters, what you're leaning toward and why, what's blocked by it.
2. Do NOT stop the rest of the work. Keep executing every other part of the plan that
   doesn't depend on that specific answer.
3. If you must make a call to keep moving, make the more conservative/reversible choice,
   note it clearly as a provisional decision in OPEN_QUESTIONS.md, and keep going.

## Quality bar

- Run the pytest suite before and after each meaningful change — **always** with the
  MANDATORY FIRST ACTIONS' env setup, never bare `pytest tests/`.
- Never leave the repo in a broken state between work chunks. If you stop for any reason
  (usage limit, crash), the repo at that moment must be in a working, tested state, or
  clearly marked WIP in HANDOFF.md with exactly what's incomplete.
- Commits should be real, working, incremental — matching the plan's suggested commit
  boundaries per phase, not one giant end-of-run commit. Normal git hygiene: no `--no-verify`,
  no force-push, create new commits rather than amending.
- Before creating Google Sheets tabs or touching Drive/Sheets in any write capacity: the
  plan's Phase 1 correction requires reading the live "Объекты" header FIRST, read-only.
  Do not write to any existing Sheets tab or column.

## Continuity — HANDOFF.md

Update `docs/HANDOFF.md` continuously as you go, not just at the end — what's done, what's
in progress, what's left, and any non-trivial decisions made and why. This is what a resumed
session (yours or a human's) reads to know where things stand.

## EXECUTION STATE MACHINE — read this before doing anything else

`docs/EXECUTION_STATE.txt` holds exactly one of: `RUNNING`, `COMPLETE`, `FAILED`, `STOPPED_FOR_REVIEW`.

- While you are actively working: state stays `RUNNING`.
- When all 7 phases are done, verified, and the final report is written per the plan's
  "Deploy" section: set state to `STOPPED_FOR_REVIEW` (this is the normal successful end —
  "complete AND awaiting the owner's deploy decision", not a bug).
- If you hit an unrecoverable error (not a usage limit, an actual logical dead end you
  cannot resolve even conservatively): write the full context to `docs/HANDOFF.md` and
  `docs/OPEN_QUESTIONS.md`, then set state to `FAILED`.
- **Never set state to `COMPLETE`** — that value is reserved for a future round after the
  owner has reviewed and the deploy has actually happened; this round's successful terminal
  state is `STOPPED_FOR_REVIEW`.
- If you are stopped by a usage limit (not by your own choice): leave state as `RUNNING`
  (the watchdog, described below, will restart you) but make sure `docs/HANDOFF.md` is
  current at that exact moment so the resumed session can pick up cleanly.

## Watchdog behavior (informational — you don't control this, but must cooperate with it)

A bounded watchdog (NOT the previous infinite 5-minute-interval one, which is what caused
yesterday's incident) checks `docs/EXECUTION_STATE.txt` periodically. It restarts you ONLY
if the state is `RUNNING`. It increments `docs/EXECUTION_RESTART_COUNT.txt` on each restart
and refuses to restart a 4th time (see MANDATORY FIRST ACTIONS step 4). It permanently
disables itself the moment state becomes anything other than `RUNNING`. Your job: keep
HANDOFF.md accurate so each restart is a clean resume, not a redo.

## No production deployment from this autonomous session

Per the plan's "Deploy" section: do NOT run `deploy_frontend.py` against the live
`/var/www/miniapp`, do NOT restart `promonta-miniapp.service`, do NOT modify
`/etc/systemd/system/promonta-miniapp.service`. All of Phase 0-7's work happens in
`/home/promonta/agent/miniapp-repo` (the git repo) — the live production directories
(`/home/promonta/agent/miniapp`, `/var/www/miniapp`) are read-only reference points for
verification (e.g. comparing deployed vs. repo state) but are never written to by this
session. The final report documents the deploy plan; a human executes it later.

## MANDATORY — Foundation Completion Addendum (added 2026-09-09, owner review of Phase 2)

Before setting EXECUTION_STATE.txt to STOPPED_FOR_REVIEW or writing a final
READY FOR OWNER REVIEW report: after Phase 7 is complete, you MUST read
docs/FOUNDATION_COMPLETION_ADDENDUM.md in full and execute it as a mandatory
FOUNDATION COMPLETION phase — not an optional backlog item.

The owner explicitly rejected treating these as harmless documented limitations.
Four items in that addendum (Sheets→DailyPlan sync, per-worker amendment ack,
server-trusted DailyPlan/checkin linkage, durable Finish outbox) are original
Production Control requirements, not deferred nice-to-haves.

Do not mark EXECUTION_STATE.txt STOPPED_FOR_REVIEW or declare READY FOR OWNER
REVIEW until the addendum's own re-report of all 16 Production Control items
has been produced and none of those four specific items are missing. If any
of the four remain missing after a good-faith attempt, the final status must
explicitly read NOT READY with the specific blocker — do not soften this to
a passing status.

No production deployment, as already stated elsewhere in this file.
