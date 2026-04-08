# Multi-Member Household Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `members` table (PAN-identified), link assets/important_data/snapshots to members, and thread `member_ids` filtering through all API/service/frontend layers so the app supports consolidated or per-person portfolio views.

**Architecture:** New `Member` model with `member_id` FK on `assets`, `important_data`, `portfolio_snapshots`. Repository `list()` methods gain optional `member_ids` filter. API endpoints accept `member_ids` (multi) or `member_id` (single, for tax). Frontend adds a global multi-select member dropdown; tax page uses its own single-select.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Alembic, Next.js (React), Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-04-07-multi-member-household-design.md`

---

## File Map

### New files (backend)
- `app/models/member.py` — Member SQLAlchemy model
- `app/repositories/member_repo.py` — MemberRepository
- `app/services/member_service.py` — MemberService (create, list)
- `app/schemas/member.py` — MemberCreate, MemberResponse Pydantic schemas
- `app/api/members.py` — GET/POST /members routes
- `alembic/versions/xxxx_add_members_table.py` — Alembic migration (auto-generated)
- `tests/unit/test_member_service.py` — Unit tests for member service
- `tests/integration/test_member_api.py` — Integration tests for member API

### New files (frontend)
- `frontend/contexts/MemberContext.tsx` — React context for member selection
- `frontend/components/ui/MemberSelector.tsx` — Multi-select dropdown component
- `frontend/hooks/useMembers.ts` — Data-fetching hook for GET /members

### Modified files (backend)
- `app/models/__init__.py` — Register Member model
- `app/models/asset.py` — Add `member_id` FK
- `app/models/important_data.py` — Add `member_id` FK
- `app/models/snapshot.py` — Add `member_id` FK
- `app/repositories/interfaces.py` — Update IAssetRepository, ISnapshotRepository protocols
- `app/repositories/asset_repo.py` — Add `member_ids` filter to `list()`, `get_by_identifier()`
- `app/repositories/important_data_repo.py` — Add `member_ids` filter to `list_all()`
- `app/repositories/snapshot_repo.py` — Add `member_ids` filter, `upsert()` gains `member_id`
- `app/repositories/unit_of_work.py` — Expose MemberRepository
- `app/api/dependencies.py` — Add `get_member_service()`, wire member repo into UoW
- `app/api/assets.py` — Add `member_ids` query param
- `app/api/returns.py` — Add `member_ids` query param to portfolio endpoints
- `app/api/tax.py` — Add required `member_id` query param
- `app/api/snapshots.py` — Add `member_ids` query param
- `app/api/imports.py` — Add required `member_id` query param
- `app/api/important_data.py` — Add `member_ids` query param
- `app/main.py` — Register members router
- `app/schemas/asset.py` — Add `member_id` to AssetCreate, AssetResponse
- `app/services/asset_service.py` — Thread `member_ids` through `list()`
- `app/services/returns/portfolio_returns_service.py` — Thread `member_ids` through all methods
- `app/services/tax_service.py` — Thread `member_id` through all methods
- `app/services/snapshot_service.py` — Per-member snapshots + aggregated listing
- `app/services/imports/orchestrator.py` — Thread `member_id` into `_find_or_create_asset()`
- `app/services/important_data_service.py` — Thread `member_ids` through listing
- `cli.py` — Add `add-member` command, `--pan` to imports, member_id resolution

### Modified files (frontend)
- `frontend/lib/api.ts` — Add `members` namespace, add `member_ids` params
- `frontend/hooks/useAssets.ts` — Accept and pass `member_ids`
- `frontend/hooks/useOverview.ts` — Accept and pass `member_ids`
- `frontend/hooks/useBreakdown.ts` — Accept and pass `member_ids`
- `frontend/hooks/useAllocation.ts` — Accept and pass `member_ids`
- `frontend/hooks/useGainers.ts` — Accept and pass `member_ids`
- `frontend/hooks/useSnapshots.ts` — Accept and pass `member_ids`
- `frontend/app/layout.tsx` — Wrap with MemberProvider
- `frontend/app/TabNavClient.tsx` — Add MemberSelector to header
- `frontend/app/tax/page.tsx` — Add independent single-select member picker
- `frontend/constants/index.ts` — Add Member type

---

## Task 1: Member Model + Repository + Migration

**Files:**
- Create: `app/models/member.py`
- Create: `app/repositories/member_repo.py`
- Modify: `app/models/__init__.py`
- Modify: `app/repositories/unit_of_work.py:21-47`
- Modify: `app/repositories/interfaces.py`
- Create: `tests/unit/test_member_repo.py`

- [x] **Step 1: Write failing test for MemberRepository**

```python
# tests/unit/test_member_repo.py
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_member_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.repositories.member_repo'`

- [x] **Step 3: Create Member model**

```python
# app/models/member.py
from datetime import datetime
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pan: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
```

- [x] **Step 4: Register Member model in `__init__.py`**

Add to `app/models/__init__.py`:
```python
from app.models.member import Member
```
And add `"Member"` to the `__all__` list.

- [x] **Step 5: Create MemberRepository**

```python
# app/repositories/member_repo.py
from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from app.models.member import Member


class MemberRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Member:
        member = Member(**kwargs)
        self.db.add(member)
        self.db.flush()
        self.db.refresh(member)
        return member

    def get_by_id(self, member_id: int) -> Optional[Member]:
        return self.db.query(Member).filter(Member.id == member_id).first()

    def get_by_pan(self, pan: str) -> Optional[Member]:
        return self.db.query(Member).filter(Member.pan == pan).first()

    def get_default(self) -> Optional[Member]:
        return self.db.query(Member).filter(Member.is_default == True).first()

    def list_all(self) -> list[Member]:
        return self.db.query(Member).order_by(Member.id).all()
```

- [x] **Step 6: Add IMemberRepository protocol to interfaces.py**

Add to `app/repositories/interfaces.py`:
```python
from app.models.member import Member

@runtime_checkable
class IMemberRepository(Protocol):
    def create(self, **kwargs) -> Member: ...
    def get_by_id(self, member_id: int) -> Optional[Member]: ...
    def get_by_pan(self, pan: str) -> Optional[Member]: ...
    def get_default(self) -> Optional[Member]: ...
    def list_all(self) -> list[Member]: ...
```

- [x] **Step 7: Add MemberRepository to UnitOfWork**

In `app/repositories/unit_of_work.py`, add import:
```python
from app.repositories.member_repo import MemberRepository
```
And in `UnitOfWork.__init__()`, add:
```python
self.members = MemberRepository(session)
```

- [x] **Step 8: Run tests**

Run: `uv run pytest tests/unit/test_member_repo.py -v`
Expected: All 4 tests PASS

- [x] **Step 9: Commit**

```bash
git add app/models/member.py app/repositories/member_repo.py app/repositories/interfaces.py app/repositories/unit_of_work.py app/models/__init__.py tests/unit/test_member_repo.py
git commit -m "feat: add Member model and MemberRepository"
```

---

## Task 2: Add `member_id` FK to Asset, ImportantData, Snapshot Models

**Files:**
- Modify: `app/models/asset.py:30-50`
- Modify: `app/models/important_data.py:17-27`
- Modify: `app/models/snapshot.py:7-14`

- [x] **Step 1: Add `member_id` FK to Asset model**

In `app/models/asset.py`, add import:
```python
from sqlalchemy import String, Boolean, Text, Enum as SAEnum, Integer, ForeignKey
```

