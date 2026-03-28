# Backend Refactoring Design

**Date:** 2026-03-27
**Scope:** Backend only (`backend/app/`). Frontend untouched.
**Strategy:** Incremental, layer-by-layer. All existing tests remain green after each phase.

---

## Goals

1. Standardise importer parsers so adding a new provider (Groww, Morgan Stanley) or format variant (CAS CSV) is a file drop-in with no changes to existing code.
2. Apply the Strategy pattern to the Returns service — one leaf class per asset type, extending a shared base, overriding only what differs.
3. Improve the Price service — self-registering fetchers, staleness policy declared on the fetcher class.
4. Decompose the Import service — separate generic pipeline from asset-type-specific post-processing.
5. Replace all `dict` returns from services with typed Pydantic response models.
6. Apply Dependency Injection everywhere — services declare abstract dependency types, never instantiate them; all wiring lives in one place.
7. Introduce a Unit of Work pattern for atomic multi-step writes.
8. Formalise post-import triggers as an event/observer system.
9. Clean up the API layer — no direct repository access from routes.
10. Make the tax rate engine data-driven — per-FY YAML config files, zero code changes to add a new year.

---

## Principles

- **SOLID throughout.** Single responsibility, open/closed (extend by adding, not editing), Liskov (subclasses are substitutable), interface segregation (small focused protocols), dependency inversion (depend on abstractions).
- **Incremental migration.** Each phase leaves tests green. No big-bang rewrite.
- **DI everywhere.** Classes declare abstract dependencies in `__init__`. Callers wire concrete implementations. All wiring lives in `api/dependencies.py`.
- **Engine stays pure.** Engine functions are pure math — no DB params, no side effects. Asset-type-specific parameters (ST/LT thresholds) move from hardcoded dicts inside the engine to parameters supplied by the strategy layer.
- **TDD mandatory.** Write failing test first, then implementation. Coverage targets from `CLAUDE.md` apply throughout.

---

## Architecture Overview

```
api/
  routes/        ← HTTP only: parse request → call service → return response model
  dependencies.py ← ALL wiring: concrete repo/strategy/policy instances injected here

services/
  returns/
    strategies/
      base.py
      market_based.py
      valuation_based.py
      asset_types/
        stock_in.py, stock_us.py, rsu.py, mf.py, nps.py, gold.py, sgb.py
        fd.py, rd.py, ppf.py, real_estate.py, epf.py
    returns_service.py  ← thin coordinator; receives IReturnsStrategyRegistry
  imports/
    orchestrator.py     ← preview/commit coordinator
    preview_store.py    ← TTL store (extracted)
    deduplicator.py     ← txn_id dedup (pure, testable)
    post_processors/
      base.py
      stock.py, corp_actions.py, mf.py
  price_service.py      ← receives IPriceFetcherRegistry
  tax_service.py        ← receives TaxRatePolicy
  snapshot_service.py
  deposits_service.py

repositories/
  interfaces.py         ← Protocol definitions for all repos
  unit_of_work.py       ← UnitOfWork context manager
  asset_repo.py, transaction_repo.py, ...  ← drop internal db.commit()

importers/
  base.py               ← BaseImporter ABC + ParsedTransaction/ImportResult
  registry.py           ← @register_importer decorator + ImporterRegistry
  pipeline.py           ← ImportPipeline: parse → validate → deduplicate
  stocks/
    zerodha_csv.py
  mutual_funds/
    cas_pdf.py
  fixed_income/
    ppf_csv.py, epf_pdf.py
  us_stocks/
    fidelity_pdf.py, fidelity_rsu_csv.py
  nps/
    nps_csv.py

engine/
  lot_engine.py         ← stcg_days as parameter (not hardcoded dict)
  tax_engine.py         ← TaxRatePolicy class + TaxRate dataclass
  returns.py, fd_engine.py, ppf_epf_engine.py, allocation.py, mf_classifier.py

config/
  tax_rates/
    2024-25.yaml
    2025-26.yaml        ← adding new FY = drop file here, zero code changes

schemas/
  requests/             ← (existing, unchanged)
  responses/
    returns.py, tax.py, imports.py, prices.py, common.py
```

