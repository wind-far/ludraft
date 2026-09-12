import { useRef, useEffect } from 'react'
import type { WorkspaceMessage } from '@/api/types'
import { TEAM_MEMBERS } from '@/utils/constants'
import AgentMessageCard from './AgentMessageCard'
import UserMessageCard from './UserMessageCard'
import DecisionGate from './DecisionGate'
import DeliverableCard from './DeliverableCard'
import WorkspaceInput from './WorkspaceInput'

interface ProcessPanelProps {
  messages: WorkspaceMessage[]
  pipelineName: string
  pipelineStatus: string
  onSendMessage: (text: string) => void
  onDecisionResponse: (decisionId: string, response: string) => void
  onFileUpload: (files: FileList) => void
  onGitHubUrl: (url: string) => void
}

/**
 * 左侧过程面板 — Agent 工作流全程可视化
 */
export default function ProcessPanel({
  messages,
  pipelineName,
  pipelineStatus,
  onSendMessage,
  onDecisionResponse,
  onFileUpload,
  onGitHubUrl,
}: ProcessPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  // 自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages.length])

  const isRunning = pipelineStatus === 'running' || pipelineStatus === 'active'

  return (
    <div className="flex h-full flex-col bg-white">
      {/* ━━━ 顶部项目信息 ━━━ */}
      <div className="flex-shrink-0 border-b border-gray-100 px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand/10 text-brand">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
            </svg>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-gray-900">{pipelineName}</h2>
            <div className="flex items-center gap-2 mt-0.5">
              {isRunning && (
                <span className="inline-flex items-center gap-1 text-[11px] text-brand font-medium">
                  <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
                  开发中
                </span>
              )}
              {pipelineStatus === 'completed' && (
                <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 font-medium">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  已完成
                </span>
              )}
              {pipelineStatus === 'failed' && (
                <span className="inline-flex items-center gap-1 text-[11px] text-red-500 font-medium">
                  <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
                  失败
                </span>
              )}
              {pipelineStatus === 'waiting_decision' && (
                <span className="inline-flex items-center gap-1 text-[11px] text-amber-600 font-medium">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
                  等待决策
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ━━━ 消息流 ━━━ */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4 space-y-4 scroll-smooth">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gray-50">
              <span className="text-3xl">🚀</span>
            </div>
            <h3 className="text-base font-semibold text-gray-900">开发流程即将启动</h3>
            <p className="mt-1.5 text-sm text-gray-400 max-w-xs">
              AI 团队正在准备中，工作进度将实时显示在这里
            </p>
          </div>
        )}

        {messages.map((msg) => {
          switch (msg.type) {
            case 'agent': {
              const agent = TEAM_MEMBERS.find((a) => a.id === msg.agent_id)
              return (
                <AgentMessageCard
                  key={msg.id}
                  message={msg}
                  agentName={agent?.name || '未知 Agent'}
                  agentIcon={agent?.icon || '🤖'}
                  agentRole={agent?.role || ''}
                />
              )
            }
            case 'user':
              return <UserMessageCard key={msg.id} message={msg} />
            case 'decision':
              return msg.decision ? (
                <DecisionGate
                  key={msg.id}
                  decision={msg.decision}
                  onResponse={onDecisionResponse}
                />
              ) : null
            case 'deliverable':
              return msg.deliverable ? (
                <DeliverableCard key={msg.id} deliverable={msg.deliverable} />
              ) : null
            case 'system':
              return (
                <div key={msg.id} className="flex justify-center">
                  <span
                    className={
                      msg.content.includes('✅')
                        ? 'rounded-xl bg-emerald-50 border border-emerald-100 px-4 py-2 text-[12px] text-emerald-600 font-medium'
                        : msg.content.includes('❌')
                          ? 'rounded-xl bg-red-50 border border-red-100 px-4 py-2 text-[12px] text-red-500 font-medium'
                          : msg.content.includes('📎') || msg.content.includes('上传')
                            ? 'rounded-xl bg-brand-50 border border-brand/20 px-4 py-2 text-[12px] text-brand font-medium'
                            : 'rounded-full bg-gray-50 px-4 py-1.5 text-[12px] text-gray-400'
                    }
                  >
                    {msg.content}
                  </span>
                </div>
              )
            default:
              return null
          }
        })}

        {/* 正在运行的 Agent 指示 */}
        {isRunning && messages.length > 0 && (
          <div className="flex items-center gap-2 py-2">
            <div className="flex gap-1">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
            <span className="text-[12px] text-gray-400">Agent 正在工作中...</span>
          </div>
        )}
      </div>

      {/* ━━━ 底部输入区 ━━━ */}
      <WorkspaceInput
        onSendMessage={onSendMessage}
        onFileUpload={onFileUpload}
        onGitHubUrl={onGitHubUrl}
        pipelineStatus={pipelineStatus}
      />
    </div>
  )
}
