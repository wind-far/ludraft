import type { WorkspaceMessage } from '@/api/types'

interface UserMessageCardProps {
  message: WorkspaceMessage
}

/**
 * 用户消息气泡 — 右对齐显示
 */
export default function UserMessageCard({ message }: UserMessageCardProps) {
  return (
    <div className="flex justify-end animate-fade-in">
      <div className="max-w-[80%]">
        {/* 消息气泡 */}
        <div className="rounded-xl bg-brand px-4 py-3 text-white">
          <div className="text-[13px] leading-relaxed whitespace-pre-wrap">
            {message.content}
          </div>
        </div>

        {/* 时间戳 */}
        <div className="mt-1.5 text-right text-[11px] text-gray-300">
          {new Date(message.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  )
}
