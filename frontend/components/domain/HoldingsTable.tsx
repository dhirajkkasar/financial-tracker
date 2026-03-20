'use client'
import { useState } from 'react'
import Link from 'next/link'
import { Asset } from '@/types'
import { formatINR, formatPct } from '@/lib/formatters'
import { ASSET_TYPE_LABELS } from '@/constants'
import { Skeleton } from '@/components/ui/Skeleton'

interface HoldingRow extends Asset {
  current_value?: number
  total_invested?: number
  gain?: number
  xirr?: number | null
  st_unrealised_gain?: number | null
  lt_unrealised_gain?: number | null
  st_realised_gain?: number | null
  lt_realised_gain?: number | null
  taxable_interest?: number | null
  potential_tax_30pct?: number | null
  price_is_stale?: boolean | null
  price_fetched_at?: string | null
  // FD/RD specific
  start_date?: string
  maturity_date?: string
  interest_rate_pct?: number
  fd_type?: string
}

type HoldingsVariant = 'default' | 'fd-tax'

type SortKey =
  | 'name' | 'asset_type' | 'total_invested' | 'current_value'
  | 'current_pnl' | 'alltime_pnl' | 'xirr'
  | 'start_date' | 'maturity_date' | 'interest_rate_pct'
  | 'taxable_interest' | 'potential_tax_30pct'

type SortDir = 'asc' | 'desc'

interface HoldingsTableProps {
  assets: HoldingRow[]
  loading: boolean
  variant?: HoldingsVariant
}

function PnlCell({ amount, pct, dim }: { amount: number | null; pct?: number | null; dim?: boolean }) {
  if (amount == null) return <span className="text-tertiary">—</span>
  const pos = amount >= 0
  const colorClass = dim
    ? (pos ? 'text-green-400' : 'text-red-300')
    : (pos ? 'text-gain' : 'text-loss')
  return (
    <div className={`text-right font-mono ${colorClass}`}>
      <div className="text-sm">{pos ? '+' : ''}{formatINR(amount)}</div>
      {pct != null && <div className="text-[11px] opacity-70">{formatPct(pct)}</div>}
    </div>
  )
}

function StaleIcon({ fetchedAt }: { fetchedAt?: string | null }) {
  const title = fetchedAt
    ? `Price last updated: ${new Date(fetchedAt).toLocaleString('en-IN')}`
    : 'Price data may be stale'
  return (
    <span title={title} className="ml-1 inline-flex items-center">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="inline text-amber-400">
        <path d="M6 1L11 10H1L6 1Z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1" strokeLinejoin="round" />
        <rect x="5.5" y="4.5" width="1" height="3" rx="0.4" fill="currentColor" />
        <rect x="5.5" y="8.5" width="1" height="1" rx="0.4" fill="currentColor" />
      </svg>
    </span>
  )
}

function SortIcon({ dir }: { dir: SortDir | null }) {
  return (
    <span className="ml-0.5 inline-flex flex-col leading-none opacity-40" aria-hidden>
      <span className={dir === 'asc' ? 'opacity-100' : ''}>▲</span>
      <span className={dir === 'desc' ? 'opacity-100' : ''}>▼</span>
    </span>
  )
}

function computeRow(a: HoldingRow) {
  const invested = a.total_invested ?? null
  const current = a.current_value ?? null
  const hasLotGains = a.st_unrealised_gain != null || a.lt_unrealised_gain != null
  const current_pnl = hasLotGains
    ? (a.st_unrealised_gain ?? 0) + (a.lt_unrealised_gain ?? 0)
    : current != null && invested != null ? current - invested : null
  const alltime_pnl = hasLotGains
    ? (a.st_unrealised_gain ?? 0) + (a.lt_unrealised_gain ?? 0) +
      (a.st_realised_gain ?? 0) + (a.lt_realised_gain ?? 0)
    : current_pnl
  return { invested, current, current_pnl, alltime_pnl }
}

function sortAssets(assets: HoldingRow[], key: SortKey, dir: SortDir): HoldingRow[] {
  const nullLast = (v: number | string | null, d: SortDir) =>
    v == null ? (d === 'asc' ? Infinity : -Infinity) : v

  return [...assets].sort((a, b) => {
    const ra = computeRow(a)
    const rb = computeRow(b)
    let av: number | string | null
    let bv: number | string | null

    switch (key) {
      case 'name':        av = a.name;                   bv = b.name; break
      case 'asset_type':  av = a.asset_type;             bv = b.asset_type; break
      case 'total_invested': av = ra.invested;           bv = rb.invested; break
      case 'current_value':  av = ra.current;            bv = rb.current; break
      case 'current_pnl':    av = ra.current_pnl;        bv = rb.current_pnl; break
      case 'alltime_pnl':    av = ra.alltime_pnl;        bv = rb.alltime_pnl; break
      case 'xirr':           av = a.xirr ?? null;        bv = b.xirr ?? null; break
      case 'start_date':     av = a.start_date ?? null;  bv = b.start_date ?? null; break
      case 'maturity_date':  av = a.maturity_date ?? null; bv = b.maturity_date ?? null; break
      case 'interest_rate_pct': av = a.interest_rate_pct ?? null; bv = b.interest_rate_pct ?? null; break
      case 'taxable_interest':  av = a.taxable_interest ?? null;  bv = b.taxable_interest ?? null; break
      case 'potential_tax_30pct': av = a.potential_tax_30pct ?? null; bv = b.potential_tax_30pct ?? null; break
      default: return 0
    }

    if (typeof av === 'string' && typeof bv === 'string') {
      return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
    }
    const na = nullLast(av as number | null, dir)
    const nb = nullLast(bv as number | null, dir)
    return dir === 'asc' ? (na as number) - (nb as number) : (nb as number) - (na as number)
  })
}

