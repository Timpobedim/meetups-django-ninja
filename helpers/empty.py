from typing import Final

from pydantic import BaseModel


class _Empty(BaseModel):
    """Маркер «поле не передано» — отличается от None, который означает «очистить значение».

    Приём из референса: экземпляр pydantic-модели не ломает генерацию openapi.json,
    потому что сериализуется через to_jsonable_python.
    """


EMPTY: Final = _Empty()
