import { useMemo, useState, useEffect, useRef } from 'react'
import { admin, adminConfig, adminUsers, adminTemplates, adminTools, adminPermissions, feedback } from '../api'
import { useAuth } from '../AuthContext'

// ─────────────────────── 子面板组件 ──────────────────────────

function SectionHeader({ title, desc, right }) {
  return (
    <div className="tab-header">
      <div>
        <h2>{title}</h2>
        {desc ? <p className="text-muted mt-4">{desc}</p> : null}
      </div>
      {right ? <div>{right}</div> : null}
    </div>
  )
}

// LLM 配置面板
function LLMConfigPanel() {
  const [configs, setConfigs] = useState({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const defaults = {
    llm_provider: 'openai',
    llm_model: 'gpt-4o',
    llm_api_key: '',
    llm_temperature: '0.2',
    llm_max_tokens: '4096',
    vision_mode: 'local_gpu',
    llm_vision_api_key: '',
    llm_vision_api_base: '',
    llm_vision_model: '',
  }

  useEffect(() => {
    adminConfig.list('llm').then(d => {
      const map = {}
      ;(d?.items || []).forEach(item => { map[item.config_key] = item.config_value })
      setConfigs({ ...defaults, ...map })
    }).catch(console.error)
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const items = Object.entries(configs).map(([k, v]) => ({
        namespace: 'llm',
        config_key: k,
        config_value: String(v),
        is_secret: k.includes('key'),
      }))
      await adminConfig.bulkUpsert(items)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (e) {
      alert('保存失败: ' + JSON.stringify(e))
    } finally {
      setSaving(false)
    }
  }

  const set = (key, val) => setConfigs(c => ({ ...c, [key]: val }))

  return (
    <div className="admin-tab-content">
      <SectionHeader
        title="LLM 模型配置"
        desc="配置 AI 大模型接入方式。API Key 保存后仅显示末4位。"
      />

      <div className="config-form">
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">提供商 (Provider)</label>
            <select className="input" value={configs.llm_provider || ''} onChange={e => set('llm_provider', e.target.value)}>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="google">Google Gemini</option>
              <option value="deepseek">DeepSeek</option>
              <option value="qwen">Qwen (通义千问)</option>
              <option value="baichuan">Baichuan (百川)</option>
              <option value="minimax">MiniMax</option>
              <option value="ollama">Ollama (本地)</option>
              <option value="mock">Mock (调试)</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">视觉推理引擎 (Vision Engine)</label>
            <select className="input" value={configs.vision_mode || 'local_gpu'} onChange={e => set('vision_mode', e.target.value)}>
              <option value="local_gpu">Local GPU (Grounding DINO 等)</option>
              <option value="llm_vision">External API (外部多模态大模型)</option>
            </select>
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">模型名称</label>
            <input className="input" value={configs.llm_model || ''} onChange={e => set('llm_model', e.target.value)} placeholder="gpt-4o / deepseek-chat" />
          </div>
        </div>
        <div className="form-group">
          <label className="form-label">API Key</label>
          <input className="input" type="password" value={configs.llm_api_key || ''} onChange={e => set('llm_api_key', e.target.value)} placeholder="sk-..." />
        </div>
        <div className="form-group">
          <label className="form-label">API Base URL</label>
          <input className="input" value={configs.llm_api_base || ''} onChange={e => set('llm_api_base', e.target.value)} placeholder="https://api.openai.com/v1" />
        </div>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Temperature (创造性)</label>
            <input className="input" type="number" step="0.1" min="0" max="2" value={configs.llm_temperature || '0.2'} onChange={e => set('llm_temperature', e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Max Tokens</label>
            <input className="input" type="number" value={configs.llm_max_tokens || '4096'} onChange={e => set('llm_max_tokens', e.target.value)} />
          </div>
        </div>

        {configs.vision_mode === 'llm_vision' && (
          <div className="card mt-16 p-16" style={{ background: 'var(--color-bg-2)' }}>
            <h4 className="mb-12 text-primary">外置视觉推理大模型独立配置</h4>
            <div className="form-group row mb-8">
              <label className="form-label" style={{ minWidth: 120 }}>Vision API Key</label>
              <input className="input" type="password" value={configs.llm_vision_api_key || ''} onChange={e => set('llm_vision_api_key', e.target.value)} placeholder="sk-..." />
            </div>
            <div className="form-group row mb-8">
              <label className="form-label" style={{ minWidth: 120 }}>Vision Base URL</label>
              <input className="input" value={configs.llm_vision_api_base || ''} onChange={e => set('llm_vision_api_base', e.target.value)} placeholder="https://api.openai.com/v1" />
            </div>
            <div className="form-group row">
              <label className="form-label" style={{ minWidth: 120 }}>Vision Model</label>
              <input className="input" value={configs.llm_vision_model || ''} onChange={e => set('llm_vision_model', e.target.value)} placeholder="gpt-4o / qwen-vl-max" />
            </div>
          </div>
        )}

        <div className="form-actions mt-16">
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? <div className="spinner" /> : saved ? '✅ 已保存' : '保存配置'}
          </button>
        </div>
      </div>

      <div className="threshold-section mt-24">
        <h3>AI 置信度阈值配置</h3>
        <p className="text-muted mt-8 mb-16">低于阈值时, AI 会自动触发人工介入 (HIL) 流程。</p>
        <ThresholdPanel />
      </div>

      <div className="threshold-section mt-24">
        <h3>Agent 限制参数</h3>
        <p className="text-muted mt-8 mb-16">用于限制单次 Agent 执行规模，避免长链路失控。</p>
        <AgentSettingsPanel />
      </div>
    </div>
  )
}

function ThresholdPanel() {
  const [thresholds, setThresholds] = useState({})
  const [saving, setSaving] = useState(false)

  const defaults = {
    detection_confidence: '0.75',
    receipt_match_confidence: '0.8',
    classification_confidence: '0.7',
    ocr_confidence: '0.85',
  }

  const labels = {
    detection_confidence: 'AI 目标检测置信度',
    receipt_match_confidence: '凭证匹配置信度',
    classification_confidence: '素材分类置信度',
    ocr_confidence: 'OCR 识别置信度',
  }

  useEffect(() => {
    adminConfig.list('thresholds').then(d => {
      const map = {}
      ;(d?.items || []).forEach(item => { map[item.config_key] = item.config_value })
      setThresholds({ ...defaults, ...map })
    }).catch(console.error)
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const items = Object.entries(thresholds).map(([k, v]) => ({
        namespace: 'thresholds', config_key: k, config_value: String(v), is_secret: false,
      }))
      await adminConfig.bulkUpsert(items)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="config-form">
      {Object.entries(thresholds).map(([key, val]) => (
        <div key={key} className="form-group threshold-row">
          <label className="form-label">{labels[key] || key}</label>
          <div className="threshold-control">
            <input type="range" min="0" max="1" step="0.01" value={val}
              onChange={e => setThresholds(t => ({ ...t, [key]: e.target.value }))} />
            <span className="threshold-value">{(parseFloat(val) * 100).toFixed(0)}%</span>
          </div>
        </div>
      ))}
      <div className="form-actions">
        <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
          {saving ? '保存中...' : '保存阈值'}
        </button>
      </div>
    </div>
  )
}

function AgentSettingsPanel() {
  const [cfg, setCfg] = useState({
    agent_max_steps: '50',
    agent_max_tokens: '200000',
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    adminConfig.list('agent').then(d => {
      const map = {}
      ;(d?.items || []).forEach(item => { map[item.config_key] = item.config_value })
      setCfg(c => ({ ...c, ...map }))
    }).catch(console.error)
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      await adminConfig.bulkUpsert(Object.entries(cfg).map(([k, v]) => ({
        namespace: 'agent',
        config_key: k,
        config_value: String(v),
        is_secret: false,
      })))
    } catch (e) {
      alert('保存失败: ' + (e?.detail || JSON.stringify(e)))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="config-form">
      <div className="form-row">
        <div className="form-group">
          <label className="form-label">AGENT_MAX_STEPS</label>
          <input className="input" type="number" min="1" value={cfg.agent_max_steps || ''} onChange={e => setCfg(x => ({ ...x, agent_max_steps: e.target.value }))} />
        </div>
        <div className="form-group">
          <label className="form-label">AGENT_MAX_TOKENS</label>
          <input className="input" type="number" min="1000" value={cfg.agent_max_tokens || ''} onChange={e => setCfg(x => ({ ...x, agent_max_tokens: e.target.value }))} />
        </div>
      </div>
      <div className="form-actions">
        <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>
          {saving ? '保存中...' : '保存 Agent 参数'}
        </button>
      </div>
    </div>
  )
}

function APIConfigPanel() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [draft, setDraft] = useState({ config_key: '', config_value: '', is_secret: true, description: '' })

  const load = () => {
    setLoading(true)
    adminConfig.list('api_keys')
      .then(d => setItems(d?.items || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const upsert = async () => {
    if (!draft.config_key) return
    setSaving(true)
    try {
      await adminConfig.upsert({
        namespace: 'api_keys',
        config_key: draft.config_key,
        config_value: String(draft.config_value || ''),
        is_secret: !!draft.is_secret,
        description: draft.description || null,
      })
      setDraft({ config_key: '', config_value: '', is_secret: true, description: '' })
      load()
    } catch (e) {
      alert('保存失败: ' + (e?.detail || JSON.stringify(e)))
    } finally {
      setSaving(false)
    }
  }

  const del = async (key) => {
    if (!confirm(`确认删除配置项 ${key}？`)) return
    try {
      await adminConfig.delete('api_keys', key)
      load()
    } catch (e) {
      alert('删除失败: ' + (e?.detail || JSON.stringify(e)))
    }
  }

  return (
    <div className="admin-tab-content">
      <SectionHeader
        title="API 配置"
        desc="集中管理第三方 API Key、Base URL、Webhook 等（脱敏展示）。"
      />

      <div className="card mb-24">
        <h3 className="mb-16">新增 / 更新配置</h3>
        <div className="flex-col gap-12">
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Key</label>
              <input className="input" value={draft.config_key} onChange={e => setDraft(d => ({ ...d, config_key: e.target.value }))} placeholder="例如：github_token / slack_webhook" />
            </div>
            <div className="form-group">
              <label className="form-label">Secret</label>
              <select className="input" value={draft.is_secret ? 'yes' : 'no'} onChange={e => setDraft(d => ({ ...d, is_secret: e.target.value === 'yes' }))}>
                <option value="yes">是（脱敏）</option>
                <option value="no">否</option>
              </select>
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Value</label>
            <input className="input" type={draft.is_secret ? 'password' : 'text'} value={draft.config_value} onChange={e => setDraft(d => ({ ...d, config_value: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">描述（可选）</label>
            <input className="input" value={draft.description} onChange={e => setDraft(d => ({ ...d, description: e.target.value }))} />
          </div>
          <div className="form-actions">
            <button className="btn btn-primary btn-sm" onClick={upsert} disabled={saving || !draft.config_key}>
              {saving ? '保存中...' : '保存配置项'}
            </button>
          </div>
        </div>
      </div>

      <div className="data-table-container">
        <table className="data-table">
          <thead><tr><th>Key</th><th>Value</th><th>描述</th><th>更新时间</th><th>操作</th></tr></thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="5" className="text-center py-16"><div className="spinner" style={{ margin: '0 auto' }} /></td></tr>
            ) : (items || []).map(x => (
              <tr key={x.id}>
                <td className="font-bold"><code>{x.config_key}</code></td>
                <td>{x.config_value || '-'}</td>
                <td>{x.description || '-'}</td>
                <td>{x.updated_at ? new Date(x.updated_at).toLocaleString() : '-'}</td>
                <td>
                  <button className="btn btn-sm btn-danger" onClick={() => del(x.config_key)}>删除</button>
                </td>
              </tr>
            ))}
            {!loading && (items || []).length === 0 && (
              <tr><td colSpan="5" className="text-center py-8 text-muted">暂无 API 配置项</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ToolsPanel() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState(null)
  const [calls, setCalls] = useState([])
  const [loadingCalls, setLoadingCalls] = useState(false)

  const load = () => {
    setLoading(true)
    adminTools.list({ q: q || undefined })
      .then(d => setItems(d?.items || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const loadCalls = async (tool_id) => {
    setSelected(tool_id)
    setLoadingCalls(true)
    try {
      const d = await adminTools.calls({ tool_id, limit: 50 })
      setCalls(d?.items || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoadingCalls(false)
    }
  }

  return (
    <div className="admin-tab-content">
      <SectionHeader
        title="Tools 管理"
        desc="查看当前已注册的工具清单与运行统计，辅助排障与治理。"
        right={
          <div className="flex gap-8">
            <input className="input" style={{ width: 260 }} value={q} onChange={e => setQ(e.target.value)} placeholder="搜索 tool_id（模糊匹配）" />
            <button className="btn btn-primary btn-sm" onClick={load} disabled={loading}>查询</button>
          </div>
        }
      />

      <div className="skills-layout">
        <div className="data-table-container" style={{ flex: 1 }}>
          <table className="data-table">
            <thead><tr><th>Tool</th><th>Skill</th><th>总调用</th><th>失败</th><th>错误率</th><th>最近调用</th></tr></thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="6" className="text-center py-16"><div className="spinner" style={{ margin: '0 auto' }} /></td></tr>
              ) : (items || []).map(t => (
                <tr key={t.tool_id} onClick={() => loadCalls(t.tool_id)} style={{ cursor: 'pointer' }}
                  className={selected === t.tool_id ? 'selected-row' : ''}>
                  <td className="font-bold"><code>{t.tool_id}</code></td>
                  <td>{t.skill_id || '-'}</td>
                  <td>{t.total_calls}</td>
                  <td>{t.failed_calls}</td>
                  <td>{((t.error_rate || 0) * 100).toFixed(1)}%</td>
                  <td>{t.last_used_at ? new Date(t.last_used_at).toLocaleString() : '-'}</td>
                </tr>
              ))}
              {!loading && (items || []).length === 0 && (
                <tr><td colSpan="6" className="text-center py-8 text-muted">暂无工具</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="skill-detail-panel card">
          <h3>最近调用</h3>
          {!selected ? (
            <p className="text-muted mt-8">点击左侧工具查看最近调用日志。</p>
          ) : loadingCalls ? (
            <div className="spinner mt-16" />
          ) : (
            <div className="mt-12">
              {(calls || []).length === 0 ? (
                <div className="text-muted">暂无调用记录</div>
              ) : (
                <div className="flex-col gap-8">
                  {calls.map(c => (
                    <div key={c.id} className="card" style={{ padding: 12 }}>
                      <div className="flex items-center justify-between gap-8">
                        <div className="font-bold"><code>{c.tool_name}</code></div>
                        <div className={`badge ${c.status === 'SUCCESS' ? 'badge-approved' : 'badge-rejected'}`}>{c.status}</div>
                      </div>
                      <div className="text-muted mt-4" style={{ fontSize: '0.85rem' }}>
                        task: <code>{(c.task_id || '').slice(0, 8)}</code> · {c.duration_ms}ms · {c.created_at ? new Date(c.created_at).toLocaleString() : '-'} {c.error_type ? `· error: ${c.error_type}` : ''}
                      </div>
                      {c.input_summary ? <div className="mt-8"><strong>输入摘要：</strong><span className="text-muted"> {c.input_summary}</span></div> : null}
                      {c.output_summary ? <div className="mt-4"><strong>输出摘要：</strong><span className="text-muted"> {c.output_summary}</span></div> : null}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ExperienceAdminPanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    feedback.metrics()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="admin-tab-content">
      <SectionHeader
        title="经验层（Experience Layer）"
        desc="汇总 HIL 人工修正事件分布，用于后续 Prompt/参数调优闭环。"
      />

      {loading ? (
        <div className="spinner mt-16" />
      ) : (
        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <h3>Feedback 统计</h3>
              <p className="text-muted mt-4">当前为 V1 最小可用报表；后续可扩展 PatternReport、PromptDiff 建议、ToolDiscovery 等。</p>
            </div>
            <div className="badge badge-approved">total: {data?.total_events || 0}</div>
          </div>
          <div className="mt-16 data-table-container">
            <table className="data-table">
              <thead><tr><th>事件类型</th><th>次数</th></tr></thead>
              <tbody>
                {Object.entries(data?.distribution || {}).map(([k, v]) => (
                  <tr key={k}>
                    <td className="font-bold"><code>{k}</code></td>
                    <td>{v}</td>
                  </tr>
                ))}
                {Object.keys(data?.distribution || {}).length === 0 && (
                  <tr><td colSpan="2" className="text-center py-8 text-muted">暂无数据</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// 用户管理面板
function UsersPanel() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [editUser, setEditUser] = useState(null)
  const [form, setForm] = useState({ username: '', password: '', email: '', role: 'executor', department_id: '' })

  const roleLabels = { admin: '超级管理员', executor: '执行员', reviewer: '审核员', finance: '财务员' }
  const roleColors = { admin: 'badge-rejected', executor: 'badge-approved', reviewer: 'badge-pending_review', finance: 'badge-draft' }

  const load = () => {
    setLoading(true)
    adminUsers.list().then(d => setUsers(d?.items || [])).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleCreate = async () => {
    try {
      await adminUsers.create(form)
      setShowCreate(false)
      setForm({ username: '', password: '', email: '', role: 'executor', department_id: '' })
      load()
    } catch (e) {
      alert('创建失败: ' + (e?.detail || JSON.stringify(e)))
    }
  }

  const handleToggleActive = async (user) => {
    if (!confirm(`确认${user.is_active ? '禁用' : '启用'}用户 ${user.username}？`)) return
    try {
      if (user.is_active) {
        await adminUsers.deactivate(user.id)
      } else {
        await adminUsers.update(user.id, { is_active: true })
      }
      load()
    } catch (e) {
      alert('操作失败: ' + JSON.stringify(e))
    }
  }

  const handleRoleChange = async (user, newRole) => {
    try {
      await adminUsers.update(user.id, { role: newRole })
      load()
    } catch (e) {
      alert('更改角色失败: ' + JSON.stringify(e))
    }
  }

  return (
    <div className="admin-tab-content">
      <div className="tab-header">
        <div>
          <h2>用户管理</h2>
          <p className="text-muted mt-4">管理平台用户账户、角色与访问权限。</p>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>+ 新增用户</button>
      </div>

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3 className="modal-title">新增用户</h3>
            <div className="flex-col gap-16">
              {[['用户名', 'username', 'text'], ['密码', 'password', 'password'], ['邮箱', 'email', 'email'], ['部门ID', 'department_id', 'text']].map(([label, key, type]) => (
                <div className="form-group" key={key}>
                  <label className="form-label">{label}</label>
                  <input className="input" type={type} value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
                </div>
              ))}
              <div className="form-group">
                <label className="form-label">角色</label>
                <select className="input" value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
                  {Object.entries(roleLabels).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setShowCreate(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleCreate}>创建</button>
            </div>
          </div>
        </div>
      )}

      <div className="data-table-container mt-16">
        <table className="data-table">
          <thead>
            <tr><th>用户名</th><th>邮箱</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="6" className="text-center py-16"><div className="spinner" style={{ margin: '0 auto' }} /></td></tr>
            ) : users.map(u => (
              <tr key={u.id}>
                <td className="font-bold">{u.username}</td>
                <td>{u.email || '-'}</td>
                <td>
                  <select className="input" style={{ padding: '4px 8px', fontSize: '0.8rem' }}
                    value={u.role} onChange={e => handleRoleChange(u, e.target.value)}>
                    {Object.entries(roleLabels).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </td>
                <td>
                  <span className={`badge ${u.is_active ? 'badge-approved' : 'badge-rejected'}`}>
                    {u.is_active ? '正常' : '已禁用'}
                  </span>
                </td>
                <td>{u.created_at ? new Date(u.created_at).toLocaleDateString() : '-'}</td>
                <td>
                  <button className={`btn btn-sm ${u.is_active ? 'btn-danger' : 'btn-primary'}`}
                    onClick={() => handleToggleActive(u)}>
                    {u.is_active ? '禁用' : '启用'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <PermissionMatrix />
    </div>
  )
}

function PermissionMatrix() {
  const [matrix, setMatrix] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    adminPermissions.matrix()
      .then(setMatrix)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const roles = useMemo(() => (matrix?.roles || []).map(r => r.id), [matrix])
  const roleLabels = useMemo(() => {
    const m = {}
    ;(matrix?.roles || []).forEach(r => { m[r.id] = r.label })
    return m
  }, [matrix])
  const features = matrix?.features || []
  const allow = matrix?.allow || {}

  return (
    <div className="mt-32">
      <h3>功能权限矩阵</h3>
      <p className="text-muted mt-8 mb-16">平台各角色拥有的功能访问权限概览（只读，来源于后端定义）。</p>
      <div className="data-table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>功能模块</th>
              {roles.map(r => <th key={r}>{roleLabels[r]}</th>)}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={1 + roles.length} className="text-center py-16"><div className="spinner" style={{ margin: '0 auto' }} /></td></tr>
            ) : features.map(f => (
              <tr key={f.id}>
                <td className="font-bold">{f.label}</td>
                {roles.map(r => (
                  <td key={r} style={{ textAlign: 'center' }}>
                    {allow?.[f.id]?.[r] ? <span style={{ color: 'var(--color-success)', fontSize: '1.2rem' }}>✓</span>
                           : <span style={{ color: 'var(--color-text-3)' }}>—</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// 技能管理面板
function SkillsPanel() {
  const [skills, setSkills] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedSkill, setSelectedSkill] = useState(null)
  const [skillDetail, setSkillDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [showInstall, setShowInstall] = useState(false)
  const [gitUrl, setGitUrl] = useState('')
  const [gitBranch, setGitBranch] = useState('main')
  const [installing, setInstalling] = useState(false)
  const fileRef = useRef(null)

  const load = () => {
    setLoading(true)
    admin.listSkills().then(d => setSkills(Array.isArray(d) ? d : [])).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleToggle = async (skill) => {
    try {
      await admin.setSkillEnabled(skill.id, !skill.is_enabled)
      setSkills(s => s.map(x => x.id === skill.id ? { ...x, is_enabled: !skill.is_enabled } : x))
    } catch (e) { alert('操作失败: ' + JSON.stringify(e)) }
  }

  const viewDetail = async (skill) => {
    setSelectedSkill(skill)
    setLoadingDetail(true)
    try {
      const d = await admin.getSkillDetail(skill.id)
      setSkillDetail(d)
    } catch (e) { console.error(e) }
    finally { setLoadingDetail(false) }
  }

  const handleGitInstall = async () => {
    if (!gitUrl) return
    setInstalling(true)
    try {
      await admin.installSkillFromGit({ git_url: gitUrl, branch: gitBranch })
      setShowInstall(false)
      setGitUrl('')
      load()
    } catch (e) { alert('安装失败: ' + (e?.detail || JSON.stringify(e))) }
    finally { setInstalling(false) }
  }

  const handleZipInstall = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setInstalling(true)
    try {
      await admin.installSkillFromZip(file)
      load()
    } catch (e) { alert('安装失败: ' + (e?.detail || JSON.stringify(e))) }
    finally { setInstalling(false); e.target.value = '' }
  }

  const toolTypeColor = { auto: 'badge-approved', human_in_loop: 'badge-pending_review' }

  return (
    <div className="admin-tab-content">
      <div className="tab-header">
        <div><h2>技能管理</h2><p className="text-muted mt-4">管理 AI Agent 的能力节点。每个Skill包含一组顺序执行的Tools。</p></div>
        <div className="flex gap-8">
          <input ref={fileRef} type="file" accept=".zip" style={{ display: 'none' }} onChange={handleZipInstall} />
          <button className="btn btn-ghost btn-sm" onClick={() => fileRef.current?.click()} disabled={installing}>
            {installing ? '安装中...' : '📦 ZIP安装'}
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => setShowInstall(true)}>🔗 Git安装</button>
        </div>
      </div>

      {showInstall && (
        <div className="modal-overlay" onClick={() => setShowInstall(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3 className="modal-title">从 Git 仓库安装 Skill</h3>
            <div className="flex-col gap-16">
              <div className="form-group">
                <label className="form-label">Git 仓库 URL</label>
                <input className="input" value={gitUrl} onChange={e => setGitUrl(e.target.value)} placeholder="https://github.com/org/skill-name.git" />
              </div>
              <div className="form-group">
                <label className="form-label">分支 (Branch)</label>
                <input className="input" value={gitBranch} onChange={e => setGitBranch(e.target.value)} placeholder="main" />
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setShowInstall(false)}>取消</button>
              <button className="btn btn-primary" onClick={handleGitInstall} disabled={installing || !gitUrl}>
                {installing ? '安装中...' : '安装'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="skills-layout">
        <div className="data-table-container" style={{ flex: 1 }}>
          <table className="data-table">
            <thead><tr><th>技能ID</th><th>名称</th><th>版本</th><th>工具数</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="6" className="text-center py-16"><div className="spinner" style={{ margin: '0 auto' }} /></td></tr>
              ) : skills.map(skill => (
                <tr key={skill.id} onClick={() => viewDetail(skill)} style={{ cursor: 'pointer' }}
                  className={selectedSkill?.id === skill.id ? 'selected-row' : ''}>
                  <td><code>{skill.id}</code></td>
                  <td className="font-bold">{skill.name}</td>
                  <td>{skill.version}</td>
                  <td>{skill.tools_count}</td>
                  <td><span className={`badge badge-${skill.is_enabled ? 'approved' : 'rejected'}`}>{skill.is_enabled ? '已启用' : '已禁用'}</span></td>
                  <td onClick={e => e.stopPropagation()}>
                    <button className={`btn btn-sm ${skill.is_enabled ? 'btn-danger' : 'btn-primary'}`} onClick={() => handleToggle(skill)}>
                      {skill.is_enabled ? '禁用' : '启用'}
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && skills.length === 0 && (
                <tr><td colSpan="6" className="text-center py-16 text-muted">暂无已注册的技能节点</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {selectedSkill && (
          <div className="skill-detail-panel card">
            <h3>技能详情：{selectedSkill.name}</h3>
            {loadingDetail ? <div className="spinner mt-16" /> : skillDetail && (
              <div className="mt-16 flex-col gap-12">
                <p><strong>描述：</strong>{skillDetail.description || '暂无'}</p>
                <p><strong>版本：</strong>{skillDetail.version}</p>
                <p><strong>所需角色：</strong>{(skillDetail.required_roles || []).join(', ')}</p>
                <p><strong>触发示例：</strong>{(skillDetail.trigger_examples || []).join(' / ')}</p>
                <hr style={{ borderColor: 'var(--color-border)' }} />
                <h4>工具链 ({(skillDetail.tools || []).length} 个工具)</h4>
                <div className="stepper mt-8">
                  {(skillDetail.tools || []).map((t, i) => (
                    <div key={t.name} className="step-item">
                      <div className={`step-dot ${t.has_implementation ? 'done' : 'pending'}`}>{i + 1}</div>
                      <div className="step-content">
                        <div className="step-name flex items-center gap-8">
                          {t.name}
                          <span className={`badge badge-sm ${toolTypeColor[t.type] || 'badge-draft'}`} style={{ fontSize: '0.65rem', padding: '2px 6px' }}>{t.type}</span>
                        </div>
                        <div className="step-detail">
                          timeout: {t.timeout}s
                          {t.ui ? ` | UI: ${t.ui}` : ''}
                          {!t.has_implementation && <span style={{ color: 'var(--color-danger)' }}> ⚠ 缺少实现文件</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// PPT 模板管理面板
function TemplatesPanel() {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)

  const load = () => {
    setLoading(true)
    adminTemplates.list().then(d => setTemplates(d?.items || [])).catch(console.error).finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file || !name) { alert('请先填写模板名称'); return }
    setUploading(true)
    try {
      await adminTemplates.uploadTemplate(name, file, desc)
      setName(''); setDesc('')
      load()
    } catch (ex) { alert('上传失败: ' + (ex?.detail || JSON.stringify(ex))) }
    finally { setUploading(false); e.target.value = '' }
  }

  const handleSetDefault = async (id) => {
    try { await adminTemplates.setDefault(id); load() }
    catch (e) { alert('设置默认失败: ' + JSON.stringify(e)) }
  }

  const handleDelete = async (id) => {
    if (!confirm('确认删除此模板？')) return
    try { await adminTemplates.delete(id); load() }
    catch (e) { alert('删除失败: ' + JSON.stringify(e)) }
  }

  return (
    <div className="admin-tab-content">
      <div className="tab-header">
        <div><h2>PPT 模板管理</h2><p className="text-muted mt-4">上传 .pptx 模板用于生成结案报告。默认模板将在任务中自动使用。</p></div>
      </div>

      <div className="card mb-24">
        <h3 className="mb-16">上传新模板</h3>
        <div className="flex gap-16 items-center flex-wrap">
          <div className="form-group" style={{ flex: 1, minWidth: 200 }}>
            <label className="form-label">模板名称</label>
            <input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="例：2026年标准活动结案模板" />
          </div>
          <div className="form-group" style={{ flex: 1, minWidth: 200 }}>
            <label className="form-label">描述 (可选)</label>
            <input className="input" value={desc} onChange={e => setDesc(e.target.value)} placeholder="描述此模板适用场景" />
          </div>
          <div style={{ alignSelf: 'flex-end' }}>
            <input ref={fileRef} type="file" accept=".pptx" style={{ display: 'none' }} onChange={handleUpload} />
            <button className="btn btn-primary" onClick={() => fileRef.current?.click()} disabled={uploading || !name}>
              {uploading ? '上传中...' : '选择 .pptx 上传'}
            </button>
          </div>
        </div>
      </div>

      <div className="data-table-container">
        <table className="data-table">
          <thead><tr><th>模板名称</th><th>描述</th><th>默认</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="5" className="text-center py-16"><div className="spinner" style={{ margin: '0 auto' }} /></td></tr>
            ) : templates.map(t => (
              <tr key={t.id}>
                <td className="font-bold">📄 {t.name}</td>
                <td>{t.description || '-'}</td>
                <td>{t.is_default ? <span className="badge badge-approved">默认</span> : '-'}</td>
                <td><span className={`badge ${t.is_active ? 'badge-approved' : 'badge-rejected'}`}>{t.is_active ? '启用' : '停用'}</span></td>
                <td className="flex gap-8">
                  {!t.is_default && (
                    <button className="btn btn-sm btn-ghost" onClick={() => handleSetDefault(t.id)}>设为默认</button>
                  )}
                  <button className="btn btn-sm btn-danger" onClick={() => handleDelete(t.id)}>删除</button>
                </td>
              </tr>
            ))}
            {!loading && templates.length === 0 && (
              <tr><td colSpan="5" className="text-center py-8 text-muted">暂无模板，请上传第一个 .pptx 模板。</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// 审计日志面板
function AuditLogPanel() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    adminConfig.auditLog(100).then(d => setLogs(d?.items || [])).catch(console.error).finally(() => setLoading(false))
  }, [])

  return (
    <div className="admin-tab-content">
      <h2>系统审计日志</h2>
      <p className="text-muted mt-8 mb-16">记录所有管理员操作，包括配置变更、用户管理、技能启停等。</p>
      <div className="data-table-container">
        <table className="data-table">
          <thead><tr><th>操作人</th><th>操作类型</th><th>资源</th><th>时间</th></tr></thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="4" className="text-center py-16"><div className="spinner" style={{ margin: '0 auto' }} /></td></tr>
            ) : logs.map(log => (
              <tr key={log.id}>
                <td className="font-bold">{log.username || '-'}</td>
                <td><code>{log.action}</code></td>
                <td>{log.resource_type} {log.resource_id ? `/ ${log.resource_id.slice(0, 8)}` : ''}</td>
                <td>{new Date(log.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {!loading && logs.length === 0 && (
              <tr><td colSpan="4" className="text-center py-8 text-muted">暂无审计记录</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─────────────────────── 主 Admin 组件 ───────────────────────

const TABS = [
  { id: 'llm', label: 'LLM 配置', icon: '🤖' },
  { id: 'api', label: 'API 配置', icon: '🔑' },
  { id: 'users', label: '用户管理', icon: '👥' },
  { id: 'skills', label: '技能管理', icon: '⚙️' },
  { id: 'tools', label: 'Tools 管理', icon: '🧰' },
  { id: 'templates', label: 'PPT 模板', icon: '📄' },
  { id: 'experience', label: '经验层', icon: '📈' },
  { id: 'audit', label: '审计日志', icon: '📋' },
]

export default function Admin() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState('llm')

  if (user?.role !== 'admin') {
    return (
      <div className="empty-state">
        <div className="empty-icon">🔒</div>
        <h3>访问被拒绝</h3>
        <p>此页面仅限系统管理员访问。</p>
      </div>
    )
  }

  return (
    <div className="admin-panel fade-in">
      <div className="admin-sidebar-tabs">
        <div className="admin-tabs-header">
          <h3>系统管理</h3>
        </div>
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`admin-tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="admin-tab-body">
        {activeTab === 'llm' && <LLMConfigPanel />}
        {activeTab === 'api' && <APIConfigPanel />}
        {activeTab === 'users' && <UsersPanel />}
        {activeTab === 'skills' && <SkillsPanel />}
        {activeTab === 'tools' && <ToolsPanel />}
        {activeTab === 'templates' && <TemplatesPanel />}
        {activeTab === 'experience' && <ExperienceAdminPanel />}
        {activeTab === 'audit' && <AuditLogPanel />}
      </div>
    </div>
  )
}
