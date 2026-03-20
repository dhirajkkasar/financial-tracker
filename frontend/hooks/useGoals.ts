'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { Goal } from '@/types'

export function useGoals() {
  const [goals, setGoals] = useState<Goal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.goals.list()
      .then(setGoals)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return { goals, loading, error }
}
