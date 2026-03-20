import { OverviewReturns } from '@/types'
import { StatCard } from './StatCard'
import { StatCardSkeleton } from './Skeleton'
import { formatINR, formatXIRR, formatPct } from '@/lib/formatters'

interface AssetSummaryCardsProps {
  data: OverviewReturns | null
  loading: boolean
}

export function AssetSummaryCards({ data, loading }: AssetSummaryCardsProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {[1, 2, 3, 4, 5].map((i) => <StatCardSkeleton key={i} />)}
      </div>
    )
  }

  const invested = data?.total_invested ?? 0
  const current = data?.total_current_value ?? 0

  // Current P&L: unrealized gains on open positions
  const hasLotGains = data != null &&
    (data.st_unrealised_gain != null || data.lt_unrealised_gain != null)

  const currentPnl = hasLotGains
    ? ((data!.st_unrealised_gain ?? 0) + (data!.lt_unrealised_gain ?? 0))
    : current - invested

  // All-time P&L: unrealized + realized
  const allTimePnl = hasLotGains
    ? ((data!.st_unrealised_gain ?? 0) + (data!.lt_unrealised_gain ?? 0) +
       (data!.st_realised_gain ?? 0) + (data!.lt_realised_gain ?? 0))
    : current - invested

  const hasInterest = data != null && data.total_taxable_interest != null

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="Invested" value={formatINR(invested)} />
        <StatCard label="Current Value" value={formatINR(current)} />
        <StatCard
          label="Current P&L"
          value={formatINR(currentPnl)}
          sub={invested > 0 ? formatPct(currentPnl / invested) : undefined}
          highlight={currentPnl >= 0 ? 'positive' : 'negative'}
        />
        <StatCard
          label="All-time P&L"
          value={formatINR(allTimePnl)}
          highlight={allTimePnl >= 0 ? 'positive' : 'negative'}
        />
        <StatCard label="XIRR" value={formatXIRR(data?.xirr ?? null)} />
      </div>

      {hasInterest && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-2">
          <StatCard
            label="Taxable Interest"
            value={data!.total_taxable_interest != null ? formatINR(data!.total_taxable_interest) : '—'}
          />
          <StatCard
            label="Est. Tax (30%)"
            value={data!.total_potential_tax != null ? formatINR(data!.total_potential_tax) : '—'}
            highlight="negative"
          />
        </div>
      )}
    </div>
  )
}
