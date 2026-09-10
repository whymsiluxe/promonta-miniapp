"""JSON-store / directory file-path constants — Phase A extraction from main.py.

Self-contained: computes DATA_ROOT/BACKEND_DIR independently the same way
main.py does (env var + package-relative), rather than importing them from
main.py — avoids any circular-import risk since core.paths has zero main.py
coupling. No constant here is imported by any file outside main.py itself
(confirmed by repo-wide grep before this extraction: daily_plan_lib.py,
mangel_lib.py, objekte_lib.py, plan_sync.py, contract_ingest.py all
independently re-derive their own DATA_ROOT/paths rather than importing from
main.py — a deliberate existing convention, not something this extraction
changes).

BACKEND_DIR here is core/paths.py's own directory's parent (backend/), NOT
core/'s own directory — os.path.dirname must be applied twice to land on
backend/, matching what BACKEND_DIR means in main.py (R2 in the Phase A
dependency map: __file__-based BACKEND_DIR silently changes meaning if not
adjusted for the extra directory level).
"""
import os

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(_CORE_DIR)
DATA_ROOT = os.environ.get('MINIAPP_DATA_ROOT', '/home/promonta/agent/miniapp')

ROLES_FILE = os.path.join(DATA_ROOT, 'roles.json')
DAILY_PLAN_STORE_FILE = os.path.join(DATA_ROOT, 'daily_plan_store.json')
PLAN_SYNC_STATE_FILE = os.path.join(DATA_ROOT, 'plan_sync_state.json')
WORK_CALENDAR_FILE = os.path.join(DATA_ROOT, 'work_calendar.json')
FINISH_OUTBOX_FILE = os.path.join(DATA_ROOT, 'finish_outbox.json')
CONTRACT_INGEST_STATE_FILE = os.path.join(DATA_ROOT, 'contract_ingest_state.json')
AUDIT_FILE = os.path.join(DATA_ROOT, 'audit.log')
NOTIFIED_USERS_FILE = os.path.join(DATA_ROOT, 'notified_users.json')
APP_VERSION_FILE = os.path.join(BACKEND_DIR, 'VERSION')
WORKER_PROFILES_FILE = os.path.join(DATA_ROOT, 'worker_profiles.json')
AVATAR_DIR = os.path.join(DATA_ROOT, 'avatars')
OBJECT_ASSIGNMENTS_FILE = os.path.join(DATA_ROOT, 'object_assignments.json')
OBJECT_IMAGES_FILE = os.path.join(DATA_ROOT, 'object_images.json')
OBJECT_PHOTO_DIR = os.path.join(DATA_ROOT, 'object_photos')
ALERT_DISMISSALS_FILE = os.path.join(DATA_ROOT, 'alert_dismissals.json')
ANGEBOT_OUT_DIR = os.path.join(DATA_ROOT, 'angebote')
OBJECT_INFO_FILE = os.path.join(DATA_ROOT, 'object_info.json')
OBJECT_DOC_DIR = os.path.join(DATA_ROOT, 'object_documents')
RECHNUNG_OUT_DIR = os.path.join(DATA_ROOT, 'rechnungen')
WEATHER_REACTIONS_FILE = os.path.join(DATA_ROOT, 'weather_reactions.json')
NEWS_REACTIONS_FILE = os.path.join(DATA_ROOT, 'news_reactions.json')
NEWS_READS_FILE = os.path.join(DATA_ROOT, 'news_reads.json')
BIRTHDAY_ALERTS_FILE = os.path.join(DATA_ROOT, 'birthday_alerts.json')
NEWS_COMMENTS_FILE = os.path.join(DATA_ROOT, 'news_comments.json')
FEED_READS_FILE = os.path.join(DATA_ROOT, 'feed_reads.json')
PHOTO_DIR = os.path.join(DATA_ROOT, 'feed_photos')
PHOTO_META_FILE = os.path.join(DATA_ROOT, 'feed_photos.json')
ACTIVITY_ALERTS_FILE = os.path.join(DATA_ROOT, 'activity_alerts.json')
CHAT_FILE = os.path.join(DATA_ROOT, 'chat_messages.json')
CHAT_ARCHIVE_FILE = os.path.join(DATA_ROOT, 'chat_messages_archive.json')
CHAT_READS_FILE = os.path.join(DATA_ROOT, 'chat_reads.json')
CHAT_THREAD_META_FILE = os.path.join(DATA_ROOT, 'chat_thread_meta.json')
CHAT_REACTIONS_FILE = os.path.join(DATA_ROOT, 'chat_reactions.json')
CHAT_ATTACH_DIR = os.path.join(DATA_ROOT, 'chat_attachments')
TRANSCRIBE_AUDIO_DIR = os.path.join(DATA_ROOT, 'transcribe_audio')
AI_RATE_FILE = os.path.join(DATA_ROOT, 'ai_chat_rate.json')
AI_MODEL_FILE = os.path.join(DATA_ROOT, 'ai_model.json')
WORKER_AI_RATE_FILE = os.path.join(DATA_ROOT, 'worker_ai_chat_rate.json')
BLOCKER_PHOTO_DIR = os.path.join(DATA_ROOT, 'blocker_photos')
TASKS_FILE = os.path.join(DATA_ROOT, 'tasks.json')
MANGEL_PHOTO_DIR = os.path.join(DATA_ROOT, 'feed_photos')  # переиспользуем feed_photos/
CHECKIN_PHOTO_BASE = os.path.join(DATA_ROOT, 'checkin_photos')
CHECKIN_META_FILE = os.path.join(DATA_ROOT, 'checkin_meta.json')
CRITICAL_ALERTS_FILE = os.path.join(DATA_ROOT, 'critical_alerts.json')
CRITICAL_ALERT_PHOTO_DIR = os.path.join(DATA_ROOT, 'critical_alert_photos')
ABWESENHEIT_FILE = os.path.join(DATA_ROOT, 'abwesenheit.json')
