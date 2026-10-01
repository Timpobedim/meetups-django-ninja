from django.conf import settings
from django.db import models

from apps.events.models import Event


class Comment(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments")
    content = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # Заполняется аннотацией в apps.comments.api; объявлено только для проверки типов.
    author_following: bool

    class Meta:
        ordering = ["-created", "-id"]

    def __str__(self) -> str:
        return str(self.content)[:50]