export function HoldingsTable({ assets, loading, variant = 'default' }: HoldingsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('current_value')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  function th(key: SortKey, label: string, className = '') {
    const active = sortKey === key
    return (
      <th
        className={`pb-2.5 pr-4 text-[10px] font-semibold uppercase tracking-[0.1em] cursor-pointer select-none transition-colors ${active ? 'text-secondary' : 'text-tertiary hover:text-secondary'} ${className}`}
        onClick={() => handleSort(key)}
      >
        {label}
        <SortIcon dir={active ? sortDir : null} />
      </th>
    )
  }

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
      </div>
    )
  }
  if (assets.length === 0) {
    return <p className="py-10 text-center text-sm text-tertiary">No holdings yet</p>
  }
  const sorted = sortAssets(assets, sortKey, sortDir)

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            {th('name', 'Name', 'text-left')}
            {th('asset_type', 'Type', 'text-left')}
            {th('total_invested', 'Invested', 'text-right')}
            {th('current_value', 'Current Value', 'text-right')}
            {th('current_pnl', 'Current P&L', 'text-right')}
            {variant !== 'fd-tax' && (
              <>
                {th('alltime_pnl', 'All-time P&L', 'text-right')}
                {th('xirr', 'XIRR', 'text-right')}
              </>
            )}
            {variant === 'fd-tax' && (
              <>
                {th('start_date', 'Start Date', 'text-right')}
                {th('maturity_date', 'End Date', 'text-right')}
                {th('interest_rate_pct', 'Rate', 'text-right')}
                {th('taxable_interest', 'Taxable Interest', 'text-right')}
                {th('potential_tax_30pct', 'Potential Tax (30%)', 'text-right last:pr-0')}
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {sorted.map((a) => {
            const { invested, current, current_pnl: currentPnl, alltime_pnl: allTimePnl } = computeRow(a)

            const currentPct = currentPnl != null && invested != null && invested > 0
              ? currentPnl / invested : null

            const isInactive = !a.is_active

            return (
              <tr key={a.id} className={`border-b border-border last:border-0 transition-colors ${isInactive ? 'bg-slate-50 text-slate-400 hover:bg-slate-100' : 'hover:bg-accent-subtle/40'}`}>
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-2">
                    <Link href={`/assets/${a.id}`} className="font-medium text-accent hover:underline">
                      {a.name}
                    </Link>
                    {isInactive && (
                      <span className="rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider bg-border text-tertiary">
                        Closed
                      </span>
                    )}
                  </div>
                </td>
                <td className="py-3 pr-4">{ASSET_TYPE_LABELS[a.asset_type]}</td>
                <td className="py-3 pr-4 text-right font-mono">
                  {invested != null ? formatINR(invested) : '—'}
                </td>
                <td className="py-3 pr-4 text-right font-mono">
                  {current != null ? (
                    <span className="inline-flex items-center justify-end gap-0.5">
                      {formatINR(current)}
                      {a.price_is_stale && !isInactive && <StaleIcon fetchedAt={a.price_fetched_at} />}
                    </span>
                  ) : '—'}
                </td>
                <td className="py-3 pr-4">
                  {isInactive ? <span className="text-slate-400">—</span> : <PnlCell amount={currentPnl} pct={currentPct} />}
                </td>
                {variant !== 'fd-tax' && (
                  <>
                    <td className="py-3 pr-4">
                      <PnlCell amount={allTimePnl} dim={isInactive} />
                    </td>
                    <td className="py-3 pr-4 text-right font-mono">
                      {a.xirr != null ? `${(a.xirr * 100).toFixed(2)}%` : '—'}
                    </td>
                  </>
                )}
                {variant === 'fd-tax' && (
                  <>
                    <td className="py-3 pr-4 text-right font-mono text-xs">
                      {a.start_date ? new Date(a.start_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-xs">
                      {a.maturity_date ? new Date(a.maturity_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-xs">
                      {a.interest_rate_pct != null ? `${a.interest_rate_pct}%` : '—'}
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-primary">
                      {a.taxable_interest != null ? formatINR(a.taxable_interest) : '—'}
                    </td>
                    <td className="py-3 text-right font-mono text-loss">
                      {a.potential_tax_30pct != null ? formatINR(a.potential_tax_30pct) : '—'}
                    </td>
                  </>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
