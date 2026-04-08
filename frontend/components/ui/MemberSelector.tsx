'use client'

import { useRef, useState, useEffect } from 'react'
import { useMembers } from '@/context/MemberContext'

function maskPan(pan: string): string {
  return pan.length >= 6 ? `XXXX${pan.slice(4, 8)}${pan.slice(-1)}` : pan
}

export default function MemberSelector() {
  const { members, selectedMemberIds, setSelectedMemberIds, loading } = useMembers()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  if (loading || members.length === 0) return null

  const allSelected = selectedMemberIds.length === members.length
  const label = allSelected
    ? 'All'
    : selectedMemberIds.length === 1
      ? (members.find((m) => m.id === selectedMemberIds[0])?.name ?? 'Select')
      : `${selectedMemberIds.length} Members`

  function toggle(id: number) {
    const next = selectedMemberIds.includes(id)
      ? selectedMemberIds.filter((x) => x !== id)
      : [...selectedMemberIds, id]
    setSelectedMemberIds(next.length === 0 ? members.map((m) => m.id) : next)
  }

  if (members.length === 1) return null

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="px-3 py-1.5 text-sm rounded-md border border-border bg-bg-page text-primary hover:bg-border transition-colors"
      >
        {label} ▾
      </button>
      {open && (
        <div className="absolute left-0 mt-1 w-56 rounded-md border border-border bg-bg-page shadow-lg z-50">
          {members.map((m) => (
            <label
              key={m.id}
              className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-border cursor-pointer"
            >
              <input
                type="checkbox"
                checked={selectedMemberIds.includes(m.id)}
                onChange={() => toggle(m.id)}
                className="rounded"
              />
              <span className="text-primary">{m.name}</span>
              <span className="text-secondary text-xs ml-auto">{maskPan(m.pan)}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
