from __future__ import annotations

from typing import Annotated, Any

from ninja import ModelSchema, Schema
from pydantic import AfterValidator, EmailStr, field_validator

from apps.accounts.models import User
from helpers.empty import EMPTY, _Empty

MIN_PASSWORD_LENGTH = 8  # NIST 800-63B 5.1.1.2 — как в референсе


def none_to_blank(value: Any) -> Any:
    return "" if value is None else value


class ProfileSchema(ModelSchema):
    model_config = {"populate_by_name": True, "from_attributes": True}

    following: bool
    bio: str | None
    image: str | None

    class Meta:
        model = User
        fields = ["username"]

    @staticmethod
    def resolve_following(obj: Any, context: dict[str, Any] | None) -> bool:
        # Флаг мог быть посчитан аннотацией запроса — тогда обходимся без отдельного SQL.
        if hasattr(obj, "is_followed"):
            return bool(obj.is_followed)
        if isinstance(obj, ProfileSchema):
            return obj.following
        user = getattr(context.get("request") if context else None, "user", None)
        return obj.followers.filter(pk=user.pk).exists() if user and user.is_authenticated else False

    @field_validator("bio", "image", mode="before")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        return value or None


class ProfileOutSchema(Schema):
    profile: ProfileSchema


class UserInCreateSchema(Schema):
    email: EmailStr
    username: str
    password: str

    @field_validator("email", "username", "password", mode="before")
    @classmethod
    def non_empty(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("не может быть пустым")
        return value

    @field_validator("password")
    @classmethod
    def password_min_length(cls, value: str) -> str:
        # В референсе минимальная длина проверялась только при смене пароля, но не при регистрации.
        if len(value) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"не короче {MIN_PASSWORD_LENGTH} символов")
        return value


class UserCreateSchema(Schema):
    user: UserInCreateSchema


class UserInLoginSchema(Schema):
    email: str
    password: str

    @field_validator("email", "password")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("не может быть пустым")
        return value


class UserLoginSchema(Schema):
    user: UserInLoginSchema


class UserMineSchema(ModelSchema):
    email: EmailStr
    bio: str | None
    image: str | None
    token: str

    class Meta:
        model = User
        fields = ["email", "bio", "image", "username"]

    @field_validator("bio", "image", mode="before")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        return value or None

    @staticmethod
    def resolve_token(obj: User, context: dict[str, Any] | None) -> str:
        return str(context.get("token", "") if context is not None else "")


class UserInPartialUpdateInSchema(Schema):
    email: Annotated[EmailStr | _Empty | None, AfterValidator(none_to_blank)] = EMPTY
    bio: Annotated[str | _Empty | None, AfterValidator(none_to_blank)] = EMPTY
    image: Annotated[str | _Empty | None, AfterValidator(none_to_blank)] = EMPTY
    username: Annotated[str | _Empty | None, AfterValidator(none_to_blank)] = EMPTY
    password: Annotated[str | _Empty | None, AfterValidator(none_to_blank)] = EMPTY

    @field_validator("email", "username", "password", mode="after")
    @classmethod
    def non_empty(cls, value: object) -> object:
        if isinstance(value, str) and not value:
            raise ValueError("не может быть пустым")
        return value

    @field_validator("password", mode="after")
    @classmethod
    def password_min_length(cls, value: object) -> object:
        if isinstance(value, str) and 0 < len(value) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"не короче {MIN_PASSWORD_LENGTH} символов")
        return value


class UserPartialUpdateInSchema(Schema):
    user: UserInPartialUpdateInSchema
