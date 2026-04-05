# Config-Driven Tax Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded tax strategy ClassVars with a hierarchical YAML config system that resolves tax rules per-lot using asset type, asset class, ISIN, and purchase date — and restructure the tax summary API/UI to show STCG/LTCG/Interest as separate sections.

**Architecture:** `TaxRuleResolver` in `engine/tax_engine.py` loads per-FY YAML configs and resolves rules via a 4-step chain: asset_type default → asset_type overrides → asset_class fields → asset_class overrides. `FifoTaxGainsStrategy` becomes config-driven (no ClassVars), resolving rules per-lot in the FIFO match loop. The API response splits into `stcg`/`ltcg`/`interest` buckets instead of asset-class grouping.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, PyYAML, pytest, Next.js, TypeScript

**Spec:** `docs/superpowers/specs/2026-04-04-config-driven-tax-rules-design.md`

**Key codebase facts:**
- Asset model field is `identifier` (not `isin`) — stores ISIN for MF/stocks (`backend/app/models/asset.py:35`)
- `_STCG_DAYS` dict in `lot_engine.py` is also used by returns strategies via their own ClassVars — returns strategies are NOT touched by this plan
- `AccruedInterestTaxGainsStrategy` (FD/RD) and `RealEstateTaxGainsStrategy` stay as separate strategy classes
- Existing tests instantiate strategies directly (e.g., `StockINTaxGainsStrategy()`) — all must be rewritten to use resolver-injected `FifoTaxGainsStrategy`

---

### Task 1: TaxRuleResolver + ResolvedTaxRule

**Files:**
- Create: `backend/tests/unit/test_tax_rule_resolver.py`
- Modify: `backend/app/engine/tax_engine.py`

This task builds the core config resolution engine. `TaxRuleResolver` replaces `TaxRatePolicy`.

- [x] **Step 1: Write failing tests for TaxRuleResolver**

Create `backend/tests/unit/test_tax_rule_resolver.py`:

```python
import pytest
from datetime import date
from pathlib import Path

from app.engine.tax_engine import TaxRuleResolver, ResolvedTaxRule


@pytest.fixture
def resolver(tmp_path):
    """Create a resolver with a test YAML config."""
    config = tmp_path / "2025-26.yaml"
    config.write_text("""
STOCK_IN:
  stcg_rate_pct: 20.0
  ltcg_rate_pct: 12.5
  stcg_days: 365
  ltcg_exemption_inr: 125000
  ltcg_exempt_eligible: true

STOCK_US:
  stcg_rate_pct: null
  ltcg_rate_pct: 12.5
  stcg_days: 730

GOLD:
  stcg_rate_pct: null
  ltcg_rate_pct: 12.5
  stcg_days: 1095

REAL_ESTATE:
  stcg_rate_pct: null
  ltcg_rate_pct: 12.5
  stcg_days: 730

MF:
  stcg_rate_pct: 20.0
  ltcg_rate_pct: 12.5
  stcg_days: 365
  ltcg_exemption_inr: 125000
  ltcg_exempt_eligible: true
  overrides:
    - match:
        bought_before: "2020-01-01"
      stcg_rate_pct: 15.0

  DEBT:
    stcg_rate_pct: null
    ltcg_rate_pct: 12.5
    stcg_days: 730
    ltcg_exemption_inr: 0
    ltcg_exempt_eligible: false
    overrides:
      - match:
          bought_on_or_after: "2023-04-01"
        ltcg_rate_pct: null

  EQUITY:
    overrides:
      - match:
          isins: ["INF209KB1YA0"]
        stcg_days: 730
        stcg_rate_pct: null
        ltcg_exemption_inr: 0
        ltcg_exempt_eligible: false
      - match:
          isins: ["INF209KB1YA0"]
          bought_on_or_after: "2023-04-01"
        ltcg_rate_pct: null
""")
    return TaxRuleResolver(tmp_path)


def test_simple_asset_type_defaults(resolver):
    rule = resolver.resolve("2025-26", "STOCK_IN")
    assert rule.stcg_rate_pct == 20.0
    assert rule.ltcg_rate_pct == 12.5
    assert rule.stcg_days == 365
    assert rule.ltcg_exemption_inr == 125000
    assert rule.ltcg_exempt_eligible is True


def test_defaults_for_optional_keys(resolver):
    """STOCK_US has no ltcg_exemption_inr or ltcg_exempt_eligible — should get defaults."""
    rule = resolver.resolve("2025-26", "STOCK_US")
    assert rule.stcg_rate_pct is None
    assert rule.ltcg_rate_pct == 12.5
    assert rule.stcg_days == 730
    assert rule.ltcg_exemption_inr == 0.0
    assert rule.ltcg_exempt_eligible is False


def test_asset_class_overrides_parent(resolver):
    """MF DEBT overrides stcg_rate_pct to None (slab) from MF default of 20.0."""
    rule = resolver.resolve("2025-26", "MF", asset_class="DEBT")
    assert rule.stcg_rate_pct is None
    assert rule.ltcg_rate_pct == 12.5
    assert rule.stcg_days == 730
    assert rule.ltcg_exemption_inr == 0
    assert rule.ltcg_exempt_eligible is False


def test_asset_class_inherits_unspecified_keys(resolver):
    """MF EQUITY has no direct keys — inherits all from MF default."""
    rule = resolver.resolve("2025-26", "MF", asset_class="EQUITY")
    assert rule.stcg_rate_pct == 20.0
    assert rule.ltcg_rate_pct == 12.5
    assert rule.stcg_days == 365
    assert rule.ltcg_exemption_inr == 125000
    assert rule.ltcg_exempt_eligible is True


def test_asset_type_level_override_by_date(resolver):
    """MF default has override: bought_before 2020-01-01 → stcg_rate_pct 15.0."""
    rule = resolver.resolve("2025-26", "MF", buy_date=date(2019, 6, 1))
    assert rule.stcg_rate_pct == 15.0
    # bought after cutoff — no override
    rule2 = resolver.resolve("2025-26", "MF", buy_date=date(2021, 1, 1))
    assert rule2.stcg_rate_pct == 20.0


def test_asset_class_epoch_override(resolver):
    """MF DEBT post-2023: ltcg_rate_pct becomes None (slab)."""
    rule = resolver.resolve("2025-26", "MF", asset_class="DEBT",
                            buy_date=date(2023, 6, 1))
    assert rule.ltcg_rate_pct is None
    assert rule.stcg_rate_pct is None


def test_debt_mf_pre2023_keeps_ltcg(resolver):
    """MF DEBT pre-2023: ltcg_rate_pct stays 12.5."""
    rule = resolver.resolve("2025-26", "MF", asset_class="DEBT",
                            buy_date=date(2022, 1, 1))
    assert rule.ltcg_rate_pct == 12.5


def test_isin_override(resolver):
    """MF EQUITY with specific ISIN gets foreign-equity-like rules."""
    rule = resolver.resolve("2025-26", "MF", asset_class="EQUITY",
                            isin="INF209KB1YA0")
    assert rule.stcg_days == 730
    assert rule.stcg_rate_pct is None
    assert rule.ltcg_exemption_inr == 0
    assert rule.ltcg_exempt_eligible is False
    # ltcg_rate_pct still 12.5 (no epoch match without buy_date)
    assert rule.ltcg_rate_pct == 12.5


def test_isin_plus_epoch_override(resolver):
    """MF EQUITY + specific ISIN + post-2023: ltcg_rate_pct becomes None."""
    rule = resolver.resolve("2025-26", "MF", asset_class="EQUITY",
                            isin="INF209KB1YA0", buy_date=date(2024, 1, 1))
    assert rule.ltcg_rate_pct is None
    assert rule.stcg_days == 730


def test_isin_no_match_gets_default(resolver):
    """MF EQUITY with non-matching ISIN gets default MF EQUITY rules."""
    rule = resolver.resolve("2025-26", "MF", asset_class="EQUITY",
                            isin="INF999ZZ9ZZ9")
    assert rule.stcg_rate_pct == 20.0
    assert rule.stcg_days == 365


def test_missing_fy_raises(resolver):
    with pytest.raises(ValueError, match="No tax rate config"):
        resolver.resolve("2099-00", "STOCK_IN")


def test_missing_asset_type_raises(resolver):
    with pytest.raises(KeyError):
        resolver.resolve("2025-26", "UNKNOWN_TYPE")


def test_resolved_tax_rule_is_frozen():
    rule = ResolvedTaxRule(
        stcg_rate_pct=20.0, ltcg_rate_pct=12.5, stcg_days=365,
        ltcg_exemption_inr=125000, ltcg_exempt_eligible=True,
    )
    with pytest.raises(AttributeError):
        rule.stcg_rate_pct = 99.0
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_tax_rule_resolver.py -v`
Expected: FAIL — `ImportError: cannot import name 'TaxRuleResolver'`

