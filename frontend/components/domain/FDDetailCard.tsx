'use client'
import { FDDetail, ReturnResult } from '@/types'
import { formatXIRR, formatDate } from '@/lib/formatters'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'

const COMPOUNDING_LABEL: Record<string, string> = {
  MONTHLY: 'Monthly',
  QUARTERLY: 'Quarterly',
  HALF_YEARLY: 'Half-yearly',
  YEARLY: 'Annually',
}

function Row({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-border last:border-0">
      <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">{label}</span>
      <span className={`text-sm text-primary ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

interface FDDetailCardProps {
  fd: FDDetail
  returns: ReturnResult
}

export function FDDetailCard({ fd, returns }: FDDetailCardProps) {
  const { formatINR } = usePrivateMoney()
  // Maturity progress
  const startMs = new Date(fd.start_date).getTime()
  const endMs = new Date(fd.maturity_date).getTime()
  const nowMs = Date.now()
  const totalDays = Math.max(1, (endMs - startMs) / 86_400_000)
  const elapsedDays = Math.min(totalDays, Math.max(0, (nowMs - startMs) / 86_400_000))
  const progressPct = Math.round((elapsedDays / totalDays) * 100)

  const xirrPct = returns.xirr != null ? (returns.xirr * 100).toFixed(2) : null
  const rateDelta = xirrPct != null ? parseFloat(xirrPct) - fd.interest_rate_pct : null

  return (
    <div className="space-y-5">
      {/* Header: rate + bank */}
      <div className="flex items-end justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
            {fd.fd_type === 'RD' ? 'Recurring Deposit' : 'Fixed Deposit'} · {fd.bank}
          </p>
          <p className="mt-1 font-mono text-3xl font-medium text-primary">
            {fd.interest_rate_pct.toFixed(2)}%
          </p>
          <p className="mt-0.5 text-xs text-tertiary">
            p.a. compounded {COMPOUNDING_LABEL[fd.compounding]}
          </p>
        </div>
        {fd.tds_applicable && (
          <span className="rounded-full bg-loss-subtle px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-loss">
            TDS applicable
          </span>
        )}
      </div>

      {/* Maturity progress bar */}
      <div>
        <div className="mb-1.5 flex justify-between text-[10px] text-tertiary">
          <span>{formatDate(fd.start_date)}</span>
          <span className="font-semibold text-primary">{progressPct}% elapsed</span>
          <span>{formatDate(fd.maturity_date)}</span>
        </div>
        <div className="h-1.5 w-full rounded-full bg-border">
          <div
            className="h-1.5 rounded-full bg-accent transition-all"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        {returns.days_to_maturity != null && returns.days_to_maturity > 0 && (
          <p className="mt-1.5 text-right text-[10px] text-secondary font-mono">
            {returns.days_to_maturity} days remaining
          </p>
        )}
        {fd.is_matured && (
          <p className="mt-1.5 text-right text-[10px] font-semibold text-gain">Matured</p>
        )}
      </div>

      {/* Detail rows */}
      <div>
        <Row
          label={fd.fd_type === 'RD' ? 'Monthly Instalment' : 'Principal'}
          value={formatINR(fd.principal_amount)}
          mono
        />
        {returns.accrued_value_today != null && (
          <Row label="Accrued Value Today" value={formatINR(returns.accrued_value_today)} mono />
        )}
        {returns.maturity_amount != null && (
          <Row label="Maturity Amount" value={formatINR(returns.maturity_amount)} mono />
        )}
        <Row
          label="Effective XIRR"
          value={
            xirrPct != null ? (
              <span className="flex items-center gap-2">
                <span className="font-mono">{xirrPct}%</span>
                {rateDelta != null && (
                  <span className={`text-[10px] font-semibold ${rateDelta >= 0 ? 'text-gain' : 'text-loss'}`}>
                    ({rateDelta >= 0 ? '+' : ''}{rateDelta.toFixed(2)}% vs stated)
                  </span>
                )}
              </span>
            ) : '—'
          }
        />
      </div>
    </div>
  )
}
