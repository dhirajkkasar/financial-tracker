# Returns Service Strategy Pattern Migration

## Overview

Migrate the legacy `ReturnsService` from ad-hoc if-else dispatching to a fully strategy-based architecture. This involves:
- Removing 7 major if-else chains from the legacy service
- Wiring the new strategy service into API endpoints
- Extending the strategy registry pattern to handle portfolio-level aggregations
- Consolidating SGB handling into a proper strategy (with lot engine support)
- Removing NPS asset class override logic (now handled at import time)
- Ensuring comprehensive test coverage across all asset types

## Current State

### Legacy Service Issues
- **Location:** `backend/app/services/returns_service.py` (~1,020 lines)
- **If-else Chains:** 7 major chains across asset type dispatch, MF snapshot logic, FD/RD type handling, SGB special case, allocation overrides, portfolio XIRR building
- **Duplication:** Parallel implementation exists in strategy layer; both services coexist

### Existing Strategy Implementation
- **Location:** `backend/app/services/returns/`
- **Architecture:** Template method pattern with 12 concrete asset-type strategies
- **Strategies:** STOCK_IN, STOCK_US, RSU, MF, NPS, GOLD, SGB, PPF, REAL_ESTATE, FD, RD, EPF
- **Test Coverage:** 558 lines in `test_returns_strategies.py`; all 12 asset types covered

### API Integration Gap
- API endpoints (`backend/app/api/returns.py`) still use legacy service
- Strategy service wired in dependencies but not used by API
- Response schemas differ: legacy returns raw dict; strategy uses Pydantic `AssetReturnsResponse`

### Portfolio-Level Methods
Currently in legacy service, not yet in strategy layer:
- `get_asset_lots()` — compute FIFO lots for a single asset
- `get_breakdown()` — portfolio breakdown by asset type (5 metrics per type)
- `get_allocation()` — asset class allocation percentages (with NPS → DEBT override)
- `get_gainers()` — top N assets by P&L
- `get_overview()` — high-level portfolio metrics (invested, current, P&L, allocation)

## Decisions Made

1. **SGB Strategy:** Handle in dedicated strategy with full lot engine support (no skipping).
2. **NPS Asset Class:** Remove override logic; NPS is imported with DEBT classification already.
3. **Extensibility:** Expand strategy registry pattern to support portfolio-level orchestration methods.

## Implementation Plan

### Phase 1: Prepare Strategy Layer (No Breaking Changes)

#### 1.1 Verify SGB Lot Engine Support
- **File:** `backend/app/services/returns/strategies/asset_types/sgb.py`
- **Task:** Confirm SGB inherits from `MarketBasedStrategy` with `stcg_days=1095`
- **Validation:** Existing test `test_sgb_strategy()` should verify lot computation works
- **Expected:** SGB computes units × price + FIFO lots (same as GOLD)

#### 1.2 Remove NPS Asset Class Override Logic
- **File:** `backend/app/services/returns_service.py` (lines 868-881)
- **Remove:** `_ALLOCATION_TYPE_OVERRIDE` dict and override logic in `get_allocation()`
- **Assumption:** NPS records are imported with `asset_class=DEBT` (not EQUITY)
- **Validation:** Check `backend/app/importers/` for NPS importer to confirm classification

#### 1.3 Extend Strategy Registry for Portfolio Methods
- **File:** `backend/app/services/returns/strategies/registry.py`
- **Add:** New method `get_portfolio_strategies()` → returns list of all available strategy instances
- **Purpose:** Enable portfolio-level aggregation without asset type dispatch logic
- **Implementation:**
  ```python
  def get_portfolio_strategies(self) -> list[AssetReturnsStrategy]:
      """Return all registered strategy instances (for portfolio-level aggregation)."""
      return [cls() for cls in self._STRATEGY_REGISTRY.values()]
  ```

### Phase 2: Implement Portfolio Orchestrator Service

Create a new service to handle portfolio-level aggregations using the strategy registry.

#### 2.1 Create Portfolio-Level Service
- **File:** `backend/app/services/returns/portfolio_returns_service.py` (new)
- **Class:** `PortfolioReturnsService`
- **Dependency Injection:** Receives `IUnitOfWorkFactory` and `IReturnsStrategyRegistry`
- **Methods to Implement:**
  - `get_asset_lots(asset_id: int) → dict` — delegate to strategy's `compute_lots()`
  - `get_breakdown() → dict` — aggregate breakdown by asset type across all active assets
  - `get_allocation() → dict` — compute asset class percentages
  - `get_gainers(n: int) → dict` — top N assets by current P&L
  - `get_overview(asset_types: list[str] | None) → dict` — portfolio-level metrics

#### 2.2 Response Schema Unification
- **File:** `backend/app/schemas/responses/returns.py`
- **Task:** Ensure all portfolio method responses match current API contracts
- **Validation:** Compare with legacy service return values to preserve backward compatibility

### Phase 3: Migrate API Endpoints

#### 3.1 Update Dependency Injection
- **File:** `backend/app/api/returns.py`
- **Replace:** Legacy `ReturnsService` with new `PortfolioReturnsService`
- **Endpoints Affected:**
  - `/assets/{asset_id}/returns` → use strategy service directly
  - `/returns/bulk` → use strategy service for each asset
  - `/assets/{asset_id}/lots` → use portfolio service
  - `/breakdown` → use portfolio service
  - `/allocation` → use portfolio service
  - `/gainers` → use portfolio service
  - `/overview` → use portfolio service

