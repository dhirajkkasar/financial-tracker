'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { ReturnResult } from '@/types'

export function useReturns(assetId: number) {
  const [data, setData] = useState<ReturnResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.returns.asset(assetId)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [assetId])

  return { data, loading, error }
}
