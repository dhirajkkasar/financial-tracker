'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { LotsResponse } from '@/types'

export function useLots(
  assetId: number,
  openPage = 1,
  matchedPage = 1,
  pageSize = 10,
) {
  const [data, setData] = useState<LotsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    api.returns.lots(assetId, openPage, matchedPage, pageSize)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [assetId, openPage, matchedPage, pageSize])

  return { data, loading, error }
}
