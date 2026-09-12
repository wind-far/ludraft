import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePageTitle } from '@/hooks/usePageTitle'
import Badge from '@/components/ui/Badge'
import Avatar from '@/components/ui/Avatar'
import { useAgentStore } from '@/stores/useAgentStore'
import { GROUP_LABELS, GROUP_COLORS } from '@/utils/constants'
import type { AgentInfo, CapabilityData } from '@/api/types'
import clsx from 'clsx'

const AVATAR_COLORS = ['blue', 'green', 'purple', 'orange', 'cyan', 'pink', 'indigo', 'blue'] as const

/** 状态标签映射 */
const STATUS_MAP: Record<string, { label: string; color: string; dotColor: string; pingColor: string }> = {
  online:  { label: '在线就绪', color: 'text-emerald-600', dotColor: 'bg-emerald-500', pingColor: 'bg-emerald-500/60' },
  busy:    { label: '配置不完整', color: 'text-amber-600', dotColor: 'bg-amber-400', pingColor: 'bg-amber-400/60' },
  offline: { label: '未配置', color: 'text-gray-400', dotColor: 'bg-gray-300', pingColor: 'bg-gray-300/0' },
}

export default function Team() {
  usePageTitle('AI 团队')
  const navigate = useNavigate()
  const { agents, loading, fetch: fetchAgents, capabilities, capabilitiesLoading, fetchCaps } = useAgentStore()
  const [expandedCap, setExpandedCap] = useState<string | null>(null)
  const [showNewAgentModal, setShowNewAgentModal] = useState(false)

  useEffect(() => {
    fetchAgents()
    fetchCaps()
  }, [fetchAgents, fetchCaps])

  // 按并行组分组
  const groups = agents.reduce<Record<string, AgentInfo[]>>((acc, m) => {
    const g = m.parallel_group || 'other'
    if (!acc[g]) acc[g] = []
    acc[g].push(m)
    return acc
  }, {})

  // 状态统计
  const onlineCount = agents.filter(a => a.model_status?.status === 'online').length
  const totalCount = agents.length

  return (
    <div className="space-y-10">
      {/* Hero */}
      <div className="text-center py-4">
        <h1 className="text-[32px] font-bold tracking-tight text-gray-900">
          认识你的 <span className="italic text-brand">AI 团队</span>
        </h1>
        <p className="mx-auto mt-3 max-w-md text-[15px] leading-relaxed text-gray-500">
          {totalCount} 位专业 AI 成员，覆盖游戏开发全流程，24/7 为你服务
        </p>
        {/* 在线状态摘要 */}
        <div className="mt-4 flex items-center justify-center gap-6">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            <span className="text-[12px] text-gray-500">
              在线 <span className="font-semibold text-gray-900">{onlineCount}</span>
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-amber-400" />
            <span className="text-[12px] text-gray-500">
              待配置 <span className="font-semibold text-gray-900">{agents.filter(a => a.model_status?.status === 'busy').length}</span>
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-gray-300" />
            <span className="text-[12px] text-gray-500">
              离线 <span className="font-semibold text-gray-900">{agents.filter(a => a.model_status?.status === 'offline').length}</span>
            </span>
          </div>
        </div>
      </div>

      {/* 协作流程 */}
      <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-card">
        <div className="mb-4 text-center">
          <span className="text-[13px] font-semibold text-gray-900">协作流程</span>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          {[
            { label: '需求分析', color: 'bg-blue-50 text-blue-600' },
            { label: '策划设计', color: 'bg-emerald-50 text-emerald-600' },
            { label: '技术架构', color: 'bg-purple-50 text-purple-600' },
            { label: '代码实现', color: 'bg-brand-50 text-brand' },
            { label: '测试验证', color: 'bg-cyan-50 text-cyan-600' },
            { label: '交付', color: 'bg-emerald-50 text-emerald-600' },
          ].map((step, i) => (
            <span key={i} className="flex items-center gap-2">
              {i > 0 && (
                <svg className="h-3 w-3 text-gray-200" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
              )}
              <span className={`rounded-lg px-3 py-2 text-[12px] font-medium ${step.color}`}>
                {step.label}
              </span>
            </span>
          ))}
        </div>
      </div>

      {/* 按组展示成员 */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-200 border-t-brand" />
        </div>
      ) : (
        Object.entries(groups).map(([group, members]) => (
          <div key={group}>
            <div className="mb-4 flex items-center gap-2">
              <h2 className="text-[15px] font-semibold text-gray-900">
                {GROUP_LABELS[group] || group}
              </h2>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500">
                {members.length > 1 ? '并行' : '串行'}
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {members.map((member) => {
                const colorIdx = agents.indexOf(member)
                const avatarColor = AVATAR_COLORS[colorIdx % AVATAR_COLORS.length] || 'blue'
                const status = member.model_status?.status || 'offline'
                const statusInfo = STATUS_MAP[status] || STATUS_MAP.offline

                return (
                  <div
                    key={member.id}
                    onClick={() => navigate(`/team/${member.id}`)}
                    className="group flex cursor-pointer items-start gap-4 rounded-xl border border-gray-100 bg-white p-5 shadow-card transition-all hover:shadow-card-hover hover:border-gray-200"
                  >
                    <Avatar
                      icon={<span className="text-2xl">{member.icon || '🤖'}</span>}
                      size="lg"
                      color={avatarColor}
                      status={status as 'online' | 'busy' | 'offline'}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2.5">
                        <h3 className="text-[15px] font-bold text-gray-900 group-hover:text-brand transition-colors">
                          {member.name}
                        </h3>
                        <Badge color={GROUP_COLORS[member.parallel_group] as any} size="sm">
                          {member.role}
                        </Badge>
                      </div>
                      <p className="mt-2 text-[13px] leading-relaxed text-gray-500">
                        {member.persona || '暂无描述'}
                      </p>
                      {/* 真实状态反馈 */}
                      <div className="mt-3 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="relative flex h-2 w-2">
                            {status === 'online' && (
                              <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${statusInfo.pingColor}`} />
                            )}
                            <span className={`relative inline-flex h-2 w-2 rounded-full ${statusInfo.dotColor}`} />
                          </span>
                          <span className={`text-[11px] font-medium ${statusInfo.color}`}>
                            {statusInfo.label}
                          </span>
                          {member.model_status?.model && (
                            <span className="text-[10px] text-gray-400">
                              {member.model_status.provider}/{member.model_status.model}
                            </span>
                          )}
                        </div>
                        {/* 进入详情箭头 */}
                        <svg className="h-4 w-4 text-gray-300 group-hover:text-brand transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                        </svg>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))
      )}

      {/* 添加新智能体按钮 */}
      <div className="flex justify-center">
        <button
          onClick={() => setShowNewAgentModal(true)}
          className="flex items-center gap-2 rounded-xl border-2 border-dashed border-gray-200 px-6 py-3 text-[13px] font-medium text-gray-400 transition-all hover:border-brand hover:text-brand hover:bg-brand-50"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          添加新智能体
        </button>
      </div>

      {/* 特色能力 */}
      <div>
        <h2 className="mb-4 text-center text-[15px] font-semibold text-gray-900">
          团队特色能力
        </h2>
        {capabilitiesLoading ? (
          <div className="flex justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-200 border-t-brand" />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(capabilities.length > 0 ? capabilities : FALLBACK_CAPS).map((cap) => (
              <CapabilityCard
                key={cap.id}
                cap={cap}
                expanded={expandedCap === cap.id}
                onToggle={() => setExpandedCap(expandedCap === cap.id ? null : cap.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* 新智能体弹窗 */}
      {showNewAgentModal && (
        <NewAgentModal onClose={() => setShowNewAgentModal(false)} />
      )}
    </div>
  )
}

/** 特色能力卡片 */
function CapabilityCard({ cap, expanded, onToggle }: { cap: CapabilityData; expanded: boolean; onToggle: () => void }) {
  return (
    <div
      className={clsx(
        'rounded-xl border bg-white p-5 shadow-card transition-all cursor-pointer',
        expanded ? 'border-brand/30 shadow-card-hover' : 'border-gray-100 hover:shadow-card-hover'
      )}
      onClick={onToggle}
    >
      <div className="flex items-start justify-between">
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-gray-50 text-xl">
          {cap.icon}
        </div>
        <svg
          className={clsx('h-4 w-4 text-gray-400 transition-transform', expanded && 'rotate-180')}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
        </svg>
      </div>
      <div className="text-[13px] font-semibold text-gray-900">{cap.title}</div>
      <div className="mt-1.5 text-[12px] leading-relaxed text-gray-400">{cap.description}</div>
      {expanded && (
        <div className="mt-4 rounded-lg bg-gray-50 p-4">
          <p className="text-[12px] leading-relaxed text-gray-600">{cap.detail}</p>
          {cap.data && typeof cap.data === 'object' && Array.isArray(cap.data) && (
            <div className="mt-3 space-y-1">
              {(cap.data as Array<Record<string, unknown>>).map((item, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px] text-gray-500">
                  <span className="h-1 w-1 rounded-full bg-brand" />
                  {item.name || item.group || JSON.stringify(item)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** 新智能体创建弹窗 */
function NewAgentModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    agent_name: '',
    agent_icon: '🤖',
    role: '',
    persona: '',
    group: 'implementation',
    entry_content: '',
    sandbox: true,
  })
  const [creating, setCreating] = useState(false)
  const [createdAgentId, setCreatedAgentId] = useState<string | null>(null)
  const { fetch: fetchAgents } = useAgentStore()

  const handleCreate = async () => {
    if (!form.agent_name.trim()) return
    setCreating(true)
    try {
      const { createNewAgent } = await import('@/api/agents')
      const result = await createNewAgent(form)
      await fetchAgents()
      setCreatedAgentId(result.agent_id)
    } catch (e) {
      console.error('创建智能体失败:', e)
    } finally {
      setCreating(false)
    }
  }

  const goToAgent = () => {
    if (createdAgentId) {
      navigate(`/team/${createdAgentId}`)
    }
  }

  const ICON_OPTIONS = ['🤖', '🧠', '🎯', '⚡', '🔮', '🛠️', '📐', '🎪', '🌟', '🦾']
  const GROUP_OPTIONS = [
    { value: 'control', label: '🎯 指挥中心' },
    { value: 'design', label: '🎨 设计组' },
    { value: 'architecture', label: '🏗️ 架构组' },
    { value: 'implementation', label: '💻 开发组' },
    { value: 'verification', label: '🧪 验证组' },
  ]

  // 创建成功界面
  if (createdAgentId) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={onClose}>
        <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-2xl text-center" onClick={e => e.stopPropagation()}>
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-50 text-3xl">✅</div>
          <h3 className="mb-2 text-[18px] font-bold text-gray-900">智能体创建成功</h3>
          <p className="mb-6 text-[13px] text-gray-500">
            <span className="font-medium text-gray-700">{form.agent_name}</span> 已加入团队，
            系统已自动为其分配独立工作环境。
          </p>
          <div className="mb-6 rounded-xl bg-gray-50 p-4 text-left space-y-2">
            {[
              { icon: '📄', label: '规则入口文件', desc: `rules/agents/${createdAgentId}.md` },
              { icon: '📁', label: '步骤 & 模板目录', desc: `rules/agents/${createdAgentId}/` },
              ...(form.sandbox ? [{ icon: '📦', label: '沙盒隔离环境', desc: '已启用独立文件系统' }] : []),
              { icon: '⚙️', label: '插件 / MCP / 技能', desc: '可在详情页配置' },
              { icon: '💾', label: '独立记忆存储', desc: '跨会话知识持久化' },
            ].map((item, i) => (
              <div key={i} className="flex items-center gap-3 text-[12px]">
                <span className="text-base">{item.icon}</span>
                <div>
                  <span className="font-medium text-gray-700">{item.label}</span>
                  <span className="text-gray-400 ml-1">{item.desc}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="flex gap-3">
            <button onClick={onClose} className="flex-1 rounded-xl border border-gray-200 px-4 py-2.5 text-[13px] font-medium text-gray-600 hover:bg-gray-50">
              返回团队
            </button>
            <button onClick={goToAgent} className="flex-1 rounded-xl bg-brand px-4 py-2.5 text-[13px] font-medium text-white hover:bg-brand/90">
              进入详情配置
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="mb-6 flex items-center justify-between">
          <h3 className="text-[17px] font-bold text-gray-900">创建新智能体</h3>
          <button onClick={onClose} className="rounded-lg p-1 hover:bg-gray-100">
            <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-4">
          {/* 图标选择 */}
          <div>
            <label className="mb-1.5 block text-[12px] font-medium text-gray-600">选择图标</label>
            <div className="flex flex-wrap gap-2">
              {ICON_OPTIONS.map(icon => (
                <button
                  key={icon}
                  onClick={() => setForm(f => ({ ...f, agent_icon: icon }))}
                  className={clsx(
                    'flex h-10 w-10 items-center justify-center rounded-xl text-xl transition-all',
                    form.agent_icon === icon ? 'bg-brand-50 ring-2 ring-brand' : 'bg-gray-50 hover:bg-gray-100'
                  )}
                >
                  {icon}
                </button>
              ))}
            </div>
          </div>

          {/* 名称 */}
          <div>
            <label className="mb-1.5 block text-[12px] font-medium text-gray-600">智能体名称 *</label>
            <input
              type="text"
              value={form.agent_name}
              onChange={e => setForm(f => ({ ...f, agent_name: e.target.value }))}
              placeholder="例：资深架构师小王"
              className="w-full rounded-xl border border-gray-200 px-4 py-2.5 text-[13px] outline-none focus:border-brand focus:ring-1 focus:ring-brand/20"
            />
          </div>

          {/* 角色 */}
          <div>
            <label className="mb-1.5 block text-[12px] font-medium text-gray-600">角色定位</label>
            <input
              type="text"
              value={form.role}
              onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
              placeholder="例：数据库架构师"
              className="w-full rounded-xl border border-gray-200 px-4 py-2.5 text-[13px] outline-none focus:border-brand focus:ring-1 focus:ring-brand/20"
            />
          </div>

          {/* 所属组 */}
          <div>
            <label className="mb-1.5 block text-[12px] font-medium text-gray-600">所属工作组</label>
            <select
              value={form.group}
              onChange={e => setForm(f => ({ ...f, group: e.target.value }))}
              className="w-full rounded-xl border border-gray-200 px-4 py-2.5 text-[13px] outline-none focus:border-brand focus:ring-1 focus:ring-brand/20"
            >
              {GROUP_OPTIONS.map(g => (
                <option key={g.value} value={g.value}>{g.label}</option>
              ))}
            </select>
          </div>

          {/* 人格描述 */}
          <div>
            <label className="mb-1.5 block text-[12px] font-medium text-gray-600">人格描述</label>
            <textarea
              value={form.persona}
              onChange={e => setForm(f => ({ ...f, persona: e.target.value }))}
              placeholder="描述这个智能体的专业背景、沟通风格..."
              rows={3}
              className="w-full rounded-xl border border-gray-200 px-4 py-2.5 text-[13px] outline-none focus:border-brand focus:ring-1 focus:ring-brand/20 resize-none"
            />
          </div>

          {/* 沙盒隔离 */}
          <div className="rounded-xl border border-gray-100 p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-base">📦</span>
                  <span className="text-[13px] font-semibold text-gray-900">沙盒隔离</span>
                </div>
                <p className="mt-1 text-[11px] text-gray-400">为智能体分配独立文件系统，防止互相干扰</p>
              </div>
              <button
                onClick={() => setForm(f => ({ ...f, sandbox: !f.sandbox }))}
                className={clsx(
                  'relative h-6 w-11 rounded-full transition-all duration-200 flex-shrink-0',
                  form.sandbox ? 'bg-brand' : 'bg-gray-200'
                )}
              >
                <span className={clsx(
                  'absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200',
                  form.sandbox && 'translate-x-5'
                )} />
              </button>
            </div>
          </div>

          {/* 创建后将自动获得的能力提示 */}
          <div className="rounded-xl bg-brand-50/50 p-4">
            <div className="text-[12px] font-medium text-brand mb-2">创建后将自动获得以下能力配置入口</div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { icon: '🔌', label: '插件管理' },
                { icon: '🔗', label: 'MCP 服务器' },
                { icon: '🧠', label: '技能包' },
                { icon: '🛠️', label: '第三方集成' },
                { icon: '💾', label: '持久记忆' },
                { icon: '✨', label: '自定义规则' },
              ].map(item => (
                <div key={item.label} className="flex items-center gap-1.5 text-[11px] text-gray-600">
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-xl px-5 py-2.5 text-[13px] font-medium text-gray-600 hover:bg-gray-100"
          >
            取消
          </button>
          <button
            onClick={handleCreate}
            disabled={!form.agent_name.trim() || creating}
            className="rounded-xl bg-brand px-5 py-2.5 text-[13px] font-medium text-white hover:bg-brand/90 disabled:opacity-50"
          >
            {creating ? '创建中...' : '创建智能体'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** 后备的静态能力数据（API 未就绪时） */
const FALLBACK_CAPS: CapabilityData[] = [
  { id: 'quality_gates', icon: '🛡️', title: '3 道质量门禁', description: '策划门禁 (21项)、技术门禁 (18项)、测试门禁 (12项)', detail: '通过三层质量检查确保每个阶段产出物符合标准。', data: null },
  { id: 'bug_fix', icon: '🐛', title: '自动 Bug 修复', description: 'QA 发现 Bug 自动回滚给程序，最多 3 轮修复循环', detail: 'QA智能体发现缺陷后自动创建Bug报告，系统回滚至程序员Agent。', data: null },
  { id: 'parallel', icon: '⚡', title: '并行协作', description: '5 个并行组同时工作，大幅提升开发效率', detail: '基于独立沙盒和消息队列，多个Agent可同时执行不同阶段的任务。', data: null },
  { id: 'sandbox', icon: '📦', title: '沙盒隔离', description: '每位成员独立工作空间，互不干扰', detail: '每个Agent拥有独立的文件系统沙盒，通过权限矩阵严格控制读写范围。', data: null },
  { id: 'review', icon: '🔍', title: '对抗审查', description: '程序员自我审查 + 主程交叉审查，双重保障', detail: '程序员Agent编写代码后先进行自我审查，再由主程Agent进行交叉审查。', data: null },
  { id: 'deliverables', icon: '📄', title: '完整交付物', description: '策划案、技术设计、代码、测试报告一应俱全', detail: '每个阶段都会产出标准化文档，所有交付物可追溯。', data: null },
]
