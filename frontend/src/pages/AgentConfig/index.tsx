import { useState, useEffect, useCallback } from 'react'
import { usePageTitle } from '@/hooks/usePageTitle'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Avatar from '@/components/ui/Avatar'
import { PageLoader } from '@/components/ui/Spinner'
import { TEAM_MEMBERS } from '@/utils/constants'
import {
  fetchAgentConfigs,
  updateAgentConfig,
  fetchModelProviders,
} from '@/api/agent-config'
import type { AgentModelConfig, ModelProviders } from '@/api/types'
import clsx from 'clsx'

const AVATAR_COLORS = ['blue', 'green', 'purple', 'orange', 'cyan', 'pink', 'indigo', 'blue'] as const

/* ━━━ 单个智能体配置卡片 ━━━ */
function AgentConfigCard({
  config,
  providers,
  onSave,
}: {
  config: AgentModelConfig
  providers: ModelProviders
  onSave: (agentId: string, updates: Record<string, unknown>) => Promise<void>
}) {
  const memberIdx = TEAM_MEMBERS.findIndex((m) => m.id === config.agent_id)
  const member = memberIdx >= 0 ? TEAM_MEMBERS[memberIdx] : null
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const [provider, setProvider] = useState(config.provider)
  const [model, setModel] = useState(config.model)
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState(config.base_url)
  const [temperature, setTemperature] = useState(config.temperature)
  const [maxTokens, setMaxTokens] = useState(config.max_tokens)
  const [enabled, setEnabled] = useState(config.enabled)

  const providerModels = providers[provider]?.models || []

  useEffect(() => {
    if (providerModels.length > 0 && !providerModels.find((m) => m.id === model)) {
      setModel(providerModels[0].id)
    }
  }, [provider]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSave = async () => {
    setSaving(true)
    try {
      const updates: Record<string, unknown> = { provider, model, temperature, max_tokens: maxTokens, enabled }
      if (apiKey) updates.api_key = apiKey
      if (baseUrl !== config.base_url) updates.base_url = baseUrl
      await onSave(config.agent_id, updates)
      setEditing(false)
      setApiKey('')
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { /* parent handles */ }
    finally { setSaving(false) }
  }

  const handleCancel = () => {
    setProvider(config.provider)
    setModel(config.model)
    setApiKey('')
    setBaseUrl(config.base_url)
    setTemperature(config.temperature)
    setMaxTokens(config.max_tokens)
    setEnabled(config.enabled)
    setEditing(false)
  }

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 shadow-card transition-all">
      {/* Agent 头部 */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Avatar
            icon={<span className="text-lg">{member?.icon || '🤖'}</span>}
            size="md"
            color={AVATAR_COLORS[memberIdx >= 0 ? memberIdx : 0]}
            status={enabled ? 'online' : 'offline'}
          />
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-[14px] font-semibold text-gray-900">
                {config.agent_name || config.agent_id}
              </h3>
              <Badge
                color={config.api_key_masked ? 'green' : 'yellow'}
                size="sm"
                variant="dot"
              >
                {config.api_key_masked ? '已配置' : '未配置密钥'}
              </Badge>
            </div>
            <p className="text-[11px] text-gray-400">{member?.role || config.agent_id}</p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {/* 开关 */}
          <button
            onClick={() => {
              const newEnabled = !enabled
              setEnabled(newEnabled)
              if (!editing) onSave(config.agent_id, { enabled: newEnabled })
            }}
            className={clsx(
              'relative h-6 w-11 rounded-full transition-all duration-200',
              enabled ? 'bg-emerald-500' : 'bg-gray-200'
            )}
          >
            <span className={clsx(
              'absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200',
              enabled && 'translate-x-5'
            )} />
          </button>

          {!editing ? (
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>配置</Button>
          ) : (
            <div className="flex gap-1.5">
              <Button variant="ghost" size="sm" onClick={handleCancel}>取消</Button>
              <Button variant="primary" size="sm" onClick={handleSave} loading={saving}>保存</Button>
            </div>
          )}
        </div>
      </div>

      {/* 配置摘要 */}
      {!editing && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl bg-gray-50 px-4 py-3">
          {[
            { label: '提供商', value: providers[config.provider]?.name || config.provider },
            { label: '模型', value: config.model },
            { label: '温度', value: String(config.temperature) },
            { label: '密钥', value: config.api_key_masked || '未设置' },
          ].map((item, i) => (
            <div key={item.label} className="flex items-center gap-1.5">
              {i > 0 && <span className="mr-2.5 hidden text-gray-200 sm:inline">·</span>}
              <span className="text-[10px] uppercase tracking-wider text-gray-400">{item.label}</span>
              <span className="text-[12px] font-medium text-gray-700">{item.value}</span>
            </div>
          ))}
          {saved && (
            <span className="ml-auto flex items-center gap-1 text-[11px] text-emerald-600">
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
              已保存
            </span>
          )}
        </div>
      )}

      {/* 编辑表单 */}
      {editing && (
        <div className="space-y-4 rounded-xl border border-gray-100 bg-gray-50 p-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                模型提供商
              </label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none focus:border-brand/40 focus:shadow-input"
              >
                {Object.entries(providers).map(([key, info]) => (
                  <option key={key} value={key}>{info.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                模型
              </label>
              {provider === 'custom' ? (
                <input
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="输入模型名称"
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none focus:border-brand/40 focus:shadow-input"
                />
              ) : (
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none focus:border-brand/40 focus:shadow-input"
                >
                  {providerModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({(m.context_window / 1000).toFixed(0)}K)
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          <div>
            <label className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
              API 密钥
              {config.api_key_masked && (
                <span className="normal-case tracking-normal font-normal">当前: {config.api_key_masked}</span>
              )}
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={config.api_key_masked ? '留空保持不变' : '输入 API 密钥'}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none focus:border-brand/40 focus:shadow-input"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-gray-400">
              Base URL <span className="font-normal normal-case tracking-normal">(可选)</span>
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={providers[provider]?.base_url || 'https://api.example.com/v1'}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none focus:border-brand/40 focus:shadow-input"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                <span>温度</span>
                <span className="text-brand font-bold text-xs normal-case">{temperature}</span>
              </label>
              <input
                type="range"
                min="0" max="1" step="0.1"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full"
              />
              <div className="mt-1 flex justify-between text-[10px] text-gray-400">
                <span>精确 0</span>
                <span>创意 1</span>
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                最大 Tokens
              </label>
              <input
                type="number"
                min={256} max={128000} step={256}
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value) || 4096)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none focus:border-brand/40 focus:shadow-input"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ━━━ 主页面 ━━━ */
export default function AgentConfig() {
  usePageTitle('智能体配置')
  const [configs, setConfigs] = useState<AgentModelConfig[]>([])
  const [providers, setProviders] = useState<ModelProviders>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [globalMessage, setGlobalMessage] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const [cfgs, provs] = await Promise.all([fetchAgentConfigs(), fetchModelProviders()])
      setConfigs(cfgs)
      setProviders(provs)
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleSave = async (agentId: string, updates: Record<string, unknown>) => {
    try {
      await updateAgentConfig(agentId, updates as any)
      const cfgs = await fetchAgentConfigs()
      setConfigs(cfgs)
      setGlobalMessage(`${agentId} 配置已保存`)
      setTimeout(() => setGlobalMessage(null), 3000)
    } catch (e) {
      setError((e as Error).message)
      throw e
    }
  }

  const groupOrder = ['control', 'design', 'architecture', 'implementation', 'verification']
  const groupLabels: Record<string, string> = {
    control: '🎯 指挥中心',
    design: '🎨 设计组',
    architecture: '🏗️ 架构组',
    implementation: '💻 开发组',
    verification: '🧪 验证组',
  }

  const groupedConfigs: Record<string, AgentModelConfig[]> = {}
  configs.forEach((cfg) => {
    const member = TEAM_MEMBERS.find((m) => m.id === cfg.agent_id)
    const group = member?.group || 'other'
    if (!groupedConfigs[group]) groupedConfigs[group] = []
    groupedConfigs[group].push(cfg)
  })

  if (loading) return <PageLoader text="加载配置..." />

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* 标题 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[28px] font-bold tracking-tight text-gray-900">智能体配置</h1>
          <p className="mt-1 text-[15px] text-gray-500">
            为每个 AI 智能体选择不同的模型提供商和参数
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={loadData}>
          刷新
        </Button>
      </div>

      {/* 全局提示 */}
      {globalMessage && (
        <div className="flex items-center gap-2 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-600">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {globalMessage}
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-red-100 bg-red-50 px-4 py-2.5 text-sm text-red-600">
          {error}
          <button onClick={() => setError(null)} className="ml-auto text-xs underline">关闭</button>
        </div>
      )}

      {/* 统计 */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { value: configs.length, label: '智能体', color: 'text-blue-600' },
          { value: configs.filter((c) => c.api_key_masked).length, label: '已配置', color: 'text-emerald-600' },
          { value: new Set(configs.map((c) => c.provider)).size, label: '提供商', color: 'text-purple-600' },
          { value: configs.filter((c) => c.enabled).length, label: '已启用', color: 'text-brand' },
        ].map((stat) => (
          <div key={stat.label} className="rounded-xl border border-gray-100 bg-white py-4 text-center shadow-card">
            <div className={clsx('text-[22px] font-bold', stat.color)}>{stat.value}</div>
            <div className="text-[11px] text-gray-400">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* 配置卡片 */}
      {groupOrder.map((group) => {
        const groupCfgs = groupedConfigs[group]
        if (!groupCfgs?.length) return null
        return (
          <div key={group}>
            <h2 className="mb-3 text-[13px] font-semibold text-gray-500">
              {groupLabels[group] || group}
            </h2>
            <div className="space-y-3">
              {groupCfgs.map((cfg) => (
                <AgentConfigCard key={cfg.agent_id} config={cfg} providers={providers} onSave={handleSave} />
              ))}
            </div>
          </div>
        )
      })}

      {/* 配置建议 */}
      <div className="rounded-xl border border-brand/20 bg-brand-50 p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
            </svg>
          </div>
          <div className="text-[12px] text-gray-500 leading-relaxed">
            <p className="mb-1.5 text-[13px] font-semibold text-gray-900">配置建议</p>
            <ul className="list-inside list-disc space-y-1 text-gray-400">
              <li><span className="text-gray-600">制作人/PM</span> — 推荐低温度 (0.2-0.3)，精确分类和管理</li>
              <li><span className="text-gray-600">策划/UX</span> — 推荐中高温度 (0.6-0.8)，需要创意和发散思维</li>
              <li><span className="text-gray-600">主程/程序</span> — 推荐低温度 (0.2-0.4)，代码需要精确性</li>
              <li><span className="text-gray-600">QA</span> — 推荐低温度 (0.2-0.3)，测试需要严谨</li>
              <li><span className="text-gray-600">美术</span> — 推荐高温度 (0.7-0.9)，视觉设计需要创意</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
