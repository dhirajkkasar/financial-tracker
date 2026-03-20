'use client'
import { LotEntry, MatchedSell, PaginatedItems } from '@/types'
import { formatINR, formatDate } from '@/lib/formatters'
import { Skeleton } from '@/components/ui/Skeleton'
import { Pagination } from '@/components/ui/Pagination'

const thClass = 'pb-2.5 pr-3 text-left text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary'
const tdClass = 'py-2.5 pr-3 text-sm'

function TermBadge({ isShortTerm }: { isShortTerm: boolean }) {
  return isShortTerm ? (
    <span className="inline-flex items-center rounded-full bg-gold-subtle px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gold">
      ST
    </span>
  ) : (
    <span className="inline-flex items-center rounded-full bg-gain-subtle px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gain">
      LT
    </span>
  )
}

function GainCell({ value }: { value: number | null }) {
  if (value === null) return <span className="text-tertiary">—</span>
  const pos = value >= 0
  return (
    <span className={`font-mono ${pos ? 'text-gain' : 'text-loss'}`}>
      {pos ? '+' : ''}{formatINR(value)}
    </span>
  )
}

interface TaxLotTableProps {
  openLots: PaginatedItems<LotEntry>
  matchedSells: PaginatedItems<MatchedSell>
  loading: boolean
  onOpenPageChange: (page: number) => void
  onMatchedPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
  pageSize: number
}

export function TaxLotTable({
  openLots,
  matchedSells,
  loading,
  onOpenPageChange,
  onMatchedPageChange,
  onPageSizeChange,
  pageSize,
}: TaxLotTableProps) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
      </div>
    )
  }

  if (openLots.total === 0 && matchedSells.total === 0) {
    return <p className="py-10 text-center text-sm text-tertiary">No lot data — add transactions to see FIFO breakdown</p>
  }

  return (
    <div className="space-y-8">
      {/* Open Positions */}
      {openLots.total > 0 && (
        <div>
          <h3 className="mb-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
            Open Positions ({openLots.total})
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className={thClass}>Buy Date</th>
                  <th className={`${thClass} text-right`}>Units</th>
                  <th className={`${thClass} text-right`}>Buy Price</th>
                  <th className={`${thClass} text-right`}>Cost Basis</th>
                  <th className={`${thClass} text-right`}>Current Value</th>
                  <th className={`${thClass} text-right`}>Unrealised P&L</th>
                  <th className={`${thClass} text-right`}>Days</th>
                  <th className={`${thClass} text-center`}>Term</th>
                </tr>
              </thead>
              <tbody>
                {openLots.items.map((lot) => {
                  const rowBg = lot.is_short_term
                    ? 'hover:bg-gold-subtle/50'
                    : 'hover:bg-gain-subtle/50'
                  return (
                    <tr key={lot.lot_id} className={`border-b border-border last:border-0 transition-colors ${rowBg}`}>
                      <td className={`${tdClass} text-secondary`}>{formatDate(lot.buy_date)}</td>
                      <td className={`${tdClass} text-right font-mono text-primary`}>{lot.units_remaining.toFixed(4)}</td>
                      <td className={`${tdClass} text-right font-mono text-secondary`}>{formatINR(lot.buy_price_per_unit)}</td>
                      <td className={`${tdClass} text-right font-mono text-primary`}>{formatINR(lot.buy_amount_inr)}</td>
                      <td className={`${tdClass} text-right font-mono text-primary`}>
                        {lot.current_value != null ? formatINR(lot.current_value) : '—'}
                      </td>
                      <td className={`${tdClass} text-right`}>
                        <GainCell value={lot.unrealised_gain} />
                      </td>
                      <td className={`${tdClass} text-right font-mono text-secondary`}>{lot.holding_days}d</td>
                      <td className={`${tdClass} text-center`}>
                        <TermBadge isShortTerm={lot.is_short_term} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {openLots.total_pages > 1 && (
            <Pagination
              page={openLots.page}
              pageSize={pageSize}
              total={openLots.total}
              totalPages={openLots.total_pages}
              onPageChange={onOpenPageChange}
              onPageSizeChange={onPageSizeChange}
            />
          )}
        </div>
      )}

      {/* Matched Sells */}
      {matchedSells.total > 0 && (
        <div>
          <h3 className="mb-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
            Realised Sells ({matchedSells.total})
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className={thClass}>Sell Date</th>
                  <th className={thClass}>Buy Date</th>
                  <th className={`${thClass} text-right`}>Units Sold</th>
                  <th className={`${thClass} text-right`}>Buy Price</th>
                  <th className={`${thClass} text-right`}>Sell Price</th>
                  <th className={`${thClass} text-right`}>Realised Gain</th>
                </tr>
              </thead>
              <tbody>
                {matchedSells.items.map((sell, i) => (
                  <tr key={i} className="border-b border-border last:border-0 transition-colors hover:bg-accent-subtle/30">
                    <td className={`${tdClass} text-secondary`}>{formatDate(sell.sell_date)}</td>
                    <td className={`${tdClass} text-secondary`}>{formatDate(sell.buy_date)}</td>
                    <td className={`${tdClass} text-right font-mono text-primary`}>{sell.units_sold.toFixed(4)}</td>
                    <td className={`${tdClass} text-right font-mono text-secondary`}>{formatINR(sell.buy_price_per_unit)}</td>
                    <td className={`${tdClass} text-right font-mono text-secondary`}>{formatINR(sell.sell_price_per_unit)}</td>
                    <td className={`${tdClass} text-right`}>
                      <GainCell value={sell.realised_gain_inr} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {matchedSells.total_pages > 1 && (
            <Pagination
              page={matchedSells.page}
              pageSize={pageSize}
              total={matchedSells.total}
              totalPages={matchedSells.total_pages}
              onPageChange={onMatchedPageChange}
              onPageSizeChange={onPageSizeChange}
            />
          )}
        </div>
      )}
    </div>
  )
}
