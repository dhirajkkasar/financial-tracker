import axios from 'axios'
import { Asset, AssetType, Transaction, Valuation, FDDetail, Goal, GoalAllocation, ReturnResult, OverviewReturns, BreakdownResponse, LotsResponse, PaginatedTransactions, AllocationResponse, GainersResponse, ImportantData, BulkReturnResponse, TaxSummaryResponse, UnrealisedResponse, HarvestResponse } from '@/types'

const client = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
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
  assets: {
    list: (params?: { type?: AssetType; active?: boolean }) =>
      client.get<Asset[]>('/assets', { params }).then((r) => r.data),
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
    overview: (types?: AssetType[]) =>
      client.get<OverviewReturns>('/returns/overview', {
        params: types?.length ? { types: types.join(',') } : {},
      }).then((r) => r.data),
    breakdown: () =>
      client.get<BreakdownResponse>('/returns/breakdown').then((r) => r.data),
    lots: (assetId: number, openPage = 1, matchedPage = 1, pageSize = 10) =>
      client.get<LotsResponse>(`/assets/${assetId}/returns/lots`, {
        params: { open_page: openPage, matched_page: matchedPage, page_size: pageSize },
      }).then((r) => r.data),
    bulk: (assetIds: number[]) =>
      client.get<BulkReturnResponse>('/returns/bulk', { params: { asset_ids: assetIds.join(',') } }).then((r) => r.data),
    allocation: () =>
      client.get<AllocationResponse>('/overview/allocation').then((r) => r.data),
    gainers: (n = 5) =>
      client.get<GainersResponse>('/overview/gainers', { params: { n } }).then((r) => r.data),
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
    summary: (fy: string) =>
      client.get<TaxSummaryResponse>('/tax/summary', { params: { fy } }).then((r) => r.data),
    unrealised: () =>
      client.get<UnrealisedResponse>('/tax/unrealised').then((r) => r.data),
    harvestOpportunities: () =>
      client.get<HarvestResponse>('/tax/harvest-opportunities').then((r) => r.data),
  },
}
