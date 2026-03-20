'use client'
import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { ImportantData } from '@/types'

// Display order for top-level sections
const SECTION_ORDER = ['IDENTITY', 'BANK', 'ACCOUNT', 'MF_FOLIO', 'INSURANCE', 'OTHER'] as const

const SECTION_LABELS: Record<string, string> = {
  IDENTITY: 'Personal & Employment Details',
  BANK: 'Bank Accounts',
  ACCOUNT: 'Investment Accounts',
  MF_FOLIO: 'Mutual Fund AMCs',
  INSURANCE: 'Insurance',
  OTHER: 'Other',
}

// For OTHER items, sub-group by notes field in this order
const OTHER_SUBSECTION_ORDER = ['Home Utilities Details', 'Property Details']

function InfoCard({ entry }: { entry: ImportantData }) {
  const fields = entry.fields ?? {}
  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <p className="mb-2.5 font-semibold text-gray-800 text-sm">{entry.label}</p>
      <div className="space-y-1">
        {Object.entries(fields).map(([k, v]) => (
          <div key={k} className="flex gap-1.5 text-xs">
            <span className="font-medium text-gray-500 shrink-0 min-w-[100px]">{k}:</span>
            <span className="text-gray-700 break-words">{v}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Section({ title, entries }: { title: string; entries: ImportantData[] }) {
  return (
    <div>
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-gray-400">{title}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {entries.map((entry) => <InfoCard key={entry.id} entry={entry} />)}
      </div>
    </div>
  )
}

export default function PersonalInfoPage() {
  const [items, setItems] = useState<ImportantData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.importantData.list().then(setItems).finally(() => setLoading(false))
  }, [])

  const groups: Partial<Record<string, ImportantData[]>> = {}
  items.forEach((item) => {
    groups[item.category] = [...(groups[item.category] ?? []), item]
  })

  return (
    <div className="space-y-8">
      <h1 className="text-xl font-semibold text-gray-800">Personal Info</h1>
      {loading ? (
        <p className="text-sm text-gray-400">Loading...</p>
      ) : Object.keys(groups).length === 0 ? (
        <p className="text-sm text-gray-400">No important data entries yet</p>
      ) : (
        SECTION_ORDER.filter((cat) => (groups[cat]?.length ?? 0) > 0).map((category) => {
          const entries = groups[category]!

          if (category === 'OTHER') {
            // Sub-group by notes field
            const subGroups: Record<string, ImportantData[]> = {}
            entries.forEach((e) => {
              const key = e.notes ?? 'Other'
              subGroups[key] = [...(subGroups[key] ?? []), e]
            })
            const subKeys = [
              ...OTHER_SUBSECTION_ORDER.filter((k) => subGroups[k]),
              ...Object.keys(subGroups).filter((k) => !OTHER_SUBSECTION_ORDER.includes(k)),
            ]
            return (
              <div key={category} className="space-y-6">
                {subKeys.map((sub) => (
                  <Section key={sub} title={sub} entries={subGroups[sub]} />
                ))}
              </div>
            )
          }

          return (
            <Section key={category} title={SECTION_LABELS[category] ?? category} entries={entries} />
          )
        })
      )}
    </div>
  )
}
