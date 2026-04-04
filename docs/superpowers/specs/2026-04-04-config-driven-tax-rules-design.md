# Config-Driven Tax Rules with Hierarchical Overrides

## Problem

Tax strategies hard-code rates, holding periods, and exemption flags as ClassVars. The existing YAML config (`config/tax_rates/*.yaml`) and `TaxRatePolicy` are unused. This makes it impossible to:

1. Apply different rules to specific funds (e.g., S&P 500 index fund classified as MF/EQUITY but taxed like foreign equity)
2. Handle budget-epoch splits (e.g., debt MF pre/post Apr 2023) without custom strategy overrides
3. Add new FY rules or budget changes without code changes

Additionally, the frontend groups realised gains by asset class, which doesn't give a clear view of total STCG vs LTCG and which assets contribute to each.

## Design

### 1. YAML Config Schema

One file per FY in `config/tax_rates/`. Only capital-gains-applicable asset types: `STOCK_IN`, `STOCK_US`, `MF`, `GOLD`, `REAL_ESTATE`. FD/RD/PPF/EPF/NPS/SGB removed from these files.

#### Structure

```yaml
ASSET_TYPE:
  # Default rule keys (flat)
  stcg_rate_pct: float | null     # null = slab rate
  ltcg_rate_pct: float | null
  stcg_days: int
  ltcg_exemption_inr: float       # default 0
  ltcg_exempt_eligible: bool      # default false

  # Optional: asset_type-level overrides
  overrides:
    - match: { bought_before: "2023-04-01" }
      ltcg_rate_pct: null

  # Optional: asset_class sub-levels (only for types that need them, e.g., MF)
  DEBT:
    stcg_rate_pct: null
    # ... override keys merge onto parent default
    overrides:
      - match: { bought_on_or_after: "2023-04-01" }
        ltcg_rate_pct: null

  EQUITY:
    overrides:
      - match: { isins: ["INF209KB1YA0"] }
        stcg_days: 730
        stcg_rate_pct: null
```

#### Reserved Keys vs Asset Class Keys

At the asset_type level, these keys are reserved (treated as rule fields):
`stcg_rate_pct`, `ltcg_rate_pct`, `stcg_days`, `ltcg_exemption_inr`, `ltcg_exempt_eligible`, `overrides`

Any other dict-valued key (e.g., `DEBT`, `EQUITY`) is treated as an asset_class sub-level.

#### Override Match Conditions

Each override has a `match` block. ALL conditions must be true for the override to apply:

| Condition | Type | Meaning |
|---|---|---|
| `isins` | list[str] | Asset's ISIN must be in the list |
| `bought_before` | date str | Lot's buy_date must be before this date |
| `bought_on_or_after` | date str | Lot's buy_date must be on or after this date |

New match conditions can be added in the future without structural changes.

#### Override Resolution

Ordered merge — walk the overrides list top to bottom. If all conditions match, merge override keys onto the running result. Later overrides win for conflicting keys. General overrides should be listed first, specific ones last.

#### Full Resolution Chain

```
asset_type default
  → apply asset_type overrides (in order)
    → merge asset_class fields (if present)
      → apply asset_class overrides (in order)
        → ResolvedTaxRule
```

### 2. Example Config — FY 2025-26

```yaml
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

### 3. TaxRuleResolver

Replaces `TaxRatePolicy` in `engine/tax_engine.py`.

```python
@dataclass(frozen=True)
class ResolvedTaxRule:
    stcg_rate_pct: float | None     # None = slab
    ltcg_rate_pct: float | None
    stcg_days: int
    ltcg_exemption_inr: float       # default 0.0
    ltcg_exempt_eligible: bool      # default False

RULE_KEYS = {
    "stcg_rate_pct", "ltcg_rate_pct", "stcg_days",
    "ltcg_exemption_inr", "ltcg_exempt_eligible", "overrides",
}

RULE_DEFAULTS = {
    "ltcg_exemption_inr": 0.0,
    "ltcg_exempt_eligible": False,
}

