from __future__ import annotations

from typing import Any, ClassVar

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email: str, password: str | None = None, **other_fields: Any) -> User:
        user = User(email=self.normalize_email(email).lower(), **other_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def create_superuser(self, email: str, password: str | None = None, **other_fields: Any) -> User:
        other_fields.setdefault("is_staff", True)
        other_fields.setdefault("is_superuser", True)
        other_fields.setdefault("is_active", True)

        if other_fields.get("is_staff") is not True:
            raise ValueError("Superuser must be assigned to is_staff=True.")
        if other_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must be assigned to is_superuser=True.")
        return self.create_user(email, password, **other_fields)


class User(AbstractUser):
    """Пользователь афиши: и организатор, и участник. Вход по email, как в референсе."""

    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]

    email = models.EmailField("Email", unique=True)
    username = models.CharField(max_length=60, unique=True)
    bio = models.TextField(blank=True)
    # В референсе было null=True; для строковых полей Django советует пустую строку вместо NULL,
    # а схема API и так превращает "" в null в ответе.
    image = models.URLField(blank=True, default="")

    followers = models.ManyToManyField("self", blank=True, symmetrical=False, related_name="following")

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects = UserManager()  # type: ignore[assignment]

    def get_full_name(self) -> str:
        return self.username

    def get_short_name(self) -> str:
        return self.username

    def is_following(self, other_user: User) -> bool:
        return other_user.followers.filter(pk=self.pk).exists() if self.is_authenticated else False
