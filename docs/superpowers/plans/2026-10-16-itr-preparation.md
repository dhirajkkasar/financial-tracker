# ITR Preparation Utility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the tracker into a local, offline ITR preparation utility: per PAN and per Assessment Year, ingest an optional Form 16, aggregate all income and capital gains from existing data, apply set-off/carry-forward, compute tax, and emit an ITR-2 JSON validated against the official schema and importable into the Income Tax Department's Common Offline Utility.

**Architecture:** New pure `engine/itr/` package (AY helpers, tax computation, 112A, form selector, AY-versioned JSON builders, schema validation) and `engine/form16_parser.py`. One new table `itr_returns` stores the per-member/per-AY `ReturnInput` snapshot plus the generated JSON. `services/itr_service.py` assembles a draft from the UoW + existing `TaxService`; `services/itr_json_service.py` builds + validates + persists. HTTP surface in `api/itr.py`; thin CLI under `fintrack itr`. Follows the repo layering in `CLAUDE.md` (engine = pure, no DB; services via UoW; all wiring in `api/dependencies.py`).

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, Alembic, PyYAML, Pydantic, `pdfplumber` (present), `fpdf2` (present, for synthetic test PDFs), `jsonschema` (**new dependency**), pytest; Next.js/TypeScript for the UI stub.

**Spec:** `docs/superpowers/specs/2026-10-16-itr-preparation-design.md`

**Key codebase facts (verified):**
- FY helpers already exist: `app.engine.tax_engine.parse_fy("2024-25") -> (date(2024,4,1), date(2025,3,31))`.
- `TaxService.get_tax_summary(fy, member_id)` returns `{stcg, ltcg, interest, ...}` per `app/schemas/responses/tax.py`.
- UoW: `with self._uow_factory() as uow: uow.members.get_by_pan(pan)`; repos live in `app/repositories/`, attached in `backend/app/repositories/unit_of_work.py`. Repos use `db.flush()` + `db.refresh()`.
- Models use `Mapped[...] = mapped_column(...)`; money is **paise as `BigInteger`** on transactions, but tax tables use `Float` INR (`member_tax_profiles.total_income_inr`). New tax tables follow the **Float INR** convention.
- Migrations: **there are two alembic heads** — `3cc18d9706a2` and `9f2c4a7b1e3d`. A merge revision is required before adding new tables (Task A2).
- Routers registered in `app/main.py` with `prefix="/api"`. Service wiring in `app/api/dependencies.py` (see `get_tax_service`, line 173).
- CLI: `backend/cli.py`, `build_parser()` + `main()` dispatch; commands are thin HTTP clients via `_api(method, path, json=...)`.
- Tests: `backend/tests/{unit,integration}`, fixtures `db` and `client` in `backend/tests/conftest.py`; run with `cd backend && uv run pytest`.
- `jsonschema` is **not** yet a dependency.

**Deliverable reality (from the spec):** the portal's direct JSON upload rejects self-built files ("Invalid Software Provider ID"). The output is a JSON to **import into the official Common Offline Utility**. All UI/CLI copy must say so.

**Milestone 1 = Phases A–D** (Form 16 → validated ITR-2 JSON for AY 2026-27). Phases E–G are outlined and picked up after.

---

## Phase A — Foundation: AY model, persistence, service, API/CLI

### Task A1: FY↔AY helper

**Files:**
- Create: `backend/app/engine/itr/__init__.py`
- Create: `backend/app/engine/itr/ay.py`
- Create: `backend/tests/unit/test_itr_ay.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_itr_ay.py
import pytest
from app.engine.itr.ay import fy_to_ay, ay_to_fy, parse_ay


def test_fy_to_ay_2024_25():
    assert fy_to_ay("2024-25") == "2025-26"


def test_fy_to_ay_2025_26():
    assert fy_to_ay("2025-26") == "2026-27"


def test_ay_to_fy_roundtrip():
    assert ay_to_fy("2026-27") == "2025-26"


def test_fy_to_ay_rejects_bad_label():
    with pytest.raises(ValueError):
        fy_to_ay("2024/25")


def test_parse_ay_returns_income_year_dates():
    # AY 2025-26 assesses the income of FY 2024-25.
    assert parse_ay("2025-26") == (date(2024, 4, 1), date(2025, 3, 31))


def test_parse_ay_matches_parse_fy_of_income_year():
    from app.engine.tax_engine import parse_fy
    assert parse_ay("2026-27") == parse_fy(ay_to_fy("2026-27"))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/unit/test_itr_ay.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.engine.itr'`

- [ ] **Step 3: Implement**

```python
# backend/app/engine/itr/ay.py
"""Assessment-year helpers. Pure functions, no DB.

FY 2024-25 → AY 2025-26. The ITR form is filed *for* the AY; the income
belongs to the FY. Keep both labels on every return.
"""
from __future__ import annotations

from datetime import date

from app.engine.tax_engine import parse_fy


def _split(label: str) -> tuple[int, int]:
    parts = label.split("-")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError(f"Invalid year label {label!r}. Expected 'YYYY-YY'.")
    start = int(parts[0])
    suffix = int(parts[1])
    end = (start // 100) * 100 + suffix if suffix < 100 else suffix
    if end != start + 1:
        raise ValueError(f"Invalid year label {label!r}. End must be start + 1.")
    return start, end


def _fmt(start: int) -> str:
    return f"{start}-{str(start + 1)[-2:]}"


def fy_to_ay(fy_label: str) -> str:
    start, _ = _split(fy_label)
    return _fmt(start + 1)


def ay_to_fy(ay_label: str) -> str:
    start, _ = _split(ay_label)
    return _fmt(start - 1)


def parse_ay(ay_label: str) -> tuple[date, date]:
    """AY '2025-26' → assessment-year window 2025-04-01 .. 2026-03-31.

    This is the *income* FY window expressed with the AY label; callers that
    need the income window should prefer parse_fy(ay_to_fy(ay)).
    """
    start, _ = _split(ay_label)
    return date(start, 4, 1), date(start + 1, 3, 31)
```

