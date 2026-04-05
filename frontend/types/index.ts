export type AssetType =
  | 'STOCK_IN' | 'STOCK_US' | 'MF' | 'FD' | 'RD'
  | 'PPF' | 'EPF' | 'NPS' | 'GOLD' | 'SGB' | 'REAL_ESTATE' | 'RSU'

export type AssetClass = 'EQUITY' | 'DEBT' | 'GOLD' | 'REAL_ESTATE' | 'MIXED'

export type TransactionType =
  | 'BUY' | 'SELL' | 'SIP' | 'REDEMPTION' | 'DIVIDEND' | 'INTEREST'
  | 'CONTRIBUTION' | 'WITHDRAWAL' | 'SWITCH_IN' | 'SWITCH_OUT'
  | 'BONUS' | 'SPLIT' | 'VEST' | 'TRANSFER' | 'BILLING'

export interface GoalRef {
  id: number
  name: string
}

export interface Asset {
  id: number
  name: string
  identifier: string | null
  asset_type: AssetType
  asset_class: AssetClass
  currency: string
  is_active: boolean
  scheme_category: string | null
  notes: string | null
  created_at: string
  goals: GoalRef[]
}

export interface Transaction {
  id: number
  txn_id: string
  asset_id: number
  type: TransactionType
  date: string
  units: number | null
  price_per_unit: number | null
  forex_rate: number | null
  amount_inr: number   // INR decimal
  charges_inr: number  // INR decimal
  lot_id: string | null
  notes: string | null
  created_at: string
}

export interface Valuation {
  id: number
  asset_id: number
  date: string
  value_inr: number  // INR decimal
  source: string
  notes: string | null
}

export interface FDDetail {
  id: number
  asset_id: number
  bank: string
  fd_type: 'FD' | 'RD'
  principal_amount: number  // INR decimal
  interest_rate_pct: number
  compounding: 'MONTHLY' | 'QUARTERLY' | 'HALF_YEARLY' | 'YEARLY'
  start_date: string
  maturity_date: string
  maturity_amount: number | null
  is_matured: boolean
  tds_applicable: boolean
  notes: string | null
}

export interface GoalAllocationWithAsset {
  id: number
  goal_id: number
  asset_id: number
  asset_name: string
  asset_type: AssetType
  allocation_pct: number
  current_value_inr: number | null
  value_toward_goal: number | null
}

export interface Goal {
  id: number
  name: string
  target_amount_inr: number  // INR decimal
  target_date: string
  notes: string | null
  created_at: string
  current_value_inr: number
  remaining_inr: number
  progress_pct: number
  allocations: GoalAllocationWithAsset[]
}

export interface GoalAllocation {
  id: number
  goal_id: number
  asset_id: number
  allocation_pct: number
}

export interface ReturnResult {
  asset_id: number
  asset_type: string
  xirr: number | null
  cagr: number | null
  absolute_return: number | null  // current P&L (unrealised only)
  alltime_pnl?: number | null     // current P&L + realised gains; null when not computable
  total_invested: number | null
  current_value: number | null
  message: string | null
  maturity_amount: number | null
  accrued_value_today: number | null
  days_to_maturity: number | null
  // Currently held units and average cost (market-based assets only)
  total_units?: number | null
  avg_price?: number | null
  current_price?: number | null
  // Lot-based gain breakdown (null for non-lot assets or SGB)
  st_unrealised_gain?: number | null
  lt_unrealised_gain?: number | null
  st_realised_gain?: number | null
  lt_realised_gain?: number | null
  // FD/RD tax fields
  taxable_interest?: number | null
  potential_tax_30pct?: number | null
  // Price cache metadata
  price_is_stale?: boolean | null
  price_fetched_at?: string | null
}

export interface PortfolioSnapshot {
  date: string
  total_value_inr: number
  breakdown: Record<string, number>
}

export interface BulkReturnResponse {
  returns: ReturnResult[]
}

