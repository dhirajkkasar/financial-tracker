'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { AssetTypeBreakdownEntry } from '@/types'

export function useBreakdown() {
  const [breakdown, setBreakdown] = useState<AssetTypeBreakdownEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.returns.breakdown()
      .then((r) => setBreakdown(r.breakdown))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return { breakdown, loading, error }
}
