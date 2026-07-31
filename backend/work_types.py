"""Единый каталог видов работ — единственный источник истины для onboarding,
профиля работника, назначения на объект и подбора кандидатов. Раньше один и тот же
список из 19 навыков был вручную продублирован в backend/main.py (SKILL_OPTIONS) и
двух frontend-файлах (onboarding.js ONBOARDING_GROUPS, bubble-assign.js
BUBBLE_STAGE_OPTIONS) — рассинхронизация неизбежна, и уже была (SKILL_STAGE_MAP
покрывал только 8 из 19 навыков).

id каждого элемента — постоянный ключ, не зависит от отображаемого названия
(name можно менять свободно, id — никогда, старые назначения/профили ссылаются на id).
"""

WORK_TYPES: list[dict] = [
    # ---------- Подготовка и демонтаж ----------
    {
        "id": "demolition", "name": "Демонтаж",
        "group_id": "preparation_demolition", "group_name": "Подготовка и демонтаж",
        "featured": True, "sort_order": 70,
        "keywords": ["демонт", "abriss", "abbruch", "снос"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "old_covering_removal", "name": "Удаление старых покрытий",
        "group_id": "preparation_demolition", "group_name": "Подготовка и демонтаж",
        "featured": False, "sort_order": 71,
        "keywords": ["удаление покрыти", "старое покрытие", "belag entfernen"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "substrate_preparation", "name": "Подготовка основания",
        "group_id": "preparation_demolition", "group_name": "Подготовка и демонтаж",
        "featured": False, "sort_order": 72,
        "keywords": ["подготовка основания", "untergrund"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "sanding", "name": "Шлифование",
        "group_id": "preparation_demolition", "group_name": "Подготовка и демонтаж",
        "featured": False, "sort_order": 73,
        "keywords": ["шлифован", "schleifen", "sanding"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "priming", "name": "Грунтование",
        "group_id": "preparation_demolition", "group_name": "Подготовка и демонтаж",
        "featured": False, "sort_order": 74,
        "keywords": ["грунтован", "grundierung", "priming"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "construction_cleaning", "name": "Строительная уборка",
        "group_id": "preparation_demolition", "group_name": "Подготовка и демонтаж",
        "featured": False, "sort_order": 75,
        "keywords": ["уборка", "baureinigung", "cleaning"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "construction_waste_handling", "name": "Сортировка и вынос строительного мусора",
        "group_id": "preparation_demolition", "group_name": "Подготовка и демонтаж",
        "featured": False, "sort_order": 76,
        "keywords": ["мусор", "bauschutt", "waste"],
        "requires_qualification": False, "active": True,
    },

    # ---------- Штукатурка и малярные работы ----------
    {
        "id": "plastering", "name": "Штукатурные работы",
        "group_id": "plastering_painting", "group_name": "Штукатурка и малярные работы",
        "featured": True, "sort_order": 30,
        "keywords": ["штукатур", "stucco", "putz"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "filling_q1_q4", "name": "Шпаклевание Q1–Q4",
        "group_id": "plastering_painting", "group_name": "Штукатурка и малярные работы",
        "featured": False, "sort_order": 31,
        "keywords": ["шпакл", "spachtel", "q1", "q2", "q3", "q4"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "painting", "name": "Малярные работы",
        "group_id": "plastering_painting", "group_name": "Штукатурка и малярные работы",
        "featured": True, "sort_order": 20,
        "keywords": ["малярн", "maler", "краск", "покраск"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "wallpapering", "name": "Поклейка обоев",
        "group_id": "plastering_painting", "group_name": "Штукатурка и малярные работы",
        "featured": False, "sort_order": 32,
        "keywords": ["обои", "tapete", "wallpaper"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "decorative_plaster", "name": "Декоративная штукатурка",
        "group_id": "plastering_painting", "group_name": "Штукатурка и малярные работы",
        "featured": False, "sort_order": 33,
        "keywords": ["декоративная штукатурка", "dekorputz"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "acrylic_silicone", "name": "Акрил и силикон",
        "group_id": "plastering_painting", "group_name": "Штукатурка и малярные работы",
        "featured": False, "sort_order": 34,
        "keywords": ["акрил", "силикон", "silikon", "acryl"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "facade_painting", "name": "Фасадная покраска",
        "group_id": "plastering_painting", "group_name": "Штукатурка и малярные работы",
        "featured": False, "sort_order": 35,
        "keywords": ["малярные работы фасада", "фасадная покраска", "fassadenanstrich"],
        "requires_qualification": False, "active": True,
    },

    # ---------- Сухое строительство ----------
    {
        "id": "drywall", "name": "Гипсокартон",
        "group_id": "drywall_group", "group_name": "Сухое строительство",
        "featured": True, "sort_order": 40,
        "keywords": ["гипсокартон", "сухая стройка", "trockenbau", "drywall", "gipskarton"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "suspended_ceiling", "name": "Подвесные потолки",
        "group_id": "drywall_group", "group_name": "Сухое строительство",
        "featured": False, "sort_order": 41,
        "keywords": ["подвесной потолок", "abgehängte decke"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "fermacell_dry_floor", "name": "Fermacell и сухой пол",
        "group_id": "drywall_group", "group_name": "Сухое строительство",
        "featured": False, "sort_order": 42,
        "keywords": ["fermacell", "сухой пол", "trockenestrich"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "thermal_insulation", "name": "Теплоизоляция",
        "group_id": "drywall_group", "group_name": "Сухое строительство",
        "featured": False, "sort_order": 43,
        "keywords": ["утепление", "изоляция", "dämmung", "insulation"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "sound_insulation", "name": "Звукоизоляция",
        "group_id": "drywall_group", "group_name": "Сухое строительство",
        "featured": False, "sort_order": 44,
        "keywords": ["звукоизоляция", "schallschutz"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "partition_installation", "name": "Монтаж перегородок",
        "group_id": "drywall_group", "group_name": "Сухое строительство",
        "featured": False, "sort_order": 45,
        "keywords": ["перегородк", "trennwand"],
        "requires_qualification": False, "active": True,
    },

    # ---------- Плитка и напольные покрытия ----------
    {
        "id": "tile_work", "name": "Плиточные работы",
        "group_id": "tile_flooring", "group_name": "Плитка и напольные покрытия",
        "featured": True, "sort_order": 10,
        "keywords": ["плитка", "плиточные", "fliesen", "tile"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "waterproofing", "name": "Гидроизоляция",
        "group_id": "tile_flooring", "group_name": "Плитка и напольные покрытия",
        "featured": False, "sort_order": 11,
        "keywords": ["гидроизоляция", "abdichtung", "waterproofing"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "tile_substrate_preparation", "name": "Подготовка основания под плитку",
        "group_id": "tile_flooring", "group_name": "Плитка и напольные покрытия",
        "featured": False, "sort_order": 12,
        "keywords": ["подготовка под плитку"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "laminate_vinyl", "name": "Ламинат и винил",
        "group_id": "tile_flooring", "group_name": "Плитка и напольные покрытия",
        "featured": False, "sort_order": 13,
        "keywords": ["ламинат", "винил", "laminat", "vinyl"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "parquet_flooring", "name": "Паркет и другие напольные покрытия",
        "group_id": "tile_flooring", "group_name": "Плитка и напольные покрытия",
        "featured": False, "sort_order": 14,
        "keywords": ["паркет", "parkett"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "skirting_boards", "name": "Монтаж плинтусов",
        "group_id": "tile_flooring", "group_name": "Плитка и напольные покрытия",
        "featured": False, "sort_order": 15,
        "keywords": ["плинтус", "sockelleiste"],
        "requires_qualification": False, "active": True,
    },

    # ---------- Кладка и бетон ----------
    {
        "id": "masonry", "name": "Каменная кладка",
        "group_id": "masonry_concrete", "group_name": "Кладка и бетон",
        "featured": True, "sort_order": 50,
        "keywords": ["каменная кладка", "кладка", "mauerwerk", "masonry"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "screed_concrete", "name": "Стяжка и бетонные работы",
        "group_id": "masonry_concrete", "group_name": "Кладка и бетон",
        "featured": True, "sort_order": 60,
        "keywords": ["стяжка", "бетон", "estrich", "beton"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "concrete_repair", "name": "Ремонт бетонных оснований",
        "group_id": "masonry_concrete", "group_name": "Кладка и бетон",
        "featured": False, "sort_order": 61,
        "keywords": ["ремонт бетона", "betonsanierung"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "floor_pouring", "name": "Заливка полов",
        "group_id": "masonry_concrete", "group_name": "Кладка и бетон",
        "featured": False, "sort_order": 62,
        "keywords": ["заливка пола", "bodenverguss"],
        "requires_qualification": False, "active": True,
    },

    # ---------- Монтаж и сборка ----------
    {
        "id": "furniture_assembly", "name": "Сборка мебели",
        "group_id": "installation_assembly", "group_name": "Монтаж и сборка",
        "featured": False, "sort_order": 80,
        "keywords": ["сборка мебели", "möbelmontage", "furniture assembly"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "windows_doors_installation", "name": "Монтаж окон и дверей",
        "group_id": "installation_assembly", "group_name": "Монтаж и сборка",
        "featured": False, "sort_order": 81,
        "keywords": ["окна и двери", "fenster", "türen", "windows", "doors"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "carpentry", "name": "Столярные и плотницкие работы",
        "group_id": "installation_assembly", "group_name": "Монтаж и сборка",
        "featured": False, "sort_order": 82,
        "keywords": ["столярн", "плотницк", "zimmerei", "carpentry"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "prefabricated_installation", "name": "Монтаж готовых конструкций",
        "group_id": "installation_assembly", "group_name": "Монтаж и сборка",
        "featured": False, "sort_order": 83,
        "keywords": ["готовые конструкции", "fertigbau"],
        "requires_qualification": False, "active": True,
    },

    # ---------- Инженерные работы ----------
    {
        "id": "plumbing", "name": "Сантехника",
        "group_id": "engineering_works", "group_name": "Инженерные работы",
        "featured": False, "sort_order": 90,
        "keywords": ["сантех", "sanit", "труб", "plumbing"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "heating_ventilation", "name": "Отопление и вентиляция",
        "group_id": "engineering_works", "group_name": "Инженерные работы",
        "featured": False, "sort_order": 91,
        "keywords": ["отопление", "вентиляция", "heizung", "lüftung"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "electrical", "name": "Электрика",
        "group_id": "engineering_works", "group_name": "Инженерные работы",
        "featured": False, "sort_order": 92,
        "keywords": ["электр", "elektr", "electrical"],
        "requires_qualification": True, "active": True,
    },
    {
        "id": "welding", "name": "Сварочные работы",
        "group_id": "engineering_works", "group_name": "Инженерные работы",
        "featured": False, "sort_order": 93,
        "keywords": ["сварк", "schweiß", "welding"],
        "requires_qualification": False, "active": True,
    },

    # ---------- Фасад и наружные работы ----------
    {
        "id": "facade_wdvs", "name": "Фасад и WDVS",
        "group_id": "facade_exterior", "group_name": "Фасад и наружные работы",
        "featured": False, "sort_order": 100,
        "keywords": ["фасад", "fassade", "wdvs"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "exterior_insulation", "name": "Наружное утепление",
        "group_id": "facade_exterior", "group_name": "Фасад и наружные работы",
        "featured": False, "sort_order": 101,
        "keywords": ["наружное утепление", "außendämmung"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "roofing", "name": "Кровля",
        "group_id": "facade_exterior", "group_name": "Фасад и наружные работы",
        "featured": False, "sort_order": 102,
        "keywords": ["кровл", "dach", "roof"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "sheet_metal_gutters", "name": "Кровельная жесть и водостоки",
        "group_id": "facade_exterior", "group_name": "Фасад и наружные работы",
        "featured": False, "sort_order": 103,
        "keywords": ["кровельная жесть", "водосток", "dachrinne"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "scaffolding", "name": "Строительные леса",
        "group_id": "facade_exterior", "group_name": "Фасад и наружные работы",
        "featured": False, "sort_order": 104,
        "keywords": ["строительные леса", "gerüst", "scaffolding"],
        "requires_qualification": False, "active": True,
    },
    {
        "id": "landscaping", "name": "Благоустройство территории",
        "group_id": "facade_exterior", "group_name": "Фасад и наружные работы",
        "featured": False, "sort_order": 105,
        "keywords": ["ландшафт", "благоустройство", "landschaft"],
        "requires_qualification": False, "active": True,
    },
]

# Порядок и состав featured — точный список из спеки (7 элементов, в этом порядке).
FEATURED_ORDER = [
    "tile_work", "painting", "plastering", "drywall",
    "masonry", "screed_concrete", "demolition",
]

# Стабильный порядок групп — по первому появлению в WORK_TYPES выше (совпадает со
# спекой: Подготовка и демонтаж → Штукатурка и малярные → Сухое строительство →
# Плитка и напольные → Кладка и бетон → Монтаж и сборка → Инженерные → Фасад).
GROUP_ORDER = [
    "preparation_demolition", "plastering_painting", "drywall_group",
    "tile_flooring", "masonry_concrete", "installation_assembly",
    "engineering_works", "facade_exterior",
]

_BY_ID = {w["id"]: w for w in WORK_TYPES}

# Проверка целостности каталога при загрузке модуля — ловит опечатку в id/group
# сразу при импорте, не только в тестах.
assert len(_BY_ID) == len(WORK_TYPES), "WORK_TYPES: дублирующийся id"
assert set(FEATURED_ORDER) <= set(_BY_ID), "FEATURED_ORDER: неизвестный id"
assert len(FEATURED_ORDER) == 7, "FEATURED_ORDER: должно быть ровно 7 элементов"


def get_work_type(work_type_id: str) -> dict | None:
    """Один элемент каталога по id, или None если не найден/удалён из каталога.
    Не фильтрует по active -- вызывающий код решает сам (старые назначения на
    неактивный вид работ должны продолжать отображаться, просто не выбираться заново)."""
    return _BY_ID.get(work_type_id)


def get_work_type_name(work_type_id: str) -> str:
    """Отображаемое название по id -- то, что видит юзер (карточка задачи, чат,
    список назначений). Неизвестный id -- возвращает сам id (не должно происходить
    для новых данных, но легаси/повреждённые записи не должны падать 500-кой)."""
    wt = _BY_ID.get(work_type_id)
    return wt["name"] if wt else work_type_id


def work_types_catalog() -> dict:
    """Ответ GET /api/work-types -- featured (7 элементов в фиксированном порядке)
    + groups (стабильный порядок, только active-элементы, доступны для НОВОГО выбора).
    Неактивные элементы не отдаются сюда -- см. get_work_type()/get_work_type_name()
    для отображения уже существующих назначений/навыков на неактивный вид работ."""
    featured = [_BY_ID[wid] for wid in FEATURED_ORDER]
    groups = []
    for gid in GROUP_ORDER:
        items = [w for w in WORK_TYPES if w["group_id"] == gid and w["active"]]
        if not items:
            continue
        items.sort(key=lambda w: w["sort_order"])
        groups.append({"id": gid, "name": items[0]["group_name"], "items": items})
    return {"featured": featured, "groups": groups}


def search_work_types(query: str) -> list[dict]:
    """Поиск по name и keywords (регистронезависимо), только active. Используется
    строкой поиска в Assignment Sheet / редактировании навыков -- НЕ основной
    механизм matching (тот работает по точному skill_id, см. matching.py)."""
    q = (query or "").strip().lower()
    if not q:
        return []
    result = []
    for w in WORK_TYPES:
        if not w["active"]:
            continue
        if q in w["name"].lower() or any(q in kw.lower() for kw in w["keywords"]):
            result.append(w)
    result.sort(key=lambda w: w["sort_order"])
    return result


# ---------- Legacy skill-name → work_type_id миграция ----------
# Старые профили хранили навыки как список НАЗВАНИЙ (main.py SKILL_OPTIONS, те же
# строки что были в onboarding.js/bubble-assign.js до этой миграции). Минимальный
# mapping из спеки -- 20 старых названий на новые id.
LEGACY_SKILL_NAME_TO_ID: dict[str, str] = {
    "Штукатурка": "plastering",
    "Малярные работы": "painting",
    "Электрика": "electrical",
    "Кровля": "roofing",
    "Фасад": "facade_wdvs",
    "Сантехника": "plumbing",
    "Плитка": "tile_work",
    "Демонтаж": "demolition",
    "Гипсокартон (сухая стройка)": "drywall",
    "Стяжка пола / бетонные работы": "screed_concrete",
    "Утепление / изоляция": "thermal_insulation",
    "Каменная кладка": "masonry",
    "Столярные / плотницкие работы": "carpentry",
    "Сварочные работы": "welding",
    "Отопление / вентиляция": "heating_ventilation",
    "Ландшафт / благоустройство территории": "landscaping",
    "Малярные работы фасада": "facade_painting",
    "Монтаж окон и дверей": "windows_doors_installation",
    "Кровельная жесть / водостоки": "sheet_metal_gutters",
    "Строительные леса": "scaffolding",
}


def legacy_skill_name_to_id(name: str) -> str | None:
    """Известное старое название -> id нового каталога. None -- неизвестное имя
    (не должно молча теряться при миграции, см. profile_migration.py)."""
    return LEGACY_SKILL_NAME_TO_ID.get(name)
