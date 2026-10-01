# MeetupBoard

Афиша IT-митапов на Django Ninja: мероприятия, регистрация участников с лимитом мест,
обсуждения, подписки на организаторов. Переделка realworld-django-ninja под другую предметную область.

## Перед завершением задачи

Запусти `make verify` (ruff + ty + быстрые тесты) и исправь всё, что упало.
Если менялся контракт API — прогони `make test-hurl-with-managed-server`.

## Команды

- `make sync` — установить зависимости (uv)
- `make verify` — lint + типы + тесты
- `make test-fast` — только быстрые тесты (SQLite в памяти)
- `make test` — тесты с покрытием (порог 95 %)
- `make test-hurl-with-managed-server` — сквозные Hurl-сценарии из `tests/hurl/`

## Архитектура

- `config/urls.py` — единственный `NinjaAPI`, роутеры приложений под `/api`, роутер jwtninja под `/auth`,
  обработчики ошибок. Формат любой ошибки API: `{"errors": {"<поле или ресурс>": ["сообщение"]}}`.
- `apps/<app>/api.py` — роутер приложения; `schemas.py` — схемы Ninja/Pydantic; `models.py` — модели.
- `helpers/jwt_utils.py` — `TokenAuth` (префиксы `Token` и `Bearer`, `pass_even=True` для анонимов)
  и `create_jwt_token` (серверная сессия jwtninja).
- `helpers/exceptions.py` — `get_or_404(model_or_qs, "<ресурс>", **lookup)`: имя ресурса попадает в текст 404.
- `helpers/empty.py` — маркер `EMPTY` для частичных обновлений: «поле не передано» ≠ `None`.

## Соглашения

- Внешние имена полей — camelCase (`startsAt`, `tagList`), внутренние — snake_case; связь через `Field(alias=...)`.
- Списки строятся на `Event.objects.with_attendance(user)`: число участников и флаги считаются аннотациями.
  Не добавляй в схемы резолверы, которые делают запрос на каждую запись (тест `test_list_has_no_n_plus_one`).
- Изменения данных, которые проверяют ограничения (места на мероприятии), — в `transaction.atomic()`
  с `select_for_update()`.
- Тексты ошибок для пользователя — на русском; коды ошибок jwtninja (`invalid_token`) не переводим.
- Тесты — `apps/<app>/tests.py` на базе `helpers.testing.ApiTestCase` (полный стек Django),
  параметризация — `parameterized`.
