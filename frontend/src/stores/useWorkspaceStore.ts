import { create } from 'zustand'
import type { WorkspaceMessage, FileNode, ToolTabId, DecisionGateData } from '@/api/types'

interface WorkspaceStore {
  // ━━━ 面板状态 ━━━
  activeToolTab: ToolTabId
  setActiveToolTab: (tab: ToolTabId) => void
  toolPanelOpen: boolean
  toggleToolPanel: () => void
  setToolPanelOpen: (open: boolean) => void

  // ━━━ 过程消息流 ━━━
  messages: WorkspaceMessage[]
  addMessage: (msg: WorkspaceMessage) => void
  setMessages: (msgs: WorkspaceMessage[]) => void
  updateMessage: (id: string, partial: Partial<WorkspaceMessage>) => void

  // ━━━ 决策门禁 ━━━
  pendingDecision: DecisionGateData | null
  setPendingDecision: (d: DecisionGateData | null) => void

  // ━━━ 编辑器状态 ━━━
  activeFile: string | null
  setActiveFile: (path: string | null) => void
  openFiles: string[]
  openFile: (path: string) => void
  closeFile: (path: string) => void

  // ━━━ 文件树 ━━━
  fileTree: FileNode[]
  setFileTree: (tree: FileNode[]) => void
  expandedDirs: string[]
  toggleDir: (path: string) => void

  // ━━━ 输入状态 ━━━
  inputText: string
  setInputText: (text: string) => void
  isUploading: boolean
  setIsUploading: (v: boolean) => void

  // ━━━ 重置 ━━━
  reset: () => void
}

const initialState = {
  activeToolTab: 'overview' as ToolTabId,
  toolPanelOpen: true,
  messages: [] as WorkspaceMessage[],
  pendingDecision: null as DecisionGateData | null,
  activeFile: null as string | null,
  openFiles: [] as string[],
  fileTree: [] as FileNode[],
  expandedDirs: [] as string[],
  inputText: '',
  isUploading: false,
}

export const useWorkspaceStore = create<WorkspaceStore>((set) => ({
  ...initialState,

  setActiveToolTab: (tab) => set({ activeToolTab: tab }),
  toggleToolPanel: () => set((s) => ({ toolPanelOpen: !s.toolPanelOpen })),
  setToolPanelOpen: (open) => set({ toolPanelOpen: open }),

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setMessages: (msgs) => set({ messages: msgs }),
  updateMessage: (id, partial) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, ...partial } : m)),
    })),

  setPendingDecision: (d) => set({ pendingDecision: d }),

  setActiveFile: (path) => set({ activeFile: path }),
  openFile: (path) =>
    set((s) => ({
      activeFile: path,
      openFiles: s.openFiles.includes(path) ? s.openFiles : [...s.openFiles, path],
    })),
  closeFile: (path) =>
    set((s) => {
      const newOpen = s.openFiles.filter((f) => f !== path)
      return {
        openFiles: newOpen,
        activeFile: s.activeFile === path ? (newOpen[newOpen.length - 1] || null) : s.activeFile,
      }
    }),

  setFileTree: (tree) => set({ fileTree: tree }),
  toggleDir: (path) =>
    set((s) => ({
      expandedDirs: s.expandedDirs.includes(path)
        ? s.expandedDirs.filter((d) => d !== path)
        : [...s.expandedDirs, path],
    })),

  setInputText: (text) => set({ inputText: text }),
  setIsUploading: (v) => set({ isUploading: v }),

  reset: () => set(initialState),
}))
