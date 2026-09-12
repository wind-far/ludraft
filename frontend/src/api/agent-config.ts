import client from './client'
import type { ApiResponse, AgentModelConfig, ModelProviders } from './types'

/** 获取所有智能体模型配置 */
export async function fetchAgentConfigs(): Promise<AgentModelConfig[]> {
  const { data } = await client.get<ApiResponse<AgentModelConfig[]>>('/agent-configs')
  return data.data
}

/** 获取单个智能体配置 */
export async function fetchAgentConfig(agentId: string): Promise<AgentModelConfig> {
  const { data } = await client.get<ApiResponse<AgentModelConfig>>(`/agent-configs/${agentId}`)
  return data.data
}

/** 更新智能体模型配置 */
export async function updateAgentConfig(
  agentId: string,
  updates: Partial<{
    provider: string
    model: string
    api_key: string
    base_url: string
    temperature: number
    max_tokens: number
    enabled: boolean
  }>
): Promise<AgentModelConfig> {
  const { data } = await client.put<ApiResponse<AgentModelConfig>>(
    `/agent-configs/${agentId}`,
    updates
  )
  return data.data
}

/** 获取所有可用的模型提供商 */
export async function fetchModelProviders(): Promise<ModelProviders> {
  const { data } = await client.get<ApiResponse<ModelProviders>>('/model-providers')
  return data.data
}
