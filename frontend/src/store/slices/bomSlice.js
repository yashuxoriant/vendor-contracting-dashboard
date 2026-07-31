import { createSlice } from '@reduxjs/toolkit'

const mkId = () => `li_${Date.now()}_${Math.random().toString(36).slice(2,7)}`

const bomSlice = createSlice({
  name: 'bom',
  initialState: {
    currentBOM: null,
    activeBOMForRFQ: null,
    bomList: [],
    loading: false,
    error: null,
    deletedIds: (() => { try { return JSON.parse(localStorage.getItem('bom_deleted_ids') || '[]') } catch { return [] } })(),
  },
  reducers: {
    setCurrentBOM:      (s, a) => { s.currentBOM = a.payload },
    setActiveBOMForRFQ: (s, a) => { s.activeBOMForRFQ = a.payload },
    saveBOM: (s, a) => {
      if (s.deletedIds.includes(a.payload?.id)) return
      const bom = { ...a.payload, updatedAt: new Date().toISOString() }
      const idx = s.bomList.findIndex(b => b.id === bom.id)
      if (idx >= 0) s.bomList[idx] = bom; else s.bomList.unshift(bom)
      // Note: do NOT set s.currentBOM here — that should be done via setCurrentBOM
      // explicitly. Auto-setting it here caused every BOM loaded from the backend
      // to overwrite the active BOM in the chat preview panel.
    },
    addLineItem: (s, a) => {
      if (!s.currentBOM) return
      const item = { ...a.payload, id: mkId(), lineNo: s.currentBOM.lineItems.length + 1, status: 'draft' }
      s.currentBOM.lineItems.push(item)
      s.currentBOM.totalValue = s.currentBOM.lineItems.reduce((t, i) => t + (i.extPrice || 0), 0)
    },
    updateLineItem: (s, a) => {
      if (!s.currentBOM) return
      const { id, updates } = a.payload
      const item = s.currentBOM.lineItems.find(i => i.id === id)
      if (item) {
        Object.assign(item, updates)
        item.extPrice = (item.qty || 1) * (item.unitPrice || 0)
        s.currentBOM.totalValue = s.currentBOM.lineItems.reduce((t, i) => t + (i.extPrice || 0), 0)
      }
    },
    removeLineItem: (s, a) => {
      if (!s.currentBOM) return
      s.currentBOM.lineItems = s.currentBOM.lineItems.filter(i => i.id !== a.payload)
      s.currentBOM.lineItems.forEach((i, idx) => { i.lineNo = idx + 1 })
      s.currentBOM.totalValue = s.currentBOM.lineItems.reduce((t, i) => t + (i.extPrice || 0), 0)
    },
    deleteBOM: (s, a) => {
      const id = a.payload
      s.bomList = s.bomList.filter(b => b.id !== id)
      if (s.currentBOM?.id === id) s.currentBOM = null
      if (!s.deletedIds.includes(id)) {
        s.deletedIds.push(id)
        try { localStorage.setItem('bom_deleted_ids', JSON.stringify(s.deletedIds)) } catch (_) {}
      }
    },
    archiveBOM: (s, a) => { const b = s.bomList.find(x => x.id === a.payload); if (b) b.status = 'archived' },
    setBOMList: (s, a) => { s.bomList = a.payload },
    setLoading:  (s, a) => { s.loading = a.payload },
    setError:    (s, a) => { s.error = a.payload },
  },
})

export const { setCurrentBOM, setActiveBOMForRFQ, saveBOM, deleteBOM, addLineItem, updateLineItem, removeLineItem, archiveBOM, setBOMList, setLoading, setError } = bomSlice.actions
export default bomSlice.reducer