- [x] **Step 3: Implement TaxRuleResolver and ResolvedTaxRule**

In `backend/app/engine/tax_engine.py`, replace the old `TaxRate` dataclass and `TaxRatePolicy` class (lines 240-287) with:

```python
# ---------------------------------------------------------------------------
# ResolvedTaxRule + TaxRuleResolver — config-driven rate lookup
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedTaxRule:
    """Resolved tax rule for one asset type + class + ISIN + buy_date combination."""
    stcg_rate_pct: float | None      # None = slab rate
    ltcg_rate_pct: float | None
    stcg_days: int
    ltcg_exemption_inr: float
    ltcg_exempt_eligible: bool


# Keys that are rule fields (not asset_class sub-levels)
_RULE_KEYS = {
    "stcg_rate_pct", "ltcg_rate_pct", "stcg_days",
    "ltcg_exemption_inr", "ltcg_exempt_eligible", "overrides",
}

_RULE_DEFAULTS: dict[str, object] = {
    "ltcg_exemption_inr": 0.0,
    "ltcg_exempt_eligible": False,
}


class TaxRuleResolver:
    """
    Loads per-FY YAML config and resolves tax rules via hierarchical override chain.

    Resolution order:
      1. asset_type default fields
      2. asset_type overrides (ordered merge)
      3. asset_class fields (if sub-level exists)
      4. asset_class overrides (ordered merge)

    Adding a new FY = drop a YYYY-YY.yaml file into config_dir.
    """

    def __init__(self, config_dir: Path):
        self._config_dir = config_dir
        self._cache: dict[str, dict] = {}

    def resolve(
        self,
        fy: str,
        asset_type: str,
        asset_class: str | None = None,
        isin: str | None = None,
        buy_date: date | None = None,
    ) -> ResolvedTaxRule:
        raw = self._load(fy)
        type_block = raw[asset_type]

        # 1. Asset type defaults (scalar rule keys only)
        result = {k: v for k, v in type_block.items()
                  if k in _RULE_KEYS and k != "overrides"}

        # 2. Asset type overrides
        result = self._apply_overrides(
            result, type_block.get("overrides", []), isin, buy_date)

        # 3. Asset class fields (if sub-level exists)
        if asset_class and asset_class in type_block:
            class_block = type_block[asset_class]
            class_fields = {k: v for k, v in class_block.items()
                           if k in _RULE_KEYS and k != "overrides"}
            result = {**result, **class_fields}

            # 4. Asset class overrides
            result = self._apply_overrides(
                result, class_block.get("overrides", []), isin, buy_date)

        # Fill defaults for optional keys
        for k, default in _RULE_DEFAULTS.items():
            result.setdefault(k, default)

        # Strip 'overrides' if it leaked in
        result.pop("overrides", None)

        return ResolvedTaxRule(**result)

    def _load(self, fy: str) -> dict:
        if fy not in self._cache:
            path = self._config_dir / f"{fy}.yaml"
            if not path.exists():
                raise ValueError(
                    f"No tax rate config for FY {fy!r}. Expected file: {path}"
                )
            with open(path) as f:
                self._cache[fy] = yaml.safe_load(f)
        return self._cache[fy]

    def _apply_overrides(
        self,
        base: dict,
        overrides: list[dict],
        isin: str | None,
        buy_date: date | None,
    ) -> dict:
        result = dict(base)
        for override in overrides:
            match_conds = override["match"]
            if not self._matches(match_conds, isin, buy_date):
                continue
            for k, v in override.items():
                if k != "match" and k in _RULE_KEYS:
                    result[k] = v
        return result

    @staticmethod
    def _matches(
        match: dict,
        isin: str | None,
        buy_date: date | None,
    ) -> bool:
        """Return True if ALL conditions in the match block are satisfied."""
        if "isins" in match:
            if isin is None or isin not in match["isins"]:
                return False
        if "bought_before" in match:
            cutoff = date.fromisoformat(match["bought_before"])
            if buy_date is None or buy_date >= cutoff:
                return False
        if "bought_on_or_after" in match:
            cutoff = date.fromisoformat(match["bought_on_or_after"])
            if buy_date is None or buy_date < cutoff:
                return False
        return True
```

