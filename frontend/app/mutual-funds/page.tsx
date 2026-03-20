'use client'
import { useState } from 'react'
import { useAssetsWithReturns } from '@/hooks/useAssetsWithReturns'
import { useOverview } from '@/hooks/useOverview'
import { HoldingsTable } from '@/components/domain/HoldingsTable'
import { AssetSummaryCards } from '@/components/ui/AssetSummaryCards'

export default function MutualFundsPage() {
  const [activeOnly, setActiveOnly] = useState(true)
  const { assets, loading } = useAssetsWithReturns('MF', activeOnly)
  const { data: summary, loading: summaryLoading } = useOverview(['MF'])
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">Mutual Funds</h1>
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
        <HoldingsTable assets={assets} loading={loading} />
      </div>
    </div>
  )
}
