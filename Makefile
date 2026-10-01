########################
# Variables

DEFAULT_API_URL := http://localhost:8000
HURL_DB := sqlite:///$(CURDIR)/.hurl.sqlite3

help:
	@echo "Available commands:"
	@echo "  sync                          установить зависимости"
	@echo "  run / migrate                 запустить сервер / применить миграции"
	@echo "  test                          тесты Django с покрытием"
	@echo "  test-fast                     тесты на SQLite в памяти, параллельно"
	@echo "  test-hurl                     Hurl-сценарии против запущенного сервера"
	@echo "  test-hurl-with-managed-server Hurl со временно поднятым сервером"
	@echo "  lint / lint-check             ruff"
	@echo "  type-check                    ty"
	@echo "  verify                        lint-check + type-check + test-fast"

########################
# Django Project

sync:
	uv sync --group dev

run:
	uv run python manage.py runserver 0.0.0.0:8000

migrate:
	uv run python manage.py migrate

test:
	USE_FAST_HASHER=True uv run coverage run manage.py test apps && uv run coverage report

test-fast:
	DATABASE_URL=sqlite:///:memory: USE_FAST_HASHER=True uv run python manage.py test apps --parallel

test-hurl:
	HOST=$(DEFAULT_API_URL) ./scripts/run-hurl.sh

test-hurl-with-managed-server:
	rm -f .hurl.sqlite3
	DATABASE_URL=$(HURL_DB) USE_FAST_HASHER=True uv run python manage.py migrate --verbosity 0
	DATABASE_URL=$(HURL_DB) USE_FAST_HASHER=True uv run python manage.py runserver 0.0.0.0:8000 --noreload & \
	SERVER_PID=$$!; \
	until curl -s $(DEFAULT_API_URL)/api/tags > /dev/null 2>&1; do sleep 0.3; done; \
	HOST=$(DEFAULT_API_URL) ./scripts/run-hurl.sh; \
	EXIT_CODE=$$?; \
	kill $$SERVER_PID; \
	rm -f .hurl.sqlite3; \
	exit $$EXIT_CODE

lint:
	uv run ruff check --fix . && uv run ruff format .

lint-check:
	uv run ruff check . && uv run ruff format --check .

type-check:
	uv run ty check

verify:
	$(MAKE) lint-check && $(MAKE) type-check && $(MAKE) test-fast

.PHONY: help sync run migrate test test-fast test-hurl test-hurl-with-managed-server lint lint-check type-check verify
