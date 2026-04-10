import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import AgentStatusBar from '../components/AgentStatusBar'

export default function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  // Track active task from sessionStorage (set by TaskExecutor/NewProject pages)
  const [activeTaskId, setActiveTaskId] = useState(() => sessionStorage.getItem('active_task_id') || null)

  // Listen for task changes across the app
  useEffect(() => {
    const handler = () => setActiveTaskId(sessionStorage.getItem('active_task_id') || null)
    window.addEventListener('active_task_changed', handler)
    return () => window.removeEventListener('active_task_changed', handler)
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="app-shell">
      {/* Global Agent Status Capsule — PRD §4.3 */}
      <AgentStatusBar taskId={activeTaskId} />

      {/* Topbar */}
      <header className="app-topbar">
        <div className="topbar-logo">
          <div className="topbar-logo-icon">C</div>
          <span>AI 办公助理</span>
        </div>
        <div className="topbar-spacer" />
        <div className="topbar-user" onClick={handleLogout} title="点击退出登录">
          <div className="topbar-avatar">{user?.username?.[0]?.toUpperCase()}</div>
          <span>{user?.username}</span>
        </div>
      </header>

      {/* Sidebar */}
      <aside className="app-sidebar">
        <div className="nav-section-label">日常操作</div>
        <NavLink to="/" end className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span>工作台</span>
        </NavLink>
        <NavLink to="/projects/new" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span>发起任务</span>
        </NavLink>
        
        {user?.role === 'admin' && (
          <>
            <div className="nav-section-label" style={{ marginTop: 16 }}>系统管理</div>
            <NavLink to="/admin" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <span>技能管理</span>
            </NavLink>
            <NavLink to="/experience" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
              <span>经验反馈网</span>
            </NavLink>
          </>
        )}
      </aside>

      {/* Main Content */}
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  )
}