export interface OverviewReturns {
  total_invested: number
  total_current_value: number
  absolute_return: number
  xirr: number | null
  st_unrealised_gain?: number | null
  lt_unrealised_gain?: number | null
  st_realised_gain?: number | null
  lt_realised_gain?: number | null
  total_taxable_interest?: number | null
  total_potential_tax?: number | null
}

export interface AssetTypeBreakdownEntry {
  asset_type: AssetType
  total_invested: number
  total_current_value: number
  xirr: number | null
  current_pnl: number | null
  alltime_pnl: number | null
}

export interface BreakdownResponse {
  breakdown: AssetTypeBreakdownEntry[]
}

export interface LotEntry {
  lot_id: string
  buy_date: string
  units_remaining: number
  buy_price_per_unit: number
  buy_amount_inr: number
  current_value: number | null
  unrealised_gain: number | null
  holding_days: number
  is_short_term: boolean
}

export interface MatchedSell {
  lot_id: string
  sell_date: string
  buy_date: string
  units_sold: number
  units_remaining: number
  buy_price_per_unit: number
  sell_price_per_unit: number
  realised_gain_inr: number
}

export interface PaginatedItems<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface LotsResponse {
  open_lots: PaginatedItems<LotEntry>
  matched_sells: PaginatedItems<MatchedSell>
}

export interface PaginatedTransactions {
  items: Transaction[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface AllocationEntry {
  asset_class: string
  value_inr: number
  pct_of_total: number
}

export interface AllocationResponse {
  total_value: number
  allocations: AllocationEntry[]
}

export interface GainerEntry {
  asset_id: number
  name: string
  asset_type: AssetType
  total_invested: number | null
  current_value: number | null
  absolute_return_pct: number | null
  xirr: number | null
}

export interface GainersResponse {
  gainers: GainerEntry[]
  losers: GainerEntry[]
}

export interface ImportantData {
  id: number
  category: 'BANK' | 'MF_FOLIO' | 'IDENTITY' | 'INSURANCE' | 'ACCOUNT' | 'OTHER'
  label: string
  fields: Record<string, string> | null
  notes: string | null
}

// ── Tax types ──────────────────────────────────────────────────────────────

export interface StcgAssetEntry {
  asset_id: number
  asset_name: string
  asset_type: AssetType
  gain: number
  tax_estimate: number
  is_slab: boolean
  tax_rate_pct: number | null
}

export interface LtcgAssetEntry {
  asset_id: number
  asset_name: string
  asset_type: AssetType
  gain: number
  tax_estimate: number
  is_slab: boolean
  tax_rate_pct: number | null
  ltcg_exempt_eligible: boolean
}

export interface InterestAssetEntry {
  asset_id: number
  asset_name: string
  asset_type: AssetType
  interest: number
  tax_estimate: number
}

export interface StcgSection {
  total_gain: number
  total_tax: number
  has_slab_items: boolean
  assets: StcgAssetEntry[]
}

export interface LtcgSection {
  total_gain: number
  total_tax: number
  ltcg_exemption_used: number
  has_slab_items: boolean
  assets: LtcgAssetEntry[]
}

export interface InterestSection {
  total_interest: number
  total_tax: number
  slab_rate_pct: number
  assets: InterestAssetEntry[]
}

export interface TaxSummaryResponse {
  fy: string
  stcg: StcgSection
  ltcg: LtcgSection
  interest: InterestSection
}

export interface UnrealisedLot {
  asset_id: number
  asset_name: string
  asset_type: AssetType
  asset_class: AssetClass
  lot_id: string
  buy_date: string
  units_remaining: number
  buy_price_per_unit: number
  buy_amount_inr: number
  current_value: number | null
  unrealised_gain: number | null
  holding_days: number
  is_short_term: boolean
  near_ltcg_threshold: boolean
}

export interface UnrealisedTotals {
  total_st_unrealised: number
  total_lt_unrealised: number
  total_unrealised: number
  near_threshold_count: number
}

export interface UnrealisedResponse {
  lots: UnrealisedLot[]
  totals: UnrealisedTotals
}

export interface HarvestOpportunity extends UnrealisedLot {
  unrealised_loss: number
}

export interface HarvestResponse {
  opportunities: HarvestOpportunity[]
}