```python
# backend/app/engine/itr/__init__.py
```
(empty)

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/unit/test_itr_ay.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/itr backend/tests/unit/test_itr_ay.py
git commit -m "feat(itr): FY<->AY helpers"
```

---

### Task A2: `itr_returns` table + schema

**Files:**
- Create: `backend/app/models/itr_return.py`
- Create: `backend/alembic/versions/<hash>_merge_heads_and_add_itr_returns.py`
- Modify: `backend/app/models/__init__.py` (import the model so `Base.metadata` sees it)
- Create: `backend/tests/unit/test_itr_return_model.py`

**Note:** there are two alembic heads. The new migration must merge them:
`down_revision = ("3cc18d9706a2", "9f2c4a7b1e3d")`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_itr_return_model.py
from app.models.itr_return import ItrReturn


def test_itr_return_tablename_and_columns():
    cols = {c.name for c in ItrReturn.__table__.columns}
    assert ItrReturn.__tablename__ == "itr_returns"
    assert {"id", "member_id", "fy_label", "ay_label", "form_type",
            "status", "input_json", "draft_json", "output_json",
            "schema_version", "generated_at", "created_at", "updated_at"} <= cols


def test_itr_return_unique_member_ay():
    names = {c.name for c in ItrReturn.__table__.constraints if c.name}
    assert "uq_itr_return_member_ay" in names
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/unit/test_itr_return_model.py -v
```
Expected: `ModuleNotFoundError: No module named 'app.models.itr_return'`

- [ ] **Step 3: Implement the model**

```python
# backend/app/models/itr_return.py
"""Per-member, per-Assessment-Year ITR return.

Stores the typed ReturnInput snapshot (so next year can be seeded), the
assembled draft, and the generated ITR JSON + schema version.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ItrReturn(Base):
    __tablename__ = "itr_returns"
    __table_args__ = (
        UniqueConstraint("member_id", "ay_label", name="uq_itr_return_member_ay"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False, index=True)
    fy_label: Mapped[str] = mapped_column(String(10), nullable=False)
    ay_label: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    form_type: Mapped[str] = mapped_column(String(10), nullable=False, default="ITR2")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    input_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    schema_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
```

Add `from app.models.itr_return import ItrReturn  # noqa: F401` to
`backend/app/models/__init__.py`.

- [ ] **Step 4: Write the migration**

Create the revision by hand (matches repo style, no autogenerate in CI):

```python
# backend/alembic/versions/xxxx_merge_heads_and_add_itr_returns.py
"""merge heads and add itr_returns

Revision ID: <new12>
Revises: 3cc18d9706a2, 9f2c4a7b1e3d
Create Date: 2026-10-16 ...
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "<new12>"
down_revision: Union[str, Sequence[str], None] = ("3cc18d9706a2", "9f2c4a7b1e3d")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "itr_returns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("fy_label", sa.String(length=10), nullable=False),
        sa.Column("ay_label", sa.String(length=10), nullable=False),
        sa.Column("form_type", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=True),
        sa.Column("draft_json", sa.Text(), nullable=True),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.String(length=50), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id", "ay_label", name="uq_itr_return_member_ay"),
    )
    op.create_index(op.f("ix_itr_returns_id"), "itr_returns", ["id"], unique=False)
    op.create_index(op.f("ix_itr_returns_member_id"), "itr_returns", ["member_id"], unique=False)
    op.create_index(op.f("ix_itr_returns_ay_label"), "itr_returns", ["ay_label"], unique=False)


def downgrade() -> None:
    op.drop_table("itr_returns")
```

- [ ] **Step 5: Verify**

```bash
cd backend && .venv/bin/python -m alembic heads          # expect a single head
uv run pytest tests/unit/test_itr_return_model.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/itr_return.py backend/app/models/__init__.py backend/alembic/versions backend/tests/unit/test_itr_return_model.py
git commit -m "feat(itr): itr_returns table + merge alembic heads"
```

---

### Task A3: Repository + UoW wiring

**Files:**
- Create: `backend/app/repositories/itr_return_repo.py`
- Modify: `backend/app/repositories/unit_of_work.py` (attach `self.itr_returns`)
- Create: `backend/tests/unit/test_itr_return_repo.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_itr_return_repo.py
from app.repositories.itr_return_repo import ItrReturnRepository


def test_get_or_create_creates_once(db):
    repo = ItrReturnRepository(db)
    a = repo.get_or_create(member_id=1, fy_label="2025-26", ay_label="2026-27")
    b = repo.get_or_create(member_id=1, fy_label="2025-26", ay_label="2026-27")
    assert a.id == b.id
    assert a.form_type == "ITR2"
    assert a.status == "draft"


def test_set_and_get_input_json(db):
    repo = ItrReturnRepository(db)
    r = repo.get_or_create(member_id=1, fy_label="2025-26", ay_label="2026-27")
    repo.save_input(r.id, '{"regime": "new"}')
    assert repo.get(r.id).input_json == '{"regime": "new"}'
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/unit/test_itr_return_repo.py -v
```

