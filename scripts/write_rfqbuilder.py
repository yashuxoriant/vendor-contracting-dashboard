content = r"""import { useState, useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Grid, Paper, Chip, Button, IconButton, TextField,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Alert, Tooltip, Select, MenuItem, FormControl, InputLabel, Divider,
} from '@mui/material'
import {
  Add, Remove, Delete, Download, AutoAwesome, CheckCircle,
  TrendingDown, Send, Build,
} from '@mui/icons-material'
import { setCurrentBOM } from '../store/slices/bomSlice'

const fmt = (v) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
const SL = { fontSize: '0.58rem', fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.7px' }

const VENDORS = ['CDW', 'NTT Data', 'Equinix', 'PC Connection', 'Cisco', 'Microsoft', 'Zscaler', 'NTT DOCOMO']

function exportRFQasCSV(items, projectName) {
  const headers = ['Line No', 'Description', 'Category', 'Unit', 'Qty', 'Target Price (USD)', 'Ext Target (USD)', 'Market Min (USD)', 'Preferred Vendor', 'Status']
  const rows = items.map(i => [
    i.lineNo,
    '"' + (i.description || '').replace(/"/g, '""') + '"',
    '"' + (i.category || '').replace(/"/g, '""') + '"',
    '"' + (i.unit || '').replace(/"/g, '""') + '"',
    i.qty,
    i.targetPrice,
    i.qty * i.targetPrice,
    i.marketMin || '',
    '"' + (i.vendor || '') + '"',
    i.status || 'pending',
  ])
  const total = items.reduce((s, i) => s + i.qty * i.targetPrice, 0)
  const csv = [headers.join(','), ...rows.map(r => r.join(',')), ['', '', '', '', 'TOTAL', '', total, '', '', ''].join(',')].join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = (projectName || 'RFQ') + '_RFQ.csv'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export default function RFQBuilderPage() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const activeBOM = useSelector(s => s.bom.activeBOMForRFQ)
  const bomList = useSelector(s => s.bom.bomList)

  const [cart, setCart] = useState([])
  const [loadedBOMName, setLoadedBOMName] = useState(null)
  const [vendor, setVendor] = useState('All Vendors')
  const [notes, setNotes] = useState('')
  const [rfqSent, setRfqSent] = useState(false)

  // Pre-populate from activeBOMForRFQ when page loads
  useEffect(() => {
    if (activeBOM && activeBOM.lineItems) {
      const items = activeBOM.lineItems.map((item, i) => ({
        ...item,
        lineNo: i + 1,
        targetPrice: item.unitPrice,
        marketMin: Math.round(item.unitPrice * 0.88),
        savings: Math.round(item.unitPrice * 0.12),
      }))
      setCart(items)
      setLoadedBOMName(activeBOM.name)
    }
  }, [activeBOM])

  const updateQty = (id, delta) => setCart(c => c.map(i => i.id === id ? { ...i, qty: Math.max(1, i.qty + delta) } : i))
  const updateTarget = (id, val) => setCart(c => c.map(i => i.id === id ? { ...i, targetPrice: parseFloat(val) || 0 } : i))
  const updateVendor = (id, val) => setCart(c => c.map(i => i.id === id ? { ...i, vendor: val } : i))
  const removeItem = (id) => setCart(c => c.filter(i => i.id !== id).map((i, idx) => ({ ...i, lineNo: idx + 1 })))

  const addBlankItem = () => setCart(c => [...c, {
    id: 'rfq_' + Date.now(), lineNo: c.length + 1, description: '', category: 'Network & Telecom',
    unit: '/unit', qty: 1, unitPrice: 0, targetPrice: 0, marketMin: 0, vendor: 'CDW', status: 'pending',
  }])

  const totalTarget = cart.reduce((s, i) => s + (i.qty * i.targetPrice), 0)
  const totalSavings = cart.reduce((s, i) => s + ((i.qty * (i.unitPrice || i.targetPrice)) - (i.qty * i.targetPrice)), 0)
  const savingsPct = totalTarget > 0 ? ((totalSavings / (totalTarget + totalSavings)) * 100).toFixed(1) : '0.0'

  const vendorGroups = cart.reduce((a, i) => { if (i.vendor) a[i.vendor] = (a[i.vendor] || 0) + 1; return a }, {})

  return (
    <Box sx={{ bgcolor: '#FAFAFA', p: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', mb: 1.5 }}>
        <Box>
          <Typography sx={{ color: '#D04A02', fontWeight: 700, letterSpacing: '1px', textTransform: 'uppercase', fontSize: '0.6rem' }}>PROCUREMENT</Typography>
          <Typography sx={{ fontWeight: 700, color: '#1F2937', fontSize: '1.3rem', fontFamily: '"Playfair Display", serif', lineHeight: 1.2 }}>RFQ Builder</Typography>
          <Typography sx={{ color: '#6B7280', fontSize: '0.72rem' }}>Build vendor shortlists and target pricing for competitive quoting</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button size="small" variant="outlined" startIcon={<AutoAwesome sx={{ fontSize: 14 }} />}
            onClick={() => navigate('/chat')}
            sx={{ textTransform: 'none', fontSize: '0.72rem', borderColor: '#D04A02', color: '#D04A02' }}>
            Edit in AI Chat
          </Button>
          <Button size="small" variant="contained" startIcon={<Download sx={{ fontSize: 14 }} />}
            onClick={() => exportRFQasCSV(cart, loadedBOMName || 'RFQ')}
            disabled={cart.length === 0}
            sx={{ textTransform: 'none', fontSize: '0.72rem', bgcolor: '#D04A02', '&:hover': { bgcolor: '#A33A00' } }}>
            Export RFQ CSV
          </Button>
        </Box>
      </Box>

      {/* Loaded from BOM banner */}
      {loadedBOMName && (
        <Alert severity="success" sx={{ mb: 1.5, fontSize: '0.75rem', py: 0.5 }}
          action={<Button size="small" onClick={() => { setCart([]); setLoadedBOMName(null) }} sx={{ fontSize: '0.65rem', color: '#065F46' }}>Clear</Button>}>
          Loaded from BOM: <strong>{loadedBOMName}</strong> - {cart.length} line items pre-populated. Review and adjust target prices below.
        </Alert>
      )}

      {/* Load BOM selector if no active BOM */}
      {!loadedBOMName && (
        <Paper sx={{ p: 1.5, mb: 1.5, border: '1px dashed #E5E7EB', bgcolor: 'white' }}>
          <Typography sx={{ fontSize: '0.72rem', color: '#6B7280', mb: 1 }}>No BOM loaded. Load from BOM Library or build manually:</Typography>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {bomList.map(b => (
              <Chip key={b.id} label={b.name} size="small" onClick={() => {
                const items = b.lineItems.map((item, i) => ({ ...item, lineNo: i + 1, targetPrice: item.unitPrice, marketMin: Math.round(item.unitPrice * 0.88) }))
                setCart(items); setLoadedBOMName(b.name)
              }}
                sx={{ fontSize: '0.65rem', height: 22, cursor: 'pointer', bgcolor: '#F9FAFB', border: '1px solid #E5E7EB', '&:hover': { bgcolor: '#FDF3ED', borderColor: '#D04A02' } }} />
            ))}
          </Box>
        </Paper>
      )}

      {cart.length === 0 ? (
        <Paper sx={{ p: 4, textAlign: 'center', border: '1px dashed #E5E7EB' }}>
          <Build sx={{ fontSize: 40, color: '#E5E7EB', mb: 1 }} />
          <Typography sx={{ fontSize: '0.85rem', color: '#9CA3AF', mb: 1.5 }}>No items in RFQ yet</Typography>
          <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center' }}>
            <Button variant="contained" size="small" onClick={addBlankItem}
              sx={{ textTransform: 'none', fontSize: '0.72rem', bgcolor: '#D04A02', '&:hover': { bgcolor: '#A33A00' } }}>
              Add Item Manually
            </Button>
            <Button variant="outlined" size="small" startIcon={<AutoAwesome sx={{ fontSize: 14 }} />}
              onClick={() => navigate('/bom-library')}
              sx={{ textTransform: 'none', fontSize: '0.72rem', borderColor: '#D04A02', color: '#D04A02' }}>
              Load from BOM Library
            </Button>
          </Box>
        </Paper>
      ) : (
        <Grid container spacing={1.5}>
          {/* KPIs */}
          <Grid item xs={12}>
            <Grid container spacing={1.25}>
              {[
                { label: 'LINE ITEMS', value: cart.length, color: '#3B82F6' },
                { label: 'TARGET TOTAL', value: fmt(totalTarget), color: '#D04A02' },
                { label: 'EST. SAVINGS', value: fmt(totalSavings > 0 ? totalSavings : 0), color: '#10B981' },
                { label: 'SAVINGS PCT', value: totalSavings > 0 ? savingsPct + '%' : '0%', color: '#F59E0B' },
              ].map(({ label, value, color }) => (
                <Grid item xs={6} md={3} key={label}>
                  <Paper sx={{ p: 1.25, borderTop: '3px solid ' + color }}>
                    <Typography sx={{ ...SL, mb: 0.3 }}>{label}</Typography>
                    <Typography sx={{ fontWeight: 700, fontFamily: '"Playfair Display", serif', fontSize: '1.3rem', color, lineHeight: 1.1 }}>{value}</Typography>
                  </Paper>
                </Grid>
              ))}
            </Grid>
          </Grid>

          {/* Line items table */}
          <Grid item xs={12} md={8}>
            <Paper sx={{ border: '1px solid #E5E7EB' }}>
              <Box sx={{ p: 1.25, borderBottom: '1px solid #F3F4F6', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography sx={{ fontWeight: 700, fontSize: '0.78rem', color: '#1F2937' }}>RFQ Line Items</Typography>
                <Button size="small" startIcon={<Add sx={{ fontSize: 13 }} />} onClick={addBlankItem}
                  sx={{ textTransform: 'none', fontSize: '0.65rem', color: '#D04A02' }}>
                  Add Item
                </Button>
              </Box>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                      {['#', 'Description', 'Qty', 'Unit Price', 'Target Price', 'Ext Target', 'Vendor', ''].map(h => (
                        <TableCell key={h} sx={{ fontSize: '0.58rem', fontWeight: 700, textTransform: 'uppercase', color: '#6B7280', py: 0.5 }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {cart.map(item => (
                      <TableRow key={item.id} sx={{ '&:hover': { bgcolor: '#FAFAFA' } }}>
                        <TableCell sx={{ fontSize: '0.62rem', color: '#9CA3AF', py: 0.4, fontWeight: 600 }}>{item.lineNo}</TableCell>
                        <TableCell sx={{ py: 0.4 }}>
                          <Typography sx={{ fontSize: '0.68rem', fontWeight: 500 }} noWrap>{item.description}</Typography>
                          <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF' }}>{item.category}</Typography>
                        </TableCell>
                        <TableCell sx={{ py: 0.4 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
                            <IconButton size="small" onClick={() => updateQty(item.id, -1)} sx={{ p: 0.2 }}><Remove sx={{ fontSize: 11 }} /></IconButton>
                            <Typography sx={{ fontSize: '0.7rem', minWidth: 24, textAlign: 'center' }}>{item.qty}</Typography>
                            <IconButton size="small" onClick={() => updateQty(item.id, 1)} sx={{ p: 0.2 }}><Add sx={{ fontSize: 11 }} /></IconButton>
                          </Box>
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.68rem', color: '#6B7280', py: 0.4 }}>{fmt(item.unitPrice || item.targetPrice)}</TableCell>
                        <TableCell sx={{ py: 0.4 }}>
                          <TextField size="small" type="number" value={item.targetPrice}
                            onChange={e => updateTarget(item.id, e.target.value)}
                            sx={{ width: 90, '& input': { fontSize: '0.7rem', py: '3px', px: '6px' } }} />
                        </TableCell>
                        <TableCell sx={{ fontSize: '0.72rem', fontWeight: 700, py: 0.4 }}>{fmt(item.qty * item.targetPrice)}</TableCell>
                        <TableCell sx={{ py: 0.4 }}>
                          <Select size="small" value={item.vendor || 'CDW'} onChange={e => updateVendor(item.id, e.target.value)}
                            sx={{ fontSize: '0.65rem', '& .MuiSelect-select': { py: '3px', px: '8px' }, minWidth: 80 }}>
                            {VENDORS.map(v => <MenuItem key={v} value={v} sx={{ fontSize: '0.68rem' }}>{v}</MenuItem>)}
                          </Select>
                        </TableCell>
                        <TableCell sx={{ py: 0.4 }}>
                          <IconButton size="small" onClick={() => removeItem(item.id)} sx={{ color: '#EF4444', p: 0.3 }}><Delete sx={{ fontSize: 14 }} /></IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <Box sx={{ p: 1.25, borderTop: '1px solid #F3F4F6', display: 'flex', justifyContent: 'flex-end', gap: 2 }}>
                <Typography sx={{ fontSize: '0.7rem', color: '#6B7280' }}>{cart.length} items</Typography>
                {totalSavings > 0 && <Typography sx={{ fontSize: '0.7rem', color: '#10B981', fontWeight: 700 }}>Est. savings: {fmt(totalSavings)}</Typography>}
                <Typography sx={{ fontWeight: 700, fontSize: '0.75rem' }}>Target Total: {fmt(totalTarget)}</Typography>
              </Box>
            </Paper>
          </Grid>

          {/* Right panel */}
          <Grid item xs={12} md={4}>
            {/* Vendor breakdown */}
            <Paper sx={{ border: '1px solid #E5E7EB', mb: 1.25 }}>
              <Box sx={{ p: 1.25, borderBottom: '1px solid #F3F4F6' }}>
                <Typography sx={{ fontWeight: 700, fontSize: '0.75rem', color: '#1F2937' }}>Vendor Breakdown</Typography>
              </Box>
              <Box sx={{ p: 1.25 }}>
                {Object.entries(vendorGroups).map(([v, count]) => (
                  <Box key={v} sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.75, alignItems: 'center' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                      <Box sx={{ width: 8, height: 8, borderRadius: '2px', bgcolor: '#D04A02' }} />
                      <Typography sx={{ fontSize: '0.7rem', fontWeight: 600 }}>{v}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                      <Typography sx={{ fontSize: '0.65rem', color: '#6B7280' }}>{count} item{count > 1 ? 's' : ''}</Typography>
                      <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, color: '#D04A02' }}>
                        {fmt(cart.filter(i => i.vendor === v).reduce((s, i) => s + i.qty * i.targetPrice, 0))}
                      </Typography>
                    </Box>
                  </Box>
                ))}
                {Object.keys(vendorGroups).length === 0 && <Typography sx={{ fontSize: '0.7rem', color: '#9CA3AF' }}>No vendors assigned yet</Typography>}
              </Box>
            </Paper>

            {/* Savings highlights */}
            {totalSavings > 0 && (
              <Paper sx={{ border: '1px solid #D1FAE5', bgcolor: '#F0FDF4', mb: 1.25 }}>
                <Box sx={{ p: 1.25 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75 }}>
                    <TrendingDown sx={{ fontSize: 16, color: '#10B981' }} />
                    <Typography sx={{ fontWeight: 700, fontSize: '0.75rem', color: '#065F46' }}>Potential Savings</Typography>
                  </Box>
                  <Typography sx={{ fontSize: '1.1rem', fontWeight: 700, fontFamily: '"Playfair Display", serif', color: '#10B981' }}>{fmt(totalSavings)}</Typography>
                  <Typography sx={{ fontSize: '0.65rem', color: '#065F46' }}>{savingsPct}% below market average</Typography>
                </Box>
              </Paper>
            )}

            {/* Notes */}
            <Paper sx={{ border: '1px solid #E5E7EB', mb: 1.25 }}>
              <Box sx={{ p: 1.25, borderBottom: '1px solid #F3F4F6' }}>
                <Typography sx={{ fontWeight: 700, fontSize: '0.75rem', color: '#1F2937' }}>RFQ Notes / Instructions</Typography>
              </Box>
              <Box sx={{ p: 1.25 }}>
                <TextField multiline rows={3} fullWidth size="small" placeholder="Add vendor instructions, deadline, T&Cs..."
                  value={notes} onChange={e => setNotes(e.target.value)}
                  sx={{ '& textarea': { fontSize: '0.72rem' } }} />
              </Box>
            </Paper>

            {/* Send RFQ */}
            <Paper sx={{ border: '1px solid #E5E7EB' }}>
              <Box sx={{ p: 1.25 }}>
                {rfqSent ? (
                  <Alert severity="success" sx={{ fontSize: '0.72rem', py: 0.5 }}>
                    <strong>RFQ sent!</strong> Vendors have been notified.
                  </Alert>
                ) : (
                  <>
                    <Typography sx={{ fontSize: '0.65rem', color: '#6B7280', mb: 1 }}>
                      Ready to send to {Object.keys(vendorGroups).length} vendor{Object.keys(vendorGroups).length !== 1 ? 's' : ''}: {Object.keys(vendorGroups).slice(0, 3).join(', ')}
                    </Typography>
                    <Button fullWidth variant="contained" size="small" startIcon={<Send sx={{ fontSize: 14 }} />}
                      onClick={() => setRfqSent(true)} disabled={cart.length === 0}
                      sx={{ textTransform: 'none', fontSize: '0.72rem', fontWeight: 700, bgcolor: '#D04A02', '&:hover': { bgcolor: '#A33A00' } }}>
                      Send RFQ to Vendors
                    </Button>
                    <Button fullWidth variant="outlined" size="small" startIcon={<Download sx={{ fontSize: 14 }} />}
                      onClick={() => exportRFQasCSV(cart, loadedBOMName || 'RFQ')}
                      sx={{ mt: 0.75, textTransform: 'none', fontSize: '0.72rem', borderColor: '#E5E7EB', color: '#6B7280' }}>
                      Export as CSV
                    </Button>
                  </>
                )}
              </Box>
            </Paper>
          </Grid>
        </Grid>
      )}
    </Box>
  )
}
"""

with open(r'c:\Users\singh_y\workspace\it-contracting-dashboard\frontend\src\pages\RFQBuilderPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('RFQBuilderPage.jsx written, lines:', content.count('\n'))
