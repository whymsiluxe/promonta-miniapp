"""Worker profile primitives needed by routes/auth.py (/api/roles) -- kept
deliberately narrow, NOT a full profiles-domain extraction.

Scope: only _load_worker_profiles() and _sanitize_display_name(), the
minimal dependency closure /api/roles needs to stop depending on main.py.
_save_worker_profiles()/_get_worker_profile()/_is_meaningful_name() and the
rest of the profiles domain stay in main.py for a later, dedicated pass --
pulling them in now would turn "extract the roles router" into "extract the
whole profiles domain," which is a different, larger task.

_load_worker_profiles is patched by name in 12 test files
(`patch.object(backend, '_load_worker_profiles', ...)`), all of them testing
functions that still live in main.py and resolve _load_worker_profiles from
that module's own namespace -- same business_now()/_load_roles trap as
before. main.py re-exports this module's implementation under the same name
so those 12 files keep working unchanged; routes/auth.py imports directly
from here and any test targeting it patches core.profiles, not backend.
_sanitize_display_name is never patched by name in any test (grepped), so a
straight move is safe.
"""
import re
import unicodedata

try:
    from .paths import WORKER_PROFILES_FILE
    from .storage import _safe_load_json
    from .constants import _INVISIBLE_FILLER_CHARS
except ImportError:
    from paths import WORKER_PROFILES_FILE  # noqa: E402
    from storage import _safe_load_json  # noqa: E402
    from constants import _INVISIBLE_FILLER_CHARS  # noqa: E402


def _load_worker_profiles() -> dict:
    return _safe_load_json(WORKER_PROFILES_FILE, {})


def _sanitize_display_name(raw: str | None, fallback: str) -> str:
    """Telegram first_name может быть невидимыми символами (заполнители Hangul,
    zero-width, чистые пробелы) или бессмысленным набором ('X13') — сохранённым
    как есть при первой авторизации. На экране это выглядит как "битый"/нечитаемый
    паттерн, а не как проблема шрифта (баг 23.07: юзер видел "нечитаемый паттерн"
    в имени и "X13" вместо имени в подписи графика — оба места брали profile['name']
    без проверки на осмысленность).
    Hangul filler (U+3164 и родня) — валидная Unicode-буква категории Lo, поэтому
    обычный \\w её не отсеивает; сначала вычищаем known invisible-filler + все
    юникод-символы категории Cf (format, включает zero-width space/joiner и т.п.),
    и только потом проверяем, остался ли хоть один "буквенный" символ."""
    if not raw:
        return fallback
    stripped = raw.strip()
    if not stripped:
        return fallback
    visible = ''.join(
        ch for ch in stripped
        if ch not in _INVISIBLE_FILLER_CHARS and unicodedata.category(ch) != 'Cf'
    )
    # 18.09: collapse whitespace left behind where filler characters used to sit
    # (e.g. 'ᅠ ᅠ ᅠ ᅠ ᅠ ᅠ1' -> filler removed leaves '      1' -- a run of spaces,
    # not a real name) -- re.sub before the final strip so a leading/trailing
    # run collapses away too, not just internal ones.
    visible = re.sub(r'\s+', ' ', visible).strip()
    if not visible or not re.search(r'\w', visible, re.UNICODE):
        return fallback
    # Bug fixed 18.09: this used to `return stripped` (the ORIGINAL uncleaned
    # string) once visible passed the meaningfulness check above -- a mixed
    # name like 'ᅠ ᅠ ᅠ ᅠ ᅠ ᅠ1' has one real character (enough to pass the
    # check) but was then returned WITH all the filler characters still in it,
    # defeating the sanitization the function exists to do. Return the cleaned
    # string instead.
    return visible
