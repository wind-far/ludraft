import { useEffect, useState } from 'react'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import type { FileNode } from '@/api/types'
import clsx from 'clsx'
import client from '@/api/client'
import type { ApiResponse } from '@/api/types'

interface FileExplorerProps {
  pipelineId: string
}

const FILE_ICONS: Record<string, string> = {
  ts: '🔷', tsx: '⚛️', js: '🟨', jsx: '⚛️',
  py: '🐍', cs: '🟪', json: '📋', md: '📝',
  yaml: '⚙️', yml: '⚙️', css: '🎨', html: '🌐',
  png: '🖼️', jpg: '🖼️', svg: '🖼️',
  txt: '📄', sh: '🖥️',
}

function getFileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || ''
  return FILE_ICONS[ext] || '📄'
}

function formatSize(bytes?: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** 递归渲染文件树节点 */
function FileTreeNode({ node, depth }: { node: FileNode; depth: number }) {
  const { expandedDirs, toggleDir, openFile, setActiveToolTab } = useWorkspaceStore()
  const isDir = node.type === 'directory'
  const isExpanded = expandedDirs.includes(node.path)

  const handleClick = () => {
    if (isDir) {
      toggleDir(node.path)
    } else {
      openFile(node.path)
      setActiveToolTab('editor')
    }
  }

  return (
    <div>
      <button
        onClick={handleClick}
        className={clsx(
          'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] transition-colors',
          'hover:bg-gray-100',
          isDir ? 'text-gray-700 font-medium' : 'text-gray-600'
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        {isDir ? (
          <>
            <svg
              className={clsx('h-3 w-3 text-gray-400 transition-transform', isExpanded && 'rotate-90')}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            <span className="text-sm">{isExpanded ? '📂' : '📁'}</span>
          </>
        ) : (
          <>
            <span className="w-3" />
            <span className="text-xs">{getFileIcon(node.name)}</span>
          </>
        )}
        <span className="flex-1 truncate font-mono">{node.name}</span>
        {!isDir && node.size && (
          <span className="text-[10px] text-gray-300">{formatSize(node.size)}</span>
        )}
      </button>

      {isDir && isExpanded && node.children && (
        <div>
          {node.children
            .sort((a, b) => {
              // 目录排在文件前面
              if (a.type !== b.type) return a.type === 'directory' ? -1 : 1
              return a.name.localeCompare(b.name)
            })
            .map((child) => (
              <FileTreeNode key={child.path} node={child} depth={depth + 1} />
            ))}
        </div>
      )}
    </div>
  )
}

/**
 * Tab4: 项目文件 — 文件树浏览器
 */
export default function FileExplorer({ pipelineId }: FileExplorerProps) {
  const { fileTree, setFileTree } = useWorkspaceStore()
  const [loading, setLoading] = useState(false)

  // 从后端 API 拉取真实文件树
  useEffect(() => {
    if (!pipelineId) return
    setLoading(true)
    client.get<ApiResponse<{ dirs: string[]; path: string }[]>>('/sandboxes')
      .then(({ data }) => {
        const sandboxes = Array.isArray(data.data) ? data.data : []
        if (sandboxes.length === 0) return

        // 将 dirs 列表转为 FileNode 树
        const nodes: FileNode[] = sandboxes.flatMap((sb) =>
          (sb.dirs || []).map((dir) => ({
            name: dir,
            path: `${sb.path}/${dir}`,
            type: 'directory' as const,
            children: [],
          }))
        )
        if (nodes.length > 0) setFileTree(nodes)
      })
      .catch(() => { /* 静默失败，降级为占位 */ })
      .finally(() => setLoading(false))
  }, [pipelineId, setFileTree])

  // 占位文件树（后端无数据时使用）
  const placeholderTree: FileNode[] = [
    {
      name: 'src',
      path: 'src',
      type: 'directory',
      children: [
        { name: 'GameScene.ts', path: 'src/GameScene.ts', type: 'file', size: 0, language: 'typescript' },
        { name: 'Player.ts', path: 'src/Player.ts', type: 'file', size: 0, language: 'typescript' },
      ],
    },
    { name: 'README.md', path: 'README.md', type: 'file', size: 0, language: 'markdown' },
  ]

  const displayTree = fileTree.length > 0 ? fileTree : placeholderTree

  const countFiles = (nodes: FileNode[]): number =>
    nodes.reduce((acc, node) => {
      if (node.type === 'file') return acc + 1
      return acc + (node.children ? countFiles(node.children) : 0)
    }, 0)

  return (
    <div className="flex h-full flex-col">
      {/* 头部信息 */}
      <div className="flex items-center justify-between border-b border-gray-100 bg-white px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-sm">📁</span>
          <span className="text-[12px] font-semibold text-gray-900">项目文件</span>
          <span className="text-[11px] text-gray-400">
            {loading ? '加载中...' : `${countFiles(displayTree)} 个文件`}
          </span>
        </div>
        <button
          onClick={() => {
            setLoading(true)
            client.get<ApiResponse<{ dirs: string[]; path: string }[]>>('/sandboxes')
              .then(({ data }) => {
                const sandboxes = Array.isArray(data.data) ? data.data : []
                const nodes: FileNode[] = sandboxes.flatMap((sb) =>
                  (sb.dirs || []).map((dir) => ({
                    name: dir,
                    path: `${sb.path}/${dir}`,
                    type: 'directory' as const,
                    children: [],
                  }))
                )
                if (nodes.length > 0) setFileTree(nodes)
              })
              .catch(() => {})
              .finally(() => setLoading(false))
          }}
          className="flex h-6 items-center gap-1 rounded px-2 text-[11px] text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
          title="刷新文件树"
        >
          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
          </svg>
          刷新
        </button>
      </div>

      {/* 文件树 */}
      <div className="flex-1 overflow-y-auto p-2">
        {displayTree.map((node) => (
          <FileTreeNode key={node.path} node={node} depth={0} />
        ))}
      </div>
    </div>
  )
}
