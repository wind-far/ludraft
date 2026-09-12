import { type ReactNode } from 'react'
import clsx from 'clsx'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'

interface WorkspaceLayoutProps {
  left: ReactNode
  right: ReactNode
}

/**
 * 工作空间左右分割布局
 * 左侧: 过程面板 (ProcessPanel)
 * 右侧: 工具面板 (ToolPanel) — 可折叠
 */
export default function WorkspaceLayout({ left, right }: WorkspaceLayoutProps) {
  const { toolPanelOpen } = useWorkspaceStore()

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* ━━━ 左侧过程面板 ━━━ */}
      <div
        className={clsx(
          'flex flex-col transition-all duration-300 ease-in-out',
          toolPanelOpen ? 'w-[45%] min-w-[400px]' : 'w-full'
        )}
      >
        {left}
      </div>

      {/* ━━━ 右侧工具面板 ━━━ */}
      <div
        className={clsx(
          'flex-1 border-l border-gray-100 transition-all duration-300 ease-in-out overflow-hidden',
          toolPanelOpen ? 'w-[55%] min-w-[420px] opacity-100' : 'w-0 min-w-0 opacity-0 border-l-0'
        )}
      >
        {right}
      </div>
    </div>
  )
}
