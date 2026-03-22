# Private Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a nav toggle that replaces all INR monetary values with `*****` site-wide while keeping percentage/XIRR values visible, persisting state in localStorage.

**Architecture:** A React Context (`PrivateModeContext`) wraps the entire app in `layout.tsx`. A `usePrivateMoney` hook reads the context and returns masked or real formatters. All components that display INR values switch from direct `formatINR` imports to the hook. Chart components with local `formatINRCompact` functions read `isPrivate` from context directly.

**Tech Stack:** Next.js App Router, React Context, localStorage, inline SVG icons (no new dependencies)

---

## File Map

| Action | File | Purpose |
|---|---|---|
| **Create** | `frontend/context/PrivateModeContext.tsx` | Context + provider + `usePrivateMode` hook |
| **Create** | `frontend/hooks/usePrivateMoney.ts` | Returns masked `formatINR`/`formatINR2` |
| **Modify** | `frontend/app/layout.tsx` | Wrap body in `PrivateModeProvider` |
| **Modify** | `frontend/app/TabNavClient.tsx` | Add eye/eye-slash toggle button |
| **Modify** | `frontend/components/ui/AssetSummaryCards.tsx` | Add `'use client'` + use hook |
| **Modify** | `frontend/components/domain/HoldingsTable.tsx` | Already `'use client'` — use hook |
| **Modify** | `frontend/components/charts/NetWorthChart.tsx` | Use `usePrivateMode` to gate `formatINRCompact` |
| **Modify** | `frontend/components/charts/AssetTypeDonut.tsx` | Same |
| **Modify** | `frontend/components/charts/AllocationDonut.tsx` | Same |
| **Modify** | `frontend/components/domain/TaxLotTable.tsx` | Already `'use client'` — use hook; pass formatter as prop to `GainCell` |
| **Modify** | `frontend/components/domain/FDDetailCard.tsx` | Already `'use client'` — use hook |
| **Modify** | `frontend/components/domain/GoalCard.tsx` | Add `'use client'` + use hook |
| **Modify** | `frontend/app/page.tsx` | Use hook |
| **Modify** | `frontend/app/assets/[id]/page.tsx` | Use hook |
| **Modify** | `frontend/app/tax/page.tsx` | Use hook |
| **Modify** | `frontend/app/goals/[id]/page.tsx` | Use hook |

---

## Task 1: Create PrivateModeContext

**Files:**
- Create: `frontend/context/PrivateModeContext.tsx`

- [ ] **Step 1: Create the context file**

```tsx
'use client'
import { createContext, useContext, useState, useEffect } from 'react'

interface PrivateModeContextValue {
  isPrivate: boolean
  toggle: () => void
}

const PrivateModeContext = createContext<PrivateModeContextValue>({
  isPrivate: false,
  toggle: () => {},
})

export function PrivateModeProvider({ children }: { children: React.ReactNode }) {
  const [isPrivate, setIsPrivate] = useState(false)

  useEffect(() => {
    setIsPrivate(localStorage.getItem('privateMode') === 'true')
  }, [])

  function toggle() {
    if (isPrivate) {
      const confirmed = window.confirm('Exit private mode? Your portfolio values will be visible.')
      if (!confirmed) return
      setIsPrivate(false)
      localStorage.setItem('privateMode', 'false')
    } else {
      setIsPrivate(true)
      localStorage.setItem('privateMode', 'true')
    }
  }

  return (
    <PrivateModeContext.Provider value={{ isPrivate, toggle }}>
      {children}
    </PrivateModeContext.Provider>
  )
}

export function usePrivateMode() {
  return useContext(PrivateModeContext)
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npm run build 2>&1 | tail -20
```
Expected: no TypeScript errors related to `PrivateModeContext.tsx`

- [ ] **Step 3: Commit**

```bash
git add frontend/context/PrivateModeContext.tsx
git commit -m "feat(private-mode): add PrivateModeContext with localStorage persistence"
```

---

## Task 2: Create usePrivateMoney hook

**Files:**
- Create: `frontend/hooks/usePrivateMoney.ts`

- [ ] **Step 1: Create the hook**

