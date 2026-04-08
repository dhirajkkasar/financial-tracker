import { AssetType, AssetClass } from '@/types'

export interface Member {
  id: number
  pan: string
  name: string
  is_default: boolean
  created_at: string
}

export const ASSET_TYPE_TO_CLASS: Record<AssetType, AssetClass> = {
  STOCK_IN: 'EQUITY',
  STOCK_US: 'EQUITY',
  RSU: 'EQUITY',
  MF: 'EQUITY',
  NPS: 'DEBT',
  FD: 'DEBT',
  RD: 'DEBT',
  PPF: 'DEBT',
  EPF: 'DEBT',
  GOLD: 'GOLD',
  SGB: 'GOLD',
  REAL_ESTATE: 'REAL_ESTATE',
}

export const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  STOCK_IN: 'Indian Stocks',
  STOCK_US: 'US Stocks',
  MF: 'Mutual Funds',
  FD: 'Fixed Deposit',
  RD: 'Recurring Deposit',
  PPF: 'PPF',
  EPF: 'EPF',
  NPS: 'NPS',
  GOLD: 'Gold',
  SGB: 'Sovereign Gold Bond',
  REAL_ESTATE: 'Real Estate',
  RSU: 'RSU',
}

export const ASSET_CLASS_COLORS: Record<AssetClass, string> = {
  EQUITY: '#6366f1',
  DEBT: '#22c55e',
  GOLD: '#f59e0b',
  REAL_ESTATE: '#ec4899',
  MIXED: '#8b5cf6',
}

export const ASSET_TYPE_COLORS: Record<AssetType, string> = {
  STOCK_IN: '#6366f1',
  STOCK_US: '#818cf8',
  MF: '#8b5cf6',
  FD: '#22c55e',
  RD: '#4ade80',
  PPF: '#14b8a6',
  EPF: '#06b6d4',
  NPS: '#0ea5e9',
  GOLD: '#f59e0b',
  SGB: '#fbbf24',
  REAL_ESTATE: '#ec4899',
  RSU: '#f97316',
}

export const XIRR_THRESHOLDS = { good: 0.12, average: 0.08 }

export const NAV_TABS = [
  { label: 'Overview', href: '/' },
  { label: 'Stocks', href: '/stocks' },
  { label: 'Mutual Funds', href: '/mutual-funds' },
  { label: 'Deposits', href: '/deposits' },
  { label: 'PPF', href: '/ppf' },
  { label: 'EPF', href: '/epf' },
  { label: 'NPS', href: '/nps' },
  { label: 'US Stocks', href: '/us-stocks' },
  { label: 'Gold', href: '/gold' },
  { label: 'Real Estate', href: '/real-estate' },
  { label: 'Goals', href: '/goals' },
  { label: 'Tax', href: '/tax' },
  { label: 'Personal Info', href: '/personal-info' },
] as const
