import type { Deliverable } from '@/api/types'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import clsx from 'clsx'

interface DeliverableCardProps {
  deliverable: Deliverable
}

const TYPE_CONFIG = {
  code: { icon: '💻', label: '代码', color: 'bg-blue-50 text-blue-700 border-blue-200' },
  document: { icon: '📄', label: '文档', color: 'bg-green-50 text-green-700 border-green-200' },
  design: { icon: '🎨', label: '设计', color: 'bg-purple-50 text-purple-700 border-purple-200' },
  test: { icon: '🧪', label: '测试', color: 'bg-cyan-50 text-cyan-700 border-cyan-200' },
  config: { icon: '⚙️', label: '配置', color: 'bg-orange-50 text-orange-700 border-orange-200' },
}

/**
 * 阶段交付物展示卡片
 */
export default function DeliverableCard({ deliverable }: DeliverableCardProps) {
  const { setActiveToolTab, openFile } = useWorkspaceStore()
  const cfg = TYPE_CONFIG[deliverable.type] || TYPE_CONFIG.code

  const handleViewFiles = () => {
    if (deliverable.files && deliverable.files.length > 0) {
      setActiveToolTab('files')
    }
  }

  const handleViewFile = (path: string) => {
    openFile(path)
    setActiveToolTab('editor')
  }

  return (
    <div className="ml-9 animate-fade-in">
      <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm hover:shadow-card transition-shadow">
        {/* 头部 */}
        <div className="flex items-center gap-2 mb-2">
          <span className={clsx('rounded-md border px-2 py-0.5 text-[11px] font-medium', cfg.color)}>
            {cfg.icon} {cfg.label}
          </span>
          <h4 className="text-[13px] font-semibold text-gray-900">{deliverable.title}</h4>
        </div>

        {/* 摘要 */}
        <p className="text-[12px] text-gray-500 leading-relaxed">{deliverable.summary}</p>

        {/* 代码预览 */}
        {deliverable.preview && (
          <pre className="mt-3 rounded-lg bg-gray-900 p-3 text-[11px] text-gray-300 font-mono overflow-x-auto max-h-32">
            <code>{deliverable.preview}</code>
          </pre>
        )}

        {/* 文件列表 */}
        {deliverable.files && deliverable.files.length > 0 && (
          <div className="mt-3 space-y-1">
            {deliverable.files.slice(0, 5).map((file) => (
              <button
                key={file}
                onClick={() => handleViewFile(file)}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12px] text-gray-600 hover:bg-gray-50 transition-colors group"
              >
                <svg className="h-3.5 w-3.5 text-gray-300 group-hover:text-brand" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
                <span className="font-mono truncate">{file}</span>
              </button>
            ))}
            {deliverable.files.length > 5 && (
              <button
                onClick={handleViewFiles}
                className="ml-2 text-[11px] text-brand hover:text-brand-dark font-medium transition-colors"
              >
                查看全部 {deliverable.files.length} 个文件 →
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