```ts
import { usePrivateMode } from '@/context/PrivateModeContext'
import { formatINR as _formatINR, formatINR2 as _formatINR2 } from '@/lib/formatters'

const MASK = '*****'

export function usePrivateMoney() {
  const { isPrivate } = usePrivateMode()
  return {
    formatINR: isPrivate ? (_: number) => MASK : _formatINR,
    formatINR2: isPrivate ? (_: number) => MASK : _formatINR2,
  }
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npm run build 2>&1 | tail -20
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/hooks/usePrivateMoney.ts
git commit -m "feat(private-mode): add usePrivateMoney hook"
```

---

## Task 3: Wire provider into layout + add nav toggle button

**Files:**
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/app/TabNavClient.tsx`

- [ ] **Step 1: Wrap layout body with PrivateModeProvider**

In `frontend/app/layout.tsx`, add the import and wrap `<TabNav />` and `<main>`:

```tsx
import type { Metadata } from 'next'
import { DM_Sans, DM_Serif_Display, DM_Mono } from 'next/font/google'
import './globals.css'
import { TabNav } from './TabNav'
import { PrivateModeProvider } from '@/context/PrivateModeContext'

// ... font declarations unchanged ...

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${dmSans.variable} ${dmSerifDisplay.variable} ${dmMono.variable}`}>
      <body className="font-sans bg-page text-primary min-h-screen">
        <PrivateModeProvider>
          <TabNav />
          <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        </PrivateModeProvider>
      </body>
    </html>
  )
}
```

- [ ] **Step 2: Add toggle button to TabNavClient**

Replace the full content of `frontend/app/TabNavClient.tsx`:

```tsx
'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { NAV_TABS } from '@/constants'
import { usePrivateMode } from '@/context/PrivateModeContext'

type Tab = typeof NAV_TABS[number]

export function TabNavClient({ tabs }: { tabs: readonly Tab[] }) {
  const pathname = usePathname()
  const { isPrivate, toggle } = usePrivateMode()

  return (
    <>
      {tabs.map((tab) => {
        const active = tab.href === '/' ? pathname === '/' : pathname.startsWith(tab.href)
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.08em] transition-colors ${
              active
                ? 'bg-accent-subtle text-accent'
                : 'text-secondary hover:bg-border hover:text-primary'
            }`}
          >
            {tab.label}
          </Link>
        )
      })}
      <button
        onClick={toggle}
        title={isPrivate ? 'Exit private mode' : 'Enter private mode'}
        className={`ml-auto rounded-md px-2 py-1.5 transition-colors ${
          isPrivate
            ? 'bg-accent-subtle text-accent'
            : 'text-secondary hover:bg-border hover:text-primary'
        }`}
      >
        {isPrivate ? (
          // Eye-slash icon
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
            <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
            <line x1="1" y1="1" x2="23" y2="23"/>
          </svg>
        ) : (
          // Eye icon
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
        )}
      </button>
    </>
  )
}
```

- [ ] **Step 3: Build and manually verify**

```bash
cd frontend && npm run build 2>&1 | tail -20
```
Expected: clean build. Open browser at `http://localhost:3000` — eye button should appear at right end of nav. Clicking it should turn it highlighted. Clicking again should show confirm dialog.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/layout.tsx frontend/app/TabNavClient.tsx
git commit -m "feat(private-mode): wire provider into layout and add nav toggle button"
```

---

## Task 4: Update AssetSummaryCards and HoldingsTable

**Files:**
- Modify: `frontend/components/ui/AssetSummaryCards.tsx`
- Modify: `frontend/components/domain/HoldingsTable.tsx`

- [ ] **Step 1: Update AssetSummaryCards**

Add `'use client'` as the first line, then replace the `formatINR` import with the hook:

```tsx
'use client'
import { OverviewReturns } from '@/types'
import { StatCard } from './StatCard'
import { StatCardSkeleton } from './Skeleton'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'
import { formatXIRR, formatPct } from '@/lib/formatters'

// ... rest of interface unchanged ...

