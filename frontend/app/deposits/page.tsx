'use client'
import { useState, useEffect } from 'react'
import { useAssetsWithReturns } from '@/hooks/useAssetsWithReturns'
import { useOverview } from '@/hooks/useOverview'
import { HoldingsTable } from '@/components/domain/HoldingsTable'
import { AssetSummaryCards } from '@/components/ui/AssetSummaryCards'
import { api } from '@/lib/api'
import type { AssetWithReturns } from '@/hooks/useAssetsWithReturns'

export default function DepositsPage() {
  const [activeOnly, setActiveOnly] = useState(true)
  const { assets, loading } = useAssetsWithReturns(['FD', 'RD'] as any, activeOnly)
  const { data: summary, loading: summaryLoading } = useOverview(['FD', 'RD'])

  const [enriched, setEnriched] = useState<(AssetWithReturns & {
    start_date?: string
    maturity_date?: string
    interest_rate_pct?: number
    fd_type?: string
  })[]>([])

  useEffect(() => {
    if (assets.length === 0) {
      setEnriched([])
      return
    }
    Promise.all(
      assets.map((a) =>
        api.fdDetail.get(a.id).then((fd) => ({
          ...a,
          start_date: fd.start_date,
          maturity_date: fd.maturity_date,
          interest_rate_pct: fd.interest_rate_pct,
          fd_type: fd.fd_type,
        })).catch(() => a)
      )
    ).then(setEnriched)
  }, [assets])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Deposits</h1>
        <button
          onClick={() => setActiveOnly((v) => !v)}
          className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
            activeOnly
              ? 'border-border bg-card text-tertiary hover:text-secondary'
              : 'border-accent/40 bg-accent/10 text-accent'
          }`}
        >
          {activeOnly ? 'Show Inactive' : 'Hide Inactive'}
        </button>
      </div>
      <AssetSummaryCards data={summary} loading={summaryLoading} />
      <div className="rounded-xl border bg-white p-5 shadow-sm">
        <HoldingsTable assets={enriched.length > 0 ? enriched : assets} loading={loading} variant="fd-tax" />
      </div>
    </div>
  )
}