- [ ] **Step 3: Implement**

```python
# backend/app/repositories/itr_return_repo.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.itr_return import ItrReturn


class ItrReturnRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, return_id: int) -> Optional[ItrReturn]:
        return self.db.query(ItrReturn).filter(ItrReturn.id == return_id).first()

    def get_by_member_ay(self, member_id: int, ay_label: str) -> Optional[ItrReturn]:
        return self.db.query(ItrReturn).filter(
            ItrReturn.member_id == member_id,
            ItrReturn.ay_label == ay_label,
        ).first()

    def list_by_member(self, member_id: int) -> list[ItrReturn]:
        return self.db.query(ItrReturn).filter(
            ItrReturn.member_id == member_id,
        ).order_by(ItrReturn.ay_label).all()

    def get_or_create(self, member_id: int, fy_label: str, ay_label: str) -> ItrReturn:
        existing = self.get_by_member_ay(member_id, ay_label)
        if existing:
            return existing
        record = ItrReturn(member_id=member_id, fy_label=fy_label, ay_label=ay_label)
        self.db.add(record)
        self.db.flush()
        self.db.refresh(record)
        return record

    def save_input(self, return_id: int, input_json: str) -> ItrReturn:
        record = self.get(return_id)
        record.input_json = input_json
        record.updated_at = datetime.utcnow()
        self.db.flush()
        self.db.refresh(record)
        return record
```

Attach in `unit_of_work.py`:

```python
from app.repositories.itr_return_repo import ItrReturnRepository
# ... inside UnitOfWork.__init__:
self.itr_returns = ItrReturnRepository(session)
```

- [ ] **Step 4: Run + commit**

```bash
cd backend && uv run pytest tests/unit/test_itr_return_repo.py -v
git add backend/app/repositories backend/tests/unit/test_itr_return_repo.py
git commit -m "feat(itr): itr_return repository + UoW wiring"
```

---

### Task A4: `ReturnInput` / `ReturnDraft` typed schemas

**Files:**
- Create: `backend/app/schemas/itr_models.py` (shared Pydantic models, not request/response specific)
- Create: `backend/tests/unit/test_itr_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_itr_models.py
import pytest
from pydantic import ValidationError
from app.schemas.itr_models import ReturnInput, Form16SummaryIn


def test_return_input_minimal_defaults():
    ri = ReturnInput(member_id=1, fy_label="2025-26", ay_label="2026-27")
    assert ri.regime == "new"
    assert ri.salary == []
    assert ri.other_income.savings_interest == 0.0


def test_return_input_rejects_bad_regime():
    with pytest.raises(ValidationError):
        ReturnInput(member_id=1, fy_label="2025-26", ay_label="2026-27", regime="flat")


def test_form16_summary_roundtrip():
    f = Form16SummaryIn(employer_name="ACME", employer_tan="BLRA05499E",
                        employee_pan="ABCDE1234F", gross_salary=1200000.0, tds=90000.0)
    assert f.model_dump()["gross_salary"] == 1200000.0
```

- [ ] **Step 2: Run to verify failure**, then **Step 3: implement**

```python
# backend/app/schemas/itr_models.py
"""Pydantic models for the per-year ITR input document (the reusable artifact)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AddressIn(BaseModel):
    line1: str = ""
    line2: str = ""
    city: str = ""
    state_code: str = ""
    pin: Optional[int] = None
    country_code: str = "91"
    mobile: Optional[str] = None
    email: Optional[str] = None


class BankAccountIn(BaseModel):
    bank_name: str = ""
    account_number: str = ""
    ifsc: str = ""
    account_type: Literal["SBA", "CA", "CC", "OD", "NRO", "NRE", "OTH"] = "SBA"
    is_refund_account: bool = False


class Form16SummaryIn(BaseModel):
    employer_name: str = ""
    employer_tan: str = ""
    employer_address: str = ""
    employee_pan: str = ""
    employee_name: str = ""
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    gross_salary: float = 0.0
    exemptions_10: float = 0.0
    standard_deduction: float = 0.0
    professional_tax: float = 0.0
    perquisites: float = 0.0
    total_taxable_income: float = 0.0
    chapter_via: dict[str, float] = Field(default_factory=dict)
    tds: float = 0.0
    opted_out_115bac: bool = False
    warnings: list[str] = Field(default_factory=list)


class OtherIncomeIn(BaseModel):
    savings_interest: float = 0.0
    term_deposit_interest_override: Optional[float] = None
    other_interest: float = 0.0
    interest_on_it_refund: float = 0.0
    dividends: float = 0.0
    dividend_quarters: dict[str, float] = Field(default_factory=dict)


class ForeignIncomeIn(BaseModel):
    dividends: float = 0.0
    tax_paid_abroad: float = 0.0
    fa_asset_overrides: list[dict] = Field(default_factory=list)


class ChallanIn(BaseModel):
    bsr_code: str = ""
    date: str = ""
    serial: str = ""
    amount: float = 0.0


class ReturnInput(BaseModel):
    member_id: int
    fy_label: str
    ay_label: str
    regime: Literal["new", "old"] = "new"
    residential_status: Literal["RES", "NRI", "NOR"] = "RES"
    pan: str = ""
    name: str = ""
    dob: Optional[str] = None
    address: AddressIn = Field(default_factory=AddressIn)
    bank_accounts: list[BankAccountIn] = Field(default_factory=list)
    salary: list[Form16SummaryIn] = Field(default_factory=list)
    other_income: OtherIncomeIn = Field(default_factory=OtherIncomeIn)
    foreign: ForeignIncomeIn = Field(default_factory=ForeignIncomeIn)
    challans: list[ChallanIn] = Field(default_factory=list)
    verification: dict[str, str] = Field(default_factory=dict)
    creation: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 4: Run + commit**

```bash
cd backend && uv run pytest tests/unit/test_itr_models.py -v
git add backend/app/schemas/itr_models.py backend/tests/unit/test_itr_models.py
git commit -m "feat(itr): typed per-year ReturnInput schemas"
```

---

### Task A5: `ItrService` — create / seed / get / list

**Files:**
- Create: `backend/app/services/itr_service.py`
- Create: `backend/tests/unit/test_itr_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_itr_service.py
import pytest
from app.services.itr_service import ItrService
from app.repositories.unit_of_work import UnitOfWork


