import axios from 'axios'

// Empty baseURL → requests use Vite's /api proxy (http://localhost:5173/api/*)
// which forwards to http://localhost:8000 server-side — no CORS at all.
// Set VITE_API_URL to an absolute URL only for production builds.
const API_BASE_URL = import.meta.env.VITE_API_URL || ''

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

// Request interceptor — Bearer token wired in Sprint 5
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  },
  (error) => Promise.reject(error)
)

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    if (status === 401) console.warn('[API] 401 Unauthorized — backend may require auth or not be running')
    if (!error.response) console.warn('[API] Network error — is the Python backend running on port 8000?')
    return Promise.reject(error)
  }
)

// ── Chat / BOM Session API ────────────────────────────────────────────────

export const chatApi = {
  ping: () => apiClient.get('/health').then(() => true).catch(() => false),
  startSession: (category, project = 'New Project', userId = 'demo_user', existingBom = null, domainPreselected = false) =>
    apiClient.post('/api/bom/start', { category, project, user_id: userId, existing_bom: existingBom, domain_preselected: domainPreselected }).then(r => r.data),
  sendMessage: (sessionId, message, userId = 'demo_user') =>
    apiClient.post('/api/bom/chat', { session_id: sessionId, message, user_id: userId }).then(r => r.data),
  sendMessageStream: (sessionId, message, userId = 'demo_user', onToken, onDone) => {
    const url = '/api/bom/stream'  // LangGraph async endpoint (Step 8)
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message, user_id: userId }),
    }).then(async (res) => {
      if (!res.ok) throw new Error('Stream request failed: ' + res.status)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) {
          // Drain remaining buffer — final SSE event may still be buffered when stream closes
          buffer += decoder.decode()
          const remaining = buffer.split('\n\n')
          for (const line of remaining) {
            if (!line.startsWith('data: ')) continue
            try {
              const evt = JSON.parse(line.slice(6))
              if (!evt.done) onToken(evt.token)
              else onDone(evt)
            } catch (_) {}
          }
          break
        }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (!evt.done) onToken(evt.token)
            else onDone(evt)
          } catch (_) {}
        }
      }
    })
  },
  getSession: (sessionId) =>
    apiClient.get(`/api/bom/session/${sessionId}`).then(r => r.data),
  /** List past sessions from Cosmos (sidebar history) */
  getHistory: (userId = 'demo_user', limit = 30) =>
    apiClient.get('/api/bom/history', { params: { user_id: userId, limit } }).then(r => r.data),
  /** Load full conversation transcript from ADLS / Cosmos */
  getTranscript: (sessionId, userId = 'demo_user') =>
    apiClient.get(`/api/bom/history/${sessionId}/transcript`, { params: { user_id: userId } }).then(r => r.data),
}

// ── BOM CRUD API ──────────────────────────────────────────────────────────

export const bomService = {
  /** List all BOMs (real Cosmos data) */
  list: (params = {}) =>
    apiClient.get('/api/bom', { params }).then(r => r.data),

  /** Get single BOM */
  get: (bomId, options = {}) =>
    apiClient.get(`/api/bom/${bomId}`, { signal: options.signal }).then(r => r.data),

  /** Create a new BOM */
  create: (bomData) =>
    apiClient.post('/api/bom', bomData).then(r => r.data),

  /** Delete a BOM permanently */
  delete: (bomId) =>
    apiClient.delete(`/api/bom/${bomId}`).then(r => r.data),

  /** Update a BOM */
  update: (bomId, data) =>
    apiClient.put(`/api/bom/${bomId}`, data).then(r => r.data),

  /** Permanently delete a BOM */
  delete: (bomId) =>
    apiClient.delete(`/api/bom/${bomId}`).then(r => r.data).catch(() => null),  // best-effort

  /** Get approval status */
  getApprovals: (bomId) =>
    apiClient.get(`/api/bom/${bomId}/approvals`).then(r => r.data),

  /** Submit an approval / request_changes / reject */
  approve: (bomId, party, approvedBy, action = 'approve', comments = '', changeDescription = '') =>
    apiClient.post(`/api/bom/${bomId}/approve`, {
      party, approved_by: approvedBy, action, comments, change_description: changeDescription,
    }).then(r => r.data),

  /** Download BOM as Excel */
  exportExcel: (bomId) =>
    apiClient.get(`/api/bom/${bomId}/export/excel`, { responseType: 'blob' }).then(r => r.data),

  /** Export chat-generated BOM (not yet in DB) as Excel */
  exportChatBOMExcel: (bomId, bomData) =>
    apiClient.post(`/api/bom/${bomId}/export/excel`, bomData, { responseType: 'blob' }).then(r => r.data),
}

// Keep backward-compatible alias
export const bomApi = bomService

// ── Analytics API ─────────────────────────────────────────────────────────

export const analyticsApi = {
  kpi: () => apiClient.get('/api/analytics/kpi').then(r => r.data),
  spending: (period = 'monthly') => apiClient.get('/api/analytics/spending', { params: { period } }).then(r => r.data),
  vendors: () => apiClient.get('/api/analytics/vendors').then(r => r.data),
  patterns: () => apiClient.get('/api/analytics/patterns').then(r => r.data),
  trends: () => apiClient.get('/api/analytics/trends').then(r => r.data),
  ask: (question) => apiClient.post('/api/analytics/ask', { question }).then(r => r.data),
}

// ── Audit API ─────────────────────────────────────────────────────────────

export const auditApi = {
  getBOMTrail: (bomId) =>
    apiClient.get(`/api/audit/bom/${bomId}`).then(r => r.data),
  getLog: (params = {}) =>
    apiClient.get('/api/audit', { params }).then(r => r.data),
  getStats: () =>
    apiClient.get('/api/audit/stats').then(r => r.data),
}

// ── Catalog API ───────────────────────────────────────────────────────────

export const catalogApi = {
  /** List items with optional search/category/vendor + pagination */
  list: ({ category, vendor, search, page = 1, limit = 50 } = {}) =>
    apiClient.get('/api/catalog', { params: { category, vendor, search, page, limit } }).then(r => r.data),

  /** All unique categories */
  categories: () =>
    apiClient.get('/api/catalog/categories').then(r => r.data),

  /** All unique vendors */
  vendors: () =>
    apiClient.get('/api/catalog/vendors').then(r => r.data),

  /** Look up a specific SKU */
  getBySku: (sku) =>
    apiClient.get(`/api/catalog/sku/${encodeURIComponent(sku)}`).then(r => r.data),
}

// ── EOL Check API ─────────────────────────────────────────────────────────

export const eolApi = {
  checkSku: (sku) =>
    apiClient.get(`/api/bom/eol/check/${encodeURIComponent(sku)}`).then(r => r.data),
  checkBom: (lineItems) =>
    apiClient.post('/api/bom/eol/check-bom', { line_items: lineItems }).then(r => r.data),
}

export const notifyApi = {
  sendEmail: ({ to, subject, body, bom_name }) =>
    apiClient.post('/api/notify/email', { to, subject, body, bom_name }).then(r => r.data),
}

export const ingestApi = {
  /**
   * Upload a file (File object) and trigger the ingest pipeline.
   * Returns { bom_id, message }.
   */
  uploadBom: (file, metadata = {}) => {
    const fd = new FormData()
    fd.append('file', file)
    if (metadata.project_name) fd.append('project_name', metadata.project_name)
    if (metadata.category) fd.append('category', metadata.category)
    return apiClient.post('/api/ingest/bom', fd, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data)
  },
  status: (bomId) => apiClient.get(`/api/ingest/status/${bomId}`).then(r => r.data),
}

export default apiClient


