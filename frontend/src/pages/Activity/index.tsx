import { useEffect, useState } from 'react'
import { usePageTitle } from '@/hooks/usePageTitle'
import { usePolling } from '@/hooks/usePolling'
import { POLLING_INTERVAL, TEAM_MEMBERS } from '@/utils/constants'
import Badge from '@/components/ui/Badge'
import { PageLoader } from '@/components/ui/Spinner'
import { fetchLogs } from '@/api/logs'
import type { LogEntry } from '@/api/types'
import clsx from 'clsx'

const EVENT_ICONS: Record<string, string> = {
  pipeline_created: '🚀',
  pipeline_completed: '✅',
  pipeline_failed: '❌',
  stage_started: '▶️',
  stage_completed: '✔️',
}

const LEVEL_COLORS: Record<string, string> = {
  error: 'text-red-600',
  warning: 'text-amber-600',
  warn: 'text-amber-600',
  info: 'text-gray-600',
  debug: 'text-gray-400',
  success: 'text-emerald-600',
}

export default function Activity() {
  usePageTitle('活动日志')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [count, setCount] = useState(50)

  const load = async () => {
    try {
      const data = await fetchLogs(count)
      if (Array.isArray(data)) setLogs(data)
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [count])
  usePolling(load, POLLING_INTERVAL)

  if (loading && logs.length === 0) return <PageLoader text="加载活动日志..." />

  if (error) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 px-5 py-4 text-sm text-red-600">
        加载失败: {error}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 标题 */}
      <div>
        <h1 className="text-[28px] font-bold tracking-tight text-gray-900">活动日志</h1>
        <p className="mt-1 text-[15px] text-gray-500">追踪 AI 团队的所有工作动态</p>
      </div>

      {/* 控制栏 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded-full border border-gray-150 bg-white px-4 py-2 text-sm">
          <span className="text-gray-400">记录数</span>
          <span className="font-bold text-gray-900">{logs.length}</span>
        </div>
        <select
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 outline-none transition-all focus:border-brand/40 focus:shadow-input"
        >
          <option value={20}>最近 20 条</option>
          <option value={50}>最近 50 条</option>
          <option value={100}>最近 100 条</option>
        </select>
      </div>

      {/* 活动列表 */}
      <div className="rounded-2xl border border-gray-100 bg-white shadow-card overflow-hidden">
        {logs.length === 0 ? (
          <div className="flex flex-col items-center py-16">
            <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-gray-50 text-2xl">📋</div>
            <p className="text-sm text-gray-400">还没有活动记录</p>
          </div>
        ) : (
          <div className="max-h-[600px] overflow-auto divide-y divide-gray-50">
            {logs.map((log, i) => {
              const level = (log.level ?? 'info').toLowerCase()
              const textColor = LEVEL_COLORS[level] ?? 'text-gray-600'
              const icon = EVENT_ICONS[log.event_type] ?? '💬'
              const agent = TEAM_MEMBERS.find((a) => log.message?.includes(a.name))

              return (
                <div key={i} className="flex items-start gap-3 px-6 py-4 transition-colors hover:bg-gray-50/50">
                  <span className="mt-0.5 text-sm">{icon}</span>
                  <div className="min-w-0 flex-1">
                    <div className={clsx('text-[13px] leading-relaxed', textColor)}>
                      {log.message}
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-gray-400">
                      <span className="font-mono">
                        {log.timestamp?.substring(0, 19)?.replace('T', ' ') || ''}
                      </span>
                      {log.event_type && (
                        <Badge color="gray" size="sm" variant="outline">{log.event_type}</Badge>
                      )}
                      {agent && (
                        <span className="flex items-center gap-1">
                          <span className="text-xs">{agent.icon}</span>
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