Also remove the old `TaxRate` dataclass and `TaxRatePolicy` class from the same file (lines 240-287).

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_tax_rule_resolver.py -v`
Expected: All 14 tests PASS

- [x] **Step 5: Commit**

```bash
cd backend
git add tests/unit/test_tax_rule_resolver.py app/engine/tax_engine.py
git commit -m "feat: add TaxRuleResolver with hierarchical override resolution"
```

---

### Task 2: Rewrite YAML Config Files

**Files:**
- Modify: `backend/app/config/tax_rates/2024-25.yaml`
- Modify: `backend/app/config/tax_rates/2025-26.yaml`
- Modify: `backend/app/config/tax_rates/2026-27.yaml`

Replace the flat per-asset-type configs with hierarchical structure. Remove FD/RD/PPF/EPF/NPS/SGB.

- [x] **Step 1: Rewrite 2025-26.yaml**

Replace entire contents of `backend/app/config/tax_rates/2025-26.yaml` with:

```yaml
# FY 2025-26 capital gains tax rules
# Only assets with capital gains: STOCK_IN, STOCK_US, GOLD, REAL_ESTATE, MF
# FD/RD (interest income), PPF/EPF/NPS/SGB (exempt/special) are not here.
#
# stcg_rate_pct / ltcg_rate_pct: null = slab rate
# overrides: ordered list — all matching overrides merge top-to-bottom

STOCK_IN:
  stcg_rate_pct: 20.0
  ltcg_rate_pct: 12.5
  stcg_days: 365
  ltcg_exemption_inr: 125000
  ltcg_exempt_eligible: true

STOCK_US:
  stcg_rate_pct: null
  ltcg_rate_pct: 12.5
  stcg_days: 730

GOLD:
  stcg_rate_pct: null
  ltcg_rate_pct: 12.5
  stcg_days: 1095

REAL_ESTATE:
  stcg_rate_pct: null
  ltcg_rate_pct: 12.5
  stcg_days: 730

MF:
  stcg_rate_pct: 20.0
  ltcg_rate_pct: 12.5
  stcg_days: 365
  ltcg_exemption_inr: 125000
  ltcg_exempt_eligible: true

  DEBT:
    stcg_rate_pct: null
    ltcg_rate_pct: 12.5
    stcg_days: 730
    ltcg_exemption_inr: 0
    ltcg_exempt_eligible: false
    overrides:
      - match:
          bought_on_or_after: "2023-04-01"
        ltcg_rate_pct: null

  EQUITY:
    overrides:
      - match:
          isins: ["INF209KB1YA0"]
        stcg_days: 730
        stcg_rate_pct: null
        ltcg_exemption_inr: 0
        ltcg_exempt_eligible: false
      - match:
          isins: ["INF209KB1YA0"]
          bought_on_or_after: "2023-04-01"
        ltcg_rate_pct: null
```

- [x] **Step 2: Rewrite 2024-25.yaml**

Same structure as 2025-26 (rates are identical per existing comment). Copy the content from 2025-26.yaml, update the comment header to `# FY 2024-25 capital gains tax rules`.

- [x] **Step 3: Rewrite 2026-27.yaml**

Same structure. Update comment header to `# FY 2026-27 capital gains tax rules`.

- [x] **Step 4: Run resolver tests against new configs**

Run: `cd backend && uv run pytest tests/unit/test_tax_rule_resolver.py -v`
Expected: PASS (tests use tmp_path fixtures, not actual config files, but this confirms no import issues)

- [x] **Step 5: Commit**

```bash
cd backend
git add app/config/tax_rates/2024-25.yaml app/config/tax_rates/2025-26.yaml app/config/tax_rates/2026-27.yaml
git commit -m "refactor: rewrite tax rate YAML configs with hierarchical override structure"
```

---

### Task 3: Refactor TaxGainsStrategy ABC + Registry

**Files:**
- Modify: `backend/app/services/tax/strategies/base.py`
- Modify: `backend/tests/unit/test_tax_strategies.py` (registry tests only)

Update the `compute()` signature to accept `fy: str` and add `register_tax_strategy_instance()` for direct instance registration.

- [x] **Step 1: Write failing test for updated signature and instance registration**

Add to `backend/tests/unit/test_tax_strategies.py`:

```python
def test_register_tax_strategy_instance():
    """register_tax_strategy_instance adds a pre-built instance to the registry."""
    from app.services.tax.strategies.base import (
        register_tax_strategy_instance, _REGISTRY, TaxGainsStrategy,
        AssetTaxGainsResult,
    )
    from datetime import date

    class DummyStrategy(TaxGainsStrategy):
        def compute(self, asset, uow, fy, fy_start, fy_end, slab_rate_pct):
            return AssetTaxGainsResult(
                asset_id=0, asset_name="", asset_type="", asset_class="",
                st_gain=0, lt_gain=0, st_tax_estimate=0, lt_tax_estimate=0,
                ltcg_exemption_used=0, has_slab=False,
                ltcg_exempt_eligible=False, ltcg_slab=False,
            )

    instance = DummyStrategy()
    register_tax_strategy_instance(("TEST_TYPE", "*"), instance)
    assert _REGISTRY[("TEST_TYPE", "*")] is instance
    # Cleanup
    del _REGISTRY[("TEST_TYPE", "*")]
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_tax_strategies.py::test_register_tax_strategy_instance -v`
Expected: FAIL — `ImportError: cannot import name 'register_tax_strategy_instance'`

- [x] **Step 3: Update base.py**

In `backend/app/services/tax/strategies/base.py`:

1. Add `fy: str` parameter to `TaxGainsStrategy.compute()` (after `uow`, before `fy_start`):

```python
class TaxGainsStrategy(ABC):
    @abstractmethod
    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy: str,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
        ...
```

2. Add `register_tax_strategy_instance` function after the existing `register_tax_strategy` decorator:

```python
def register_tax_strategy_instance(key: tuple[str, str], instance: TaxGainsStrategy):
    """Register a pre-built strategy instance for a (asset_type, asset_class) key."""
    _REGISTRY[key] = instance
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/test_tax_strategies.py::test_register_tax_strategy_instance -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
cd backend
git add app/services/tax/strategies/base.py tests/unit/test_tax_strategies.py
git commit -m "refactor: add fy param to TaxGainsStrategy.compute(), add register_tax_strategy_instance"
```

---

### Task 4: Rewrite FifoTaxGainsStrategy as Config-Driven

**Files:**
- Modify: `backend/app/services/tax/strategies/fifo_base.py`
- Modify: `backend/tests/unit/test_tax_strategies.py`

Remove all ClassVars. Inject `TaxRuleResolver`. Resolve rules per-lot in the match loop.

- [x] **Step 1: Write failing tests for config-driven FifoTaxGainsStrategy**

Replace the strategy-specific tests in `backend/tests/unit/test_tax_strategies.py`. Remove imports of deleted strategies (`StockINTaxGainsStrategy`, `ForeignEquityTaxGainsStrategy`, `GoldTaxGainsStrategy`, `DebtMFTaxGainsStrategy`). Replace with tests that create a `FifoTaxGainsStrategy(resolver)`:

