'use client'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { AssetTypeBreakdownEntry } from '@/types'
import { ASSET_TYPE_COLORS, ASSET_TYPE_LABELS } from '@/constants'
import { Skeleton } from '@/components/ui/Skeleton'
import { usePrivateMode } from '@/context/PrivateModeContext'
import { useDarkMode } from '@/context/DarkModeContext'

interface AssetTypeDonutProps {
  data: AssetTypeBreakdownEntry[]
  loading?: boolean
}

function formatINRCompact(n: number) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n)
}

function DonutTooltip({ active, payload, total }: { active?: boolean; payload?: { name: string; value: number }[]; total: number }) {
  const { isPrivate } = usePrivateMode()
  if (!active || !payload?.length) return null
  const { name, value } = payload[0]
  const pct = total > 0 ? ((value / total) * 100).toFixed(2) : '0.00'
  return (
    <div style={{ background: '#1a1a18', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '8px 12px', boxShadow: '0 4px 16px rgba(0,0,0,0.25)' }}>
      <p style={{ color: '#a0a09c', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>{name}</p>
      <p style={{ color: '#fff', fontSize: 13, fontFamily: 'var(--font-dm-mono, monospace)', fontWeight: 500 }}>{isPrivate ? '*****' : formatINRCompact(value)}</p>
      <p style={{ color: '#6b6b67', fontSize: 11, fontFamily: 'var(--font-dm-mono, monospace)', marginTop: 2 }}>{pct}% of portfolio</p>
    </div>
  )
}

export function AssetTypeDonut({ data, loading }: AssetTypeDonutProps) {
  const { isDark } = useDarkMode()
  const legendColor = isDark ? '#9a9a96' : '#6b6b67'

  if (loading) {
    return <Skeleton className="mx-auto h-48 w-48 rounded-full" />
  }
  if (!data || data.length === 0) {
    return <div className="flex h-48 items-center justify-center text-sm text-tertiary">No allocation data</div>
  }

  const total = data.reduce((sum, d) => sum + (d.total_current_value ?? 0), 0)
  const chartData = data
    .filter((entry) => (entry.total_current_value ?? 0) > 0)
    .map((entry) => ({
      name: ASSET_TYPE_LABELS[entry.asset_type] ?? entry.asset_type,
      value: entry.total_current_value,
      asset_type: entry.asset_type,
    }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie data={chartData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={88} strokeWidth={2} stroke="var(--color-card)">
          {chartData.map((entry, i) => (
            <Cell key={i} fill={ASSET_TYPE_COLORS[entry.asset_type] ?? '#94a3b8'} />
          ))}
        </Pie>
        <Tooltip content={<DonutTooltip total={total} />} />
        <Legend
          iconType="circle"
          iconSize={7}
          formatter={(value) => <span style={{ fontSize: 11, color: legendColor, fontFamily: 'var(--font-dm-sans)' }}>{value}</span>}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}
