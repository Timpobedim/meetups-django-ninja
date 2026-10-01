from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from ninja import Router
from ninja.errors import AuthorizationError, ValidationError

from apps.events.models import Event, EventQuerySet, Tag
from apps.events.schemas import (
    EventCreateSchema,
    EventListOutSchema,
    EventOutSchema,
    EventPartialUpdateSchema,
)
from helpers.empty import EMPTY
from helpers.exceptions import get_or_404
from helpers.jwt_utils import AuthedRequest, TokenAuth

User = get_user_model()
router = Router(tags=["Мероприятия"])

MAX_LIMIT = 100


def _events(request: HttpRequest) -> EventQuerySet:
    return Event.objects.with_attendance(request.user)


def _check_page(limit: int, offset: int) -> None:
    errors = []
    if not 1 <= limit <= MAX_LIMIT:
        errors.append({"loc": ["query", "limit"], "msg": f"от 1 до {MAX_LIMIT}", "type": "value_error"})
    if offset < 0:
        errors.append({"loc": ["query", "offset"], "msg": "не меньше 0", "type": "value_error"})
    if errors:
        raise ValidationError(errors)


def _out(event: Event, request: HttpRequest, *, full: bool = True) -> dict[str, Any]:
    # Флаг подписки на организатора уже посчитан аннотацией — передаём его в схему профиля.
    event.organizer.is_followed = event.organizer_followed  # type: ignore[attr-defined]
    schema = EventOutSchema if full else EventListOutSchema
    return schema.from_orm(event, context={"request": request}).model_dump()


def _page(queryset: EventQuerySet, request: HttpRequest, limit: int, offset: int) -> dict[str, Any]:
    events = list(queryset[offset : offset + limit])
    return {
        "events": [_out(event, request, full=False) for event in events],
        "eventsCount": queryset.count(),
    }


def _set_tags(event: Event, names: list[str]) -> None:
    event.tags.set([Tag.objects.get_or_create(name=name)[0] for name in names])


@router.post(
    "/events/{slug}/attend",
    auth=TokenAuth(),
    response={200: Any, 400: Any, 404: Any, 409: Any},
)
def attend(request: AuthedRequest, slug: str) -> Any:
    """Регистрация на мероприятие (аналог «избранного» в референсе) с проверкой мест.

    Строка мероприятия блокируется SELECT … FOR UPDATE: два участника не займут одно
    последнее место одновременно (в SQLite блокировок строк нет, но запись и так сериализована).
    """
    with transaction.atomic():
        event = get_or_404(Event.objects.select_for_update(), "event", slug=slug)
        if event.starts_at <= timezone.now():
            return 400, {"errors": {"event": ["мероприятие уже прошло"]}}
        if event.attendees.filter(pk=request.user.pk).exists():
            return 409, {"errors": {"event": ["вы уже зарегистрированы"]}}
        if event.capacity is not None and event.attendees.count() >= event.capacity:
            return 409, {"errors": {"event": ["свободных мест нет"]}}
        event.attendees.add(request.user)

    return {"event": _out(get_or_404(_events(request), "event", pk=event.pk), request)}


@router.delete("/events/{slug}/attend", auth=TokenAuth(), response={200: Any, 404: Any})
def unattend(request: AuthedRequest, slug: str) -> dict[str, Any]:
    event = get_or_404(Event, "event", slug=slug)
    get_or_404(event.attendees, "event", pk=request.user.pk)
    event.attendees.remove(request.user)
    return {"event": _out(get_or_404(_events(request), "event", pk=event.pk), request)}


@router.get("/events/feed", auth=TokenAuth(), response={200: Any})
def feed(request: AuthedRequest, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    _check_page(limit, offset)
    followed = User.objects.filter(followers=request.user)
    return _page(
        _events(request).filter(organizer__in=followed).order_by("-created", "-id"), request, limit, offset
    )


@router.get("/events", auth=TokenAuth(pass_even=True), response={200: Any})
def list_events(
    request: HttpRequest,
    tag: str | None = None,
    organizer: str | None = None,
    attendee: str | None = None,
    city: str | None = None,
    online: bool | None = None,
    upcoming: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    _check_page(limit, offset)
    queryset = _events(request)
    if tag:
        queryset = queryset.filter(tags__name=tag.strip().lower())
    if organizer:
        queryset = queryset.filter(organizer__username=organizer)
    if attendee:
        queryset = queryset.filter(attendees__username=attendee)
    if city:
        queryset = queryset.filter(city__icontains=city.strip())
    if online is not None:
        queryset = queryset.filter(is_online=online)
    if upcoming:
        # Для «ближайших» логичен порядок по дате начала, а не по дате публикации.
        queryset = queryset.filter(starts_at__gt=timezone.now()).order_by("starts_at", "id")
    else:
        queryset = queryset.order_by("-created", "-id")
    return _page(queryset, request, limit, offset)


@router.post("/events", auth=TokenAuth(), response={201: Any})
def create_event(request: AuthedRequest, data: EventCreateSchema) -> tuple[int, dict[str, Any]]:
    fields = data.event.model_dump(exclude={"tags"})
    with transaction.atomic():
        event = Event.objects.create(organizer=request.user, **fields)
        if data.event.tags is not EMPTY:
            _set_tags(event, data.event.tags)
    return 201, {"event": _out(get_or_404(_events(request), "event", pk=event.pk), request)}


@router.get("/events/{slug}", auth=TokenAuth(pass_even=True), response={200: Any, 404: Any})
def retrieve(request: HttpRequest, slug: str) -> dict[str, Any]:
    return {"event": _out(get_or_404(_events(request), "event", slug=slug), request)}


@router.delete("/events/{slug}", auth=TokenAuth(), response={204: None, 403: Any, 404: Any})
def destroy(request: AuthedRequest, slug: str) -> HttpResponse:
    event = get_or_404(Event, "event", slug=slug)
    if event.organizer_id != request.user.pk:
        raise AuthorizationError
    event.delete()
    return HttpResponse(status=204)


@router.put("/events/{slug}", auth=TokenAuth(), response={200: Any, 403: Any, 404: Any, 409: Any})
def update(request: AuthedRequest, slug: str, data: EventPartialUpdateSchema) -> Any:
    """Частичное обновление (как PUT в спецификации RealWorld). Только организатор."""
    event = get_or_404(Event, "event", slug=slug)
    if event.organizer_id != request.user.pk:
        raise AuthorizationError

    changes = data.event.model_dump(exclude_unset=True, exclude={"tags"})
    new_capacity = changes.get("capacity")
    if new_capacity is not None and new_capacity < event.attendees.count():
        return 409, {"errors": {"capacity": ["меньше числа уже зарегистрированных участников"]}}

    with transaction.atomic():
        for attr, value in changes.items():
            setattr(event, attr, value)
        event.save()
        if data.event.tags is not EMPTY:
            _set_tags(event, data.event.tags)

    return {"event": _out(get_or_404(_events(request), "event", pk=event.pk), request)}


@router.get("/tags", response={200: Any})
def list_tags(request: HttpRequest) -> dict[str, Any]:
    return {"tags": list(Tag.objects.values_list("name", flat=True))}
