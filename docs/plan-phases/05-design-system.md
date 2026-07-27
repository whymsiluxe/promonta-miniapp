# Promonta Mini App — Audit Master Plan (Phase file)

PHASE D — Design tokens, typography, Home/Profile/Calendar/Bubble Assignment. Часть единого плана из 10 файлов в `docs/plan-phases/`. Источники: 6 owner ТЗ от 2026-07-27, слиты вручную по темам.
Порядок выполнения согласован: Security P0 (01-02) первым, затем Product flows (03-04), Telegram UI/Navigation (05), Design System (06), Chat Hub (07), Object Card (08), Radio (09), Architecture/Tests/Docs (10).
Каждый пункт верифицируется по реальному коду перед стартом, не по документации. Правила: маленькие коммиты, py_compile+node --check после блока, не ломать routes, не деплоить без разрешения, DSGVO вне скоупа, Bubble Assignment сохранить.

---

## PHASE D — Design System V2

Источники: ТЗ2 §14-18, §33-35.

Единый token system (не накладывать aliases поверх старого CSS):
```
--color-canvas: #F8F4EC;  --color-surface: #FFFDF8;  --color-surface-muted: #F0E9DD;  --color-surface-deep: #E8DFD0;
--color-text: #201D18;  --color-text-secondary: #696257;  --color-text-tertiary: #91897C;
--color-forest: #1E4B3A;  --color-forest-hover: #173B2E;  --color-forest-soft: #DCE7E1;
--color-brass: #A4814E;  --color-brass-soft: #EEE3CF;
--color-oxblood: #8F453E;  --color-oxblood-soft: #F0DEDB;
--color-border: #DED5C6;  --color-divider: #E8E0D4;
```
Семантика: forest=primary/active/success/selected, brass=premium detail/secondary/caution, oxblood=destructive/error/critical. Не использовать pure black, random blue, яркий оранжевый, множество похожих зелёных.

Типографика: единственный UI font Manrope (+ system fallback). Удалить Montserrat из функционального UI — **известный реальный факт**: `tokens.css` имеет `--font-heading: Manrope`, `--font-body: Montserrat` одновременно (найдено в предыдущей сессии, AUDIT_COVERAGE_MATRIX.md), но по SESSION_HANDOFF commit `871414a` это уже унифицировано — **проверить актуальное состояние перед повтором работы**, не задваивать. Scale: Page title 32/700, Large 28/700, Section 22-24/700, Card title 19-20/650-700, Body 16-17/450-500, Button 16-17/650, Secondary 14-15/450-500, Caption 12-13/500. Не мельче 16px для рабочего текста.

Spacing scale 4/8/12/16/20/24/32. Radius: controls 10-12, inputs/buttons 14, cards 16-18, sheets 22-24, chips/avatars 999. Максимум 3 shadow tokens (card/floating/pressed) — убрать множественные тени, neumorphism, hover translateY на мобильном.

Icons: единый SVG набор, одинаковый stroke, 20-24px, aria-label. Emoji — только как пользовательский контент, не системные иконки (radio/camera/CSV/tools/AI/settings/status/nav/primary actions).

### Home (owner + worker)
Проблемы: title под Telegram Close, разные дизайн-системы карточек, alert card случайная рамка, красная полоса неясного смысла, всё визуально одного приоритета, слабые иконки. Целевая иерархия: title → критические действия → сегодня → операционные показатели → последняя активность → второстепенные инструменты. Worker Home компактнее — без новостей/AI/бюджетов/статистики компании/настроек, фокус на: текущий объект, начать/завершить смену, мои задачи, важное сообщение, создать потребность, сообщить дефект, offline queue status.

### Profile
Header card (avatar/name/role/metadata, без огромного пустого пространства). Tabs: Мой профиль/Команда/Настройки, единый design system. Accordions свёрнуты по умолчанию (кроме секции с validation error). Objects — compact rows, не raw text dump. Team — avatar/name/role/status/object, remove через context menu с confirm. Settings — реальные (sounds/haptic/theme/radio/notifications). CSV export — secondary action, не огромная primary button.

### Calendar
Крупный title, заметный selector chip (owner: Все/worker; worker: свой), today vs selected различимы, отпуск/болезнь/обучение — цвет+icon+label (не только цвет), day tap → bottom sheet.

### Bubble Assignment — сохранить, не заменять таблицей
Проверить: hardcoded skills расходятся с profile data, unescaped stage names, inline onclick, drag конфликтует со swipe navigation, assignment conflicts/absences/overlapping dates, optimistic update+rollback+undo. Два режима: Просмотр (workers на объектах, unassigned отдельно, visible conflicts/absence) и Распределение (tap ИЛИ drag, global swipe отключён во время drag, haptic, conflict explained, Undo после изменения). Drag — не единственный способ (нужна tap-альтернатива).

---