```python
from pathlib import Path
from app.engine.tax_engine import TaxRuleResolver
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy


@pytest.fixture
def resolver(tmp_path):
    config = tmp_path / "2024-25.yaml"
    config.write_text("""
STOCK_IN:
  stcg_rate_pct: 20.0
  ltcg_rate_pct: 12.5
  stcg_days: 365
  ltcg_exemption_inr: 125000
  ltcg_exempt_eligible: true

STOCK_US:
  stcg_rate_pct: null
  ltcg_rate_pct: 12.5
  stcg_days: 730

GOLD:
  stcg_rate_pct: null
  ltcg_rate_pct: 12.5
  stcg_days: 1095

MF:
  stcg_rate_pct: 20.0
  ltcg_rate_pct: 12.5
  stcg_days: 365
  ltcg_exemption_inr: 125000
  ltcg_exempt_eligible: true

  DEBT:
    stcg_rate_pct: null
    ltcg_rate_pct: 12.5
    stcg_days: 730
    ltcg_exemption_inr: 0
    ltcg_exempt_eligible: false
    overrides:
      - match:
          bought_on_or_after: "2023-04-01"
        ltcg_rate_pct: null
""")
    return TaxRuleResolver(tmp_path)


def _make_asset(asset_type="STOCK_IN", asset_class="EQUITY", asset_id=1,
                name="Test Asset", identifier=None):
    asset = MagicMock()
    asset.id = asset_id
    asset.name = name
    asset.asset_type.value = asset_type
    asset.asset_class.value = asset_class
    asset.identifier = identifier
    return asset


def test_fifo_config_no_sells_returns_zero(resolver):
    strategy = FifoTaxGainsStrategy(resolver)
    asset = _make_asset()
    txns = [_make_txn("BUY", d(2023, 1, 1), 10, -1000000)]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, "2024-25", d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == 0.0
    assert result.lt_gain == 0.0


def test_fifo_config_st_gain_stock_in(resolver):
    strategy = FifoTaxGainsStrategy(resolver)
    asset = _make_asset()
    txns = [
        _make_txn("BUY",  d(2024, 6, 1), 10, -1000000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 9, 1), 10,  1200000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, "2024-25", d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == pytest.approx(2000.0)
    assert result.lt_gain == pytest.approx(0.0)
    assert result.st_tax_estimate == pytest.approx(400.0)   # 2000 * 20%
    assert result.has_slab is False
    assert result.ltcg_exempt_eligible is True


def test_fifo_config_lt_gain_stock_in(resolver):
    strategy = FifoTaxGainsStrategy(resolver)
    asset = _make_asset()
    txns = [
        _make_txn("BUY",  d(2023, 1, 1), 10, -1000000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 6, 1), 10,  1500000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, "2024-25", d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.lt_gain == pytest.approx(5000.0)
    assert result.lt_tax_estimate == pytest.approx(625.0)   # 5000 * 12.5%


def test_fifo_config_foreign_equity_slab(resolver):
    strategy = FifoTaxGainsStrategy(resolver)
    asset = _make_asset(asset_type="STOCK_US", asset_class="EQUITY")
    txns = [
        _make_txn("BUY",  d(2024, 6, 1), 5, -50000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 9, 1), 5,  60000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, "2024-25", d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == pytest.approx(100.0)
    assert result.st_tax_estimate == pytest.approx(30.0)   # 100 * 30% slab
    assert result.has_slab is True
    assert result.ltcg_exempt_eligible is False


def test_fifo_config_gold_1095_day_threshold(resolver):
    strategy = FifoTaxGainsStrategy(resolver)
    asset = _make_asset(asset_type="GOLD", asset_class="GOLD")
    txns = [
        _make_txn("BUY",  d(2021, 1, 1), 10, -5000000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2023, 10, 1), 10, 6000000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, "2023-24", d(2023, 4, 1), d(2024, 3, 31), 30.0)
    assert result.st_gain == pytest.approx(10000.0)
    assert result.lt_gain == pytest.approx(0.0)
    assert result.has_slab is True


def test_fifo_config_debt_mf_pre2023_ltcg(resolver):
    strategy = FifoTaxGainsStrategy(resolver)
    asset = _make_asset(asset_type="MF", asset_class="DEBT")
    txns = [
        _make_txn("BUY",  d(2022, 1, 1), 100, -1000000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 6, 1), 100,  1200000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, "2024-25", d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.lt_gain == pytest.approx(2000.0)
    assert result.lt_tax_estimate == pytest.approx(250.0)   # 2000 * 12.5%


def test_fifo_config_debt_mf_post2023_all_slab(resolver):
    strategy = FifoTaxGainsStrategy(resolver)
    asset = _make_asset(asset_type="MF", asset_class="DEBT")
    txns = [
        _make_txn("BUY",  d(2023, 6, 1), 100, -1000000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2027, 12, 1), 100,  1200000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, "2027-28", d(2027, 4, 1), d(2028, 3, 31), 30.0)
    # Post-2023 debt: ltcg_rate_pct is null → slab
    # But stcg_days is 730 and holding is 1644 days → classified as LT
    # LT at slab rate
    assert result.lt_gain == pytest.approx(2000.0)
    assert result.lt_tax_estimate == pytest.approx(600.0)   # 2000 * 30% slab
    assert result.has_slab is True


def test_fifo_config_sell_outside_fy_excluded(resolver):
    strategy = FifoTaxGainsStrategy(resolver)
    asset = _make_asset()
    txns = [
        _make_txn("BUY",  d(2022, 1, 1), 10, -1000000, lot_id="lot1", txn_id=1),
        _make_txn("SELL", d(2024, 3, 1), 10,  1500000, txn_id=2),
    ]
    uow = _make_uow(transactions=txns)
    result = strategy.compute(asset, uow, "2024-25", d(2024, 4, 1), d(2025, 3, 31), 30.0)
    assert result.st_gain == 0.0
    assert result.lt_gain == 0.0
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_tax_strategies.py -v -k "fifo_config"`
Expected: FAIL — `FifoTaxGainsStrategy` still expects ClassVars, not a resolver

- [x] **Step 3: Rewrite fifo_base.py**

Replace entire contents of `backend/app/services/tax/strategies/fifo_base.py`:

