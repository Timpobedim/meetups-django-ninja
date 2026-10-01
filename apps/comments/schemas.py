from datetime import datetime

from ninja import Field, ModelSchema, Schema
from pydantic import field_validator

from apps.accounts.schemas import ProfileSchema
from apps.comments.models import Comment


class CommentOutSchema(ModelSchema):
    body: str = Field(alias="content")
    createdAt: datetime = Field(alias="created")
    updatedAt: datetime = Field(alias="updated")
    author: ProfileSchema

    class Meta:
        model = Comment
        fields = ["id"]


class CommentInSchema(Schema):
    body: str

    @field_validator("body")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("не может быть пустым")
        return value


class CommentContainerSchemaIn(Schema):
    comment: CommentInSchema
