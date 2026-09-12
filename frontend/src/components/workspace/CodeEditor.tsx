import { useEffect, useState } from 'react'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import clsx from 'clsx'
import client from '@/api/client'
import type { ApiResponse } from '@/api/types'

const LANG_ICONS: Record<string, string> = {
  ts: '🔷', tsx: '⚛️', js: '🟨', jsx: '⚛️',
  py: '🐍', cs: '🟪', json: '📋', md: '📝',
  yaml: '⚙️', yml: '⚙️', css: '🎨', html: '🌐',
  txt: '📄', sh: '🖥️', default: '📄',
}

function getExtension(filename: string): string {
  const parts = filename.split('.')
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : ''
}

function getLangIcon(filename: string): string {
  const ext = getExtension(filename)
  return LANG_ICONS[ext] || LANG_ICONS.default
}

/**
 * Tab3: 代码编辑器 — 查看/编辑 Agent 生成的代码
 */
export default function CodeEditor() {
  const { openFiles, activeFile, setActiveFile, closeFile } = useWorkspaceStore()
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [loadingFile, setLoadingFile] = useState(false)

  // 切换文件时从后端加载内容
  useEffect(() => {
    if (!activeFile) {
      setFileContent(null)
      return
    }
    setLoadingFile(true)
    // 尝试从 agent-rules API 获取文件内容（规则文件）
    // 或从沙盒文件 API 获取代码文件
    const agentId = activeFile.split('/')[0]
    client.get<ApiResponse<{ entry_content: string }>>(`/agents/${agentId}/rules`)
      .then(({ data }) => {
        if (data.data?.entry_content) {
          setFileContent(data.data.entry_content)
        } else {
          setFileContent(`// ${activeFile}\n// 文件内容加载中...`)
        }
      })
      .catch(() => {
        setFileContent(`// ${activeFile}\n// 无法加载文件内容，请检查沙盒环境`)
      })
      .finally(() => setLoadingFile(false))
  }, [activeFile])

  return (
    <div className="flex h-full flex-col">
      {/* ━━━ 文件标签栏 ━━━ */}
      {openFiles.length > 0 && (
        <div className="flex items-center border-b border-gray-100 bg-white overflow-x-auto">
          {openFiles.map((file) => {
            const fileName = file.split('/').pop() || file
            const isActive = file === activeFile

            return (
              <div
                key={file}
                className={clsx(
                  'group flex items-center gap-1.5 border-r border-gray-100 px-3 py-2 text-[12px] cursor-pointer transition-colors',
                  isActive
                    ? 'bg-white text-gray-900 border-b-2 border-b-brand'
                    : 'bg-gray-50/50 text-gray-500 hover:bg-gray-50'
                )}
                onClick={() => setActiveFile(file)}
              >
                <span className="text-xs">{getLangIcon(fileName)}</span>
                <span className="font-mono truncate max-w-[120px]">{fileName}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    closeFile(file)
                  }}
                  className="ml-1 flex h-4 w-4 items-center justify-center rounded opacity-0 group-hover:opacity-100 hover:bg-gray-200 transition-all"
                >
                  <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* ━━━ 编辑器区域 ━━━ */}
      <div className="flex-1 overflow-auto">
        {activeFile && fileContent ? (
          <div className="p-4">
            {/* 文件路径 */}
            <div className="mb-3 flex items-center gap-1.5 text-[11px] text-gray-400">
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
              <span className="font-mono">{activeFile}</span>
            </div>

            {/* 代码区域 */}
            <pre className="rounded-xl bg-gray-900 p-4 text-[12px] text-gray-300 font-mono leading-relaxed overflow-x-auto">
              {fileContent.split('\n').map((line, i) => (
                <div key={i} className="flex">
                  <span className="inline-block w-8 text-right mr-4 text-gray-600 select-none">{i + 1}</span>
                  <code>{line}</code>
                </div>
              ))}
            </pre>
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center text-center p-8">
            <div className="mb-4 flex h-20 w-20 items-center justify-center rounded-2xl bg-gray-50">
              <span className="text-4xl">📝</span>
            </div>
            <h3 className="text-base font-semibold text-gray-900">代码编辑器</h3>
            <p className="mt-2 text-sm text-gray-400 max-w-sm leading-relaxed">
              在左侧的交付物或项目文件中点击文件名，即可在此查看和编辑代码。
              后续版本将集成完整的 Monaco Editor。
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
