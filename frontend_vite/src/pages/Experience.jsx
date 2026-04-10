import { useState, useEffect } from 'react'
import { feedback } from '../api'

export default function Experience() {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchMetrics()
  }, [])

  const fetchMetrics = async () => {
    try {
      setLoading(true)
      const data = await feedback.metrics()
      if (data) {
        setMetrics(data)
      }
    } catch (err) {
      console.error(err)
      alert("加载经验层指标失败")
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="p-8">正在加载元学习数据...</div>
  }

  return (
    <div className="p-8 fade-in">
      <h1 className="text-2xl font-bold mb-6">经验反馈网 (Experience Layer)</h1>
      <p className="text-gray-400 mb-8">
        聚合从 Human-in-the-Loop (人工介入修正) 中收集到的机器预测偏差。
        可利用此数据表为模型微调 (Prompt refinements / Skill training) 排序优先级。
      </p>

      {metrics && (
        <div className="metrics-grid">
          <div className="card stat-card">
            <div className="stat-value">{metrics.total_events || 0}</div>
            <div className="stat-label">历史捕获的人工修正总数</div>
          </div>
        </div>
      )}

      {metrics && metrics.distribution && Object.keys(metrics.distribution).length > 0 && (
        <div className="data-table-container mt-8">
          <h2 className="text-lg font-semibold mb-4 text-text">修正指标分布图</h2>
          <table className="data-table">
            <thead>
              <tr>
                <th>修正事件标签 (技能 / 行为)</th>
                <th>触发错误次数</th>
                <th>严重程度</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(metrics.distribution).map(([type, count]) => (
                <tr key={type}>
                  <td><code>{type}</code></td>
                  <td>{count}</td>
                  <td>
                    {count > 10 ? (
                      <span className="badge badge-rejected">高危</span>
                    ) : count > 3 ? (
                      <span className="badge badge-pending_review">中等</span>
                    ) : (
                      <span className="badge badge-approved">低</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      
      {metrics && (!metrics.distribution || Object.keys(metrics.distribution).length === 0) && (
        <div className="card mt-8 p-6 text-center text-gray-500">
          目前尚未收集到任何人工介入的更正数据。AI 目前执行完美，或者尚未完成任何包含人工确认流程的任务。
        </div>
      )}
    </div>
  )
}
