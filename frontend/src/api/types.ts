// ━━━ 通用 API 响应 ━━━
export interface ApiResponse<T = unknown> {
  success: boolean
  message: string
  data: T
  timestamp: string
}

// ━━━ 概览数据 ━━━
export interface OverviewData {
  system: {
    name: string
    version: string
    status: string
    uptime: string
  }
  agents: {
    total: number
    active: number
    parallel_groups: number
  }
  pipelines: {
    active: number
    types: number
    quality_gates: number
  }
  inventory: Record<string, number>
  message_queue: Record<string, unknown>
}

// ━━━ Agent ━━━
export interface AgentModelStatus {
  status: 'online' | 'busy' | 'offline'
  enabled: boolean
  has_api_key: boolean
  has_model: boolean
  provider: string
  model: string
  is_registered: boolean
}

export interface AgentInfo {
  id: string
  key: string
  name: string
  persona: string
  icon: string
  role: string
  parallel_group: string
  has_sandbox: boolean
  sandbox_active: boolean
  context: Record<string, unknown> | null
  model_status?: AgentModelStatus
}

export interface AgentDetailData {
  agent_id: string
  spec: Record<string, unknown> | null
  sandbox: {
    path: string
    dirs: string[]
  } | null
  context: Record<string, unknown> | null
  operation_logs: Array<Record<string, unknown>>
}

// ━━━ 流水线 ━━━
export interface PipelineStep {
  stage: string
  name: string
  agent_id: string
  execution: string
  parallel_with: string[]
  quality_gate: string | null
  optional: boolean
  status: string  // pending / running / completed / failed / skipped
}

export interface PipelineInstance {
  pipeline_id: string
  req_id: string
  req_type: string
  req_scale: string
  req_name: string
  current_stage: string
  current_step_index: number
  status: string
  bug_rounds: number
  progress_pct: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  steps: PipelineStep[]
  stages: PipelineStep[]
  execution_status?: {
    status: string
    started_at?: string
    completed_at?: string
    progress?: number
    error?: string
  }
}

export interface PipelineDefinitions {
  definitions: Record<string, {
    name: string
    stages: Array<{ name: string; agent_id: string }>
  }>
  quality_gates: Record<string, {
    name: string
    from_stage: string
    to_stage: string
    check_items: string[]
  }>
}

// ━━━ 消息 ━━━
export interface MessageStats {
  channels: Record<string, { count: number; status: string }>
  total_messages: number
}

export interface MessageItem {
  msg_id: string
  from_agent: string
  to_agent: string
  msg_type: string
  priority: string
  payload: Record<string, unknown>
  timestamp: string
}

// ━━━ 沙盒 ━━━
export interface SandboxInfo {
  agent_id: string
  path: string
  status: string
  dirs?: string[]
}

// ━━━ 规则资产 ━━━
export interface InventoryData {
  statistics: Record<string, number>
  agents: Record<string, {
    steps: string[]
    templates: string[]
  }>
  skills: Record<string, {
    skill_name: string
    category: string
    title: string
  }>
  rules: string[]
}

// ━━━ 日志 ━━━
export interface LogEntry {
  timestamp: string
  event_type: string
  message: string
  level?: string
}

// ━━━ 团队 ━━━
export interface TeamStatus {
  team_name: string
  member_count: number
  members: Record<string, {
    name: string
    role: string
    group: string
    mode: string
    has_agent_file: boolean
  }>
}

// ━━━ 智能体模型配置 ━━━
export interface AgentModelConfig {
  agent_id: string
  agent_name: string
  provider: string
  model: string
  api_key_masked: string
  base_url: string
  temperature: number
  max_tokens: number
  enabled: boolean
  extra_params: Record<string, unknown>
}

export interface ModelProviderInfo {
  name: string
  base_url: string
  models: Array<{
    id: string
    name: string
    context_window: number
  }>
}

export type ModelProviders = Record<string, ModelProviderInfo>

// ━━━ Workspace 工作空间类型 ━━━

