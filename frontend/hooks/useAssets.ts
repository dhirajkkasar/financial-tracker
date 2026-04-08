'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { Asset, AssetType } from '@/types'
import { useMembers } from '@/context/MemberContext'

export function useAssets(type?: AssetType, active = true) {
  const { selectedMemberIds } = useMembers()
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const memberKey = selectedMemberIds.join(',')

  useEffect(() => {
    setLoading(true)
    api.assets.list({ type, active, member_ids: selectedMemberIds })
      .then(setAssets)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, active, memberKey])

  return { assets, loading, error }
}