export function AssetSummaryCards({ data, loading }: AssetSummaryCardsProps) {
  const { formatINR } = usePrivateMoney()
  // ... rest of component unchanged, formatINR calls now use the hook version ...
```

- [ ] **Step 2: Update HoldingsTable**

`HoldingsTable` has a module-scope sub-component `PnlCell` (line 48) that calls `formatINR` directly — same pattern as `GainCell`/`GainAmt`. Add a `fmt` prop to `PnlCell` and pass the hook formatter from `HoldingsTable`. File already has `'use client'`.

```tsx
// 1. Remove formatINR/formatINR2 from formatters import:
import { formatPct } from '@/lib/formatters'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'

// 2. Change PnlCell to accept fmt prop:
function PnlCell({ amount, pct, dim, fmt }: { amount: number | null; pct?: number | null; dim?: boolean; fmt: (n: number) => string }) {
  if (amount == null) return <span className="text-tertiary">—</span>
  const pos = amount >= 0
  const colorClass = dim
    ? 'text-tertiary'
    : (pos ? 'text-gain' : 'text-loss')
  return (
    <div className={`text-right font-mono ${colorClass}`}>
      <div className="text-sm">{pos ? '+' : ''}{fmt(amount)}</div>
      {pct != null && <div className="text-[11px] opacity-70">{formatPct(pct)}</div>}
    </div>
  )
}

// 3. Inside HoldingsTable component body add:
const { formatINR, formatINR2 } = usePrivateMoney()

// 4. Pass fmt to both PnlCell call sites (lines 252 and 257):
// <PnlCell amount={currentPnl} pct={currentPct} fmt={formatINR} />
// <PnlCell amount={allTimePnl} dim={isInactive} fmt={formatINR} />
// All other direct formatINR/formatINR2 calls (lines 231, 236, 248, 276, 279) are inside
// HoldingsTable's body and will pick up the hook-provided formatter automatically.
```

- [ ] **Step 3: Build and verify**

```bash
cd frontend && npm run build 2>&1 | tail -20
```
Open browser — enable private mode, go to any listing page (e.g. `/stocks`). Invested, Current Value, P&L columns should show `*****`. XIRR% and return% should still show real values.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/ui/AssetSummaryCards.tsx frontend/components/domain/HoldingsTable.tsx
git commit -m "feat(private-mode): mask money values in AssetSummaryCards and HoldingsTable"
```

---

## Task 5: Update chart components (formatINRCompact)

These three files use a **local** `formatINRCompact` function, not the shared `formatINR`. The fix is to read `isPrivate` from context and short-circuit the local formatter.

**Files:**
- Modify: `frontend/components/charts/NetWorthChart.tsx`
- Modify: `frontend/components/charts/AssetTypeDonut.tsx`
- Modify: `frontend/components/charts/AllocationDonut.tsx`

- [ ] **Step 1: Update NetWorthChart**

Add the import and wrap `formatINRCompact`:

```tsx
// Add import at top (file already has 'use client'):
import { usePrivateMode } from '@/context/PrivateModeContext'

// Inside the NetWorthTooltip component, add:
const { isPrivate } = usePrivateMode()
// Then replace: formatINRCompact(value)
// With:         isPrivate ? '*****' : formatINRCompact(value)

// Inside the main NetWorthChart component, add:
const { isPrivate } = usePrivateMode()
// Replace the YAxis tickFormatter prop:
// tickFormatter={(v) => formatINRCompact(v)}
// With:
// tickFormatter={(v) => isPrivate ? '*****' : formatINRCompact(v)}
```

- [ ] **Step 2: Update AssetTypeDonut**

```tsx
// Add import (file already has 'use client'):
import { usePrivateMode } from '@/context/PrivateModeContext'

// Inside DonutTooltip, add:
const { isPrivate } = usePrivateMode()
// Replace: formatINRCompact(value)
// With:    isPrivate ? '*****' : formatINRCompact(value)
```

- [ ] **Step 3: Update AllocationDonut**

`AllocationDonut` has the same `DonutTooltip` + `formatINRCompact` pattern as `AssetTypeDonut`:

```tsx
// Add import (file already has 'use client'):
import { usePrivateMode } from '@/context/PrivateModeContext'

// Inside DonutTooltip, add:
const { isPrivate } = usePrivateMode()
// Replace: formatINRCompact(value)
// With:    isPrivate ? '*****' : formatINRCompact(value)
```

- [ ] **Step 4: Build and verify**

```bash
cd frontend && npm run build 2>&1 | tail -20
```
Enable private mode, go to Overview page — hover over Net Worth chart tooltip and donut chart tooltip. Values should show `*****`. Y-axis labels should show `*****`.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/charts/NetWorthChart.tsx \
        frontend/components/charts/AssetTypeDonut.tsx \
        frontend/components/charts/AllocationDonut.tsx
git commit -m "feat(private-mode): mask chart tooltip and axis INR values"
```

---

## Task 6: Update domain components

**Files:**
- Modify: `frontend/components/domain/TaxLotTable.tsx`
- Modify: `frontend/components/domain/FDDetailCard.tsx`
- Modify: `frontend/components/domain/GoalCard.tsx`

For all three: `HoldingsTable`, `TaxLotTable`, and `FDDetailCard` already have `'use client'`. `GoalCard` does not — add it. Remove `formatINR`/`formatINR2` from the `formatters` import, add `usePrivateMoney`, and destructure inside the component.

**Important — `TaxLotTable` has a module-scope sub-component `GainCell` that calls `formatINR` directly.** Hooks cannot be called at module scope. Fix: add a `fmt` prop to `GainCell` and pass the hook formatter down from `TaxLotTable`.

- [ ] **Step 1: Update TaxLotTable**

`GainCell` is defined at module scope (line 22) and calls `formatINR` directly. Change its signature to accept `fmt` as a prop, then pass the hook formatter from `TaxLotTable`:

```tsx
// 1. Change GainCell signature to accept fmt prop:
function GainCell({ value, fmt }: { value: number | null; fmt: (n: number) => string }) {
  if (value === null) return <span className="text-tertiary">—</span>
  const pos = value >= 0
  return (
    <span className={`font-mono ${pos ? 'text-gain' : 'text-loss'}`}>
      {pos ? '+' : ''}{fmt(value)}
    </span>
  )
}

// 2. Remove formatINR from formatters import, add usePrivateMoney import:
import { formatDate } from '@/lib/formatters'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'

// 3. Inside TaxLotTable component body, add:
const { formatINR } = usePrivateMoney()

// 4. Everywhere <GainCell value={...} /> is rendered inside TaxLotTable, add fmt prop:
// <GainCell value={...} fmt={formatINR} />
```

- [ ] **Step 2: Update FDDetailCard**

```tsx
// Already has 'use client'. Remove formatINR/formatINR2 from formatters import:
import { formatDate, formatPct } from '@/lib/formatters'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'

export function FDDetailCard(...) {
  const { formatINR, formatINR2 } = usePrivateMoney()
  // rest unchanged
}
```

- [ ] **Step 3: Update GoalCard**

```tsx
'use client'
// Remove formatINR from formatters import
import { usePrivateMoney } from '@/hooks/usePrivateMoney'

export function GoalCard(...) {
  const { formatINR } = usePrivateMoney()
  // rest unchanged
}
```

- [ ] **Step 4: Build and verify**

```bash
cd frontend && npm run build 2>&1 | tail -20
```
Enable private mode, visit `/tax`, `/deposits` (FD detail card), `/goals` — all INR values should show `*****`.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/domain/TaxLotTable.tsx \
        frontend/components/domain/FDDetailCard.tsx \
        frontend/components/domain/GoalCard.tsx
git commit -m "feat(private-mode): mask money in TaxLotTable, FDDetailCard, GoalCard"
```

---

## Task 7: Update page-level files

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/assets/[id]/page.tsx`
- Modify: `frontend/app/tax/page.tsx`
- Modify: `frontend/app/goals/[id]/page.tsx`

All four are already `'use client'`. Same pattern: replace `formatINR`/`formatINR2` from formatters import with `usePrivateMoney` hook.

- [ ] **Step 1: Update app/page.tsx (overview)**

```tsx
// Remove formatINR from: import { formatINR, ... } from '@/lib/formatters'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'

export default function OverviewPage() {
  const { formatINR } = usePrivateMoney()
  // rest unchanged
}
```

- [ ] **Step 2: Update app/assets/[id]/page.tsx**

```tsx
// Remove formatINR/formatINR2 from formatters import
import { usePrivateMoney } from '@/hooks/usePrivateMoney'

export default function AssetDetailPage(...) {
  const { formatINR, formatINR2 } = usePrivateMoney()
  // rest unchanged
}
```

- [ ] **Step 3: Update app/tax/page.tsx**

`tax/page.tsx` has two module-scope helper components — `GainAmt` (line 80) and `TaxAmt` (line 85) — that call `formatINR` directly. Same fix as `GainCell` in TaxLotTable: add a `fmt` prop to each, pass the hook formatter from `TaxPage`.

```tsx
// 1. Remove formatINR from formatters import:
import { ASSET_TYPE_LABELS } from '@/constants'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'

// 2. Change GainAmt to accept fmt prop:
function GainAmt({ value, fmt }: { value: number; fmt: (n: number) => string }) {
  if (value === 0) return <span className="text-tertiary">—</span>
  return <span className={`font-mono ${value >= 0 ? 'text-gain' : 'text-loss'}`}>{fmt(value)}</span>
}

// 3. Change TaxAmt to accept fmt prop:
function TaxAmt({ value, hasSlab, fmt }: { value: number | null; hasSlab?: boolean; fmt: (n: number) => string }) {
  const parts = []
  if (value !== null && value !== 0) parts.push(<span key="v" className="font-mono text-loss">{fmt(value)}</span>)
  if (hasSlab) parts.push(<span key="s" className="ml-1 text-[10px] text-tertiary">+slab</span>)
  if (parts.length === 0) return <span className="text-tertiary">{hasSlab ? <span className="text-[10px] text-tertiary">slab</span> : '—'}</span>
  return <>{parts}</>
}

// 4. Inside TaxPage, get formatter from hook and pass to every GainAmt/TaxAmt:
export default function TaxPage() {
  const { formatINR } = usePrivateMoney()
  // ...
  // All <GainAmt value={...} /> become <GainAmt value={...} fmt={formatINR} />
  // All <TaxAmt value={...} /> become <TaxAmt value={...} fmt={formatINR} />
}
```

- [ ] **Step 4: Update app/goals/[id]/page.tsx**

```tsx
// Remove formatINR from formatters import
import { usePrivateMoney } from '@/hooks/usePrivateMoney'

export default function GoalDetailPage(...) {
  const { formatINR } = usePrivateMoney()
  // rest unchanged
}
```

- [ ] **Step 5: Final build + full verification**

```bash
cd frontend && npm run build 2>&1 | tail -30
```
Expected: clean build with no errors.

Manual verification checklist:
- [ ] Enable private mode — eye-slash icon highlighted in nav
- [ ] Overview page: portfolio value, invested, P&L → `*****`; XIRR % and return % still visible
- [ ] Overview breakdown table: all INR columns → `*****`
- [ ] Net Worth chart: Y-axis and tooltip → `*****`
- [ ] Donut chart tooltips → `*****`
- [ ] Stocks / MF / any listing page: stat cards and holdings table → `*****`
- [ ] `/deposits`: FD detail card values → `*****`
- [ ] `/tax`: lot table amounts → `*****`
- [ ] `/goals`: goal values → `*****`
- [ ] Asset detail page `/assets/[id]`: all INR → `*****`
- [ ] Refresh page with private mode on → still masked (localStorage persisted)
- [ ] Click eye-slash → confirm dialog appears → cancel → still masked
- [ ] Click eye-slash → confirm → values reappear, button back to eye icon
- [ ] XIRR, return %, allocation % — never masked on any page

- [ ] **Step 6: Commit**

```bash
git add frontend/app/page.tsx \
        frontend/app/assets/[id]/page.tsx \
        frontend/app/tax/page.tsx \
        frontend/app/goals/[id]/page.tsx
git commit -m "feat(private-mode): mask money values in page-level components"
```
