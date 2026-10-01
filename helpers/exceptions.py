from sqlite3 import IntegrityError as SQLiteIntegrityError
from typing import Any

from django.db.models import Model, QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404
from psycopg.errors import UniqueViolation


class ResourceNotFound(Http404):
    def __init__(self, resource: str) -> None:
        self.resource = resource
        super().__init__(f"{resource} not found")


def get_or_404(model_or_qs: Any, resource: str, **kwargs: Any) -> Any:
    """get_object_or_404 с именем ресурса для текста ошибки: {"errors": {"event": [...]}}."""
    try:
        return get_object_or_404(model_or_qs, **kwargs)
    except Http404:
        raise ResourceNotFound(resource) from None


def clean_integrity_error(error: Exception) -> str | None:
    """Имя поля из IntegrityError (psycopg 3 или sqlite3) для ответа 409.

    В референсе разбирался psycopg2; здесь — актуальный psycopg 3, формат DETAIL тот же:
    «Key (email)=(x) already exists.».
    """
    cause = error.__cause__
    try:
        if isinstance(cause, UniqueViolation):
            detail = cause.diag.message_detail or ""
            return detail.split("(", 1)[1].split(")", 1)[0]
        if isinstance(cause, SQLiteIntegrityError):
            return str(cause.args[0]).split(": ", 1)[1].split(".", 1)[1]
    except (IndexError, AttributeError):
        return None
    return None


__all__ = ["Model", "QuerySet", "ResourceNotFound", "clean_integrity_error", "get_or_404"]
