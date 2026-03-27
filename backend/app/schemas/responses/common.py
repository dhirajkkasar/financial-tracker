from typing import TypeVar, Generic, List
from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated wrapper returned by any list endpoint."""
    items: List[T]
    total: int
    page: int
    size: int
