"""MIME allowlists + magic-byte sniffers, plus simple enum/allowlist constants
— Phase A extraction from main.py.

The MIME allowlists and their sniff_*() functions are kept together (not split
across files) because they're a single cohesive unit -- each sniffer reads
exactly one allowlist dict defined right above it. Only dependency: the
optional `magic` library (python-magic). Local/dev environments do not always
have system libmagic installed, so import/use failures fall back to conservative
magic-byte checks for the formats Promonta explicitly allows.
"""
try:
    import magic as _magic
except ImportError:
    _magic = None

_ALLOWED_IMAGE_MIME_EXT = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/gif': 'gif',
}


def _fallback_detect_mime(raw: bytes) -> str | None:
    if raw.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if raw.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if len(raw) >= 12 and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return 'image/webp'
    if raw.startswith(b'%PDF-'):
        return 'application/pdf'
    if raw.startswith(b'OggS'):
        return 'audio/ogg'
    if raw.startswith(b'ID3') or (len(raw) >= 2 and raw[0] == 0xFF and (raw[1] & 0xE0) == 0xE0):
        return 'audio/mpeg'
    if len(raw) >= 12 and raw[:4] == b'RIFF' and raw[8:12] == b'WAVE':
        return 'audio/wav'
    if len(raw) >= 12 and raw[4:8] == b'ftyp':
        return 'audio/mp4'
    if raw.startswith(b'\x1a\x45\xdf\xa3'):
        return 'video/webm'
    return None


def _detect_mime(raw: bytes) -> str | None:
    if _magic is not None:
        try:
            detected = _magic.from_buffer(raw, mime=True)
            if detected and detected != 'application/octet-stream':
                return detected
        except Exception:
            pass
    return _fallback_detect_mime(raw)


def sniff_image(raw: bytes) -> str | None:
    """Content-Type из клиента (file.content_type) -- заголовок, который клиент
    присылает сам, ничего не проверяя по факту (spoofable: переименовать .exe в
    .jpg с Content-Type: image/jpeg проходило раньше без вопросов). Смотрит
    реальные magic bytes через libmagic, возвращает канонический MIME из
    allowlist или None, если это не один из 4 разрешённых форматов изображений
    -- вызывающий код решает как реагировать (обычно HTTPException 400)."""
    detected = _detect_mime(raw)
    return detected if detected in _ALLOWED_IMAGE_MIME_EXT else None


def sniff_image_or_pdf(raw: bytes) -> str | None:
    """Как sniff_image(), плюс PDF -- для endpoints, что принимают либо
    изображение, либо документ (object documents, AI attachments)."""
    detected = _detect_mime(raw)
    if detected in _ALLOWED_IMAGE_MIME_EXT or detected == 'application/pdf':
        return detected
    return None


# 30.07 (Release-аудит P0): chat-вложения/голосовые/transcribe раньше принимали
# ЛЮБОЙ файл без magic-byte проверки (только size limit) -- единственные upload
# endpoints без sniff_image()/sniff_image_or_pdf(), в отличие от avatar/object-photo/
# document/feed/mangel/blocker, которые уже так делали. Расширенный allowlist:
# изображения + PDF (вложение может быть и документом) + аудио (голосовые).
_ALLOWED_AUDIO_MIME_EXT = {
    'audio/ogg': 'ogg', 'application/ogg': 'ogg',
    'audio/webm': 'webm', 'video/webm': 'webm',  # webm audio-only контейнер иногда детектится как video/webm
    'audio/mpeg': 'mp3', 'audio/mp4': 'm4a', 'audio/x-m4a': 'm4a',
    'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/vnd.wave': 'wav',
}
_ALLOWED_CHAT_ATTACHMENT_MIME_EXT = {**_ALLOWED_IMAGE_MIME_EXT, 'application/pdf': 'pdf', **_ALLOWED_AUDIO_MIME_EXT}


def sniff_audio(raw: bytes) -> str | None:
    """Как sniff_image(), но для голосовых -- отдельная функция (не смешиваем
    allowlist изображений с аудио, вызывающий код явно говорит что ожидает)."""
    detected = _detect_mime(raw)
    return detected if detected in _ALLOWED_AUDIO_MIME_EXT else None


def sniff_chat_attachment(raw: bytes) -> tuple[str, str] | None:
    """Чат принимает и фото, и голосовые, и документы через один и тот же upload
    endpoint (/api/chat/messages/attachment) -- единая проверка на объединённый
    allowlist. Возвращает (mime, безопасное_расширение) или None, если формат не
    разрешён. Расширение ВСЕГДА берётся из этой таблицы (не из имени файла от
    клиента) -- закрывает как "любой файл проходит", так и path-traversal через
    непровалидированное имя/расширение (10.07 -- Release-аудит P0)."""
    detected = _detect_mime(raw)
    ext = _ALLOWED_CHAT_ATTACHMENT_MIME_EXT.get(detected)
    if ext is None:
        return None
    return detected, ext


_INVISIBLE_FILLER_CHARS = (
    'ᅟᅠㅤﾠ'  # Hangul choseong/jungseong filler + halfwidth filler —
                                 # популярный трюк для "невидимого" имени в Telegram
)


# ── Simple enum/allowlist constants ───────────────────────────────────────

BUDGET_FIELDS = ['Бюджет (EUR)', 'Потрачено (EUR)', 'потрачено в % от бюджета', '% бюджета', 'Потрачено %']
VALID_OBJECT_STATUSES = {'В работе', 'Пауза', 'Завершён'}
CHAT_REACTION_OPTIONS = ['👍', '✅', '👀', '❗']
THREAD_TYPE_BY_PREFIX = {'obj:': 'OBJECT', 'mangel:': 'DEFECT', 'task:': 'TASK'}
DEFAULT_THREAD_PREFS = {'muted': False, 'pinned': False, 'archived': False}
AI_MODELS = ('glm', 'sonnet', 'opus')
AI_MODEL_DEFAULT = 'glm'
_OWNER_AI_ENV_ALLOWLIST = ('PATH', 'HOME', 'ANTHROPIC_API_KEY', 'LANG', 'LC_ALL')
TASK_PRIORITIES = ('обычная', 'срочно')
TASK_CATEGORIES = ('materials', 'tool', 'ppe', 'access', 'other')
TASK_STATUSES = ('открыто', 'в работе', 'закрыто', 'принято', 'заказано', 'выдано', 'отклонено')
ABWESENHEIT_REASONS = ('Krankheit', 'Urlaub', 'Sonstiges')
ABWESENHEIT_PUBLIC_FIELDS = {'id', 'user_id', 'name', 'date_from', 'date_to', 'open_ended', 'status'}
_EMPTY_CONTRACT_STORE = {"contracts": {}}
