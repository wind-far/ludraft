import { NavLink, useLocation, useParams } from 'react-router-dom'
import { useAppStore } from '@/stores/useAppStore'
import { useWorkspaceStore } from '@/stores/useWorkspaceStore'
import type { ToolTabId } from '@/api/types'
import clsx from 'clsx'

const TOOL_TAB_ICONS: Array<{ id: ToolTabId; icon: string; label: string }> = [
  { id: 'viewer', icon: '▶️', label: '应用查看器' },
  { id: 'overview', icon: '📊', label: '项目概览' },
  { id: 'editor', icon: '📝', label: '编辑器' },
  { id: 'files', icon: '📁', label: '项目文件' },
  { id: 'activity', icon: '📋', label: '活动日志' },
]

export default function TopBar() {
  const { rightSidebarOpen, toggleRightSidebar } = useAppStore()
  const { activeToolTab, setActiveToolTab, toolPanelOpen, toggleToolPanel } = useWorkspaceStore()
  const location = useLocation()
  const isDashboard = location.pathname === '/dashboard' || location.pathname === '/'
  const isWorkspace = location.pathname.startsWith('/projects/')

  return (
    <header className="sticky top-0 z-50 border-b border-gray-100 bg-white/80 backdrop-blur-lg">
      <div
        className="mx-auto flex h-14 items-center justify-between px-6"
        style={{ maxWidth: isDashboard || isWorkspace ? 'none' : '72rem' }}
      >
        {/* ━━━ Logo ━━━ */}
        <div className="flex items-center gap-4">
          <NavLink to="/" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-white">
              <svg className="h-4.5 w-4.5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
              </svg>
            </div>
            <span className="text-[15px] font-bold text-gray-900 tracking-tight">OpenClaw</span>
          </NavLink>

          {/* 工作空间模式 — 返回按钮 */}
          {isWorkspace && (
            <div className="flex items-center gap-2 ml-2">
              <NavLink
                to="/dashboard"
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-[12px] text-gray-400 hover:bg-gray-50 hover:text-gray-600 transition-colors"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
                </svg>
                返回
              </NavLink>
              <span className="text-gray-200">|</span>
              <span className="text-[12px] text-gray-500">工作空间</span>
            </div>
          )}
        </div>

        {/* ━━━ 导航 / 工作空间工具栏 ━━━ */}
        {isWorkspace ? (
          /* 工作空间模式 — 工具面板 Tab 切换按钮组 */
          <div className="flex items-center gap-1 rounded-lg bg-gray-50 p-1">
            {TOOL_TAB_ICONS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  if (!toolPanelOpen) toggleToolPanel()
                  setActiveToolTab(tab.id)
                }}
                className={clsx(
                  'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium transition-all',
                  activeToolTab === tab.id && toolPanelOpen
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-400 hover:text-gray-600'
                )}
                title={tab.label}
              >
                <span className="text-sm">{tab.icon}</span>
                <span className="hidden md:inline">{tab.label}</span>
              </button>
            ))}
          </div>
        ) : (
          /* 普通模式 — 导航菜单 */
          <nav className="flex items-center gap-1">
            {[
              { to: '/dashboard', label: '首页' },
              { to: '/team', label: '团队' },
              { to: '/agent-config', label: '设置' },
            ].map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  clsx(
                    'rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors',
                    isActive
                      ? 'bg-gray-100 text-gray-900'
                      : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        )}

        {/* ━━━ 右侧 ━━━ */}
        <div className="flex items-center gap-2">
          {/* 工作空间模式 — 面板折叠切换 */}
          {isWorkspace && (
            <button
              onClick={toggleToolPanel}
              className={clsx(
                'flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[12px] font-medium transition-colors',
                toolPanelOpen
                  ? 'bg-brand-50 text-brand'
                  : 'text-gray-400 hover:bg-gray-50 hover:text-gray-600'
              )}
              title={toolPanelOpen ? '收起工具面板' : '展开工具面板'}
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 4.5v15m6-15v15m-10.875 0h15.75c.621 0 1.125-.504 1.125-1.125V5.625c0-.621-.504-1.125-1.125-1.125H4.125C3.504 4.5 3 5.004 3 5.625v12.75c0 .621.504 1.125 1.125 1.125z" />
              </svg>
              <span className="hidden sm:inline">{toolPanelOpen ? '收起' : '展开'}</span>
            </button>
          )}

          {/* 首页模式 — 项目历史侧栏切换 */}
          {isDashboard && (
            <button
              onClick={toggleRightSidebar}
              className={clsx(
                'flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[12px] font-medium transition-colors',
                rightSidebarOpen
                  ? 'bg-brand-50 text-brand'
                  : 'text-gray-400 hover:bg-gray-50 hover:text-gray-600'
              )}
              title={rightSidebarOpen ? '收起项目历史' : '展开项目历史'}
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25H12" />
              </svg>
              <span className="hidden sm:inline">项目</span>
            </button>
          )}

          {/* 通知 */}
          <button className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-50 hover:text-gray-600" title="通知">
            <svg className="h-[18px] w-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
            </svg>
          </button>

          {/* 用户头像 */}
          <div className="h-8 w-8 rounded-full bg-brand flex items-center justify-center text-[11px] font-bold text-white cursor-pointer">
            U
          </div>
        </div>
      </div>
    </header>
  )
}
