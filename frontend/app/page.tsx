'use client'
import { useOverview } from '@/hooks/useOverview'
import { useBreakdown } from '@/hooks/useBreakdown'
import { useAllocation } from '@/hooks/useAllocation'
import { useGainers } from '@/hooks/useGainers'
import { StatCard } from '@/components/ui/StatCard'
import { StatCardSkeleton } from '@/components/ui/Skeleton'
import { AllocationDonut } from '@/components/charts/AllocationDonut'
import { AssetTypeDonut } from '@/components/charts/AssetTypeDonut'
import { formatINR, formatXIRR, formatPct } from '@/lib/formatters'
import { ASSET_TYPE_LABELS } from '@/constants'
import Link from 'next/link'

const card = 'rounded-xl border border-border bg-card p-5'
const cardStyle = { boxShadow: 'var(--shadow-card)' }
const thClass = 'pb-3 text-left text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary'

export default function OverviewPage() {
  const { data: overview, loading: overviewLoading } = useOverview()
  const { breakdown, loading: breakdownLoading } = useBreakdown()
  const { data: allocation, loading: allocLoading } = useAllocation()
  const { data: gainersData, loading: gainersLoading } = useGainers(5)

  const gain = overview ? overview.total_current_value - overview.total_invested : null
  const gainHighlight = gain === null ? 'neutral' : gain >= 0 ? 'positive' : 'negative'

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
                <th className={thClass}>Asset Type</th>
                <th className={`${thClass} text-right`}>Share</th>
                <th className={`${thClass} text-right`}>Invested</th>
                <th className={`${thClass} text-right`}>Current Value</th>
                <th className={`${thClass} text-right`}>XIRR</th>
                <th className={`${thClass} text-right`}>Current P&amp;L</th>
                <th className={`${thClass} text-right`}>All-time P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {breakdown.map((row) => {
                const totalInvested = overview?.total_invested ?? 0
                const pct = totalInvested > 0 ? (row.total_invested / totalInvested) * 100 : 0
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
