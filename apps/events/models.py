import uuid
from typing import Any, Self

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from slugify import slugify

SLUG_MAX_LENGTH = 255


class Tag(models.Model):
    name = models.CharField(max_length=40, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class EventQuerySet(models.QuerySet["Event"]):
    def with_attendance(self, user: Any) -> Self:
        """Число участников и флаги «я иду» / «я подписан на организатора» одним запросом.

        Идея из референса (with_favorites в articles): аннотации вместо запроса на каждую запись.
        Добавлен флаг подписки на организатора и distinct в Count — счётчик не искажается,
        когда список фильтруется по тем же участникам.
        """
        user_model = get_user_model()
        queryset = (
            self.select_related("organizer")
            .prefetch_related("tags")
            .annotate(
                num_attendees=models.Count("attendees", distinct=True),
            )
        )
        if not user.is_authenticated:
            false = models.Value(False, output_field=models.BooleanField())
            return queryset.annotate(is_attending=false, organizer_followed=false)

        return queryset.annotate(
            is_attending=models.Exists(
                user_model.objects.filter(pk=user.pk, attending_events=models.OuterRef("pk")),
            ),
            organizer_followed=models.Exists(
                user_model.objects.filter(pk=models.OuterRef("organizer_id"), followers=user),
            ),
        )


class EventManager(models.Manager["Event"]):
    """Менеджер объявлен явно, а не через Manager.from_queryset(): поведение то же,
    но методы набора видны проверке типов (ty + django-stubs без плагина mypy)."""

    def get_queryset(self) -> EventQuerySet:
        return EventQuerySet(self.model, using=self._db)

    def with_attendance(self, user: Any) -> EventQuerySet:
        return self.get_queryset().with_attendance(user)


class Event(models.Model):
    """IT-митап или конференция (аналог Article в референсе)."""

    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organized_events",
    )
    title = models.CharField(max_length=150)
    summary = models.TextField(blank=True)
    content = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    city = models.CharField(max_length=80, blank=True)
    is_online = models.BooleanField(default=False)
    venue = models.CharField(max_length=200, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    tags = models.ManyToManyField(Tag, blank=True)
    attendees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="attending_events")
    slug = models.SlugField(unique=True, max_length=SLUG_MAX_LENGTH)

    objects = EventManager()

    # Заполняются аннотациями EventQuerySet.with_attendance(). Объявлены только для проверки
    # типов: колонок в базе нет, у объекта без аннотаций этих атрибутов тоже нет.
    num_attendees: int
    is_attending: bool
    organizer_followed: bool

    class Meta:
        ordering = ["-created", "-id"]
        indexes = [models.Index(fields=["starts_at"])]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Как в референсе, slug следует за заголовком; кириллица транслитерируется.
        self.slug = slugify(self.title, max_length=SLUG_MAX_LENGTH - 9) or "event"
        if Event.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
            self.slug = f"{self.slug}-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)
