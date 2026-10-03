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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset loading/error synchronously on refetch (standard fetch pattern)
    setLoading(true)
    setError(null)
    // Note: assetId 0 (invalid ?id=) still fires a request that 404s into
    // error state — harmless, since the detail page renders "Invalid link"
    // without reading lots data on that path.
    api.returns.lots(assetId, openPage, matchedPage, pageSize)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [assetId, openPage, matchedPage, pageSize])

  return { data, loading, error }
}