---

## Section 1: Typed Response Objects

### Problem
All services return raw `dict`. There is no enforced contract between service output and API response. Rename refactors silently break things; `mypy` cannot catch mismatches.

### Design
Introduce `schemas/responses/` with Pydantic models for every service's public output. Services annotate return types. FastAPI serialises the models directly.

```python
# schemas/responses/returns.py
class LotResponse(BaseModel):
    lot_id: str
    buy_date: date
    units: float
    buy_price_per_unit: float
    current_price: float
    holding_days: int
    is_short_term: bool
    unrealised_gain: float
    unrealised_gain_pct: float

class AssetReturnsResponse(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    invested: float | None
    current_value: float | None
    current_pnl: float | None
    current_pnl_pct: float | None
    alltime_pnl: float | None
    xirr: float | None
    cagr: float | None
    is_active: bool

# schemas/responses/common.py
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
```

`MoneyMixin` paise↔INR conversion is applied in the response model validators, not scattered in service code.

### Files Changed
- **New:** `schemas/responses/returns.py`, `tax.py`, `imports.py`, `prices.py`, `common.py`
- **Updated:** All service method signatures to declare return types
- **Updated:** API routes to return response models (not bare dicts)

---

## Section 2: Repository Interfaces + Unit of Work

### Problem
Services receive a raw `Session` and instantiate repositories internally — the concrete repo type is hardcoded. Every `repo.create()` calls `db.commit()` immediately, making multi-step imports non-atomic. A failure halfway through leaves partial data.

### Repository Interfaces

```python
# repositories/interfaces.py
class IAssetRepository(Protocol):
    def get_by_id(self, id: int) -> Asset | None: ...
    def list(self, asset_type=None, active=None) -> list[Asset]: ...
    def create(self, **kwargs) -> Asset: ...
    def update(self, asset: Asset, **kwargs) -> Asset: ...

class ITransactionRepository(Protocol):
    def get_by_txn_id(self, txn_id: str) -> Transaction | None: ...
    def create(self, **kwargs) -> Transaction: ...
    def list_by_asset(self, asset_id: int) -> list[Transaction]: ...

# ... IValuationRepository, IPriceCacheRepository, IFDRepository, etc.
```

All existing repository classes implement these protocols (duck-typing — no code change needed in the repos themselves, just add the interface file).

### Unit of Work

```python
# repositories/unit_of_work.py
class UnitOfWork:
    def __init__(self, session: Session):
        self.session = session
        self.assets: IAssetRepository = SQLAlchemyAssetRepository(session)
        self.transactions: ITransactionRepository = SQLAlchemyTransactionRepository(session)
        self.valuations: IValuationRepository = SQLAlchemyValuationRepository(session)
        self.price_cache: IPriceCacheRepository = SQLAlchemyPriceCacheRepository(session)
        self.fd: IFDRepository = SQLAlchemyFDRepository(session)
        # ... all repos

    def __enter__(self) -> "UnitOfWork":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.session.rollback()
        else:
            self.session.commit()

class IUnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
```

Services receive `IUnitOfWorkFactory` via DI. They call `with self._uow_factory() as uow:` — all writes within the block commit atomically or roll back entirely.

### Repository Changes
Each repository drops its internal `db.commit()` call. Commit is the UoW's responsibility.

### Wiring
```python
# api/dependencies.py
def get_uow_factory(db: Session = Depends(get_db)) -> IUnitOfWorkFactory:
    return lambda: UnitOfWork(db)
```

---

## Section 3: Dependency Injection Pattern

### Problem
Services are instantiated inline in route functions, hard-coding their concrete dependencies. Swapping an implementation (e.g., for testing or a future data-source change) requires editing service internals.

### Design
Every service declares all dependencies as abstract types in `__init__`. No service instantiates anything. All concrete wiring lives in `api/dependencies.py`.