```python
from __future__ import annotations

from datetime import date

from app.engine.lot_engine import match_lots_fifo
from app.engine.lot_helper import LotHelper
from app.engine.tax_engine import TaxRuleResolver
from app.repositories.unit_of_work import UnitOfWork
from app.services.tax.strategies.base import AssetTaxGainsResult, TaxGainsStrategy


class FifoTaxGainsStrategy(TaxGainsStrategy):
    """
    Config-driven FIFO lot-matched tax strategy.

    Resolves tax rules per-lot using TaxRuleResolver — no hardcoded rates.
    Handles epoch splits (e.g., debt MF pre/post 2023) and ISIN overrides
    automatically via the YAML config.
    """

    def __init__(self, resolver: TaxRuleResolver):
        self._resolver = resolver

    def _zero_result(self, asset) -> AssetTaxGainsResult:
        return AssetTaxGainsResult(
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset.asset_type.value,
            asset_class=asset.asset_class.value,
            st_gain=0.0, lt_gain=0.0,
            st_tax_estimate=0.0, lt_tax_estimate=0.0,
            ltcg_exemption_used=0.0,
            has_slab=False,
            ltcg_exempt_eligible=False,
            ltcg_slab=False,
        )

    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy: str,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
        asset_type = asset.asset_type.value
        asset_class = asset.asset_class.value
        isin = asset.identifier

        # Default rule (no buy_date) for stcg_days used in lot matching
        default_rule = self._resolver.resolve(
            fy, asset_type, asset_class=asset_class, isin=isin,
        )

        txns = uow.transactions.list_by_asset(asset.id)
        lots, sells = LotHelper(stcg_days=default_rule.stcg_days).build_lots_sells(txns)

        if not lots or not sells:
            return self._zero_result(asset)

        matched = match_lots_fifo(lots, sells, stcg_days=default_rule.stcg_days)

        st_gain, lt_gain = 0.0, 0.0
        st_tax, lt_tax = 0.0, 0.0
        has_slab = False
        ltcg_exempt_eligible = False

        for m in matched:
            sell_date = m["sell_date"]
            buy_date = m["buy_date"]
            if isinstance(sell_date, str):
                sell_date = date.fromisoformat(sell_date)
            if isinstance(buy_date, str):
                buy_date = date.fromisoformat(buy_date)
            if not (fy_start <= sell_date <= fy_end):
                continue

            # Resolve rule for THIS lot's buy_date
            rule = self._resolver.resolve(
                fy, asset_type, asset_class=asset_class,
                isin=isin, buy_date=buy_date,
            )

            holding_days = (sell_date - buy_date).days
            gain = m["realised_gain_inr"]

            if holding_days < rule.stcg_days:
                st_gain += gain
                rate = rule.stcg_rate_pct if rule.stcg_rate_pct is not None else slab_rate_pct
                if gain > 0:
                    st_tax += gain * rate / 100.0
                if rule.stcg_rate_pct is None:
                    has_slab = True
            else:
                lt_gain += gain
                rate = rule.ltcg_rate_pct if rule.ltcg_rate_pct is not None else slab_rate_pct
                if gain > 0:
                    lt_tax += gain * rate / 100.0
                if rule.ltcg_rate_pct is None:
                    has_slab = True

            if rule.ltcg_exempt_eligible:
                ltcg_exempt_eligible = True

        return AssetTaxGainsResult(
            asset_id=asset.id,
            asset_name=asset.name,
            asset_type=asset_type,
            asset_class=asset_class,
            st_gain=st_gain,
            lt_gain=lt_gain,
            st_tax_estimate=st_tax,
            lt_tax_estimate=lt_tax,
            ltcg_exemption_used=0.0,
            has_slab=has_slab,
            ltcg_exempt_eligible=ltcg_exempt_eligible,
            ltcg_slab=False,
        )
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_tax_strategies.py -v -k "fifo_config"`
Expected: All 8 new tests PASS

- [x] **Step 5: Commit**

```bash
cd backend
git add app/services/tax/strategies/fifo_base.py tests/unit/test_tax_strategies.py
git commit -m "refactor: rewrite FifoTaxGainsStrategy as config-driven with per-lot resolution"
```

---

### Task 5: Update AccruedInterestTaxGainsStrategy + RealEstateTaxGainsStrategy Signatures

**Files:**
- Modify: `backend/app/services/tax/strategies/accrued_interest.py`
- Modify: `backend/app/services/tax/strategies/real_estate.py`

Both need the `fy: str` parameter added to their `compute()` signatures.

- [ ] **Step 1: Update AccruedInterestTaxGainsStrategy**

In `backend/app/services/tax/strategies/accrued_interest.py`, change the `compute` method signature to add `fy: str` after `uow`:

```python
    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy: str,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
```

The body stays identical — `fy` is unused for interest income.

- [ ] **Step 2: Update RealEstateTaxGainsStrategy**

In `backend/app/services/tax/strategies/real_estate.py`:

1. Add `fy: str` parameter to `compute()` signature (same position as above)
2. Inject `TaxRuleResolver` via `__init__` and use it for rate lookups instead of hardcoded `LTCG_RATE = 12.5`:

```python
from app.engine.tax_engine import TaxRuleResolver

class RealEstateTaxGainsStrategy(TaxGainsStrategy):
    def __init__(self, resolver: TaxRuleResolver):
        self._resolver = resolver

    def compute(
        self,
        asset,
        uow: UnitOfWork,
        fy: str,
        fy_start: date,
        fy_end: date,
        slab_rate_pct: float,
    ) -> AssetTaxGainsResult:
        # ... existing logic ...
        # Replace: lt_tax = max(0.0, lt_gain) * LTCG_RATE / 100.0
        # With:
        rule = self._resolver.resolve(fy, "REAL_ESTATE")
        lt_tax = max(0.0, lt_gain) * (rule.ltcg_rate_pct or slab_rate_pct) / 100.0
```

Remove the `LTCG_RATE = 12.5` constant and `REAL_ESTATE_STCG_DAYS = 730` — use `rule.stcg_days` from the resolver instead.

- [ ] **Step 3: Update existing accrued_interest and real_estate tests**

In `backend/tests/unit/test_tax_strategies.py`, update existing tests:
- `test_accrued_interest_*` tests: add `"2024-25"` as the third argument to `strategy.compute()`
- `test_real_estate_*` tests: create the strategy with `RealEstateTaxGainsStrategy(resolver)` and add `"2024-25"` arg. Add `REAL_ESTATE` to the resolver fixture YAML.

- [ ] **Step 4: Run all strategy tests**

Run: `cd backend && uv run pytest tests/unit/test_tax_strategies.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/services/tax/strategies/accrued_interest.py app/services/tax/strategies/real_estate.py tests/unit/test_tax_strategies.py
git commit -m "refactor: update AccruedInterest and RealEstate strategy signatures for fy param"
```

---

### Task 6: Delete Old Leaf Strategies + Update Registry

**Files:**
- Delete: `backend/app/services/tax/strategies/indian_equity.py`
- Delete: `backend/app/services/tax/strategies/foreign_equity.py`
- Delete: `backend/app/services/tax/strategies/gold.py`
- Delete: `backend/app/services/tax/strategies/debt_mf.py`
- Modify: `backend/app/services/tax/strategies/__init__.py`
- Modify: `backend/app/api/dependencies.py`

- [ ] **Step 1: Delete the four leaf strategy files**

```bash
cd backend
rm app/services/tax/strategies/indian_equity.py
rm app/services/tax/strategies/foreign_equity.py
rm app/services/tax/strategies/gold.py
rm app/services/tax/strategies/debt_mf.py
```

- [ ] **Step 2: Update `__init__.py` to remove deleted imports**

Replace `backend/app/services/tax/strategies/__init__.py` with:

