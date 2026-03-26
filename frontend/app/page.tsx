'use client'
import { useState } from 'react'
import { useOverview } from '@/hooks/useOverview'
import { useBreakdown } from '@/hooks/useBreakdown'
import { useAllocation } from '@/hooks/useAllocation'
import { useGainers } from '@/hooks/useGainers'
import { useSnapshots } from '@/hooks/useSnapshots'
import { StatCard } from '@/components/ui/StatCard'
import { StatCardSkeleton } from '@/components/ui/Skeleton'
import { AllocationDonut } from '@/components/charts/AllocationDonut'
import { AssetTypeDonut } from '@/components/charts/AssetTypeDonut'
import { NetWorthChart } from '@/components/charts/NetWorthChart'
import { GoalsWidget } from '@/components/domain/GoalsWidget'
import { formatXIRR, formatPct } from '@/lib/formatters'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'
import { ASSET_TYPE_LABELS } from '@/constants'
import Link from 'next/link'

const card = 'rounded-xl border border-border bg-card p-5'
const cardStyle = { boxShadow: 'var(--shadow-card)' }
const thClass = 'pb-3 text-left text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary'

export default function OverviewPage() {
  const { formatINR } = usePrivateMoney()
  const { data: overview, loading: overviewLoading } = useOverview()
  const { breakdown, loading: breakdownLoading } = useBreakdown()
  const { data: allocation, loading: allocLoading } = useAllocation()
  const { data: gainersData, loading: gainersLoading } = useGainers(5)
  const { data: snapshots, loading: snapshotsLoading } = useSnapshots()

  const gain = overview ? overview.total_current_value - overview.total_invested : null
  const gainHighlight = gain === null ? 'neutral' : gain >= 0 ? 'positive' : 'negative'

  type BdSortKey = 'asset_type' | 'share' | 'total_invested' | 'total_current_value' | 'xirr' | 'current_pnl' | 'alltime_pnl'
  type SortDir = 'asc' | 'desc'
  const [bdSortKey, setBdSortKey] = useState<BdSortKey>('total_current_value')
  const [bdSortDir, setBdSortDir] = useState<SortDir>('desc')

  function bdHandleSort(key: BdSortKey) {
    if (bdSortKey === key) setBdSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setBdSortKey(key); setBdSortDir('desc') }
  }

  const totalInvested = overview?.total_invested ?? 0
  const totalCurrentValue = overview?.total_current_value ?? 0
  const sortedBreakdown = [...breakdown].sort((a, b) => {
    const nullLast = (v: number | string | null) =>
      v == null ? (bdSortDir === 'asc' ? Infinity : -Infinity) : v
    let av: number | string | null
    let bv: number | string | null
    switch (bdSortKey) {
      case 'asset_type':          av = a.asset_type;          bv = b.asset_type; break
      case 'share':               av = a.total_current_value; bv = b.total_current_value; break
      case 'total_invested':      av = a.total_invested;      bv = b.total_invested; break
      case 'total_current_value': av = a.total_current_value; bv = b.total_current_value; break
      case 'xirr':                av = a.xirr ?? null;        bv = b.xirr ?? null; break
      case 'current_pnl':         av = a.current_pnl ?? null; bv = b.current_pnl ?? null; break
      case 'alltime_pnl':         av = a.alltime_pnl ?? null; bv = b.alltime_pnl ?? null; break
      default: return 0
    }
    if (typeof av === 'string' && typeof bv === 'string')
      return bdSortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
    const na = nullLast(av as number | null) as number
    const nb = nullLast(bv as number | null) as number
    return bdSortDir === 'asc' ? na - nb : nb - na
  })

  function BdTh({ k, label, align = 'right' }: { k: BdSortKey; label: string; align?: 'left' | 'right' }) {
    const active = bdSortKey === k
    return (
      <th
        onClick={() => bdHandleSort(k)}
        className={`pb-3 text-[10px] font-semibold uppercase tracking-[0.1em] cursor-pointer select-none transition-colors ${align === 'right' ? 'text-right' : 'text-left'} ${active ? 'text-secondary' : 'text-tertiary hover:text-secondary'}`}
      >
        {label}
        <span className="ml-0.5 inline-flex flex-col leading-none opacity-40" aria-hidden>
          <span className={active && bdSortDir === 'asc' ? 'opacity-100' : ''}>▲</span>
          <span className={active && bdSortDir === 'desc' ? 'opacity-100' : ''}>▼</span>
        </span>
      </th>
    )
  }

  // Map allocation response → AllocationDonut shape
  const allocationChartData = (allocation?.allocations ?? []).map((a) => ({
    name: a.asset_class,
    value: a.value_inr,
    asset_class: a.asset_class as import('@/types').AssetClass,
  }))

  return (
    <div className="space-y-8">
      <h1 className="text-2xl text-primary">Overview</h1>

      {/* Portfolio stat cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {(overviewLoading || breakdownLoading) ? (
          [1, 2, 3, 4, 5].map((i) => <StatCardSkeleton key={i} />)
        ) : (
          <>
            <StatCard label="Invested" value={formatINR(overview?.total_invested ?? 0)} />
            <StatCard label="Current Value" value={formatINR(overview?.total_current_value ?? 0)} />
            <StatCard
              label="Current P&L"
              value={gain !== null ? formatINR(gain) : '—'}
              sub={gain !== null && overview!.total_invested > 0 ? formatPct(gain / overview!.total_invested) : undefined}
              highlight={gainHighlight}
            />
            <StatCard
              label="All-time P&L"
              value={formatINR(breakdown.reduce((s, r) => s + (r.alltime_pnl ?? 0), 0))}
              highlight={breakdown.reduce((s, r) => s + (r.alltime_pnl ?? 0), 0) >= 0 ? 'positive' : 'negative'}
            />
            <StatCard label="XIRR" value={formatXIRR(overview?.xirr ?? null)} />
          </>
        )}
      </div>

      {/* Net Worth Chart */}
      <div className={card} style={cardStyle}>
        <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">Net Worth Over Time</h2>
        <NetWorthChart data={snapshots} loading={snapshotsLoading} />
      </div>

      {/* Goals */}
      <GoalsWidget />

      {/* Two donuts */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className={card} style={cardStyle}>
          <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">By Asset Class</h2>
          <AllocationDonut data={allocationChartData} />
        </div>
        <div className={card} style={cardStyle}>
          <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">By Asset Type</h2>
          <AssetTypeDonut data={breakdown} loading={breakdownLoading} />
        </div>
      </div>

      {/* Gainers / Losers */}
      {!gainersLoading && ((gainersData?.gainers.length ?? 0) > 0 || (gainersData?.losers.length ?? 0) > 0) && (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {/* Top Gainers */}
          <div className={card} style={cardStyle}>
            <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">Top Gainers</h2>
            {gainersData!.gainers.length === 0 ? (
              <p className="py-6 text-center text-sm text-tertiary">No gainers yet</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className={thClass}>Asset</th>
                    <th className={`${thClass} text-right`}>Return</th>
                    <th className={`${thClass} text-right`}>XIRR</th>
                  </tr>
                </thead>
                <tbody>
                  {gainersData!.gainers.map((g) => (
                    <tr key={g.asset_id} className="border-b border-border last:border-0 transition-colors hover:bg-gain-subtle/40">
                      <td className="py-2.5 pr-3">
                        <Link href={`/assets/${g.asset_id}`} className="font-medium text-accent hover:underline">
                          {g.name}
                        </Link>
                        <p className="text-[10px] text-tertiary">{ASSET_TYPE_LABELS[g.asset_type]}</p>
                      </td>
                      <td className="py-2.5 pr-3 text-right font-mono text-gain">
                        +{g.absolute_return_pct?.toFixed(2)}%
                      </td>
                      <td className="py-2.5 text-right font-mono text-secondary">
                        {formatXIRR(g.xirr)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Top Losers */}
          <div className={card} style={cardStyle}>
            <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">Underperformers</h2>
            {gainersData!.losers.length === 0 ? (
              <p className="py-6 text-center text-sm text-tertiary">No losers yet</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className={thClass}>Asset</th>
                    <th className={`${thClass} text-right`}>Return</th>
                    <th className={`${thClass} text-right`}>XIRR</th>
                  </tr>
                </thead>
                <tbody>
                  {gainersData!.losers.map((g) => (
                    <tr key={g.asset_id} className="border-b border-border last:border-0 transition-colors hover:bg-loss-subtle/40">
                      <td className="py-2.5 pr-3">
                        <Link href={`/assets/${g.asset_id}`} className="font-medium text-accent hover:underline">
                          {g.name}
                        </Link>
                        <p className="text-[10px] text-tertiary">{ASSET_TYPE_LABELS[g.asset_type]}</p>
                      </td>
                      <td className="py-2.5 pr-3 text-right font-mono text-loss">
                        {g.absolute_return_pct?.toFixed(2)}%
                      </td>
                      <td className="py-2.5 text-right font-mono text-secondary">
                        {formatXIRR(g.xirr)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Breakdown table */}
      <div className={card} style={cardStyle}>
        <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">Summary by Asset Type</h2>
        {breakdownLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse h-10 rounded bg-border" />
            ))}
          </div>
        ) : breakdown.length === 0 ? (
          <p className="py-10 text-center text-sm text-tertiary">No holdings yet</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <BdTh k="asset_type" label="Asset Type" align="left" />
                <BdTh k="share" label="Share" />
                <BdTh k="total_invested" label="Invested" />
                <BdTh k="total_current_value" label="Current Value" />
                <BdTh k="xirr" label="XIRR" />
                <BdTh k="current_pnl" label="Current P&L" />
                <BdTh k="alltime_pnl" label="All-time P&L" />
              </tr>
            </thead>
            <tbody>
              {sortedBreakdown.map((row) => {
                const pct = totalCurrentValue > 0 ? ((row.total_current_value ?? 0) / totalCurrentValue) * 100 : 0
                return (
                  <tr key={row.asset_type} className="border-b border-border last:border-0 hover:bg-accent-subtle/30 transition-colors">
                    <td className="py-3 pr-4 font-medium text-primary">{ASSET_TYPE_LABELS[row.asset_type]}</td>
                    <td className="py-3 pr-4 text-right font-mono text-secondary">{pct.toFixed(2)}%</td>
                    <td className="py-3 pr-4 text-right font-mono text-primary">{formatINR(row.total_invested)}</td>
                    <td className="py-3 pr-4 text-right font-mono text-primary">
                      {row.total_current_value > 0 ? formatINR(row.total_current_value) : '—'}
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-secondary">{formatXIRR(row.xirr)}</td>
                    <td className={`py-3 pr-4 text-right font-mono ${row.current_pnl != null && row.current_pnl >= 0 ? 'text-gain' : 'text-loss'}`}>
                      {row.current_pnl != null ? formatINR(row.current_pnl) : '—'}
                    </td>
                    <td className={`py-3 text-right font-mono ${row.alltime_pnl != null && row.alltime_pnl >= 0 ? 'text-gain' : 'text-loss'}`}>
                      {row.alltime_pnl != null ? formatINR(row.alltime_pnl) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
