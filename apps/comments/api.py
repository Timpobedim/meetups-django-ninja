from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef, QuerySet, Value
from django.http import HttpRequest, HttpResponse
from ninja import Router
from ninja.errors import AuthorizationError

from apps.comments.models import Comment
from apps.comments.schemas import CommentContainerSchemaIn, CommentOutSchema
from apps.events.models import Event
from helpers.exceptions import get_or_404
from helpers.jwt_utils import AuthedRequest, TokenAuth

User = get_user_model()
router = Router(tags=["Обсуждения"])


def _annotate_author_following(queryset: QuerySet[Comment], user: Any) -> QuerySet[Comment]:
    """Как в референсе: подписка на автора комментария считается аннотацией, а не запросом на запись."""
    if user.is_authenticated:
        return queryset.annotate(
            author_following=Exists(User.objects.filter(pk=OuterRef("author_id"), followers=user)),
        )
    return queryset.annotate(author_following=Value(False))


def _out(comment: Comment) -> dict[str, Any]:
    return CommentOutSchema.from_orm(comment).model_dump()


@router.get("/events/{slug}/comments", auth=TokenAuth(pass_even=True), response={200: Any, 404: Any})
def list_comments(request: HttpRequest, slug: str) -> dict[str, Any]:
    event = get_or_404(Event, "event", slug=slug)
    comments = _annotate_author_following(
        Comment.objects.filter(event=event).select_related("author"), request.user
    )

    result = []
    for comment in comments:
        comment.author.is_followed = comment.author_following  # type: ignore[attr-defined]
        result.append(_out(comment))
    return {"comments": result}


@router.post("/events/{slug}/comments", auth=TokenAuth(), response={201: Any, 404: Any})
def create_comment(
    request: AuthedRequest, slug: str, data: CommentContainerSchemaIn
) -> tuple[int, dict[str, Any]]:
    event = get_or_404(Event, "event", slug=slug)
    comment = Comment.objects.create(event=event, author=request.user, content=data.comment.body)
    comment.author.is_followed = False  # type: ignore[attr-defined]  # на себя не подписываются
    return 201, {"comment": _out(comment)}


@router.delete(
    "/events/{slug}/comments/{comment_id}", auth=TokenAuth(), response={204: None, 403: Any, 404: Any}
)
def delete_comment(request: AuthedRequest, slug: str, comment_id: int) -> HttpResponse:
    event = get_or_404(Event, "event", slug=slug)
    # Комментарий ищется в пределах мероприятия из URL: чужой id под другим slug даст 404.
    comment = get_or_404(Comment.objects.filter(event=event), "comment", id=comment_id)
    if comment.author_id != request.user.pk and event.organizer_id != request.user.pk:
        raise AuthorizationError
    comment.delete()
    return HttpResponse(status=204)
