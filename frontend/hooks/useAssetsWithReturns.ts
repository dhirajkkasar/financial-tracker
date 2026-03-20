'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { Asset, AssetType, ReturnResult } from '@/types'

export interface AssetWithReturns extends Asset {
  total_invested?: number
  current_value?: number
  gain?: number          // absolute_return decimal (e.g. 0.15 = 15%)
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

export function useAssetsWithReturns(type?: AssetType | AssetType[], activeOnly = true) {
  const [assets, setAssets] = useState<AssetWithReturns[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // activeOnly=true → send active=true (filter to active only)
  // activeOnly=false → omit active param (backend returns all assets)
  const activeParam = activeOnly ? true : undefined

  useEffect(() => {
    setLoading(true)
    const types = Array.isArray(type) ? type : type ? [type] : [undefined as AssetType | undefined]

    Promise.all(types.map((t) => api.assets.list({ type: t, active: activeParam })))
      .then((results) => results.flat())
      .then(async (assetList) => {
        if (assetList.length === 0) {
          setAssets([])
          return
        }
        const ids = assetList.map((a) => a.id)
        let returnsMap: Record<number, ReturnResult> = {}
        try {
          const bulk = await api.returns.bulk(ids)
          returnsMap = Object.fromEntries(bulk.returns.map((r) => [r.asset_id, r]))
        } catch {
          // returns unavailable — show assets without financial data
        }
        const mapped = assetList.map((a) => {
          const r = returnsMap[a.id]
          return {
            ...a,
            total_invested: r?.total_invested ?? undefined,
            current_value: r?.current_value ?? undefined,
            gain: r?.absolute_return ?? undefined,
            xirr: r?.xirr ?? undefined,
            st_unrealised_gain: r?.st_unrealised_gain ?? undefined,
            lt_unrealised_gain: r?.lt_unrealised_gain ?? undefined,
            st_realised_gain: r?.st_realised_gain ?? undefined,
            lt_realised_gain: r?.lt_realised_gain ?? undefined,
            taxable_interest: r?.taxable_interest ?? undefined,
            potential_tax_30pct: r?.potential_tax_30pct ?? undefined,
            price_is_stale: r?.price_is_stale ?? undefined,
            price_fetched_at: r?.price_fetched_at ?? undefined,
          }
        })
        mapped.sort((a, b) => (b.current_value ?? -Infinity) - (a.current_value ?? -Infinity))
        setAssets(mapped)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [type, activeParam])

  return { assets, loading, error }
}