Add field to `Asset` class (after `id`):
```python
member_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.id"), nullable=False, index=True)
```

- [x] **Step 2: Add `member_id` FK to ImportantData model**

In `app/models/important_data.py`, add import of `Integer, ForeignKey`:
```python
from sqlalchemy import String, Text, Enum as SAEnum, Integer, ForeignKey
```

Add field to `ImportantData` class (after `id`):
```python
member_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.id"), nullable=False, index=True)
```

- [x] **Step 3: Add `member_id` FK to PortfolioSnapshot model**

In `app/models/snapshot.py`, add import of `ForeignKey`:
```python
from sqlalchemy import Date, Integer, Text, ForeignKey
```

Add field to `PortfolioSnapshot` class (after `id`):
```python
member_id: Mapped[int] = mapped_column(Integer, ForeignKey("members.id"), nullable=False, index=True)
```

Remove `unique=True` from the `date` column (since multiple members can have snapshots on the same date). Add a unique constraint on `(member_id, date)` instead:
```python
from sqlalchemy import UniqueConstraint

# Inside the class:
date: Mapped[date] = mapped_column(Date, index=True, nullable=False)

__table_args__ = (
    UniqueConstraint("member_id", "date", name="uq_snapshot_member_date"),
)
```

- [x] **Step 4: Run existing tests to check nothing is broken structurally**

Run: `uv run pytest tests/unit/test_member_repo.py -v`
Expected: PASS (confirms models are valid)

- [x] **Step 5: Commit**

```bash
git add app/models/asset.py app/models/important_data.py app/models/snapshot.py
git commit -m "feat: add member_id FK to assets, important_data, portfolio_snapshots"
```

---

## Task 3: Alembic Migration with Data Backfill

**Files:**
- Create: `alembic/versions/xxxx_add_members_table.py` (auto-generated)

- [x] **Step 1: Generate migration**

Run: `cd /Users/dhirajkasar/Documents/workspace/financial-tracker/backend && uv run alembic revision --autogenerate -m "add members table and member_id FKs"`

- [x] **Step 2: Edit the generated migration to add data backfill**

The auto-generated migration will create the `members` table and add `member_id` columns. Edit it to:

1. Create the `members` table first
2. Add `member_id` columns as **nullable**
3. Insert default member from env vars and backfill
4. Make `member_id` NOT NULL

Replace the `upgrade()` function body with:

```python
import os
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    # 1. Create members table
    op.create_table(
        "members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pan", sa.String(10), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # 2. Add member_id columns (nullable initially)
    op.add_column("assets", sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=True))
    op.create_index("ix_assets_member_id", "assets", ["member_id"])

    op.add_column("important_data", sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=True))
    op.create_index("ix_important_data_member_id", "important_data", ["member_id"])

    op.add_column("portfolio_snapshots", sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id"), nullable=True))
    op.create_index("ix_portfolio_snapshots_member_id", "portfolio_snapshots", ["member_id"])

    # 3. Seed default member and backfill
    pan = os.environ.get("DEFAULT_MEMBER_PAN")
    name = os.environ.get("DEFAULT_MEMBER_NAME")
    if not pan or not name:
        raise RuntimeError(
            "Set DEFAULT_MEMBER_PAN and DEFAULT_MEMBER_NAME env vars before running this migration. "
            "Example: DEFAULT_MEMBER_PAN=ABCDE1234F DEFAULT_MEMBER_NAME=Dhiraj uv run alembic upgrade head"
        )

    conn = op.get_bind()
    conn.execute(
        sa.text("INSERT INTO members (pan, name, is_default) VALUES (:pan, :name, 1)"),
        {"pan": pan, "name": name},
    )
    result = conn.execute(sa.text("SELECT id FROM members WHERE pan = :pan"), {"pan": pan})
    default_id = result.scalar_one()

    conn.execute(sa.text("UPDATE assets SET member_id = :mid"), {"mid": default_id})
    conn.execute(sa.text("UPDATE important_data SET member_id = :mid"), {"mid": default_id})
    conn.execute(sa.text("UPDATE portfolio_snapshots SET member_id = :mid"), {"mid": default_id})

    # 4. Make NOT NULL (assets and important_data)
    with op.batch_alter_table("assets") as batch_op:
        batch_op.alter_column("member_id", nullable=False)
    with op.batch_alter_table("important_data") as batch_op:
        batch_op.alter_column("member_id", nullable=False)
    with op.batch_alter_table("portfolio_snapshots") as batch_op:
        batch_op.alter_column("member_id", nullable=False)

    # 5. Drop old unique constraint on snapshot date, add composite unique
    with op.batch_alter_table("portfolio_snapshots") as batch_op:
        batch_op.drop_constraint("uq_snapshot_member_date", type_="unique")  # may need to drop old ix first
    op.create_unique_constraint("uq_snapshot_member_date", "portfolio_snapshots", ["member_id", "date"])
```

Note: The exact `downgrade()` function should reverse all operations. For SQLite, `batch_alter_table` is needed for column alterations.

- [x] **Step 3: Run the migration**

Run: `DEFAULT_MEMBER_PAN=<your-pan> DEFAULT_MEMBER_NAME=<your-name> uv run alembic upgrade head`
Expected: Migration completes. All existing assets/important_data/snapshots now have `member_id` pointing to the default member.

- [x] **Step 4: Verify data**

Run: `uv run python -c "from app.database import SessionLocal; s = SessionLocal(); print(s.execute(__import__('sqlalchemy').text('SELECT COUNT(*) FROM members')).scalar())"`
Expected: `1`

- [x] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat: add Alembic migration for members table and member_id backfill"
```

---

## Task 4: Member Schema + Service + API

**Files:**
- Create: `app/schemas/member.py`
- Create: `app/services/member_service.py`
- Create: `app/api/members.py`
- Modify: `app/api/dependencies.py:107-108`
- Modify: `app/main.py`
- Create: `tests/integration/test_member_api.py`

- [x] **Step 1: Write failing integration test**

```python
# tests/integration/test_member_api.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_member_api.py -v`
Expected: FAIL — route not found (404)

- [x] **Step 3: Create Member Pydantic schemas**

```python
# app/schemas/member.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator
import re


class MemberCreate(BaseModel):
    pan: str
    name: str

    @field_validator("pan")
    @classmethod
    def validate_pan(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", v):
            raise ValueError("Invalid PAN format. Expected: ABCDE1234F")
        return v


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pan: str
    name: str
    is_default: bool
    created_at: datetime
```

- [x] **Step 4: Create MemberService**

```python
# app/services/member_service.py
from __future__ import annotations

from app.middleware.error_handler import ValidationError
from app.models.member import Member
from app.repositories.unit_of_work import IUnitOfWorkFactory


class MemberService:
    def __init__(self, uow_factory: IUnitOfWorkFactory):
        self._uow_factory = uow_factory

    def create(self, pan: str, name: str) -> Member:
        with self._uow_factory() as uow:
            existing = uow.members.get_by_pan(pan)
            if existing:
                raise ValidationError(f"Member with PAN {pan} already exists")
            return uow.members.create(pan=pan, name=name)

    def list_all(self) -> list[Member]:
        with self._uow_factory() as uow:
            return uow.members.list_all()
```

- [x] **Step 5: Create members API router**

