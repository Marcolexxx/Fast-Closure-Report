import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { projects } from '../api'

export default function Dashboard() {
  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const loadProjects = () => {
    setLoading(true)
    projects.list()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadProjects() }, [])

  return (
    <div>
      <div className="page-header">
        <h1>工作台</h1>
        <button className="btn btn-primary" onClick={() => navigate('/projects/new')}>
          + 发起任务
        </button>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">总项目数</div>
          <div className="stat-value">{data.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">待审核</div>
          <div className="stat-value text-warn">
            {data.items.filter(p => p.status === 'pending_review').length}
          </div>
        </div>
      </div>

      <div className="card">
        {loading ? (
          <div className="flex justify-center p-8"><div className="spinner"></div></div>
        ) : data.items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📁</div>
            <h3>无进行中的项目</h3>
            <p>请点击右上角 发起任务 开始新工作流。</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>项目名称</th>
                <th>状态</th>
                <th>创建时间</th>
                <th>被驳回次数</th>
                <th>任务入口</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map(p => (
                <tr key={p.id} onClick={() => p.task_id ? navigate(`/tasks/${p.task_id}`) : null}>
                  <td className="font-bold">{p.name}</td>
                  <td><span className={`badge badge-${p.status}`}>{p.status.replace('_', ' ')}</span></td>
                  <td>{new Date(p.created_at).toLocaleString()}</td>
                  <td>{p.reject_count > 0 ? <span className="text-danger">{p.reject_count}</span> : '-'}</td>
                  <td>
                    {(p.status === 'pending_review' || p.status === 'approved') && (
                      <button className="btn btn-sm btn-ghost mr-8" onClick={(e) => { e.stopPropagation(); projects.downloadResult(p.id).catch(err => alert("下载失败: " + err.message))}}>下载报告</button>
                    )}
                    {p.task_id ? (
                      <span className="text-primary font-bold">查看任务 &rarr;</span>
                    ) : (
                      <span className="text-muted">草稿</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
