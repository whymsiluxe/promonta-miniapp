# Autonomous Execution Rules — Production Control Program

You are executing `docs/PRODUCTION_CONTROL_PLAN.md` (read it fully first — it is the complete architecture spec, Round 0-7 scope, data models, Sheets schemas, all the "do not build" constraints). This file adds the operating rules for running unattended.

## Core mandate

Execute Round 0 (discovery) then continue **directly into Round 1 through Round 7** — real implementation: DailyPlan backend, Sheets schema/sync worker, worker "Сегодня" UX, Finish wizard integration, carryover, owner Контроль дня + matrix + Worker Card extensions, Google Drive contract ingestion, productivity system, hardening/tests. **No stopping between rounds. No waiting for a "GO" message.** The plan file's own "STOP after each round" language is superseded — the user explicitly overrode it (07.09.2026): run start to finish autonomously, however many hours/sessions it takes.

## The one exception — real decision points, handled WITHOUT halting everything

If a genuine fork-in-the-road comes up — an architectural choice with several reasonable options, something irreversible/risky to production, a real conflict between two parts of the spec, a discovery that meaningfully changes scope — do this:

1. Write it into a running `docs/OPEN_QUESTIONS.md` with full context: what the question is, why it matters, what you're leaning toward and why, what's blocked by it.
2. **Do NOT stop the rest of the work.** Keep executing every other part of the plan that doesn't depend on that specific answer.
3. If you must make a call to keep moving, make the more conservative/reversible choice, note it clearly as a provisional decision in OPEN_QUESTIONS.md, and keep going — don't let one uncertainty freeze the whole pipeline.

This is a hard rule from the user: questions come back to them, the pipeline does not stop and wait.

## Non-negotiable architecture constraints (from the plan, Section II)

No second stage system, no second check-in, no second assignment system, no second work-type catalog, no second notification system, no duplicate Roadmap, no second Worker Card, no second calendar inside Worker Card, no bottom-nav changes, no second parallel DailyPlan representation for the owner. Worker and Owner always view different *presentations* of the same underlying DailyPlan data.

## Quality bar

- Run the existing pytest suite (~355+ tests) before and after each meaningful change. Never leave the repo in a broken state between work chunks — if you stop for any reason (usage limit, crash), the repo at that moment must be in a working, tested state, or clearly marked WIP in HANDOFF.md with exactly what's incomplete.
- Before creating Google Sheets tabs or touching Drive: do the safety checks the plan specifies. Check Drive OAuth scope before any Drive work — do not silently reauthorize or overwrite tokens. If Drive scope is missing, mark that sub-feature `DRIVE_SCOPE_REQUIRED` / BLOCKED in OPEN_QUESTIONS.md and continue with everything else that doesn't need Drive.
- Commits should be real, working, incremental — not one giant end-of-run commit. Use normal git hygiene (the plan/user's own conventions: no `--no-verify`, no force-push, create new commits rather than amending).

## Continuity — HANDOFF.md

Maintain `docs/HANDOFF.md` **continuously**, not just at the end: what's done, what's in progress, what's left (by round/step), all non-trivial decisions made and why, technical risks found, exact files touched. A fresh process invocation (after a crash, VPS reboot, or usage-limit reset) must be able to read HANDOFF.md alone and resume with zero reliance on any conversation memory.

## If you hit a usage/rate limit mid-work

Do not just stop silently. Update HANDOFF.md with exact state, then self-reschedule via `at` or `cron` for a reasonable retry window (e.g. a few hours out, or when a known reset window applies), so the work chain continues automatically rather than waiting for a human to notice and manually restart it. Check both `root` and `promonta` user's `at`/`cron` queues before adding a new one, to avoid duplicate scheduled resumes.

## Environment notes

- Repo: `/home/promonta/agent/miniapp-repo/` on this VPS. Deployed frontend: `/var/www/miniapp/`. Deployed backend service: `promonta-miniapp` (systemd).
- `claude` CLI should be available and authorized via `/etc/claude-agent.env` — verify and source explicitly if needed under whichever user you're running as.
- This VPS also runs other production services (Telegram bot, etc.) — do not restart/touch unrelated services.

## When genuinely done

If all 7 rounds are complete, tests pass, and the app is deployed and verified working end-to-end: write a final summary to HANDOFF.md, stop cleanly (no more scheduled resumes), and leave OPEN_QUESTIONS.md as the definitive list of anything still needing a human decision.


## CRITICAL — self-reschedule on usage limit is MANDATORY, not optional

The previous run (2026-09-07 14:52-15:16) hit the account usage limit and DIED without
scheduling a resume. This must not happen again. The moment you see any output resembling
"You've hit your session limit" or similar rate-limit message:

1. IMMEDIATELY update docs/HANDOFF.md with exact current state (this is your last chance
   before the process dies).
2. Schedule a resume via `at` RIGHT THEN, before doing anything else. Write the resume
   command to a shell script file first (e.g. /home/promonta/agent/miniapp-repo/docs/resume_cmd.sh),
   then pipe that script's path into `at` — avoids shell-quoting problems with nested
   quotes in a one-liner. The resume command should re-launch via systemd-run with
   EnvironmentFile=/etc/claude-agent.env, WorkingDirectory=the repo, logging to
   docs/autonomous_run.log, prompting claude to read docs/HANDOFF.md fully and continue
   the Production Control Program from exactly where it left off per
   docs/AUTONOMOUS_EXECUTION_RULES.md.
   Schedule for the stated reset time + 5 min buffer if a specific time is given in the
   limit message, otherwise 2 hours out as a safe default.
3. Check `atq` before scheduling to avoid stacking duplicate resume jobs (as both root
   and promonta users).
4. This is not a suggestion — a died process with no scheduled resume is a failure of
   this run's own rules, not an acceptable stopping point short of full plan completion.

## Token efficiency (added 2026-09-07, mid-run)

The owner asked to conserve tokens/usage. Concretely:
- Do not re-read files you already read this run unless they changed — trust your own HANDOFF.md notes on file contents/line numbers instead of re-opening files to double-check.
- Do not re-explain the plan to yourself at the start of every round — you already have HANDOFF.md, PRODUCTION_CONTROL_PLAN.md, and AUTONOMOUS_EXECUTION_RULES.md; skim only the sections relevant to the current round, not the whole plan again.
- Prefer targeted greps/reads over dumping whole large files (main.py is 7600+ lines — read only the relevant function ranges, not the full file).
- Keep commits and test runs meaningful-sized — don't run the full pytest suite after every single small edit; batch related changes, then test.
- Keep OPEN_QUESTIONS.md / HANDOFF.md updates concise — enough for a fresh session to resume, not verbose restating of context already in PRODUCTION_CONTROL_PLAN.md.
