'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { AllocationResponse } from '@/types'

export function useAllocation() {
  const [data, setData] = useState<AllocationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.returns.allocation()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return { data, loading, error }
}
