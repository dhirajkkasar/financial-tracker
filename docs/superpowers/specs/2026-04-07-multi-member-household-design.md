# Multi-Member Household Support

## Problem

The financial tracker is single-user — no concept of asset ownership per person. One household has multiple members with separate PANs, investments, and tax obligations. Currently, assets like a spouse's FDs show tax implications for the wrong person. The system needs to track investments per individual while providing a consolidated household view.

## Scope

- 2–4 household members, identified by PAN
- Consolidated portfolio view across selected members
- Per-PAN tax reporting
- Manual member selection during imports (CLI-only)
- No authentication/authorization — single operator managing all members

## Data Model

### New table: `members`

| Column | Type | Constraints |
|---|---|---|
| `id` | INT | PK, auto-increment |
| `pan` | VARCHAR(10) | UNIQUE, NOT NULL |
| `name` | VARCHAR(255) | NOT NULL |
| `is_default` | BOOLEAN | NOT NULL, DEFAULT FALSE — exactly one row TRUE |
| `created_at` | DATETIME | NOT NULL |

### Modified tables

| Table | Change |
|---|---|
| `assets` | Add `member_id INT FK → members.id NOT NULL` |
| `important_data` | Add `member_id INT FK → members.id NOT NULL` |
| `portfolio_snapshots` | Add `member_id INT FK → members.id NOT NULL` |

### Unchanged tables (and why)

| Table | Reason |
|---|---|
| `transactions` | Scoped via `asset.member_id` |
| `valuations` | Scoped via `asset.member_id` |
| `price_cache` | Per-asset-identifier, not per-person |
| `fd_detail` | Scoped via `asset.member_id` |
| `goals` | Household-level; allocations point to assets which carry member context |
| `goal_allocations` | Points to asset (which has member_id) |
| `cas_snapshots` | Scoped via `asset.member_id` |
| `interest_rate` | Global reference data |

### Migration strategy

Single Alembic migration that:

1. Creates `members` table
2. Adds `member_id` column (nullable initially) to `assets`, `important_data`, `portfolio_snapshots`
3. Data migration: creates a default member row — PAN and name are read from environment variables (`DEFAULT_MEMBER_PAN`, `DEFAULT_MEMBER_NAME`) at migration time — backfills all existing rows to that member
4. Sets `member_id` NOT NULL on `assets` and `important_data`

## API Changes

### New endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/members` | List all members (for frontend dropdown) |
| `POST` | `/members` | Add a new member `{pan, name}` |

### Modified endpoints — `member_ids` filter

These endpoints gain an optional `member_ids` query parameter (comma-separated integer IDs). When omitted, data for all members is returned (household view).

| Endpoint | Change |
|---|---|
| `GET /assets` | Filter by `member_ids` |
| `GET /returns/overview` | Filter by `member_ids` |
| `GET /returns/breakdown` | Filter by `member_ids` |
| `GET /overview/allocation` | Filter by `member_ids` |
| `GET /overview/gainers` | Filter by `member_ids` |
| `GET /snapshots` | Aggregate snapshots across selected `member_ids` (SUM by date) |
| `POST /snapshots/take` | Stores one snapshot row per member |

### Modified endpoints — single `member_id` (tax)

Tax is per-PAN. These endpoints require a single `member_id` query parameter. Requests without it are rejected.

| Endpoint | Change |
|---|---|
| `GET /tax/summary?fy=...` | Requires `&member_id=X` |
| `GET /tax/unrealised` | Requires `&member_id=X` |
| `GET /tax/harvest-opportunities` | Requires `&member_id=X` |

### Modified endpoints — import

| Endpoint | Change |
|---|---|
| `POST /import/preview-file` | Add required `member_id` query param |
| `POST /import/commit-file/{id}` | No change — preview carries member_id |

### Asset creation

`POST /assets` request body gains a required `member_id` field.

### Unchanged endpoints

