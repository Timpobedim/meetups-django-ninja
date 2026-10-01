import dataclasses
import time
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest
from jwt_ninja import settings as jwt_settings_module
from jwt_ninja.auth_classes import AuthDetails, JWTAuth
from jwt_ninja.cryptography import generate_jwt
from jwt_ninja.errors import APIError
from jwt_ninja.models import Session

User = get_user_model()

ACCEPTED_PREFIXES = ("Token", "Bearer")


@dataclasses.dataclass
class AuthedRequest(HttpRequest):
    auth: AuthDetails


class TokenAuth(JWTAuth):
    """JWT-аутентификация jwtninja с двумя префиксами: «Token» (спецификация RealWorld) и «Bearer».

    pass_even=True — анонимный доступ разрешён: request.user становится AnonymousUser,
    и эндпоинт отвечает с точки зрения неавторизованного пользователя (как в референсе).
    """

    def __init__(self, *, pass_even: bool = False) -> None:
        self.pass_even = pass_even
        super().__init__()

    def __call__(self, request: HttpRequest) -> Any:
        prefix, _, token = request.headers.get("Authorization", "").partition(" ")
        if prefix not in ACCEPTED_PREFIXES or not token:
            return self._anonymous(request)

        try:
            auth_details = self.authenticate(request, token)
        except APIError:
            if self.pass_even:
                return self._anonymous(request)
            raise

        # jwtninja либо бросает APIError, либо возвращает AuthDetails, но сигнатура унаследована
        # от HttpBearer (AuthDetails | None). По контракту Ninja None — «не аутентифицирован».
        if auth_details is None:
            return self._anonymous(request)

        request.user = auth_details.user
        return auth_details

    def _anonymous(self, request: HttpRequest) -> Any:
        if not self.pass_even:
            return None
        request.user = AnonymousUser()
        return request.user


def bearer_token_from(request: HttpRequest) -> str:
    """Токен из заголовка текущего запроса — чтобы не выпускать новую сессию на каждый GET /user."""
    return request.headers.get("Authorization", "").partition(" ")[2]


def create_jwt_token(user: Any, request: HttpRequest | None = None) -> str:
    """Создаёт серверную сессию jwtninja и access-токен, привязанный к ней.

    Сессия хранит «отпечаток» пароля: после смены пароля все старые токены
    перестают приниматься — это даёт jwtninja из коробки.
    """
    config = jwt_settings_module.jwt_settings
    user_agent = request.headers.get("User-Agent", "") if request is not None else ""
    session = Session.create_session(user=user, ip_address=None, user_agent=user_agent)
    payload = config.payload_class(
        user_id=user.id,
        type="access",
        exp=int(time.time()) + config.ACCESS_TOKEN_EXPIRE_SECONDS,
        session_id=session.id,
    )
    return generate_jwt(payload)
