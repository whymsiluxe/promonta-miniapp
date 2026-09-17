# Data Retention Policy — Draft (2026-09-17)

Inventory-based draft, written against the actual data stores in
`backend/core/paths.py` (not a generic template). This is a first proposal
for owner review, not a legal document and not yet enforced by code.

## Personal / business data categories currently stored

| Category | Path(s) | What it is |
|---|---|---|
| GPS check-in data | `checkin_meta.json` | lat/lon/accuracy/timestamp at shift start/finish |
| Check-in photos | `checkin_photos/` | evidence photos required at shift finish (P2 min. 2) |
| Voice/transcription audio | `transcribe_audio/` | recorded voice notes + their transcripts |
| Chat messages (active) | `chat_messages.json` | live chat, all categories (general/DM/object/task) |
| Chat messages (archive) | `chat_messages_archive.json` | deleted/archived threads (see chat delete semantics) |
| Chat attachments | `chat_attachments/` | files/photos sent in chat |
| Avatars | `avatars/` | worker profile photos |
| Absence records | `abwesenheit.json` | sick leave / vacation requests + approval history |
| Audit log | `audit.log` | append-only actor/action/timestamp log (see Phase 8 audit-actor fix) |
| Critical alert photos | `critical_alert_photos/` | evidence photos attached to critical/safety alerts |
| Object photos/documents | `object_photos/`, `object_documents/` | site photos, uploaded contracts/plans |
| Feed photos | `feed_photos/` | photo-tab posts (also reused by мангель/defects, see `MANGEL_PHOTO_DIR` comment) |
| Blocker photos | `blocker_photos/` | evidence attached to stage blockers |
| Backups | `/tmp/rollback_backup_*` (deploy-time) | pre-deploy snapshots, currently untended in /tmp |

## Proposed retention periods (first draft — needs owner sign-off)

| Category | Proposed period | Rationale |
|---|---|---|
| Audit log | 1 year, then archive/compress | Compliance/dispute trail; low storage cost (text log) |
| Voice/transcription audio | 90 days | Transcript text is the durable record; raw audio only needed for short-term dispute resolution |
| Check-in GPS/photos | 1 year | Matches typical construction-project audit trail length; ties to contract/warranty disputes |
| Chat messages (active) | Indefinite while thread active | Working communication, no clear cutoff while object is live |
| Chat archive (deleted threads) | 180 days after archival, then purge | Deleted-by-user should not live forever, but a short grace window helps accidental-delete recovery |
| Critical alert photos | 2 years | Safety-incident evidence — longer than general checkin photos |
| Object photos/documents | Indefinite while object active; review at object completion + 1 year | These are the actual project record (contracts, as-built documentation) |
| Avatars | Until profile deleted/replaced | Trivial storage, no retention benefit to purging |
| Deploy backups (`/tmp/rollback_backup_*`) | 7 days, then delete | Currently accumulate unbounded in /tmp — real disk-growth risk, no business value past the next deploy cycle |

## What this draft deliberately does NOT do yet

- No automatic cleanup job is implemented. Implementing deletion against
  live, cross-referenced JSON stores (e.g. a chat message referenced by an
  object's history, a checkin photo referenced by a DailyPlan execution
  record) needs its own safety pass — a naive time-based delete could break
  a live reference. This doc exists so that pass has a target to build
  against, not to trigger deletion itself.
- No legal/compliance review — periods above are engineering defaults for a
  ~10-person German construction company, not vetted against GDPR/BDSG
  requirements for construction-industry recordkeeping. Recommend an
  actual legal consult before enforcing deletion, particularly for GPS/audit
  data that may have statutory minimum retention rather than a maximum.
- Deploy backup cleanup (`/tmp/rollback_backup_*`) is the one item here that
  IS safe to automate immediately (no live references, no compliance
  question, pure disk hygiene) — flagged as a quick separate follow-up.

## Revoke/offboarding note (already existing behavior, documented here for completeness)

Revoking a worker's role (removing from `roles.json`) removes app access
immediately but does NOT delete their historical `object_assignments.json`
entries, `checkin_meta.json` records, or `audit.log` lines — this is
correct and intentional: historical work/audit records must survive
personnel changes. Only active-session/access data is affected by revoke.
