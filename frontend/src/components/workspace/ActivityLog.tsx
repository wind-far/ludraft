import { useEffect, useState, useCallback } from 'react'
import { usePolling } from '@/hooks/usePolling'
import { POLLING_INTERVAL, TEAM_MEMBERS } from '@/utils/constants'
import Badge from '@/components/ui/Badge'
import { fetchPipelineLogs } from '@/api/logs'
import type { LogEntry } from '@/api/types'
import clsx from 'clsx'

const EVENT_ICONS: Record<string, string> = {
  pipeline_created: '🚀',
  pipeline_completed: '✅',
  pipeline_failed: '❌',
  pipeline_deleted: '🗑️',
  pipeline_renamed: '✏️',
  step_dispatch: '▶️',
  stage_started: '▶️',
  stage_completed: '✔️',
  quality_gate_passed: '🟢',
  quality_gate_failed: '🔴',
  bug_flow: '🐛',
  bug_max_rounds: '⚠️',
  requirement_received: '📩',
  requirement_initialized: '📋',
  setup: '⚙️',
  register_agent: '🤖',
}

const LEVEL_COLORS: Record<string, string> = {
  error: 'text-red-600',
  warning: 'text-amber-600',
  warn: 'text-amber-600',
  info: 'text-gray-600',
  debug: 'text-gray-400',
  success: 'text-emerald-600',
}

interface ActivityLogProps {
  pipelineId: string
}

/**
 * 项目活动日志面板 — 展示当前项目的所有活动记录
 */
export default function ActivityLog({ pipelineId }: ActivityLogProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [count, setCount] = useState(50)

  const load = useCallback(async () => {
    try {
      const data = await fetchPipelineLogs(pipelineId, count)
      if (Array.isArray(data)) setLogs(data)
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [pipelineId, count])

  useEffect(() => {
    setLoading(true)
    load()
  }, [pipelineId, count, load])

  usePolling(load, POLLING_INTERVAL)

  if (loading && logs.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-200 border-t-brand" />
          <span className="text-sm text-gray-400">加载活动日志...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 px-5 py-4 text-sm text-red-600">
          <span>❌</span>
          <span>加载失败: {error}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* ━━━ 控制栏 ━━━ */}
      <div className="flex items-center justify-between border-b border-gray-100 bg-white px-4 py-2.5">
        <div className="flex items-center gap-2 text-[12px] text-gray-500">
          <span className="text-sm">📋</span>
          <span>活动日志</span>
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600">
            {logs.length}
          </span>
        </div>
        <select
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
          className="rounded-md border border-gray-200 bg-white px-2 py-1 text-[11px] text-gray-600 outline-none transition-all focus:border-brand/40"
        >
          <option value={20}>最近 20 条</option>
          <option value={50}>最近 50 条</option>
          <option value={100}>最近 100 条</option>
        </select>
      </div>

      {/* ━━━ 日志列表 ━━━ */}
      <div className="flex-1 overflow-auto">
        {logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-gray-50 text-xl">📋</div>
            <p className="text-[13px] text-gray-400">该项目还没有活动记录</p>
            <p className="mt-1 text-[11px] text-gray-300">活动会在流水线执行时自动产生</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {logs.map((log, i) => {
              const level = (log.level ?? 'info').toLowerCase()
              const textColor = LEVEL_COLORS[level] ?? 'text-gray-600'
              const icon = EVENT_ICONS[log.event_type] ?? '💬'
              const agent = TEAM_MEMBERS.find((a) => log.message?.includes(a.name))

              return (
                <div
                  key={`${log.timestamp}-${i}`}
                  className="flex items-start gap-3 px-4 py-3 transition-colors hover:bg-gray-50/50"
                >
                  <span className="mt-0.5 text-[13px]">{icon}</span>
                  <div className="min-w-0 flex-1">
                    <div className={clsx('text-[12px] leading-relaxed', textColor)}>
                      {log.message}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-gray-400">
                      <span className="font-mono">
                        {log.timestamp?.substring(11, 19) || ''}
                      </span>
                      {log.event_type && (
                        <Badge color="gray" size="sm" variant="outline">
                          {log.event_type}
                        </Badge>
                      )}
                      {agent && (
                        <span className="flex items-center gap-1">
                          <span className="text-[10px]">{agent.icon}</span>
                          <span>{agent.name}</span>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
