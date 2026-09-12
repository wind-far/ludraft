import client from './client'
import type { ApiResponse, OverviewData } from './types'

export async function fetchOverview(): Promise<OverviewData> {
  const { data } = await client.get<ApiResponse<OverviewData>>('/overview')
  return data.data
}
