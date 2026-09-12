import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useOverviewStore } from '@/stores/useOverviewStore'
import { usePipelineStore } from '@/stores/usePipelineStore'
import { useAppStore } from '@/stores/useAppStore'
import { usePolling } from '@/hooks/usePolling'
import { usePageTitle } from '@/hooks/usePageTitle'
import { POLLING_INTERVAL, TEAM_MEMBERS, REQ_TYPES } from '@/utils/constants'
import { createPipeline, createPipelineWithFiles, deletePipeline, renamePipeline } from '@/api/pipelines'
import Badge from '@/components/ui/Badge'
import ProgressBar from '@/components/ui/ProgressBar'
import Avatar from '@/components/ui/Avatar'
import clsx from 'clsx'

const AVATAR_COLORS = ['blue', 'green', 'purple', 'orange', 'cyan', 'pink', 'indigo', 'blue'] as const

/* ── 状态颜色映射 ── */
const STATUS_MAP: Record<string, { label: string; color: 'green' | 'blue' | 'orange' | 'red' | 'gray'; dot: string }> = {
  completed: { label: '已完成', color: 'green', dot: 'bg-emerald-400' },
  running:   { label: '进行中', color: 'blue',  dot: 'bg-blue-400' },
  active:    { label: '进行中', color: 'blue',  dot: 'bg-blue-400' },
  failed:    { label: '失败',   color: 'red',   dot: 'bg-red-400' },
  pending:   { label: '等待中', color: 'gray',  dot: 'bg-gray-300' },
}

/* ── 时间格式化 ── */
function formatRelativeTime(dateStr?: string) {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return '刚刚'
    if (diffMin < 60) return `${diffMin} 分钟前`
    const diffHr = Math.floor(diffMin / 60)
    if (diffHr < 24) return `${diffHr} 小时前`
    const diffDay = Math.floor(diffHr / 24)
    if (diffDay < 7) return `${diffDay} 天前`
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch { return '' }
}

