import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { usePipelineStore } from '@/stores/usePipelineStore'
import { usePolling } from '@/hooks/usePolling'
import { usePageTitle } from '@/hooks/usePageTitle'
import { POLLING_INTERVAL, TEAM_MEMBERS } from '@/utils/constants'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import ProgressBar from '@/components/ui/ProgressBar'
import { PageLoader } from '@/components/ui/Spinner'
import EmptyState from '@/components/ui/EmptyState'
import clsx from 'clsx'

const STATUS_MAP: Record<string, { label: string; color: 'blue' | 'green' | 'red' | 'yellow' | 'purple' }> = {
  pending:    { label: '等待中', color: 'yellow' },
  running:    { label: '进行中', color: 'blue' },
  active:     { label: '进行中', color: 'blue' },
  completed:  { label: '已完成', color: 'green' },
  failed:     { label: '失败',   color: 'red' },
  paused:     { label: '已暂停', color: 'purple' },
}

export default function Projects() {
  usePageTitle('我的项目')
  const navigate = useNavigate()
  const { pipelines, loading, error, fetch } = usePipelineStore()

  useEffect(() => { fetch() }, [fetch])
  usePolling(fetch, POLLING_INTERVAL)

  if (loading && (!pipelines || pipelines.length === 0)) {
    return <PageLoader text="加载项目列表..." />
  }

  if (error) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-red-100 bg-red-50 px-5 py-4 text-sm text-red-600">
        加载失败: {error}
      </div>
    )
  }

  const allPipelines = Array.isArray(pipelines) ? pipelines : []
  const runningCount = allPipelines.filter((p: any) => p.status === 'running' || p.status === 'active').length
  const completedCount = allPipelines.filter((p: any) => p.status === 'completed').length

  return (
    <div className="space-y-6">
      {/* 标题 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[28px] font-bold tracking-tight text-gray-900">我的项目</h1>
          <p className="mt-1 text-[15px] text-gray-500">跟踪你提交的所有需求和项目进度</p>
        </div>
        <Button
          variant="primary"
          onClick={() => navigate('/new')}
          icon={
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          }
        >
          新建需求
        </Button>
      </div>

      {/* 统计 */}
      <div className="flex flex-wrap gap-2">
        {[
          { label: '全部', value: allPipelines.length, color: 'text-gray-900' },
          { label: '进行中', value: runningCount, color: 'text-blue-600' },
          { label: '已完成', value: completedCount, color: 'text-emerald-600' },
        ].map((stat) => (
          <div key={stat.label} className="flex items-center gap-2 rounded-full border border-gray-150 bg-white px-4 py-2 text-sm">
            <span className="text-gray-400">{stat.label}</span>
            <span className={clsx('font-bold', stat.color)}>{stat.value}</span>
          </div>
        ))}
      </div>

      {/* 项目列表 */}
      {allPipelines.length === 0 ? (
        <EmptyState
          icon="📁"
          title="还没有项目"
          description="提交一个需求，开始你的 AI 辅助游戏开发之旅"
          action={{ label: '提交需求', onClick: () => navigate('/new') }}
        />
      ) : (
        <div className="space-y-2">
          {allPipelines.map((p: any, i: number) => {
            const stages = Array.isArray(p.stages) ? p.stages : []
            const completedStages = stages.filter((s: any) => s.status === 'completed').length
            const progress = stages.length > 0 ? Math.round((completedStages / stages.length) * 100) : 0
            const currentAgent = stages.find((s: any) => s.status === 'active')
            const agentDef = currentAgent ? TEAM_MEMBERS.find((a) => a.id === currentAgent.agent_id) : null
            const statusInfo = STATUS_MAP[p.status] || { label: p.status, color: 'blue' as const }

            return (
              <Link key={p.pipeline_id || i} to={`/projects/${p.pipeline_id || i}`} className="block">
                <div className="group flex items-start justify-between gap-4 rounded-xl border border-gray-100 bg-white p-5 shadow-card transition-all hover:shadow-card-hover">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2.5">
                      <h3 className="truncate text-[14px] font-semibold text-gray-900 group-hover:text-brand transition-colors">
                        {p.req_name || `需求 ${p.req_id || ''}`}
                      </h3>
                      <Badge color={statusInfo.color} size="sm" variant="dot">{statusInfo.label}</Badge>
                      <Badge color="gray" size="sm" variant="outline">{p.req_type}</Badge>
                    </div>

                    {agentDef && (
                      <div className="mt-2 flex items-center gap-2 text-[12px] text-gray-400">
                        <span className="text-base">{agentDef.icon}</span>
                        <span>{agentDef.name}</span>
                        <span className="text-gray-200">·</span>
                        <span>正在处理: {p.current_stage}</span>
                      </div>
                    )}

                    <div className="mt-3">
                      <ProgressBar
                        value={p.status === 'completed' ? 100 : progress}
                        color={p.status === 'completed' ? 'green' : p.status === 'failed' ? 'red' : 'blue'}
                        size="sm"
                      />
                      <div className="mt-1.5 flex items-center justify-between text-[11px] text-gray-400">
                        <span>{completedStages}/{stages.length} 阶段</span>
                        <span>{p.created_at?.substring(0, 16)?.replace('T', ' ')}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-col items-center pt-1">
                    <div className={clsx(
                      'text-xl font-bold',
                      p.status === 'completed' ? 'text-emerald-600' : 'text-blue-600'
                    )}>
                      {p.status === 'completed' ? (
                        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                        </svg>
                      ) : `${progress}%`}
                    </div>
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
