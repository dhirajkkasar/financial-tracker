'use client'

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react'
import { api } from '@/lib/api'
import { Member } from '@/constants'

interface MemberContextType {
  members: Member[]
  selectedMemberIds: number[]
  setSelectedMemberIds: (ids: number[]) => void
  loading: boolean
  error: string | null
}

const MemberContext = createContext<MemberContextType>({
  members: [],
  selectedMemberIds: [],
  setSelectedMemberIds: () => {},
  loading: true,
  error: null,
})

const STORAGE_KEY = 'selectedMemberIds'

export function MemberProvider({ children }: { children: ReactNode }) {
  const [members, setMembers] = useState<Member[]>([])
  const [selectedMemberIds, setSelectedMemberIdsState] = useState<number[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.members
      .list()
      .then((data) => {
        setMembers(data)
        setError(null)
        const stored = localStorage.getItem(STORAGE_KEY)
        if (stored) {
          try {
            const ids = JSON.parse(stored) as number[]
            const valid = ids.filter((id) => data.some((m) => m.id === id))
            setSelectedMemberIdsState(valid.length > 0 ? valid : data.map((m) => m.id))
          } catch {
            setSelectedMemberIdsState(data.map((m) => m.id))
          }
        } else {
          setSelectedMemberIdsState(data.map((m) => m.id))
        }
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const setSelectedMemberIds = useCallback((ids: number[]) => {
    setSelectedMemberIdsState(ids)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
  }, [])

  return (
    <MemberContext.Provider value={{ members, selectedMemberIds, setSelectedMemberIds, loading, error }}>
      {error && !loading && (
        <div className="mx-auto max-w-7xl px-4 pt-4">
          <div className="flex items-center justify-between gap-3 rounded-xl border border-loss/30 bg-loss-subtle/40 px-4 py-3 text-sm">
            <p className="text-loss">Couldn&apos;t load members: {error}</p>
            <button
              onClick={() => window.location.reload()}
              className="shrink-0 rounded-lg border border-loss/40 px-3 py-1 text-xs font-medium text-loss hover:bg-loss/10 transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      )}
      {children}
    </MemberContext.Provider>
  )
}

export function useMembers() {
  return useContext(MemberContext)
}
