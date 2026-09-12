import { create } from 'zustand'
import type { AgentInfo, AgentDetailData, AgentRulesData, CapabilityData, CustomRule, AgentPanelData } from '../api/types'
import { fetchAgents, fetchAgentDetail, fetchAgentRules, fetchCapabilities, fetchCustomRules, fetchAgentPanel } from '../api/agents'

interface AgentStore {
  agents: AgentInfo[]
  loading: boolean
  error: string | null
  selectedDetail: AgentDetailData | null
  detailLoading: boolean

  // 规则数据
  agentRules: AgentRulesData | null
  rulesLoading: boolean

  // 团队能力
  capabilities: CapabilityData[]
  capabilitiesLoading: boolean

  // 自定义规则
  customRules: CustomRule[]
  customRulesLoading: boolean

  // 面板数据 (CodeBuddy-style)
  panelData: AgentPanelData | null
  panelLoading: boolean

  // Actions
  fetch: () => Promise<void>
  fetchDetail: (id: string) => Promise<void>
  fetchRules: (id: string) => Promise<void>
  fetchCaps: () => Promise<void>
  fetchCustom: (id: string) => Promise<void>
  fetchPanel: (id: string) => Promise<void>
  clearRules: () => void
  clearPanel: () => void
}

export const useAgentStore = create<AgentStore>((set) => ({
  agents: [],
  loading: false,
  error: null,
  selectedDetail: null,
  detailLoading: false,

  agentRules: null,
  rulesLoading: false,

  capabilities: [],
  capabilitiesLoading: false,

  customRules: [],
  customRulesLoading: false,

  panelData: null,
  panelLoading: false,

  fetch: async () => {
    set({ loading: true, error: null })
    try {
      const agents = await fetchAgents()
      set({ agents, loading: false })
    } catch (e) {
      set({ error: (e as Error).message, loading: false })
    }
  },

  fetchDetail: async (id: string) => {
    set({ detailLoading: true })
    try {
      const detail = await fetchAgentDetail(id)
      set({ selectedDetail: detail, detailLoading: false })
    } catch (e) {
      set({ detailLoading: false, error: (e as Error).message })
    }
  },

  fetchRules: async (id: string) => {
    set({ rulesLoading: true })
    try {
      const rules = await fetchAgentRules(id)
      set({ agentRules: rules, rulesLoading: false })
    } catch (e) {
      set({ rulesLoading: false, error: (e as Error).message })
    }
  },

  fetchCaps: async () => {
    set({ capabilitiesLoading: true })
    try {
      const caps = await fetchCapabilities()
      set({ capabilities: caps, capabilitiesLoading: false })
    } catch (e) {
      set({ capabilitiesLoading: false, error: (e as Error).message })
    }
  },

  fetchCustom: async (id: string) => {
    set({ customRulesLoading: true })
    try {
      const rules = await fetchCustomRules(id)
      set({ customRules: rules, customRulesLoading: false })
    } catch (e) {
      set({ customRulesLoading: false, error: (e as Error).message })
    }
  },

  fetchPanel: async (id: string) => {
    set({ panelLoading: true, error: null })
    try {
      const data = await fetchAgentPanel(id)
      set({ panelData: data, panelLoading: false })
    } catch (e) {
      set({ panelLoading: false, error: (e as Error).message })
    }
  },

  clearRules: () => set({ agentRules: null, customRules: [] }),
  clearPanel: () => set({ panelData: null }),
}))
