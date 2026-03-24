'use client'
import { useParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Asset, Transaction, ReturnResult, FDDetail, PaginatedTransactions } from '@/types'
import { StatCard } from '@/components/ui/StatCard'
import { Skeleton } from '@/components/ui/Skeleton'
import { Pagination } from '@/components/ui/Pagination'
import { TaxLotTable } from '@/components/domain/TaxLotTable'
import { FDDetailCard } from '@/components/domain/FDDetailCard'
import { useLots } from '@/hooks/useLots'
import { formatXIRR, formatDate, formatPct } from '@/lib/formatters'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'
import { ASSET_TYPE_LABELS } from '@/constants'

const card = 'rounded-xl border border-border bg-card p-5'
const cardStyle = { boxShadow: 'var(--shadow-card)' }
const thClass = 'pb-2.5 pr-3 text-left text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary'

const LOT_BASED_TYPES = new Set(['STOCK_IN', 'STOCK_US', 'MF', 'GOLD', 'SGB', 'REAL_ESTATE', 'RSU'])
const FD_TYPES = new Set(['FD', 'RD'])

export default function AssetDetailPage() {
  const { formatINR, formatINR2 } = usePrivateMoney()
  const { id } = useParams<{ id: string }>()
  const assetId = parseInt(id)

  const [asset, setAsset] = useState<Asset | null>(null)
  const [txnData, setTxnData] = useState<PaginatedTransactions | null>(null)
  const [txnPage, setTxnPage] = useState(1)
  const [txnPageSize, setTxnPageSize] = useState(10)
  const [returns, setReturns] = useState<ReturnResult | null>(null)
  const [fdDetail, setFdDetail] = useState<FDDetail | null>(null)
  const [loading, setLoading] = useState(true)

  // Lot pagination state
  const [openPage, setOpenPage] = useState(1)
  const [matchedPage, setMatchedPage] = useState(1)
  const [lotsPageSize, setLotsPageSize] = useState(10)

  const { data: lots, loading: lotsLoading } = useLots(assetId, openPage, matchedPage, lotsPageSize)

  // Initial load
  useEffect(() => {
    Promise.all([
      api.assets.get(assetId),
      api.returns.asset(assetId).catch(() => null),
    ]).then(async ([a, ret]) => {
      setAsset(a)
      setReturns(ret)
      if (FD_TYPES.has(a.asset_type)) {
        try {
          const fd = await api.fdDetail.get(assetId)
          setFdDetail(fd)
        } catch {
          // no FD detail yet
        }
      }
    }).finally(() => setLoading(false))
  }, [assetId])

  // Fetch transactions whenever page/pageSize changes
  useEffect(() => {
    api.transactions.list(assetId, txnPage, txnPageSize)
      .then(setTxnData)
      .catch(() => setTxnData(null))
  }, [assetId, txnPage, txnPageSize])

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-56" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}
        </div>
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    )
  }

  if (!asset) return <p className="text-loss">Asset not found</p>

  const invested = returns?.total_invested ?? null
  // Fully closed: any inactive lot-based asset where position is fully unwound
  const isFullyRedeemed = !asset.is_active && LOT_BASED_TYPES.has(asset.asset_type)

  const currentPnl = !isFullyRedeemed && returns && invested != null && returns.current_value != null
    ? returns.current_value - invested
    : null
  const allTimePnl = isFullyRedeemed
    ? (returns?.st_realised_gain ?? 0) + (returns?.lt_realised_gain ?? 0)
    : currentPnl != null
      ? currentPnl + (returns?.st_realised_gain ?? 0) + (returns?.lt_realised_gain ?? 0)
      : null
  const totalUnits = returns?.total_units ?? null
  const avgPrice = returns?.avg_price ?? null
  const currentPnlHighlight = currentPnl === null ? 'neutral' : currentPnl >= 0 ? 'positive' : 'negative'
  const allTimePnlHighlight = allTimePnl === null ? 'neutral' : allTimePnl >= 0 ? 'positive' : 'negative'

  const showLots = LOT_BASED_TYPES.has(asset.asset_type)
  const showFD = FD_TYPES.has(asset.asset_type) && fdDetail != null && returns != null

  const transactions = txnData?.items ?? []
  const txnTotal = txnData?.total ?? 0
  const txnTotalPages = txnData?.total_pages ?? 1

  const emptyLots = {
    items: [] as any[],
    total: 0,
    page: 1,
    page_size: lotsPageSize,
    total_pages: 1,
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl text-primary">{asset.name}</h1>
        <p className="mt-1 text-sm text-secondary">
          {ASSET_TYPE_LABELS[asset.asset_type]}
          {asset.identifier ? <> · <span className="font-mono">{asset.identifier}</span></> : null}
          {!asset.is_active && (
            <span className="ml-2 rounded-full bg-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-tertiary">
              Inactive
            </span>
          )}
        </p>
      </div>

      {/* Summary cards */}
      {isFullyRedeemed ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <StatCard label="Invested" value={formatINR(invested ?? 0)} />
          <StatCard
            label="All-time P&L"
            value={allTimePnl !== null ? formatINR(allTimePnl) : '—'}
            highlight={allTimePnlHighlight}
          />
          <StatCard label="XIRR" value={formatXIRR(returns?.xirr ?? null)} />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          <StatCard label="Invested" value={formatINR(invested ?? 0)} />
          <StatCard label="Current Value" value={formatINR(returns?.current_value ?? 0)} />
          <StatCard
            label="Current P&L"
            value={currentPnl !== null ? formatINR(currentPnl) : '—'}
            sub={currentPnl !== null && (invested ?? 0) > 0
              ? formatPct(currentPnl / invested!)
              : undefined}
            highlight={currentPnlHighlight}
          />
          <StatCard
            label="All-time P&L"
            value={allTimePnl !== null ? formatINR(allTimePnl) : '—'}
            highlight={allTimePnlHighlight}
          />
          <StatCard label="XIRR" value={formatXIRR(returns?.xirr ?? null)} />
        </div>
      )}
      {/* Units and avg cost — active market-based assets only */}
      {asset.is_active && totalUnits != null && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          <StatCard label="Units Held" value={totalUnits.toLocaleString('en-IN', { maximumFractionDigits: 4 })} />
          <StatCard label="Avg Cost / Unit" value={avgPrice != null ? formatINR2(avgPrice) : '—'} />
        </div>
      )}

      {/* Message (PPF/EPF no valuation, etc.) */}
      {returns?.message && (
        <div className={`${card} border-l-4 border-l-gold`} style={cardStyle}>
          <p className="text-sm text-secondary">{returns.message}</p>
        </div>
      )}

      {/* FD Detail Card */}
      {showFD && (
        <div className={card} style={cardStyle}>
          <h2 className="mb-5 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">Deposit Details</h2>
          <FDDetailCard fd={fdDetail!} returns={returns!} />
        </div>
      )}

      {/* FIFO Lot Table */}
      {showLots && (
        <div className={card} style={cardStyle}>
          <h2 className="mb-5 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
            Tax Lots · FIFO
          </h2>
          <TaxLotTable
            openLots={lots?.open_lots ?? emptyLots}
            matchedSells={lots?.matched_sells ?? emptyLots}
            loading={lotsLoading}
            onOpenPageChange={setOpenPage}
            onMatchedPageChange={setMatchedPage}
            onPageSizeChange={(size) => {
              setLotsPageSize(size)
              setOpenPage(1)
              setMatchedPage(1)
            }}
            pageSize={lotsPageSize}
          />
        </div>
      )}

      {/* Transactions */}
      <div className={card} style={cardStyle}>
        <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
          Transactions ({txnTotal})
        </h2>
        {txnTotal === 0 && !txnData ? (
          <p className="py-10 text-center text-sm text-tertiary">Loading...</p>
        ) : transactions.length === 0 ? (
          <p className="py-10 text-center text-sm text-tertiary">No transactions yet</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className={thClass}>Date</th>
                    <th className={thClass}>Type</th>
                    <th className={`${thClass} text-right`}>Units</th>
                    <th className={`${thClass} text-right pr-0`}>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((t: Transaction) => {
                    const isOut = ['BUY', 'SIP', 'CONTRIBUTION', 'VEST'].includes(t.type)
                    return (
                      <tr key={t.id} className="border-b border-border last:border-0 transition-colors hover:bg-accent-subtle/30">
                        <td className="py-2.5 pr-3 text-sm text-secondary font-mono">{formatDate(t.date)}</td>
                        <td className="py-2.5 pr-3">
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                            isOut ? 'bg-loss-subtle text-loss' : 'bg-gain-subtle text-gain'
                          }`}>
                            {t.type}
                          </span>
                        </td>
                        <td className="py-2.5 pr-3 text-right font-mono text-sm text-secondary">
                          {t.units != null ? t.units.toFixed(4) : '—'}
                        </td>
                        <td className="py-2.5 text-right font-mono text-sm text-primary">
                          {formatINR(Math.abs(t.amount_inr))}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <Pagination
              page={txnPage}
              pageSize={txnPageSize}
              total={txnTotal}
              totalPages={txnTotalPages}
              onPageChange={setTxnPage}
              onPageSizeChange={(size) => {
                setTxnPageSize(size)
                setTxnPage(1)
              }}
            />
          </>
        )}
      </div>
    </div>
  )
}
