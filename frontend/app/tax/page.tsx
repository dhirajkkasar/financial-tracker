'use client'
import React, { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { ASSET_TYPE_LABELS } from '@/constants'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'
import { useMembers } from '@/context/MemberContext'
import {
  TaxSummaryResponse,
  UnrealisedResponse, UnrealisedLot, HarvestResponse, HarvestOpportunity, AssetType,
} from '@/types'
import { Skeleton } from '@/components/ui/Skeleton'
import { Pagination } from '@/components/ui/Pagination'

function inferCurrentFy(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = now.getMonth() + 1 // 1-based
  const startYear = month >= 4 ? year : year - 1
  return `${startYear}-${String(startYear + 1).slice(-2)}`
}

function pickDefaultFy(fys: string[]): string {
  const current = inferCurrentFy()
  return fys.includes(current) ? current : fys[fys.length - 1] ?? current
}

const ASSET_CLASS_LABELS: Record<string, string> = {
  EQUITY: 'Equity',
  DEBT: 'Debt',
  GOLD: 'Gold',
  REAL_ESTATE: 'Real Estate',
}

// Unrealised section still groups by asset_class (now in response)
interface UnrealisedRow { cls: string; st: number; lt: number }

function rollupUnrealised(lots: UnrealisedLot[]): UnrealisedRow[] {
  const map: Record<string, UnrealisedRow> = {}
  for (const lot of lots) {
    if (lot.unrealised_gain == null) continue
    const cls = lot.asset_class ?? 'Other'
    if (!map[cls]) map[cls] = { cls, st: 0, lt: 0 }
    if (lot.is_short_term) map[cls].st += lot.unrealised_gain
    else map[cls].lt += lot.unrealised_gain
  }
  return Object.values(map).sort((a, b) => Math.abs(b.st + b.lt) - Math.abs(a.st + a.lt))
}

interface HarvestRow { asset_id: number; asset_name: string; asset_type: string; st_loss: number; lt_loss: number; total_loss: number }

function rollupHarvest(opps: HarvestOpportunity[]): HarvestRow[] {
  const map: Record<number, HarvestRow> = {}
  for (const o of opps) {
    if (!map[o.asset_id]) map[o.asset_id] = { asset_id: o.asset_id, asset_name: o.asset_name, asset_type: o.asset_type, st_loss: 0, lt_loss: 0, total_loss: 0 }
    const r = map[o.asset_id]
    if (o.is_short_term) r.st_loss += o.unrealised_loss
    else r.lt_loss += o.unrealised_loss
    r.total_loss += o.unrealised_loss
  }
  return Object.values(map).sort((a, b) => b.total_loss - a.total_loss)
}

// ── Shared styles ─────────────────────────────────────────────────────────────

const card = 'rounded-xl border border-border bg-card p-5'
const cardStyle = { boxShadow: 'var(--shadow-card)' }
const th = 'pb-3 text-left text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary'
const thr = `${th} text-right`

function GainAmt({ value, fmt }: { value: number; fmt: (n: number) => string }) {
  if (value === 0) return <span className="text-tertiary">—</span>
  return <span className={`font-mono ${value >= 0 ? 'text-gain' : 'text-loss'}`}>{fmt(value)}</span>
}

function TaxEstimate({ value, fmt }: { value: number; fmt: (n: number) => string }) {
  if (value === 0) return <span className="text-tertiary">—</span>
  return <span className="font-mono text-loss">{fmt(value)}</span>
}

// ── Main page ─────────────────────────────────────────────────────────────────

function maskPan(pan: string): string {
  return pan.length >= 6 ? `XXXX${pan.slice(4, 8)}${pan.slice(-1)}` : pan
}

export default function TaxPage() {
  const { formatINR } = usePrivateMoney()
  const { members } = useMembers()
  const [taxMemberId, setTaxMemberId] = useState<number | null>(null)
  const [fyOptions, setFyOptions] = useState<string[]>([])
  const [fy, setFy] = useState('')
  const [summary, setSummary] = useState<TaxSummaryResponse | null>(null)
  const [unrealised, setUnrealised] = useState<UnrealisedResponse | null>(null)
  const [harvest, setHarvest] = useState<HarvestResponse | null>(null)
  const [loadingSummary, setLoadingSummary] = useState(true)
  const [loadingUnrealised, setLoadingUnrealised] = useState(true)
  const [loadingHarvest, setLoadingHarvest] = useState(true)

  const [harvestPage, setHarvestPage] = useState(1)
  const [harvestPageSize, setHarvestPageSize] = useState(10)

  // Set default member when members load
  useEffect(() => {
    if (members.length > 0 && taxMemberId === null) {
      setTaxMemberId(members[0].id)
    }
  }, [members, taxMemberId])

  useEffect(() => {
    api.tax.fiscalYears().then(({ fiscal_years }) => {
      setFyOptions(fiscal_years)
      setFy(pickDefaultFy(fiscal_years))
    })
  }, [])

  useEffect(() => {
    if (taxMemberId === null) return
    setLoadingUnrealised(true)
    setLoadingHarvest(true)
    api.tax.unrealised(taxMemberId).then(setUnrealised).finally(() => setLoadingUnrealised(false))
    api.tax.harvestOpportunities(taxMemberId).then(setHarvest).finally(() => setLoadingHarvest(false))
  }, [taxMemberId])

  useEffect(() => {
    if (!fy || taxMemberId === null) return
    void (async () => {
      setLoadingSummary(true)
      setSummary(null)
      try {
        const data = await api.tax.summary(fy, taxMemberId)
        setSummary(data)
      } finally {
        setLoadingSummary(false)
      }
    })()
  }, [fy, taxMemberId])

  const unrealisedRows = useMemo(() => rollupUnrealised(unrealised?.lots ?? []), [unrealised])
  const harvestRows = useMemo(() => rollupHarvest(harvest?.opportunities ?? []), [harvest])

  const harvestTotal = harvestRows.length
  const harvestTotalPages = Math.max(1, Math.ceil(harvestTotal / harvestPageSize))
  const harvestSlice = harvestRows.slice((harvestPage - 1) * harvestPageSize, harvestPage * harvestPageSize)

  return (
    <div className="space-y-8">
      {/* Header + member + FY selector */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-2xl text-primary">Tax Summary</h1>
        <div className="flex items-center gap-2">
          {members.length > 0 && (
            <select
              value={taxMemberId ?? ''}
              onChange={(e) => setTaxMemberId(Number(e.target.value))}
              className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent"
            >
              {members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} — {maskPan(m.pan)}
                </option>
              ))}
            </select>
          )}
          <select
            value={fy}
            onChange={(e) => setFy(e.target.value)}
            className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent"
          >
            {fyOptions.map((f) => <option key={f} value={f}>FY {f}</option>)}
          </select>
        </div>
      </div>

      {/* ── Short-Term Capital Gains ── */}
      <div className={card} style={cardStyle}>
        <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
          Short-Term Capital Gains — FY {fy}
        </h2>
        {loadingSummary ? (
          <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 rounded" />)}</div>
        ) : !summary?.stcg.assets.length ? (
          <p className="py-10 text-center text-sm text-tertiary">No short-term capital gains for FY {fy}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className={th}>Asset</th>
                <th className={thr}>Gain / Loss</th>
                <th className={thr}>Tax Rate</th>
                <th className={thr}>Tax Est.</th>
              </tr>
            </thead>
            <tbody>
              {summary.stcg.assets.map((a) => (
                <tr key={a.asset_id} className="border-b border-border last:border-0 hover:bg-accent-subtle/30 transition-colors">
                  <td className="py-3 pr-4">
                    <Link href={`/assets/${a.asset_id}`} className="font-medium text-accent hover:underline">{a.asset_name}</Link>
                    <span className="ml-2 text-[10px] text-tertiary">{ASSET_TYPE_LABELS[a.asset_type as AssetType] ?? a.asset_type}</span>
                  </td>
                  <td className="py-3 pr-4 text-right"><GainAmt value={a.gain} fmt={formatINR} /></td>
                  <td className="py-3 pr-4 text-right text-xs text-secondary">
                    {a.is_slab ? 'slab' : a.tax_rate_pct !== null ? `${a.tax_rate_pct}%` : '—'}
                  </td>
                  <td className="py-3 text-right"><TaxEstimate value={a.tax_estimate} fmt={formatINR} /></td>
                </tr>
              ))}
              {/* Footer total */}
              <tr className="border-t-2 border-border font-semibold">
                <td className="py-3 pr-4 text-primary">Total STCG</td>
                <td className="py-3 pr-4 text-right"><GainAmt value={summary.stcg.total_gain} fmt={formatINR} /></td>
                <td className="py-3 pr-4" />
                <td className="py-3 text-right"><TaxEstimate value={summary.stcg.total_tax} fmt={formatINR} /></td>
              </tr>
            </tbody>
          </table>
        )}
        {summary?.stcg.has_slab_items && !loadingSummary && (
          <p className="mt-3 text-[11px] text-tertiary">* Slab-rate estimates use the configured SLAB_RATE. Actual tax depends on your income bracket.</p>
        )}
      </div>

      {/* ── Long-Term Capital Gains ── */}
      <div className={card} style={cardStyle}>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
            Long-Term Capital Gains — FY {fy}
          </h2>
          {summary && summary.ltcg.ltcg_exemption_used > 0 && !loadingSummary && (
            <span className="text-xs text-tertiary">
              Exemption: <span className="font-mono text-gain">{formatINR(summary.ltcg.ltcg_exemption_used)}</span>
            </span>
          )}
        </div>
        {loadingSummary ? (
          <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 rounded" />)}</div>
        ) : !summary?.ltcg.assets.length ? (
          <p className="py-10 text-center text-sm text-tertiary">No long-term capital gains for FY {fy}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className={th}>Asset</th>
                <th className={thr}>Gain / Loss</th>
                <th className={thr}>Tax Rate</th>
                <th className={thr}>Tax Est.</th>
              </tr>
            </thead>
            <tbody>
              {summary.ltcg.assets.map((a) => (
                <tr key={a.asset_id} className="border-b border-border last:border-0 hover:bg-accent-subtle/30 transition-colors">
                  <td className="py-3 pr-4">
                    <Link href={`/assets/${a.asset_id}`} className="font-medium text-accent hover:underline">{a.asset_name}</Link>
                    <span className="ml-2 text-[10px] text-tertiary">{ASSET_TYPE_LABELS[a.asset_type as AssetType] ?? a.asset_type}</span>
                    {a.ltcg_exempt_eligible && (
                      <span className="ml-2 rounded bg-gain/10 px-1.5 py-0.5 text-[9px] font-medium text-gain">112A</span>
                    )}
                  </td>
                  <td className="py-3 pr-4 text-right"><GainAmt value={a.gain} fmt={formatINR} /></td>
                  <td className="py-3 pr-4 text-right text-xs text-secondary">
                    {a.is_slab ? 'slab' : a.tax_rate_pct !== null ? `${a.tax_rate_pct}%` : '—'}
                  </td>
                  <td className="py-3 text-right"><TaxEstimate value={a.tax_estimate} fmt={formatINR} /></td>
                </tr>
              ))}
              {/* Footer total */}
              <tr className="border-t-2 border-border font-semibold">
                <td className="py-3 pr-4 text-primary">Total LTCG</td>
                <td className="py-3 pr-4 text-right"><GainAmt value={summary.ltcg.total_gain} fmt={formatINR} /></td>
                <td className="py-3 pr-4" />
                <td className="py-3 text-right"><TaxEstimate value={summary.ltcg.total_tax} fmt={formatINR} /></td>
              </tr>
            </tbody>
          </table>
        )}
        {summary?.ltcg.has_slab_items && !loadingSummary && (
          <p className="mt-3 text-[11px] text-tertiary">* Slab-rate estimates use the configured SLAB_RATE. Actual tax depends on your income bracket.</p>
        )}
      </div>

      {/* ── Interest Income ── */}
      <div className={card} style={cardStyle}>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
            Interest Income — FY {fy}
          </h2>
          {summary && !loadingSummary && (
            <span className="text-xs text-tertiary">Slab rate: {summary.interest.slab_rate_pct}%</span>
          )}
        </div>
        {loadingSummary ? (
          <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 rounded" />)}</div>
        ) : !summary?.interest.assets.length ? (
          <p className="py-10 text-center text-sm text-tertiary">No interest income for FY {fy}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className={th}>Asset</th>
                <th className={thr}>Interest</th>
                <th className={thr}>Tax Est.</th>
              </tr>
            </thead>
            <tbody>
              {summary.interest.assets.map((a) => (
                <tr key={a.asset_id} className="border-b border-border last:border-0 hover:bg-accent-subtle/30 transition-colors">
                  <td className="py-3 pr-4">
                    <Link href={`/assets/${a.asset_id}`} className="font-medium text-accent hover:underline">{a.asset_name}</Link>
                    <span className="ml-2 text-[10px] text-tertiary">{ASSET_TYPE_LABELS[a.asset_type as AssetType] ?? a.asset_type}</span>
                  </td>
                  <td className="py-3 pr-4 text-right font-mono text-gain">{formatINR(a.interest)}</td>
                  <td className="py-3 text-right"><TaxEstimate value={a.tax_estimate} fmt={formatINR} /></td>
                </tr>
              ))}
              {/* Footer total */}
              <tr className="border-t-2 border-border font-semibold">
                <td className="py-3 pr-4 text-primary">Total Interest</td>
                <td className="py-3 pr-4 text-right font-mono text-gain">{summary ? formatINR(summary.interest.total_interest) : '—'}</td>
                <td className="py-3 text-right"><TaxEstimate value={summary?.interest.total_tax ?? 0} fmt={formatINR} /></td>
              </tr>
            </tbody>
          </table>
        )}
        <p className="mt-3 text-[11px] text-tertiary">Interest income is taxed at your income slab rate.</p>
      </div>

      {/* ── Unrealised gains ── */}
      <div className={card} style={cardStyle}>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">Unrealised Gains (Open Positions)</h2>
          {unrealised && (
            <span className="text-xs text-tertiary">
              Total: <span className={`font-mono ${unrealised.totals.total_unrealised >= 0 ? 'text-gain' : 'text-loss'}`}>{formatINR(unrealised.totals.total_unrealised)}</span>
              {unrealised.totals.near_threshold_count > 0 && (
                <span className="ml-3 text-gold">⚠ {unrealised.totals.near_threshold_count} near ₹1.25L threshold</span>
              )}
            </span>
          )}
        </div>
        {loadingUnrealised ? (
          <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 rounded" />)}</div>
        ) : unrealisedRows.length === 0 ? (
          <p className="py-8 text-center text-sm text-tertiary">No open positions with price data</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className={th}>Category</th>
                <th className={thr}>ST Unrealised</th>
                <th className={thr}>LT Unrealised</th>
                <th className={thr}>Total</th>
              </tr>
            </thead>
            <tbody>
              {unrealisedRows.map((row) => (
                <tr key={row.cls} className="border-b border-border last:border-0 hover:bg-accent-subtle/30 transition-colors">
                  <td className="py-3 pr-4 font-medium text-primary">{ASSET_CLASS_LABELS[row.cls] ?? row.cls}</td>
                  <td className="py-3 pr-4 text-right"><GainAmt value={row.st} fmt={formatINR} /></td>
                  <td className="py-3 pr-4 text-right"><GainAmt value={row.lt} fmt={formatINR} /></td>
                  <td className={`py-3 text-right font-mono font-medium ${row.st + row.lt >= 0 ? 'text-gain' : 'text-loss'}`}>
                    {formatINR(row.st + row.lt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Tax-loss harvesting ── */}
      <div className={card} style={cardStyle}>
        <div className="mb-1">
          <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">Tax-Loss Harvesting Opportunities</h2>
          <p className="mt-1 text-xs text-tertiary">Positions with unrealised losses — consider selling to offset gains</p>
        </div>
        {loadingHarvest ? (
          <div className="mt-4 space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 rounded" />)}</div>
        ) : harvestRows.length === 0 ? (
          <p className="py-8 text-center text-sm text-tertiary">No loss-making positions</p>
        ) : (
          <>
            <table className="mt-4 w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className={th}>Asset</th>
                  <th className={th}>Type</th>
                  <th className={thr}>ST Loss</th>
                  <th className={thr}>LT Loss</th>
                  <th className={thr}>Total Loss</th>
                </tr>
              </thead>
              <tbody>
                {harvestSlice.map((row) => (
                  <tr key={row.asset_id} className="border-b border-border last:border-0 hover:bg-loss-subtle/30 transition-colors">
                    <td className="py-2.5 pr-4">
                      <Link href={`/assets/${row.asset_id}`} className="font-medium text-accent hover:underline">
                        {row.asset_name}
                      </Link>
                    </td>
                    <td className="py-2.5 pr-4 text-xs text-secondary">{ASSET_TYPE_LABELS[row.asset_type as AssetType]}</td>
                    <td className="py-2.5 pr-4 text-right font-mono text-loss">
                      {row.st_loss > 0 ? formatINR(row.st_loss) : '—'}
                    </td>
                    <td className="py-2.5 pr-4 text-right font-mono text-loss">
                      {row.lt_loss > 0 ? formatINR(row.lt_loss) : '—'}
                    </td>
                    <td className="py-2.5 text-right font-mono font-semibold text-loss">
                      {formatINR(row.total_loss)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination
              page={harvestPage}
              pageSize={harvestPageSize}
              total={harvestTotal}
              totalPages={harvestTotalPages}
              onPageChange={setHarvestPage}
              onPageSizeChange={(s) => { setHarvestPageSize(s); setHarvestPage(1) }}
            />
          </>
        )}
      </div>
    </div>
  )
}