class TaxRuleResolver:
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

        # 1. Asset type defaults
        result = {k: v for k, v in type_block.items()
                  if k in RULE_KEYS and k != "overrides"}

        # 2. Asset type overrides
        result = self._apply_overrides(
            result, type_block.get("overrides", []), isin, buy_date)

        # 3. Asset class fields (if sub-level exists)
        if asset_class and asset_class in type_block:
            class_block = type_block[asset_class]
            class_fields = {k: v for k, v in class_block.items()
                           if k in RULE_KEYS and k != "overrides"}
            result = {**result, **class_fields}

            # 4. Asset class overrides
            result = self._apply_overrides(
                result, class_block.get("overrides", []), isin, buy_date)

        # Fill defaults for optional keys
        for k, default in RULE_DEFAULTS.items():
            result.setdefault(k, default)

        return ResolvedTaxRule(**{k: v for k, v in result.items() if k != "overrides"})

    def _load(self, fy: str) -> dict:
        if fy not in self._cache:
            path = self._config_dir / f"{fy}.yaml"
            if not path.exists():
                raise ValueError(f"No tax rate config for FY {fy!r}. Expected: {path}")
            with open(path) as f:
                self._cache[fy] = yaml.safe_load(f)
        return self._cache[fy]

    def _apply_overrides(self, base, overrides, isin, buy_date):
        result = dict(base)
        for override in overrides:
            match_conds = override["match"]
            if not self._matches(match_conds, isin, buy_date):
                continue
            for k, v in override.items():
                if k != "match" and k in RULE_KEYS:
                    result[k] = v
        return result

    def _matches(self, match, isin, buy_date) -> bool:
        if "isins" in match:
            if isin is None or isin not in match["isins"]:
                return False
        if "bought_before" in match:
            if buy_date is None or buy_date >= date.fromisoformat(match["bought_before"]):
                return False
        if "bought_on_or_after" in match:
            if buy_date is None or buy_date < date.fromisoformat(match["bought_on_or_after"]):
                return False
        return True
```

### 4. Strategy Refactoring

#### Updated ABC Signature

`compute()` receives `fy: str` so strategies can call the resolver:

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
    ) -> AssetTaxGainsResult: ...
```

#### FifoTaxGainsStrategy — Config-Driven

No more ClassVar rates. Resolves rules per lot using `buy_date` + `isin`:

```python
class FifoTaxGainsStrategy(TaxGainsStrategy):
    def __init__(self, resolver: TaxRuleResolver):
        self._resolver = resolver

    def compute(self, asset, uow, fy, fy_start, fy_end, slab_rate_pct):
        default_rule = self._resolver.resolve(
            fy, asset.asset_type.value,
            asset_class=asset.asset_class.value,
            isin=asset.isin,
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

            rule = self._resolver.resolve(
                fy, asset.asset_type.value,
                asset_class=asset.asset_class.value,
                isin=asset.isin,
                buy_date=buy_date,
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
            asset_type=asset.asset_type.value,
            asset_class=asset.asset_class.value,
            st_gain=st_gain, lt_gain=lt_gain,
            st_tax_estimate=st_tax, lt_tax_estimate=lt_tax,
            ltcg_exemption_used=0.0,
            has_slab=has_slab,
            ltcg_exempt_eligible=ltcg_exempt_eligible,
            ltcg_slab=False,
        )
```

#### Leaf Strategy Disposition

| Current Strategy | After |
|---|---|
| `IndianEquityTaxGainsStrategy` | Deleted — absorbed into config-driven `FifoTaxGainsStrategy` |
| `StockINTaxGainsStrategy` | Deleted — registered directly in `dependencies.py` |
| `EquityMFTaxGainsStrategy` | Deleted |
| `ForeignEquityTaxGainsStrategy` | Deleted |
| `DebtMFTaxGainsStrategy` | Deleted — per-lot buy_date resolution replaces custom `_fy_gains()` |
| `GoldTaxGainsStrategy` | Deleted |
| `RealEstateTaxGainsStrategy` | Kept — custom `compute()` (not FIFO, not unit-tracked). Receives resolver for rate lookups. |
| `AccruedInterestTaxGainsStrategy` | Kept unchanged — FD/RD interest is not capital gains |

#### Registration in `dependencies.py`

```python
resolver = TaxRuleResolver(Path("app/config/tax_rates"))
fifo_strategy = FifoTaxGainsStrategy(resolver)

for key in [("STOCK_IN", "*"), ("STOCK_US", "*"), ("MF", "*"), ("GOLD", "*")]:
    register_tax_strategy_instance(key, fifo_strategy)

register_tax_strategy_instance(("REAL_ESTATE", "*"), RealEstateTaxGainsStrategy(resolver))
register_tax_strategy_instance(("FD", "*"), AccruedInterestTaxGainsStrategy())
register_tax_strategy_instance(("RD", "*"), AccruedInterestTaxGainsStrategy())
```

