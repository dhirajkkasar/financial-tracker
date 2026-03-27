from app.schemas.responses.common import PaginatedResponse


def test_paginated_response_instantiation():
    r = PaginatedResponse[str](items=["a", "b"], total=10, page=1, size=2)
    assert r.items == ["a", "b"]
    assert r.total == 10
    assert r.page == 1
    assert r.size == 2


def test_paginated_response_empty():
    r = PaginatedResponse[int](items=[], total=0, page=1, size=20)
    assert r.items == []
    assert r.total == 0
