from typing import Final

from pydantic import BaseModel


class _Empty(BaseModel):
    """Маркер «поле не передано» — отличается от None, который означает «очистить значение».

    Экземпляр pydantic-модели не ломает генерацию openapi.json,
    потому что сериализуется через to_jsonable_python.
    """


EMPTY: Final = _Empty()