### 5. Code to Delete

- `_STCG_DAYS` dict and individual `*_STCG_DAYS` constants in `lot_engine.py` (see note below)
- All ClassVar rates on `FifoTaxGainsStrategy` (`stcg_days`, `stcg_rate_pct`, `ltcg_rate_pct`, `ltcg_exempt_eligible`, `ltcg_slab`)
- `indian_equity.py` — entire file
- `foreign_equity.py` — entire file
- `gold.py` — entire file
- `debt_mf.py` — entire file
- Old `TaxRatePolicy` and `TaxRate` dataclass in `tax_engine.py`
- Hardcoded constant sets in `tax_engine.py`: `EXEMPTION_ELIGIBLE`, `FULLY_EXEMPT`, `SLAB_RATE_ALL`, `LTCG_FLAT_ST_SLAB`
- `get_tax_rate()`, `estimate_tax()`, `compute_fy_realised_gains()` functions in `tax_engine.py`
- `_BUDGET_2023_CUTOFF` and `_DEBT_MF_LTCG_DAYS` constants in `debt_mf.py`

**Note on `_STCG_DAYS` removal:** `tax_service._build_lots_for_asset()` uses `_STCG_DAYS` for unrealised gains and harvest endpoints. This method must be updated to use `TaxRuleResolver` instead — resolve the default rule (no `buy_date`) for the asset to get `stcg_days`, then use per-lot `buy_date` resolution for `is_short_term` classification on each open lot. The returns strategies (`services/returns/strategies/`) have their own `stcg_days` ClassVars and are unaffected by this change.

### 6. API Response Restructure

`GET /tax/summary?fy=2025-26` response changes from asset-class grouping to STCG/LTCG/Interest split:

```json
{
  "fy": "2025-26",
  "stcg": {
    "total_gain": 45000.0,
    "total_tax": 9000.0,
    "has_slab_items": false,
    "assets": [
      {
        "asset_id": 1,
        "asset_name": "HDFC Bank",
        "asset_type": "STOCK_IN",
        "gain": 30000.0,
        "tax_estimate": 6000.0,
        "is_slab": false,
        "tax_rate_pct": 20.0
      }
    ]
  },
  "ltcg": {
    "total_gain": 200000.0,
    "total_tax": 9375.0,
    "ltcg_exemption_used": 125000.0,
    "has_slab_items": false,
    "assets": [
      {
        "asset_id": 1,
        "asset_name": "HDFC Bank",
        "asset_type": "STOCK_IN",
        "gain": 150000.0,
        "tax_estimate": 3125.0,
        "is_slab": false,
        "tax_rate_pct": 12.5,
        "ltcg_exempt_eligible": true
      }
    ]
  },
  "interest": {
    "total_interest": 25000.0,
    "total_tax": 7500.0,
    "slab_rate_pct": 30.0,
    "assets": [
      {
        "asset_id": 10,
        "asset_name": "SBI FD 2024",
        "asset_type": "FD",
        "interest": 15000.0,
        "tax_estimate": 4500.0
      }
    ]
  }
}
```

An asset can appear in both `stcg.assets` and `ltcg.assets` if it has both ST and LT gains in the FY.

LTCG exemption (Section 112A, 1.25L) is applied once across all exempt-eligible assets, not per-asset. The `ltcg_exemption_used` field is at the `ltcg` level.

### 7. Frontend — Tax Page Redesign

#### Page Layout

