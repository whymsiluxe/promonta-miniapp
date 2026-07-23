# Session handoff

**Date**: 2026-07-23, ~13:20 Berlin.
**Branch**: `master` (repo root: `/home/promonta/agent/miniapp-repo/` on the VPS).
**Last commit**: `8836e81` "chore: merge frontend git history (14 commits) as frontend/ subtree" — a documentation commit adding everything in `docs/` plus `README.md`/`CLAUDE.md` was pending as of this handoff, see below.

## Goal of this session

Recover from a lost Claude Code session on the Promonta Mini App: locate the real (VPS) state of the code, secure it in version control, document it accurately from the actual code (not assumption), and publish to a private GitHub repo — without doing any destructive operations or starting a UI redesign.

## What was done

1. Audited the project (see conversation history / this doc's siblings for full detail) — found the Mac-local copy was stale (Jul 8-12) vs. the live VPS code (through Jul 23), and that backend + frontend lived in separate directories with separate (or no) git history.
2. Built `/home/promonta/agent/miniapp-repo/` on the VPS: `backend/` (copied source, no data) + `frontend/` (git-subtree-merged from `/var/www/miniapp`'s existing 14-commit history).
3. Verified no hardcoded secrets in anything committed.
4. Wrote `.gitignore`, `backend/.env.example`, `backend/requirements.txt` (none existed before).
5. Wrote the full `docs/` set plus `README.md` from reading the actual code (`main.py`, frontend JS modules, systemd/Caddy config) — see `docs/PROJECT_STATE.md` for the itemized list.
6. Flagged (did not silently fix) one permission gap: `POST /api/objects/{object_id}/tasks` not assignment-scoped.
7. (Off-task but blocking) found and killed ~400+ orphaned `chroma-mcp` processes on the Mac that had filled the local disk to zero free space mid-session, making every shell command fail with ENOSPC. Not related to the miniapp itself.
8. Started `gh auth login --web` for GitHub publishing — **awaiting user to complete browser auth as of this handoff**.

## What was NOT done

- **Not pushed to GitHub yet** — blocked on `gh auth login` completing (user was mid-authorization when this handoff was written).
- **Documentation commit not yet created** — all `docs/*.md`, `README.md`, and `CLAUDE.md` were written to a local scratchpad path on the Mac (`/private/tmp/claude-501/.../scratchpad/`) and need to be `scp`'d to the VPS repo and committed. See "Next steps" below for exact commands.
- Full endpoint-by-endpoint permission audit (only GPS/chat/tools/critical-alerts routes were spot-checked; ~93 routes total — see `docs/TODO.md` REC-3).
- Branch rename `master` → `main` (docs reference `main` as convention; repo is actually on `master` — reconcile one way or the other, see `docs/PROJECT_STATE.md` note).
- GitHub PR/issue templates, CODEOWNERS (needs the owner's actual GitHub username, not yet known).
- Deciding what to do with the stale Mac-local copy at `~/Projects/promonta/miniapp/frontend/` (left untouched, not deleted — see `docs/TODO.md` REC-2).

## Files changed/created this session (on the Mac, pending sync to VPS)

All under `/private/tmp/claude-501/-Users-mac/d60acb86-70ba-4b7e-99ef-2c71e59608e9/scratchpad/`:
`README.md`, `.env.example`, `requirements.txt`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/DEPLOYMENT.md`, `docs/ENVIRONMENT.md`, `docs/SECURITY.md`, `docs/TROUBLESHOOTING.md`, `docs/TESTING.md`, `docs/ROLES_AND_PERMISSIONS.md`, `docs/API.md`, `docs/FEATURES.md`, `docs/UI_UX.md`, `docs/DECISIONS.md`, `docs/CHANGELOG.md`, `docs/TODO.md`, `docs/PROJECT_STATE.md`, `docs/RELEASE_PROCESS.md`, this file. `CLAUDE.md` (governance) still pending as of this handoff.

## Next steps (exact commands)

```bash
# 1. finish GitHub auth if not done
gh auth status

# 2. copy all scratchpad docs to the VPS repo
scp -i ~/.ssh/promonta_hetzner -r /private/tmp/claude-501/-Users-mac/d60acb86-70ba-4b7e-99ef-2c71e59608e9/scratchpad/docs \
  /private/tmp/claude-501/-Users-mac/d60acb86-70ba-4b7e-99ef-2c71e59608e9/scratchpad/README.md \
  /private/tmp/claude-501/-Users-mac/d60acb86-70ba-4b7e-99ef-2c71e59608e9/scratchpad/CLAUDE.md \
  root@162.55.53.147:/home/promonta/agent/miniapp-repo/
scp -i ~/.ssh/promonta_hetzner /private/tmp/claude-501/-Users-mac/d60acb86-70ba-4b7e-99ef-2c71e59608e9/scratchpad/.env.example \
  root@162.55.53.147:/home/promonta/agent/miniapp-repo/backend/.env.example
scp -i ~/.ssh/promonta_hetzner /private/tmp/claude-501/-Users-mac/d60acb86-70ba-4b7e-99ef-2c71e59608e9/scratchpad/requirements.txt \
  root@162.55.53.147:/home/promonta/agent/miniapp-repo/backend/requirements.txt

# 3. commit on the VPS
ssh -i ~/.ssh/promonta_hetzner root@162.55.53.147 'cd /home/promonta/agent/miniapp-repo && \
  git add . && git commit -m "docs: rebuild project documentation from source"'

# 4. create private GitHub repo and push
ssh -i ~/.ssh/promonta_hetzner root@162.55.53.147 'cd /home/promonta/agent/miniapp-repo && \
  gh repo create promonta-miniapp --private --source=. --remote=origin && \
  git push -u origin master'
```

(`gh` needs to be installed and authenticated on whichever machine runs step 4 — check `gh --version` on the VPS first; if not present there, run step 4 from the Mac instead, after adding a `origin` remote pointing at a repo created via the Mac's `gh`.)

## Blocking questions for the user

None outstanding beyond completing GitHub auth (see above) — no destructive action, secret-in-history, or conflicting architectural choice was hit that needed a decision beyond what's already logged in `docs/DECISIONS.md` and `docs/TODO.md`.

## Warnings for whoever continues this

- Do not treat `~/Projects/promonta/miniapp/` (Mac-local) as current — it is 2-3 weeks stale versus the VPS.
- Do not edit `/var/www/miniapp/` or `/home/promonta/agent/miniapp/` directly on the VPS anymore without also syncing the change into `/home/promonta/agent/miniapp-repo/` and committing — that's the whole point of this recovery, and skipping it recreates the original problem.
- The `chroma-mcp` process leak (see above) may recur — if shell commands start failing with `ENOSPC` again, check `ps aux | grep chroma-mcp` count before assuming it's a miniapp-related disk issue.
