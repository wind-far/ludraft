import clsx from 'clsx'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import type { ToolTabId } from '@/api/types'
import AppViewer from './AppViewer'
import ProjectOverview from './ProjectOverview'
import CodeEditor from './CodeEditor'
import FileExplorer from './FileExplorer'
import ActivityLog from './ActivityLog'

const TOOL_TABS: Array<{ id: ToolTabId; icon: string; label: string }> = [
  { id: 'viewer', icon: '▶️', label: '应用查看器' },
  { id: 'overview', icon: '📊', label: '项目概览' },
  { id: 'editor', icon: '📝', label: '编辑器' },
  { id: 'files', icon: '📁', label: '项目文件' },
  { id: 'activity', icon: '📋', label: '活动日志' },
]

interface ToolPanelProps {
  pipelineId: string
  stages: Array<{ name: string; status: string; agent_id: string }>
  progress: number
}

/**
 * 右侧工具面板 — 4 个 Tab 可切换
 */
export default function ToolPanel({ pipelineId, stages, progress }: ToolPanelProps) {
  const { activeToolTab, setActiveToolTab } = useWorkspaceStore()

  return (
    <div className="flex h-full flex-col bg-gray-50/50">
      {/* ━━━ Tab 栏 ━━━ */}
      <div className="flex items-center border-b border-gray-100 bg-white px-2">
        {TOOL_TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveToolTab(tab.id)}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-2.5 text-[12px] font-medium transition-colors relative',
              activeToolTab === tab.id
                ? 'text-gray-900'
                : 'text-gray-400 hover:text-gray-600'
            )}
          >
            <span className="text-sm">{tab.icon}</span>
            <span>{tab.label}</span>
            {activeToolTab === tab.id && (
              <span className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-brand" />
            )}
          </button>
        ))}
      </div>

      {/* ━━━ 面板内容 ━━━ */}
      <div className="flex-1 overflow-hidden">
        {activeToolTab === 'viewer' && <AppViewer pipelineId={pipelineId} />}
        {activeToolTab === 'overview' && (
          <ProjectOverview stages={stages} progress={progress} />
        )}
        {activeToolTab === 'editor' && <CodeEditor />}
        {activeToolTab === 'files' && <FileExplorer pipelineId={pipelineId} />}
        {activeToolTab === 'activity' && <ActivityLog pipelineId={pipelineId} />}
      </div>
    </div>
  )
}