```python
# Import strategy modules to trigger registration.
# indian_equity, foreign_equity, gold, debt_mf are DELETED —
# their asset types are now handled by FifoTaxGainsStrategy registered in dependencies.py.
from app.services.tax.strategies import (  # noqa: F401
    accrued_interest,
    real_estate,
)
```

- [ ] **Step 3: Wire strategies in dependencies.py**

In `backend/app/api/dependencies.py`, update `get_tax_service`:

```python
from pathlib import Path
from app.engine.tax_engine import TaxRuleResolver
from app.services.tax.strategies.base import register_tax_strategy_instance
from app.services.tax.strategies.fifo_base import FifoTaxGainsStrategy
from app.services.tax.strategies.real_estate import RealEstateTaxGainsStrategy
from app.services.tax.strategies.accrued_interest import AccruedInterestTaxGainsStrategy

_tax_resolver = TaxRuleResolver(Path("app/config/tax_rates"))

# Register config-driven FIFO strategy for all lot-tracked capital gains types
_fifo_strategy = FifoTaxGainsStrategy(_tax_resolver)
for _key in [("STOCK_IN", "*"), ("STOCK_US", "*"), ("MF", "*"), ("GOLD", "*")]:
    register_tax_strategy_instance(_key, _fifo_strategy)

# Non-FIFO strategies
register_tax_strategy_instance(("REAL_ESTATE", "*"), RealEstateTaxGainsStrategy(_tax_resolver))
register_tax_strategy_instance(("FD", "*"), AccruedInterestTaxGainsStrategy())
register_tax_strategy_instance(("RD", "*"), AccruedInterestTaxGainsStrategy())


def get_tax_service(db: Session = Depends(get_db)) -> TaxService:
    slab_rate_pct = float(os.environ.get("SLAB_RATE", "30.0"))
    return TaxService(uow_factory=lambda: UnitOfWork(db), slab_rate_pct=slab_rate_pct)
```

- [ ] **Step 4: Remove old `@register_tax_strategy` decorators from real_estate.py and accrued_interest.py**

Since these are now registered in `dependencies.py`, remove the `@register_tax_strategy(...)` decorators from both files. Keep the class definitions.

- [ ] **Step 5: Run all tests**

Run: `cd backend && uv run pytest tests/unit/test_tax_strategies.py -v`
Expected: PASS — old tests that imported deleted strategies have already been replaced in Task 4

- [ ] **Step 6: Commit**

```bash
cd backend
git add -A app/services/tax/strategies/ app/api/dependencies.py
git commit -m "refactor: delete leaf tax strategies, wire config-driven registration in dependencies.py"
```

---

### Task 7: Update TaxService.get_tax_summary() — STCG/LTCG/Interest Split

**Files:**
- Modify: `backend/app/services/tax_service.py`
- Modify: `backend/tests/unit/test_tax_strategies.py` (or create new test file)

- [ ] **Step 1: Write failing test for new response shape**

Add to `backend/tests/unit/test_tax_strategies.py` (or a new file `test_tax_service_summary.py`):

```python
def test_tax_summary_returns_stcg_ltcg_interest_split():
    """get_tax_summary returns { fy, stcg, ltcg, interest } structure."""
    # This is a high-level shape test — detailed tests per-field come next
    from app.services.tax_service import TaxService
    from unittest.mock import MagicMock

    uow_factory = MagicMock()
    uow = MagicMock()
    uow_factory.return_value.__enter__ = MagicMock(return_value=uow)
    uow_factory.return_value.__exit__ = MagicMock(return_value=False)
    uow.assets.list.return_value = []  # no assets

    svc = TaxService(uow_factory=uow_factory, slab_rate_pct=30.0)
    result = svc.get_tax_summary("2024-25")

    assert result["fy"] == "2024-25"
    assert "stcg" in result
    assert "ltcg" in result
    assert "interest" in result
    assert result["stcg"]["assets"] == []
    assert result["ltcg"]["assets"] == []
    assert result["interest"]["assets"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_tax_strategies.py::test_tax_summary_returns_stcg_ltcg_interest_split -v`
Expected: FAIL — current response uses `entries` key

- [ ] **Step 3: Rewrite get_tax_summary()**

In `backend/app/services/tax_service.py`, rewrite `get_tax_summary()` to:

1. Collect all strategy results (same loop as before)
2. Separate FD/RD results into `interest_results`
3. For remaining results, split each into stcg_assets (if `st_gain != 0`) and ltcg_assets (if `lt_gain != 0`)
4. Apply Section 112A exemption once across all exempt-eligible LTCG
5. Return `{ fy, stcg: {...}, ltcg: {...}, interest: {...} }`

Update the `strategy.compute()` call to pass `fy_label` as the new `fy` argument:

```python
result = strategy.compute(asset, uow, fy_label, fy_start, fy_end, self._slab_rate_pct)
```

The new response shape:

```python
{
    "fy": fy_label,
    "stcg": {
        "total_gain": total_st_gain,
        "total_tax": total_st_tax,
        "has_slab_items": st_has_slab,
        "assets": [
            {
                "asset_id": r.asset_id,
                "asset_name": r.asset_name,
                "asset_type": r.asset_type,
                "gain": r.st_gain,
                "tax_estimate": r.st_tax_estimate,
                "is_slab": r.stcg_rate_pct is None,  # derived from has_slab per asset
                "tax_rate_pct": effective_st_rate,
            }
            for r in results if r.st_gain != 0
        ],
    },
    "ltcg": {
        "total_gain": total_lt_gain,
        "total_tax": total_lt_tax,
        "ltcg_exemption_used": exemption_used,
        "has_slab_items": lt_has_slab,
        "assets": [
            {
                "asset_id": r.asset_id,
                "asset_name": r.asset_name,
                "asset_type": r.asset_type,
                "gain": r.lt_gain,
                "tax_estimate": per_asset_lt_tax,
                "is_slab": r.ltcg_slab,
                "tax_rate_pct": effective_lt_rate,
                "ltcg_exempt_eligible": r.ltcg_exempt_eligible,
            }
            for r in results if r.lt_gain != 0
        ],
    },
    "interest": {
        "total_interest": total_interest,
        "total_tax": interest_tax,
        "slab_rate_pct": self._slab_rate_pct,
        "assets": [
            {
                "asset_id": r.asset_id,
                "asset_name": r.asset_name,
                "asset_type": r.asset_type,
                "interest": r.st_gain,
                "tax_estimate": r.st_tax_estimate,
            }
            for r in interest_results
        ],
    },
}
```

