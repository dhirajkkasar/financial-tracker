'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { PortfolioSnapshot } from '@/types'

export function useSnapshots(from?: string, to?: string) {
  const [data, setData] = useState<PortfolioSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    api.snapshots
      .list(from, to)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [from, to])

  return { data, loading, error }
}