```python
# Example: ReturnsService
class ReturnsService:
    def __init__(
        self,
        uow_factory: IUnitOfWorkFactory,
        strategy_registry: IReturnsStrategyRegistry,
    ):
        self._uow_factory = uow_factory
        self._strategy_registry = strategy_registry

    def get_asset_returns(self, asset_id: int) -> AssetReturnsResponse:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            strategy = self._strategy_registry.get(asset.asset_type)
            return strategy.compute(asset, uow)
```

```python
# api/dependencies.py  ← the only place concrete types appear
def get_returns_service(db: Session = Depends(get_db)) -> ReturnsService:
    return ReturnsService(
        uow_factory=lambda: UnitOfWork(db),
        strategy_registry=DefaultReturnsStrategyRegistry(),
    )

def get_tax_service(db: Session = Depends(get_db)) -> TaxService:
    return TaxService(
        uow_factory=lambda: UnitOfWork(db),
        tax_rate_policy=TaxRatePolicy(Path("config/tax_rates")),
        returns_service=get_returns_service(db),
    )
```

**Testing:** inject fakes directly — no `monkeypatch`, no `dependency_overrides`:
```python
service = ReturnsService(
    uow_factory=lambda: FakeUnitOfWork(assets=[sample_asset]),
    strategy_registry=FakeStrategyRegistry(returns=mock_response),
)
```

### Rule
No service file may contain the word `Session` except through `UnitOfWork`. No service file may import a concrete repository class.

---

## Section 4: Importer Standardisation

### Problem
Parsers are loosely coupled to a Protocol but don't formally extend a base class. The API layer manually instantiates the right parser inline — adding Groww or Morgan Stanley means editing `api/imports.py`. There is no common validation or pipeline step.

### BaseImporter ABC

```python
# importers/base.py
class BaseImporter(ABC):
    source: ClassVar[str]        # "zerodha", "cas", "groww"
    asset_type: ClassVar[AssetType]
    format: ClassVar[str]        # "csv", "pdf"

    @abstractmethod
    def parse(self, file_bytes: bytes) -> ImportResult: ...

    def validate(self, result: ImportResult) -> list[str]:
        """Optional validation hook. Default: no-op."""
        return []
```

### Registry + Decorator

```python
# importers/registry.py
_REGISTRY: dict[tuple[str, str], type[BaseImporter]] = {}

def register_importer(cls: type[BaseImporter]) -> type[BaseImporter]:
    _REGISTRY[(cls.source, cls.format)] = cls
    return cls

class ImporterRegistry:
    def get(self, source: str, fmt: str) -> BaseImporter:
        cls = _REGISTRY.get((source, fmt))
        if not cls:
            raise ValueError(f"No importer for source={source} format={fmt}")
        return cls()
```

### Import Pipeline

```python
# importers/pipeline.py
class ImportPipeline:
    def __init__(self, registry: ImporterRegistry, deduplicator: IDeduplicator):
        self._registry = registry
        self._deduplicator = deduplicator

    def run(self, source: str, fmt: str, file_bytes: bytes) -> ImportResult:
        importer = self._registry.get(source, fmt)
        result = importer.parse(file_bytes)
        warnings = importer.validate(result)
        result.warnings.extend(warnings)
        result = self._deduplicator.filter_duplicates(result)
        return result
```

### Directory Structure

```
importers/
├── base.py
├── registry.py
├── pipeline.py
├── stocks/
│   └── zerodha_csv.py        # @register_importer; source="zerodha", format="csv"
├── mutual_funds/
│   └── cas_pdf.py            # @register_importer; source="cas", format="pdf"
├── fixed_income/
│   ├── ppf_csv.py
│   └── epf_pdf.py
├── us_stocks/
│   ├── fidelity_pdf.py
│   └── fidelity_rsu_csv.py
└── nps/
    └── nps_csv.py
```

Adding Groww: create `importers/stocks/groww_csv.py` with `@register_importer`. Done. No other files change.

Adding CAS CSV variant: create `importers/mutual_funds/cas_csv.py`. Done.

---

## Section 5: Returns Service → Strategy Pattern

