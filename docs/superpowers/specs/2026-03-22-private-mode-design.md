# Private Mode — Design Spec

**Date:** 2026-03-22
**Status:** Approved

---

## Overview

A toggle in the top navigation bar that masks all raw INR monetary values with `*****` across every page, while keeping percentage values (XIRR, returns %) visible. State persists in `localStorage`. Exiting private mode requires a confirmation dialog.

---

## Requirements

- Single toggle button in the nav bar (right end of tab row)
- When **on**: all `formatINR` / `formatINR2` outputs replaced with `*****`
- When **off**: all values shown normally
- `formatPct`, `formatXIRR`, `formatGain`, `formatDate` — **unaffected**
- Chart tooltips masked (see note on chart files below)
- Persists across page refreshes via `localStorage` key `privateMode`
- Turning **off** requires `window.confirm("Exit private mode? Your portfolio values will be visible.")`
- Turning **on** is instant (no confirm)

---

## Architecture

### 1. `frontend/context/PrivateModeContext.tsx` (new file)

Must begin with `'use client'` — uses `localStorage` on mount and `window.confirm` in `toggle()`, both browser-only APIs.

```
PrivateModeContext
  isPrivate: boolean
  toggle(): void
```

- On mount: reads `localStorage.getItem('privateMode') === 'true'`
- `toggle()`:
  - If currently **off** → set `isPrivate = true`, write `localStorage.setItem('privateMode', 'true')`
  - If currently **on** → show `window.confirm(...)`, if confirmed set `isPrivate = false`, write `localStorage.setItem('privateMode', 'false')`
- Export `PrivateModeProvider` and `usePrivateMode` hook

### 2. `frontend/hooks/usePrivateMoney.ts` (new file)

```ts
function usePrivateMoney(): {
  formatINR: (amount: number) => string
  formatINR2: (amount: number) => string
}
```

- Reads `isPrivate` from `PrivateModeContext`
- Returns `() => '*****'` for both when `isPrivate === true`
- Returns the real `formatINR` / `formatINR2` from `lib/formatters.ts` when `false`

### 3. `frontend/app/layout.tsx` (modified)

Wrap `<body>` contents in `<PrivateModeProvider>`:

```tsx
<PrivateModeProvider>
  <TabNav />
  <main>…</main>
</PrivateModeProvider>
```

### 4. `frontend/app/TabNavClient.tsx` (modified)

- Import `usePrivateMode`
- Add eye / eye-slash icon button at the right end of the nav after the tab links
- **Private off:** eye icon, `text-secondary` style
- **Private on:** eye-slash icon, `bg-accent-subtle text-accent` style (matches active tab pill)
- On click: calls `toggle()`

Eye icons: use inline SVG (no new icon library dependency).

### 5. Components updated to use `usePrivateMoney`

All components that currently call `formatINR` or `formatINR2` switch to the hook. Each gets `'use client'` added if not already present.

| File | Already `'use client'`? |
|---|---|
| `components/ui/AssetSummaryCards.tsx` | No — add it |
| `components/domain/HoldingsTable.tsx` | No — add it |
| `components/charts/NetWorthChart.tsx` | Yes — but uses local `formatINRCompact`, not `formatINR`; consume `usePrivateMode` directly and return `'*****'` when on |
| `components/charts/AssetTypeDonut.tsx` | Yes — same local `formatINRCompact` pattern |
| `components/charts/AllocationDonut.tsx` | Yes — same local `formatINRCompact` pattern |
| `components/domain/TaxLotTable.tsx` | No — add it |
| `components/domain/FDDetailCard.tsx` | No — add it |
| `components/domain/GoalCard.tsx` | No — add it |
| `app/page.tsx` (overview) | Yes |
| `app/assets/[id]/page.tsx` | Yes |
| `app/tax/page.tsx` | Yes |
| `app/goals/[id]/page.tsx` | Yes |

---

## Confirm Dialog

Text: `"Exit private mode? Your portfolio values will be visible."`
Implementation: `window.confirm(...)` — no custom modal needed.

---

## Non-Goals

- No backend changes
- No server-side rendering of masked values
- No per-page granularity (it's all-or-nothing globally)
- No blur/fade animation (straight `*****` replacement)
