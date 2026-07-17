import { useState, useEffect, useCallback, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Grid, Paper, Chip, Button, IconButton, TextField,
  MenuItem, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Alert, Tooltip, Dialog, DialogTitle, DialogContent, DialogActions,
  CircularProgress, Divider,
} from '@mui/material'
import {
  Search, Download, AutoAwesome, Send, Archive, CheckCircle,
  RateReview, Refresh, CloudUpload, Close, ArrowBack, FilterList, Sync,
} from '@mui/icons-material'
import { setActiveBOMForRFQ, setCurrentBOM, archiveBOM, saveBOM } from '../store/slices/bomSlice'
import { bomService } from '../services/api'

const fmt = (v) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v || 0)
const fmtDate = (s) => {
  if (!s) return '--'
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// Category definitions (Chetan: "big baseball cards across multiple categories")
const CATEGORIES = [
  {
    key: 'Data Center / COLO',
    label: 'Data Center / COLO',
    icon: '\uD83C\uDFE2',
    accent: '#1F2937',
    light: '#F9FAFB',
    desc: 'Top-of-rack, leaf/spine, power, cooling, colo cage',
  },
  {
    key: 'Network & Telecom',
    label: 'Network & Telecom',
    icon: '\uD83C\uDF10',
    accent: '#1D4ED8',
    light: '#EFF6FF',
    desc: 'LAN/WAN, switches, firewalls, access points, voice/UCaaS',
  },
  {
    key: 'SD-WAN',
    label: 'SD-WAN / WAN',
    icon: '\uD83D\uDD17',
    accent: '#3B82F6',
    light: '#EFF6FF',
    desc: 'SD-WAN routers, carrier circuits, MPLS, broadband',
  },
  {
    key: 'Cybersecurity',
    label: 'Cybersecurity',
    icon: '\uD83D\uDD10',
    accent: '#D04A02',
    light: '#FFF7ED',
    desc: 'NGFW, EDR, SIEM, PAM, Zero Trust, compliance tooling',
  },
  {
    key: 'M365 & Power Platform',
    label: 'M365 & Licensing',
    icon: '\uD83D\uDCBC',
    accent: '#7C3AED',
    light: '#F5F3FF',
    desc: 'E3/E5 licensing, Power Apps, Teams Phone, FastTrack',
  },
  {
    key: 'Cloud Infrastructure',
    label: 'Cloud Infrastructure',
    icon: '\u2601\uFE0F',
    accent: '#D97706',
    light: '#FFFBEB',
    desc: 'Azure, AWS, GCP -- IaaS, PaaS, landing zones, ExpressRoute',
  },
  {
    key: 'EOL Replacement',
    label: 'EOL Replacement',
    icon: '\u26A0\uFE0F',
    accent: '#DC2626',
    light: '#FEF2F2',
    desc: 'End-of-life / end-of-support hardware replacement BOMs',
  },
  {
    key: 'Network Equipment',
    label: 'Network Equipment',
    icon: '\uD83D\uDDA5',
    accent: '#059669',
    light: '#ECFDF5',
    desc: 'Switches, routers, access points, wireless controllers',
  },
]

// Vendor filter chips (Chetan: "filter by Cisco, filter by Microsoft")
const VENDOR_FILTERS = ['All', 'Cisco', 'Fortinet', 'Palo Alto', 'Juniper', 'Aruba', 'Microsoft', 'CDW', 'NTT Data']

const STATUS_STYLE = {
  active:   { bg: '#D1FAE5', color: '#065F46', label: 'Active' },
  draft:    { bg: '#FEF3C7', color: '#92400E', label: 'Draft' },
  review:   { bg: '#DBEAFE', color: '#1E40AF', label: 'In Review' },
  approved: { bg: '#F3E8FF', color: '#6B21A8', label: 'Approved' },
  archived: { bg: '#F3F4F6', color: '#6B7280', label: 'Archived' },
}

function backendToFrontend(b) {
  return {
    id: b.bom_id || b.id || b._id,
    name: b.name || ((b.project_name || b.project || 'Unknown') + ' -- ' + (b.category || '') + ' BOM'),
    project: b.project_name || b.project || 'Unknown Project',
    category: b.category || 'Data Center / COLO',
    status: b.status === 'in_progress' ? 'draft' : (b.status || 'draft'),
    version: b.version || 1,
    totalValue: b.totals?.total_otc || b.total_value || 0,
    createdAt: b.created_at,
    updatedAt: b.updated_at || b.created_at,
    notes: b.notes || '',
    lineItems: (b.line_items || []).map((item, idx) => ({
      id: 'item_' + idx,
      lineNo: item.line_number || idx + 1,
      description: item.description || '',
      category: item.category || '',
      sku: item.sku || '',
      qty: item.qty || item.quantity || 1,
      unit: item.unit || '/unit',
      unitPrice: item.unit_price || 0,
      extPrice: item.extended_price || item.ext_price || 0,
      vendor: item.vendor || '',
      term: item.term || 'one-time',
      eolFlag: item.eol_flag || false,
      notes: item.notes || '',
      priceBasis: item.price_basis || '',
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
    const headers = ['#', 'Category', 'Description / SKU', 'Qty', 'Unit', 'Unit Price', 'Ext Price', 'Vendor', 'Term']
    const rows = bom.lineItems.map(i => [
      i.lineNo, '"' + i.category + '"', '"' + i.description + '"', i.sku,
      i.qty, i.unit, i.unitPrice || 'TBD', i.extPrice || 'TBD', '"' + i.vendor + '"', i.term,
    ])
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = bom.name + '_BOM.csv'
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }
}

// Category Baseball Card
function CategoryCard({ cat, boms, onSelect }) {
  const catBOMs = boms.filter(b => {
    const c = (b.category || '').toLowerCase()
    return c === cat.key.toLowerCase() || c.includes(cat.key.toLowerCase().split('/')[0].trim())
  })
  const vendors = [...new Set(catBOMs.flatMap(b => b.lineItems.map(i => i.vendor)).filter(Boolean))].slice(0, 5)
  const latest = catBOMs.reduce((acc, b) => (!acc || new Date(b.updatedAt) > new Date(acc.updatedAt) ? b : acc), null)

  return (
    <Paper
      onClick={() => onSelect(cat)}
      elevation={0}
      sx={{
        border: '2px solid ' + (catBOMs.length ? cat.accent : '#E5E7EB'),
        borderRadius: 3,
        p: 2.5,
        cursor: 'pointer',
        bgcolor: catBOMs.length ? cat.light : '#FAFAFA',
        transition: 'all 0.18s',
        '&:hover': {
          transform: 'translateY(-3px)',
          boxShadow: '0 8px 24px ' + cat.accent + '30',
          borderColor: cat.accent,
        },
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: 1.5,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Typography sx={{ fontSize: 26 }}>{cat.icon}</Typography>
          <Box>
            <Typography sx={{ fontWeight: 700, fontSize: '0.92rem', color: cat.accent, lineHeight: 1.2 }}>
              {cat.label}
            </Typography>
            <Typography sx={{ fontSize: '0.68rem', color: '#6B7280', mt: 0.3 }}>
              {cat.desc}
            </Typography>
          </Box>
        </Box>
        <Box sx={{
          minWidth: 38, height: 38, borderRadius: '50%',
          bgcolor: catBOMs.length ? cat.accent : '#E5E7EB',
          color: catBOMs.length ? '#fff' : '#9CA3AF',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontWeight: 800, fontSize: '0.95rem', flexShrink: 0,
        }}>
          {catBOMs.length}
        </Box>
      </Box>

      <Divider sx={{ borderColor: cat.accent + '30' }} />

      <Box sx={{ display: 'flex', gap: 2.5 }}>
        <Box>
          <Typography sx={{ fontSize: '0.6rem', fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.6px' }}>
            Reference BOMs
          </Typography>
          <Typography sx={{ fontWeight: 800, fontSize: '1.1rem', color: cat.accent }}>{catBOMs.length}</Typography>
        </Box>
        {latest && (
          <Box>
            <Typography sx={{ fontSize: '0.6rem', fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.6px' }}>
              Latest
            </Typography>
            <Typography sx={{ fontWeight: 600, fontSize: '0.75rem', color: '#374151' }}>
              {fmtDate(latest.updatedAt || latest.createdAt)}
            </Typography>
          </Box>
        )}
      </Box>

      {vendors.length > 0 && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
          {vendors.map(v => (
            <Chip key={v} label={v} size="small"
              sx={{ height: 18, fontSize: '0.62rem', fontWeight: 600,
                bgcolor: cat.accent + '18', color: cat.accent, border: '1px solid ' + cat.accent + '35' }} />
          ))}
        </Box>
      )}

      {catBOMs.length === 0 && (
        <Typography sx={{ fontSize: '0.7rem', color: '#9CA3AF', fontStyle: 'italic' }}>
          No reference BOMs yet -- upload to add
        </Typography>
      )}

      <Typography sx={{ fontSize: '0.62rem', color: cat.accent, fontWeight: 700, mt: 'auto', textAlign: 'right' }}>
        View BOMs {'>'}
      </Typography>
    </Paper>
  )
}

// BOM Row with expandable raw line items
function BOMRow({ bom, dispatch, navigate, onArchive }) {
  const [expanded, setExpanded] = useState(false)
  const st = STATUS_STYLE[bom.status] || STATUS_STYLE.draft

  return (
    <>
      <TableRow hover onClick={() => setExpanded(e => !e)} sx={{ cursor: 'pointer' }}>
        <TableCell sx={{ fontWeight: 600, fontSize: '0.82rem', color: '#111827' }}>{bom.name}</TableCell>
        <TableCell sx={{ fontSize: '0.78rem', color: '#6B7280' }}>{bom.project}</TableCell>
        <TableCell>
          <Chip label={st.label} size="small"
            sx={{ bgcolor: st.bg, color: st.color, fontWeight: 700, fontSize: '0.65rem' }} />
        </TableCell>
        <TableCell sx={{ fontSize: '0.75rem', color: '#6B7280' }}>
          v{bom.version} &mdash; {fmtDate(bom.updatedAt || bom.createdAt)}
        </TableCell>
        <TableCell sx={{ fontSize: '0.78rem' }}>{bom.lineItems.length} items</TableCell>
        <TableCell sx={{ fontWeight: 700, fontSize: '0.82rem' }}>
          {bom.totalValue ? fmt(bom.totalValue) : 'TBD'}
        </TableCell>
        <TableCell onClick={e => e.stopPropagation()}>
          <Box sx={{ display: 'flex', gap: 0.5 }}>
            <Tooltip title="Open in AI Chat">
              <IconButton size="small" sx={{ color: '#D04A02' }}
                onClick={() => { dispatch(setCurrentBOM(bom)); navigate('/chat') }}>
                <AutoAwesome sx={{ fontSize: 15 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Send to RFQ Builder">
              <IconButton size="small" sx={{ color: '#3B82F6' }}
                onClick={() => { dispatch(setActiveBOMForRFQ(bom)); navigate('/rfq-builder') }}>
                <Send sx={{ fontSize: 15 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Export Excel">
              <IconButton size="small" sx={{ color: '#059669' }} onClick={() => exportBOMExcel(bom)}>
                <Download sx={{ fontSize: 15 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Submit for Review">
              <IconButton size="small" sx={{ color: '#7C3AED' }}
                onClick={() => { dispatch(setCurrentBOM(bom)); navigate('/bom-review') }}>
                <RateReview sx={{ fontSize: 15 }} />
              </IconButton>
            </Tooltip>
            <Tooltip title="Archive">
              <IconButton size="small" sx={{ color: '#9CA3AF' }} onClick={() => onArchive(bom.id)}>
                <Archive sx={{ fontSize: 15 }} />
              </IconButton>
            </Tooltip>
          </Box>
        </TableCell>
      </TableRow>

      {expanded && (
        <TableRow>
          <TableCell colSpan={7} sx={{ p: 0, bgcolor: '#F8FAFC' }}>
            <Box sx={{ p: 2 }}>
              <Typography sx={{ fontWeight: 700, fontSize: '0.72rem', color: '#374151', mb: 1.5,
                textTransform: 'uppercase', letterSpacing: '0.6px' }}>
                Raw BOM &mdash; {bom.lineItems.length} Line Items
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#1F2937' }}>
                      {['#', 'Category', 'Description / SKU', 'Qty', 'Unit', 'Unit Price', 'Ext Price', 'Vendor', 'Term'].map(h => (
                        <TableCell key={h} sx={{ color: '#fff', fontWeight: 700, fontSize: '0.62rem', py: 0.7,
                          textTransform: 'uppercase', letterSpacing: '0.5px' }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {bom.lineItems.map((item, i) => (
                      <TableRow key={item.id} sx={{ bgcolor: item.eolFlag ? '#FEF2F2' : (i % 2 === 0 ? '#fff' : '#F9FAFB') }}>
                        <TableCell sx={{ fontSize: '0.7rem', fontWeight: 600 }}>{item.lineNo}</TableCell>
                        <TableCell>
                          <Chip label={item.category || '--'} size="small"
                            sx={{ height: 17, fontSize: '0.58rem', bgcolor: '#E5E7EB', color: '#374151' }} />
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.72rem', maxWidth: 260 }}>
                          <Typography sx={{ fontSize: '0.72rem', fontWeight: 600, color: '#111827' }}>{item.description}</Typography>
                          {item.sku && <Typography sx={{ fontSize: '0.6rem', color: '#6B7280' }}>{item.sku}</Typography>}
                          {item.eolFlag && <Chip label="EOL" size="small"
                            sx={{ height: 14, fontSize: '0.55rem', bgcolor: '#FEE2E2', color: '#DC2626', ml: 0.5 }} />}
                          {item.notes && <Typography sx={{ fontSize: '0.6rem', color: '#9CA3AF', fontStyle: 'italic' }}>{item.notes}</Typography>}
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.72rem', fontWeight: 700 }}>{item.qty}</TableCell>
                        <TableCell sx={{ fontSize: '0.68rem', color: '#6B7280' }}>{item.unit}</TableCell>
                        <TableCell sx={{ fontSize: '0.72rem' }}>
                          {item.unitPrice ? fmt(item.unitPrice) : <Typography component="span" sx={{ fontSize: '0.65rem', color: '#9CA3AF', fontStyle: 'italic' }}>TBD</Typography>}
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.72rem', fontWeight: 700 }}>
                          {item.extPrice ? fmt(item.extPrice) : <Typography component="span" sx={{ fontSize: '0.65rem', color: '#9CA3AF', fontStyle: 'italic' }}>TBD</Typography>}
                        </TableCell>
                        <TableCell>
                          {item.vendor && <Chip label={item.vendor} size="small"
                            sx={{ height: 17, fontSize: '0.6rem', bgcolor: '#DBEAFE', color: '#1E40AF' }} />}
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.68rem', color: '#6B7280' }}>{item.term}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

// Main Page
export default function BOMLibraryPage() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const bomList = useSelector(s => s.bom.bomList)

  const [search, setSearch] = useState('')
  const [vendorFilter, setVendorFilter] = useState('All')
  const [selectedCategory, setSelectedCategory] = useState(null)
  const [loading, setLoading] = useState(false)
  const [backendError, setBackendError] = useState(null)

  // SharePoint delta sync state
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)

  const handleSyncSharePoint = async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const resp = await fetch('/api/ingest/delta?force_full_sync=true', { method: 'POST' })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Sync failed')
      setSyncResult({ ok: true, msg: 'SharePoint sync started in background. Check back in a minute.' })
      // Refresh the BOM list after a short delay
      setTimeout(() => loadFromBackend(), 5000)
    } catch (err) {
      setSyncResult({ ok: false, msg: err.message })
    } finally {
      setSyncing(false)
    }
  }

  // SharePoint upload state
  const [spUploadOpen, setSpUploadOpen] = useState(false)
  const [spFile, setSpFile] = useState(null)
  const [spVendor, setSpVendor] = useState('')
  const [spCategory, setSpCategory] = useState('')
  const [spUploading, setSpUploading] = useState(false)
  const [spResult, setSpResult] = useState(null)
  const [ingestStatus, setIngestStatus] = useState(null)
  const spFileRef = useRef(null)
  const ingestPollRef = useRef(null)

  const pollIngestStatus = (bomId) => {
    setIngestStatus({ status: 'processing' })
    let attempts = 0
    ingestPollRef.current = setInterval(async () => {
      attempts++
      try {
        const r = await fetch('/api/ingest/status/' + bomId)
        if (r.ok) {
          const d = await r.json()
          setIngestStatus(d)
          if (d.status === 'indexed' || d.status === 'failed' || attempts >= 60) {
            clearInterval(ingestPollRef.current)
          }
        }
      } catch { /* ignore */ }
    }, 3000)
  }

  useEffect(() => () => clearInterval(ingestPollRef.current), [])

  const handleSpUpload = async () => {
    if (!spFile) return
    setSpUploading(true)
    setSpResult(null)
    setIngestStatus(null)
    try {
      const fd = new FormData()
      fd.append('file', spFile)
      // Use the selected category as the SharePoint folder name (e.g. 'SD-WAN', 'Data Center / COLO')
      fd.append('folder', spCategory.trim() || 'BOMs')
      if (spVendor) fd.append('vendor', spVendor)
      if (spCategory) fd.append('category', spCategory)
      const resp = await fetch('/api/sharepoint/upload', { method: 'POST', body: fd })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || 'Upload failed')
      setSpResult({ ok: true, url: data.web_url, bomId: data.bom_id, folder: data.folder || spCategory || 'BOMs' })
      if (data.bom_id) pollIngestStatus(data.bom_id)
    } catch (err) {
      setSpResult({ ok: false, msg: err.message })
    } finally {
      setSpUploading(false)
    }
  }

  const loadFromBackend = useCallback(async () => {
    setLoading(true)
    setBackendError(null)
    try {
      const data = await bomService.list()
      const boms = (data.boms || []).map(backendToFrontend)
      boms.forEach(b => dispatch(saveBOM(b)))
    } catch {
      setBackendError('Could not reach backend -- showing local data')
    } finally {
      setLoading(false)
    }
  }, [dispatch])

  useEffect(() => { loadFromBackend() }, [loadFromBackend])

  const filteredBOMs = bomList.filter(b => {
    if (b.status === 'archived') return false
    const q = search.toLowerCase()
    if (q && !b.name.toLowerCase().includes(q) && !(b.project || '').toLowerCase().includes(q) &&
        !(b.category || '').toLowerCase().includes(q)) return false
    if (vendorFilter !== 'All') {
      const hasVendor = b.lineItems.some(i => (i.vendor || '').toLowerCase().includes(vendorFilter.toLowerCase()))
      if (!hasVendor) return false
    }
    return true
  })

  const categoryBOMs = selectedCategory
    ? filteredBOMs.filter(b => {
        const c = (b.category || '').toLowerCase()
        return c === selectedCategory.key.toLowerCase() ||
               c.includes(selectedCategory.key.toLowerCase().split('/')[0].trim())
      })
    : []

  const handleArchive = (id) => dispatch(archiveBOM(id))

  const closeUpload = () => { setSpUploadOpen(false); setSpResult(null); setSpFile(null); setSpVendor(''); setSpCategory('') }

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1400, mx: 'auto' }}>

      {/* Page Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3, flexWrap: 'wrap', gap: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          {selectedCategory && (
            <IconButton onClick={() => setSelectedCategory(null)} size="small" sx={{ color: '#6B7280' }}>
              <ArrowBack sx={{ fontSize: 20 }} />
            </IconButton>
          )}
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 800, color: '#111827' }}>
              {selectedCategory ? selectedCategory.icon + ' ' + selectedCategory.label : 'BOM Reference Library'}
            </Typography>
            <Typography sx={{ fontSize: '0.78rem', color: '#6B7280', mt: 0.2 }}>
              {selectedCategory
                ? categoryBOMs.length + ' BOMs -- click a row to expand raw line items'
                : 'Reference BOMs organized by category -- click a card to browse'}
            </Typography>
          </Box>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <Button size="small" startIcon={syncing ? <CircularProgress size={12} sx={{ color: '#fff' }} /> : <Sync sx={{ fontSize: 14 }} />}
            onClick={handleSyncSharePoint}
            disabled={syncing}
            sx={{ bgcolor: '#1D4ED8', color: '#fff', fontWeight: 700, fontSize: '0.75rem',
              '&:hover': { bgcolor: '#1E40AF' }, borderRadius: 2, px: 2, py: 0.75, textTransform: 'none' }}>
            {syncing ? 'Syncing...' : 'Sync from SharePoint'}
          </Button>
          <Button size="small" startIcon={<CloudUpload sx={{ fontSize: 14 }} />}
            onClick={() => setSpUploadOpen(true)}
            sx={{ bgcolor: '#D04A02', color: '#fff', fontWeight: 700, fontSize: '0.75rem',
              '&:hover': { bgcolor: '#B33D00' }, borderRadius: 2, px: 2, py: 0.75, textTransform: 'none' }}>
            Upload BOM
          </Button>
          <IconButton onClick={loadFromBackend} disabled={loading} size="small" sx={{ color: '#6B7280' }}>
            {loading ? <CircularProgress size={15} /> : <Refresh sx={{ fontSize: 18 }} />}
          </IconButton>
        </Box>
      </Box>

      {backendError && <Alert severity="warning" sx={{ mb: 2, fontSize: '0.78rem' }}>{backendError}</Alert>}
      {syncResult && (
        <Alert severity={syncResult.ok ? 'info' : 'error'} sx={{ mb: 2, fontSize: '0.78rem' }}
          onClose={() => setSyncResult(null)}>
          {syncResult.msg}
        </Alert>
      )}

      {/* Search + Vendor filter strip */}
      <Box sx={{ display: 'flex', gap: 2, mb: 3, flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField size="small" placeholder="Search BOMs, projects..." value={search}
          onChange={e => setSearch(e.target.value)}
          InputProps={{ startAdornment: <Search sx={{ fontSize: 15, color: '#9CA3AF', mr: 0.5 }} /> }}
          sx={{ minWidth: 210, '& .MuiOutlinedInput-root': { borderRadius: 2, fontSize: '0.8rem' } }} />

        <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', alignItems: 'center' }}>
          <FilterList sx={{ fontSize: 15, color: '#6B7280' }} />
          {VENDOR_FILTERS.map(v => (
            <Chip key={v} label={v} size="small" onClick={() => setVendorFilter(v)}
              sx={{
                height: 25, fontWeight: vendorFilter === v ? 800 : 500, fontSize: '0.7rem', cursor: 'pointer',
                bgcolor: vendorFilter === v ? '#1F2937' : '#F3F4F6',
                color: vendorFilter === v ? '#fff' : '#374151',
                border: '1.5px solid ' + (vendorFilter === v ? '#1F2937' : '#E5E7EB'),
                '&:hover': { bgcolor: vendorFilter === v ? '#374151' : '#E5E7EB' },
              }} />
          ))}
        </Box>
      </Box>

      {/* CATEGORY CARDS VIEW -- baseball cards */}
      {!selectedCategory && (
        <Grid container spacing={2.5}>
          {CATEGORIES.map(cat => (
            <Grid item xs={12} sm={6} md={4} lg={3} key={cat.key}>
              <CategoryCard cat={cat} boms={filteredBOMs} onSelect={setSelectedCategory} />
            </Grid>
          ))}
        </Grid>
      )}

      {/* DRILL-DOWN VIEW -- raw BOMs in selected category */}
      {selectedCategory && (
        <Box>
          {categoryBOMs.length === 0 ? (
            <Paper elevation={0} sx={{ border: '2px dashed #E5E7EB', borderRadius: 3, p: 6, textAlign: 'center' }}>
              <Typography sx={{ fontSize: 40, mb: 1 }}>{selectedCategory.icon}</Typography>
              <Typography sx={{ fontWeight: 700, color: '#374151', mb: 0.5 }}>No {selectedCategory.label} BOMs yet</Typography>
              <Typography sx={{ fontSize: '0.8rem', color: '#6B7280', mb: 3 }}>
                Upload a reference BOM or create one with the AI BOM Assistant
              </Typography>
              <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
                <Button startIcon={<CloudUpload />} onClick={() => setSpUploadOpen(true)}
                  sx={{ bgcolor: '#D04A02', color: '#fff', fontWeight: 700, borderRadius: 2, textTransform: 'none',
                    '&:hover': { bgcolor: '#B33D00' } }}>
                  Upload BOM
                </Button>
                <Button startIcon={<AutoAwesome />} onClick={() => navigate('/chat')} variant="outlined"
                  sx={{ fontWeight: 700, borderRadius: 2, textTransform: 'none',
                    borderColor: selectedCategory.accent, color: selectedCategory.accent }}>
                  Create with AI
                </Button>
              </Box>
            </Paper>
          ) : (
            <TableContainer component={Paper} elevation={0}
              sx={{ border: '1px solid #E5E7EB', borderRadius: 2, overflow: 'hidden' }}>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ bgcolor: '#1F2937' }}>
                    {['BOM Name', 'Project', 'Status', 'Version / Date', 'Items', 'Total Value', 'Actions'].map(h => (
                      <TableCell key={h} sx={{ color: '#fff', fontWeight: 700, fontSize: '0.68rem', py: 1.1,
                        textTransform: 'uppercase', letterSpacing: '0.5px' }}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {categoryBOMs.map(bom => (
                    <BOMRow key={bom.id} bom={bom} dispatch={dispatch} navigate={navigate} onArchive={handleArchive} />
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>
      )}

      {/* Upload Dialog */}
      <Dialog open={spUploadOpen} onClose={closeUpload} maxWidth="sm" fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}>
        <DialogTitle sx={{ fontWeight: 800, fontSize: '0.95rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          Upload Reference BOM
          <IconButton size="small" onClick={closeUpload}><Close sx={{ fontSize: 17 }} /></IconButton>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <Button variant="outlined" component="label" startIcon={<CloudUpload />}
              sx={{ borderRadius: 2, borderStyle: 'dashed', py: 2, fontSize: '0.8rem', textTransform: 'none' }}>
              {spFile ? spFile.name : 'Select BOM file (Excel, PDF, CSV, Word)'}
              <input ref={spFileRef} type="file" hidden accept=".xlsx,.xls,.csv,.pdf,.doc,.docx,.txt"
                onChange={e => setSpFile(e.target.files[0])} />
            </Button>
            <Box sx={{ display: 'flex', gap: 1.5 }}>
              <TextField size="small" fullWidth label="Category" value={spCategory}
                onChange={e => setSpCategory(e.target.value)}
                select sx={{ '& .MuiOutlinedInput-root': { borderRadius: 2 } }}>
                {CATEGORIES.map(c => <MenuItem key={c.key} value={c.key}>{c.icon} {c.label}</MenuItem>)}
              </TextField>
              <TextField size="small" fullWidth label="Vendor" value={spVendor}
                onChange={e => setSpVendor(e.target.value)} placeholder="Cisco, Fortinet..."
                sx={{ '& .MuiOutlinedInput-root': { borderRadius: 2 } }} />
            </Box>
            {spResult && (
              <Alert severity={spResult.ok ? 'success' : 'error'} sx={{ fontSize: '0.78rem' }}>
                {spResult.ok
                  ? <>Uploaded to <strong>SharePoint/PWC_Vendor_Contracting_Hub/{spResult.folder}</strong>. RAG embedding pipeline started.{spResult.url && <> <a href={spResult.url} target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>View file ↗</a></>}</>
                  : spResult.msg}
              </Alert>
            )}
            {ingestStatus && (
              <Alert severity={ingestStatus.status === 'indexed' ? 'success' : ingestStatus.status === 'failed' ? 'error' : 'info'}
                sx={{ fontSize: '0.78rem' }}>
                Embedding: {ingestStatus.status}
                {ingestStatus.chunks_upserted != null ? ' -- ' + ingestStatus.chunks_upserted + ' chunks indexed' : ''}
              </Alert>
            )}
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={closeUpload} sx={{ color: '#6B7280', textTransform: 'none', fontSize: '0.78rem' }}>Cancel</Button>
          <Button onClick={handleSpUpload} disabled={!spFile || spUploading} variant="contained"
            sx={{ bgcolor: '#D04A02', fontWeight: 700, fontSize: '0.78rem', borderRadius: 2, textTransform: 'none',
              '&:hover': { bgcolor: '#B33D00' } }}>
            {spUploading ? <CircularProgress size={15} sx={{ color: '#fff' }} /> : 'Upload & Index'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
