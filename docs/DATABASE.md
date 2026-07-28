# Data storage

There is no database. No ORM, no schema, no migrations. All persistence is flat JSON files on the VPS filesystem, under `/home/promonta/agent/miniapp/` — **not** in this repository (gitignored, contains personal data).

## Concurrency handling

Every JSON store is written through `_atomic_write_json(path, data)` (write to temp file, `os.replace()` for atomicity) guarded by a `threading.Lock` from a `_json_locks` dict keyed by path (`_lock_for(path)`). This was retrofitted in the 2026-07-15 audit after identifying that unprotected read-modify-write could corrupt a file mid-write and crash the whole backend on next start. Protects against races within one process; would need a real lock (file lock / DB) if the backend ever runs with multiple workers.

## Stores (as of 2026-07-23, sizes indicate current data volume — all tiny)

| File | Contents | Contains personal data? |
|---|---|---|
| `roles.json` | `{telegram_user_id: "owner"\|"worker"}` | Telegram user IDs |
| `worker_profiles.json` | skills, clothing sizes, birthday, onboarding quiz status | Yes — names/sizes/birthday |
| `object_assignments.json` | `{object_id: [{user_id, stage_id, assigned_at}]}` | Telegram user IDs |
| `abwesenheit.json` | absence/vacation entries: date range, status, partial-day times, approval state | Yes |
| `tasks.json` | task list, assignment, completion state | Telegram user IDs |
| `mangel_tickets.json` | defect tickets | Photos, descriptions |
| `checkin_meta.json` | shift check-in/out sessions: GPS, photos, summaries | Yes — GPS + photos, most sensitive store |
| `critical_alerts.json` | critical alerts with ack/resolve workflow | Photos, descriptions |
| `chat_messages.json` | chat messages (200-message cap, 7-day retention) | Yes — message content |
| `chat_reads.json` | per-thread read receipts, `{user_id: {thread_id: ts}}` | Telegram user IDs |
| `chat_thread_meta.json` | thread open/closed state (owner-set, global); since 2026-07-28 also `user_prefs: {user_id: {muted,pinned,archived}}` per thread, per-user (Phase 06 data layer, no frontend UI yet) | — |
| `chat_reactions.json` (2026-07-28) | flat list `[{message_id,user_id,reaction,created_at}]`, fixed reaction set `👍✅👀❗`, uniqueness per (message_id,user_id,reaction) | Telegram user IDs |
| `feed_photos.json` | news/photo feed posts | Photos |
| `news_reactions.json` / `news_reads.json` | feed engagement | Telegram user IDs |
| `notified_users.json` | `{user_id: notified_at_ts}`, 7-day TTL | Telegram user IDs |
| `birthday_alerts.json` | birthday reminder dedup state | — |
| `ai_model.json` / `ai_chat_rate.json` | AI feature config + rate limiting | — |

Directories (binary data, same personal-data caveat): `checkin_photos/`, `chat_attachments/`, `critical_alert_photos/`, `feed_photos/`, `avatars/`, `angebote/` (generated quote PDFs), `rechnungen/` (generated invoice PDFs).

Logs: `audit.log` (JSONL, POST/PATCH/DELETE only) with logrotate (`/etc/logrotate.d/promonta-miniapp`, weekly, 8 rotations, copytruncate).

## Backup

`/home/promonta/agent/backup.sh`, daily via systemd timer (`promonta-backup.service`). Tars the entire `agent/` directory (excludes `.venv`/`__pycache__`/`node_modules`) plus secrets (`/etc/claude-agent.env`) separately, keeps last 14 of each, symlinks `*_latest.tgz`. The Mac side pulls the latest archive into iCloud (per user's global backup convention). This is the only backup mechanism for the JSON data stores — there is no separate database backup because there is no database.

## If a real database is ever introduced

Not currently planned. If it becomes necessary (e.g. multi-tenant, higher concurrency, need for real transactions/relations), it should be scoped as its own migration project — see [TODO.md](TODO.md) P2/P3 — not bolted on incrementally. Do not add a database to a subset of features while others stay on JSON; that would create two sources of truth.