@pytest.fixture
def svc(db):
    return ItrService(lambda: UnitOfWork(db))


def test_prepare_creates_return(svc, db):
    from tests.factories import make_member
    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    r = svc.prepare(member_id=m.id, fy_label="2025-26")
    assert r.ay_label == "2026-27"
    assert r.form_type == "ITR2"


def test_prepare_is_idempotent(svc, db):
    from tests.factories import make_member
    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    a = svc.prepare(member_id=m.id, fy_label="2025-26")
    b = svc.prepare(member_id=m.id, fy_label="2025-26")
    assert a.id == b.id


def test_prepare_seeds_from_previous_ay(svc, db):
    from tests.factories import make_member
    m = make_member(db, pan="ABCDE1234F", name="Dhiraj")
    prior = svc.prepare(member_id=m.id, fy_label="2024-25")
    svc.update_input(prior.id, {"address": {"city": "Pune"},
                                "bank_accounts": [{"bank_name": "HDFC", "account_number": "123"}]})
    nxt = svc.prepare(member_id=m.id, fy_label="2025-26")
    inp = svc.get_input(nxt.id)
    assert inp.address.city == "Pune"
    assert inp.bank_accounts[0].bank_name == "HDFC"
```

> `tests/factories.py` needs `make_member`. If absent, add it there (TDD: assert-first).

- [ ] **Step 2: Run to verify failure**, then **Step 3: implement** the service with `prepare`, `get`, `list_for_member`, `get_input`, `update_input`, and a private `_seed_from_previous_ay` that merges only the *fixed* blocks (address, bank accounts, creation/verification identity, foreign opening balances) — never prior-year income or gains.

Service takes `IUnitOfWorkFactory`; resolves `member_id` → member for PAN/name defaults; raises `ValidationError` (existing `app.middleware.error_handler`) for unknown member or bad FY.

- [ ] **Step 4: Run + commit**

```bash
cd backend && uv run pytest tests/unit/test_itr_service.py -v
git add backend/app/services/itr_service.py backend/tests/unit/test_itr_service.py backend/tests/factories.py
git commit -m "feat(itr): ItrService prepare/seed/input"
```

---

### Task A6: API router + dependency wiring

**Files:**
- Create: `backend/app/api/itr.py`
- Create: `backend/app/schemas/requests/itr.py`, `backend/app/schemas/responses/itr.py`
- Modify: `backend/app/api/dependencies.py` (`get_itr_service`)
- Modify: `backend/app/main.py` (register `itr_router`)
- Create: `backend/tests/integration/test_itr_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_itr_api.py
def test_list_returns_empty(client):
    m = client.post("/members", json={"pan": "ABCDE1234F", "name": "Dhiraj"}).json()
    resp = client.get(f"/itr/returns?member_id={m['id']}")
    assert resp.status_code == 200
    assert resp.json()["returns"] == []


def test_prepare_creates_and_lists(client):
    m = client.post("/members", json={"pan": "ABCDE1234F", "name": "Dhiraj"}).json()
    resp = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025-26"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["ay_label"] == "2026-27"
    assert body["form_type"] == "ITR2"


