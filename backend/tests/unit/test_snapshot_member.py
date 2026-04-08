import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.member import Member
from app.models.snapshot import PortfolioSnapshot
from app.repositories.snapshot_repo import SnapshotRepository
from datetime import date


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


def test_upsert_with_member_id(db_session):
    m = Member(pan="ABCDE1234F", name="Dhiraj", is_default=True)
    db_session.add(m)
    db_session.flush()

    repo = SnapshotRepository(db_session)
    snap = repo.upsert(date(2026, 4, 7), 1000000, '{"STOCK_IN": 500000}', member_id=m.id)
    db_session.flush()
    assert snap.member_id == m.id


def test_list_aggregated_by_member_ids(db_session):
    m1 = Member(pan="ABCDE1234F", name="Dhiraj", is_default=True)
    m2 = Member(pan="FGHIJ5678K", name="Spouse")
    db_session.add_all([m1, m2])
    db_session.flush()

    repo = SnapshotRepository(db_session)
    repo.upsert(date(2026, 4, 7), 1000000, '{}', member_id=m1.id)
    repo.upsert(date(2026, 4, 7), 500000, '{}', member_id=m2.id)
    db_session.flush()

    # Single member
    result = repo.list(member_ids=[m1.id])
    assert len(result) == 1
    assert result[0].total_value_paise == 1000000

    # All members — aggregated
    result = repo.list_aggregated(member_ids=[m1.id, m2.id])
    assert len(result) == 1
    assert result[0]["total_value_paise"] == 1500000
