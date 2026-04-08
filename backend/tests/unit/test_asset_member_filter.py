import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.member import Member
from app.models.asset import Asset, AssetType, AssetClass
from app.repositories.asset_repo import AssetRepository


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
def setup_members(db_session):
    m1 = Member(pan="ABCDE1234F", name="Dhiraj", is_default=True)
    m2 = Member(pan="FGHIJ5678K", name="Spouse")
    db_session.add_all([m1, m2])
    db_session.flush()
    return m1, m2


def test_list_filters_by_member_ids(db_session, setup_members):
    m1, m2 = setup_members
    db_session.add(Asset(name="Stock A", asset_type=AssetType.STOCK_IN, asset_class=AssetClass.EQUITY, member_id=m1.id))
    db_session.add(Asset(name="Stock B", asset_type=AssetType.STOCK_IN, asset_class=AssetClass.EQUITY, member_id=m2.id))
    db_session.add(Asset(name="FD", asset_type=AssetType.FD, asset_class=AssetClass.DEBT, member_id=m1.id))
    db_session.flush()

    repo = AssetRepository(db_session)

    # Filter by m1 only
    assets = repo.list(member_ids=[m1.id])
    assert len(assets) == 2
    assert all(a.member_id == m1.id for a in assets)

    # Filter by m2 only
    assets = repo.list(member_ids=[m2.id])
    assert len(assets) == 1
    assert assets[0].name == "Stock B"

    # No filter = all members
    assets = repo.list()
    assert len(assets) == 3

    # Both members
    assets = repo.list(member_ids=[m1.id, m2.id])
    assert len(assets) == 3
