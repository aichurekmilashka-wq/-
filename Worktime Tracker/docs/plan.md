# Worktime Tracker Implementation Plan

**Goal:** готовое локальное приложение с реальными ролями, расширением Chrome и проверками.
**Architecture:** Store отвечает за SQLite и интервалы, Auth — за пользователей и вход, Application — за HTTP и права. UI и расширение используют JSON API.
**Tech Stack:** Python 3.11+, SQLite, HTML/CSS/JS, Chrome Manifest V3, unittest.
**Spec:** [design.md](design.md).
**Execution:** в этой сессии, без дополнительных агентов, по инструкции пользователя.

## Global Constraints

- Только вымышленные данные; публикацию делает пользователь.
- Пароли, runtime-токены и БД не включаются в исходники и архив.
- Перезапуск не сбрасывает активную задачу; повторный старт не создаёт дубликат.
- Роли проверяются на сервере; даты отчётов UTC включительно.
- Нет зависимостей для Python и сборки интерфейса.

## Review Focus

Параллельные старты; доступ сотрудника к чужой задаче; повторная доставка активности;
сон/задержка опроса; переход через полночь и пустой отчёт.

## Task 1: Хранилище и интервалы

Files: worktime/store.py, tests/test_store.py.
Produces: Store.add_employee(name), start(employee_id, description), stop(session_id),
report(start, end, employee_id=None), record_activity(key, event).

- [x] Написать проверки жизненного цикла, пустого отчёта, конкуренции, полуночи, повторов и простоя.
- [x] `python3 -m unittest tests.test_store -q`: увидеть отсутствие реализации.
- [x] Реализовать SQLite и обрезание интервалов; тот же запуск — 21 успешная проверка.

## Task 2: Вход, роли и API

Files: worktime/auth.py, worktime/web.py, app.py, tests/test_web.py.
Consumes: Store. Produces: Application(store), Auth.add_user/login/resolve/logout.

- [x] Проверки: без входа 401; сотрудник не создаёт людей и не видит чужие отчёты; администратор создаёт сотрудника; выход отзывает cookie.
- [x] `python3 -m unittest tests.test_web -q`: зафиксировано отсутствие функциональности до реализации.
- [x] Реализованы PBKDF2, сессии в SQLite, маршруты и контроль Origin/Host/JSON.
- [x] Полный финальный прогон: 48 Python-тестов успешны.

## Task 3: Интерфейс и расширение

Files: static/index.html, static/app.js, static/style.css, extension/*, tests/extension.test.js.
Consumes: HTTP API. Produces: вход, сотрудники, таймер, отчёты; события активности расширения.

- [x] JS-проверки: фоновая вкладка, простой, сон, смена задачи, очистка URL.
- [x] До реализации зафиксировано отсутствие WorktimeCore.
- [x] Реализованы интерфейс и service worker с alarms, очередью и сохранением состояния.
- [x] 21 JS-проверка и синтаксис четырёх JS-файлов успешны.
- [x] По дополнительному запросу добавлены тема и исходники React/TypeScript/Tailwind/shadcn-интеграции.
- [ ] React-сборка: не выполнена из-за отсутствия Node.js и доступа к установке пакетов; инструкция в README, автоматический job в GitHub Actions.
- [ ] Проверка в браузере и установка расширения: ограничены средой; перечислены в verification.md.

## Task 4: Передача

Files: README.md, Start.command, .github/workflows/tests.yml, docs/verification.md.

- [x] Описаны запуск, роли, установка расширения, ограничения, инструменты ИИ и фактические исправления.
- [x] Отдельная проверка автором и полный набор тестов выполнены; дополнительных агентов пользователь запретил.
- [x] Подготовлена чистая передаваемая версия; состав папки и ZIP сверяется при упаковке, data/ и кэш исключены.
