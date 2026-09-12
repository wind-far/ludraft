import { useState } from 'react'
import type { WorkspaceMessage } from '@/api/types'
import clsx from 'clsx'

interface AgentMessageCardProps {
  message: WorkspaceMessage
  agentName: string
  agentIcon: string
  agentRole: string
}

/**
 * Agent 消息卡片 — 含思考过程展开/折叠
 */
export default function AgentMessageCard({
  message,
  agentName,
  agentIcon,
  agentRole,
}: AgentMessageCardProps) {
  const [showThinking, setShowThinking] = useState(false)
  const hasThinking = message.thinking && message.thinking.length > 0
  const isStreaming = message.status === 'streaming'

  return (
    <div className="animate-fade-in">
      {/* Agent 头部 */}
      <div className="flex items-center gap-2 mb-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gray-100 text-sm">
          {agentIcon}
        </span>
        <span className="text-[13px] font-semibold text-gray-900">{agentName}</span>
        <span className="text-[11px] text-gray-400">{agentRole}</span>
        {isStreaming && (
          <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-brand">
            <span className="h-1 w-1 rounded-full bg-brand animate-pulse" />
            思考中
          </span>
        )}
      </div>

      {/* 思考过程（可折叠） */}
      {hasThinking && (
        <div className="ml-9 mb-2">
          <button
            onClick={() => setShowThinking(!showThinking)}
            className="flex items-center gap-1.5 text-[11px] text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg
              className={clsx('h-3 w-3 transition-transform', showThinking && 'rotate-90')}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            <span className="flex items-center gap-1">
              💭 思考过程
              <span className="text-gray-300">({message.thinking!.length} 步)</span>
            </span>
          </button>

          {showThinking && (
            <div className="mt-2 space-y-1.5 border-l-2 border-gray-100 pl-3 animate-fade-in">
              {message.thinking!.map((step) => (
                <div key={step.id} className="text-[12px] text-gray-500 leading-relaxed">
                  <span className="text-gray-300 mr-1.5">•</span>
                  {step.content}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 消息内容 */}
      <div className="ml-9 rounded-xl bg-gray-50 px-4 py-3">
        <div className="text-[13px] text-gray-700 leading-relaxed whitespace-pre-wrap">
          {message.content}
          {isStreaming && <span className="inline-block h-4 w-0.5 bg-brand animate-pulse ml-0.5" />}
        </div>
      </div>

      {/* 时间戳 */}
      <div className="ml-9 mt-1.5 text-[11px] text-gray-300">
        {new Date(message.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
      </div>
    </div>
  )
}
