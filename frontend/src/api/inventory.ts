import client from './client'
import type { ApiResponse, InventoryData } from './types'

export async function fetchInventory(): Promise<InventoryData> {
  const { data } = await client.get<ApiResponse<InventoryData>>('/inventory')
  return data.data
}

export async function rescanInventory(): Promise<{
  statistics: Record<string, number>
  issues: string[]
}> {
  const { data } = await client.post<ApiResponse<{
    statistics: Record<string, number>
    issues: string[]
  }>>('/inventory/rescan')
  return data.data
}