def test_prepare_rejects_bad_fy(client):
    m = client.post("/members", json={"pan": "ABCDE1234F", "name": "Dhiraj"}).json()
    resp = client.post("/itr/returns", json={"member_id": m["id"], "fy": "2025/26"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run to verify failure**, then **Step 3: implement** the routes from the spec §10 (`GET /itr/fiscal-years`, `GET /itr/returns`, `POST /itr/returns`, `GET /itr/returns/{id}`, `PUT /itr/returns/{id}/input`). Wire `get_itr_service` in `dependencies.py` and register the router in `main.py` with `prefix="/api"`.

- [ ] **Step 4: Run full suite (no regressions)**

```bash
cd backend && uv run pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/itr.py backend/app/api/dependencies.py backend/app/main.py backend/app/schemas backend/tests/integration/test_itr_api.py
git commit -m "feat(itr): HTTP surface for returns"
```

---

### Task A7: CLI `fintrack itr`

**Files:**
- Modify: `backend/cli.py` (`build_parser`, `main`, new `cmd_itr_*`)
- Create: `backend/tests/unit/test_cli_itr.py`

- [ ] **Step 1: Write the failing tests** (parser shape + dispatch, no network)

```python
# backend/tests/unit/test_cli_itr.py
from cli import build_parser


def test_parser_has_itr_subcommands():
    parser = build_parser()
    args = parser.parse_args(["itr", "prepare", "--pan", "ABCDE1234F", "--fy", "2025-26"])
    assert args.command == "itr" and args.pan == "ABCDE1234F" and args.fy == "2025-26"


def test_parser_itr_generate_out():
    args = build_parser().parse_args(
        ["itr", "generate", "--pan", "ABCDE1234F", "--fy", "2025-26", "--out", "itr.json"])
    assert args.out == "itr.json"
```

- [ ] **Step 2: Run to verify failure**, then **Step 3: implement** subcommands `prepare`, `list`, `form16` (phase B), `generate` (phase D) as thin `_api(...)` calls. Resolve `--pan` → `member_id` via `GET /members`.

- [ ] **Step 4: Run + commit**

```bash
cd backend && uv run pytest tests/unit/test_cli_itr.py -v
git add backend/cli.py backend/tests/unit/test_cli_itr.py
git commit -m "feat(itr): fintrack itr prepare/list"
```

**Milestone A acceptance:** a member can be prepared, an empty `ReturnInput` snapshot persisted, listed via API and CLI, and the full suite is green.

---

## Phase B — Form 16 parsing

### Task B1: Text-layer parser

**Files:**
- Create: `backend/app/engine/form16_parser.py`
- Create: `backend/tests/fixtures/form16_sample.txt`
- Create: `backend/tests/unit/test_form16_parser.py`

- [ ] **Step 1: Create the fixture** — a *synthetic* Form 16 text mirroring the Amazon layout (Part A identity, Part B salary lines). Never commit a real Form 16 (PAN/privacy). Include the labels observed in `~/Downloads/Form16_FY_2024_25.pdf`: employer name/address, "PAN of the Deductor", "TAN of the Deductor", employee name/PAN, "Gross Salary", "Standard deduction", "Taxable Income", "Total Tax Deducted".

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/unit/test_form16_parser.py
from pathlib import Path
from app.engine.form16_parser import parse_form16_text

FIX = Path(__file__).parent.parent / "fixtures" / "form16_sample.txt"


def test_parses_identity_and_salary():
    summary = parse_form16_text(FIX.read_text())
    assert summary.employer_tan == "ZZZZ00000Z"
    assert summary.employee_pan == "ABCDE1234F"
    assert summary.gross_salary == 2000000.0
    assert summary.tds == 250000.0


def test_missing_fields_are_warned_not_silently_zeroed():
    summary = parse_form16_text("employer name: ACME\n")
    assert summary.warnings                       # non-empty
    assert summary.gross_salary == 0.0


def test_parse_is_deterministic():
    text = FIX.read_text()
    assert parse_form16_text(text).model_dump() == parse_form16_text(text).model_dump()
```

- [ ] **Step 3: Run to verify failure**, then **Step 4: implement** a label/regex-driven parser returning `Form16SummaryIn` (from Task A4). Strip commas/₹, handle "0" vs blank, collect `warnings` for every unresolved label. No PDF import at this layer.

- [ ] **Step 5: Run + commit**

```bash
cd backend && uv run pytest tests/unit/test_form16_parser.py -v
git add backend/app/engine/form16_parser.py backend/tests/fixtures backend/tests/unit/test_form16_parser.py
git commit -m "feat(itr): deterministic Form 16 text parser"
```

---

### Task B2: PDF wrapper + synthetic-PDF test

**Files:**
- Modify: `backend/app/engine/form16_parser.py` (`parse_form16_pdf`)
- Create: `backend/tests/unit/test_form16_pdf.py`

- [ ] **Step 1: Write the failing test** — build a PDF from the fixture text with `fpdf2` (already a dependency), pass the bytes, assert the same summary as the text path.

```python
# backend/tests/unit/test_form16_pdf.py
from pathlib import Path
from fpdf import FPDF
from app.engine.form16_parser import parse_form16_pdf

FIX = Path(__file__).parent.parent / "fixtures" / "form16_sample.txt"


def _pdf_bytes(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in text.splitlines():
        pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_parse_pdf_matches_text_path():
    summary = parse_form16_pdf(_pdf_bytes(FIX.read_text()))
    assert summary.employer_tan == "ZZZZ00000Z"
    assert summary.gross_salary == 2000000.0
```

- [ ] **Step 2: Run to verify failure**, then **Step 3: implement** `parse_form16_pdf(file_bytes)` using `pdfplumber.open(io.BytesIO(...))`, joining page text (same approach as `app/importers/epf_pdf_importer.py:140`).

- [ ] **Step 4: Run + commit**

```bash
cd backend && uv run pytest tests/unit/test_form16_pdf.py -v
git add backend/app/engine/form16_parser.py backend/tests/unit/test_form16_pdf.py
git commit -m "feat(itr): Form 16 PDF extraction"
```

---

### Task B3: Upload endpoint → merge into `ReturnInput`

**Files:**
- Modify: `backend/app/api/itr.py` (`POST /itr/returns/{id}/form16`)
- Modify: `backend/app/services/itr_service.py` (`attach_form16`)
- Modify: `backend/tests/integration/test_itr_api.py`

- [ ] **Step 1: Write the failing test** — post the synthetic PDF (`files={"file": ("f16.pdf", bytes, "application/pdf")}`), assert 200, the parsed summary appears in the return input, and the response flags missing fields.

- [ ] **Step 2-4: Run → implement → run.** `attach_form16` parses and appends to `input.salary` (dedupe by employer TAN + period). Return the updated input + warnings.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(itr): Form 16 upload merges into return input"
```

**Milestone B acceptance:** upload the sample Form 16, see the parsed summary, correct anything flagged, persisted per PAN/AY, and next year's return seeds the identity/bank blocks.

---

## Phase C — Tax computation + 112A

### Task C1: Income buckets + new-regime computation

**Files:**
- Create: `backend/app/engine/itr/tax_compute.py`
- Create: `backend/tests/unit/test_itr_tax_compute.py`

- [ ] **Step 1: Write hand-derived failing tests** (rupee-exact; reuse `load_income_tax_config` for FY config)

```python
# backend/tests/unit/test_itr_tax_compute.py
from app.engine.itr.tax_compute import compute_return_tax, IncomeBuckets


def test_only_salary_new_regime_fy2025_26():
    tax = compute_return_tax(IncomeBuckets(salary=1_200_000), fy_label="2025-26", regime="new")
    # 75k std ded already applied upstream; 12L normal income → 60k tax; 87A nil (income > 12L)
    assert tax.total_tax_inr == 60_000 * 1.04  # + 4% cess approx, see impl note


def test_112a_exemption_and_rate():
    b = IncomeBuckets(ltcg_112a=300_000)
    tax = compute_return_tax(b, fy_label="2025-26", regime="new")
    assert tax.ltcg_112a_taxable == 175_000      # 3L - 1.25L
    assert tax.ltcg_112a_tax_inr == 175_000 * 0.125


def test_87a_rebate_does_not_apply_to_112a():
    b = IncomeBuckets(salary=200_000, ltcg_112a=300_000)
    tax = compute_return_tax(b, fy_label="2025-26", regime="new")
    assert tax.rebate_87a_inr == 0.0             # 112A is outside the rebate


def test_stcg_111a_rate():
    tax = compute_return_tax(IncomeBuckets(stcg_111a=100_000), fy_label="2025-26", regime="new")
    assert tax.stcg_111a_tax_inr == 100_000 * 0.20
```

> Exact expected values must be computed by hand from the FY YAML and locked in the test; the numbers above are illustrative — adjust to the true slab maths when implementing.

- [ ] **Step 2: Run to verify failure**, then **Step 3: implement**

```python
# backend/app/engine/itr/tax_compute.py
"""New-regime whole-return tax computation. Pure, no DB.

Composes engine.income_tax (slabs, surcharge, cess, 87A) with special rates:
  STCG 111A @ 20%, LTCG 112A @ 12.5% after the Rs 1.25L exemption.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.engine.income_tax import compute_income_tax, load_income_tax_config


@dataclass
class IncomeBuckets:
    salary: float = 0.0
    other_interest: float = 0.0
    dividends: float = 0.0
    stcg_slab: float = 0.0
    stcg_111a: float = 0.0
    ltcg_112a: float = 0.0
    ltcg_other_12_5: float = 0.0


@dataclass
class ItrTaxComputation:
    normal_income: float = 0.0
    ltcg_112a_taxable: float = 0.0
    stcg_111a_tax_inr: float = 0.0
    ltcg_112a_tax_inr: float = 0.0
    ltcg_other_tax_inr: float = 0.0
    normal_tax_inr: float = 0.0
    rebate_87a_inr: float = 0.0
    surcharge_inr: float = 0.0
    cess_inr: float = 0.0
    total_tax_inr: float = 0.0


def compute_return_tax(buckets: IncomeBuckets, fy_label: str, regime: str = "new") -> ItrTaxComputation:
    ...  # see spec §7
```

- [ ] **Step 4: Run + commit**

---

### Task C2: Rebate, marginal relief, surcharge cap, cess

**Files:** Modify `tax_compute.py`; extend `test_itr_tax_compute.py`.

Add cases: 87A at the threshold (FY 2025-26 ₹12L → ₹60k; FY 2024-25 ₹12.5k), marginal relief just above the threshold, surcharge ≥ ₹50L/₹1Cr with the 15% cap on 111A/112/112A income, 4% cess. All hand-derived from `app/config/tax_rates/{FY}.yaml`.

> **Config risk (spec §13.6):** verify `2024-25.yaml`'s `income_tax` block carries FY-2024-25 slabs/rebate, not FY-2025-26 values. Correct it here if wrong, with a test pinning both years.

- [ ] Commit: `fix(itr): FY-2024-25 income_tax config + rebate/surcharge coverage`

---

### Task C3: Schedule 112A scrip-wise builder

**Files:**
- Create: `backend/app/engine/itr/schedule_112a.py`
- Create: `backend/tests/unit/test_schedule_112a.py`

- [ ] **Step 1: Failing tests** — 112A column maths per CBDT rules v1.0 (rule 84–90):
  col6=col4×col5; col7=higher(col8, lower(col6, col11)); col9=lower(col6,col11) only
  when acquired ≤31-Jan-2018; col11=col4×col10; col13=col7+col12; col14=col6−col13;
  totals = sum of rows; cols 4,5,10,11 are 0 when acquired after 31-Jan-2018.

- [ ] **Step 2-4: Implement** over the existing lot engine (`app/engine/lot_engine.py`), emitting
  `Schedule112ARow(isin, scrip_name, qty, sale_value, cost, fmv_2018, gain, ...)`.

- [ ] Commit: `feat(itr): Schedule 112A scrip-wise builder`

---

### Task C4: ITR form selector

**Files:**
- Create: `backend/app/engine/itr/form_selector.py`
- Create: `backend/tests/unit/test_itr_form_selector.py`

- [ ] Failing tests for the spec §6 decision table (ITR-1 vs ITR-2), including foreign
  assets ⇒ ITR-2 and 112A LTCG > ₹1.25L ⇒ ITR-2. Implement `select_form(draft) -> (form, reasons)`.

- [ ] Commit: `feat(itr): ITR-1 vs ITR-2 selector`

---

### Task C5: `assemble` — draft from DB + input

**Files:**
- Create: `backend/app/services/itr_assembler.py`
- Modify: `backend/app/services/itr_service.py` (`assemble(return_id)`)
- Modify: `backend/app/api/itr.py` (`POST /itr/returns/{id}/assemble`)
- Create: `backend/tests/integration/test_itr_assemble.py`

- [ ] **Failing test:** seed a member + one Indian equity buy/sell + one FD + a `ReturnInput`
  with salary and savings interest; `POST .../assemble` returns a draft with populated
  `stcg_111a`, `ltcg_112a`, `other_interest`, and a tax computation; `draft_json` persisted.

- [ ] **Implement** by composing `TaxService.get_tax_summary` (gains) + FD/RD interest + the
  `ReturnInput` (salary, savings interest, dividends, foreign) into `IncomeBuckets`, then
  `compute_return_tax` + `schedule_112a` + `select_form`. Idempotent per AY.

- [ ] Commit: `feat(itr): assemble return draft from portfolio + inputs`

**Milestone C acceptance:** `assemble` yields a full draft (income buckets, gains, 112A rows, tax, form choice) for any member — with or without a Form 16.

---

## Phase D — ITR-2 JSON for AY 2026-27

### Task D1: Bundle the official schema + loader

**Files:**
- Create: `backend/app/config/itr_schemas/AY2026-27/ITR-2_2026_Main_V1.2.json` (the CBDT V1.2 schema, released 13-Aug-2026; already downloaded — bundle **once**, offline thereafter)
- Reference (record, not bundle): `ITR 2_Schema change document_AY2026-27_V1.2.pdf`, `CBDT__e-Filing_ITR 2_Validation Rules_AY 2026-27_V1.0.pdf`
- Create: `backend/app/engine/itr/schema_loader.py`
- Create: `backend/tests/unit/test_schema_loader.py`
- Modify: `backend/pyproject.toml` (add `jsonschema>=4.0`), run `uv lock`/`uv sync`

- [x] Write failing tests: loader resolves the AY's schema path; raises a clear error when
  absent (never emit unvalidated output); exposes the pinned version string. Implement.
  Commit: `feat(itr): bundle AY 2026-27 ITR-2 schema + loader`. **(done — `85a42d9`)**

### Task D2: Schema + semantic validation

**Files:**
- Create: `backend/app/engine/itr/schema_validation.py`
- Create: `backend/tests/unit/test_schema_validation.py`

- [x] Failing tests: a known-good minimal JSON passes; a camelCase-keyed HP block fails;
  a schedule with a total but no itemised rows fails the **semantic** audit; a Table-F/BFLA
  mismatch fails; a **CG B3a ≠ 112A col-14 total** fails (rule 134); a **CFL↔BFLA
  tie** break fails (rules 234/235); `ScheduleFA` absent while
  `AssetOutIndiaFlag=YES` fails (rule 746). Implement
  `validate_itr_json(doc, ay) -> ValidationReport` using `jsonschema.Draft4Validator` +
  the §8.4/§8.6 rules. Commit. **(done after D3/D4 — the "known-good JSON" test needed the
  builder first. Rules encoded: schema, itemised-rows audit, 134, 234/235, 746.)**

### Task D3: `Itr2BuilderAY2026` — metadata, personal, salary, OS

**Files:**
- Create: `backend/app/engine/itr/builders/__init__.py`, `base.py`, `common.py`, `itr2_ay2026.py`
- Create: `backend/tests/unit/test_itr2_builder_ay2026.py`

- [x] Failing tests: registry resolves `(ITR2, "2026-27")`; built doc has
  `{"ITR": {"ITR2": {...}}}` with `CreationInfo`, `Form_ITR2`, `PartA_GEN1.PersonalInfo`,
  `ScheduleS`, `ScheduleOS` populated and **schema-valid**; `Form_ITR2` carries
  `FormName="ITR-2"`, `AssessmentYear="2026"`, `SchemaVer="Ver1.0"`, `FormVer="Ver1.0"`;
  `CreationInfo` carries a pattern-valid `SWCreatedBy` (`SW\d{8}` placeholder) and
  `JSONCreationDate` ≥ 2026-04-01; `Verification.Declaration` has name/father/PAN when
  known. Implement by overlaying the `ReturnInput` + draft onto a full skeleton of
  required 0s (never totals-only). Commit. **(done — `b368773`; skeleton is auto-derived
  from the bundled schema in `builders/common.py`, so a schema revision cannot silently
  drop a required field.)**

### Task D4: `Itr2BuilderAY2026` — CG, 112A, SI, TI, TTI, CFL

**Files:** Modify `itr2_ay2026.py`, `common.py`; extend `test_itr2_builder_ay2026.py`.

- [x] Failing tests: `ScheduleCGFor23` itemised (not totals-only) with STCG 111A / STCG slab /
  LTCG 112A / LTCG other split; `Schedule112A` rows sum and **CG B3a = 112A col-14 total**;
  `ScheduleSI` carries the special-rate income; `PartB-TI` carries gross gains (exemption
  only in SI); `PartB_TTI` recomputes to the same total as `tax_compute`; Table F quarters
  tie to **both BFLA (3iv/3v/3vi/3viii) and `ScheduleSI` Sl. No. 7**. Implement, then
  assert the whole doc validates against the bundled schema. Commit. **(done for the core
  schedules. Deviations: (1) the draft now also carries a `gross` block (assembler change
  in this task) because `PartB-TI.CapGain` must show gains *before* set-off; (2) **Table F
  quarterly** breakup is deferred — the AY 2026-27 `ScheduleCGFor23` exposes
  `AccruOrRecOfCG` (accrual vs receipt), not the paper form's quarterly Table F, so
  `ScheduleCYLA`/`ScheduleBFLA` stay at their required-only skeleton and quarterly tie-outs
  are out of scope until Phase E. `ScheduleCFL` carry-forward is populated.)**

### Task D5: `generate` endpoint + download + report

**Files:**
- Create: `backend/app/services/itr_json_service.py`
- Modify: `backend/app/api/itr.py` (`POST .../generate`, `GET .../json`, `GET .../validation`)
- Modify: `backend/app/services/itr_service.py`
- Modify: `backend/cli.py` (`cmd_itr_generate`)
- Create: `backend/tests/integration/test_itr_generate.py`

- [x] Failing tests: after assemble, `POST .../generate` validates, persists `output_json` +
  `schema_version` + `status="generated"`; `GET .../json` downloads it; validation failure
  ⇒ 422 with the error paths and **no** output written; CLI `generate --out` writes the file.
  Implement. Commit: `feat(itr): generate + validate + download ITR-2 JSON`. **(done.
  `GET .../validation` was also added — it reports the report without persisting.)**

### Task D6: Golden end-to-end

**Files:**
- Create: `backend/tests/integration/test_itr_end_to_end.py`
- Create: `backend/tests/fixtures/itr_golden_portfolio.py`

- [ ] One test: seed a member with Indian equity (STCG+112A LTCG), a US stock sale, an FD,
  a synthetic Form 16, and savings interest → prepare → assemble → generate → assert the
  output validates against the official schema and key schedules equal hand-derived values.
  Commit: `test(itr): golden end-to-end AY 2026-27`.

**Milestone 1 (A–D) acceptance:** upload a Form 16, assemble from the portfolio, generate a
schema-valid ITR-2 JSON that imports into the Common Offline Utility, with a clear
"import, don't direct-upload" message.

---

## Phase E — Loss carry-forward & multi-year (outline)

- **E1** Extend `tax_loss_carryforwards` → ITR-2 `ScheduleCFL` shape (categories, all columns);
  TDD the set-off order (STCL→STCG→LTCG, LTCL→LTCG) against hand cases.
- **E2** `seed_from_previous_ay` extends to opening balances + prior carry-forwards; write-back
  of the current year's unabsorbed loss at generate time (idempotent per AY).
- **E3** `Itr2BuilderAY2025` (AY 2025-26) + bundle that schema; parametrise the builder tests
  across AYs.

## Phase F — Foreign assets & income (outline)

- **F1** `ScheduleFA` from `STOCK_US` transactions over the **calendar year**, with manual
  opening/peak/closing overrides; country codes read from the schema (never ISO-guessed).
- **F2** `ScheduleFSI` + foreign tax credit (Form 67 metadata); US dividends → `ScheduleOS`/FSI.
- **F3** Rule 115 SBI TTBR rate table + conversion; document the app's monthly rate as fallback.

## Phase G — Old regime, ITR-1, UI (outline)

- **G1** Old-regime config + Chapter VI-A + old 87A; side-by-side comparison.
- **G2** `Itr1Builder` for eligible simple returns.
- **G3** `frontend/app/itr/page.tsx` + `lib/api.ts` + types: prepare, upload Form 16, review
  warnings, assemble, generate, download; masked PAN.
- **G4** Docs (`CLAUDE.md`, `CONTEXT.md`, `docs/taxation_rules.md`) + the "offline utility"
  caveat stated wherever output is offered.

---

## Testing & verification rules

- Every task is **test-first**: write the failing test, run it, implement, run green, commit.
- Run `cd backend && uv run pytest -q` before each commit; keep the suite green.
- **Never** commit a real Form 16, PAN, Aadhaar, or account number. Fixtures are synthetic.
- Builders **refuse** to emit JSON when the official schema is missing or validation fails.
- Output copy always reads: *import into the Common Offline Utility* — not "upload to the portal".
- Coverage targets: `engine/itr` ≥ 90%, `form16_parser` ≥ 85% (repo convention).
