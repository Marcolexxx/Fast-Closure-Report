// ── API base client ─────────────────────────────────────────
const BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

let inMemoryToken = null

export function setToken(token) {
  inMemoryToken = token
}

function getToken() {
  return inMemoryToken
}

async function request(method, path, body, opts = {}) {
  const token = getToken()
  const headers = {
    ...(body && !(body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...opts.headers,
  }
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: 'include',  // Send HttpOnly cookies (refresh token)
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) {
    // Try refresh via HttpOnly cookie (no localStorage needed)
    const refreshed = await tryRefresh()
    if (!refreshed) {
      setToken(null)
      window.location.href = '/login'
      throw new Error('Session expired')
    }
    // retry once
    const token2 = getToken()
    const res2 = await fetch(`${BASE}${path}`, {
      method,
      headers: {
        ...headers,
        Authorization: `Bearer ${token2}`,
      },
      credentials: 'include',
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    })
    if (!res2.ok) throw await res2.json().catch(() => ({ detail: res2.statusText }))
    return res2.json().catch(() => null)
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw err
  }
  return res.json().catch(() => null)
}

async function tryRefresh() {
  // Refresh token is stored in HttpOnly cookie — just call the endpoint with credentials.
  // No localStorage access needed.
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
    if (!res.ok) return false
    const data = await res.json()
    if (data.access_token) {
      setToken(data.access_token)
      return true
    }
    return false
  } catch {
    return false
  }
}

// ── Auth ─────────────────────────────────────────────────────
export const auth = {
  login: (username, password) => request('POST', '/auth/login', { username, password }),
  register: (body) => request('POST', '/auth/register', body),
  me: () => request('GET', '/auth/me'),
  logout: () => request('POST', '/auth/logout'),
}

// ── Projects ─────────────────────────────────────────────────
export const projects = {
  list: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request('GET', `/projects${q ? '?' + q : ''}`)
  },
  get: (id) => request('GET', `/projects/${id}`),
  create: (body) => request('POST', '/projects', body),
  submitReview: (id) => request('POST', `/projects/${id}/submit-review`),
  review: (id, body) => request('PATCH', `/projects/${id}/review`, body),
  listFiles: (id) => request('GET', `/projects/${id}/files`),
  uploadFile: (id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('POST', `/projects/${id}/files`, fd)
  },
  uploadInit: (id, payload) => request('POST', `/projects/${id}/files/init`, payload),
  uploadChunk: (id, uploadId, chunkIndex, fileBlob) => {
    const fd = new FormData()
    fd.append('upload_id', uploadId)
    fd.append('chunk_index', chunkIndex)
    fd.append('file', fileBlob)
    return request('POST', `/projects/${id}/files/chunk`, fd)
  },
  uploadComplete: (id, payload) => request('POST', `/projects/${id}/files/complete`, payload),
  downloadResult: async (id) => {
    const token = getToken()
    const res = await fetch(`${BASE}/projects/${id}/download-result`, {
      method: 'GET',
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Download failed' }))
      throw err
    }
    const blob = await res.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Report_${id}.pptx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  },
}

// ── Tasks ─────────────────────────────────────────────────────
export const tasks = {
  create: (body) => request('POST', '/tasks', body),
  resume: (id) => request('POST', `/tasks/${id}/resume`),
  getHilState: (id) => request('GET', `/tasks/${id}/hil/current`),
  submitHil: (id, body) => request('POST', `/tasks/${id}/hil/submit`, body),
}

// ── Admin / Skills ────────────────────────────────────────────
export const admin = {
  // Skills
  listSkills: () => request('GET', '/admin/skills'),
  getSkillDetail: (id) => request('GET', `/admin/skills/${id}`),
  setSkillEnabled: (id, enabled) => request('POST', `/admin/skills/${id}/enabled`, { enabled }),
  reloadSkill: (id) => request('POST', `/admin/skills/${id}/reload`),
  reloadAllSkills: () => request('POST', '/admin/skills/reload_all'),
  installSkillFromGit: (body) => request('POST', '/admin/skills/install-from-git', body),
  installSkillFromZip: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('POST', '/admin/skills/install-from-zip', fd)
  },
}

// ── Admin / Tools ─────────────────────────────────────────────
export const adminTools = {
  list: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request('GET', `/admin/tools${q ? '?' + q : ''}`)
  },
  calls: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request('GET', `/admin/tools/calls${q ? '?' + q : ''}`)
  },
}

// ── Admin / Permissions Matrix ────────────────────────────────
export const adminPermissions = {
  matrix: () => request('GET', '/admin/permissions'),
}

// ── Admin / System Config ─────────────────────────────────────
export const adminConfig = {
  list: (namespace) => request('GET', `/admin/config${namespace ? `?namespace=${namespace}` : ''}`),
  upsert: (body) => request('PUT', '/admin/config', body),
  bulkUpsert: (items) => request('PUT', '/admin/config/bulk', { items }),
  delete: (namespace, key) => request('DELETE', `/admin/config/${namespace}/${key}`),
  auditLog: (limit = 50) => request('GET', `/admin/config/audit-log?limit=${limit}`),
}

// ── Admin / Users ─────────────────────────────────────────────
export const adminUsers = {
  list: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request('GET', `/admin/users${q ? '?' + q : ''}`)
  },
  get: (id) => request('GET', `/admin/users/${id}`),
  create: (body) => request('POST', '/admin/users', body),
  update: (id, body) => request('PATCH', `/admin/users/${id}`, body),
  deactivate: (id) => request('DELETE', `/admin/users/${id}`),
  resetPassword: (id, password) => request('POST', `/admin/users/${id}/reset-password`, { password }),
}

// ── Admin / PPT Templates ─────────────────────────────────────
export const adminTemplates = {
  list: () => request('GET', '/admin/templates'),
  uploadTemplate: (name, file, description) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', name)
    if (description) fd.append('description', description)
    return request('POST', '/admin/templates', fd)
  },
  update: (id, body) => request('PATCH', `/admin/templates/${id}`, body),
  setDefault: (id) => request('POST', `/admin/templates/${id}/set-default`),
  delete: (id) => request('DELETE', `/admin/templates/${id}`),
}

// ── Experience Layer (Feedback) ────────────────────────────────
export const feedback = {
  submit: (body) => request('POST', '/experience/feedback', body),
  metrics: () => request('GET', '/experience/metrics')
}

// ── WS helper ────────────────────────────────────────────────
export function connectTaskWs(taskId, onMessage) {
  const wsBase = BASE.replace(/^http/, 'ws')
  const ws = new WebSocket(`${wsBase}/ws/task/${taskId}`)
  let ping;
  
  ws.onopen = () => {
    const token = getToken() || ''
    ws.send(JSON.stringify({ type: 'auth', token }))
  }

  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch {}
  }
  
  ping = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
  }, 30000)
  
  ws.onclose = () => {
    clearInterval(ping)
    // Add reconnect
    setTimeout(() => {
      onMessage({ type: 'reconnect_attempt' })
      // Notice: reconnect is manually handled by caller if needed, or we just rely on parent component.
    }, 5000)
  }
  return ws
}