### Problem
`returns_service.py` is 975 LOC with `if asset_type == "MF": ... elif ...` branches throughout. Every asset-type change requires working in the same large file.

### AssetReturnsStrategy ABC (Template Method)

```python
# services/returns/strategies/base.py
class AssetReturnsStrategy(ABC):
    """Template method: orchestrates computation. Subclasses override hooks."""

    def compute(self, asset: Asset, uow: UnitOfWork) -> AssetReturnsResponse:
        invested = self.get_invested_value(asset, uow)
        current = self.get_current_value(asset, uow)
        cashflows = self.build_cashflows(asset, uow)
        xirr = compute_xirr(cashflows)
        pnl = (current - invested) if (current and invested) else None
        return AssetReturnsResponse(
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset.asset_type.value,
            invested=invested,
            current_value=current,
            current_pnl=pnl,
            xirr=xirr,
            is_active=asset.is_active,
        )

    def get_invested_value(self, asset: Asset, uow: UnitOfWork) -> float | None:
        """Default: sum of outflow transaction amounts."""
        txns = uow.transactions.list_by_asset(asset.id)
        return sum(abs(t.amount_inr / 100) for t in txns if t.type in OUTFLOW_TYPES)

    @abstractmethod
    def get_current_value(self, asset: Asset, uow: UnitOfWork) -> float | None: ...

    def build_cashflows(self, asset: Asset, uow: UnitOfWork) -> list[tuple[date, float]]:
        """Default: standard inflow/outflow cashflow building for XIRR."""
        txns = uow.transactions.list_by_asset(asset.id)
        return _build_cashflows(txns)  # extracted pure function

    def compute_lots(self, asset: Asset, uow: UnitOfWork) -> list[LotResponse]:
        """Default: lots not supported. Override in MarketBasedStrategy."""
        return []
```

### Strategy Hierarchy

```
AssetReturnsStrategy (ABC)
├── MarketBasedStrategy          get_current_value = units × price_cache_nav
│   │                            compute_lots = lot_engine FIFO
│   │                            stcg_days: ClassVar[int]  ← subclass declares
│   ├── StockINStrategy          stcg_days = 365  (no other overrides)
│   ├── NPSStrategy              stcg_days = 365  (no overrides)
│   ├── GoldStrategy             stcg_days = 1095 (no overrides)
│   ├── StockUSStrategy          stcg_days = 730
│   │                            override get_invested_value() → USD→INR at vest
│   ├── RSUStrategy              stcg_days = 730
│   │                            override build_cashflows() → VEST unit calc
│   ├── MFStrategy               stcg_days = 365
│   │                            override get_current_value() → CAS snapshot first
│   └── SGBStrategy              stcg_days = 1095
│                                override get_current_value() → maturity tax-free check
└── ValuationBasedStrategy       get_current_value = latest Valuation entry
    ├── PPFStrategy              (no overrides)
    ├── RealEstateStrategy       (no overrides)
    ├── FDStrategy               override get_current_value() → fd_engine formula
    ├── RDStrategy               override get_current_value() → rd formula
    │                            override get_invested_value() → sum monthly installments
    └── EPFStrategy              override get_invested_value() → sum CONTRIBUTION outflows
                                 override get_current_value() → invested + INTEREST inflows
```

Leaf classes that need no overrides are 3-line files:
```python
# services/returns/strategies/asset_types/stock_in.py
@register_strategy(AssetType.STOCK_IN)
class StockINStrategy(MarketBasedStrategy):
    stcg_days: ClassVar[int] = 365
```

### Registry

```python
# services/returns/strategies/registry.py
class IReturnsStrategyRegistry(Protocol):
    def get(self, asset_type: AssetType) -> AssetReturnsStrategy: ...

class DefaultReturnsStrategyRegistry(IReturnsStrategyRegistry):
    def __init__(self):
        self._map = {at: cls() for at, cls in _STRATEGY_REGISTRY.items()}

    def get(self, asset_type: AssetType) -> AssetReturnsStrategy:
        strategy = self._map.get(asset_type)
        if not strategy:
            raise ValueError(f"No returns strategy for {asset_type}")
        return strategy
```