```python
# app/api/members.py
from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_member_service
from app.middleware.error_handler import ValidationError
from app.schemas.member import MemberCreate, MemberResponse
from app.services.member_service import MemberService

router = APIRouter(prefix="/members", tags=["members"])


@router.get("", response_model=list[MemberResponse])
def list_members(service: MemberService = Depends(get_member_service)):
    return service.list_all()


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def create_member(body: MemberCreate, service: MemberService = Depends(get_member_service)):
    return service.create(pan=body.pan, name=body.name)
```

- [x] **Step 6: Add dependency factory and register router**

In `app/api/dependencies.py`, add:
```python
from app.services.member_service import MemberService

def get_member_service(db: Session = Depends(get_db)) -> MemberService:
    return MemberService(uow_factory=lambda: UnitOfWork(db))
```

In `app/main.py`, add:
```python
from app.api.members import router as members_router
app.include_router(members_router)
```

- [x] **Step 7: Handle duplicate PAN as 409**

Check how `ValidationError` is handled in the error middleware. If it doesn't map to 409, add a `ConflictError` or use an `HTTPException(status_code=409)` in the route. Adjust the `create_member` route:

```python
from fastapi import HTTPException

@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def create_member(body: MemberCreate, service: MemberService = Depends(get_member_service)):
    try:
        return service.create(pan=body.pan, name=body.name)
    except ValidationError:
        raise HTTPException(status_code=409, detail=f"Member with PAN {body.pan} already exists")
```

- [x] **Step 8: Run tests**

Run: `uv run pytest tests/integration/test_member_api.py -v`
Expected: All 3 tests PASS

- [x] **Step 9: Commit**

```bash
git add app/schemas/member.py app/services/member_service.py app/api/members.py app/api/dependencies.py app/main.py tests/integration/test_member_api.py
git commit -m "feat: add Member API with GET/POST /members endpoints"
```

---

## Task 5: Update Asset Schema + Repository + Service with `member_id`

**Files:**
- Modify: `app/schemas/asset.py:12-49`
- Modify: `app/repositories/asset_repo.py:27-40`
- Modify: `app/repositories/interfaces.py:24-32`
- Modify: `app/services/asset_service.py:19-30`
- Modify: `app/api/assets.py:12-27`
- Create: `tests/unit/test_asset_member_filter.py`

- [x] **Step 1: Write failing test for member_ids filtering**

```python
# tests/unit/test_asset_member_filter.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.member import Member
from app.models.asset import Asset, AssetType, AssetClass
from app.repositories.asset_repo import AssetRepository


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_asset_member_filter.py -v`
Expected: FAIL — `list() got an unexpected keyword argument 'member_ids'`

- [x] **Step 3: Update AssetRepository.list() to accept member_ids**

In `app/repositories/asset_repo.py`, modify `list()`:

```python
def list(
    self,
    asset_type: Optional[AssetType] = None,
    asset_class: Optional[AssetClass] = None,
    active: Optional[bool] = None,
    member_ids: Optional[list[int]] = None,
) -> list[Asset]:
    q = self.db.query(Asset)
    if member_ids is not None:
        q = q.filter(Asset.member_id.in_(member_ids))
    if asset_type is not None:
        q = q.filter(Asset.asset_type == asset_type)
    if asset_class is not None:
        q = q.filter(Asset.asset_class == asset_class)
    if active is not None:
        q = q.filter(Asset.is_active == active)
    return q.order_by(Asset.id).all()
```

- [x] **Step 4: Update IAssetRepository protocol**

In `app/repositories/interfaces.py`, update `IAssetRepository.list`:

```python
def list(
    self,
    asset_type: Optional[AssetType] = None,
    asset_class: Optional[AssetClass] = None,
    active: Optional[bool] = None,
    member_ids: Optional[list[int]] = None,
) -> list[Asset]: ...
```

- [x] **Step 5: Update AssetCreate and AssetResponse schemas**

In `app/schemas/asset.py`, add `member_id` to `AssetCreate`:
```python
class AssetCreate(BaseModel):
    name: str
    member_id: int
    identifier: Optional[str] = None
    # ... rest unchanged
```

Add `member_id` to `AssetResponse`:
```python
class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: int
    name: str
    # ... rest unchanged
```

- [x] **Step 6: Update AssetService.list() to accept member_ids**

In `app/services/asset_service.py`:

```python
def list(
    self,
    asset_type: Optional[AssetType] = None,
    asset_class: Optional[AssetClass] = None,
    active: Optional[bool] = None,
    member_ids: Optional[list[int]] = None,
) -> list[Asset]:
    with self._uow_factory() as uow:
        return uow.assets.list(asset_type=asset_type, asset_class=asset_class, active=active, member_ids=member_ids)
```

- [x] **Step 7: Update assets API route to accept member_ids**

In `app/api/assets.py`:

```python
@router.get("", response_model=list[AssetResponse])
def list_assets(
    type: Optional[AssetType] = Query(None),
    asset_class: Optional[AssetClass] = Query(None),
    active: Optional[bool] = Query(None),
    member_ids: Optional[str] = Query(None, description="Comma-separated member IDs"),
    service: AssetService = Depends(get_asset_service),
):
    parsed_member_ids = [int(x.strip()) for x in member_ids.split(",") if x.strip()] if member_ids else None
    return service.list(asset_type=type, asset_class=asset_class, active=active, member_ids=parsed_member_ids)
```

- [x] **Step 8: Run tests**

Run: `uv run pytest tests/unit/test_asset_member_filter.py -v`
Expected: All PASS

- [x] **Step 9: Commit**

```bash
git add app/schemas/asset.py app/repositories/asset_repo.py app/repositories/interfaces.py app/services/asset_service.py app/api/assets.py tests/unit/test_asset_member_filter.py
git commit -m "feat: add member_ids filtering to asset repository, service, and API"
```

---

## Task 6: Update PortfolioReturnsService with `member_ids` Filtering

**Files:**
- Modify: `app/services/returns/portfolio_returns_service.py:45-56, 125-200, 202-228, 229-263, 265-377`
- Modify: `app/api/returns.py:69-93`

- [x] **Step 1: Write failing test**

```python
# tests/unit/test_portfolio_returns_member_filter.py
import pytest
from unittest.mock import MagicMock, patch
from app.services.returns.portfolio_returns_service import PortfolioReturnsService


def test_get_breakdown_passes_member_ids():
    """Verify that member_ids is forwarded to uow.assets.list()."""
    db = MagicMock()
    registry = MagicMock()

    svc = PortfolioReturnsService(db, registry)

    # Patch UnitOfWork to capture the call
    with patch("app.services.returns.portfolio_returns_service.UnitOfWork") as MockUoW:
        mock_uow = MagicMock()
        mock_uow.assets.list.return_value = []
        MockUoW.return_value.__enter__ = MagicMock(return_value=mock_uow)
        MockUoW.return_value.__exit__ = MagicMock(return_value=False)

        svc.get_breakdown(member_ids=[1, 2])
        mock_uow.assets.list.assert_called_once_with(active=None, member_ids=[1, 2])
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_portfolio_returns_member_filter.py -v`
Expected: FAIL — `get_breakdown() got an unexpected keyword argument 'member_ids'`

- [x] **Step 3: Add `member_ids` parameter to all PortfolioReturnsService aggregation methods**

In `app/services/returns/portfolio_returns_service.py`, modify each method:

`get_breakdown`:
```python
def get_breakdown(self, member_ids: Optional[list[int]] = None) -> dict:
    # ... existing docstring ...
    with self._uow_factory() as uow:
        assets = uow.assets.list(active=None, member_ids=member_ids)
        # ... rest unchanged
```