Also add `is_slab_st` and `is_slab_lt` booleans to `AssetTaxGainsResult` to track per-asset slab status, or derive from the existing `has_slab` field and rate values.

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/unit/test_tax_strategies.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/services/tax_service.py tests/unit/test_tax_strategies.py
git commit -m "refactor: restructure get_tax_summary to return stcg/ltcg/interest split"
```

---

### Task 8: Update TaxService Unrealised Path to Use Resolver

**Files:**
- Modify: `backend/app/services/tax_service.py`

- [ ] **Step 1: Update `_build_lots_for_asset` to use TaxRuleResolver**

In `TaxService.__init__`, accept and store a `TaxRuleResolver`:

```python
class TaxService:
    def __init__(self, uow_factory: IUnitOfWorkFactory, slab_rate_pct: float = 30.0,
                 resolver: TaxRuleResolver | None = None):
        self._uow_factory = uow_factory
        self._slab_rate_pct = slab_rate_pct
        self._registry = TaxStrategyRegistry()
        self._resolver = resolver
```

In `_build_lots_for_asset`, replace:
```python
stcg_days = _STCG_DAYS.get(asset_type, EQUITY_STCG_DAYS)
```
with:
```python
if self._resolver:
    fy_label = self._current_fy_label()  # helper that returns current FY
    rule = self._resolver.resolve(fy_label, asset_type,
                                   asset_class=asset.asset_class.value,
                                   isin=asset.identifier)
    stcg_days = rule.stcg_days
else:
    stcg_days = 365  # fallback
```

Add helper:
```python
def _current_fy_label(self) -> str:
    from datetime import date
    today = date.today()
    start_yr = today.year if today.month >= 4 else today.year - 1
    return f"{start_yr}-{str(start_yr + 1)[-2:]}"
```

- [ ] **Step 2: Update dependencies.py to pass resolver to TaxService**

```python
def get_tax_service(db: Session = Depends(get_db)) -> TaxService:
    slab_rate_pct = float(os.environ.get("SLAB_RATE", "30.0"))
    return TaxService(
        uow_factory=lambda: UnitOfWork(db),
        slab_rate_pct=slab_rate_pct,
        resolver=_tax_resolver,
    )
```

- [ ] **Step 3: Remove `_STCG_DAYS` import from tax_service.py**

Remove: `from app.engine.lot_engine import _STCG_DAYS, EQUITY_STCG_DAYS`

- [ ] **Step 4: Run all backend tests**

Run: `cd backend && uv run pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd backend
git add app/services/tax_service.py app/api/dependencies.py
git commit -m "refactor: update unrealised gains path to use TaxRuleResolver"
```

---

### Task 9: Clean Up tax_engine.py — Remove Dead Code

**Files:**
- Modify: `backend/app/engine/tax_engine.py`
- Modify: `backend/tests/unit/test_tax_engine.py`

- [ ] **Step 1: Remove dead functions and constants**

From `backend/app/engine/tax_engine.py`, remove:
- `EXEMPTION_ELIGIBLE`, `FULLY_EXEMPT`, `SLAB_RATE_ALL`, `LTCG_FLAT_ST_SLAB` constant sets
- `get_tax_rate()` function
- `compute_fy_realised_gains()` function
- `estimate_tax()` function
- Old `TaxRate` dataclass (if not already removed in Task 1)
- Old `TaxRatePolicy` class (if not already removed in Task 1)
- Import of `_STCG_DAYS, EQUITY_STCG_DAYS` from lot_engine (only needed by deleted `compute_fy_realised_gains`)

Keep: `parse_fy()`, `classify_holding()`, `apply_ltcg_exemption()`, `find_harvest_opportunities()`, `LTCG_EXEMPTION_LIMIT`, `TaxRuleResolver`, `ResolvedTaxRule`

- [ ] **Step 2: Update test_tax_engine.py**

Remove tests for deleted functions (`test_get_tax_rate_*`, `test_compute_fy_realised_gains_*`, `test_estimate_tax_*`). Keep tests for `parse_fy`, `classify_holding`, `apply_ltcg_exemption`, `find_harvest_opportunities`.

- [ ] **Step 3: Run tests**

Run: `cd backend && uv run pytest tests/unit/test_tax_engine.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
cd backend
git add app/engine/tax_engine.py tests/unit/test_tax_engine.py
git commit -m "cleanup: remove dead tax functions replaced by TaxRuleResolver"
```

---

### Task 10: Update API Response Schema

**Files:**
- Modify: `backend/app/schemas/responses/tax.py`

- [ ] **Step 1: Rewrite tax response models**

Replace `TaxGainEntry` and `TaxSummaryResponse` in `backend/app/schemas/responses/tax.py`:

```python
from datetime import date
from typing import List, Optional
from pydantic import BaseModel