```
Tax Summary                                          [FY dropdown]

Capital Gains — FY {fy}
┌─────────────────────────────────────────────────────────────────┐
│ SHORT-TERM CAPITAL GAINS                                        │
│                                                                 │
│ Asset               Type        Gain/Loss    Tax Rate  Tax Est. │
│ HDFC Bank           Stock IN    +30,000      20%       6,000    │
│ Motilal S&P 500     MF          +15,000      slab      4,500    │
│ ─────────────────────────────────────────────────────────────── │
│ Total STCG                      +45,000                9,000    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ LONG-TERM CAPITAL GAINS                    Exemption: ₹1,25,000│
│                                                                 │
│ Asset               Type        Gain/Loss    Tax Rate  Tax Est. │
│ HDFC Bank           Stock IN    +1,50,000    12.5%     3,125    │
│ Gold ETF            Gold        +50,000      12.5%     6,250    │
│ ─────────────────────────────────────────────────────────────── │
│ Total LTCG                      +2,00,000              9,375    │
└─────────────────────────────────────────────────────────────────┘

Interest Income — FY {fy}
┌─────────────────────────────────────────────────────────────────┐
│ INTEREST INCOME                              Slab rate: 30%     │
│                                                                 │
│ Asset               Type        Interest              Tax Est.  │
│ SBI FD 2024         FD          15,000                4,500     │
│ HDFC RD             RD          10,000                3,000     │
│ ─────────────────────────────────────────────────────────────── │
│ Total                           25,000                7,500     │
└─────────────────────────────────────────────────────────────────┘

Unrealised Gains (unchanged)
Tax-Loss Harvesting (unchanged)
```

#### Changes from Current

1. Remove the 4 summary stat cards at the top
2. Remove asset_class-level grouping and expand/collapse — replaced by flat asset lists under STCG / LTCG
3. Both STCG and LTCG sections are always expanded, showing all contributing assets directly
4. Interest Income (FD/RD) is a completely separate card, not under Capital Gains
5. Each asset row shows the applicable tax rate (`20%`, `12.5%`, `slab`)
6. Asset names link to `/assets/{id}` (existing behavior preserved)
7. LTCG section shows the Section 112A exemption used at the section level
8. Slab rate footnote appears when any slab-rate items exist

#### Unrealised Gains and Tax-Loss Harvesting

No changes to these sections.

### 8. Files Changed

#### Backend — New/Modified
| File | Change |
|---|---|
| `config/tax_rates/2024-25.yaml` | Rewrite: remove FD/RD/PPF/EPF/NPS/SGB; add hierarchical structure |
| `config/tax_rates/2025-26.yaml` | Same |
| `config/tax_rates/2026-27.yaml` | Same |
| `engine/tax_engine.py` | Replace `TaxRatePolicy`/`TaxRate` with `TaxRuleResolver`/`ResolvedTaxRule`; remove hardcoded constants and functions |
| `services/tax/strategies/base.py` | Update `TaxGainsStrategy.compute()` signature (add `fy` param); update registry to support instance registration |
| `services/tax/strategies/fifo_base.py` | Rewrite: remove ClassVars, inject resolver, per-lot rule resolution |
| `services/tax/strategies/real_estate.py` | Inject resolver for rate lookups instead of hardcoded `LTCG_RATE` |
| `services/tax/strategies/accrued_interest.py` | Update `compute()` signature (add `fy` param, ignore it) |
| `services/tax_service.py` | Restructure `get_tax_summary()` to return stcg/ltcg/interest split; update `_build_lots_for_asset()` to use resolver for stcg_days |
| `api/dependencies.py` | Wire `TaxRuleResolver`, register strategy instances |
| `schemas/responses/tax.py` | New response models for restructured API |

#### Backend — Deleted
| File | Reason |
|---|---|
| `services/tax/strategies/indian_equity.py` | Absorbed into config-driven FifoTaxGainsStrategy |
| `services/tax/strategies/foreign_equity.py` | Same |
| `services/tax/strategies/gold.py` | Same |
| `services/tax/strategies/debt_mf.py` | Same |

#### Frontend — Modified
| File | Change |
|---|---|
| `app/tax/page.tsx` | Redesign: remove stat cards, STCG/LTCG/Interest sections, flat asset lists |
| `types/index.ts` (or wherever `TaxSummaryResponse` lives) | Update types to match new API shape |
| `lib/api.ts` | Update if response type changed |

### 9. Testing Strategy

- **TaxRuleResolver unit tests**: resolution chain, override merging, epoch matching, ISIN matching, missing FY/asset_type errors, default propagation
- **FifoTaxGainsStrategy tests**: per-lot rule resolution with mixed buy dates, ISIN overrides, slab rate handling
- **TaxService integration tests**: STCG/LTCG/interest split, Section 112A exemption across assets, FD/RD separated correctly
- **API tests**: response shape validation for new structure
- **Existing tests**: update to match new `compute()` signature and response shape
