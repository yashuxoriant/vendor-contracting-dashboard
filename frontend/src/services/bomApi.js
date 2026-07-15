import apiClient from './api'

// Chat & BOM Creation
export const chatService = {
  startSession: async (category) => {
    const response = await apiClient.post('/api/bom/start', { category })
    return response.data
  },

  sendMessage: async (sessionId, message) => {
    const response = await apiClient.post('/api/bom/chat', {
      session_id: sessionId,
      message,
    })
    return response.data
  },

  getSession: async (sessionId) => {
    const response = await apiClient.get(`/api/bom/session/${sessionId}`)
    return response.data
  },
}

// BOM Management
export const bomService = {
  getBOM: async (bomId) => {
    const response = await apiClient.get(`/api/bom/${bomId}`)
    return response.data
  },

  listBOMs: async (filters = {}) => {
    const response = await apiClient.get('/api/bom', { params: filters })
    return response.data
  },

  updateBOM: async (bomId, updates) => {
    const response = await apiClient.put(`/api/bom/${bomId}`, updates)
    return response.data
  },

  exportBOM: async (bomId, format = 'excel') => {
    const response = await apiClient.post(
      `/api/bom/export/${format}`,
      { bom_id: bomId },
      { responseType: 'blob' }
    )
    return response.data
  },

  validateBOM: async (bom) => {
    const response = await apiClient.post('/api/bom/validate', bom)
    return response.data
  },
}

// Analytics
export const analyticsService = {
  getSpending: async (period = 'monthly') => {
    const response = await apiClient.get('/api/analytics/spending', {
      params: { period },
    })
    return response.data
  },

  getVendorPerformance: async () => {
    const response = await apiClient.get('/api/analytics/vendors')
    return response.data
  },

  getPatterns: async () => {
    const response = await apiClient.get('/api/analytics/patterns')
    return response.data
  },

  getTrends: async () => {
    const response = await apiClient.get('/api/analytics/trends')
    return response.data
  },
}

// Templates
export const templateService = {
  listTemplates: async () => {
    const response = await apiClient.get('/api/templates')
    return response.data
  },

  getTemplate: async (category) => {
    const response = await apiClient.get(`/api/templates/${category}`)
    return response.data
  },
}

// Health Check
export const healthCheck = async () => {
  const response = await apiClient.get('/health')
  return response.data
}
