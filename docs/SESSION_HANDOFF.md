# Session handoff

**Date**: 2026-07-23, ~13:45 Berlin.
**Branch**: `main` (renamed from `master` during this session, now the default on GitHub too).
**Last commit**: `d30d2c9` "chore: add GitHub PR/issue templates and CODEOWNERS placeholder" — pushed.
**Repo**: https://github.com/whymsiluxe/promonta-miniapp — **private**, confirmed via `gh repo view`.

## Goal of this session

Recover from a lost Claude Code session on the Promonta Mini App: locate the real (VPS) state of the code, secure it in version control, document it accurately from the actual code (not assumption), and publish to a private GitHub repo — without doing any destructive operations or starting a UI redesign.

## What was done (all completed)

1. Audited the project — found the Mac-local copy was stale (Jul 8-12) vs. the live VPS code (through Jul 23), and that backend + frontend lived in separate directories with separate (or no) git history.
2. Built `/home/promonta/agent/miniapp-repo/` on the VPS: `backend/` (copied source only, no data) + `frontend/` (git-subtree-merged from `/var/www/miniapp`'s existing 14-commit history, full history preserved).
3. Verified no hardcoded secrets anywhere committed (multiple grep passes, including a final pass on the docs themselves).
4. Wrote `.gitignore`, `backend/.env.example`, `backend/requirements.txt` (none existed before).
5. Wrote the full `docs/` set (17 files) plus `README.md` and `CLAUDE.md` (governance) from reading the actual code — `main.py` (93 routes, all grepped and classified by permission; GPS/chat/tools/critical-alerts routes read in full detail), frontend JS module list, systemd/Caddy config, installed Python packages.
6. Corrected one piece of stale institutional memory: unknown Telegram user IDs get a hard 403 now, not a silent `worker` default (a whitelist hardening happened since the note that said otherwise was written) — documented in `docs/ROLES_AND_PERMISSIONS.md` and `docs/CHANGELOG.md`.
7. Flagged (did not silently fix) one permission gap: `POST /api/objects/{object_id}/tasks` lets any worker add a task to any object, not just their own assignment. See `docs/ROLES_AND_PERMISSIONS.md` and `docs/TODO.md` REC-9.
8. Added `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}`, `.github/CODEOWNERS` (placeholder — owner's GitHub username unknown, not guessed).
9. Authenticated `gh` CLI on the Mac (account `whymsiluxe`, via device-code browser flow, no token pasted in chat).
10. Created the private GitHub repo, transferred the token to the VPS over SSH stdin (never displayed), pushed, then **removed the token from the VPS disk and from `git remote -v`** immediately after — `origin` now points at a plain HTTPS URL with no embedded credential.
11. (Off-task, blocking) found and killed ~400+ orphaned `chroma-mcp` processes on the Mac that had filled local disk to zero free space mid-session (`ENOSPC` on every shell command, including `df -h` itself). User manually freed additional space via Finder. Not a miniapp issue — a `claude-mem`/`uvx` process-reaping bug worth someone looking into separately.

## What was NOT done (deliberately, or as follow-up)

- Full endpoint-by-endpoint permission audit — only GPS/chat/tools/critical-alerts routes were read in full; the other ~85 were classified by decorator (owner-gated vs. not) via grep, not individually read line-by-line. See `docs/TODO.md` REC-3.
- Deciding what to do with the stale Mac-local copy at `~/Projects/promonta/miniapp/frontend/` — left untouched (not deleted, per the no-destructive-action-without-confirmation rule). See `docs/TODO.md` REC-2.
- Setting up an actual deploy pipeline from this repo back to the VPS's live-serving directories (`/var/www/miniapp/`, `/home/promonta/agent/miniapp/`) — this repo is the source of truth now, but nothing yet automates syncing a commit here to production. See `docs/TODO.md` REC-1 and `docs/DEPLOYMENT.md`.
- Any UI/UX changes — explicitly out of scope for this recovery per the task brief.
- No CI, no automated tests were added (none existed before either) — `docs/TESTING.md` and `docs/TODO.md` REC-6 record this honestly rather than fabricating either.

## Next recommended step

Set up the sync-back path from `miniapp-repo` to the live VPS directories (`docs/TODO.md` REC-1), so future edits go: edit in repo → commit → sync to `/var/www/miniapp` or `/home/promonta/agent/miniapp` → restart service — rather than editing production directly again, which is the exact failure mode this recovery fixed.

## Warnings for whoever continues this

- Do not treat `~/Projects/promonta/miniapp/` (Mac-local) as current — it is 2-3 weeks stale versus the VPS/GitHub state.
- Do not edit `/var/www/miniapp/` or `/home/promonta/agent/miniapp/` directly on the VPS without also syncing the change into `/home/promonta/agent/miniapp-repo/` and committing/pushing it.
- If shell commands start failing with `ENOSPC` again on the Mac, check `ps aux | grep -c chroma-mcp` before assuming it's unrelated — this leak may recur until its root cause (in the `claude-mem`/`uvx` tooling, not this project) is fixed.
- `gh` on the Mac is now authenticated as `whymsiluxe` for this repo — any future GitHub operation for this project should use that account unless told otherwise.
