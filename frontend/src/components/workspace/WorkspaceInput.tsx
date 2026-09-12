import { useState, useRef, useCallback } from 'react'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import clsx from 'clsx'

interface WorkspaceInputProps {
  onSendMessage: (text: string) => void
  onFileUpload: (files: FileList) => void
  onGitHubUrl: (url: string) => void
  pipelineStatus?: string
}

/**
 * 底部输入区 — 支持文本、文件上传、GitHub URL
 */
export default function WorkspaceInput({
  onSendMessage,
  onFileUpload,
  onGitHubUrl,
  pipelineStatus,
}: WorkspaceInputProps) {
  const { inputText, setInputText, isUploading } = useWorkspaceStore()
  const [dragOver, setDragOver] = useState(false)
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSubmit = useCallback(() => {
    const trimmed = inputText.trim()
    const hasFiles = pendingFiles.length > 0
    if (!trimmed && !hasFiles) return

    // 如果有待上传文件，先触发上传
    if (hasFiles) {
      const dt = new DataTransfer()
      for (const f of pendingFiles) dt.items.add(f)
      onFileUpload(dt.files)
      setPendingFiles([])
    }

    // 如果有文字，发送消息或 GitHub URL
    if (trimmed) {
      if (/^https?:\/\/(www\.)?github\.com\//.test(trimmed)) {
        onGitHubUrl(trimmed)
      } else {
        onSendMessage(trimmed)
      }
      setInputText('')
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    }
  }, [inputText, pendingFiles, onSendMessage, onFileUpload, onGitHubUrl, setInputText])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputText(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files.length > 0) {
      setPendingFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)])
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setPendingFiles((prev) => [...prev, ...Array.from(e.target.files!)])
    }
    e.target.value = ''
  }

  const removeFile = (index: number) => {
    setPendingFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const canSend = inputText.trim() || pendingFiles.length > 0

  return (
    <div
      className={clsx(
        'flex-shrink-0 border-t border-gray-100 bg-white p-4 transition-colors',
        dragOver && 'bg-brand-50 border-brand/30'
      )}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={() => setDragOver(false)}
    >
      {/* 拖拽提示 */}
      {dragOver && (
        <div className="mb-3 flex items-center justify-center rounded-xl border-2 border-dashed border-brand/40 bg-brand-50 py-6">
          <div className="text-center">
            <span className="text-2xl">📎</span>
            <p className="mt-1 text-sm font-medium text-brand">松开鼠标上传文件</p>
            <p className="text-[11px] text-gray-400">支持 md, pdf, docx, zip 等格式</p>
          </div>
        </div>
      )}

      {/* 已选文件预览标签 */}
      {pendingFiles.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {pendingFiles.map((file, i) => (
            <div
              key={`${file.name}-${i}`}
              className="flex items-center gap-1.5 rounded-lg bg-brand-50 border border-brand/20 px-2.5 py-1.5 text-[12px] text-brand-dark animate-fade-in"
            >
              <span className="text-sm">
                {file.name.endsWith('.pdf')
                  ? '📕'
                  : file.name.endsWith('.docx') || file.name.endsWith('.doc')
                    ? '📘'
                    : file.name.endsWith('.md')
                      ? '📝'
                      : file.name.endsWith('.zip') || file.name.endsWith('.rar')
                        ? '📦'
                        : '📄'}
              </span>
              <span className="max-w-[120px] truncate font-medium">{file.name}</span>
              <span className="text-[10px] text-brand/60">
                {file.size < 1024
                  ? `${file.size}B`
                  : file.size < 1048576
                    ? `${(file.size / 1024).toFixed(0)}KB`
                    : `${(file.size / 1048576).toFixed(1)}MB`}
              </span>
              <button
                onClick={() => removeFile(i)}
                className="flex h-4 w-4 items-center justify-center rounded-full hover:bg-brand/10 text-brand/60 hover:text-brand transition-colors"
              >
                <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="relative">
        <textarea
          ref={textareaRef}
          value={inputText}
          onChange={handleTextareaInput}
          onKeyDown={handleKeyDown}
          placeholder={
            pendingFiles.length > 0
              ? '可添加文字描述，按 Enter 上传...'
              : pipelineStatus === 'completed'
                ? '项目已完成，输入新需求继续升级开发...'
                : pipelineStatus === 'failed'
                  ? '项目出现问题，输入修改意见重新调整...'
                  : '输入新的想法或需求...（支持粘贴 GitHub URL）'
          }
          rows={1}
          className={clsx(
            'w-full resize-none rounded-xl border border-gray-200 bg-gray-50/50 px-4 py-3 pr-24 text-sm text-gray-900',
            'placeholder:text-gray-400 focus:border-brand/40 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand/10',
            'transition-all'
          )}
        />

        {/* 右侧按钮组 */}
        <div className="absolute bottom-2 right-2 flex items-center gap-1">
          {/* 上传文件 */}
          <label
            htmlFor="workspace-file-input"
            className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            title="上传文件（md, pdf, docx, zip）"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
            </svg>
          </label>

          {/* 上传文件夹 */}
          <label
            htmlFor="workspace-folder-input"
            className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            title="上传文件夹（整个项目目录）"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
            </svg>
          </label>

          {/* 发送按钮 */}
          <button
            onClick={handleSubmit}
            disabled={!canSend || isUploading}
            className={clsx(
              'flex h-8 w-8 items-center justify-center rounded-lg transition-all',
              canSend && !isUploading
                ? 'bg-brand text-white hover:bg-brand-dark shadow-sm'
                : 'bg-gray-100 text-gray-300'
            )}
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
            </svg>
          </button>
        </div>
      </div>

      {/* 隐藏的文件输入 */}
      <input
        id="workspace-file-input"
        ref={fileInputRef}
        type="file"
        multiple
        accept=".md,.pdf,.docx,.doc,.txt,.zip,.rar"
        className="hidden"
        onChange={handleFileSelect}
      />
      <input
        id="workspace-folder-input"
        ref={folderInputRef}
        type="file"
        // @ts-expect-error webkitdirectory is non-standard
        webkitdirectory=""
        className="hidden"
        onChange={handleFileSelect}
      />

      {/* 上传中指示 */}
      {isUploading && (
        <div className="mt-2 flex items-center gap-2 text-[12px] text-brand">
          <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          正在上传和解析文件...
        </div>
      )}
    </div>
  )
}
