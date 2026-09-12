import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useAgentStore } from '@/stores/useAgentStore'
import Badge from '@/components/ui/Badge'
import Avatar from '@/components/ui/Avatar'
import { GROUP_COLORS } from '@/utils/constants'
import type { AgentRuleStep, CustomRule, AgentPlugin, AgentMCPServer, AgentSkillItem, AgentIntegration, AgentMemoryItem } from '@/api/types'
import {
  toggleAgentPlugin, addAgentMCP, removeAgentMCP,
  toggleAgentSkill, toggleAgentIntegration,
  addAgentMemory, deleteAgentMemory,
} from '@/api/agents'
import clsx from 'clsx'

const AVATAR_COLORS = ['blue', 'green', 'purple', 'orange', 'cyan', 'pink', 'indigo', 'blue'] as const

type TabId = 'overview' | 'steps' | 'templates' | 'custom' | 'plugins' | 'mcp' | 'skills' | 'integrations' | 'memory'

/* ═══════════════════════════════════════════════════════
   主组件
   ═══════════════════════════════════════════════════════ */
export default function AgentDetail() {
  const { agentId } = useParams<{ agentId: string }>()
  const navigate = useNavigate()
  const {
    agents, agentRules, rulesLoading, customRules, customRulesLoading,
    panelData, panelLoading,
    fetch: fetchAgents, fetchRules, fetchCustom, fetchPanel,
    clearRules, clearPanel,
  } = useAgentStore()

  const [activeTab, setActiveTab] = useState<TabId>('overview')
  const [expandedStep, setExpandedStep] = useState<string | null>(null)
  const [showEditor, setShowEditor] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [editFilename, setEditFilename] = useState('')
  const [editMode, setEditMode] = useState<'create' | 'edit'>('create')
  const [saving, setSaving] = useState(false)

  const agentInfo = agents.find(a => a.id === agentId)
  usePageTitle(agentInfo?.name || '智能体详情')

  useEffect(() => {
    if (agents.length === 0) fetchAgents()
    if (agentId) {
      fetchRules(agentId)
      fetchCustom(agentId)
      fetchPanel(agentId)
    }
    return () => { clearRules(); clearPanel() }
  }, [agentId, agents.length, fetchAgents, fetchRules, fetchCustom, fetchPanel, clearRules, clearPanel])

  const colorIdx = agents.indexOf(agentInfo!)
  const avatarColor = AVATAR_COLORS[colorIdx >= 0 ? colorIdx % AVATAR_COLORS.length : 0]

  const STATUS_MAP: Record<string, { label: string; color: string; bg: string }> = {
    online:  { label: '在线就绪', color: 'text-emerald-700', bg: 'bg-emerald-50' },
    busy:    { label: '配置不完整', color: 'text-amber-700', bg: 'bg-amber-50' },
    offline: { label: '未配置', color: 'text-gray-500', bg: 'bg-gray-100' },
  }
  const status = agentInfo?.model_status?.status || 'offline'
  const statusInfo = STATUS_MAP[status] || STATUS_MAP.offline

  const TABS: { id: TabId; label: string; icon: string; count?: number }[] = [
    { id: 'overview', label: '总览', icon: '📋' },
    { id: 'steps', label: '工作步骤', icon: '🔄', count: agentRules?.steps.length },
    { id: 'templates', label: '模板文件', icon: '📝', count: agentRules?.templates.length },
    { id: 'custom', label: '自定义规则', icon: '✨', count: customRules.length },
    { id: 'plugins', label: '插件', icon: '🔌', count: panelData?.config?.plugins?.filter(p => p.enabled).length },
    { id: 'mcp', label: 'MCP', icon: '🔗', count: panelData?.config?.mcp_servers?.length },
    { id: 'skills', label: '技能', icon: '🧠', count: panelData?.config?.skills?.filter(s => s.enabled).length },
    { id: 'integrations', label: '集成', icon: '🛠️', count: panelData?.config?.integrations?.filter(i => i.enabled).length },
    { id: 'memory', label: '记忆', icon: '💾', count: panelData?.config?.memory?.length },
  ]

  // 保存自定义规则
  const handleSaveRule = async () => {
    if (!agentId || !editContent.trim()) return
    setSaving(true)
    try {
      if (editMode === 'create') {
        const { createCustomRule } = await import('@/api/agents')
        await createCustomRule(agentId, editContent, editFilename || undefined)
      } else {
        const { updateCustomRule } = await import('@/api/agents')
        await updateCustomRule(agentId, editFilename, editContent)
      }
      await fetchCustom(agentId)
      setShowEditor(false); setEditContent(''); setEditFilename('')
    } catch (e) { console.error('保存失败:', e) }
    finally { setSaving(false) }
  }

  const handleDeleteRule = async (filename: string) => {
    if (!agentId || !confirm(`确定删除 ${filename}？`)) return
    try {
      const { deleteCustomRule } = await import('@/api/agents')
      await deleteCustomRule(agentId, filename)
      await fetchCustom(agentId)
    } catch (e) { console.error('删除失败:', e) }
  }

  const handleRefreshPanel = useCallback(() => {
    if (agentId) {
      fetchPanel(agentId)
      fetchRules(agentId)
      fetchCustom(agentId)
    }
  }, [agentId, fetchPanel, fetchRules, fetchCustom])

  return (
    <div className="space-y-6">
      {/* 返回按钮 + Header */}
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/team')} className="flex h-9 w-9 items-center justify-center rounded-xl border border-gray-200 text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-all">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" /></svg>
        </button>
        <span className="text-[13px] text-gray-400">AI 团队</span>
        <svg className="h-3 w-3 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" /></svg>
        <span className="text-[13px] font-medium text-gray-700">{agentInfo?.name || agentId}</span>
      </div>

      {/* Agent Profile Card */}
      <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-card">
        <div className="flex items-start gap-5">
          <Avatar icon={<span className="text-3xl">{agentInfo?.icon || '🤖'}</span>} size="xl" color={avatarColor} status={status as 'online' | 'busy' | 'offline'} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-[22px] font-bold text-gray-900">{agentInfo?.name || agentId}</h1>
              {agentInfo && <Badge color={GROUP_COLORS[agentInfo.parallel_group] as any} size="sm">{agentInfo.role}</Badge>}
              <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${statusInfo.bg} ${statusInfo.color}`}>{statusInfo.label}</span>
            </div>
            <p className="mt-2 text-[14px] leading-relaxed text-gray-500">{agentInfo?.persona || '暂无描述'}</p>
            {agentInfo?.model_status && (
              <div className="mt-4 flex flex-wrap gap-4 text-[12px] text-gray-400">
                <span><span className="text-gray-500">模型:</span> <span className="font-medium text-gray-700">{agentInfo.model_status.provider ? `${agentInfo.model_status.provider}/${agentInfo.model_status.model}` : '未配置'}</span></span>
                <span><span className="text-gray-500">沙盒:</span> <span className={agentInfo.has_sandbox ? 'text-emerald-600' : 'text-gray-400'}>{agentInfo.has_sandbox ? '已启用' : '未启用'}</span></span>
                <span><span className="text-gray-500">文件数:</span> <span className="font-medium text-gray-700">{agentRules?.file_count || '-'}</span></span>
                <span><span className="text-gray-500">插件:</span> <span className="font-medium text-gray-700">{panelData?.config?.plugins?.filter(p => p.enabled).length || 0}</span></span>
                <span><span className="text-gray-500">MCP:</span> <span className="font-medium text-gray-700">{panelData?.config?.mcp_servers?.length || 0}</span></span>
                <span><span className="text-gray-500">技能:</span> <span className="font-medium text-gray-700">{panelData?.config?.skills?.filter(s => s.enabled).length || 0}</span></span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button onClick={handleRefreshPanel} className="rounded-xl border border-gray-200 px-3 py-2 text-[12px] font-medium text-gray-600 hover:bg-gray-50 transition-all">🔄 刷新</button>
            <button onClick={() => navigate('/agent-config')} className="rounded-xl border border-gray-200 px-3 py-2 text-[12px] font-medium text-gray-600 hover:bg-gray-50 transition-all">⚙️ 模型配置</button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-100 overflow-x-auto">
        <div className="flex gap-0 min-w-max">
          {TABS.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={clsx('relative whitespace-nowrap px-4 py-3 text-[13px] font-medium transition-colors', activeTab === tab.id ? 'text-brand' : 'text-gray-400 hover:text-gray-600')}>
              <span className="mr-1">{tab.icon}</span>{tab.label}
              {tab.count !== undefined && tab.count > 0 && <span className="ml-1 rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">{tab.count}</span>}
              {activeTab === tab.id && <span className="absolute bottom-0 left-0 right-0 h-[2px] rounded-full bg-brand" />}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {(rulesLoading || panelLoading) ? (
        <div className="flex justify-center py-16"><div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-200 border-t-brand" /></div>
      ) : (
        <>
          {activeTab === 'overview' && <OverviewTab content={agentRules?.entry_content || ''} title={agentRules?.title || ''} />}
          {activeTab === 'steps' && <StepsTab steps={agentRules?.steps || []} expandedStep={expandedStep} onToggle={(p) => setExpandedStep(expandedStep === p ? null : p)} />}
          {activeTab === 'templates' && <TemplatesTab templates={agentRules?.templates || []} />}
          {activeTab === 'custom' && <CustomRulesTab rules={customRules} loading={customRulesLoading} onEdit={(r) => { setEditMode('edit'); setEditFilename(r.filename); setEditContent(r.content); setShowEditor(true) }} onDelete={handleDeleteRule} onNew={() => { setEditMode('create'); setEditFilename(''); setEditContent(''); setShowEditor(true) }} />}
          {activeTab === 'plugins' && <PluginsTab agentId={agentId!} plugins={panelData?.available_plugins || []} onToggle={async (pid, en) => { if (!agentId) return; await toggleAgentPlugin(agentId, pid, en); await fetchPanel(agentId) }} />}
          {activeTab === 'mcp' && <MCPTab agentId={agentId!} servers={panelData?.config?.mcp_servers || []} onAdd={async (name, url, tools) => { if (!agentId) return; await addAgentMCP(agentId, name, url, tools); await fetchPanel(agentId) }} onRemove={async (name) => { if (!agentId) return; await removeAgentMCP(agentId, name); await fetchPanel(agentId) }} />}
          {activeTab === 'skills' && <SkillsTab agentId={agentId!} skills={panelData?.available_skills || []} onToggle={async (sid, en) => { if (!agentId) return; await toggleAgentSkill(agentId, sid, en); await fetchPanel(agentId) }} />}
          {activeTab === 'integrations' && <IntegrationsTab agentId={agentId!} integrations={panelData?.available_integrations || []} onToggle={async (iid, en) => { if (!agentId) return; await toggleAgentIntegration(agentId, iid, en); await fetchPanel(agentId) }} />}
          {activeTab === 'memory' && <MemoryTab agentId={agentId!} memories={panelData?.config?.memory || []} onAdd={async (title, content, type) => { if (!agentId) return; await addAgentMemory(agentId, title, content, type); await fetchPanel(agentId) }} onDelete={async (mid) => { if (!agentId) return; await deleteAgentMemory(agentId, mid); await fetchPanel(agentId) }} />}
        </>
      )}

      {/* 规则编辑器弹窗 */}
      {showEditor && (
        <RuleEditorModal mode={editMode} filename={editFilename} content={editContent} saving={saving} onChangeFilename={setEditFilename} onChangeContent={setEditContent} onSave={handleSaveRule} onClose={() => setShowEditor(false)} />
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   Tab: 总览 — 渲染入口文件 Markdown
   ═══════════════════════════════════════════════════════ */
function OverviewTab({ content, title }: { content: string; title: string }) {
  if (!content) return <EmptyTab icon="📄" text="暂无规则入口文件" />
  return (
    <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-card">
      {title && <h3 className="mb-4 text-[16px] font-bold text-gray-900">{title}</h3>}
      <div className="prose prose-sm max-w-none"><MarkdownContent content={content} /></div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   Tab: 工作步骤
   ═══════════════════════════════════════════════════════ */
function StepsTab({ steps, expandedStep, onToggle }: { steps: AgentRuleStep[]; expandedStep: string | null; onToggle: (p: string) => void }) {
  if (steps.length === 0) return <EmptyTab icon="🔄" text="该智能体没有定义工作步骤文件" />
  return (
    <div className="space-y-2">
      {steps.map((step, idx) => (
        <div key={step.path} className="rounded-xl border border-gray-100 bg-white shadow-card overflow-hidden">
          <button className="flex w-full items-center gap-3 p-4 text-left hover:bg-gray-50 transition-colors" onClick={() => onToggle(step.path)}>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-[13px] font-bold text-brand">{String(idx + 1).padStart(2, '0')}</div>
            <div className="flex-1 min-w-0"><div className="text-[13px] font-semibold text-gray-900">{formatStepName(step.name)}</div><div className="text-[11px] text-gray-400">{step.path}</div></div>
            <svg className={clsx('h-4 w-4 text-gray-400 transition-transform', expandedStep === step.path && 'rotate-180')} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" /></svg>
          </button>
          {expandedStep === step.path && <div className="border-t border-gray-50 bg-gray-50/50 p-4"><div className="prose prose-sm max-w-none"><MarkdownContent content={step.content} /></div></div>}
        </div>
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   Tab: 模板文件
   ═══════════════════════════════════════════════════════ */
function TemplatesTab({ templates }: { templates: AgentRuleStep[] }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  if (templates.length === 0) return <EmptyTab icon="📝" text="该智能体没有模板文件" />
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {templates.map(tmpl => (
        <div key={tmpl.path} className={clsx('rounded-xl border bg-white p-4 shadow-card transition-all cursor-pointer', expanded === tmpl.path ? 'border-brand/30 col-span-1 sm:col-span-2' : 'border-gray-100 hover:shadow-card-hover')} onClick={() => setExpanded(expanded === tmpl.path ? null : tmpl.path)}>
          <div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-lg bg-purple-50 text-lg">📄</div><div className="flex-1 min-w-0"><div className="text-[13px] font-semibold text-gray-900 truncate">{tmpl.name}</div><div className="text-[11px] text-gray-400 truncate">{tmpl.path}</div></div></div>
          {expanded === tmpl.path && <div className="mt-4 rounded-lg bg-gray-50 p-4"><div className="prose prose-sm max-w-none"><MarkdownContent content={tmpl.content} /></div></div>}
        </div>
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   Tab: 自定义规则
   ═══════════════════════════════════════════════════════ */
function CustomRulesTab({ rules, loading, onEdit, onDelete, onNew }: { rules: CustomRule[]; loading: boolean; onEdit: (r: CustomRule) => void; onDelete: (f: string) => void; onNew: () => void }) {
  if (loading) return <div className="flex justify-center py-8"><div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-200 border-t-brand" /></div>
  return (
    <div className="space-y-3">
      {rules.length === 0 && <EmptyTab icon="✨" text="还没有自定义规则模板" subtext="你可以为该智能体编写自定义规则，扩展或覆盖默认行为" />}
      {rules.map(rule => (
        <div key={rule.filename} className="rounded-xl border border-gray-100 bg-white p-4 shadow-card">
          <div className="flex items-center justify-between">
            <div><div className="text-[13px] font-semibold text-gray-900">{rule.title || rule.filename}</div><div className="mt-1 flex items-center gap-3 text-[11px] text-gray-400"><span>{rule.filename}</span><span>•</span><span>{(rule.size / 1024).toFixed(1)} KB</span><span>•</span><span>{new Date(rule.modified).toLocaleDateString()}</span></div></div>
            <div className="flex items-center gap-2"><button onClick={() => onEdit(rule)} className="rounded-lg px-3 py-1.5 text-[11px] font-medium text-brand hover:bg-brand-50">编辑</button><button onClick={() => onDelete(rule.filename)} className="rounded-lg px-3 py-1.5 text-[11px] font-medium text-red-500 hover:bg-red-50">删除</button></div>
          </div>
        </div>
      ))}
      <button onClick={onNew} className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-gray-200 py-4 text-[13px] font-medium text-gray-400 transition-all hover:border-brand hover:text-brand hover:bg-brand-50">
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>
        创建自定义规则模板
      </button>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   Tab: 插件管理
   ═══════════════════════════════════════════════════════ */
function PluginsTab({ agentId, plugins, onToggle }: { agentId: string; plugins: AgentPlugin[]; onToggle: (id: string, en: boolean) => Promise<void> }) {
  const [toggling, setToggling] = useState<string | null>(null)
  if (plugins.length === 0) return <EmptyTab icon="🔌" text="暂无可用插件" />

  const categories = [...new Set(plugins.map(p => p.category))]
  const catLabels: Record<string, string> = { quality: '质量保障', testing: '自动化测试', productivity: '效率提升', monitoring: '监控', security: '安全', workflow: '工作流', maintenance: '维护' }

  const handleToggle = async (pid: string, currentEnabled: boolean) => {
    setToggling(pid)
    try { await onToggle(pid, !currentEnabled) } catch (e) { console.error(e) }
    finally { setToggling(null) }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-card">
        <div className="mb-1 text-[14px] font-semibold text-gray-900">插件市场</div>
        <p className="text-[12px] text-gray-400 mb-4">为 {agentId} 启用或禁用系统插件，扩展智能体能力</p>
        <div className="flex items-center gap-4 text-[12px] text-gray-500">
          <span>已启用 <span className="font-semibold text-gray-900">{plugins.filter(p => p.enabled).length}</span></span>
          <span>总计 <span className="font-semibold text-gray-900">{plugins.length}</span></span>
        </div>
      </div>
      {categories.map(cat => (
        <div key={cat}>
          <div className="mb-2 text-[12px] font-semibold text-gray-400 uppercase tracking-wider">{catLabels[cat] || cat}</div>
          <div className="space-y-2">
            {plugins.filter(p => p.category === cat).map(plugin => (
              <div key={plugin.id} className={clsx('flex items-center gap-4 rounded-xl border p-4 bg-white shadow-card transition-all', plugin.enabled ? 'border-brand/20' : 'border-gray-100')}>
                <div className="flex h-10 w-10 items-center justify-center rounded-xl text-xl bg-gray-50">{plugin.icon}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-semibold text-gray-900">{plugin.name}</div>
                  <div className="text-[11px] text-gray-400 mt-0.5">{plugin.desc}</div>
                  {plugin.tags?.length > 0 && <div className="mt-2 flex gap-1">{plugin.tags.map(t => <span key={t} className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-500">{t}</span>)}</div>}
                </div>
                <button disabled={toggling === plugin.id} onClick={() => handleToggle(plugin.id, !!plugin.enabled)} className={clsx('relative h-6 w-11 rounded-full transition-all duration-200 flex-shrink-0', plugin.enabled ? 'bg-brand' : 'bg-gray-200', toggling === plugin.id && 'opacity-50')}>
                  <span className={clsx('absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200', plugin.enabled && 'translate-x-5')} />
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   Tab: MCP 服务器
   ═══════════════════════════════════════════════════════ */
function MCPTab({ agentId, servers, onAdd, onRemove }: { agentId: string; servers: AgentMCPServer[]; onAdd: (n: string, u: string, t?: string[]) => Promise<void>; onRemove: (n: string) => Promise<void> }) {
  const [showAdd, setShowAdd] = useState(false)
  const [newName, setNewName] = useState('')
  const [newUrl, setNewUrl] = useState('')
  const [newTools, setNewTools] = useState('')
  const [adding, setAdding] = useState(false)

  const handleAdd = async () => {
    if (!newName.trim() || !newUrl.trim()) return
    setAdding(true)
    try {
      const tools = newTools.split(',').map(t => t.trim()).filter(Boolean)
      await onAdd(newName.trim(), newUrl.trim(), tools)
      setNewName(''); setNewUrl(''); setNewTools('')
      setShowAdd(false)
    } catch (e) { console.error(e) }
    finally { setAdding(false) }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-card">
        <div className="flex items-center justify-between">
          <div>
            <div className="mb-1 text-[14px] font-semibold text-gray-900">MCP 服务器</div>
            <p className="text-[12px] text-gray-400">管理该智能体的 Model Context Protocol 服务器连接</p>
          </div>
          <button onClick={() => setShowAdd(!showAdd)} className="rounded-xl bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand/90 transition-all">{showAdd ? '取消' : '+ 添加'}</button>
        </div>
      </div>

      {showAdd && (
        <div className="rounded-xl border border-brand/20 bg-white p-5 shadow-card space-y-3">
          <input type="text" value={newName} onChange={e => setNewName(e.target.value)} placeholder="服务器名称" className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-[13px] outline-none focus:border-brand" />
          <input type="text" value={newUrl} onChange={e => setNewUrl(e.target.value)} placeholder="服务器 URL (如 http://localhost:3001)" className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-[13px] outline-none focus:border-brand" />
          <input type="text" value={newTools} onChange={e => setNewTools(e.target.value)} placeholder="工具列表 (逗号分隔，可选)" className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-[13px] outline-none focus:border-brand" />
          <button onClick={handleAdd} disabled={!newName.trim() || !newUrl.trim() || adding} className="rounded-lg bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand/90 disabled:opacity-50">{adding ? '添加中...' : '添加服务器'}</button>
        </div>
      )}

      {servers.length === 0 && !showAdd && <EmptyTab icon="🔗" text="尚未配置 MCP 服务器" subtext="MCP 允许智能体连接外部工具服务" />}

      <div className="space-y-2">
        {servers.map(server => (
          <div key={server.server_name} className="flex items-center gap-4 rounded-xl border border-gray-100 bg-white p-4 shadow-card">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-brand text-lg">🔗</div>
            <div className="flex-1 min-w-0">
              <div className="text-[13px] font-semibold text-gray-900">{server.server_name}</div>
              <div className="text-[11px] text-gray-400 mt-0.5 truncate">{server.server_url || '未配置 URL'}</div>
              {server.tools?.length > 0 && <div className="mt-1.5 flex gap-1 flex-wrap">{server.tools.map(t => <span key={t} className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] text-blue-600">{t}</span>)}</div>}
            </div>
            <button onClick={() => onRemove(server.server_name)} className="rounded-lg px-3 py-1.5 text-[11px] font-medium text-red-500 hover:bg-red-50">移除</button>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   Tab: 技能管理
   ═══════════════════════════════════════════════════════ */
function SkillsTab({ agentId, skills, onToggle }: { agentId: string; skills: AgentSkillItem[]; onToggle: (id: string, en: boolean) => Promise<void> }) {
  if (skills.length === 0) return <EmptyTab icon="🧠" text="暂无可用技能" subtext="系统规则目录 rules/skills/ 中没有发现技能包" />

  const [toggling, setToggling] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const categories = [...new Set(skills.map(s => s.category))]
  const catLabels: Record<string, string> = { architecture: '架构设计', unity: 'Unity 开发', csharp: 'C# 开发', testing: '测试' }

  const handleToggle = async (sid: string, currentBound: boolean) => {
    setToggling(sid)
    try { await onToggle(sid, !currentBound) } catch (e) { console.error(e) }
    finally { setToggling(null) }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-card">
        <div className="mb-1 text-[14px] font-semibold text-gray-900">技能包管理</div>
        <p className="text-[12px] text-gray-400">绑定或解绑技能包，增强智能体在特定领域的专业能力</p>
        <div className="mt-3 flex items-center gap-4 text-[12px] text-gray-500">
          <span>已绑定 <span className="font-semibold text-gray-900">{skills.filter(s => s.bound).length}</span></span>
          <span>总计 <span className="font-semibold text-gray-900">{skills.length}</span></span>
        </div>
      </div>
      {categories.map(cat => (
        <div key={cat}>
          <div className="mb-2 text-[12px] font-semibold text-gray-400 uppercase tracking-wider">{catLabels[cat] || cat}</div>
          <div className="space-y-2">
            {skills.filter(s => s.category === cat).map(skill => (
              <div key={skill.skill_id} className={clsx('rounded-xl border bg-white shadow-card overflow-hidden transition-all', skill.bound ? 'border-brand/20' : 'border-gray-100')}>
                <div className="flex items-center gap-4 p-4 cursor-pointer" onClick={() => setExpanded(expanded === skill.skill_id ? null : skill.skill_id)}>
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-50 text-brand text-lg">🧠</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-semibold text-gray-900">{skill.skill_name || skill.title}</div>
                    <div className="text-[11px] text-gray-400">{skill.file_path}</div>
                  </div>
                  <button disabled={toggling === skill.skill_id} onClick={e => { e.stopPropagation(); handleToggle(skill.skill_id, skill.bound) }} className={clsx('relative h-6 w-11 rounded-full transition-all duration-200 flex-shrink-0', skill.bound ? 'bg-brand' : 'bg-gray-200', toggling === skill.skill_id && 'opacity-50')}>
                    <span className={clsx('absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200', skill.bound && 'translate-x-5')} />
                  </button>
                </div>
                {expanded === skill.skill_id && skill.content_preview && (
                  <div className="border-t border-gray-50 bg-gray-50/50 p-4"><div className="prose prose-sm max-w-none"><MarkdownContent content={skill.content_preview} /></div></div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   Tab: 集成管理
   ═══════════════════════════════════════════════════════ */
function IntegrationsTab({ agentId, integrations, onToggle }: { agentId: string; integrations: AgentIntegration[]; onToggle: (id: string, en: boolean) => Promise<void> }) {
  const [toggling, setToggling] = useState<string | null>(null)

  if (integrations.length === 0) return <EmptyTab icon="🛠️" text="暂无可用集成" />

  const handleToggle = async (iid: string, currentEnabled: boolean) => {
    setToggling(iid)
    try { await onToggle(iid, !currentEnabled) } catch (e) { console.error(e) }
    finally { setToggling(null) }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-card">
        <div className="mb-1 text-[14px] font-semibold text-gray-900">第三方集成</div>
        <p className="text-[12px] text-gray-400">连接外部服务，扩展智能体能力边界</p>
        <div className="mt-3 flex items-center gap-4 text-[12px] text-gray-500">
          <span>已启用 <span className="font-semibold text-gray-900">{integrations.filter(i => i.enabled).length}</span></span>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {integrations.map(integ => (
          <div key={integ.id} className={clsx('rounded-xl border p-4 bg-white shadow-card transition-all', integ.enabled ? 'border-brand/20' : 'border-gray-100')}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gray-50 text-xl">{integ.icon}</div>
                <div>
                  <div className="text-[13px] font-semibold text-gray-900">{integ.name}</div>
                  <div className="text-[11px] text-gray-400 mt-0.5">{integ.desc}</div>
                  <span className={clsx('mt-1 inline-block rounded-full px-2 py-0.5 text-[10px] font-medium', integ.status === 'available' ? 'bg-emerald-50 text-emerald-600' : 'bg-gray-100 text-gray-500')}>{integ.status === 'available' ? '可连接' : integ.status}</span>
                </div>
              </div>
              <button disabled={toggling === integ.id} onClick={() => handleToggle(integ.id, !!integ.enabled)} className={clsx('relative h-6 w-11 rounded-full transition-all duration-200 flex-shrink-0', integ.enabled ? 'bg-brand' : 'bg-gray-200', toggling === integ.id && 'opacity-50')}>
                <span className={clsx('absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200', integ.enabled && 'translate-x-5')} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   Tab: 记忆管理
   ═══════════════════════════════════════════════════════ */
function MemoryTab({ agentId, memories, onAdd, onDelete }: { agentId: string; memories: AgentMemoryItem[]; onAdd: (t: string, c: string, type?: string) => Promise<void>; onDelete: (id: string) => Promise<void> }) {
  const [showAdd, setShowAdd] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newContent, setNewContent] = useState('')
  const [newType, setNewType] = useState('knowledge')
  const [adding, setAdding] = useState(false)

  const handleAdd = async () => {
    if (!newTitle.trim() || !newContent.trim()) return
    setAdding(true)
    try {
      await onAdd(newTitle.trim(), newContent.trim(), newType)
      setNewTitle(''); setNewContent(''); setShowAdd(false)
    } catch (e) { console.error(e) }
    finally { setAdding(false) }
  }

  const typeLabels: Record<string, { label: string; color: string }> = {
    knowledge: { label: '知识', color: 'bg-blue-50 text-blue-600' },
    preference: { label: '偏好', color: 'bg-purple-50 text-purple-600' },
    context: { label: '上下文', color: 'bg-amber-50 text-amber-600' },
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-card">
        <div className="flex items-center justify-between">
          <div>
            <div className="mb-1 text-[14px] font-semibold text-gray-900">智能体记忆</div>
            <p className="text-[12px] text-gray-400">为智能体添加持久化知识条目，跨会话保留</p>
          </div>
          <button onClick={() => setShowAdd(!showAdd)} className="rounded-xl bg-brand px-4 py-2 text-[12px] font-medium text-white hover:bg-brand/90 transition-all">{showAdd ? '取消' : '+ 添加记忆'}</button>
        </div>
      </div>

      {showAdd && (
        <div className="rounded-xl border border-brand/20 bg-white p-5 shadow-card space-y-3">
          <input type="text" value={newTitle} onChange={e => setNewTitle(e.target.value)} placeholder="记忆标题" className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-[13px] outline-none focus:border-brand" />
          <textarea value={newContent} onChange={e => setNewContent(e.target.value)} placeholder="记忆内容..." rows={3} className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-[13px] outline-none focus:border-brand resize-none" />
          <select value={newType} onChange={e => setNewType(e.target.value)} className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-[13px] outline-none focus:border-brand">
            <option value="knowledge">知识</option>
            <option value="preference">偏好</option>
            <option value="context">上下文</option>
          </select>
          <button onClick={handleAdd} disabled={!newTitle.trim() || !newContent.trim() || adding} className="rounded-lg bg-brand px-4 py-2 text-[13px] font-medium text-white hover:bg-brand/90 disabled:opacity-50">{adding ? '添加中...' : '保存记忆'}</button>
        </div>
      )}

      {memories.length === 0 && !showAdd && <EmptyTab icon="💾" text="暂无记忆条目" subtext="添加知识、偏好或上下文，让智能体更了解你的项目" />}

      <div className="space-y-2">
        {memories.map(mem => {
          const tl = typeLabels[mem.memory_type] || typeLabels.knowledge
          return (
            <div key={mem.id} className="rounded-xl border border-gray-100 bg-white p-4 shadow-card">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2"><span className="text-[13px] font-semibold text-gray-900">{mem.title}</span><span className={clsx('rounded-full px-2 py-0.5 text-[10px] font-medium', tl.color)}>{tl.label}</span></div>
                  <p className="mt-1.5 text-[12px] text-gray-500 leading-relaxed">{mem.content}</p>
                  {mem.created_at && <span className="text-[10px] text-gray-300 mt-2 block">{new Date(mem.created_at).toLocaleString()}</span>}
                </div>
                <button onClick={() => onDelete(mem.id)} className="flex-shrink-0 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-red-500 hover:bg-red-50">删除</button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   空状态
   ═══════════════════════════════════════════════════════ */
function EmptyTab({ icon, text, subtext }: { icon: string; text: string; subtext?: string }) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-8 text-center">
      <div className="text-4xl mb-3">{icon}</div>
      <p className="text-[13px] text-gray-400">{text}</p>
      {subtext && <p className="text-[12px] text-gray-300 max-w-sm mx-auto mt-1">{subtext}</p>}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   规则编辑器弹窗
   ═══════════════════════════════════════════════════════ */
function RuleEditorModal({ mode, filename, content, saving, onChangeFilename, onChangeContent, onSave, onClose }: { mode: 'create' | 'edit'; filename: string; content: string; saving: boolean; onChangeFilename: (v: string) => void; onChangeContent: (v: string) => void; onSave: () => void; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={onClose}>
      <div className="flex h-[80vh] w-full max-w-3xl flex-col rounded-2xl bg-white shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h3 className="text-[16px] font-bold text-gray-900">{mode === 'create' ? '✨ 创建自定义规则' : `📝 编辑 ${filename}`}</h3>
          <button onClick={onClose} className="rounded-lg p-1 hover:bg-gray-100"><svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg></button>
        </div>
        {mode === 'create' && <div className="border-b border-gray-50 px-6 py-3"><input type="text" value={filename} onChange={e => onChangeFilename(e.target.value)} placeholder="文件名（可选，如 my_rule.md）" className="w-full rounded-lg border border-gray-200 px-3 py-2 text-[13px] outline-none focus:border-brand" /></div>}
        <div className="flex-1 overflow-hidden px-6 py-4"><textarea value={content} onChange={e => onChangeContent(e.target.value)} placeholder="在此编写 Markdown 格式的规则内容..." className="h-full w-full resize-none rounded-xl border border-gray-200 p-4 font-mono text-[13px] leading-relaxed text-gray-700 outline-none focus:border-brand focus:ring-1 focus:ring-brand/20" /></div>
        <div className="flex items-center justify-between border-t border-gray-100 px-6 py-4">
          <span className="text-[11px] text-gray-400">支持 Markdown 格式 • {content.length} 字符</span>
          <div className="flex gap-3"><button onClick={onClose} className="rounded-xl px-5 py-2 text-[13px] font-medium text-gray-600 hover:bg-gray-100">取消</button><button onClick={onSave} disabled={!content.trim() || saving} className="rounded-xl bg-brand px-5 py-2 text-[13px] font-medium text-white hover:bg-brand/90 disabled:opacity-50">{saving ? '保存中...' : '保存'}</button></div>
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   Markdown 简易渲染
   ═══════════════════════════════════════════════════════ */
function MarkdownContent({ content }: { content: string }) {
  const html = content
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-gray-900 text-gray-100 rounded-lg p-4 text-xs overflow-x-auto my-3"><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code class="bg-gray-100 text-brand px-1.5 py-0.5 rounded text-xs font-mono">$1</code>')
    .replace(/\|(.+)\|/g, (match) => {
      const cells = match.split('|').filter(Boolean).map(c => c.trim())
      if (cells.every(c => /^[-:]+$/.test(c))) return ''
      return `<tr>${cells.map(c => `<td class="border border-gray-200 px-3 py-2 text-xs">${c}</td>`).join('')}</tr>`
    })
    .replace(/^#### (.+)$/gm, '<h4 class="text-sm font-bold text-gray-800 mt-4 mb-2">$1</h4>')
    .replace(/^### (.+)$/gm, '<h3 class="text-sm font-bold text-gray-900 mt-5 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-base font-bold text-gray-900 mt-6 mb-3">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-lg font-bold text-gray-900 mt-6 mb-3">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^> (.+)$/gm, '<blockquote class="border-l-3 border-brand/30 pl-4 py-1 my-2 text-gray-500 italic text-xs">$1</blockquote>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc text-xs text-gray-600 py-0.5">$1</li>')
    .replace(/^---$/gm, '<hr class="my-4 border-gray-100" />')
    .replace(/\n\n/g, '</p><p class="text-xs text-gray-600 leading-relaxed my-2">')
    .replace(/\n/g, '<br />')
  return <div className="text-[12px] leading-relaxed text-gray-600" dangerouslySetInnerHTML={{ __html: `<p class="text-xs text-gray-600 leading-relaxed">${html}</p>` }} />
}

function formatStepName(name: string): string { return name.replace(/^step-\d{2}_/, '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) }
