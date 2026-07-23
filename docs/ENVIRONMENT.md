# Environment variables

Loaded on the VPS from `/etc/systemd/system/promonta-miniapp.service`'s `EnvironmentFile=/etc/claude-agent.env` — a file shared with other Promonta agent services, **not** specific to this app, and **not** in this repo. See `backend/.env.example` for names only.

| Variable | Required | Used for | Where read | Redeploy needed to change? |
|---|---|---|---|---|
| `BOT_TOKEN` | Yes | Telegram WebApp `initData` HMAC validation, `sendMessage`/`sendDocument` Bot API calls | `main.py` (`os.environ['BOT_TOKEN']`, line ~22 — hard fails at import if missing) | Yes, service restart |
| `CLAUDE_BIN` | Yes for AI chat features | Path to Claude Code CLI binary, invoked as subprocess for AI chat/task-extraction | `main.py` | Yes |
| `GLM_KEY` | Optional | Fallback/alternative AI model (GLM) for chat features | `main.py` | Yes |
| `ALLOWED_CHAT` | No — not referenced anywhere in `main.py` (verified via grep). Belongs to another Promonta service (`bot.py`/`webhook.py`) sharing the same env file | N/A to this app | — | N/A to this app |
| `WEBHOOK_SECRET` | No — belongs to a *different* service (`promonta-webhook`, lead intake), listed here only because it's in the same shared env file | Lead webhook auth | Not used by miniapp `main.py` | N/A to this app |

## Who issues values

Owner (business owner, has Telegram/BotFather access and the VPS root credentials). `BOT_TOKEN` is issued once per bot via @BotFather and is long-lived unless manually rotated.

## Consequences of a missing variable

`BOT_TOKEN` missing → `main.py` fails at import time (`os.environ['BOT_TOKEN']` raises `KeyError`, no default) → `promonta-miniapp.service` fails to start → entire app down. This is the single point of failure to check first if the service won't start after an env file edit.

`CLAUDE_BIN`/`GLM_KEY` missing → AI chat/extraction features fail at call time, rest of the app unaffected — UNVERIFIED whether these fail gracefully (error toast) or throw a raw 500; worth checking next time that code path is touched.

## Local development

Verified: `main.py` does **not** call `load_dotenv()` (grepped, no match) despite `python-dotenv` being an installed dependency — it must be a transitive dependency of something else, or unused. A local `.env` file will **not** be picked up automatically; env vars must be exported into the shell/process environment directly (or `load_dotenv()` added, which would be a small, worthwhile local-dev improvement — see TODO.md).
