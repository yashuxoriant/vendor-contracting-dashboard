import { createSlice } from '@reduxjs/toolkit'

// Notification types and their display config
export const NOTIF_TYPES = {
  bom_created:       { color: '#3B82F6', bg: '#EFF6FF', icon: '📄' },
  bom_saved:         { color: '#10B981', bg: '#ECFDF5', icon: '💾' },
  bom_ready:         { color: '#8B5CF6', bg: '#F5F3FF', icon: '✅' },
  approval_request:  { color: '#F59E0B', bg: '#FFFBEB', icon: '🔔' },
  approved:          { color: '#10B981', bg: '#ECFDF5', icon: '✅' },
  changes_requested: { color: '#F59E0B', bg: '#FFFBEB', icon: '⚠️' },
  rejected:          { color: '#EF4444', bg: '#FEF2F2', icon: '❌' },
  all_approved:      { color: '#10B981', bg: '#ECFDF5', icon: '🎉' },
  rebuild_required:  { color: '#D04A02', bg: '#FFF7F0', icon: '🔧' },
  info:              { color: '#6B7280', bg: '#F9FAFB', icon: 'ℹ️' },
}

const MAX_NOTIFICATIONS = 50

const notificationsSlice = createSlice({
  name: 'notifications',
  initialState: {
    items: [],        // [{id, type, title, message, timestamp, read, targetRole, bomName}]
    unreadCount: 0,
  },
  reducers: {
    pushNotification: (state, action) => {
      const notif = {
        id: Date.now() + '_' + Math.random().toString(36).slice(2),
        timestamp: new Date().toISOString(),
        read: false,
        ...action.payload,
      }
      state.items.unshift(notif)
      // Cap at MAX_NOTIFICATIONS
      if (state.items.length > MAX_NOTIFICATIONS) state.items.length = MAX_NOTIFICATIONS
      state.unreadCount = state.items.filter(n => !n.read).length
    },
    markRead: (state, action) => {
      const item = state.items.find(n => n.id === action.payload)
      if (item) item.read = true
      state.unreadCount = state.items.filter(n => !n.read).length
    },
    markAllRead: (state) => {
      state.items.forEach(n => { n.read = true })
      state.unreadCount = 0
    },
    deleteNotification: (state, action) => {
      state.items = state.items.filter(n => n.id !== action.payload)
      state.unreadCount = state.items.filter(n => !n.read).length
    },
    clearAll: (state) => {
      state.items = []
      state.unreadCount = 0
    },
  },
})

export const { pushNotification, markRead, markAllRead, deleteNotification, clearAll } = notificationsSlice.actions
export default notificationsSlice.reducer