class StcgAssetEntry(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    gain: float
    tax_estimate: float
    is_slab: bool = False
    tax_rate_pct: Optional[float] = None


class LtcgAssetEntry(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    gain: float
    tax_estimate: float
    is_slab: bool = False
    tax_rate_pct: Optional[float] = None
    ltcg_exempt_eligible: bool = False


class InterestAssetEntry(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    interest: float
    tax_estimate: float


class StcgSection(BaseModel):
    total_gain: float = 0.0
    total_tax: float = 0.0
    has_slab_items: bool = False
    assets: List[StcgAssetEntry] = []


class LtcgSection(BaseModel):
    total_gain: float = 0.0
    total_tax: float = 0.0
    ltcg_exemption_used: float = 0.0
    has_slab_items: bool = False
    assets: List[LtcgAssetEntry] = []


class InterestSection(BaseModel):
    total_interest: float = 0.0
    total_tax: float = 0.0
    slab_rate_pct: float = 30.0
    assets: List[InterestAssetEntry] = []


class TaxSummaryResponse(BaseModel):
    fy: str
    stcg: StcgSection = StcgSection()
    ltcg: LtcgSection = LtcgSection()
    interest: InterestSection = InterestSection()


# Keep existing UnrealisedGainEntry and HarvestOpportunityEntry unchanged
class UnrealisedGainEntry(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    st_unrealised_gain: Optional[float] = None
    lt_unrealised_gain: Optional[float] = None
    total_unrealised_gain: Optional[float] = None


class HarvestOpportunityEntry(BaseModel):
    asset_id: int
    asset_name: str
    asset_type: str
    lot_id: str
    buy_date: date
    units: float
    unrealised_loss: float
    is_short_term: bool
```

- [ ] **Step 2: Run backend tests**

Run: `cd backend && uv run pytest -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd backend
git add app/schemas/responses/tax.py
git commit -m "refactor: update tax response schemas for stcg/ltcg/interest split"
```

---

### Task 11: Update Integration Tests

**Files:**
- Modify: `backend/tests/integration/test_tax_api.py`

- [ ] **Step 1: Update API test assertions for new response shape**

Update `test_tax_api.py` to expect the new `{ fy, stcg, ltcg, interest }` structure instead of `{ fy, entries, totals }`. Adjust assertions to check `data["stcg"]["assets"]`, `data["ltcg"]["total_gain"]`, etc.

- [ ] **Step 2: Run integration tests**

Run: `cd backend && uv run pytest tests/integration/test_tax_api.py -v`
Expected: PASS

- [ ] **Step 3: Run full backend test suite**

Run: `cd backend && uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
cd backend
git add tests/integration/test_tax_api.py
git commit -m "test: update integration tests for new tax summary response shape"
```

---

### Task 12: Frontend — Update Types and API Client

**Files:**
- Modify: `frontend/types/index.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Replace tax-related types**

In `frontend/types/index.ts`, replace `AssetGainBreakdown`, `TaxSummaryEntry`, `TaxSummaryTotals`, `TaxSummaryResponse` (lines 249-287) with:

```typescript
export interface StcgAssetEntry {
  asset_id: number
  asset_name: string
  asset_type: AssetType
  gain: number
  tax_estimate: number
  is_slab: boolean
  tax_rate_pct: number | null
}

export interface LtcgAssetEntry {
  asset_id: number
  asset_name: string
  asset_type: AssetType
  gain: number
  tax_estimate: number
  is_slab: boolean
  tax_rate_pct: number | null
  ltcg_exempt_eligible: boolean
}

export interface InterestAssetEntry {
  asset_id: number
  asset_name: string
  asset_type: AssetType
  interest: number
  tax_estimate: number
}

export interface StcgSection {
  total_gain: number
  total_tax: number
  has_slab_items: boolean
  assets: StcgAssetEntry[]
}

export interface LtcgSection {
  total_gain: number
  total_tax: number
  ltcg_exemption_used: number
  has_slab_items: boolean
  assets: LtcgAssetEntry[]
}

export interface InterestSection {
  total_interest: number
  total_tax: number
  slab_rate_pct: number
  assets: InterestAssetEntry[]
}

export interface TaxSummaryResponse {
  fy: string
  stcg: StcgSection
  ltcg: LtcgSection
  interest: InterestSection
}
```

- [ ] **Step 2: Update api.ts import**

In `frontend/lib/api.ts`, update the import line to include new types. The `api.tax.summary` call shape doesn't change (still returns `TaxSummaryResponse`), just the type definition changed.

- [ ] **Step 3: Commit**

```bash
cd frontend
git add types/index.ts lib/api.ts
git commit -m "refactor: update frontend types for stcg/ltcg/interest tax summary split"
```

---

### Task 13: Frontend — Redesign Tax Page

**Files:**
- Modify: `frontend/app/tax/page.tsx`

- [ ] **Step 1: Rewrite the tax page**

Replace the current Realised Gains section and stat cards with three separate cards:

1. **STCG card** — table with columns: Asset (linked), Type, Gain/Loss, Tax Rate, Tax Est. Footer row with totals.
2. **LTCG card** — same columns + exemption badge in header. Footer row with totals (post-exemption).
3. **Interest Income card** — separate card below capital gains. Columns: Asset, Type, Interest, Tax Est. Header shows slab rate. Footer with totals.

Remove:
- The 4 stat cards (`grid grid-cols-2 gap-4 sm:grid-cols-4`)
- `expandedClasses` state and `toggleClass` function
- `ASSET_CLASS_LABELS` constant
- The asset-class-grouped table

Keep unchanged:
- Unrealised Gains section
- Tax-Loss Harvesting section
- FY selector

Key implementation details:
- Both STCG and LTCG sections always show all assets (no expand/collapse)
- Tax Rate column shows `"20%"`, `"12.5%"`, or `"slab"` based on `is_slab` / `tax_rate_pct`
- Asset names link to `/assets/${asset_id}`
- LTCG header shows `Exemption: ₹{formatINR(ltcg_exemption_used)}` when > 0
- Interest card header shows `Slab rate: {slab_rate_pct}%`
- Empty state: "No short-term capital gains" / "No long-term capital gains" / "No interest income"

```tsx
{/* ── Short-Term Capital Gains ── */}
<div className={card} style={cardStyle}>
  <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
    Short-Term Capital Gains — FY {fy}
  </h2>
  {loadingSummary ? (
    <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 rounded" />)}</div>
  ) : !summary?.stcg.assets.length ? (
    <p className="py-10 text-center text-sm text-tertiary">No short-term capital gains for FY {fy}</p>
  ) : (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-border">
          <th className={th}>Asset</th>
          <th className={thr}>Gain / Loss</th>
          <th className={thr}>Tax Rate</th>
          <th className={thr}>Tax Est.</th>
        </tr>
      </thead>
      <tbody>
        {summary.stcg.assets.map((a) => (
          <tr key={a.asset_id} className="border-b border-border last:border-0 hover:bg-accent-subtle/30 transition-colors">
            <td className="py-3 pr-4">
              <Link href={`/assets/${a.asset_id}`} className="font-medium text-accent hover:underline">{a.asset_name}</Link>
              <span className="ml-2 text-[10px] text-tertiary">{ASSET_TYPE_LABELS[a.asset_type as AssetType] ?? a.asset_type}</span>
            </td>
            <td className="py-3 pr-4 text-right"><GainAmt value={a.gain} fmt={formatINR} /></td>
            <td className="py-3 pr-4 text-right text-xs text-secondary">
              {a.is_slab ? 'slab' : `${a.tax_rate_pct}%`}
            </td>
            <td className="py-3 text-right"><TaxEstimate value={a.tax_estimate} fmt={formatINR} /></td>
          </tr>
        ))}
        {/* Footer total */}
        <tr className="border-t-2 border-border font-semibold">
          <td className="py-3 pr-4 text-primary">Total STCG</td>
          <td className="py-3 pr-4 text-right"><GainAmt value={summary.stcg.total_gain} fmt={formatINR} /></td>
          <td className="py-3 pr-4" />
          <td className="py-3 text-right"><TaxEstimate value={summary.stcg.total_tax} fmt={formatINR} /></td>
        </tr>
      </tbody>
    </table>
  )}
  {summary?.stcg.has_slab_items && !loadingSummary && (
    <p className="mt-3 text-[11px] text-tertiary">* Slab-rate estimates use the configured SLAB_RATE. Actual tax depends on your income bracket.</p>
  )}
</div>
```

Follow the same pattern for LTCG (with exemption display) and Interest Income (with slab rate badge). See the spec Section 7 for the exact layout.

- [ ] **Step 2: Build the frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no type errors

- [ ] **Step 3: Commit**

```bash
cd frontend
git add app/tax/page.tsx
git commit -m "feat: redesign tax page with STCG/LTCG/Interest sections"
```

---

### Task 14: Final Verification

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Run frontend lint**

Run: `cd frontend && npm run lint`
Expected: No errors

- [ ] **Step 4: Start backend and test manually**

Run: `cd backend && uvicorn app.main:app --reload`
Then: `curl "http://localhost:8000/tax/summary?fy=2025-26" | python -m json.tool`
Expected: Response has `stcg`, `ltcg`, `interest` keys with correct asset entries

- [ ] **Step 5: Commit any final fixes if needed**