export default function Dashboard() {
  usePageTitle('OpenClaw — AI 游戏开发平台')
  const navigate = useNavigate()
  const { data, fetch: fetchOverview } = useOverviewStore()
  const { pipelines, fetch: fetchPipelines } = usePipelineStore()
  const { rightSidebarOpen, toggleRightSidebar } = useAppStore()

  const [input, setInput] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([])
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    fetchOverview()
    fetchPipelines()
  }, [fetchOverview, fetchPipelines])

  usePolling(() => { fetchOverview(); fetchPipelines() }, POLLING_INTERVAL)

  const handleSubmit = async () => {
    if (!input.trim() && uploadedFiles.length === 0) return
    if (submitting) return
    setSubmitting(true)
    setError(null)
    try {
      let result
      if (uploadedFiles.length > 0) {
        result = await createPipelineWithFiles({
          user_input: input.trim(),
          files: uploadedFiles,
        })
      } else {
        result = await createPipeline({ user_input: input.trim() })
      }
      setInput('')
      setUploadedFiles([])
      fetchPipelines()
      if (result?.pipeline_id) {
        navigate(`/projects/${result.pipeline_id}`)
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const allPipelines = Array.isArray(pipelines) ? pipelines : []

  const handleDeleteProject = async (pipelineId: string) => {
    try {
      await deletePipeline(pipelineId)
      await fetchPipelines()
    } catch (e) {
      console.error('删除项目失败:', e)
      alert('删除失败，请重试')
    }
  }

  const handleRenameProject = async (pipelineId: string, newName: string) => {
    try {
      await renamePipeline(pipelineId, newName)
      await fetchPipelines()
    } catch (e) {
      console.error('重命名项目失败:', e)
      alert('重命名失败，请重试')
    }
  }

  const filteredPipelines = searchQuery.trim()
    ? allPipelines.filter((p: any) =>
        (p.req_name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (p.req_type || '').toLowerCase().includes(searchQuery.toLowerCase())
      )
    : allPipelines

  const activePipelines = allPipelines.filter((p: any) => p.status !== 'completed' && p.status !== 'failed')
  const completedPipelines = allPipelines.filter((p: any) => p.status === 'completed')

  return (
    <div className="flex h-[calc(100vh-57px)]">
      {/* ═══════════════════════════════════════════════
          左侧 / 中央 — 主聊天区域
          ═══════════════════════════════════════════════ */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex flex-1 flex-col items-center overflow-y-auto px-6 pb-6">
          {/* ━━━ Hero 区域 ━━━ */}
          <div className="mt-10 flex flex-col items-center text-center lg:mt-16">
            {/* Agent 头像行 */}
            <div className="mb-7 flex items-center -space-x-2">
              {TEAM_MEMBERS.map((member, i) => (
                <div
                  key={member.id}
                  className="relative transition-transform hover:-translate-y-1 hover:z-10"
                  title={`${member.name} — ${member.role}`}
                >
                  <Avatar
                    icon={<span className="text-base">{member.icon}</span>}
                    size="md"
                    color={AVATAR_COLORS[i]}
                    className="ring-2 ring-white"
                  />
                </div>
              ))}
            </div>

            {/* 标题 */}
            <h1 className="text-[40px] font-bold leading-tight tracking-tight text-gray-900 lg:text-[48px]">
              将想法变成<br />
              <span className="italic text-brand">真正能玩的游戏</span>
            </h1>

            <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-gray-500">
              AI 团队自动验证想法、开发功能、测试质量。无需手动编码，几分钟内完成从策划到交付的完整流程。
            </p>
          </div>

          {/* ━━━ 聊天输入框 ━━━ */}
          <div
            className="mt-8 w-full max-w-2xl"
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              if (e.dataTransfer.files.length > 0) {
                setUploadedFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)])
              }
            }}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
          >
            {/* 拖拽覆盖提示 */}
            {dragOver && (
              <div className="mb-3 flex items-center justify-center rounded-xl border-2 border-dashed border-brand/40 bg-brand-50 py-8 animate-fade-in">
                <div className="text-center">
                  <span className="text-3xl">📎</span>
                  <p className="mt-1 text-sm font-medium text-brand">松开鼠标上传文件</p>
                  <p className="text-[11px] text-gray-400">支持 md, pdf, docx, zip 等格式，或整个文件夹</p>
                </div>
              </div>
            )}

            <div className={clsx(
              'relative rounded-2xl border bg-white shadow-card transition-all',
              dragOver ? 'border-brand/40 shadow-input' : error ? 'border-red-200' : 'border-gray-200 focus-within:border-brand/40 focus-within:shadow-input'
            )}>
              {/* 已上传文件预览 */}
              {uploadedFiles.length > 0 && (
                <div className="flex flex-wrap gap-2 px-5 pt-4 pb-0">
                  {uploadedFiles.map((file, i) => (
                    <div key={`${file.name}-${i}`} className="flex items-center gap-1.5 rounded-lg bg-gray-50 border border-gray-100 px-2.5 py-1.5 text-[12px] text-gray-600 animate-fade-in">
                      <span className="text-sm">
                        {file.name.endsWith('.pdf') ? '📕' : file.name.endsWith('.docx') || file.name.endsWith('.doc') ? '📘' : file.name.endsWith('.md') ? '📝' : file.name.endsWith('.zip') || file.name.endsWith('.rar') ? '📦' : '📄'}
                      </span>
                      <span className="max-w-[140px] truncate">{file.name}</span>
                      <span className="text-[10px] text-gray-300">{(file.size / 1024).toFixed(0)}KB</span>
                      <button
                        onClick={() => setUploadedFiles((prev) => prev.filter((_, j) => j !== i))}
                        className="flex h-4 w-4 items-center justify-center rounded-full hover:bg-gray-200 text-gray-400 hover:text-gray-600 transition-colors"
                      >
                        <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="描述你想要开发的游戏功能..."
                rows={3}
                className={clsx(
                  'w-full resize-none rounded-2xl bg-transparent px-5 pb-12 text-[15px] text-gray-900 placeholder-gray-400 outline-none',
                  uploadedFiles.length > 0 ? 'pt-3' : 'pt-4'
                )}
              />

              {/* 底部工具栏 */}
              <div className="absolute inset-x-0 bottom-0 flex items-center justify-between px-4 pb-3">
                <div className="flex items-center gap-1">
                  {/* 上传文件 — label 直接触发 input，无需 JS */}
                  <label
                    htmlFor="dashboard-file-input"
                    className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-50 hover:text-gray-600"
                    title="上传文件（md, pdf, docx, zip）"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
                    </svg>
                  </label>

                  {/* 上传文件夹 */}
                  <label
                    htmlFor="dashboard-folder-input"
                    className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-50 hover:text-gray-600"
                    title="上传文件夹（整个项目目录）"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
                    </svg>
                  </label>

                  <span className="ml-1 text-[12px] text-gray-300">
                    Enter 发送 · Shift+Enter 换行
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5 rounded-lg bg-gray-50 px-3 py-1.5 text-[12px] text-gray-500">
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
                    </svg>
                    AI 团队协作
                  </div>

                  <button
                    onClick={handleSubmit}
                    disabled={(!input.trim() && uploadedFiles.length === 0) || submitting}
                    className={clsx(
                      'flex h-8 w-8 items-center justify-center rounded-lg transition-all',
                      (input.trim() || uploadedFiles.length > 0) && !submitting
                        ? 'bg-brand text-white hover:bg-brand-dark'
                        : 'bg-gray-100 text-gray-300'
                    )}
                  >
                    {submitting ? (
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    ) : (
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            </div>

            {/* 隐藏的文件输入 */}
            <input
              id="dashboard-file-input"
              type="file"
              multiple
              accept=".md,.pdf,.docx,.doc,.txt,.zip,.rar,.png,.jpg,.svg"
              className="hidden"
              onChange={(e) => {
                if (e.target.files) setUploadedFiles((prev) => [...prev, ...Array.from(e.target.files!)])
                e.target.value = ''
              }}
            />
            <input
              id="dashboard-folder-input"
              type="file"
              // @ts-expect-error webkitdirectory is non-standard
              webkitdirectory=""
              className="hidden"
              onChange={(e) => {
                if (e.target.files) setUploadedFiles((prev) => [...prev, ...Array.from(e.target.files!)])
                e.target.value = ''
              }}
            />

            {error && (
              <p className="mt-2 text-sm text-red-500">{error}</p>
            )}

            {/* 快速操作标签 */}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
              {REQ_TYPES.slice(0, 5).map((type) => (
                <button
                  key={type.key}
                  onClick={() => {
                    setInput(`[${type.name}] `)
                    inputRef.current?.focus()
                  }}
                  className="flex items-center gap-1.5 rounded-full border border-gray-150 bg-white px-3 py-1.5 text-[12px] text-gray-500 transition-all hover:border-brand/30 hover:text-brand"
                >
                  <span>{type.icon}</span>
                  {type.name}
                </button>
              ))}
            </div>
          </div>

          {/* ━━━ 进行中项目卡片（聊天区内简要展示） ━━━ */}
          {activePipelines.length > 0 && (
            <div className="mt-12 w-full max-w-2xl">
              <h3 className="mb-3 text-[13px] font-semibold text-gray-400 uppercase tracking-wider">进行中</h3>
              <div className="grid gap-2">
                {activePipelines.slice(0, 3).map((p: any, i: number) => {
                  const stages = Array.isArray(p.stages) ? p.stages : []
                  const completedStages = stages.filter((s: any) => s.status === 'completed').length
                  const progress = stages.length > 0 ? Math.round((completedStages / stages.length) * 100) : 0
                  const currentAgent = stages.find((s: any) => s.status === 'active')
                  const agentDef = currentAgent ? TEAM_MEMBERS.find((a) => a.id === currentAgent.agent_id) : null

                  return (
                    <Link
                      key={p.pipeline_id || i}
                      to={`/projects/${p.pipeline_id || i}`}
                      className="group flex items-center gap-4 rounded-xl border border-gray-100 bg-white p-3.5 transition-all hover:shadow-card hover:border-gray-200"
                    >
                      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-500">
                        {agentDef ? <span className="text-base">{agentDef.icon}</span> : (
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
                          </svg>
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <h4 className="truncate text-[13px] font-medium text-gray-900 group-hover:text-brand transition-colors">
                          {p.req_name || `需求 ${p.req_id || ''}`}
                        </h4>
                        <div className="mt-0.5 flex items-center gap-2 text-[11px] text-gray-400">
                          {agentDef && <span>{agentDef.name} 处理中</span>}
                          <span>{progress}%</span>
                        </div>
                      </div>
                      <div className="w-20">
                        <ProgressBar value={progress} color="blue" size="sm" />
                      </div>
                    </Link>
                  )
                })}
              </div>
            </div>
          )}

          <div className="h-8 flex-shrink-0" />
        </div>
      </div>

      {/* ═══════════════════════════════════════════════
          右侧 — 项目历史侧栏 (GPT/Grok 风格)
          ═══════════════════════════════════════════════ */}
      <aside
        className={clsx(
          'flex flex-col border-l border-gray-100 bg-gray-50/50 transition-all duration-300 ease-in-out',
          rightSidebarOpen ? 'w-80' : 'w-0'
        )}
      >
        {rightSidebarOpen && (
          <div className="flex h-full w-80 flex-col overflow-hidden">
            {/* 侧栏头部 */}
            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
              <h2 className="text-[14px] font-semibold text-gray-900">项目历史</h2>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => navigate('/new')}
                  className="flex h-7 w-7 items-center justify-center rounded-md text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                  title="新建项目"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                  </svg>
                </button>
                <button
                  onClick={toggleRightSidebar}
                  className="flex h-7 w-7 items-center justify-center rounded-md text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                  title="收起侧栏"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 4.5l7.5 7.5-7.5 7.5m-6-15l7.5 7.5-7.5 7.5" />
                  </svg>
                </button>
              </div>
            </div>

            {/* 搜索框 */}
            <div className="px-3 pt-3 pb-2">
              <div className="relative">
                <svg className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                </svg>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="搜索项目..."
                  className="w-full rounded-lg border border-gray-200 bg-white py-1.5 pl-8 pr-3 text-[12px] text-gray-900 placeholder-gray-400 outline-none transition-colors focus:border-brand/40"
                />
              </div>
            </div>

            {/* 项目列表 */}
            <div className="flex-1 overflow-y-auto px-3 pb-3">
              {/* 进行中的项目 */}
              {activePipelines.length > 0 && (
                <div className="mb-4">
                  <div className="mb-1.5 flex items-center gap-1.5 px-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
                    <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">进行中 ({activePipelines.length})</span>
                  </div>
                  <div className="space-y-0.5">
                    {(searchQuery ? filteredPipelines.filter((p: any) => p.status !== 'completed' && p.status !== 'failed') : activePipelines).map((p: any, i: number) => (
                      <SidebarProjectItem key={p.pipeline_id || `active-${i}`} pipeline={p} onDelete={handleDeleteProject} onRename={handleRenameProject} />
                    ))}
                  </div>
                </div>
              )}

              {/* 全部项目 */}
              <div>
                <div className="mb-1.5 px-1">
                  <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
                    {searchQuery ? `搜索结果 (${filteredPipelines.length})` : `全部项目 (${allPipelines.length})`}
                  </span>
                </div>
                <div className="space-y-0.5">
                  {(searchQuery ? filteredPipelines : allPipelines).map((p: any, i: number) => (
                    <SidebarProjectItem key={p.pipeline_id || `all-${i}`} pipeline={p} onDelete={handleDeleteProject} onRename={handleRenameProject} />
                  ))}
                  {allPipelines.length === 0 && (
                    <div className="flex flex-col items-center py-8 text-center">
                      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-gray-100 text-xl">📂</div>
                      <p className="text-[12px] text-gray-400">暂无项目</p>
                      <p className="mt-1 text-[11px] text-gray-300">在左侧输入需求开始创建</p>
                    </div>
                  )}
                  {searchQuery && filteredPipelines.length === 0 && allPipelines.length > 0 && (
                    <div className="flex flex-col items-center py-6 text-center">
                      <p className="text-[12px] text-gray-400">未找到匹配的项目</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* 侧栏底部统计 */}
            <div className="border-t border-gray-100 px-4 py-3">
              <div className="flex items-center justify-between text-[11px] text-gray-400">
                <span>共 {allPipelines.length} 个项目</span>
                <span>{completedPipelines.length} 已完成</span>
              </div>
            </div>
          </div>
        )}
      </aside>

      {/* ═══ 侧栏展开按钮（折叠时显示） ═══ */}
      {!rightSidebarOpen && (
        <button
          onClick={toggleRightSidebar}
          className="fixed right-4 top-1/2 z-40 -translate-y-1/2 flex h-10 w-10 items-center justify-center rounded-xl border border-gray-200 bg-white text-gray-400 shadow-card transition-all hover:shadow-card-hover hover:text-gray-600"
          title="展开项目历史"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M18.75 19.5l-7.5-7.5 7.5-7.5m-6 15L5.25 12l7.5-7.5" />
          </svg>
        </button>
      )}
    </div>
  )
}

/* ══════════════════════════════════════
   侧栏项目条目组件 — atoms.dev 风格
   ══════════════════════════════════════ */
function SidebarProjectItem({
  pipeline,
  onDelete,
  onRename,
}: {
  pipeline: any
  onDelete?: (id: string) => void
  onRename?: (id: string, newName: string) => void
}) {
  const [showMenu, setShowMenu] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isRenaming, setIsRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState('')
  const isRenamingRef = useRef(false)  // 防止 blur + enter 双重触发
  const menuRef = useRef<HTMLDivElement>(null)
  const renameInputRef = useRef<HTMLInputElement>(null)
  const p = pipeline
  const stages = Array.isArray(p.stages) ? p.stages : []
  const completedStages = stages.filter((s: any) => s.status === 'completed').length
  const progress = stages.length > 0 ? Math.round((completedStages / stages.length) * 100) : 0
  const status = STATUS_MAP[p.status] || STATUS_MAP.pending
  const currentAgent = stages.find((s: any) => s.status === 'active')
  const agentDef = currentAgent ? TEAM_MEMBERS.find((a) => a.id === currentAgent.agent_id) : null
  const displayName = p.req_name || `需求 ${p.req_id || ''}`

  // 点击外部关闭菜单
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false)
      }
    }
    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showMenu])

  // 进入重命名模式时聚焦输入框
  useEffect(() => {
    if (isRenaming && renameInputRef.current) {
      renameInputRef.current.focus()
      renameInputRef.current.select()
    }
  }, [isRenaming])

  const handleMenuToggle = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setShowMenu(!showMenu)
  }

  const handleRenameClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setShowMenu(false)
    setRenameValue(displayName)
    isRenamingRef.current = true
    setIsRenaming(true)
  }

  const handleRenameConfirm = () => {
    // 防止 blur + keydown 双重触发
    if (!isRenamingRef.current) return
    isRenamingRef.current = false

    const trimmed = renameValue.trim()
    if (trimmed && trimmed !== displayName) {
      onRename?.(p.pipeline_id, trimmed)
    }
    setIsRenaming(false)
  }

  const handleRenameCancel = () => {
    isRenamingRef.current = false
    setIsRenaming(false)
  }

  const handleRenameKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleRenameConfirm()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      handleRenameCancel()
    }
  }

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setShowMenu(false)
    setShowDeleteConfirm(true)
  }

  const handleConfirmDelete = () => {
    onDelete?.(p.pipeline_id)
    setShowDeleteConfirm(false)
  }

  // 重命名模式 — 不包裹 Link，项目名变为 input
  if (isRenaming) {
    return (
      <div className="group relative flex items-start gap-3 rounded-lg px-2.5 py-2.5 bg-white shadow-sm border border-brand/30">
        {/* 状态指示点 */}
        <div className="mt-1.5 flex-shrink-0">
          <span className={clsx('block h-2 w-2 rounded-full', status.dot)} />
        </div>

        <div className="min-w-0 flex-1">
          <input
            ref={renameInputRef}
            type="text"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={handleRenameKeyDown}
            onBlur={handleRenameConfirm}
            className="w-full rounded-md border border-gray-200 bg-white px-2 py-1 text-[13px] font-medium text-gray-900 outline-none focus:border-brand/50 focus:ring-1 focus:ring-brand/20"
            placeholder="输入新名称..."
          />
          <div className="mt-1.5 flex items-center gap-2 text-[10px] text-gray-400">
            <span>Enter 确认 · Esc 取消</span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <>
      <Link
        to={`/projects/${p.pipeline_id}`}
        className="group relative flex items-start gap-3 rounded-lg px-2.5 py-2.5 transition-all hover:bg-white hover:shadow-sm"
      >
        {/* 状态指示点 */}
        <div className="mt-1.5 flex-shrink-0">
          <span className={clsx('block h-2 w-2 rounded-full', status.dot)} />
        </div>

        <div className="min-w-0 flex-1">
          <h4 className="truncate text-[13px] font-medium text-gray-800 group-hover:text-brand transition-colors pr-7">
            {displayName}
          </h4>
          <div className="mt-0.5 flex items-center gap-2">
            <Badge color={status.color} size="sm">{status.label}</Badge>
            {agentDef && (
              <span className="truncate text-[11px] text-gray-400">
                {agentDef.icon} {agentDef.name}
              </span>
            )}
          </div>
          {/* 进度条 */}
          {p.status !== 'completed' && p.status !== 'failed' && stages.length > 0 && (
            <div className="mt-1.5">
              <ProgressBar value={progress} color="blue" size="sm" />
            </div>
          )}
          {/* 时间 */}
          {p.created_at && (
            <span className="mt-1 block text-[10px] text-gray-300">{formatRelativeTime(p.created_at)}</span>
          )}
        </div>

        {/* ··· 更多按钮 — hover 时显示 */}
        <div ref={menuRef} className="absolute right-1.5 top-2">
          <button
            onClick={handleMenuToggle}
            className={clsx(
              'flex h-6 w-6 items-center justify-center rounded-md transition-all',
              showMenu
                ? 'bg-gray-100 text-gray-600 opacity-100'
                : 'text-gray-300 opacity-0 group-hover:opacity-100 hover:bg-gray-100 hover:text-gray-500'
            )}
          >
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <circle cx="12" cy="5" r="1.5" />
              <circle cx="12" cy="12" r="1.5" />
              <circle cx="12" cy="19" r="1.5" />
            </svg>
          </button>

          {/* 下拉菜单 */}
          {showMenu && (
            <div className="absolute right-0 top-7 z-30 w-36 rounded-lg border border-gray-100 bg-white py-1 shadow-float animate-fade-in">
              <button
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); setShowMenu(false) }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-[12px] text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <span className="text-sm text-gray-400">☆</span>
                收藏
              </button>
              <button
                onClick={handleRenameClick}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-[12px] text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <span className="text-sm text-gray-400">✏️</span>
                重命名
              </button>
              <div className="my-0.5 border-t border-gray-100" />
              <button
                onClick={handleDeleteClick}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-[12px] text-red-500 hover:bg-red-50 transition-colors"
              >
                <span className="text-sm">🗑️</span>
                删除
              </button>
            </div>
          )}
        </div>
      </Link>

      {/* ── 删除确认弹窗 ── */}
      {showDeleteConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm animate-fade-in"
          onClick={() => setShowDeleteConfirm(false)}
        >
          <div
            className="w-80 rounded-2xl border border-gray-100 bg-white p-6 shadow-float animate-fade-in-up"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex flex-col items-center text-center">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-red-50">
                <svg className="h-6 w-6 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                </svg>
              </div>
              <h3 className="text-[15px] font-semibold text-gray-900">删除项目</h3>
              <p className="mt-2 text-[13px] text-gray-500 leading-relaxed">
                确定要删除「{displayName}」吗？<br />
                删除后将无法恢复。
              </p>
            </div>
            <div className="mt-5 flex gap-2.5">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="flex-1 rounded-lg border border-gray-200 bg-white py-2 text-[13px] font-medium text-gray-600 transition-colors hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleConfirmDelete}
                className="flex-1 rounded-lg bg-red-500 py-2 text-[13px] font-medium text-white transition-colors hover:bg-red-600"
              >
                确定删除
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
