import client from './client'
import type { ApiResponse, MessageStats, MessageItem } from './types'

export async function fetchMessageStats(): Promise<MessageStats> {
  const { data } = await client.get<ApiResponse<MessageStats>>('/messages/stats')
  return data.data
}

export async function fetchAgentMessages(agentId: string, limit = 20): Promise<MessageItem[]> {
  const { data } = await client.get<ApiResponse<MessageItem[]>>(`/messages/${agentId}?limit=${limit}`)
  return data.data
}

export async function sendMessage(params: {
  from_agent: string
  to_agent: string
  msg_type?: string
  payload?: Record<string, unknown>
}): Promise<{ msg_id: string }> {
  const { data } = await client.post<ApiResponse<{ msg_id: string }>>('/messages/send', params)
  return data.data
}
