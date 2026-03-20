'use client'
import { useState } from 'react'
import { useAssetsWithReturns } from '@/hooks/useAssetsWithReturns'
import { useOverview } from '@/hooks/useOverview'
import { HoldingsTable } from '@/components/domain/HoldingsTable'
import { AssetSummaryCards } from '@/components/ui/AssetSummaryCards'

export default function EpfPage() {
  const [activeOnly, setActiveOnly] = useState(true)
  // EPF assets: all EPF-type assets whose name does NOT start with "EPS"
  const { assets: allAssets, loading } = useAssetsWithReturns('EPF', activeOnly)
  const { data: summary, loading: summaryLoading } = useOverview(['EPF'])

  // Split into EPF accounts and EPS sub-accounts
  const epfAssets = allAssets.filter((a) => !a.name.startsWith('EPS'))
  const epsAssets = allAssets.filter((a) => a.name.startsWith('EPS'))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-800">EPF</h1>
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
        <HoldingsTable assets={epfAssets} loading={loading} />
      </div>

      {/* EPS sub-section — shown only when EPS assets exist */}
      {(loading || epsAssets.length > 0) && (
        <div className="space-y-3">
          <h2 className="text-base font-semibold text-gray-700">
            EPS (Employee Pension Scheme)
          </h2>
          <p className="text-xs text-gray-500">
            Pension contributions tracked separately. EPS balances are not
            withdrawable and do not accrue market-rate interest.
          </p>
          <div className="rounded-xl border bg-white p-5 shadow-sm">
            <HoldingsTable assets={epsAssets} loading={loading} />
          </div>
        </div>
      )}
    </div>
  )
}