| Endpoint | Reason |
|---|---|
| `GET /assets/{id}/returns` | Asset-level, already scoped |
| `GET /assets/{id}/returns/lots` | Asset-level, already scoped |
| `GET /returns/bulk` | Takes explicit asset_ids |
| `GET /tax/fiscal-years` | Global reference data |
| `GET /prices/*` | Prices are per-asset, not per-person |
| `GET /interest-rates/*` | Global reference data |

## Service Layer Changes

### Repository layer

- `AssetRepository.list()` gains `member_ids: Optional[list[int]]` filter → `WHERE member_id IN (...)`
- `ImportantDataRepository` gains same `member_ids` filtering
- `SnapshotRepository` gains `member_ids` filter with date-level aggregation (`GROUP BY date, SUM(total_value_paise)`)

### Portfolio returns service

`PortfolioReturnsService` methods (`get_breakdown`, `get_allocation`, `get_gainers`, `get_overview`) gain optional `member_ids: Optional[list[int]]` parameter, passed through to `uow.assets.list()`.

No changes to strategy classes, lot engine, XIRR calculations, or any engine code. Filtering happens before assets reach computation.

### Tax service

`TaxService` methods (`get_tax_summary`, `get_unrealised_summary`, `get_harvest_opportunities`) gain required `member_id: int` parameter. Filters assets to that single member before computing.

### Import orchestrator

`ImportOrchestrator.preview()` gains `member_id` parameter. When creating/finding assets during commit, `member_id` is attached. Deduplication unchanged (txn_id is globally unique).

### Snapshot service

`take_snapshot()` iterates all members, stores one row per member per date. Query-time aggregation for combined views.

## CLI Changes

### New command

```
cli.py add-member --pan ABCDE1234F --name "Spouse"
```

Calls `POST /members`.

### Modified import commands

All import commands gain a required `--pan` flag. If omitted, CLI framework prompts for it (argparse/click required argument behavior).

```
cli.py import --pan ABCDE1234F --source cas --file statement.pdf
```

Flow:
1. CLI calls `GET /members`, matches PAN → `member_id`
2. If PAN not found, exits with error: "Member with PAN ABCDE1234F not found. Run `add-member` first."
3. Passes `member_id` to `POST /import/preview-file`

### Snapshot command

`cli.py snapshot` — iterates all members, takes one snapshot per member.

### Unchanged commands

`cli.py refresh-prices` — prices are per-asset-identifier, not per-person.

## Frontend Changes

### Member context (global state)

A `MemberContext` React context holds:
- `members: Member[]` — fetched once from `GET /members` on app load
- `selectedMemberIds: number[]` — current dropdown selection, persisted to `localStorage`

### Multi-select dropdown (header)

- Lives in the top nav/header — persistent across all pages
- Shows member name + masked PAN (e.g. "Dhiraj - XXXX1234F")
- Multi-select checkboxes
- Selecting none = selecting all (household view)
- Selection persisted to `localStorage` for page refresh survival

### Data fetching hooks

All existing hooks (`useReturns`, `useBreakdown`, `useAssets`, etc.) read `selectedMemberIds` from context and append `?member_ids=1,2` to API calls. Selection change triggers refetch.

### Tax page

- **Does not use** the global multi-select dropdown or localStorage state
- Has its own **independent single-select** PAN picker (local component state)
- Defaults to the first member
- All tax API calls use only this local single `member_id`

### Asset list / holdings tables

- Multiple members selected: all assets shown, same stock held by two people = two separate rows. Subtle member badge (e.g. "DK", "SP") to distinguish ownership.
- Single member selected: behaves exactly like today

### Snapshots / networth chart

- Receives pre-aggregated data from backend (summed by date across selected members)
- No frontend aggregation logic needed

## Out of Scope

- Authentication / authorization (remains single-operator)
- Auto-detection of PAN from imported documents (future enhancement)
- PUT/DELETE for members (direct SQL if needed)
- Per-member goals (goals remain household-level)
