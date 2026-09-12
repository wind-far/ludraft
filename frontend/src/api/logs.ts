import client from './client'
import type { ApiResponse, LogEntry } from './types'

export async function fetchLogs(count = 50): Promise<LogEntry[]> {
  const { data } = await client.get<ApiResponse<LogEntry[]>>(`/logs?count=${count}`)
  return data.data
}

export async function fetchPipelineLogs(pipelineId: string, count = 50): Promise<LogEntry[]> {
  const { data } = await client.get<ApiResponse<LogEntry[]>>(`/pipelines/${pipelineId}/logs?count=${count}`)
  return data.data
}