`get_allocation`:
```python
def get_allocation(self, member_ids: Optional[list[int]] = None) -> dict:
    # ... existing docstring ...
    with self._uow_factory() as uow:
        assets = uow.assets.list(active=True, member_ids=member_ids)
        # ... rest unchanged
```

`get_gainers`:
```python
def get_gainers(self, n: int = 5, member_ids: Optional[list[int]] = None) -> dict:
    # ... existing docstring ...
    with self._uow_factory() as uow:
        assets = uow.assets.list(active=True, member_ids=member_ids)
        # ... rest unchanged
```

`get_overview`:
```python
def get_overview(self, asset_types: Optional[list[str]] = None, member_ids: Optional[list[int]] = None) -> dict:
    # ... existing docstring ...
    with self._uow_factory() as uow:
        assets = uow.assets.list(active=None, member_ids=member_ids)
        # ... rest unchanged
```

Add the import at the top:
```python
from typing import Optional
```
(Already imported — just ensure it's there.)

- [x] **Step 4: Update API routes to parse and forward member_ids**

In `app/api/returns.py`, create a helper and update endpoints:

```python
def _parse_member_ids(member_ids: Optional[str]) -> Optional[list[int]]:
    if not member_ids:
        return None
    return [int(x.strip()) for x in member_ids.split(",") if x.strip()]


@router.get("/returns/breakdown", response_model=BreakdownResponse)
def get_returns_breakdown(
    member_ids: Optional[str] = Query(None, description="Comma-separated member IDs"),
    svc: PortfolioReturnsService = Depends(get_portfolio_returns_service),
):
    return svc.get_breakdown(member_ids=_parse_member_ids(member_ids))


@router.get("/overview/allocation", response_model=AllocationResponse)
def get_overview_allocation(
    member_ids: Optional[str] = Query(None, description="Comma-separated member IDs"),
    svc: PortfolioReturnsService = Depends(get_portfolio_returns_service),
):
    return svc.get_allocation(member_ids=_parse_member_ids(member_ids))


@router.get("/overview/gainers", response_model=GainersResponse)
def get_overview_gainers(
    n: int = Query(5, ge=1, le=20, description="Number of top gainers/losers to return"),
    member_ids: Optional[str] = Query(None, description="Comma-separated member IDs"),
    svc: PortfolioReturnsService = Depends(get_portfolio_returns_service),
):
    return svc.get_gainers(n=n, member_ids=_parse_member_ids(member_ids))


@router.get("/returns/overview", response_model=OverviewReturnsResponse)
def get_returns_overview(
    types: Optional[str] = Query(None, description="Comma-separated asset types, e.g. STOCK_IN,MF"),
    member_ids: Optional[str] = Query(None, description="Comma-separated member IDs"),
    svc: PortfolioReturnsService = Depends(get_portfolio_returns_service),
):
    asset_types = [t.strip() for t in types.split(",")] if types else None
    return svc.get_overview(asset_types=asset_types, member_ids=_parse_member_ids(member_ids))
```

- [x] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_portfolio_returns_member_filter.py -v`
Expected: PASS

- [x] **Step 6: Run full test suite to check for regressions**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: No new failures

- [x] **Step 7: Commit**

```bash
git add app/services/returns/portfolio_returns_service.py app/api/returns.py tests/unit/test_portfolio_returns_member_filter.py
git commit -m "feat: add member_ids filtering to portfolio returns service and API"
```

---

## Task 7: Update TaxService with `member_id` Filtering

**Files:**
- Modify: `app/services/tax_service.py:71-76, 256-259, 319-325`
- Modify: `app/api/tax.py:19-38`

- [x] **Step 1: Write failing test**

```python
# tests/unit/test_tax_member_filter.py
import pytest
from unittest.mock import MagicMock, patch
from app.services.tax_service import TaxService


def test_get_tax_summary_filters_by_member_id():
    uow_factory = MagicMock()
    mock_uow = MagicMock()
    mock_uow.assets.list.return_value = []
    uow_factory.return_value.__enter__ = MagicMock(return_value=mock_uow)
    uow_factory.return_value.__exit__ = MagicMock(return_value=False)

    svc = TaxService(uow_factory=uow_factory)
    svc.get_tax_summary("2024-25", member_id=1)
    mock_uow.assets.list.assert_called_once_with(active=None, member_ids=[1])


def test_get_unrealised_filters_by_member_id():
    uow_factory = MagicMock()
    mock_uow = MagicMock()
    mock_uow.assets.list.return_value = []
    uow_factory.return_value.__enter__ = MagicMock(return_value=mock_uow)
    uow_factory.return_value.__exit__ = MagicMock(return_value=False)

    svc = TaxService(uow_factory=uow_factory)
    svc.get_unrealised_summary(member_id=1)
    mock_uow.assets.list.assert_called_once_with(active=True, member_ids=[1])
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_tax_member_filter.py -v`
Expected: FAIL — `get_tax_summary() got an unexpected keyword argument 'member_id'`

- [x] **Step 3: Update TaxService methods**

In `app/services/tax_service.py`:

`get_tax_summary`:
```python
def get_tax_summary(self, fy_label: str, member_id: int | None = None) -> dict:
    fy_start, fy_end = parse_fy(fy_label)
    all_results: list[AssetTaxGainsResult] = []
    member_ids = [member_id] if member_id else None

    with self._uow_factory() as uow:
        for asset in uow.assets.list(active=None, member_ids=member_ids):
            # ... rest unchanged
```

`get_unrealised_summary`:
```python
def get_unrealised_summary(self, member_id: int | None = None) -> dict:
    all_lots: list[dict] = []
    member_ids = [member_id] if member_id else None
    with self._uow_factory() as uow:
        for asset in uow.assets.list(active=True, member_ids=member_ids):
            # ... rest unchanged
```

`get_harvest_opportunities`:
```python
def get_harvest_opportunities(self, member_id: int | None = None) -> dict:
    summary = self.get_unrealised_summary(member_id=member_id)
    # ... rest unchanged
```

- [x] **Step 4: Update tax API routes to require member_id**

In `app/api/tax.py`:

```python
@router.get("/summary")
def get_tax_summary(
    fy: str = Query(..., description="Fiscal year label, e.g. '2024-25'"),
    member_id: int = Query(..., description="Member ID (required — tax is per-PAN)"),
    svc: TaxService = Depends(get_tax_service),
):
    try:
        parse_fy(fy)
    except ValueError as e:
        raise ValidationError(str(e))
    return svc.get_tax_summary(fy, member_id=member_id)


@router.get("/unrealised")
def get_unrealised(
    member_id: int = Query(..., description="Member ID (required — tax is per-PAN)"),
    svc: TaxService = Depends(get_tax_service),
):
    return svc.get_unrealised_summary(member_id=member_id)


@router.get("/harvest-opportunities")
def get_harvest_opportunities(
    member_id: int = Query(..., description="Member ID (required — tax is per-PAN)"),
    svc: TaxService = Depends(get_tax_service),
):
    return svc.get_harvest_opportunities(member_id=member_id)
```

- [x] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_tax_member_filter.py -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add app/services/tax_service.py app/api/tax.py tests/unit/test_tax_member_filter.py
git commit -m "feat: add required member_id to tax service and API endpoints"
```

---

## Task 8: Update SnapshotService for Per-Member Snapshots

**Files:**
- Modify: `app/repositories/snapshot_repo.py:10-34`
- Modify: `app/repositories/interfaces.py:108-111`
- Modify: `app/services/snapshot_service.py:17-56`
- Modify: `app/api/snapshots.py:1-23`

- [x] **Step 1: Write failing test**

```python
# tests/unit/test_snapshot_member.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.member import Member
from app.models.snapshot import PortfolioSnapshot
from app.repositories.snapshot_repo import SnapshotRepository
from datetime import date


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
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
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_snapshot_member.py -v`
Expected: FAIL

- [x] **Step 3: Update SnapshotRepository**

In `app/repositories/snapshot_repo.py`:

```python
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.snapshot import PortfolioSnapshot


class SnapshotRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, snapshot_date: date, total_value_paise: int, breakdown_json: str, member_id: int | None = None) -> PortfolioSnapshot:
        q = self.db.query(PortfolioSnapshot).filter_by(date=snapshot_date)
        if member_id is not None:
            q = q.filter_by(member_id=member_id)
        existing = q.first()
        if existing:
            existing.total_value_paise = total_value_paise
            existing.breakdown_json = breakdown_json
            self.db.flush()
            self.db.refresh(existing)
            return existing
        snapshot = PortfolioSnapshot(
            date=snapshot_date,
            total_value_paise=total_value_paise,
            breakdown_json=breakdown_json,
            member_id=member_id,
        )
        self.db.add(snapshot)
        self.db.flush()
        self.db.refresh(snapshot)
        return snapshot

    def list(self, from_date: date | None = None, to_date: date | None = None, member_ids: Optional[list[int]] = None) -> list[PortfolioSnapshot]:
        q = self.db.query(PortfolioSnapshot)
        if member_ids is not None:
            q = q.filter(PortfolioSnapshot.member_id.in_(member_ids))
        if from_date:
            q = q.filter(PortfolioSnapshot.date >= from_date)
        if to_date:
            q = q.filter(PortfolioSnapshot.date <= to_date)
        return q.order_by(PortfolioSnapshot.date.asc()).all()

    def list_aggregated(self, from_date: date | None = None, to_date: date | None = None, member_ids: Optional[list[int]] = None) -> list[dict]:
        """Return date-level aggregated snapshots (SUM across members)."""
        q = self.db.query(
            PortfolioSnapshot.date,
            func.sum(PortfolioSnapshot.total_value_paise).label("total_value_paise"),
        )
        if member_ids is not None:
            q = q.filter(PortfolioSnapshot.member_id.in_(member_ids))
        if from_date:
            q = q.filter(PortfolioSnapshot.date >= from_date)
        if to_date:
            q = q.filter(PortfolioSnapshot.date <= to_date)
        q = q.group_by(PortfolioSnapshot.date).order_by(PortfolioSnapshot.date.asc())
        return [{"date": row.date, "total_value_paise": row.total_value_paise} for row in q.all()]
```

- [x] **Step 4: Update ISnapshotRepository protocol**

In `app/repositories/interfaces.py`:

```python
@runtime_checkable
class ISnapshotRepository(Protocol):
    def upsert(self, snapshot_date: date, total_value_paise: int, breakdown_json: str, member_id: int | None = None) -> PortfolioSnapshot: ...
    def list(self, from_date: Optional[date] = None, to_date: Optional[date] = None, member_ids: Optional[list[int]] = None) -> list[PortfolioSnapshot]: ...
    def list_aggregated(self, from_date: Optional[date] = None, to_date: Optional[date] = None, member_ids: Optional[list[int]] = None) -> list[dict]: ...
    def get_by_date(self, snapshot_date: date) -> Optional[PortfolioSnapshot]: ...
```

- [x] **Step 5: Update SnapshotService**

In `app/services/snapshot_service.py`:

```python
class SnapshotService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = SnapshotRepository(db)

    def take_snapshot(self) -> dict:
        """Compute current portfolio value per member and store as today's snapshot (IST date)."""
        from datetime import datetime
        from app.repositories.member_repo import MemberRepository
        today_ist = datetime.now(tz=IST).date()

        member_repo = MemberRepository(self.db)
        members = member_repo.list_all()
        if not members:
            logger.warning("SnapshotService: no members found, skipping snapshot")
            return {}

        results = []
        for member in members:
            try:
                strategy_registry = DefaultReturnsStrategyRegistry()
                svc = PortfolioReturnsService(self.db, strategy_registry)
                overview = svc.get_overview(member_ids=[member.id])
                total_value_inr = overview.get("total_current_value", 0.0)
                total_value_paise = round(total_value_inr * 100)

                breakdown = svc.get_breakdown(member_ids=[member.id])
                breakdown_dict = {
                    entry["asset_type"]: round(entry["total_current_value"] * 100)
                    for entry in breakdown.get("breakdown", [])
                }
                breakdown_json = json.dumps(breakdown_dict)

                snapshot = self.repo.upsert(today_ist, total_value_paise, breakdown_json, member_id=member.id)
                logger.info("SnapshotService: stored snapshot for %s (member=%s) — ₹%.2f", today_ist, member.name, total_value_inr)
                results.append({"member_id": member.id, "member_name": member.name, "date": str(snapshot.date), "total_value_inr": total_value_inr})
            except Exception as e:
                logger.warning("SnapshotService: failed to take snapshot for member %s: %s", member.name, e)

        return {"snapshots": results}

    def list(self, from_date=None, to_date=None, member_ids=None) -> list[dict]:
        rows = self.repo.list_aggregated(from_date, to_date, member_ids)
        return [
            {
                "date": str(row["date"]),
                "total_value_inr": row["total_value_paise"] / 100.0,
            }
            for row in rows
        ]
```

- [x] **Step 6: Update snapshots API**

In `app/api/snapshots.py`:

```python
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_snapshot_service
from app.services.snapshot_service import SnapshotService

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.post("/take")
def take_snapshot(svc: SnapshotService = Depends(get_snapshot_service)):
    return svc.take_snapshot()


@router.get("")
def list_snapshots(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    member_ids: Optional[str] = Query(None, description="Comma-separated member IDs"),
    svc: SnapshotService = Depends(get_snapshot_service),
):
    parsed = [int(x.strip()) for x in member_ids.split(",") if x.strip()] if member_ids else None
    return svc.list(from_date, to_date, member_ids=parsed)
```

- [x] **Step 7: Run tests**

Run: `uv run pytest tests/unit/test_snapshot_member.py -v`
Expected: PASS

- [x] **Step 8: Commit**

```bash
git add app/repositories/snapshot_repo.py app/repositories/interfaces.py app/services/snapshot_service.py app/api/snapshots.py tests/unit/test_snapshot_member.py
git commit -m "feat: per-member snapshots with aggregated listing"
```

---

## Task 9: Update ImportOrchestrator with `member_id`

**Files:**
- Modify: `app/services/imports/orchestrator.py:72-78, 180-227`
- Modify: `app/api/imports.py:13-48`

- [x] **Step 1: Write failing test**

```python
# tests/unit/test_import_member.py
import pytest
from unittest.mock import MagicMock
from app.services.imports.orchestrator import ImportOrchestrator
from app.importers.base import ImportResult, ParsedTransaction
from datetime import date


def test_find_or_create_asset_uses_member_id():
    """New assets created during import should carry the member_id from preview."""
    uow = MagicMock()
    uow.assets.list.return_value = []  # no existing assets

    mock_create = MagicMock()
    mock_create.return_value = MagicMock(id=1, asset_type=MagicMock(value="STOCK_IN"))
    uow.assets.create = mock_create

    orchestrator = ImportOrchestrator(
        uow_factory=MagicMock(),
        pipeline=MagicMock(),
        preview_store=MagicMock(),
        post_processors=[],
        event_bus=MagicMock(),
    )

    parsed_txn = ParsedTransaction(
        txn_id="test-1",
        asset_name="Test Stock",
        asset_type="STOCK_IN",
        txn_type="BUY",
        date=date(2026, 1, 1),
        amount_inr=-10000.0,
        asset_identifier="INE001A01036",
    )

    orchestrator._find_or_create_asset(parsed_txn, uow, member_id=42)
    _, kwargs = mock_create.call_args
    assert kwargs["member_id"] == 42
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_import_member.py -v`
Expected: FAIL — `_find_or_create_asset() got an unexpected keyword argument 'member_id'`

- [x] **Step 3: Update ImportOrchestrator**

In `app/services/imports/orchestrator.py`:

Update `preview()` to store `member_id` in the result:
```python
def preview(
    self,
    source: str,
    fmt: str,
    file_bytes: bytes,
    member_id: int | None = None,
    **importer_kwargs,
) -> ImportPreviewResponse:
    result = self._pipeline.run(source, fmt, file_bytes, **importer_kwargs)
    result.member_id = member_id  # attach for commit phase
    # ... rest unchanged
```

Update `commit()` to forward member_id:
```python
def commit(self, preview_id: str) -> Optional[ImportCommitResponse]:
    result = self._store.get(preview_id)
    if result is None:
        return None

    member_id = getattr(result, "member_id", None)
    # ... existing code ...
    
    with self._uow_factory() as uow:
        # ... existing pre-commit processor code ...
        
        for parsed_txn in result.transactions:
            try:
                asset = self._find_or_create_asset(parsed_txn, uow, member_id=member_id)
                # ... rest unchanged
```

Update `_find_or_create_asset()` to accept and use `member_id`:
```python
def _find_or_create_asset(self, parsed_txn: ParsedTransaction, uow: UnitOfWork, member_id: int | None = None) -> Asset:
    # ... existing matching logic (by identifier, by name) unchanged ...
    
    # Create new asset — include member_id
    return uow.assets.create(
        name=parsed_txn.asset_name,
        identifier=parsed_txn.asset_identifier or "",
        mfapi_scheme_code=scheme_code,
        scheme_category=scheme_category,
        asset_type=asset_type_enum,
        asset_class=asset_class,
        currency="USD" if parsed_txn.asset_type in ("STOCK_US", "RSU") else "INR",
        is_active=True,
        member_id=member_id,
    )
```

- [x] **Step 4: Update import API to accept member_id**

In `app/api/imports.py`:

```python
@router.post("/preview-file")
async def preview_file_import(
    source: str = Query(..., description="Importer source: zerodha/cas/nps/ppf/epf/fidelity_rsu/fidelity_sale"),
    format: str = Query(..., description="File format: csv or pdf"),
    member_id: int = Query(..., description="Member ID to associate imported assets with"),
    file: UploadFile = File(...),
    user_inputs: str | None = Form(None, description='JSON object e.g. {"2025-03": 86.5} for fidelity sources'),
    orchestrator: ImportOrchestrator = Depends(get_import_orchestrator),
):
    # ... existing code ...
    try:
        response = orchestrator.preview(source, format, file_bytes, member_id=member_id, **importer_kwargs)
    # ... rest unchanged
```

- [x] **Step 5: Run tests**

Run: `uv run pytest tests/unit/test_import_member.py -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add app/services/imports/orchestrator.py app/api/imports.py tests/unit/test_import_member.py
git commit -m "feat: thread member_id through import orchestrator and API"
```

---

## Task 10: Update ImportantData with `member_ids` Filtering

**Files:**
- Modify: `app/repositories/important_data_repo.py:20-24`
- Modify: `app/services/important_data_service.py`
- Modify: `app/api/important_data.py`

- [x] **Step 1: Update ImportantDataRepository.list_all()**

In `app/repositories/important_data_repo.py`:

```python
def list_all(self, category: Optional[ImportantDataCategory] = None, member_ids: Optional[list[int]] = None) -> list[ImportantData]:
    q = self.db.query(ImportantData)
    if member_ids is not None:
        q = q.filter(ImportantData.member_id.in_(member_ids))
    if category is not None:
        q = q.filter(ImportantData.category == category)
    return q.order_by(ImportantData.id).all()
```

- [x] **Step 2: Thread `member_ids` through ImportantDataService**

Find the `list` or `list_all` method in the service and add the `member_ids` parameter, forwarding it to the repo.

- [x] **Step 3: Add `member_ids` query param to the important_data API route**

In the `GET /important-data` route, add:
```python
member_ids: Optional[str] = Query(None, description="Comma-separated member IDs")
```
Parse and forward to service.

- [x] **Step 4: Run existing tests**

Run: `uv run pytest tests/integration/test_important_data_api.py -v`
Expected: PASS (existing tests unaffected since member_ids is optional)

- [x] **Step 5: Commit**

```bash
git add app/repositories/important_data_repo.py app/services/important_data_service.py app/api/important_data.py
git commit -m "feat: add member_ids filtering to important_data repository and API"
```

---

## Task 11: CLI — `add-member` Command + `--pan` on Imports

**Files:**
- Modify: `cli.py:52-67, 111-281, 654-841, 844-865`

- [ ] **Step 1: Add member resolution helper**

Near the top of `cli.py` (after `find_asset`), add:

```python
def resolve_member_id(pan: str) -> int:
    """Look up member by PAN via GET /members. Exit if not found."""
    members = _api("get", "/members")
    for m in members:
        if m["pan"].upper() == pan.upper():
            print(f"  → matched member: {m['name']} (id={m['id']}, PAN={m['pan']})")
            return m["id"]
    sys.exit(f"No member with PAN '{pan}'. Run 'add-member --pan {pan} --name <name>' first.")
```

- [ ] **Step 2: Add `cmd_add_member` function**

```python
def cmd_add_member(pan: str, name: str) -> dict:
    result = _api("post", "/members", json={"pan": pan, "name": name})
    print(f"  → created member: {result['name']} (id={result['id']}, PAN={result['pan']})")
    return result
```

- [ ] **Step 3: Add `--pan` to all import subparsers**

In `build_parser()`, after the import subparsers are created, add `--pan` to each:

```python
# Replace the loop at lines 665-667:
for src in ("ppf", "epf", "cas", "nps"):
    s = import_sub.add_parser(src, help=f"Import {src.upper()} file")
    s.add_argument("file", help="Path to the file")
    s.add_argument("--pan", required=True, help="PAN of the member this import belongs to")

s = import_sub.add_parser("zerodha", help="Import Zerodha tradebook CSV")
s.add_argument("file", help="Path to CSV")
s.add_argument("--pan", required=True, help="PAN of the member this import belongs to")

s = import_sub.add_parser("fidelity-rsu", help="Import Fidelity RSU holding CSV (MARKET_TICKER.csv)")
s.add_argument("file", help="Path to CSV file")
s.add_argument("--pan", required=True, help="PAN of the member this import belongs to")

s = import_sub.add_parser("fidelity-sale", help="Import Fidelity tax-cover sale PDF")
s.add_argument("file", help="Path to PDF file")
s.add_argument("--pan", required=True, help="PAN of the member this import belongs to")
```

- [ ] **Step 4: Add `add-member` subparser**

In `build_parser()`, before the `return parser`:

```python
# ── add-member ───────────────────────────────────────────────────────
p_add_member = sub.add_parser("add-member", help="Register a household member")
p_add_member.add_argument("--pan", required=True, help="PAN card number (e.g. ABCDE1234F)")
p_add_member.add_argument("--name", required=True, help="Member name")
```

- [ ] **Step 5: Update all import command functions to accept and forward member_id**

Each import command function gains a `member_id: int` parameter and appends `&member_id={member_id}` to the preview API call. For example:

`cmd_import_ppf`:
```python
def cmd_import_ppf(file_path: str, member_id: int) -> dict:
    _check_file(file_path)
    with open(file_path, "rb") as f:
        preview = _api("post", f"/import/preview-file?source=ppf&format=csv&member_id={member_id}", files={"file": f})
    result = _api("post", f"/import/commit-file/{preview['preview_id']}")
    _print_import_summary("PPF", inserted=result["inserted"], skipped=result["skipped"])
    return result
```

Apply the same pattern to `cmd_import_epf`, `cmd_import_cas`, `cmd_import_nps`, `cmd_import_broker_csv`, `cmd_import_fidelity_rsu`, `cmd_import_fidelity_sale`.

- [ ] **Step 6: Update main() dispatch to resolve PAN and pass member_id**

In `main()`, update the import dispatch:

```python
if args.command == "import":
    if not args.source:
        parser.parse_args(["import", "--help"])
        return
    member_id = resolve_member_id(args.pan)
    if args.source == "ppf":
        cmd_import_ppf(args.file, member_id)
    elif args.source == "epf":
        cmd_import_epf(args.file, member_id)
    elif args.source == "cas":
        cmd_import_cas(args.file, member_id)
    elif args.source == "nps":
        cmd_import_nps(args.file, member_id)
    elif args.source == "zerodha":
        cmd_import_broker_csv(args.file, broker="zerodha", member_id=member_id)
    elif args.source == "fidelity-rsu":
        cmd_import_fidelity_rsu(args.file, member_id)
    elif args.source == "fidelity-sale":
        cmd_import_fidelity_sale(args.file, member_id)
```

Add the `add-member` dispatch:
```python
elif args.command == "add-member":
    cmd_add_member(args.pan, args.name)
```

- [ ] **Step 7: Update `cmd_snapshot` to call the same API** (no change needed — API handles per-member internally)

- [ ] **Step 8: Run a quick smoke test**

Run: `uv run python cli.py add-member --help`
Expected: Shows `--pan` and `--name` as required args

Run: `uv run python cli.py import ppf --help`
Expected: Shows `--pan` as required arg

- [ ] **Step 9: Commit**

```bash
git add cli.py
git commit -m "feat: add add-member CLI command and --pan to all import commands"
```

---

## Task 12: Frontend — Member Context + API

**Files:**
- Create: `frontend/contexts/MemberContext.tsx`
- Create: `frontend/hooks/useMembers.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/constants/index.ts`

- [ ] **Step 1: Add Member type to constants**

In `frontend/constants/index.ts`, add:

```typescript
export interface Member {
  id: number;
  pan: string;
  name: string;
  is_default: boolean;
  created_at: string;
}
```

- [ ] **Step 2: Add members API namespace**

In `frontend/lib/api.ts`, add:

```typescript
members: {
  list: (): Promise<Member[]> => client.get('/members').then(r => r.data),
  create: (data: { pan: string; name: string }): Promise<Member> => client.post('/members', data).then(r => r.data),
},
```

Import the `Member` type from constants.

- [ ] **Step 3: Create MemberContext**

```tsx
// frontend/contexts/MemberContext.tsx
'use client';

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import { api } from '@/lib/api';
import { Member } from '@/constants';

interface MemberContextType {
  members: Member[];
  selectedMemberIds: number[];
  setSelectedMemberIds: (ids: number[]) => void;
  loading: boolean;
}

const MemberContext = createContext<MemberContextType>({
  members: [],
  selectedMemberIds: [],
  setSelectedMemberIds: () => {},
  loading: true,
});

const STORAGE_KEY = 'selectedMemberIds';

export function MemberProvider({ children }: { children: ReactNode }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [selectedMemberIds, setSelectedMemberIdsState] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.members.list()
      .then((data) => {
        setMembers(data);
        // Restore from localStorage, fallback to all members
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          try {
            const ids = JSON.parse(stored) as number[];
            // Filter to valid member ids
            const valid = ids.filter(id => data.some(m => m.id === id));
            setSelectedMemberIdsState(valid.length > 0 ? valid : data.map(m => m.id));
          } catch {
            setSelectedMemberIdsState(data.map(m => m.id));
          }
        } else {
          setSelectedMemberIdsState(data.map(m => m.id));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const setSelectedMemberIds = useCallback((ids: number[]) => {
    setSelectedMemberIdsState(ids);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  }, []);

  return (
    <MemberContext.Provider value={{ members, selectedMemberIds, setSelectedMemberIds, loading }}>
      {children}
    </MemberContext.Provider>
  );
}

export function useMembers() {
  return useContext(MemberContext);
}
```

- [ ] **Step 4: Wrap app with MemberProvider**

In `frontend/app/layout.tsx`, import and wrap:

```tsx
import { MemberProvider } from '@/contexts/MemberContext';

// Inside the layout body, wrap children:
<MemberProvider>
  {children}
</MemberProvider>
```

- [ ] **Step 5: Commit**

```bash
cd /Users/dhirajkasar/Documents/workspace/financial-tracker
git add frontend/contexts/MemberContext.tsx frontend/lib/api.ts frontend/constants/index.ts frontend/app/layout.tsx
git commit -m "feat: add MemberContext, members API, and MemberProvider"
```

---

## Task 13: Frontend — MemberSelector Dropdown in Header

**Files:**
- Create: `frontend/components/ui/MemberSelector.tsx`
- Modify: `frontend/app/TabNavClient.tsx`

- [ ] **Step 1: Create MemberSelector component**

```tsx
// frontend/components/ui/MemberSelector.tsx
'use client';

import { useRef, useState, useEffect } from 'react';
import { useMembers } from '@/contexts/MemberContext';

function maskPan(pan: string): string {
  return pan.length >= 6 ? `XXXX${pan.slice(4, 8)}${pan.slice(-1)}` : pan;
}

export default function MemberSelector() {
  const { members, selectedMemberIds, setSelectedMemberIds, loading } = useMembers();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  if (loading || members.length === 0) return null;

  const allSelected = selectedMemberIds.length === members.length;
  const label = allSelected
    ? 'All Members'
    : selectedMemberIds.length === 1
      ? members.find(m => m.id === selectedMemberIds[0])?.name ?? 'Select'
      : `${selectedMemberIds.length} Members`;

  function toggle(id: number) {
    const next = selectedMemberIds.includes(id)
      ? selectedMemberIds.filter(x => x !== id)
      : [...selectedMemberIds, id];
    // Don't allow empty selection — default to all
    setSelectedMemberIds(next.length === 0 ? members.map(m => m.id) : next);
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="px-3 py-1.5 text-sm rounded-md border border-border bg-bg-page text-primary hover:bg-border transition-colors"
      >
        {label} ▾
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-56 rounded-md border border-border bg-bg-page shadow-lg z-50">
          {members.map((m) => (
            <label
              key={m.id}
              className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-border cursor-pointer"
            >
              <input
                type="checkbox"
                checked={selectedMemberIds.includes(m.id)}
                onChange={() => toggle(m.id)}
                className="rounded"
              />
              <span className="text-primary">{m.name}</span>
              <span className="text-secondary text-xs ml-auto">{maskPan(m.pan)}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add MemberSelector to header**

In `frontend/app/TabNavClient.tsx`, import and add the selector alongside the dark mode / private mode toggles:

```tsx
import MemberSelector from '@/components/ui/MemberSelector';

// In the JSX, add before or alongside the existing toggle buttons:
<MemberSelector />
```

- [ ] **Step 3: Verify in browser**

Run: `cd /Users/dhirajkasar/Documents/workspace/financial-tracker/frontend && npm run dev`
Check: Member dropdown appears in header with checkboxes

- [ ] **Step 4: Commit**

```bash
cd /Users/dhirajkasar/Documents/workspace/financial-tracker
git add frontend/components/ui/MemberSelector.tsx frontend/app/TabNavClient.tsx
git commit -m "feat: add MemberSelector multi-select dropdown in header"
```

---

## Task 14: Frontend — Thread `member_ids` Through Data-Fetching Hooks

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/hooks/useAssets.ts`
- Modify: `frontend/hooks/useOverview.ts`
- Modify: `frontend/hooks/useBreakdown.ts`
- Modify: `frontend/hooks/useAllocation.ts`
- Modify: `frontend/hooks/useGainers.ts`
- Modify: `frontend/hooks/useSnapshots.ts`

- [ ] **Step 1: Update API functions to accept member_ids**

In `frontend/lib/api.ts`, update the affected functions. Example for `assets.list`:

```typescript
assets: {
  list: (params?: { type?: AssetType; active?: boolean; member_ids?: number[] }): Promise<Asset[]> => {
    const p: Record<string, string> = {};
    if (params?.type) p.type = params.type;
    if (params?.active !== undefined) p.active = String(params.active);
    if (params?.member_ids?.length) p.member_ids = params.member_ids.join(',');
    return client.get('/assets', { params: p }).then(r => r.data);
  },
  // ... rest unchanged
},
```

Apply the same pattern to `returns.overview`, `returns.breakdown`, `returns.allocation`, `returns.gainers`, `snapshots.list`.

- [ ] **Step 2: Update each hook to read from MemberContext and pass member_ids**

Each hook should import `useMembers` and include `selectedMemberIds` in its dependency array. Example for `useOverview.ts`:

```typescript
import { useMembers } from '@/contexts/MemberContext';

export function useOverview(types?: AssetType[]) {
  const { selectedMemberIds } = useMembers();
  const [data, setData] = useState<OverviewReturns | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.returns.overview(types, selectedMemberIds)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [types?.join(','), selectedMemberIds.join(',')]);

  return { data, loading, error };
}
```

Apply the same pattern to `useAssets`, `useBreakdown`, `useAllocation`, `useGainers`, `useSnapshots`.

- [ ] **Step 3: Verify in browser**

Toggle the member dropdown — all pages should refetch data for selected members.

- [ ] **Step 4: Commit**

```bash
cd /Users/dhirajkasar/Documents/workspace/financial-tracker
git add frontend/lib/api.ts frontend/hooks/
git commit -m "feat: thread member_ids from context through all data-fetching hooks"
```

---

## Task 15: Frontend — Tax Page Single-Select Member Picker

**Files:**
- Modify: `frontend/app/tax/page.tsx`
- Modify: `frontend/lib/api.ts` (tax functions)

- [ ] **Step 1: Update tax API functions to require member_id**

In `frontend/lib/api.ts`:

```typescript
tax: {
  fiscalYears: (): Promise<{ fiscal_years: string[] }> => client.get('/tax/fiscal-years').then(r => r.data),
  summary: (fy: string, memberId: number): Promise<TaxSummaryResponse> =>
    client.get('/tax/summary', { params: { fy, member_id: memberId } }).then(r => r.data),
  unrealised: (memberId: number): Promise<UnrealisedResponse> =>
    client.get('/tax/unrealised', { params: { member_id: memberId } }).then(r => r.data),
  harvestOpportunities: (memberId: number): Promise<HarvestResponse> =>
    client.get('/tax/harvest-opportunities', { params: { member_id: memberId } }).then(r => r.data),
},
```

- [ ] **Step 2: Add single-select member picker to tax page**

In the tax page component, add a local state for the selected member (not from MemberContext):

```tsx
import { useMembers } from '@/contexts/MemberContext';

// Inside the component:
const { members } = useMembers();
const [taxMemberId, setTaxMemberId] = useState<number | null>(null);

// Set default to first member when members load
useEffect(() => {
  if (members.length > 0 && taxMemberId === null) {
    setTaxMemberId(members[0].id);
  }
}, [members, taxMemberId]);

// Render a simple select dropdown at the top:
<select
  value={taxMemberId ?? ''}
  onChange={(e) => setTaxMemberId(Number(e.target.value))}
  className="px-3 py-1.5 text-sm rounded-md border border-border bg-bg-page text-primary"
>
  {members.map((m) => (
    <option key={m.id} value={m.id}>
      {m.name} — {maskPan(m.pan)}
    </option>
  ))}
</select>
```

- [ ] **Step 3: Pass taxMemberId to all tax API calls**

Update all tax data fetching in the tax page to use `taxMemberId` instead of any global member context.

- [ ] **Step 4: Verify in browser**

Navigate to Tax page. Single-select dropdown should appear. Changing it should reload tax data for that member only.

- [ ] **Step 5: Commit**

```bash
cd /Users/dhirajkasar/Documents/workspace/financial-tracker
git add frontend/lib/api.ts frontend/app/tax/
git commit -m "feat: tax page uses independent single-select member picker"
```

---

## Task 16: Run Full Test Suite + Fix Regressions

**Files:** Various test files

- [ ] **Step 1: Run all backend tests**

Run: `uv run pytest tests/ -v --timeout=120`

- [ ] **Step 2: Fix any failures**

Common issues:
- Existing tests creating `Asset` objects without `member_id` → add a test fixture that creates a default member and passes `member_id` to all asset creation
- Tax API tests missing required `member_id` query param → add it
- Snapshot tests need member_id in upsert calls

- [ ] **Step 3: Run frontend build**

Run: `cd /Users/dhirajkasar/Documents/workspace/financial-tracker/frontend && npm run build`

- [ ] **Step 4: Fix any TypeScript errors**

- [ ] **Step 5: Commit all fixes**

```bash
git add -A
git commit -m "fix: update existing tests and types for multi-member support"
```

---

## Task 17: Update CLAUDE.md

**Files:**
- Modify: `/Users/dhirajkasar/Documents/workspace/financial-tracker/CLAUDE.md`

- [ ] **Step 1: Add Member to the relevant sections**

Add to the "Asset Types" or a new "Members" section:
- `members` table: PAN-identified household members
- `member_id` FK on `assets`, `important_data`, `portfolio_snapshots`
- API: `GET/POST /members`; most list endpoints accept optional `member_ids`; tax endpoints require `member_id`
- CLI: `add-member --pan --name`; all import commands require `--pan`

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with multi-member household support"
```
