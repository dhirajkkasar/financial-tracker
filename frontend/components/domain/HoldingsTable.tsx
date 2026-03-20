'use client'
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
}

type HoldingsVariant = 'default' | 'fd-tax'

interface HoldingsTableProps {
  assets: HoldingRow[]
  loading: boolean
  variant?: HoldingsVariant
}

function PnlCell({ amount, pct }: { amount: number | null; pct?: number | null }) {
  if (amount == null) return <span className="text-tertiary">—</span>
  const pos = amount >= 0
  return (
    <div className={`text-right font-mono ${pos ? 'text-gain' : 'text-loss'}`}>
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

export function HoldingsTable({ assets, loading, variant = 'default' }: HoldingsTableProps) {
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
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="pb-2.5 pr-4 text-left text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">Name</th>
            <th className="pb-2.5 pr-4 text-left text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">Type</th>
            <th className="pb-2.5 pr-4 text-right text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">Invested</th>
            <th className="pb-2.5 pr-4 text-right text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">Current Value</th>
            <th className="pb-2.5 pr-4 text-right text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">Current P&L</th>
            <th className="pb-2.5 pr-4 text-right text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">All-time P&L</th>
            <th className="pb-2.5 pr-4 text-right text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">XIRR</th>
            {variant === 'fd-tax' && (
              <>
                <th className="pb-2.5 pr-4 text-right text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">Taxable Interest</th>
                <th className="pb-2.5 text-right text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">Potential Tax (30%)</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {assets.map((a) => {
            const invested = a.total_invested ?? null
            const current = a.current_value ?? null

            const hasLotGains = a.st_unrealised_gain != null || a.lt_unrealised_gain != null
            const currentPnl = hasLotGains
              ? ((a.st_unrealised_gain ?? 0) + (a.lt_unrealised_gain ?? 0))
              : (current != null && invested != null ? current - invested : null)
            const allTimePnl = hasLotGains
              ? ((a.st_unrealised_gain ?? 0) + (a.lt_unrealised_gain ?? 0) +
                 (a.st_realised_gain ?? 0) + (a.lt_realised_gain ?? 0))
              : currentPnl

            const currentPct = currentPnl != null && invested != null && invested > 0
              ? currentPnl / invested : null

            const isInactive = !a.is_active

            return (
              <tr key={a.id} className={`border-b border-border last:border-0 transition-colors hover:bg-accent-subtle/40 ${isInactive ? 'opacity-60' : ''}`}>
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
                <td className="py-3 pr-4 text-secondary">{ASSET_TYPE_LABELS[a.asset_type]}</td>
                <td className="py-3 pr-4 text-right font-mono text-primary">
                  {invested != null ? formatINR(invested) : '—'}
                </td>
                <td className="py-3 pr-4 text-right font-mono text-primary">
                  {current != null ? (
                    <span className="inline-flex items-center justify-end gap-0.5">
                      {formatINR(current)}
                      {a.price_is_stale && <StaleIcon fetchedAt={a.price_fetched_at} />}
                    </span>
                  ) : '—'}
                </td>
                <td className="py-3 pr-4">
                  <PnlCell amount={currentPnl} pct={currentPct} />
                </td>
                <td className="py-3 pr-4">
                  <PnlCell amount={allTimePnl} />
                </td>
                <td className="py-3 pr-4 text-right font-mono text-secondary">
                  {a.xirr != null ? `${(a.xirr * 100).toFixed(2)}%` : '—'}
                </td>
                {variant === 'fd-tax' && (
                  <>
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