### Thin ReturnsService

```python
# services/returns/returns_service.py
class ReturnsService:
    def __init__(
        self,
        uow_factory: IUnitOfWorkFactory,
        strategy_registry: IReturnsStrategyRegistry,
    ):
        self._uow_factory = uow_factory
        self._registry = strategy_registry

    def get_asset_returns(self, asset_id: int) -> AssetReturnsResponse:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            if not asset:
                raise NotFoundError(f"Asset {asset_id} not found")
            return self._registry.get(asset.asset_type).compute(asset, uow)

    def get_asset_lots(self, asset_id: int, page: int, size: int) -> PaginatedResponse[LotResponse]:
        with self._uow_factory() as uow:
            asset = uow.assets.get_by_id(asset_id)
            strategy = self._registry.get(asset.asset_type)
            lots = strategy.compute_lots(asset, uow)
            return paginate(lots, page, size)
```

---

## Section 6: Price Service → Improved Strategy

### Problem
`FETCHER_REGISTRY` is a hardcoded dict in `price_feed.py`. Staleness thresholds (1 day for MF, 6 hours for stocks) are scattered in service logic rather than declared on the fetcher.

### Design

```python
# services/price_feed.py
class BasePriceFetcher(ABC):
    asset_types: ClassVar[list[AssetType]]
    staleness_threshold: ClassVar[timedelta]

    @abstractmethod
    def fetch(self, asset: Asset) -> PriceResult | None: ...

_FETCHER_REGISTRY: dict[AssetType, type[BasePriceFetcher]] = {}

def register_fetcher(cls: type[BasePriceFetcher]) -> type[BasePriceFetcher]:
    for at in cls.asset_types:
        _FETCHER_REGISTRY[at] = cls
    return cls

@register_fetcher
class MFAPIFetcher(BasePriceFetcher):
    asset_types = [AssetType.MF]
    staleness_threshold = timedelta(days=1)

    def fetch(self, asset: Asset) -> PriceResult | None: ...

@register_fetcher
class YFinanceStockFetcher(BasePriceFetcher):
    asset_types = [AssetType.STOCK_IN, AssetType.STOCK_US, AssetType.RSU, AssetType.GOLD, AssetType.SGB]
    staleness_threshold = timedelta(hours=6)

    def fetch(self, asset: Asset) -> PriceResult | None: ...

@register_fetcher
class NPSNavFetcher(BasePriceFetcher):
    asset_types = [AssetType.NPS]
    staleness_threshold = timedelta(days=1)

    def fetch(self, asset: Asset) -> PriceResult | None: ...
```

`PriceService` reads `staleness_threshold` from the fetcher class — no hardcoded per-type logic in the service. Adding a new price source = new `@register_fetcher` class. No edits to existing files.

---

## Section 7: Import Service Decomposition

### Problem
`import_service.py` mixes generic pipeline logic (preview store, deduplication) with asset-type-specific post-processing (mark stocks inactive, trigger corp actions, persist CAS snapshots). Corp actions are triggered with a direct inline call — tight coupling.

### Design

```python
# services/imports/post_processors/base.py
class IPostProcessor(Protocol):
    asset_types: ClassVar[list[AssetType]]
    def process(self, asset: Asset, txns: list[Transaction], uow: UnitOfWork) -> None: ...

# services/imports/post_processors/stock.py
class StockPostProcessor(IPostProcessor):
    asset_types = [AssetType.STOCK_IN, AssetType.STOCK_US, AssetType.RSU]

    def process(self, asset, txns, uow):
        net_units = sum_net_units(txns)
        if net_units <= 0:
            uow.assets.update(asset, is_active=False)

# services/imports/post_processors/mf.py
class MFPostProcessor(IPostProcessor):
    asset_types = [AssetType.MF]

    def process(self, asset, txns, uow):
        # persist CAS snapshots
        ...
```

