import json
from datetime import timedelta
from typing import Any

from django.test import TestCase
from django.test.client import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.events.models import Event, Tag
from helpers.jwt_utils import create_jwt_token


class ApiTestCase(TestCase):
    """Базовый класс API-тестов: полный стек Django — маршрутизация, middleware, обработчики ошибок."""

    client: Client

    def call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        user: User | None = None,
        token: str | None = None,
        prefix: str = "Token",
    ) -> Any:
        headers: dict[str, str] = {}
        if user is not None:
            token = create_jwt_token(user)
        if token is not None:
            headers["Authorization"] = f"{prefix} {token}"
        payload = json.dumps(body) if body is not None else ""
        return self.client.generic(
            method, path, data=payload, content_type="application/json", headers=headers
        )

    @staticmethod
    def make_user(username: str, password: str = "password123") -> User:
        return User.objects.create_user(f"{username}@example.com", username=username, password=password)

    @staticmethod
    def make_event(organizer: User, title: str = "Python-митап", **fields: Any) -> Event:
        tags = fields.pop("tags", [])
        values: dict[str, Any] = {
            "summary": "Доклады про асинхронность",
            "content": "Программа вечера и регистрация",
            "starts_at": timezone.now() + timedelta(days=7),
        }
        values.update(fields)
        event = Event.objects.create(organizer=organizer, title=title, **values)
        event.tags.set([Tag.objects.get_or_create(name=name)[0] for name in tags])
        return event
