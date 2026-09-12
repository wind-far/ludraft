import { Outlet, useLocation } from 'react-router-dom'
import TopBar from './TopBar'

export default function AppLayout() {
  const location = useLocation()
  const isDashboard = location.pathname === '/dashboard' || location.pathname === '/'
  const isWorkspace = location.pathname.startsWith('/projects/')

  return (
    <div className="min-h-screen bg-white">
      <TopBar />

      {/* Dashboard 和 Workspace 使用全宽，其他页面居中 */}
      {isDashboard || isWorkspace ? (
        <main className="animate-fade-in" key={location.pathname}>
          <Outlet />
        </main>
      ) : (
        <main className="mx-auto max-w-6xl px-6 py-8">
          <div className="animate-fade-in" key={location.pathname}>
            <Outlet />
          </div>
        </main>
      )}
    </div>
  )
}