```python
# services/imports/orchestrator.py
class ImportOrchestrator:
    def __init__(
        self,
        uow_factory: IUnitOfWorkFactory,
        pipeline: ImportPipeline,
        preview_store: PreviewStore,
        post_processors: list[IPostProcessor],
        event_bus: IEventBus,
    ):
        self._uow_factory = uow_factory
        self._pipeline = pipeline
        self._preview_store = preview_store
        self._processors = {at: p for p in post_processors for at in p.asset_types}
        self._bus = event_bus

    def preview(self, source: str, fmt: str, file_bytes: bytes) -> ImportPreviewResponse:
        result = self._pipeline.run(source, fmt, file_bytes)
        preview_id = self._preview_store.put(result)
        return ImportPreviewResponse(preview_id=preview_id, ...)

    def commit(self, preview_id: str) -> ImportCommitResponse:
        result = self._preview_store.get(preview_id)  # raises if expired
        with self._uow_factory() as uow:
            for parsed_asset, parsed_txns in result.grouped_by_asset():
                asset = uow.assets.find_or_create(parsed_asset)
                txns = [uow.transactions.create(**t) for t in parsed_txns]
                if processor := self._processors.get(asset.asset_type):
                    processor.process(asset, txns, uow)
            # UoW commits here — all or nothing
        self._bus.publish(ImportCompletedEvent(...))
        return ImportCommitResponse(...)
```

Adding a new post-processing behaviour (e.g., auto-refresh prices after import) = add a new `IPostProcessor` class and register it in `api/dependencies.py`. No edits to `ImportOrchestrator`.

---

## Section 8: Post-Import Event System

### Problem
Corp actions processing is triggered inline inside the import commit path. Decoupling is needed as the import service is decomposed.

### Design

Lightweight synchronous event bus — no external dependencies.

```python
# services/event_bus.py
@dataclass
class ImportCompletedEvent:
    asset_id: int
    asset_type: AssetType
    inserted_count: int

class IEventBus(Protocol):
    def publish(self, event: object) -> None: ...
    def subscribe(self, event_type: type, handler: Callable) -> None: ...

class SyncEventBus(IEventBus):
    def __init__(self):
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type, handler):
        self._handlers[event_type].append(handler)

    def publish(self, event):
        for handler in self._handlers.get(type(event), []):
            handler(event)
```

Registration at startup:
```python
# api/dependencies.py
def build_event_bus(corp_actions_service: CorpActionsService) -> IEventBus:
    bus = SyncEventBus()
    bus.subscribe(ImportCompletedEvent, corp_actions_service.on_import_completed)
    return bus
```

Future observers (auto-price-refresh, Slack notification, snapshot trigger) are additive — subscribe more handlers. `ImportOrchestrator` only knows about `IEventBus`, not any concrete handler.

---

## Section 9: API Layer Cleanup

### Problem
Some API routes call repositories directly (e.g., `assets.py` calls `AssetRepository.create()` without a service). Routes should only parse requests and call services.

### Rule
Every route function body must have this shape:
```python
@router.post("/assets", response_model=AssetResponse)
def create_asset(
    body: AssetCreateRequest,
    service: AssetService = Depends(get_asset_service),
):
    return service.create(body)
```

No `db: Session` in route functions. No repository imports in `api/` files. All data flows through a service method.

### Changes
- `api/assets.py` → all CRUD via `AssetService`
- `api/valuations.py` → via `ValuationService`
- `api/transactions.py` → via `TransactionService`
- `api/goals.py` → via `GoalService`
- All other routes already call services — verify and adjust as needed.

---

## Section 10: Engine Improvements

### lot_engine.py — Remove asset-type coupling

**Current:** `_STCG_DAYS = {AssetType.STOCK_IN: 365, ...}` hardcoded in the engine. Adding a new asset type means editing the engine.

**Fix:** Engine functions accept `stcg_days` as a parameter. Each returns strategy subclass declares its own threshold and passes it to the engine.

```python
# engine/lot_engine.py (after)
def compute_lot_unrealised(
    lot: LotLike,
    current_price: float,
    stcg_days: int,          # ← parameter, not looked up internally
    grandfathering_cutoff: date | None,  # ← parameter
    as_of: date,
) -> dict: ...

def match_lots_fifo(
    lots: list[LotLike],
    sells: list[SellLike],
    stcg_days: int,
) -> list[dict]: ...
```

