import client from './client'
import type {
  ApiResponse, AgentInfo, AgentDetailData,
  AgentRulesData, CapabilityData, CustomRule, NewAgentData,
  AgentPanelData, AgentPlugin, AgentMCPServer, AgentSkillItem,
  AgentIntegration, AgentMemoryItem,
} from './types'

export async function fetchAgents(): Promise<AgentInfo[]> {
  const { data } = await client.get<ApiResponse<AgentInfo[]>>('/agents')
  return data.data
}

export async function fetchAgentDetail(agentId: string): Promise<AgentDetailData> {
  const { data } = await client.get<ApiResponse<AgentDetailData>>(`/agents/${agentId}`)
  return data.data
}

/** 获取智能体完整规则内容 */
export async function fetchAgentRules(agentId: string): Promise<AgentRulesData> {
  const { data } = await client.get<ApiResponse<AgentRulesData>>(`/agents/${agentId}/rules`)
  return data.data
}

/** 获取团队能力详情 */
export async function fetchCapabilities(): Promise<CapabilityData[]> {
  const { data } = await client.get<ApiResponse<CapabilityData[]>>('/capabilities')
  return data.data
}

/** 获取自定义规则列表 */
export async function fetchCustomRules(agentId: string): Promise<CustomRule[]> {
  const { data } = await client.get<ApiResponse<CustomRule[]>>(`/agents/${agentId}/custom-rules`)
  return data.data
}

/** 创建自定义规则 */
export async function createCustomRule(agentId: string, content: string, filename?: string): Promise<{ filename: string; path: string }> {
  const { data } = await client.post<ApiResponse<{ filename: string; path: string }>>(`/agents/${agentId}/custom-rules`, { content, filename })
  return data.data
}

/** 更新自定义规则 */
export async function updateCustomRule(agentId: string, filename: string, content: string): Promise<void> {
  await client.put(`/agents/${agentId}/custom-rules/${filename}`, { content })
}

/** 删除自定义规则 */
export async function deleteCustomRule(agentId: string, filename: string): Promise<void> {
  await client.delete(`/agents/${agentId}/custom-rules/${filename}`)
}

/** 创建新智能体 */
export async function createNewAgent(agentData: NewAgentData): Promise<{ agent_id: string; entry_file: string; directory: string }> {
  const { data } = await client.post<ApiResponse<{ agent_id: string; entry_file: string; directory: string }>>('/agents/create', agentData)
  return data.data
}

// ━━━ 面板 API (仿 CodeBuddy) ━━━

/** 获取智能体完整面板数据 */
export async function fetchAgentPanel(agentId: string): Promise<AgentPanelData> {
  const { data } = await client.get<ApiResponse<AgentPanelData>>(`/agents/${agentId}/panel`)
  return data.data
}

/** 插件 - 切换启用/禁用 */
export async function toggleAgentPlugin(agentId: string, pluginId: string, enabled: boolean, config?: Record<string, unknown>): Promise<void> {
  await client.put(`/agents/${agentId}/plugins`, { plugin_id: pluginId, enabled, config: config || {} })
}

/** MCP - 添加服务器 */
export async function addAgentMCP(agentId: string, serverName: string, serverUrl: string, tools?: string[]): Promise<void> {
  await client.post(`/agents/${agentId}/mcp`, { server_name: serverName, server_url: serverUrl, tools: tools || [] })
}

/** MCP - 移除服务器 */
export async function removeAgentMCP(agentId: string, serverName: string): Promise<void> {
  await client.delete(`/agents/${agentId}/mcp/${serverName}`)
}

/** 技能 - 绑定/解绑 */
export async function toggleAgentSkill(agentId: string, skillId: string, enabled: boolean): Promise<void> {
  await client.put(`/agents/${agentId}/skills`, { skill_id: skillId, enabled })
}

/** 集成 - 启用/禁用 */
export async function toggleAgentIntegration(agentId: string, integrationId: string, enabled: boolean): Promise<void> {
  await client.put(`/agents/${agentId}/integrations`, { integration_id: integrationId, enabled })
}

/** 记忆 - 添加 */
export async function addAgentMemory(agentId: string, title: string, content: string, memoryType?: string): Promise<void> {
  await client.post(`/agents/${agentId}/memory`, { title, content, memory_type: memoryType || 'knowledge' })
}

/** 记忆 - 删除 */
export async function deleteAgentMemory(agentId: string, memoryId: string): Promise<void> {
  await client.delete(`/agents/${agentId}/memory/${memoryId}`)
}
