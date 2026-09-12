import { Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import Dashboard from './pages/Dashboard'
import NewRequest from './pages/NewRequest'
import ProjectDetail from './pages/Projects/ProjectDetail'
import Team from './pages/Team'
import AgentDetail from './pages/Team/AgentDetail'
import AgentConfig from './pages/AgentConfig'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/new" element={<NewRequest />} />
        {/* /projects 重定向到首页（项目列表已集成到首页侧栏） */}
        <Route path="/projects" element={<Navigate to="/dashboard" replace />} />
        <Route path="/projects/:pipelineId" element={<ProjectDetail />} />
        <Route path="/team" element={<Team />} />
        <Route path="/team/:agentId" element={<AgentDetail />} />
        {/* Activity 已迁移到每个项目工作空间的 Tab 中 */}
        <Route path="/activity" element={<Navigate to="/dashboard" replace />} />
        <Route path="/agent-config" element={<AgentConfig />} />
      </Route>
    </Routes>
  )
}
