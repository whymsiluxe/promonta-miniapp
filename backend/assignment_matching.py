"""Подбор кандидатов для назначения на объект -- заменяет клиентский SKILL_STAGE_MAP
(bubble-assign.js), который покрывал только 8 из 19 навыков через keyword-substring
matching. Новая логика: assignment.work_type_id == profile.skills_v2[].skill_id,
точное совпадение id, работает одинаково для ВСЕХ навыков каталога.

Чистые функции без файлового I/O -- вызывающий код (main.py) сам загружает
профили/назначения/абсенсы и передаёт сюда, что упрощает тестирование (не нужно
мокать _load_*, только собрать входные dict/list) и переиспользование (GET
/api/assignment-candidates и Assignment Sheet используют одну и ту же логику)."""

# 01.08 (доп.раунд): та же проблема, что main.py/profile_skills.py -- relative import
# для package-import сценария (uvicorn miniapp.main:app), absolute fallback для
# top-level (тесты).
try:
    from .profile_skills import SKILL_LEVEL_RANK, normalize_profile_skills
except ImportError:
    from profile_skills import SKILL_LEVEL_RANK, normalize_profile_skills


def _dates_overlap(a_from: str, a_to: str, b_from: str, b_to: str) -> bool:
    if not (a_from and a_to and b_from and b_to):
        return False
    return a_from <= b_to and b_from <= a_to


def availability_for_worker(
    user_id: str, date_from: str, date_to: str, object_id: str,
    all_assignments: dict, abwesenheit_entries: list, checkin_sessions: list,
) -> tuple[str, str]:
    """Возвращает (availability, reason) для одного работника на период date_from..date_to.
    availability: 'available' | 'unavailable'.
    reason -- owner-safe строка (НЕ приватные детали абсенса -- см. спеку п.5:
    "не раскрывать другим Worker медицинские или приватные причины отсутствия",
    здесь та же осторожность применена для ЛЮБОГО потребителя этой функции, т.к.
    Assignment Sheet открыт только Owner, но причина не должна содержать note/reason
    текст абсенса -- только безопасное обозначение)."""
    uid = str(user_id)

    # approved-абсенс, пересекающийся с периодом
    for entry in abwesenheit_entries:
        if str(entry.get('user_id')) != uid:
            continue
        if entry.get('status') != 'approved':
            continue
        if _dates_overlap(date_from, date_to, entry.get('date_from', ''), entry.get('date_to', '')):
            return "unavailable", "Отсутствует"

    # пересекающееся accepted/pending назначение на ДРУГОМ объекте или другой work_type
    # на ЭТОМ объекте (тот же object_id + тот же work_type_id считается допустимым
    # дублем-кандидатом -- реальный duplicate-check делает batch endpoint отдельно)
    for oid, records in all_assignments.items():
        for a in records:
            if str(a.get('user_id')) != uid:
                continue
            status = a.get('status') or 'accepted'
            if status == 'declined':
                continue
            if not _dates_overlap(date_from, date_to, a.get('date_from', ''), a.get('date_to', '')):
                continue
            if oid != object_id:
                return "unavailable", "Назначен на другой объект"
            return "unavailable", "Уже назначен на этот период"

    # уже работает (открытая check-in сессия) на другом объекте сегодня -- актуально
    # только для периода, включающего сегодня.
    # 03.08 (ТЗ Задача 5): было datetime.date.today() -- UTC, расходится с business-day
    # Europe/Berlin вечером/ночью (тот же класс бага, что чинили в main.py, см.
    # business_today_str()). Модуль не импортирует main.py (избегаем циклического
    # импорта), поэтому Berlin-логика продублирована здесь напрямую через zoneinfo,
    # не через shared helper.
    import datetime
    from zoneinfo import ZoneInfo
    today = datetime.datetime.now(ZoneInfo('Europe/Berlin')).strftime('%Y-%m-%d')
    if date_from <= today <= date_to:
        for s in checkin_sessions:
            if str(s.get('user_id')) != uid:
                continue
            if s.get('finish_at') is not None:
                continue
            if s.get('object_id') != object_id:
                return "unavailable", "Назначен на другой объект"

    return "available", ""


def rank_candidate(skill_entry: dict | None) -> tuple:
    """Ключ сортировки -- порядок из спеки: verified master -> unverified master ->
    verified independent -> helper -> ... Значит level -- СТАРШИЙ разряд, verified --
    младший (иначе unverified master оказался бы ниже verified independent, что
    противоречит явно заданному порядку). Возвращает tuple для сортировки по
    убыванию значимости (используется с reverse=True)."""
    if skill_entry is None:
        return (0, 0, 0)
    verified_rank = 1 if skill_entry.get('verified') else 0
    level_rank = SKILL_LEVEL_RANK.get(skill_entry.get('level'), 0)
    return (1, level_rank, verified_rank)


def build_candidates(
    work_type_id: str, object_id: str, date_from: str, date_to: str,
    workers: list, all_assignments: dict, abwesenheit_entries: list, checkin_sessions: list,
) -> dict:
    """workers -- список dict {'user_id', 'name', 'has_avatar', 'profile'} (profile --
    сырой профиль работника, skills_v2 нормализуется здесь). Возвращает
    {'recommended': [...], 'available': [...], 'unavailable': [...]} -- каждый элемент
    в формате из спеки п.7 (user_id/name/has_avatar/skill_id/skill_level/
    skill_verified/availability/reason)."""
    recommended, available, unavailable = [], [], []

    for w in workers:
        uid = str(w['user_id'])
        skills_v2, _ = normalize_profile_skills(w.get('profile') or {})
        skill_entry = next((s for s in skills_v2 if s.get('skill_id') == work_type_id), None)

        avail, reason = availability_for_worker(
            uid, date_from, date_to, object_id, all_assignments, abwesenheit_entries, checkin_sessions,
        )

        candidate = {
            "user_id": uid,
            "name": w.get('name', uid),
            "has_avatar": bool(w.get('has_avatar')),
            "skill_id": skill_entry.get('skill_id') if skill_entry else None,
            "skill_level": skill_entry.get('level') if skill_entry else None,
            "skill_verified": bool(skill_entry.get('verified')) if skill_entry else False,
            "availability": avail,
            "reason": reason if avail == "unavailable" else "",
        }

        if avail == "unavailable":
            unavailable.append(candidate)
        elif skill_entry is not None:
            recommended.append(candidate)
        else:
            available.append(candidate)

    # verified master -> unverified master -> verified independent -> helper -> ...
    # затем стабильная сортировка по имени: сначала сортируем по имени (возрастание),
    # потом стабильно по рангу (убывание) -- Python sort стабилен, поэтому итоговый
    # порядок внутри одного ранга остаётся алфавитным.
    recommended.sort(key=lambda c: c["name"])
    recommended.sort(key=lambda c: rank_candidate({
        "verified": c["skill_verified"], "level": c["skill_level"],
    }), reverse=True)
    available.sort(key=lambda c: c["name"])
    unavailable.sort(key=lambda c: c["name"])

    return {"recommended": recommended, "available": available, "unavailable": unavailable}
