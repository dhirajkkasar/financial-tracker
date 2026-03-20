'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { ImportantData } from '@/types'

const CATEGORY_LABELS: Record<string, string> = {
  BANK: 'Bank', MF_FOLIO: 'MF Folio', IDENTITY: 'Identity',
  INSURANCE: 'Insurance', ACCOUNT: 'Account', OTHER: 'Other',
}

export default function PersonalInfoPage() {
  const [items, setItems] = useState<ImportantData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.importantData.list().then(setItems).finally(() => setLoading(false))
  }, [])

  // Group by category
  const groups: Record<string, ImportantData[]> = {}
  items.forEach((item) => {
    groups[item.category] = [...(groups[item.category] || []), item]
  })

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-gray-800">Personal Info</h1>
      {loading ? (
        <p className="text-sm text-gray-400">Loading...</p>
      ) : Object.keys(groups).length === 0 ? (
        <p className="text-sm text-gray-400">No important data entries yet</p>
      ) : (
        Object.entries(groups).map(([category, entries]) => (
          <div key={category}>
            <h2 className="mb-3 text-sm font-semibold text-gray-600">{CATEGORY_LABELS[category] || category}</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {entries.map((entry) => {
                let fields: Record<string, string> = {}
                try { fields = JSON.parse(entry.fields_json) } catch {}
                return (
                  <div key={entry.id} className="rounded-xl border bg-white p-4 shadow-sm">
                    <p className="font-medium text-gray-800">{entry.label}</p>
                    {Object.entries(fields).map(([k, v]) => (
                      <p key={k} className="mt-1 text-xs text-gray-500"><span className="font-medium">{k}:</span> {v}</p>
                    ))}
                  </div>
                )
              })}
            </div>
          </div>
        ))
      )}
    </div>
  )
}
