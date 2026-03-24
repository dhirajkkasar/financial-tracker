'use client'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { PortfolioSnapshot } from '@/types'
import { usePrivateMode } from '@/context/PrivateModeContext'

function formatINRCompact(n: number) {
  if (n >= 1_00_00_000) return `₹${(n / 1_00_00_000).toFixed(2)}Cr`
  if (n >= 1_00_000) return `₹${(n / 1_00_000).toFixed(2)}L`
  if (n >= 1_000) return `₹${(n / 1_000).toFixed(1)}K`
  return `₹${n.toFixed(0)}`
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

function NetWorthTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  const { isPrivate } = usePrivateMode()
  if (!active || !payload?.length) return null
  const value = payload[0].value
  return (
    <div style={{
      background: '#1a1a18',
      border: '1px solid rgba(255,255,255,0.08)',
      borderRadius: 8,
      padding: '8px 12px',
      boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
    }}>
      <p style={{ color: '#a0a09c', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>
        {label ? formatDate(label) : ''}
      </p>
      <p style={{ color: '#fff', fontSize: 13, fontFamily: 'var(--font-dm-mono, monospace)', fontWeight: 500 }}>
        {isPrivate ? '*****' : formatINRCompact(value)}
      </p>
    </div>
  )
}

interface NetWorthChartProps {
  data: PortfolioSnapshot[]
  loading?: boolean
}

export function NetWorthChart({ data, loading }: NetWorthChartProps) {
  const { isPrivate } = usePrivateMode()
  if (loading) {
    return <div className="h-48 animate-pulse rounded bg-border" />
  }
  if (!data || data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-tertiary">
        No snapshot data yet — data appears after the first daily refresh.
      </div>
    )
  }

  const chartData = data.map((s) => ({
    date: s.date,
    value: s.total_value_inr,
  }))

  const values = chartData.map((d) => d.value)
  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)
  const padding = (maxVal - minVal) * 0.1 || maxVal * 0.05

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="netWorthGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#c9a96e" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#c9a96e" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={formatDate}
          tick={{ fill: '#6b6b67', fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tickFormatter={(v) => isPrivate ? '*****' : formatINRCompact(v)}
          tick={{ fill: '#6b6b67', fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          domain={[Math.max(0, minVal - padding), maxVal + padding]}
          width={52}
        />
        <Tooltip content={<NetWorthTooltip />} />
        <Area
          type="monotone"
          dataKey="value"
          stroke="#c9a96e"
          strokeWidth={2}
          fill="url(#netWorthGradient)"
          dot={false}
          activeDot={{ r: 4, fill: '#c9a96e', strokeWidth: 0 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