`MarketBasedStrategy` has `stcg_days: ClassVar[int]` and passes it when calling the engine. The engine has zero asset-type knowledge.

### tax_engine.py — TaxRatePolicy + config-driven rates

**Current:** `get_tax_rate(asset_type, is_short_term)` is a flat conditional function.

**Fix:** `TaxRatePolicy` class reads per-FY YAML files. `TaxRate` dataclass returned.

```python
# engine/tax_engine.py
@dataclass
class TaxRate:
    stcg_rate_pct: float | None   # None = slab rate
    stcg_is_slab: bool
    ltcg_rate_pct: float | None
    ltcg_is_slab: bool
    ltcg_threshold_days: int | None
    ltcg_exemption_inr: float
    is_exempt: bool
    maturity_exempt: bool = False  # SGB

class TaxRatePolicy:
    def __init__(self, config_dir: Path):
        self._config_dir = config_dir
        self._cache: dict[str, dict] = {}

    def get_rate(self, fy: str, asset_type: AssetType) -> TaxRate:
        if fy not in self._cache:
            path = self._config_dir / f"{fy}.yaml"
            if not path.exists():
                raise ValueError(f"No tax rate config for FY {fy}: {path}")
            with open(path) as f:
                self._cache[fy] = yaml.safe_load(f)
        raw = self._cache[fy].get(asset_type.value)
        if not raw:
            raise ValueError(f"No tax rate for {asset_type} in FY {fy}")
        return TaxRate(**raw)
```

Config directory:
```
config/tax_rates/
├── 2024-25.yaml
└── 2025-26.yaml    ← new year = drop file here
```

`TaxService` receives `TaxRatePolicy` via DI. No hardcoded rate conditionals anywhere in the service or engine.

### mf_classifier.py — ISchemeClassifier protocol

Low-cost future-proofing. Wrap the existing function in a class implementing a protocol:

```python
class ISchemeClassifier(Protocol):
    def classify(self, scheme_category: str) -> AssetClass: ...

class DefaultSchemeClassifier(ISchemeClassifier):
    def classify(self, scheme_category: str) -> AssetClass:
        # existing logic
        if "Debt" in scheme_category:
            return AssetClass.DEBT
        return AssetClass.EQUITY
```

Injected into `MFStrategy` and `ImportOrchestrator` — swappable without touching callers.

---

## What Stays Unchanged

| Component | Reason |
|---|---|
| `engine/returns.py` | Pure XIRR/CAGR functions, no asset-type branching |
| `engine/fd_engine.py` | Pure math, no coupling |
| `engine/ppf_epf_engine.py` | Pure rate lookup, no coupling |
| `engine/allocation.py` | Pure aggregation, no coupling |
| `models/` | ORM models are stable |
| `middleware/` | Error handling is clean |
| Frontend | Out of scope |

---

## Testing Strategy

- **Unit tests:** Each strategy class tested in isolation with `FakeUnitOfWork`. Engine functions tested with direct parameter calls — no DB, no HTTP.
- **Integration tests:** `ImportOrchestrator.commit()` tested against in-memory SQLite with real UoW. Each post-processor tested separately.
- **Registry tests:** `ImporterRegistry` and `DefaultReturnsStrategyRegistry` — verify all asset types have a registered strategy/importer.
- **TaxRatePolicy tests:** Load from a temp YAML file; assert correct `TaxRate` returned per FY/asset_type combo.
- Coverage targets from `CLAUDE.md` apply: overall ≥ 80%, engine ≥ 90%, importers ≥ 85%.

---

## Migration Safety Rules

1. Each phase ends with `uv run pytest` green.
2. No phase touches more than one layer at a time.
3. New interfaces are additive — existing concrete classes satisfy them via duck-typing; no forced rewrites.
4. The `api/dependencies.py` wiring file is the only place concrete types appear. All other files use abstract types.
5. Old flat service files are deleted only after all callers are updated and tests pass.
