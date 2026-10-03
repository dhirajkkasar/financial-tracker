'use client'
import { useState } from 'react'
import { useAssetsWithReturns } from '@/hooks/useAssetsWithReturns'
import { useOverview } from '@/hooks/useOverview'
import { HoldingsTable } from '@/components/domain/HoldingsTable'
import { AssetSummaryCards } from '@/components/ui/AssetSummaryCards'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import MemberSelector from '@/components/ui/MemberSelector'

export default function GoldPage() {
  const [activeOnly, setActiveOnly] = useState(true)
  const { assets, loading, error } = useAssetsWithReturns(['GOLD', 'SGB'], activeOnly)
  const { data: summary, loading: summaryLoading, error: summaryError } = useOverview(['GOLD', 'SGB'])
  const pageError = error ?? summaryError
  return (
    <div className="space-y-6">
      <MemberSelector />
      {pageError && <ErrorBanner message={pageError} />}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-primary">Gold</h1>
        <button
          onClick={() => setActiveOnly((v) => !v)}
          className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
            activeOnly
              ? 'border-border bg-card text-secondary hover:text-primary'
              : 'border-accent/40 bg-accent/10 text-accent'
          }`}
        >
          {activeOnly ? 'Show Inactive' : 'Hide Inactive'}
        </button>
      </div>
      <AssetSummaryCards data={summary} loading={summaryLoading} />
      <div className="rounded-xl border bg-card p-5 shadow-card">
        <HoldingsTable assets={assets} loading={loading} />
      </div>
    </div>
  )
}
