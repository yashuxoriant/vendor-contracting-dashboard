content = r"""import { useState, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Grid, Paper, Chip, Button, Alert, Table, TableBody,
  TableCell, TableContainer, TableHead, TableRow, LinearProgress, Tooltip,
  Select, MenuItem, FormControl, InputLabel,
} from '@mui/material'
import {
  CloudUpload, AutoAwesome, Send, CheckCircle, Error as ErrorIcon,
  Warning, Download, Map,
} from '@mui/icons-material'
import { saveBOM } from '../store/slices/bomSlice'

const fmt = (v) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
const SL = { fontSize: '0.58rem', fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.7px' }

const FIELD_MAP = {
  description: ['description', 'name', 'product', 'item', 'part name', 'service', 'desc'],
  qty:         ['qty', 'quantity', 'amount', 'count', 'units'],
  unitPrice:   ['unit price', 'unitprice', 'price', 'unit cost', 'rate', 'each'],
  vendor:      ['vendor', 'supplier', 'mfr', 'manufacturer', 'distributor'],
  category:    ['category', 'type', 'class', 'group'],
}

function detectField(headerName) {
  const h = headerName.toLowerCase().trim()
  for (const [field, aliases] of Object.entries(FIELD_MAP)) {
    if (aliases.some(a => h.includes(a))) return field
  }
  return null
}

function parseCSV(text) {
  const lines = text.trim().split('\n').filter(l => l.trim())
  if (lines.length < 2) return null
  const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''))
  const fieldIndex = {}
  headers.forEach((h, i) => {
    const f = detectField(h)
    if (f && fieldIndex[f] === undefined) fieldIndex[f] = i
  })
  const items = lines.slice(1).map((line, idx) => {
    const cols = line.split(',').map(c => c.trim().replace(/^"|"$/g, ''))
    const rawQty = parseFloat(cols[fieldIndex.qty]) || 1
    const rawPrice = parseFloat((cols[fieldIndex.unitPrice] || '').replace(/[$,]/g, '')) || 0
    return {
      id: 'ex_' + Date.now() + '_' + idx,
      lineNo: idx + 1,
      description: cols[fieldIndex.description] || 'Item ' + (idx + 1),
      category: cols[fieldIndex.category] || 'General',
      unit: '/unit', qty: rawQty, unitPrice: rawPrice, extPrice: rawQty * rawPrice,
      vendor: cols[fieldIndex.vendor] || 'Unknown',
      status: 'draft',
      confidence: fieldIndex.description !== undefined && fieldIndex.unitPrice !== undefined ? 0.92 : 0.65,
    }
  })
  return { items, headers, fieldIndex }
}

function parseJSON(text) {
  try {
    const data = JSON.parse(text)
    const arr = Array.isArray(data) ? data : data.items || data.lineItems || data.lines || []
    return arr.map((item, idx) => {
      const qty = parseFloat(item.qty || item.quantity || item.amount || 1)
      const price = parseFloat((item.unitPrice || item.price || item.unit_price || item.rate || 0).toString().replace(/[$,]/g, ''))
      return {
        id: 'ex_' + Date.now() + '_' + idx,
        lineNo: idx + 1,
        description: item.description || item.name || item.product || 'Item ' + (idx + 1),
        category: item.category || item.type || 'General',
        unit: item.unit || '/unit', qty, unitPrice: price, extPrice: qty * price,
        vendor: item.vendor || item.supplier || 'Unknown',
        status: 'draft', confidence: 0.95,
      }
    })
  } catch { return null }
}

export default function QuoteExtractorPage() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const fileRef = useRef(null)
  const bomList = useSelector(s => s.bom.bomList)
  const currentBOM = useSelector(s => s.bom.currentBOM)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [extractedItems, setExtractedItems] = useState(null)
  const [fileName, setFileName] = useState(null)
  const [targetBOMId, setTargetBOMId] = useState(currentBOM?.id || '')
  const [mapped, setMapped] = useState(false)

  const handleFile = (file) => {
    if (!file) return
    setUploadError(null); setExtractedItems(null); setMapped(false)
    const ext = file.name.split('.').pop().toLowerCase()
    if (!['csv', 'json'].includes(ext)) { setUploadError('Only .csv and .json files are supported.'); return }
    setFileName(file.name); setUploading(true)
    const reader = new FileReader()
    reader.onload = (e) => {
      setTimeout(() => {
        setUploading(false)
        const text = e.target.result
        let result = null
        if (ext === 'csv') result = parseCSV(text)
        if (ext === 'json') { const r = parseJSON(text); result = r ? { items: r, headers: [], fieldIndex: {} } : null }
        if (!result || !result.items || result.items.length === 0) {
          setUploadError('Could not parse the file. Ensure it has description, qty and price columns.')
        } else {
          setExtractedItems(result.items)
        }
      }, 800)
    }
    reader.onerror = () => { setUploading(false); setUploadError('Failed to read file.') }
    reader.readAsText(file)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    handleFile(file)
  }

  const mapToBOM = () => {
    if (!extractedItems || !targetBOMId) return
    const targetBOM = bomList.find(b => b.id === targetBOMId)
    if (!targetBOM) return
    const startNo = (targetBOM.lineItems?.length || 0) + 1
    const newItems = extractedItems.map((item, i) => ({ ...item, id: 'li_ex_' + Date.now() + '_' + i, lineNo: startNo + i }))
    const allItems = [...(targetBOM.lineItems || []), ...newItems]
    dispatch(saveBOM({ ...targetBOM, lineItems: allItems, totalValue: allItems.reduce((s, i) => s + i.extPrice, 0), updatedAt: new Date().toISOString() }))
    setMapped(true)
  }

  const exportExtracted = () => {
    if (!extractedItems) return
    const headers = ['Line No', 'Description', 'Category', 'Unit', 'Qty', 'Unit Price', 'Ext Price', 'Vendor', 'Confidence']
    const rows = extractedItems.map(i => [i.lineNo, '"' + i.description.replace(/"/g, '""') + '"', '"' + i.category + '"', i.unit, i.qty, i.unitPrice, i.extPrice, i.vendor, Math.round(i.confidence * 100) + '%'])
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'extracted_quote.csv'
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url)
  }

  const totalExtracted = extractedItems ? extractedItems.reduce((s, i) => s + i.extPrice, 0) : 0
  const highConfidence = extractedItems ? extractedItems.filter(i => i.confidence >= 0.9).length : 0

  return (
    <Box sx={{ bgcolor: '#FAFAFA', p: 2 }}>
      <Box sx={{ mb: 1.5 }}>
        <Typography sx={{ color: '#D04A02', fontWeight: 700, letterSpacing: '1px', textTransform: 'uppercase', fontSize: '0.6rem' }}>VENDOR QUOTE PARSING</Typography>
        <Typography sx={{ fontWeight: 700, color: '#1F2937', fontSize: '1.3rem', fontFamily: '"Playfair Display", serif', lineHeight: 1.2 }}>Quote Extractor</Typography>
        <Typography sx={{ color: '#6B7280', fontSize: '0.72rem' }}>Upload a vendor CSV or JSON quote - auto-extracts line items with confidence scoring</Typography>
      </Box>

      {/* Upload zone */}
      <Paper onDrop={handleDrop} onDragOver={e => e.preventDefault()}
        onClick={() => fileRef.current?.click()}
        sx={{ border: '2px dashed #D1D5DB', p: 3, textAlign: 'center', cursor: 'pointer', mb: 1.5, bgcolor: 'white',
          '&:hover': { border: '2px dashed #D04A02', bgcolor: '#FDF3ED' }, transition: 'all 0.2s' }}>
        <input ref={fileRef} type="file" accept=".csv,.json" style={{ display: 'none' }} onChange={e => handleFile(e.target.files[0])} />
        <CloudUpload sx={{ fontSize: 36, color: '#D04A02', mb: 1 }} />
        <Typography sx={{ fontWeight: 600, fontSize: '0.85rem', color: '#1F2937' }}>Drop vendor quote here or click to upload</Typography>
        <Typography sx={{ fontSize: '0.7rem', color: '#9CA3AF', mt: 0.5 }}>Supports .csv and .json - must include description, qty, and price columns</Typography>
        {fileName && <Chip label={fileName} size="small" sx={{ mt: 1, bgcolor: '#F0FDF4', color: '#065F46', fontWeight: 600 }} />}
      </Paper>

      {uploading && (
        <Box sx={{ mb: 1.5 }}>
          <Typography sx={{ fontSize: '0.72rem', color: '#6B7280', mb: 0.5 }}>Parsing file...</Typography>
          <LinearProgress sx={{ height: 4, borderRadius: 2 }} />
        </Box>
      )}

      {uploadError && <Alert severity="error" sx={{ mb: 1.5, fontSize: '0.75rem', py: 0.5 }}>{uploadError}</Alert>}

      {extractedItems && (
        <>
          {mapped && <Alert severity="success" sx={{ mb: 1.5, fontSize: '0.75rem', py: 0.5 }} icon={<CheckCircle />}>
            {extractedItems.length} items successfully mapped to <strong>{bomList.find(b => b.id === targetBOMId)?.name}</strong>
            <Button size="small" sx={{ ml: 1, fontSize: '0.65rem' }} onClick={() => navigate('/bom-library')}>View BOM Library</Button>
          </Alert>}

          {/* KPIs */}
          <Grid container spacing={1.25} sx={{ mb: 1.5 }}>
            {[
              { label: 'ITEMS EXTRACTED', value: extractedItems.length, color: '#3B82F6' },
              { label: 'HIGH CONFIDENCE', value: highConfidence + '/' + extractedItems.length, color: '#10B981' },
              { label: 'TOTAL VALUE', value: fmt(totalExtracted), color: '#D04A02' },
              { label: 'UNIQUE VENDORS', value: new Set(extractedItems.map(i => i.vendor)).size, color: '#8B5CF6' },
            ].map(({ label, value, color }) => (
              <Grid item xs={6} md={3} key={label}>
                <Paper sx={{ p: 1.25, borderTop: '3px solid ' + color }}>
                  <Typography sx={{ ...SL, mb: 0.3 }}>{label}</Typography>
                  <Typography sx={{ fontWeight: 700, fontFamily: '"Playfair Display", serif', fontSize: '1.2rem', color, lineHeight: 1.1 }}>{value}</Typography>
                </Paper>
              </Grid>
            ))}
          </Grid>

          {/* Map to BOM controls */}
          <Box sx={{ display: 'flex', gap: 1, mb: 1.25, alignItems: 'center', p: 1.25, bgcolor: 'white', border: '1px solid #E5E7EB', borderRadius: 1 }}>
            <Map sx={{ fontSize: 18, color: '#D04A02' }} />
            <Typography sx={{ fontSize: '0.75rem', fontWeight: 600 }}>Map to BOM:</Typography>
            <FormControl size="small" sx={{ minWidth: 260 }}>
              <Select value={targetBOMId} onChange={e => setTargetBOMId(e.target.value)} displayEmpty sx={{ fontSize: '0.75rem' }}>
                <MenuItem value="" sx={{ fontSize: '0.75rem', color: '#9CA3AF' }}>Select target BOM...</MenuItem>
                {bomList.filter(b => b.status !== 'archived').map(b => (
                  <MenuItem key={b.id} value={b.id} sx={{ fontSize: '0.75rem' }}>{b.name} (v{b.version})</MenuItem>
                ))}
              </Select>
            </FormControl>
            <Button variant="contained" startIcon={<Send sx={{ fontSize: 14 }} />}
              disabled={!targetBOMId || mapped}
              onClick={mapToBOM}
              sx={{ textTransform: 'none', fontSize: '0.72rem', bgcolor: '#D04A02', '&:hover': { bgcolor: '#A33A00' } }}>
              {mapped ? 'Mapped!' : 'Map ' + extractedItems.length + ' Items to BOM'}
            </Button>
            <Button variant="outlined" startIcon={<Download sx={{ fontSize: 14 }} />}
              onClick={exportExtracted}
              sx={{ textTransform: 'none', fontSize: '0.72rem', borderColor: '#6B7280', color: '#6B7280' }}>
              Export
            </Button>
          </Box>

          {/* Extracted items table */}
          <Paper sx={{ border: '1px solid #E5E7EB', overflow: 'hidden' }}>
            <Box sx={{ px: 1.5, py: 0.75, bgcolor: '#F9FAFB', borderBottom: '1px solid #F3F4F6' }}>
              <Typography sx={{ ...SL }}>EXTRACTED LINE ITEMS</Typography>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                    {['#', 'Description', 'Category', 'Qty', 'Unit Price', 'Ext Price', 'Vendor', 'Confidence'].map(h => (
                      <TableCell key={h} sx={{ fontSize: '0.58rem', fontWeight: 700, textTransform: 'uppercase', py: 0.5, color: '#6B7280' }}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {extractedItems.map(item => (
                    <TableRow key={item.id} sx={{ '&:hover': { bgcolor: '#FAFAFA' } }}>
                      <TableCell sx={{ fontSize: '0.62rem', py: 0.4, color: '#9CA3AF' }}>{item.lineNo}</TableCell>
                      <TableCell sx={{ fontSize: '0.72rem', py: 0.4, maxWidth: 280 }}>{item.description}</TableCell>
                      <TableCell sx={{ py: 0.4 }}><Chip label={item.category} size="small" sx={{ fontSize: '0.58rem', height: 16 }} /></TableCell>
                      <TableCell sx={{ fontSize: '0.7rem', py: 0.4 }}>{item.qty}</TableCell>
                      <TableCell sx={{ fontSize: '0.7rem', py: 0.4 }}>{fmt(item.unitPrice)}</TableCell>
                      <TableCell sx={{ fontSize: '0.75rem', py: 0.4, fontWeight: 700 }}>{fmt(item.extPrice)}</TableCell>
                      <TableCell sx={{ fontSize: '0.68rem', py: 0.4 }}>{item.vendor}</TableCell>
                      <TableCell sx={{ py: 0.4 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          {item.confidence >= 0.9
                            ? <CheckCircle sx={{ fontSize: 12, color: '#10B981' }} />
                            : item.confidence >= 0.7 ? <Warning sx={{ fontSize: 12, color: '#F59E0B' }} /> : <ErrorIcon sx={{ fontSize: 12, color: '#EF4444' }} />}
                          <Typography sx={{ fontSize: '0.65rem', color: item.confidence >= 0.9 ? '#10B981' : item.confidence >= 0.7 ? '#F59E0B' : '#EF4444' }}>
                            {Math.round(item.confidence * 100)}%
                          </Typography>
                        </Box>
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                    <TableCell colSpan={5} sx={{ fontSize: '0.7rem', fontWeight: 700, py: 0.5 }}>TOTAL</TableCell>
                    <TableCell sx={{ fontSize: '0.8rem', fontWeight: 700, color: '#D04A02', py: 0.5 }}>{fmt(totalExtracted)}</TableCell>
                    <TableCell colSpan={2} />
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </>
      )}

      {!extractedItems && !uploading && (
        <Paper sx={{ p: 2, bgcolor: 'white', border: '1px solid #E5E7EB' }}>
          <Typography sx={{ fontWeight: 600, fontSize: '0.8rem', mb: 1 }}>Expected file formats:</Typography>
          <Grid container spacing={1.5}>
            <Grid item xs={12} md={6}>
              <Box sx={{ p: 1.25, bgcolor: '#F9FAFB', borderRadius: 1, fontFamily: 'monospace', fontSize: '0.65rem', color: '#374151' }}>
                <Typography sx={{ ...SL, mb: 0.5 }}>CSV FORMAT</Typography>
                Description,Qty,Unit Price,Vendor,Category<br/>
                Cisco Catalyst 9300,5,7800,CDW,Network Equipment<br/>
                Palo Alto PA-220,2,5200,NTT Data,Cybersecurity
              </Box>
            </Grid>
            <Grid item xs={12} md={6}>
              <Box sx={{ p: 1.25, bgcolor: '#F9FAFB', borderRadius: 1, fontFamily: 'monospace', fontSize: '0.65rem', color: '#374151' }}>
                <Typography sx={{ ...SL, mb: 0.5 }}>JSON FORMAT</Typography>
                {'[{"description":"Cisco C9300","qty":5,"unitPrice":7800,"vendor":"CDW"},...]'}
              </Box>
            </Grid>
          </Grid>
        </Paper>
      )}
    </Box>
  )
}
"""

with open(r'c:\Users\singh_y\workspace\it-contracting-dashboard\frontend\src\pages\QuoteExtractorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('QuoteExtractorPage.jsx written, lines:', content.count('\n'))
