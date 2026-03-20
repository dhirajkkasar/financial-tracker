'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { GainersResponse } from '@/types'

export function useGainers(n = 5) {
  const [data, setData] = useState<GainersResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.returns.gainers(n)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [n])

  return { data, loading, error }
}