/** 工作空间消息类型 */
export type WorkspaceMessageType =
  | 'agent'          // Agent 工作消息
  | 'user'           // 用户输入
  | 'decision'       // 决策门禁
  | 'deliverable'    // 阶段交付物
  | 'system'         // 系统通知

/** 交付物类型 */
export type DeliverableType = 'code' | 'document' | 'design' | 'test' | 'config'

/** Agent 思考过程 */
export interface ThinkingStep {
  id: string
  content: string
  timestamp: string
}

/** 阶段交付物 */
export interface Deliverable {
  id: string
  type: DeliverableType
  title: string
  summary: string
  files?: string[]
  preview?: string
}

/** 决策门禁 */
export interface DecisionGateData {
  id: string
  stage: string
  agent_id: string
  title: string
  description: string
  options: Array<{ key: string; label: string; icon: string }>
  status: 'pending' | 'approved' | 'rejected'
  user_response?: string
  responded_at?: string
}

/** 工作空间消息 */
export interface WorkspaceMessage {
  id: string
  type: WorkspaceMessageType
  agent_id?: string
  content: string
  thinking?: ThinkingStep[]
  deliverable?: Deliverable
  decision?: DecisionGateData
  timestamp: string
  status?: 'streaming' | 'complete' | 'error'
}

/** 文件节点（文件树） */
export interface FileNode {
  name: string
  path: string
  type: 'file' | 'directory'
  children?: FileNode[]
  size?: number
  language?: string
}

/** 右侧工具面板 Tab */
export type ToolTabId = 'viewer' | 'overview' | 'editor' | 'files' | 'activity'

/** 上传文件信息 */
export interface UploadFileInfo {
  name: string
  type: string
  size: number
  status: 'uploading' | 'done' | 'error'
  progress: number
}

// ━━━ 智能体规则详情 ━━━
export interface AgentRuleStep {
  path: string
  name: string
  content: string
}

export interface AgentRulesData {
  agent_id: string
  agent_name: string
  title: string
  entry_content: string
  steps: AgentRuleStep[]
  templates: AgentRuleStep[]
  file_count: number
  directory: string
}

// ━━━ 团队能力 ━━━
export interface CapabilityData {
  id: string
  icon: string
  title: string
  description: string
  detail: string
  data: unknown
}

// ━━━ 自定义规则 ━━━
export interface CustomRule {
  filename: string
  title: string
  content: string
  size: number
  modified: string
}

// ━━━ 新智能体 ━━━
export interface NewAgentData {
  agent_name: string
  agent_icon: string
  role: string
  persona: string
  group: string
  entry_content: string
  sandbox?: boolean
}

// ━━━ 智能体面板 (仿 CodeBuddy) ━━━

export interface AgentPlugin {
  id: string
  name: string
  icon: string
  desc: string
  category: string
  tags: string[]
  enabled?: boolean
  config?: Record<string, unknown>
}

export interface AgentMCPServer {
  server_name: string
  server_url: string
  enabled: boolean
  tools: string[]
  added_at?: string
}

export interface AgentIntegration {
  id: string
  name: string
  icon: string
  desc: string
  status: string
  enabled?: boolean
  config?: Record<string, unknown>
}

export interface AgentSkillItem {
  skill_id: string
  skill_name: string
  category: string
  file_path: string
  title: string
  description: string
  bound: boolean
  enabled?: boolean
  content_preview?: string
}

export interface AgentMemoryItem {
  id: string
  title: string
  content: string
  memory_type: string
  created_at: string
}

export interface AgentPanelData {
  config: {
    agent_id: string
    plugins: Array<{ plugin_id: string; enabled: boolean; config: Record<string, unknown> }>
    mcp_servers: AgentMCPServer[]
    integrations: Array<{ integration_id: string; enabled: boolean; config: Record<string, unknown> }>
    skills: Array<{ skill_id: string; enabled: boolean }>
    memory: AgentMemoryItem[]
  }
  rules: AgentRulesData
  custom_rules: CustomRule[]
  available_skills: AgentSkillItem[]
  available_plugins: AgentPlugin[]
  available_integrations: AgentIntegration[]
}
