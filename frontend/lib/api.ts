import axios from 'axios'
import { Asset, AssetType, Transaction, Valuation, FDDetail, Goal, GoalAllocation, ReturnResult, OverviewReturns, BreakdownResponse, LotsResponse, PaginatedTransactions, AllocationResponse, GainersResponse, ImportantData, BulkReturnResponse, TaxSummaryResponse, UnrealisedResponse, HarvestResponse, PortfolioSnapshot } from '@/types'
import { Member } from '@/constants'

const client = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Normalize errors
client.interceptors.response.use(
  (res) => res,
  (err) => {
    const message = err.response?.data?.error?.message || err.message
    return Promise.reject(new Error(message))
  }
)

export const api = {
  members: {
    list: (): Promise<Member[]> => client.get('/members').then((r) => r.data),
    create: (data: { pan: string; name: string }): Promise<Member> => client.post('/members', data).then((r) => r.data),
  },
  assets: {
    list: (params?: { type?: AssetType; active?: boolean; member_ids?: number[] }) => {
      const p: Record<string, string> = {}
      if (params?.type) p.type = params.type
      if (params?.active !== undefined) p.active = String(params.active)
      if (params?.member_ids?.length) p.member_ids = params.member_ids.join(',')
      return client.get<Asset[]>('/assets', { params: p }).then((r) => r.data)
    },
    get: (id: number) =>
      client.get<Asset>(`/assets/${id}`).then((r) => r.data),
    create: (data: Partial<Asset>) =>
      client.post<Asset>('/assets', data).then((r) => r.data),
    update: (id: number, data: Partial<Asset>) =>
      client.put<Asset>(`/assets/${id}`, data).then((r) => r.data),
    delete: (id: number) =>
      client.delete(`/assets/${id}`).then((r) => r.data),
  },
  transactions: {
    list: (assetId: number, page = 1, pageSize = 10) =>
      client.get<PaginatedTransactions>(`/assets/${assetId}/transactions`, {
        params: { page, page_size: pageSize },
      }).then((r) => r.data),
    create: (assetId: number, data: Partial<Transaction>) =>
      client.post<Transaction>(`/assets/${assetId}/transactions`, data).then((r) => r.data),
    delete: (assetId: number, txnId: number) =>
      client.delete(`/assets/${assetId}/transactions/${txnId}`).then((r) => r.data),
  },
  valuations: {
    list: (assetId: number) =>
      client.get<Valuation[]>(`/assets/${assetId}/valuations`).then((r) => r.data),
  },
  fdDetail: {
    get: (assetId: number) =>
      client.get<FDDetail>(`/assets/${assetId}/fd-detail`).then((r) => r.data),
  },
  returns: {
    asset: (assetId: number) =>
      client.get<ReturnResult>(`/assets/${assetId}/returns`).then((r) => r.data),
    overview: (types?: AssetType[], memberIds?: number[]) => {
      const params: Record<string, string> = {}
      if (types?.length) params.types = types.join(',')
      if (memberIds?.length) params.member_ids = memberIds.join(',')
      return client.get<OverviewReturns>('/returns/overview', { params }).then((r) => r.data)
    },
    breakdown: (memberIds?: number[]) =>
      client.get<BreakdownResponse>('/returns/breakdown', {
        params: memberIds?.length ? { member_ids: memberIds.join(',') } : {},
      }).then((r) => r.data),
    lots: (assetId: number, openPage = 1, matchedPage = 1, pageSize = 10) =>
      client.get<LotsResponse>(`/assets/${assetId}/returns/lots`, {
        params: { open_page: openPage, matched_page: matchedPage, page_size: pageSize },
      }).then((r) => r.data),
    bulk: (assetIds: number[]) =>
      client.get<BulkReturnResponse>('/returns/bulk', { params: { asset_ids: assetIds.join(',') } }).then((r) => r.data),
    allocation: (memberIds?: number[]) =>
      client.get<AllocationResponse>('/overview/allocation', {
        params: memberIds?.length ? { member_ids: memberIds.join(',') } : {},
      }).then((r) => r.data),
    gainers: (n = 5, memberIds?: number[]) =>
      client.get<GainersResponse>('/overview/gainers', {
        params: memberIds?.length ? { n, member_ids: memberIds.join(',') } : { n },
      }).then((r) => r.data),
  },
  goals: {
    list: () => client.get<Goal[]>('/goals').then((r) => r.data),
    get: (id: number) => client.get<Goal>(`/goals/${id}`).then((r) => r.data),
    allocations: (goalId: number) =>
      client.get<GoalAllocation[]>(`/goals/${goalId}/allocations`).then((r) => r.data),
  },
  importantData: {
    list: (category?: string) =>
      client.get<ImportantData[]>('/important-data', { params: category ? { category } : {} }).then((r) => r.data),
  },
  tax: {
    fiscalYears: () =>
      client.get<{ fiscal_years: string[] }>('/tax/fiscal-years').then((r) => r.data),
    summary: (fy: string, memberId: number) =>
      client.get<TaxSummaryResponse>('/tax/summary', { params: { fy, member_id: memberId } }).then((r) => r.data),
    unrealised: (memberId: number) =>
      client.get<UnrealisedResponse>('/tax/unrealised', { params: { member_id: memberId } }).then((r) => r.data),
    harvestOpportunities: (memberId: number) =>
      client.get<HarvestResponse>('/tax/harvest-opportunities', { params: { member_id: memberId } }).then((r) => r.data),
  },
  snapshots: {
    list: (from?: string, to?: string, memberIds?: number[]) =>
      client.get<PortfolioSnapshot[]>('/snapshots', {
        params: { from, to, ...(memberIds?.length ? { member_ids: memberIds.join(',') } : {}) },
      }).then((r) => r.data),
    take: () =>
      client.post<{ date: string; total_value_inr: number }>('/snapshots').then((r) => r.data),
  },
}
