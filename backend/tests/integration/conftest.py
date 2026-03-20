import pytest
from tests.factories import make_asset


@pytest.fixture
def seeded_asset(client):
    resp = client.post("/assets", json=make_asset())
    assert resp.status_code == 201
    return resp.json()
