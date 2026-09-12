import client from './client'
import type { ApiResponse, SandboxInfo } from './types'

export async function fetchSandboxes(): Promise<SandboxInfo[]> {
  const { data } = await client.get<ApiResponse<SandboxInfo[]>>('/sandboxes')
  return data.data
}

export async function fetchSandboxLogs(agentId: string): Promise<Array<Record<string, unknown>>> {
  const { data } = await client.get<ApiResponse<Array<Record<string, unknown>>>>(`/sandboxes/${agentId}/logs`)
  return data.data
}

export async function checkAccess(agentId: string, filePath: string, operation: string): Promise<{
  allowed: boolean
  reason: string
}> {
  const { data } = await client.post<ApiResponse<{ allowed: boolean; reason: string }>>(
    `/sandboxes/check-access?agent_id=${agentId}&file_path=${filePath}&operation=${operation}`
  )
  return data.data
}
