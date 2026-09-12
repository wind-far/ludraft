interface AppViewerProps {
  pipelineId: string
}

/**
 * Tab1: 应用查看器 — iframe 预览运行中的应用
 */
export default function AppViewer({ pipelineId }: AppViewerProps) {
  // 实际应用中，这里会连接到沙盒服务获取预览 URL
  const previewUrl = null // TODO: 从沙盒 API 获取

  return (
    <div className="flex h-full flex-col">
      {/* 地址栏 */}
      <div className="flex items-center gap-2 border-b border-gray-100 bg-white px-4 py-2">
        <div className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-red-300" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber-300" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-300" />
        </div>
        <div className="flex-1 rounded-md bg-gray-50 px-3 py-1 text-[12px] text-gray-400 font-mono">
          {previewUrl || `localhost:3000 — ${pipelineId}`}
        </div>
        <button
          className="flex h-6 w-6 items-center justify-center rounded text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
          title="刷新"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
          </svg>
        </button>
      </div>

      {/* 预览区域 */}
      <div className="flex-1 bg-white">
        {previewUrl ? (
          <iframe
            src={previewUrl}
            className="h-full w-full border-0"
            title="应用预览"
            sandbox="allow-scripts allow-same-origin allow-forms"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center text-center p-8">
            <div className="mb-4 flex h-20 w-20 items-center justify-center rounded-2xl bg-gray-50">
              <span className="text-4xl">🖥️</span>
            </div>
            <h3 className="text-base font-semibold text-gray-900">应用查看器</h3>
            <p className="mt-2 text-sm text-gray-400 max-w-sm leading-relaxed">
              当 Agent 完成代码编写后，应用将自动构建并在此预览。
              您可以实时查看开发进度和运行效果。
            </p>
            <div className="mt-6 flex items-center gap-3">
              <div className="flex items-center gap-1.5 rounded-lg bg-gray-50 px-3 py-2 text-[12px] text-gray-500">
                <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
                等待构建中...
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
