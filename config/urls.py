from django.contrib import admin
from django.http import Http404, HttpRequest, HttpResponse
from django.urls import path
from jwt_ninja.errors import APIError
from jwt_ninja.handlers import error_handler as jwt_ninja_error_handler
from ninja import NinjaAPI
from ninja.errors import AuthorizationError, HttpError, ValidationError

from helpers.exceptions import ResourceNotFound

api = NinjaAPI(
    title="MeetupBoard API",
    version="1.0.0",
    description="Афиша IT-митапов: мероприятия, регистрация участников, обсуждения",
)


@api.exception_handler(ValidationError)
def validation_error_handler(request: HttpRequest, exc: ValidationError) -> HttpResponse:
    errors: dict[str, list[str]] = {}
    for error in exc.errors:
        loc = error.get("loc", [])
        field = str(loc[-1]) if loc else "unknown"
        msg = str(error.get("msg", ""))
        for prefix in ("Value error, ", "Assertion failed, "):
            msg = msg.removeprefix(prefix)
        errors.setdefault(field, []).append(msg)
    return api.create_response(request, {"errors": errors}, status=422)


def _resource_from_path(path: str) -> str:
    if "/comments/" in path:
        return "comment"
    if "/profiles/" in path:
        return "profile"
    if "/events/" in path:
        return "event"
    return "resource"


@api.exception_handler(Http404)
def not_found_handler(request: HttpRequest, exc: Http404) -> HttpResponse:
    resource = exc.resource if isinstance(exc, ResourceNotFound) else _resource_from_path(request.path)
    return api.create_response(request, {"errors": {resource: ["не найдено"]}}, status=404)


@api.exception_handler(AuthorizationError)
def authorization_error_handler(request: HttpRequest, exc: AuthorizationError) -> HttpResponse:
    resource = _resource_from_path(request.path)
    return api.create_response(request, {"errors": {resource: ["нет прав"]}}, status=403)


@api.exception_handler(HttpError)
def http_error_handler(request: HttpRequest, exc: HttpError) -> HttpResponse:
    if exc.status_code == 401:
        return api.create_response(request, {"errors": {"token": ["отсутствует"]}}, status=401)
    return api.create_response(request, {"errors": {"detail": [str(exc)]}}, status=exc.status_code)


@api.exception_handler(APIError)
def jwt_error_handler(request: HttpRequest, exc: APIError) -> HttpResponse:
    """Ошибки jwtninja. В 2.x APIError — не HttpError, и без обработчика неверный токен давал бы 500.

    Для собственных эндпоинтов jwtninja (/auth/…) сохраняем их документированный формат,
    для остального API — общий формат {"errors": {...}}.
    """
    if request.path.startswith("/auth/"):
        return jwt_ninja_error_handler(request, exc)

    response = api.create_response(
        request,
        {"errors": {"token": [exc.error_code]}},
        status=exc.http_status_code,
    )
    if exc.retry_after is not None:
        response["Retry-After"] = str(exc.retry_after)
    return response


api.add_router("/api", "apps.accounts.api.router")
api.add_router("/api", "apps.events.api.router")
api.add_router("/api", "apps.comments.api.router")
# Готовые эндпоинты jwtninja: вход с refresh-токеном, список активных сессий, выход со всех устройств.
api.add_router("/auth", "jwt_ninja.api.router")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", api.urls),
]
