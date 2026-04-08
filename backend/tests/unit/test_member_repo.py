import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.repositories.member_repo import MemberRepository


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def repo(db_session):
    return MemberRepository(db_session)


def test_create_member(repo, db_session):
    member = repo.create(pan="ABCDE1234F", name="Dhiraj")
    db_session.flush()
    assert member.id is not None
    assert member.pan == "ABCDE1234F"
    assert member.name == "Dhiraj"
    assert member.is_default is False


def test_list_members(repo, db_session):
    repo.create(pan="ABCDE1234F", name="Dhiraj")
    repo.create(pan="FGHIJ5678K", name="Spouse")
    db_session.flush()
    members = repo.list_all()
    assert len(members) == 2
    assert members[0].pan == "ABCDE1234F"


def test_get_by_pan(repo, db_session):
    repo.create(pan="ABCDE1234F", name="Dhiraj")
    db_session.flush()
    found = repo.get_by_pan("ABCDE1234F")
    assert found is not None
    assert found.name == "Dhiraj"
    assert repo.get_by_pan("XXXXX0000X") is None


def test_get_default(repo, db_session):
    repo.create(pan="ABCDE1234F", name="Dhiraj", is_default=True)
    repo.create(pan="FGHIJ5678K", name="Spouse")
    db_session.flush()
    default = repo.get_default()
    assert default.pan == "ABCDE1234F"
