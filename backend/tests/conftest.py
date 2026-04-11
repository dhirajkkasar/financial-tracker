import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
from fastapi.testclient import TestClient

SQLALCHEMY_TEST_URL = "sqlite:///:memory:"


class _ApiClient:
    """Thin wrapper around TestClient that prepends /api to every path.

    All integration tests were written against the old unprefixed routes.
    Rather than updating every test call site, we transparently add the
    prefix here so the tests continue to read as plain /assets, /members, etc.
    """

    def __init__(self, client: TestClient):
        self._c = client

    def _p(self, path: str) -> str:
        return f"/api{path}" if not path.startswith("/api") else path

    def get(self, path, **kw):
        return self._c.get(self._p(path), **kw)

    def post(self, path, **kw):
        return self._c.post(self._p(path), **kw)

    def put(self, path, **kw):
        return self._c.put(self._p(path), **kw)

    def patch(self, path, **kw):
        return self._c.patch(self._p(path), **kw)

    def delete(self, path, **kw):
        return self._c.delete(self._p(path), **kw)


@pytest.fixture(scope="function")
def db():
    engine = create_engine(
        SQLALCHEMY_TEST_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield _ApiClient(c)
    app.dependency_overrides.clear()
