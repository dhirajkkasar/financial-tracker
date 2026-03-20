'use client'
import { useAssetsWithReturns } from '@/hooks/useAssetsWithReturns'
import { useOverview } from '@/hooks/useOverview'
import { HoldingsTable } from '@/components/domain/HoldingsTable'
import { AssetSummaryCards } from '@/components/ui/AssetSummaryCards'

export default function RealEstatePage() {
  const { assets, loading } = useAssetsWithReturns('REAL_ESTATE')
  const { data: summary, loading: summaryLoading } = useOverview(['REAL_ESTATE'])
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-gray-800">Real Estate</h1>
      <AssetSummaryCards data={summary} loading={summaryLoading} />
      <div className="rounded-xl border bg-white p-5 shadow-sm">
        <HoldingsTable assets={assets} loading={loading} />
      </div>
    </div>
  )
}
