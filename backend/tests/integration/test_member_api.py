import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_member(client):
    resp = client.post("/members", json={"pan": "ABCDE1234F", "name": "Dhiraj"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["pan"] == "ABCDE1234F"
    assert data["name"] == "Dhiraj"
    assert "id" in data


def test_create_duplicate_pan(client):
    client.post("/members", json={"pan": "ABCDE1234F", "name": "Dhiraj"})
    resp = client.post("/members", json={"pan": "ABCDE1234F", "name": "Other"})
    assert resp.status_code == 409


def test_list_members(client):
    client.post("/members", json={"pan": "ABCDE1234F", "name": "Dhiraj"})
    client.post("/members", json={"pan": "FGHIJ5678K", "name": "Spouse"})
    resp = client.get("/members")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
