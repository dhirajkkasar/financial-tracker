'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { Asset, AssetType } from '@/types'

export function useAssets(type?: AssetType, active = true) {
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    api.assets.list({ type, active })
      .then(setAssets)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [type, active])

  return { assets, loading, error }
}