#### 3.2 Route-by-Route Migration
- **Route 1:** `GET /assets/{asset_id}/returns`
  - Current: `ReturnsService.get_asset_returns()`
  - New: Direct strategy dispatch via registry
  
- **Route 2:** `GET /returns/bulk`
  - Current: Loop + legacy service calls
  - New: Loop + strategy registry dispatch
  
- **Route 3:** `GET /assets/{asset_id}/lots`
  - Current: `ReturnsService.get_asset_lots()`
  - New: `PortfolioReturnsService.get_asset_lots()`
  
- **Route 4:** `GET /breakdown`
  - Current: `ReturnsService.get_breakdown()`
  - New: `PortfolioReturnsService.get_breakdown()`
  
- **Route 5:** `GET /allocation`
  - Current: `ReturnsService.get_allocation()` (with NPS override)
  - New: `PortfolioReturnsService.get_allocation()` (no override)
  
- **Route 6:** `GET /gainers`
  - Current: `ReturnsService.get_gainers(n)`
  - New: `PortfolioReturnsService.get_gainers(n)`
  
- **Route 7:** `GET /overview`
  - Current: `ReturnsService.get_overview(asset_types)`
  - New: `PortfolioReturnsService.get_overview(asset_types)`

### Phase 4: Update and Consolidate Tests

**NOTE** FULL TEST SUITE CAN BE RUN BY COMMAND `cd backend && source .venv/bin/activate && pytest`

#### 4.1 Migrate Legacy Tests
- **Source File:** `backend/tests/unit/test_mf_returns.py` (362 lines)
- **Target File:** `backend/tests/unit/test_returns_strategies.py` (existing)
- **Tasks:**
  - Move snapshot freshness tests → MF strategy tests
  - Move P&L and XIRR tests → base strategy tests
  - Move bonus unit tests → MF strategy tests
  - Remove duplicate utility functions

#### 4.2 Add Integration Tests for Portfolio Methods
- **File:** `backend/tests/integration/test_returns_api.py` (new or updated)
- **Coverage:**
  - `GET /breakdown` with mixed asset types
  - `GET /allocation` asset class calculation (verify NPS is DEBT)
  - `GET /gainers` sorting and filtering
  - `GET /overview` aggregate calculations
  - Error cases (no assets, invalid asset_id)

#### 4.3 Add E2E Test for SGB Lot Engine
- **File:** `backend/tests/integration/test_returns_api.py`
- **Test:** Verify SGB correctly computes FIFO lots (not skipped)
- **Scenario:** Create SGB holdings with buy/sell transactions; verify lots show in response

#### 4.4 Verify All Asset Types Via API
- **File:** `backend/tests/integration/test_returns_api.py`
- **Test:** Call `GET /assets/{asset_id}/returns` for all 12 asset types
- **Purpose:** End-to-end validation that strategy dispatch works through API

### Phase 5: Remove Legacy Code

#### 5.1 Deprecate Legacy Service
- **File:** `backend/app/services/returns_service.py`
- **Action:** Remove the service and its tests completely.
- **Validation:** Run full test suite by `cd backend && source .venv/bin/activate && pytest` to ensure nothing is breaking

#### 5.2 Remove Asset Class Override Logic
- **File:** `backend/app/services/returns_service.py` (if still exists)
- **Remove:** `_ALLOCATION_TYPE_OVERRIDE` dict
- **Affected Code:** `get_allocation()` method, allocation response building

#### 5.3 Clean Up If-Else Chains
Once all tests pass on new implementation, verify these chains are fully removed from active code:
- Asset type dispatcher (lines 48-63)
- MF snapshot age check (lines 125-131) — now in MF strategy
- FD/RD type dispatch (lines 397-410) — now in FD/RD strategies
- SGB skip logic (lines 552-569) — now in SGB strategy with lot support
- Allocation override (lines 868-881) — removed entirely
- Asset type in portfolio XIRR (lines 971-1007) — now in portfolio service
- Asset type for outflow-only (lines 1028-1053) — now in respective strategies

## Validation Checklist

### Code Quality
- [ ] All 7 if-else chains removed from legacy service or replaced with strategy dispatch
- [ ] No duplicate method implementations between old and new services
- [ ] Strategy registry fully used by API endpoints
- [ ] Zero hardcoded asset type strings in service layer (all via registry)

### Test Coverage
- [ ] All 12 asset types tested end-to-end via API
- [ ] SGB lot engine test confirms FIFO computation (not skipped)
- [ ] NPS asset class verified as DEBT in allocation breakdown
- [ ] Portfolio methods (breakdown, allocation, gainers, overview) tested with varied portfolios
- [ ] Edge cases: empty portfolio, single asset, mixed active/inactive assets
- [ ] Test coverage >= 85% for returns service module

### Backward Compatibility
- [ ] API response schemas unchanged (dict structure preserved)
- [ ] All endpoints return identical data as before migration
- [ ] Error messages and codes unchanged
- [ ] Pagination behavior preserved

### Performance
- [ ] Portfolio methods don't regress on response time (< 500ms for 100+ assets)
- [ ] Strategy registry lookup doesn't introduce latency (lazy-load validates)

## Success Criteria

1. ✅ All 7 if-else chains fully removed or replaced with strategy registry
2. ✅ Legacy service deprecated and not called by any API endpoint
3. ✅ All tests pass (unit, integration, and E2E)
4. ✅ SGB handles lots correctly (not skipped)
5. ✅ NPS asset class override removed; verify import handles it
6. ✅ Portfolio orchestrator service fully implements aggregation methods
7. ✅ Zero breaking changes to API contracts
8. ✅ Code coverage maintained or improved
