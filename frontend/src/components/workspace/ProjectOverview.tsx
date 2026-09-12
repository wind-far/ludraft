import { TEAM_MEMBERS } from '@/utils/constants'
import clsx from 'clsx'

interface ProjectOverviewProps {
  stages: Array<{ name: string; status: string; agent_id: string }>
  progress: number
}

const STATUS_MAP: Record<string, { label: string; color: string; bg: string }> = {
  completed: { label: '已完成', color: 'text-emerald-600', bg: 'bg-emerald-500' },
  active: { label: '进行中', color: 'text-brand', bg: 'bg-brand' },
  running: { label: '进行中', color: 'text-brand', bg: 'bg-brand' },
  failed: { label: '失败', color: 'text-red-500', bg: 'bg-red-500' },
  pending: { label: '等待中', color: 'text-gray-400', bg: 'bg-gray-300' },
}

/**
 * Tab2: 项目概览 — 进度统计、阶段时间线、Agent 工作量
 */
export default function ProjectOverview({ stages, progress }: ProjectOverviewProps) {
  const completedCount = stages.filter((s) => s.status === 'completed').length
  const activeCount = stages.filter((s) => s.status === 'active' || s.status === 'running').length
  const failedCount = stages.filter((s) => s.status === 'failed').length

  // 统计每个 Agent 参与的阶段数
  const agentWorkload = TEAM_MEMBERS.map((agent) => ({
    ...agent,
    stages: stages.filter((s) => s.agent_id === agent.id),
    completedStages: stages.filter((s) => s.agent_id === agent.id && s.status === 'completed').length,
  })).filter((a) => a.stages.length > 0)

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      {/* ━━━ 进度概览 ━━━ */}
      <div>
        <h3 className="text-sm font-semibold text-gray-900 mb-4">开发进度</h3>
        <div className="grid grid-cols-4 gap-3">
          <div className="rounded-xl bg-white border border-gray-100 p-4 text-center">
            <div className="text-2xl font-bold text-gray-900">{stages.length}</div>
            <div className="mt-1 text-[11px] text-gray-400">总阶段</div>
          </div>
          <div className="rounded-xl bg-white border border-gray-100 p-4 text-center">
            <div className="text-2xl font-bold text-emerald-600">{completedCount}</div>
            <div className="mt-1 text-[11px] text-gray-400">已完成</div>
          </div>
          <div className="rounded-xl bg-white border border-gray-100 p-4 text-center">
            <div className="text-2xl font-bold text-brand">{activeCount}</div>
            <div className="mt-1 text-[11px] text-gray-400">进行中</div>
          </div>
          <div className="rounded-xl bg-white border border-gray-100 p-4 text-center">
            <div className="text-2xl font-bold text-red-500">{failedCount}</div>
            <div className="mt-1 text-[11px] text-gray-400">失败</div>
          </div>
        </div>

        {/* 进度条 */}
        <div className="mt-4">
          <div className="flex justify-between text-[11px] text-gray-400 mb-1.5">
            <span>整体进度</span>
            <span className="font-semibold text-gray-600">{progress}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full rounded-full bg-brand transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      {/* ━━━ 阶段时间线 ━━━ */}
      <div>
        <h3 className="text-sm font-semibold text-gray-900 mb-4">阶段时间线</h3>
        <div className="space-y-0">
          {stages.map((stage, i) => {
            const agent = TEAM_MEMBERS.find((a) => a.id === stage.agent_id)
            const status = STATUS_MAP[stage.status] || STATUS_MAP.pending
            const isLast = i === stages.length - 1

            return (
              <div key={i} className="flex gap-3">
                {/* 时间线竖线 + 圆点 */}
                <div className="flex flex-col items-center">
                  <div className={clsx('h-3 w-3 rounded-full border-2 border-white shadow-sm', status.bg)} />
                  {!isLast && <div className="w-px flex-1 bg-gray-100 min-h-[2rem]" />}
                </div>

                {/* 阶段信息 */}
                <div className="flex-1 pb-4">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">{agent?.icon || '🤖'}</span>
                    <span className="text-[13px] font-medium text-gray-900">{stage.name}</span>
                    <span className={clsx('text-[11px] font-medium', status.color)}>
                      {status.label}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[11px] text-gray-400">
                    {agent?.name} · {agent?.role}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ━━━ Agent 工作量 ━━━ */}
      <div>
        <h3 className="text-sm font-semibold text-gray-900 mb-4">团队工作量</h3>
        <div className="space-y-3">
          {agentWorkload.map((agent) => (
            <div key={agent.id} className="flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gray-100 text-sm">
                {agent.icon}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-[12px] font-medium text-gray-900 truncate">{agent.name}</span>
                  <span className="text-[11px] text-gray-400">{agent.completedStages}/{agent.stages.length}</span>
                </div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                  <div
                    className="h-full rounded-full bg-brand/60 transition-all duration-500"
                    style={{
                      width: `${agent.stages.length > 0 ? (agent.completedStages / agent.stages.length) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
