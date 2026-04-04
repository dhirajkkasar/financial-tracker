'use client'
import React, { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { ASSET_TYPE_LABELS } from '@/constants'
import { usePrivateMoney } from '@/hooks/usePrivateMoney'
import {
  TaxSummaryResponse,
  UnrealisedResponse, UnrealisedLot, HarvestResponse, HarvestOpportunity, AssetType,
} from '@/types'
import { Skeleton } from '@/components/ui/Skeleton'
import { Pagination } from '@/components/ui/Pagination'

const CURRENT_FY = '2024-25'
const FY_OPTIONS = ['2024-25', '2023-24', '2022-23']

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

function ToggleBtn({ expanded, onClick }: { expanded: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border border-border text-[10px] text-tertiary transition-colors hover:border-accent hover:text-accent"
      aria-label={expanded ? 'Collapse' : 'Expand'}
    >
      {expanded ? '−' : '+'}
    </button>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TaxPage() {
  const { formatINR } = usePrivateMoney()
  const [fy, setFy] = useState(CURRENT_FY)
  const [summary, setSummary] = useState<TaxSummaryResponse | null>(null)
  const [unrealised, setUnrealised] = useState<UnrealisedResponse | null>(null)
  const [harvest, setHarvest] = useState<HarvestResponse | null>(null)
  const [loadingSummary, setLoadingSummary] = useState(true)
  const [loadingUnrealised, setLoadingUnrealised] = useState(true)
  const [loadingHarvest, setLoadingHarvest] = useState(true)
  const [expandedClasses, setExpandedClasses] = useState<Set<string>>(new Set())

  const [harvestPage, setHarvestPage] = useState(1)
  const [harvestPageSize, setHarvestPageSize] = useState(10)

  useEffect(() => {
    void (async () => {
      setLoadingSummary(true)
      setSummary(null)
      try {
        const data = await api.tax.summary(fy)
        setSummary(data)
      } finally {
        setLoadingSummary(false)
      }
    })()
  }, [fy])

  useEffect(() => {
    api.tax.unrealised().then(setUnrealised).finally(() => setLoadingUnrealised(false))
    api.tax.harvestOpportunities().then(setHarvest).finally(() => setLoadingHarvest(false))
  }, [])

  const unrealisedRows = useMemo(() => rollupUnrealised(unrealised?.lots ?? []), [unrealised])
  const harvestRows = useMemo(() => rollupHarvest(harvest?.opportunities ?? []), [harvest])

  const harvestTotal = harvestRows.length
  const harvestTotalPages = Math.max(1, Math.ceil(harvestTotal / harvestPageSize))
  const harvestSlice = harvestRows.slice((harvestPage - 1) * harvestPageSize, harvestPage * harvestPageSize)

  const totals = summary?.totals

  function toggleClass(cls: string) {
    setExpandedClasses(prev => {
      const next = new Set(prev)
      if (next.has(cls)) { next.delete(cls) } else { next.add(cls) }
      return next
    })
  }

  return (
    <div className="space-y-8">
      {/* Header + FY selector */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl text-primary">Tax Summary</h1>
        <select
          value={fy}
          onChange={(e) => { setFy(e.target.value); setExpandedClasses(new Set()) }}
          className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-primary focus:outline-none focus:ring-2 focus:ring-accent"
        >
          {FY_OPTIONS.map((f) => <option key={f} value={f}>FY {f}</option>)}
        </select>
      </div>

      {/* Summary stat cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {loadingSummary ? [1,2,3,4].map((i) => <Skeleton key={i} className="h-20 rounded-xl" />) : (<>
          {[
            { label: 'ST Gains', value: totals?.total_st_gain ?? 0 },
            { label: 'LT Gains', value: totals?.total_lt_gain ?? 0 },
            { label: 'Total Gain', value: totals?.total_gain ?? 0 },
            { label: 'Est. Tax', value: totals?.total_tax ?? 0, suffix: totals?.has_slab_rate_items ? '+ slab est.' : undefined },
          ].map(({ label, value, suffix }) => (
            <div key={label} className={`${card} space-y-1`} style={cardStyle}>
              <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-tertiary">{label}</p>
              <p className={`text-xl font-semibold font-mono ${value >= 0 ? 'text-gain' : 'text-loss'}`}>{formatINR(value)}</p>
              {suffix && <p className="text-[10px] text-tertiary">{suffix}</p>}
            </div>
          ))}
        </>)}
      </div>

      {/* ── Realised gains ── */}
      <div className={card} style={cardStyle}>
        <h2 className="mb-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-tertiary">
          Realised Gains — FY {fy}
        </h2>
        {loadingSummary ? (
          <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 rounded" />)}</div>
        ) : !summary?.entries.length ? (
          <p className="py-10 text-center text-sm text-tertiary">No realised gains for FY {fy}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className={th}>Category</th>
                <th className={thr}>ST Gain / Loss</th>
                <th className={thr}>LT Gain / Loss</th>
                <th className={thr}>Exemption</th>
                <th className={thr}>ST Tax Est.</th>
                <th className={thr}>LT Tax Est.</th>
              </tr>
            </thead>
            <tbody>
              {summary.entries.map((row) => {
                const isExpanded = expandedClasses.has(row.asset_class)
                const hasBreakdown = row.asset_breakdown.length > 0
                return (
                  <React.Fragment key={row.asset_class}>
                    {/* Category row */}
                    <tr className="border-b border-border hover:bg-accent-subtle/30 transition-colors">
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          {hasBreakdown && (
                            <ToggleBtn expanded={isExpanded} onClick={() => toggleClass(row.asset_class)} />
                          )}
                          <span className="font-medium text-primary">
                            {ASSET_CLASS_LABELS[row.asset_class] ?? row.asset_class}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 pr-4 text-right"><GainAmt value={row.st_gain} fmt={formatINR} /></td>
                      <td className="py-3 pr-4 text-right"><GainAmt value={row.lt_gain} fmt={formatINR} /></td>
                      <td className="py-3 pr-4 text-right font-mono text-gain">
                        {row.ltcg_exemption_used > 0 ? formatINR(row.ltcg_exemption_used) : '—'}
                      </td>
                      <td className="py-3 pr-4 text-right">
                        <TaxEstimate value={row.st_tax_estimate} fmt={formatINR} />
                        {row.slab_rate_pct != null && (
                          <div className="mt-0.5 text-[10px] text-tertiary">{row.slab_rate_pct}% slab (est.)</div>
                        )}
                      </td>
                      <td className="py-3 text-right">
                        <TaxEstimate value={row.lt_tax_estimate} fmt={formatINR} />
                      </td>
                    </tr>

                    {/* Asset sub-rows */}
                    {isExpanded && row.asset_breakdown.map((asset) => (
                      <tr
                        key={asset.asset_id}
                        className="border-b border-border last:border-0 bg-accent-subtle/20"
                      >
                        <td className="py-2 pl-8 pr-4">
                          <Link
                            href={`/assets/${asset.asset_id}`}
                            className="text-sm font-medium text-accent hover:underline"
                          >
                            {asset.asset_name}
                          </Link>
                          <span className="ml-2 text-[10px] text-tertiary">
                            {ASSET_TYPE_LABELS[asset.asset_type as AssetType] ?? asset.asset_type}
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-right text-sm">
                          <GainAmt value={asset.st_gain} fmt={formatINR} />
                        </td>
                        <td className="py-2 pr-4 text-right text-sm">
                          <GainAmt value={asset.lt_gain} fmt={formatINR} />
                        </td>
                        <td className="py-2 pr-4 text-right text-tertiary text-sm">—</td>
                        <td className="py-2 pr-4 text-right text-sm">
                          <TaxEstimate value={asset.st_tax_estimate} fmt={formatINR} />
                        </td>
                        <td className="py-2 text-right text-sm">
                          <TaxEstimate value={asset.lt_tax_estimate} fmt={formatINR} />
                        </td>
                      </tr>
                    ))}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        )}
        {totals?.has_slab_rate_items && !loadingSummary && (
          <p className="mt-3 text-[11px] text-tertiary">
            * Slab-rate estimates use the configured SLAB_RATE. Actual tax depends on your income bracket.
          </p>
        )}
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
