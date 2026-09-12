import { useState } from 'react'
import type { DecisionGateData } from '@/api/types'
import { TEAM_MEMBERS } from '@/utils/constants'
import clsx from 'clsx'

interface DecisionGateProps {
  decision: DecisionGateData
  onResponse: (decisionId: string, response: string) => void
}

/**
 * 决策门禁卡片 — 人机协同审批
 */
export default function DecisionGate({ decision, onResponse }: DecisionGateProps) {
  const [comment, setComment] = useState('')
  const agent = TEAM_MEMBERS.find((a) => a.id === decision.agent_id)
  const isPending = decision.status === 'pending'

  const handleResponse = (key: string) => {
    onResponse(decision.id, key === 'comment' ? comment : key)
  }

  return (
    <div className="animate-fade-in">
      {/* 系统分割线 */}
      <div className="flex items-center gap-3 my-2">
        <div className="flex-1 border-t border-amber-200" />
        <span className="text-[11px] font-medium text-amber-600 flex items-center gap-1">
          ⚡ 需要您的决策
        </span>
        <div className="flex-1 border-t border-amber-200" />
      </div>

      {/* 审批卡片 */}
      <div className={clsx(
        'rounded-xl border-2 p-5 transition-all',
        isPending
          ? 'border-amber-200 bg-amber-50/50 shadow-sm'
          : decision.status === 'approved'
            ? 'border-emerald-200 bg-emerald-50/30'
            : 'border-red-200 bg-red-50/30'
      )}>
        {/* 头部 */}
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white shadow-sm text-lg">
            {agent?.icon || '🤖'}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-gray-900">{agent?.name || '系统'}</span>
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700">
                {decision.stage}
              </span>
            </div>
            <h4 className="mt-1 text-[14px] font-semibold text-gray-900">{decision.title}</h4>
            <p className="mt-1.5 text-[13px] text-gray-600 leading-relaxed">{decision.description}</p>
          </div>
        </div>

        {/* 操作按钮 */}
        {isPending ? (
          <div className="mt-4 space-y-3">
            {/* 预设选项 */}
            <div className="flex gap-2">
              {decision.options.map((opt) => (
                <button
                  key={opt.key}
                  onClick={() => handleResponse(opt.key)}
                  className={clsx(
                    'flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-medium transition-all',
                    opt.key === 'approve'
                      ? 'bg-emerald-500 text-white hover:bg-emerald-600 shadow-sm'
                      : opt.key === 'reject'
                        ? 'bg-white text-red-600 border border-red-200 hover:bg-red-50'
                        : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50'
                  )}
                >
                  <span>{opt.icon}</span>
                  {opt.label}
                </button>
              ))}
            </div>

            {/* 追加意见 */}
            <div className="flex gap-2">
              <input
                type="text"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="添加意见或修改建议..."
                className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-[12px] text-gray-700 placeholder:text-gray-400 focus:border-brand/40 focus:outline-none focus:ring-2 focus:ring-brand/10"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && comment.trim()) {
                    handleResponse('comment')
                  }
                }}
              />
              {comment.trim() && (
                <button
                  onClick={() => handleResponse('comment')}
                  className="rounded-lg bg-brand px-3 py-2 text-[12px] font-medium text-white hover:bg-brand-dark transition-colors"
                >
                  发送
                </button>
              )}
            </div>
          </div>
        ) : (
          /* 已决策状态 */
          <div className="mt-3 flex items-center gap-2 text-[12px]">
            <span className={clsx(
              'rounded-full px-2.5 py-0.5 font-medium',
              decision.status === 'approved'
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-red-100 text-red-700'
            )}>
              {decision.status === 'approved' ? '✅ 已通过' : '❌ 已拒绝'}
            </span>
            {decision.user_response && (
              <span className="text-gray-500">— {decision.user_response}</span>
            )}
            {decision.responded_at && (
              <span className="ml-auto text-gray-300">
                {new Date(decision.responded_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
