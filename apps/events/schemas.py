from datetime import datetime
from typing import Any

from django.utils import timezone
from ninja import Field, ModelSchema, Schema
from pydantic import SerializeAsAny, field_validator

from apps.accounts.schemas import ProfileSchema
from apps.events.models import Event
from helpers.empty import EMPTY

MAX_TAGS = 10
MAX_TAG_LENGTH = 40


def normalize_tags(tags: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for tag in tags:
        name = tag.strip().lower()[:MAX_TAG_LENGTH]
        if name:
            seen.setdefault(name, None)
    if len(seen) > MAX_TAGS:
        raise ValueError(f"не больше {MAX_TAGS} тегов")
    return list(seen)


def ensure_future(value: datetime) -> datetime:
    if value <= timezone.now():
        raise ValueError("дата мероприятия должна быть в будущем")
    return value


class EventOutSchema(ModelSchema):
    description: str = Field(alias="summary")
    body: str = Field(alias="content")
    startsAt: datetime = Field(alias="starts_at")
    isOnline: bool = Field(alias="is_online")
    createdAt: datetime = Field(alias="created")
    updatedAt: datetime = Field(alias="updated")
    attending: bool
    attendeesCount: int
    seatsLeft: int | None
    organizer: ProfileSchema
    tagList: list[str]

    class Meta:
        model = Event
        fields = ["slug", "title", "city", "venue", "capacity"]

    @staticmethod
    def resolve_attending(obj: Event) -> bool:
        return bool(obj.is_attending)

    @staticmethod
    def resolve_attendeesCount(obj: Event) -> int:
        return int(obj.num_attendees)

    @staticmethod
    def resolve_seatsLeft(obj: Event) -> int | None:
        if obj.capacity is None:
            return None
        return max(obj.capacity - int(obj.num_attendees), 0)

    @staticmethod
    def resolve_tagList(obj: Event) -> list[str]:
        return sorted(tag.name for tag in obj.tags.all())


class EventListOutSchema(EventOutSchema):
    body: str = Field(alias="content", exclude=True)


class EventInCreateSchema(Schema):
    title: str
    summary: str = Field(alias="description")
    content: str = Field(alias="body")
    starts_at: datetime = Field(alias="startsAt")
    city: str = ""
    is_online: bool = Field(False, alias="isOnline")
    venue: str = ""
    capacity: int | None = Field(None, ge=1, le=100_000)
    # EMPTY — маркер «поле не передано»; pydantic не валидирует значение по умолчанию.
    tags: SerializeAsAny[list[str]] = Field(EMPTY, alias="tagList")  # ty: ignore[invalid-assignment]

    @field_validator("title", "summary", "content")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("не может быть пустым")
        return value

    @field_validator("starts_at")
    @classmethod
    def in_future(cls, value: datetime) -> datetime:
        return ensure_future(value)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: Any) -> Any:
        return normalize_tags(value) if isinstance(value, list) else value


class EventCreateSchema(Schema):
    event: EventInCreateSchema


class EventInPartialUpdateSchema(Schema):
    title: str | None = None
    summary: str | None = Field(None, alias="description")
    content: str | None = Field(None, alias="body")
    starts_at: datetime | None = Field(None, alias="startsAt")
    city: str | None = None
    is_online: bool | None = Field(None, alias="isOnline")
    venue: str | None = None
    capacity: int | None = Field(None, ge=1, le=100_000)
    # EMPTY — маркер «поле не передано»; pydantic не валидирует значение по умолчанию.
    tags: SerializeAsAny[list[str]] = Field(EMPTY, alias="tagList")  # ty: ignore[invalid-assignment]

    @field_validator("title", "summary", "content")
    @classmethod
    def non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("не может быть пустым")
        return value

    @field_validator("starts_at")
    @classmethod
    def in_future(cls, value: datetime | None) -> datetime | None:
        return ensure_future(value) if value is not None else None

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: Any) -> Any:
        return normalize_tags(value) if isinstance(value, list) else value


class EventPartialUpdateSchema(Schema):
    event: EventInPartialUpdateSchema
