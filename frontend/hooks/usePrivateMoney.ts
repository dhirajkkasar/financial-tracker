import { usePrivateMode } from '@/context/PrivateModeContext'
import { formatINR as _formatINR, formatINR2 as _formatINR2 } from '@/lib/formatters'

const MASK = '*****'

export function usePrivateMoney() {
  const { isPrivate } = usePrivateMode()
  return {
    formatINR: isPrivate ? (_: number) => MASK : _formatINR,
    formatINR2: isPrivate ? (_: number) => MASK : _formatINR2,
  }
}
