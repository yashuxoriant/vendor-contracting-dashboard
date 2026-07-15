import { useState, useEffect, useCallback, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Grid, Paper, Chip, Button, IconButton, TextField,
  Select, MenuItem, FormControl, InputLabel, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Collapse, Alert, Tooltip, Dialog,
  DialogTitle, DialogContent, DialogActions, CircularProgress, LinearProgress,
} from '@mui/material'
import {
  Search, ExpandMore, ExpandLess, Send, Archive, Download,
  AutoAwesome, ContentCopy, Compare, CheckCircle, RateReview, Edit, Save, Close, Refresh,
  CloudUpload,
} from '@mui/icons-material'
import { setActiveBOMForRFQ, setCurrentBOM, archiveBOM, saveBOM, resetToSeed } from '../store/slices/bomSlice'
import { bomService } from '../services/api'

const fmt = (v) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
const fmtDate = (s) => new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })

const ST = {
  active:    { label: 'Active',    bg: '#D1FAE5', color: '#065F46' },
  draft:     { label: 'Draft',     bg: '#FEF3C7', color: '#92400E' },
  review:    { label: 'In Review', bg: '#DBEAFE', color: '#1E40AF' },
  approved:  { label: 'Approved',  bg: '#F3E8FF', color: '#6B21A8' },
  archived:  { label: 'Archived',  bg: '#F3F4F6', color: '#6B7280' },
}
const CC = {
  'Data Center / COLO': '#1F2937', 'SD-WAN': '#3B82F6', 'Cybersecurity': '#D04A02',
  'Network Equipment': '#10B981', 'M365 & Power Platform': '#8B5CF6', 'Cloud Infrastructure': '#F59E0B',
}
const SL = { fontSize: '0.58rem', fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.7px' }

// Convert backend snake_case BOM → frontend camelCase shape
function backendToFrontend(b) {
  return {
    id: b.bom_id,
    name: `${b.project_name} — ${b.category} BOM`,
    project: b.project_name,
    category: b.category,
    status: b.status === 'in_progress' ? 'draft' : b.status,
    version: b.version || 1,
    totalValue: b.totals?.total_otc || 0,
    createdAt: b.created_at,
    updatedAt: b.updated_at || b.created_at,
    notes: b.notes || '',
    approvals: b.approvals || [],
    lineItems: (b.line_items || []).map((item, idx) => ({
      id: `item_${idx}`,
      lineNo: item.line_number || idx + 1,
      description: item.description,
      category: item.category || '',
      sku: item.sku || '',
      qty: item.quantity,
      unit: item.term || '/unit',
      unitPrice: item.unit_price,
      extPrice: item.extended_price,
      vendor: item.vendor || '',
      status: item.eol_flag ? 'eol' : 'active',
      eolFlag: item.eol_flag || false,
      orderSequence: item.order_sequence,
    })),
  }
}

async function exportBOMExcel(bom) {
  try {
    const blob = await bomService.exportExcel(bom.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = bom.name.replace(/[^a-zA-Z0-9 _-]/g, '') + '.xlsx'
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch {
    // Fallback to CSV if backend unavailable
    const headers = ['Line No', 'Description', 'Category', 'Qty', 'Unit Price', 'Ext Price', 'Vendor']
    const rows = bom.lineItems.map(i => [i.lineNo, `"${i.description}"`, `"${i.category}"`, i.qty, i.unitPrice, i.extPrice, `"${i.vendor}"`])
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = bom.name + '_BOM.csv'
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }
}

export default function BOMLibraryPage() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const bomList = useSelector(s => s.bom.bomList)
  const [search, setSearch] = useState('')
  const [filterProject, setFilterProject] = useState('All')
  const [filterStatus, setFilterStatus] = useState('All')
  const [expandedId, setExpandedId] = useState(null)
  const [editingCell, setEditingCell] = useState(null)
  const [editValue, setEditValue] = useState('')
  const [compareIds, setCompareIds] = useState([])
  const [compareOpen, setCompareOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [backendError, setBackendError] = useState(null)

  // SharePoint upload state
  const [spUploadOpen, setSpUploadOpen] = useState(false)
  const [spFile, setSpFile] = useState(null)
  const [spFolder, setSpFolder] = useState('BOMs')
  const [spVendor, setSpVendor] = useState('')
  const [spCategory, setSpCategory] = useState('')
  const [spUploading, setSpUploading] = useState(false)
  const [spResult, setSpResult] = useState(null)
  const [ingestStatus, setIngestStatus] = useState(null)  // null | {status, chunks_upserted, ...}
  const [ingestPolling, setIngestPolling] = useState(false)
  const spFileRef = useRef(null)
  const ingestPollRef = useRef(null)

  // Poll /api/ingest/status/{bom_id} until terminal status
  const pollIngestStatus = (bomId) => {
    setIngestStatus({ status: 'processing' })
    setIngestPolling(true)
    let attempts = 0
    const maxAttempts = 60  // 60 × 3s = 3 minutes max
    ingestPollRef.current = setInterval(async () => {
      attempts++
      try {
        const r = await fetch(`/api/ingest/status/${bomId}`)
        if (r.ok) {
          const d = await r.json()
          setIngestStatus(d)
          if (d.status === 'indexed' || d.status === 'failed' || attempts >= maxAttempts) {
            clearInterval(ingestPollRef.current)
            setIngestPolling(false)
          }
        }
      } catch { /* ignore polling errors */ }
    }, 3000)
  }

  // Cleanup polling on unmount
  useEffect(() => () => clearInterval(ingestPollRef.current), [])

  const handleSpUpload = async () => {
    if (!spFile) return
    setSpUploading(true)
    setSpResult(null)
    setIngestStatus(null)
    try {
      const fd = new FormData()
      fd.append('file', spFile)
      fd.append('folder', spFolder)
      if (spVendor)   fd.append('vendor', spVendor)
      if (spCategory) fd.append('category', spCategory)
      const resp = await fetch('/api/sharepoint/upload', { method: 'POST', body: fd })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Upload failed')
      setSpResult({ ok: true, url: data.web_url, mock: data.mock, bomId: data.bom_id })
      if (data.bom_id) pollIngestStatus(data.bom_id)
    } catch (err) {
      setSpResult({ ok: false, msg: err.message })
    } finally {
      setSpUploading(false)
    }
  }

  // Load BOMs from backend on mount — merge into Redux
  const loadFromBackend = useCallback(async () => {
    setLoading(true)
    setBackendError(null)
    try {
      const data = await bomService.list()
      const boms = (data.boms || []).map(backendToFrontend)
      boms.forEach(b => dispatch(saveBOM(b)))
    } catch (err) {
      setBackendError('Could not reach backend — showing local data')
    } finally {
      setLoading(false)
    }
  }, [dispatch])

  useEffect(() => { loadFromBackend() }, [loadFromBackend])

  const filtered = bomList.filter(b => {
    if (filterProject !== 'All' && b.project !== filterProject) return false
    if (filterStatus !== 'All' && b.status !== filterStatus) return false
    if (search && !b.name.toLowerCase().includes(search.toLowerCase()) && !b.category.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  const projects = ['All', ...new Set(bomList.map(b => b.project))]
  const kpis = [
    { label: 'ACTIVE BOMs',  value: bomList.filter(b => b.status === 'active').length,    color: '#10B981' },
    { label: 'IN REVIEW',    value: bomList.filter(b => b.status === 'review').length,    color: '#3B82F6' },
    { label: 'TOTAL ITEMS',  value: bomList.reduce((s, b) => s + (b.lineItems?.length || 0), 0), color: '#8B5CF6' },
    { label: 'ACTIVE VALUE', value: fmt(bomList.filter(b => b.status === 'active').reduce((s, b) => s + b.totalValue, 0)), color: '#D04A02' },
  ]

  // Inline cell edit helpers
  const startEdit = (bomId, itemId, field, value) => { setEditingCell({ bomId, itemId, field }); setEditValue(String(value)) }
  const commitEdit = async (bom) => {
    if (!editingCell) return
    const newItems = bom.lineItems.map(i => {
      if (i.id !== editingCell.itemId) return i
      const updates = { ...i, [editingCell.field]: editingCell.field === 'qty' || editingCell.field === 'unitPrice' ? parseFloat(editValue) || 0 : editValue }
      updates.extPrice = (updates.qty || 1) * (updates.unitPrice || 0)
      return updates
    })
    const updated = { ...bom, lineItems: newItems, totalValue: newItems.reduce((s, i) => s + i.extPrice, 0), updatedAt: new Date().toISOString() }
    dispatch(saveBOM(updated))
    setEditingCell(null)
    // Persist to backend
    try {
      await bomService.update(bom.id, {
        line_items: newItems.map(i => ({
          line_number: i.lineNo, description: i.description, category: i.category,
          sku: i.sku, quantity: i.qty, unit_price: i.unitPrice, extended_price: i.extPrice,
          vendor: i.vendor, term: i.unit,
        })),
      })
    } catch { /* silent — Redux already updated */ }
  }

  // Duplicate BOM
  const duplicateBOM = (bom) => {
    const newBOM = {
      ...bom,
      id: 'bom_dup_' + Date.now(),
      name: bom.name + ' (Copy)',
      status: 'draft',
      version: 1,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      history: [{ version: 1, timestamp: new Date().toISOString(), action: 'Duplicated from ' + bom.name, changes: bom.lineItems.length + ' items copied', user: 'User', totalValue: bom.totalValue }],
    }
    dispatch(saveBOM(newBOM))
  }

  // Approval workflow
  const changeStatus = (bom, newStatus) => dispatch(saveBOM({ ...bom, status: newStatus, updatedAt: new Date().toISOString() }))

  // Compare BOMs
  const toggleCompare = (id) => {
    setCompareIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : prev.length < 2 ? [...prev, id] : [prev[1], id])
  }
  const compareBOMs = compareIds.map(id => bomList.find(b => b.id === id)).filter(Boolean)

  const EditableCell = ({ bom, item, field, display }) => {
    const isEditing = editingCell?.bomId === bom.id && editingCell?.itemId === item.id && editingCell?.field === field
    if (isEditing) return (
      <TextField size="small" value={editValue} onChange={e => setEditValue(e.target.value)} autoFocus
        onBlur={() => commitEdit(bom)} onKeyDown={e => { if (e.key === 'Enter') commitEdit(bom); if (e.key === 'Escape') setEditingCell(null) }}
        sx={{ width: field === 'description' ? 200 : 80, '& input': { fontSize: '0.68rem', py: '2px', px: '6px' } }} />
    )
    return (
      <Box onClick={() => startEdit(bom.id, item.id, field, field === 'qty' ? item.qty : field === 'unitPrice' ? item.unitPrice : item.vendor)}
        sx={{ cursor: 'text', '&:hover': { bgcolor: '#FEF3C7', borderRadius: '3px' }, px: 0.5, py: 0.2, display: 'inline-flex', alignItems: 'center', gap: 0.3 }}>
        <Typography sx={{ fontSize: '0.68rem' }}>{display}</Typography>
        <Edit sx={{ fontSize: 9, color: '#D0D5DD', opacity: 0 }} className="edit-icon" />
      </Box>
    )
  }

  return (
    <Box sx={{ bgcolor: '#FAFAFA', p: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', mb: 1.5 }}>
        <Box>
          <Typography sx={{ color: '#D04A02', fontWeight: 700, letterSpacing: '1px', textTransform: 'uppercase', fontSize: '0.6rem' }}>DOCUMENT REPOSITORY</Typography>
          <Typography sx={{ fontWeight: 700, color: '#1F2937', fontSize: '1.3rem', fontFamily: '"Playfair Display", serif', lineHeight: 1.2 }}>BOM Library</Typography>
          <Typography sx={{ color: '#6B7280', fontSize: '0.72rem' }}>All versions tracked - synchronized across modules - click any cell to edit inline</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          {backendError && <Alert severity="warning" sx={{ py: 0, fontSize: '0.7rem' }}>{backendError}</Alert>}
          <Tooltip title="Refresh from backend">
            <IconButton size="small" onClick={loadFromBackend} disabled={loading}>
              {loading ? <CircularProgress size={16} /> : <Refresh sx={{ fontSize: 18 }} />}
            </IconButton>
          </Tooltip>
          {compareIds.length === 2 && (
            <Button size="small" variant="outlined" startIcon={<Compare sx={{ fontSize: 14 }} />}
              onClick={() => setCompareOpen(true)}
              sx={{ textTransform: 'none', fontSize: '0.72rem', borderColor: '#3B82F6', color: '#3B82F6' }}>
              Compare Selected ({compareIds.length})
            </Button>
          )}
          <Button size="small" variant="outlined" startIcon={<CloudUpload sx={{ fontSize: 14 }} />}
            onClick={() => { setSpFile(null); setSpResult(null); setSpUploadOpen(true) }}
            sx={{ textTransform: 'none', fontSize: '0.72rem', borderColor: '#0078D4', color: '#0078D4', '&:hover': { bgcolor: '#EFF6FF' } }}>
            Upload to SharePoint
          </Button>
          <Button size="small" variant="outlined" startIcon={<Refresh sx={{ fontSize: 14 }} />}
            onClick={() => { if (window.confirm('Reset BOM library to the initial 4 BOMs? This cannot be undone.')) dispatch(resetToSeed()) }}
            sx={{ textTransform: 'none', fontSize: '0.72rem', borderColor: '#9CA3AF', color: '#6B7280', '&:hover': { bgcolor: '#F3F4F6' } }}>
            Reset to Initial 4
          </Button>
          <Button variant="contained" startIcon={<AutoAwesome sx={{ fontSize: 15 }} />}
            onClick={() => { dispatch(setCurrentBOM(null)); navigate('/chat') }}
            sx={{ bgcolor: '#D04A02', '&:hover': { bgcolor: '#A33A00' }, textTransform: 'none', fontSize: '0.75rem', fontWeight: 700 }}>
            New BOM via AI
          </Button>
        </Box>
      </Box>

      <Grid container spacing={1.25} sx={{ mb: 1.5 }}>
        {kpis.map(({ label, value, color }) => (
          <Grid item xs={6} md={3} key={label}>
            <Paper sx={{ p: 1.5, borderTop: '3px solid ' + color }}>
              <Typography sx={{ ...SL, mb: 0.4 }}>{label}</Typography>
              <Typography sx={{ fontWeight: 700, fontFamily: '"Playfair Display", serif', fontSize: '1.5rem', color, lineHeight: 1.1 }}>{value}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>

      <Box sx={{ display: 'flex', gap: 1, mb: 1.25, alignItems: 'center', flexWrap: 'wrap' }}>
        <TextField size="small" placeholder="Search BOMs..." value={search} onChange={e => setSearch(e.target.value)}
          InputProps={{ startAdornment: <Search sx={{ fontSize: 16, color: '#9CA3AF', mr: 0.5 }} /> }}
          sx={{ bgcolor: 'white', minWidth: 220, '& .MuiInputBase-input': { fontSize: '0.78rem', py: '6px' } }} />
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel sx={{ fontSize: '0.75rem' }}>Project</InputLabel>
          <Select value={filterProject} onChange={e => setFilterProject(e.target.value)} label="Project" sx={{ bgcolor: 'white', fontSize: '0.75rem' }}>
            {projects.map(p => <MenuItem key={p} value={p} sx={{ fontSize: '0.75rem' }}>{p}</MenuItem>)}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel sx={{ fontSize: '0.75rem' }}>Status</InputLabel>
          <Select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} label="Status" sx={{ bgcolor: 'white', fontSize: '0.75rem' }}>
            {['All', 'active', 'draft', 'review', 'approved', 'archived'].map(s => <MenuItem key={s} value={s} sx={{ fontSize: '0.75rem', textTransform: 'capitalize' }}>{s === 'All' ? 'All Status' : s}</MenuItem>)}
          </Select>
        </FormControl>
        <Typography sx={{ fontSize: '0.7rem', color: '#9CA3AF', ml: 'auto' }}>{filtered.length} of {bomList.length} BOMs</Typography>
      </Box>

      {filtered.length === 0 ? <Alert severity="info">No BOMs match your filters.</Alert> : filtered.map(bom => {
        const st = ST[bom.status] || ST.draft
        const catColor = CC[bom.category] || '#6B7280'
        const isX = expandedId === bom.id
        const catCounts = bom.lineItems?.reduce((a, i) => { a[i.category] = (a[i.category] || 0) + 1; return a }, {}) || {}
        const isComparing = compareIds.includes(bom.id)

        return (
          <Paper key={bom.id} sx={{ mb: 1.25, border: isComparing ? '2px solid #3B82F6' : '1px solid #E5E7EB', overflow: 'hidden' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 1.5, borderLeft: '5px solid ' + catColor }}>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.4, flexWrap: 'wrap' }}>
                  <Typography sx={{ fontWeight: 700, fontSize: '0.88rem', color: '#1F2937' }}>{bom.name}</Typography>
                  <Chip label={st.label} size="small" sx={{ bgcolor: st.bg, color: st.color, fontWeight: 700, fontSize: '0.62rem', height: 18 }} />
                  <Chip label={'v' + bom.version} size="small" sx={{ bgcolor: '#F3F4F6', color: '#374151', fontWeight: 700, fontSize: '0.62rem', height: 18 }} />
                </Box>
                <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
                  {[['Project', bom.project], ['Category', bom.category], ['Items', (bom.lineItems?.length || 0) + ' items'], ['By', bom.createdBy], ['Updated', fmtDate(bom.updatedAt)]].map(([k, v]) => (
                    <Typography key={k} sx={{ fontSize: '0.65rem', color: '#6B7280' }}>{v}</Typography>
                  ))}
                </Box>
              </Box>
              <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                <Typography sx={{ fontWeight: 700, fontFamily: '"Playfair Display", serif', fontSize: '1.1rem', color: '#1F2937' }}>{fmt(bom.totalValue)}</Typography>
                <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF' }}>Total Value</Typography>
              </Box>
              {/* Action buttons */}
              <Box sx={{ display: 'flex', gap: 0.25, flexShrink: 0, flexWrap: 'wrap' }}>
                <Tooltip title="Edit in AI Chat"><IconButton size="small" onClick={() => { dispatch(setCurrentBOM(bom)); navigate('/chat') }} sx={{ color: '#D04A02' }}><AutoAwesome sx={{ fontSize: 16 }} /></IconButton></Tooltip>
                <Tooltip title="Send to RFQ"><IconButton size="small" onClick={() => { dispatch(setActiveBOMForRFQ(bom)); navigate('/rfq-builder') }} sx={{ color: '#3B82F6' }}><Send sx={{ fontSize: 16 }} /></IconButton></Tooltip>
                <Tooltip title="Duplicate BOM"><IconButton size="small" onClick={() => duplicateBOM(bom)} sx={{ color: '#8B5CF6' }}><ContentCopy sx={{ fontSize: 16 }} /></IconButton></Tooltip>
                <Tooltip title="Export CSV"><IconButton size="small" onClick={() => exportBOMExcel(bom)} sx={{ color: '#6B7280' }}><Download sx={{ fontSize: 16 }} /></IconButton></Tooltip>
                <Tooltip title={isComparing ? 'Remove from comparison' : 'Add to comparison'}>
                  <IconButton size="small" onClick={() => toggleCompare(bom.id)} sx={{ color: isComparing ? '#3B82F6' : '#6B7280', bgcolor: isComparing ? '#EFF6FF' : 'transparent' }}>
                    <Compare sx={{ fontSize: 16 }} />
                  </IconButton>
                </Tooltip>
                {/* Approval workflow buttons */}
                {bom.status === 'draft' && <Tooltip title="Submit for Review"><IconButton size="small" onClick={() => changeStatus(bom, 'review')} sx={{ color: '#3B82F6' }}><RateReview sx={{ fontSize: 16 }} /></IconButton></Tooltip>}
                {bom.status === 'review' && <Tooltip title="3-Party Approval"><IconButton size="small" onClick={() => navigate(`/bom-review/${bom.id}`)} sx={{ color: '#10B981' }}><CheckCircle sx={{ fontSize: 16 }} /></IconButton></Tooltip>}
                {bom.status === 'approved' && <Tooltip title="Mark Active"><IconButton size="small" onClick={() => changeStatus(bom, 'active')} sx={{ color: '#10B981' }}><CheckCircle sx={{ fontSize: 16 }} /></IconButton></Tooltip>}
                {bom.status !== 'archived' && <Tooltip title="Archive"><IconButton size="small" onClick={() => dispatch(archiveBOM(bom.id))} sx={{ color: '#9CA3AF' }}><Archive sx={{ fontSize: 16 }} /></IconButton></Tooltip>}
                <IconButton size="small" onClick={() => setExpandedId(isX ? null : bom.id)} sx={{ color: '#6B7280' }}>
                  {isX ? <ExpandLess sx={{ fontSize: 18 }} /> : <ExpandMore sx={{ fontSize: 18 }} />}
                </IconButton>
              </Box>
            </Box>
            <Box sx={{ px: 1.75, pb: 0.75, display: 'flex', gap: 1.25, flexWrap: 'wrap' }}>
              {Object.entries(catCounts).map(([cat, cnt]) => (
                <Box key={cat} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <Box sx={{ width: 5, height: 5, bgcolor: CC[cat] || '#9CA3AF', borderRadius: '2px' }} />
                  <Typography sx={{ fontSize: '0.6rem', color: '#6B7280' }}>{cat} ({cnt})</Typography>
                </Box>
              ))}
            </Box>

            <Collapse in={isX}>
              <Box sx={{ borderTop: '1px solid #F3F4F6', p: 1.5 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.75 }}>
                  <Typography sx={{ ...SL }}>LINE ITEMS - click any cell to edit inline</Typography>
                  <Chip label="Tip: click Qty, Unit Price or Vendor to edit" size="small" sx={{ fontSize: '0.58rem', height: 16, bgcolor: '#FEF3C7', color: '#92400E' }} />
                </Box>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                        {['#', 'Description', 'Category', 'Qty', 'Unit', 'Unit Price', 'Ext. Price', 'Vendor', 'Status'].map(h => (
                          <TableCell key={h} sx={{ fontSize: '0.58rem', fontWeight: 700, textTransform: 'uppercase', py: 0.4, color: '#6B7280' }}>{h}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {bom.lineItems?.map(item => (
                        <TableRow key={item.id} sx={{ '&:hover': { bgcolor: '#FFFBF9' } }}>
                          <TableCell sx={{ fontSize: '0.65rem', py: 0.35, color: '#9CA3AF', fontWeight: 600 }}>{item.lineNo}</TableCell>
                          <TableCell sx={{ py: 0.35, maxWidth: 260 }}>
                            <EditableCell bom={bom} item={item} field="description" display={item.description} />
                          </TableCell>
                          <TableCell sx={{ py: 0.35 }}>
                            <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.4 }}>
                              <Box sx={{ width: 5, height: 5, borderRadius: '1px', bgcolor: CC[item.category] || '#9CA3AF' }} />
                              <Typography sx={{ fontSize: '0.62rem' }}>{item.category}</Typography>
                            </Box>
                          </TableCell>
                          <TableCell sx={{ py: 0.35 }}>
                            <EditableCell bom={bom} item={item} field="qty" display={item.qty} />
                          </TableCell>
                          <TableCell sx={{ fontSize: '0.62rem', py: 0.35, color: '#6B7280' }}>{item.unit}</TableCell>
                          <TableCell sx={{ py: 0.35 }}>
                            <EditableCell bom={bom} item={item} field="unitPrice" display={fmt(item.unitPrice)} />
                          </TableCell>
                          <TableCell sx={{ fontSize: '0.7rem', py: 0.35, fontWeight: 700 }}>{fmt(item.extPrice)}</TableCell>
                          <TableCell sx={{ py: 0.35 }}>
                            <EditableCell bom={bom} item={item} field="vendor" display={item.vendor} />
                          </TableCell>
                          <TableCell sx={{ py: 0.35 }}>
                            <Chip label={item.status} size="small" sx={{ fontSize: '0.58rem', height: 16,
                              bgcolor: item.status === 'quoted' ? '#D1FAE5' : item.status === 'pending' ? '#FEF3C7' : '#F3F4F6',
                              color: item.status === 'quoted' ? '#065F46' : item.status === 'pending' ? '#92400E' : '#6B7280' }} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 0.75, gap: 2, borderTop: '1px solid #F3F4F6', pt: 0.75 }}>
                  <Typography sx={{ fontSize: '0.68rem', color: '#6B7280' }}>{bom.lineItems?.filter(i => i.status === 'quoted').length}/{bom.lineItems?.length} quoted</Typography>
                  <Typography sx={{ fontWeight: 700, fontSize: '0.75rem' }}>Total: {fmt(bom.totalValue)}</Typography>
                </Box>

                {/* Version history */}
                <Typography sx={{ ...SL, mb: 0.75, mt: 1.25 }}>VERSION HISTORY</Typography>
                {bom.history?.slice().reverse().map((h, i) => (
                  <Box key={i} sx={{ display: 'flex', gap: 1.25, mb: 0.75, alignItems: 'flex-start' }}>
                    <Box sx={{ width: 20, height: 20, borderRadius: '50%', bgcolor: i === 0 ? '#D04A02' : '#F3F4F6', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Typography sx={{ fontSize: '0.55rem', fontWeight: 700, color: i === 0 ? 'white' : '#6B7280' }}>v{h.version}</Typography>
                    </Box>
                    <Box>
                      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                        <Typography sx={{ fontSize: '0.7rem', fontWeight: 600, color: '#1F2937' }}>{h.action}</Typography>
                        <Typography sx={{ fontSize: '0.6rem', color: '#9CA3AF' }}>{fmtDate(h.timestamp)} - {h.user}</Typography>
                        {h.totalValue && <Typography sx={{ fontSize: '0.6rem', color: i === 0 ? '#D04A02' : '#9CA3AF', fontWeight: 600 }}>{fmt(h.totalValue)}</Typography>}
                      </Box>
                      <Typography sx={{ fontSize: '0.62rem', color: '#6B7280' }}>{h.changes}</Typography>
                    </Box>
                  </Box>
                ))}
              </Box>
            </Collapse>
          </Paper>
        )
      })}

      {/* Compare Dialog */}
      <Dialog open={compareOpen} onClose={() => setCompareOpen(false)} maxWidth="xl" fullWidth>
        <DialogTitle sx={{ fontSize: '0.9rem', fontWeight: 700, pb: 1 }}>
          BOM Comparison
          <IconButton size="small" onClick={() => setCompareOpen(false)} sx={{ float: 'right' }}><Close sx={{ fontSize: 16 }} /></IconButton>
        </DialogTitle>
        <DialogContent>
          {compareBOMs.length === 2 && (
            <Grid container spacing={2}>
              {compareBOMs.map((bom, idx) => (
                <Grid item xs={6} key={bom.id}>
                  <Box sx={{ bgcolor: idx === 0 ? '#FDF3ED' : '#EFF6FF', p: 1.25, borderRadius: 1, mb: 1.5, border: '1px solid ' + (idx === 0 ? '#FBBF9F' : '#BFDBFE') }}>
                    <Typography sx={{ fontWeight: 700, fontSize: '0.85rem' }}>{bom.name}</Typography>
                    <Box sx={{ display: 'flex', gap: 1, mt: 0.5 }}>
                      <Chip label={'v' + bom.version} size="small" sx={{ fontSize: '0.6rem', height: 18 }} />
                      <Chip label={bom.status} size="small" sx={{ fontSize: '0.6rem', height: 18, bgcolor: ST[bom.status]?.bg, color: ST[bom.status]?.color }} />
                      <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, color: idx === 0 ? '#D04A02' : '#1D4ED8' }}>{fmt(bom.totalValue)}</Typography>
                    </Box>
                  </Box>
                  <TableContainer component={Paper} sx={{ border: '1px solid #F3F4F6' }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                          {['#', 'Description', 'Qty', 'Unit Price', 'Ext Price', 'Vendor'].map(h => (
                            <TableCell key={h} sx={{ fontSize: '0.58rem', fontWeight: 700, py: 0.4, textTransform: 'uppercase', color: '#6B7280' }}>{h}</TableCell>
                          ))}
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {bom.lineItems?.map(item => {
                          const other = compareBOMs[1 - idx]?.lineItems?.find(x => x.lineNo === item.lineNo)
                          const priceDiff = other && item.extPrice !== other.extPrice
                          const cheaper = other && item.extPrice < other.extPrice
                          return (
                            <TableRow key={item.id} sx={{ bgcolor: priceDiff ? (cheaper ? '#F0FDF4' : '#FFF7F7') : 'transparent' }}>
                              <TableCell sx={{ fontSize: '0.62rem', py: 0.35, color: '#9CA3AF' }}>{item.lineNo}</TableCell>
                              <TableCell sx={{ fontSize: '0.65rem', py: 0.35, maxWidth: 180 }} noWrap>{item.description}</TableCell>
                              <TableCell sx={{ fontSize: '0.68rem', py: 0.35 }}>{item.qty}</TableCell>
                              <TableCell sx={{ fontSize: '0.68rem', py: 0.35 }}>{fmt(item.unitPrice)}</TableCell>
                              <TableCell sx={{ fontSize: '0.7rem', py: 0.35, fontWeight: 700, color: priceDiff ? (cheaper ? '#10B981' : '#EF4444') : '#374151' }}>
                                {fmt(item.extPrice)}
                                {priceDiff && <Typography component="span" sx={{ fontSize: '0.55rem', ml: 0.5 }}>{cheaper ? 'lower' : 'higher'}</Typography>}
                              </TableCell>
                              <TableCell sx={{ fontSize: '0.62rem', py: 0.35 }}>{item.vendor}</TableCell>
                            </TableRow>
                          )
                        })}
                        <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                          <TableCell colSpan={4} sx={{ fontSize: '0.7rem', fontWeight: 700, py: 0.5 }}>TOTAL</TableCell>
                          <TableCell sx={{ fontSize: '0.8rem', fontWeight: 700, color: idx === 0 ? '#D04A02' : '#1D4ED8', py: 0.5 }}>{fmt(bom.totalValue)}</TableCell>
                          <TableCell />
                        </TableRow>
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Grid>
              ))}
              {/* Diff summary */}
              <Grid item xs={12}>
                <Paper sx={{ p: 1.25, bgcolor: '#F9FAFB', border: '1px solid #E5E7EB' }}>
                  <Typography sx={{ fontWeight: 700, fontSize: '0.75rem', mb: 0.75 }}>Comparison Summary</Typography>
                  <Box sx={{ display: 'flex', gap: 3 }}>
                    <Box>
                      <Typography sx={{ ...SL }}>DIFFERENCE</Typography>
                      <Typography sx={{ fontWeight: 700, fontSize: '1rem', color: compareBOMs[0].totalValue < compareBOMs[1].totalValue ? '#10B981' : '#EF4444' }}>
                        {fmt(Math.abs(compareBOMs[0].totalValue - compareBOMs[1].totalValue))}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography sx={{ ...SL }}>CHEAPER BOM</Typography>
                      <Typography sx={{ fontWeight: 700, fontSize: '0.8rem', color: '#10B981' }}>
                        {compareBOMs[0].totalValue < compareBOMs[1].totalValue ? compareBOMs[0].name : compareBOMs[1].name}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography sx={{ ...SL }}>ITEMS COMPARED</Typography>
                      <Typography sx={{ fontWeight: 700, fontSize: '0.8rem' }}>{Math.max(compareBOMs[0].lineItems?.length || 0, compareBOMs[1].lineItems?.length || 0)}</Typography>
                    </Box>
                  </Box>
                </Paper>
              </Grid>
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button size="small" onClick={() => setCompareOpen(false)} sx={{ textTransform: 'none', fontSize: '0.72rem' }}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* ── SharePoint Upload + Ingest Pipeline Dialog ────────────────────── */}
      <Dialog open={spUploadOpen} onClose={() => !spUploading && !ingestPolling && setSpUploadOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ pb: 0.5, display: 'flex', alignItems: 'center', gap: 1 }}>
          <CloudUpload sx={{ color: '#0078D4', fontSize: 20 }} />
          <Typography sx={{ fontWeight: 700, fontSize: '0.95rem' }}>Upload BOM to SharePoint</Typography>
        </DialogTitle>
        <DialogContent sx={{ pt: 1.5 }}>
          <Typography sx={{ fontSize: '0.72rem', color: '#6B7280', mb: 1.5 }}>
            File is uploaded to SharePoint then automatically indexed for AI search.
          </Typography>

          {/* Folder */}
          <TextField size="small" fullWidth label="Destination folder" value={spFolder}
            onChange={e => setSpFolder(e.target.value)}
            sx={{ mb: 1, '& label': { fontSize: '0.75rem' }, '& input': { fontSize: '0.8rem' } }}
            placeholder="e.g. BOMs/Panasonic" />

          {/* Vendor + Category */}
          <Box sx={{ display: 'flex', gap: 1, mb: 1.5 }}>
            <TextField size="small" fullWidth label="Vendor" value={spVendor}
              onChange={e => setSpVendor(e.target.value)}
              sx={{ '& label': { fontSize: '0.75rem' }, '& input': { fontSize: '0.8rem' } }}
              placeholder="e.g. Cisco" />
            <TextField size="small" fullWidth label="Category" value={spCategory}
              onChange={e => setSpCategory(e.target.value)}
              sx={{ '& label': { fontSize: '0.75rem' }, '& input': { fontSize: '0.8rem' } }}
              placeholder="e.g. Network Equipment" />
          </Box>

          {/* File drop zone */}
          <Box onClick={() => spFileRef.current?.click()} sx={{
            border: '2px dashed #D1D5DB', borderRadius: 1.5, p: 2, textAlign: 'center',
            cursor: 'pointer', bgcolor: '#F9FAFB',
            '&:hover': { borderColor: '#0078D4', bgcolor: '#EFF6FF' },
          }}>
            <CloudUpload sx={{ fontSize: 32, color: spFile ? '#0078D4' : '#9CA3AF', mb: 0.5 }} />
            <Typography sx={{ fontSize: '0.78rem', color: spFile ? '#0078D4' : '#6B7280', fontWeight: spFile ? 600 : 400 }}>
              {spFile ? spFile.name : 'Click to select a file'}
            </Typography>
            <Typography sx={{ fontSize: '0.65rem', color: '#9CA3AF' }}>PDF, Excel, Word, CSV — max 20 MB</Typography>
            <input ref={spFileRef} type="file" hidden
              accept=".pdf,.xlsx,.xls,.docx,.doc,.csv,.txt"
              onChange={e => { setSpFile(e.target.files[0] || null); setSpResult(null); setIngestStatus(null) }} />
          </Box>

          {spUploading && <LinearProgress sx={{ mt: 1.5, borderRadius: 1 }} />}

          {/* Upload result */}
          {spResult && (
            <Alert severity={spResult.ok ? 'success' : 'error'} sx={{ mt: 1.5, fontSize: '0.72rem', py: 0.5 }}>
              {spResult.ok
                ? <>{spResult.mock ? 'Demo mode — ' : ''}Uploaded! Embedding pipeline started.{' '}
                    {spResult.url && <a href={spResult.url} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit' }}>Open ↗</a>}
                  </>
                : spResult.msg}
            </Alert>
          )}

          {/* Ingest pipeline status */}
          {ingestStatus && (
            <Box sx={{ mt: 1.5, p: 1.5, borderRadius: 1.5, bgcolor: '#F0F9FF', border: '1px solid #BAE6FD' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                {ingestStatus.status === 'indexed' ? (
                  <CheckCircle sx={{ color: '#10B981', fontSize: 16 }} />
                ) : ingestStatus.status === 'failed' ? (
                  <RateReview sx={{ color: '#EF4444', fontSize: 16 }} />
                ) : (
                  <CircularProgress size={14} sx={{ color: '#0078D4' }} />
                )}
                <Typography sx={{ fontSize: '0.72rem', fontWeight: 700, color:
                  ingestStatus.status === 'indexed' ? '#065F46' :
                  ingestStatus.status === 'failed'  ? '#991B1B' : '#0369A1' }}>
                  {ingestStatus.status === 'indexed'    ? `✓ Indexed — ${ingestStatus.chunks_upserted || 0} chunks ready for AI` :
                   ingestStatus.status === 'failed'     ? `✗ Indexing failed: ${ingestStatus.detail || ''}` :
                   ingestStatus.status === 'processing' ? 'Embedding pipeline running…' :
                   `Status: ${ingestStatus.status}`}
                </Typography>
              </Box>
              {ingestPolling && <LinearProgress sx={{ borderRadius: 1, height: 3 }} />}
              {ingestStatus.status === 'indexed' && (
                <Typography sx={{ fontSize: '0.65rem', color: '#6B7280', mt: 0.5 }}>
                  BOM ID: {ingestStatus.bom_id} — the AI chat can now reference this BOM
                </Typography>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 2, pb: 1.5 }}>
          <Button size="small"
            onClick={() => { setSpUploadOpen(false); clearInterval(ingestPollRef.current); setIngestPolling(false) }}
            disabled={spUploading}
            sx={{ textTransform: 'none', fontSize: '0.72rem' }}>Close</Button>
          <Button size="small" variant="contained" disabled={!spFile || spUploading}
            onClick={handleSpUpload}
            sx={{ bgcolor: '#0078D4', '&:hover': { bgcolor: '#005A9E' }, textTransform: 'none', fontSize: '0.72rem' }}>
            {spUploading ? 'Uploading…' : 'Upload & Index'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
