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
  startSession: (category, project = 'New Project', userId = 'demo_user') =>
    apiClient.post('/api/bom/start', { category, project, user_id: userId }).then(r => r.data),
  sendMessage: (sessionId, message, userId = 'demo_user') =>
    apiClient.post('/api/bom/chat', { session_id: sessionId, message, user_id: userId }).then(r => r.data),
  /** Send a message with an optional file attachment */
  sendMessageWithAttachment: (sessionId, message, file, category, userId = 'demo_user') => {
    const fd = new FormData()
    fd.append('session_id', sessionId)
    fd.append('message', message || '')
    fd.append('user_id', userId)
    fd.append('category', category || 'BOMs')
    if (file) fd.append('file', file)
    return apiClient.post('/api/bom/chat-with-attachment', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
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

  /** Update a BOM */
  update: (bomId, data) =>
    apiClient.put(`/api/bom/${bomId}`, data).then(r => r.data),

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

export default apiClient


