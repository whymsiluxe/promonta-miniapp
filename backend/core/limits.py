"""Numeric limits/TTLs/rate-limit tunables — Phase A extraction from main.py.

Pure constants, zero coupling to anything else in main.py. Scoped narrowly to
single-line numeric values (Phase A step 3, first pass) -- the more complex
multi-line allowlist/prompt constants (MIME allowlists tightly coupled to their
sniff_*() functions, AI system prompts) are left in main.py for a later,
more careful pass rather than rushed in the same step.
"""

INIT_DATA_MAX_AGE = 3600  # секунд — Telegram initData считается протухшим через час
SESSION_TOKEN_MAX_AGE = 12 * 3600  # 12 часов
NOTIFIED_USERS_TTL = 7 * 86400  # 7 дней — потом можно напомнить owner'у снова (10.29)
ONLINE_THRESHOLD_SECONDS = 5 * 60
AVATAR_MAX_BYTES = 4 * 1024 * 1024
OBJECT_PHOTO_MAX = 8  # разумный потолок для carousel, не безлимит
SHEETS_CACHE_TTL = 45  # секунд — list_objects/get_alerts дёргались синхронно на Google Sheets
ALERT_DISMISS_TTL = 24 * 3600
PHOTO_MAX_BYTES = 8 * 1024 * 1024  # 8 МБ
PHOTO_MAX_COUNT = 300  # старые фото (и файлы) обрезаются сверху этого лимита
PHOTO_MAX_FILES = 10  # разумный потолок на пост, не архитектурное ограничение
CHAT_MAX = 200
CHAT_RETENTION_SECONDS = 7 * 24 * 3600  # 7 дней — сообщения старше удаляются автоматически
TRANSCRIBE_MAX_BYTES = 8 * 1024 * 1024
AI_RATE_LIMIT = 20
AI_RATE_WINDOW = 3600
WORKER_AI_RATE_LIMIT = 15
AI_UPLOAD_MAX_BYTES = 8 * 1024 * 1024  # 8 МБ
CHECKIN_MAX_BYTES = 8 * 1024 * 1024
_IDEMPOTENCY_TTL = 600  # 10 минут
