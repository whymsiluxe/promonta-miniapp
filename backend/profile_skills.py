"""skills_v2 -- структурированные навыки работника поверх backend/work_types.py.

Старые профили хранят навыки как список названий: profile['skills'] = ["Плитка", ...].
Новая структура:
    profile['skills_v2'] = [
        {"skill_id": "tile_work", "level": "independent", "verified": false},
        ...
    ]

Уровни: helper (Помощник) / independent (Самостоятельно) / master (Мастер).

Миграция идемпотентна: вызывать normalize_profile_skills() можно на каждый GET,
повторный вызов на уже мигрированном профиле не меняет результат и не пишет файл
без необходимости (см. main.py -- запись происходит только если что-то РЕАЛЬНО
изменилось, не на каждый read)."""

from work_types import get_work_type, legacy_skill_name_to_id, WORK_TYPES

SKILL_LEVELS = ("helper", "independent", "master")
SKILL_LEVEL_LABELS = {
    "helper": "Помощник",
    "independent": "Самостоятельно",
    "master": "Мастер",
}
# Для сортировки кандидатов при подборе -- master выше independent выше helper.
SKILL_LEVEL_RANK = {"master": 3, "independent": 2, "helper": 1}


def migrate_legacy_skills(legacy_names: list) -> list[dict]:
    """Список старых названий -> список skills_v2 записей. Неизвестное старое
    название НЕ теряется молча -- id остаётся исходной строкой (не резолвится в
    каталог), чтобы легаси-данные были видны и восстановимы вручную, а не исчезали.
    Новому легаси-навыку без уровня временно назначается independent, verified=False
    (ровно как в спеке)."""
    result = []
    seen = set()
    for name in legacy_names or []:
        skill_id = legacy_skill_name_to_id(name) or name
        if skill_id in seen:
            continue
        seen.add(skill_id)
        result.append({"skill_id": skill_id, "level": "independent", "verified": False})
    return result


def normalize_profile_skills(profile: dict) -> tuple[list[dict], bool]:
    """Возвращает (skills_v2, changed). changed=True означает, что profile нужно
    пересохранить (миграция legacy skills произошла впервые) -- вызывающий код сам
    решает, вызывать ли _save_worker_profiles (не переписывать файл при каждом GET,
    см. спеку п.2). Идемпотентно: если skills_v2 уже присутствует, возвращает его
    как есть без изменений, даже если legacy 'skills' тоже ещё лежит в профиле."""
    if 'skills_v2' in profile and isinstance(profile['skills_v2'], list):
        return profile['skills_v2'], False
    legacy = profile.get('skills') or []
    if not legacy:
        return [], False
    return migrate_legacy_skills(legacy), True


def legacy_skill_names_from_v2(skills_v2: list[dict]) -> list[str]:
    """skills_v2 -> список названий, для API, которое временно должно продолжать
    отдавать legacy-совместимый список строк старому frontend-коду (спека п.2:
    "API может временно возвращать legacy skills как список названий")."""
    names = []
    for s in skills_v2 or []:
        wt = get_work_type(s.get('skill_id', ''))
        names.append(wt['name'] if wt else s.get('skill_id', ''))
    return names


def skill_display_name(skill_id: str) -> str:
    wt = get_work_type(skill_id)
    return wt['name'] if wt else skill_id


def worker_has_skill(skills_v2: list[dict], work_type_id: str) -> dict | None:
    """Запись skills_v2 работника для конкретного work_type_id, или None.
    Основная логика matching: assignment.work_type_id == profile.skills_v2[].skill_id,
    точное совпадение id -- НЕ через keywords (те только для поиска, см. work_types.py)."""
    for s in skills_v2 or []:
        if s.get('skill_id') == work_type_id:
            return s
    return None


def set_worker_skill(skills_v2: list[dict], skill_id: str, level: str) -> list[dict]:
    """Добавляет или обновляет один навык work_type_id в списке skills_v2.
    Изменение уровня существующего навыка сбрасывает verified в False (спека п.4:
    "после изменения навыка поле verified должно сбрасываться в false, если навык
    или его уровень изменён") -- ВСЕГДА, даже если уровень тот же (простое и
    предсказуемое правило: любой self-service PATCH сбрасывает verified, снятие
    verified -- только отдельный owner-only endpoint)."""
    result = [s for s in skills_v2 if s.get('skill_id') != skill_id]
    result.append({"skill_id": skill_id, "level": level, "verified": False})
    return result


def remove_worker_skill(skills_v2: list[dict], skill_id: str) -> list[dict]:
    return [s for s in skills_v2 if s.get('skill_id') != skill_id]


def set_skill_verification(skills_v2: list[dict], skill_id: str, verified: bool) -> tuple[list[dict], bool]:
    """Owner-only: подтверждает/снимает подтверждение конкретного навыка. Возвращает
    (skills_v2, found) -- found=False если у работника нет такого навыка вообще
    (вызывающий код возвращает 404)."""
    found = False
    result = []
    for s in skills_v2:
        if s.get('skill_id') == skill_id:
            found = True
            result.append({**s, "verified": verified})
        else:
            result.append(s)
    return result, found
