from typing import Any

from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from ninja import Router
from ninja.errors import AuthorizationError

from apps.accounts.models import User
from apps.accounts.schemas import (
    EMPTY,
    ProfileSchema,
    UserCreateSchema,
    UserLoginSchema,
    UserMineSchema,
    UserPartialUpdateInSchema,
)
from helpers.exceptions import clean_integrity_error, get_or_404
from helpers.jwt_utils import AuthedRequest, TokenAuth, bearer_token_from, create_jwt_token

router = Router(tags=["Пользователи и профили"])

TAKEN = ["уже занято"]


def _user_out(user: User, token: str) -> dict[str, Any]:
    return {"user": UserMineSchema.from_orm(user, context={"token": token}).model_dump()}


def _profile_out(profile: User, request: HttpRequest) -> dict[str, Any]:
    return {"profile": ProfileSchema.from_orm(profile, context={"request": request}).model_dump()}


@router.post("/users", response={201: Any, 409: Any})
def account_registration(request: HttpRequest, data: UserCreateSchema) -> tuple[int, dict[str, Any]]:
    email = str(data.user.email).lower()
    # Email сравнивается без учёта регистра: иначе «Anna@Mail.ru» обходила бы уникальность.
    if User.objects.filter(email__iexact=email).exists():
        return 409, {"errors": {"email": TAKEN}}
    try:
        with transaction.atomic():
            user = User.objects.create_user(email, username=data.user.username, password=data.user.password)
    except IntegrityError as err:
        return 409, {"errors": {clean_integrity_error(err) or "unknown": TAKEN}}
    return 201, _user_out(user, create_jwt_token(user, request))


@router.post("/users/login", response={200: Any, 401: Any})
def account_login(request: HttpRequest, data: UserLoginSchema) -> Any:
    user = authenticate(request, email=data.user.email.lower(), password=data.user.password)
    # authenticate() объявлен как возвращающий AbstractBaseUser | None; isinstance сужает тип до User.
    if not isinstance(user, User):
        return 401, {"errors": {"credentials": ["неверный email или пароль"]}}
    return _user_out(user, create_jwt_token(user, request))


@router.get("/user", auth=TokenAuth(), response={200: Any})
def get_user(request: AuthedRequest) -> dict[str, Any]:
    # Референс выпускал новую сессию на каждый GET /user; при лимите активных сессий jwtninja
    # это со временем «выбивало» исходную. Здесь возвращается токен текущего запроса.
    return _user_out(request.auth.user, bearer_token_from(request))


@router.put("/user", auth=TokenAuth(), response={200: Any, 409: Any})
def put_user(request: AuthedRequest, data: UserPartialUpdateInSchema) -> Any:
    """По спецификации RealWorld PUT ведёт себя как PATCH: меняются только переданные поля."""
    user = request.auth.user
    changes = data.user
    if changes.email != EMPTY:
        changes.email = str(changes.email).lower()
        if User.objects.filter(email__iexact=changes.email).exclude(pk=user.pk).exists():
            return 409, {"errors": {"email": TAKEN}}

    for field in ("email", "bio", "image", "username"):
        value = getattr(changes, field)
        if value != EMPTY:
            setattr(user, field, value)

    password_changed = changes.password != EMPTY
    if password_changed:
        user.set_password(changes.password)

    try:
        with transaction.atomic():
            user.save()
    except IntegrityError as err:
        return 409, {"errors": {clean_integrity_error(err) or "unknown": TAKEN}}

    # После смены пароля старые сессии jwtninja недействительны — выдаём новый токен.
    token = create_jwt_token(user, request) if password_changed else bearer_token_from(request)
    return _user_out(user, token)


@router.get("/profiles/{username}", auth=TokenAuth(pass_even=True), response={200: Any, 404: Any})
def get_profile(request: HttpRequest, username: str) -> dict[str, Any]:
    return _profile_out(get_or_404(User, "profile", username=username), request)


@router.post(
    "/profiles/{username}/follow", auth=TokenAuth(), response={200: Any, 403: Any, 404: Any, 409: Any}
)
def follow_profile(request: AuthedRequest, username: str) -> Any:
    profile = get_or_404(User, "profile", username=username)
    if profile == request.user:
        raise AuthorizationError
    if profile.followers.filter(pk=request.user.pk).exists():
        return 409, {"errors": {"profile": ["вы уже подписаны"]}}
    profile.followers.add(request.user)
    return _profile_out(profile, request)


@router.delete(
    "/profiles/{username}/follow", auth=TokenAuth(), response={200: Any, 403: Any, 404: Any, 409: Any}
)
def unfollow_profile(request: AuthedRequest, username: str) -> Any:
    profile = get_or_404(User, "profile", username=username)
    if profile == request.user:
        raise AuthorizationError
    if not profile.followers.filter(pk=request.user.pk).exists():
        return 409, {"errors": {"profile": ["вы не подписаны"]}}
    profile.followers.remove(request.user)
    return _profile_out(profile, request)
