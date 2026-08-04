content = r"""import { useState, useMemo } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Grid, Paper, Chip, Button, IconButton, TextField,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Alert, Tooltip, InputAdornment, LinearProgress,
} from '@mui/material'
import {
  Search, TrendingDown, TrendingUp, Add, AutoAwesome, Download,
  CheckCircle, Info,
} from '@mui/icons-material'
import { setCurrentBOM, saveBOM } from '../store/slices/bomSlice'

const fmt = (v) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
const SL = { fontSize: '0.58rem', fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.7px' }

const CATALOG = [
  { id: 'c001', name: 'Cisco Catalyst 9300 48P PoE+', sku: 'C9300-48P-A', category: 'Network Equipment', unit: '/unit',
    vendors: [{ name: 'CDW', price: 7800, quotes: 12, region: 'US' }, { name: 'PC Connection', price: 8200, quotes: 4, region: 'US' }, { name: 'NTT Data', price: 7650, quotes: 6, region: 'APAC' }] },
  { id: 'c002', name: 'Cisco ASR 1001-X Router', sku: 'ASR1001X-5G-SHA/K9', category: 'Network Equipment', unit: '/unit',
    vendors: [{ name: 'CDW', price: 12500, quotes: 8, region: 'US' }, { name: 'NTT Data', price: 11900, quotes: 5, region: 'Global' }] },
  { id: 'c003', name: 'Palo Alto PA-220 NGFW', sku: 'PAN-PA-220', category: 'Cybersecurity', unit: '/unit',
    vendors: [{ name: 'CDW', price: 5200, quotes: 10, region: 'US' }, { name: 'NTT Data', price: 4950, quotes: 7, region: 'Global' }, { name: 'PC Connection', price: 5450, quotes: 3, region: 'US' }] },
  { id: 'c004', name: 'CrowdStrike Falcon EDR', sku: 'CS-FALCON-EP', category: 'Cybersecurity', unit: '/ep/yr',
    vendors: [{ name: 'CDW', price: 180, quotes: 15, region: 'US' }, { name: 'NTT Data', price: 172, quotes: 8, region: 'Global' }] },
  { id: 'c005', name: 'Splunk Enterprise SIEM', sku: 'SPLUNK-ENT-500GB', category: 'Cybersecurity', unit: '/yr',
    vendors: [{ name: 'NTT Data', price: 48000, quotes: 6, region: 'Global' }, { name: 'CDW', price: 51000, quotes: 4, region: 'US' }] },
  { id: 'c006', name: 'SD-WAN Edge Cisco Viptela', sku: 'VIPTELA-EDGE-LIC', category: 'SD-WAN', unit: '/device',
    vendors: [{ name: 'CDW', price: 4800, quotes: 9, region: 'US' }, { name: 'NTT Data', price: 4600, quotes: 11, region: 'Global' }] },
  { id: 'c007', name: 'MPLS Circuit 1Gbps', sku: 'MPLS-1G-PRIMARY', category: 'Network & Telecom', unit: '/ckt/mo',
    vendors: [{ name: 'NTT Data', price: 4200, quotes: 18, region: 'Global' }, { name: 'NTT DOCOMO', price: 3950, quotes: 7, region: 'APAC' }] },
  { id: 'c008', name: 'Azure ExpressRoute 1Gbps', sku: 'AZ-ER-1G-METER', category: 'Cloud Infrastructure', unit: '/ckt/mo',
    vendors: [{ name: 'NTT Data', price: 8500, quotes: 5, region: 'Global' }, { name: 'NTT DOCOMO', price: 8100, quotes: 3, region: 'APAC' }] },
  { id: 'c009', name: 'Microsoft 365 E3', sku: 'M365-E3-USER', category: 'M365 & Power Platform', unit: '/user/mo',
    vendors: [{ name: 'CDW', price: 36, quotes: 20, region: 'US' }, { name: 'NTT Data', price: 35, quotes: 12, region: 'Global' }, { name: 'PC Connection', price: 37, quotes: 8, region: 'US' }] },
  { id: 'c010', name: 'Full Rack 42U Colocation', sku: 'COLO-RACK-42U', category: 'Data Center / COLO', unit: '/rack/mo',
    vendors: [{ name: 'Equinix', price: 2800, quotes: 14, region: 'Global' }, { name: 'NTT DOCOMO', price: 2650, quotes: 6, region: 'APAC' }] },
  { id: 'c011', name: 'SOC 24x7 Managed Security', sku: 'SOC-24X7-BASIC', category: 'Cybersecurity', unit: '/mo',
    vendors: [{ name: 'NTT Data', price: 5500, quotes: 9, region: 'Global' }, { name: 'CDW', price: 6200, quotes: 4, region: 'US' }] },
  { id: 'c012', name: 'UPS Power Backup 3kVA', sku: 'UPS-3KVA-RACK', category: 'Network Equipment', unit: '/unit',
    vendors: [{ name: 'PC Connection', price: 2400, quotes: 8, region: 'US' }, { name: 'CDW', price: 2550, quotes: 5, region: 'US' }] },
]

const CATEGORIES = ['All', ...new Set(CATALOG.map(c => c.category))]

export default function VendorPriceSelectorPage() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const currentBOM = useSelector(s => s.bom.currentBOM)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const [selected, setSelected] = useState([]) // { catalogId, vendorName, qty }
  const [addedAlert, setAddedAlert] = useState(null)

  const filtered = useMemo(() => CATALOG.filter(item => {
    if (category !== 'All' && item.category !== category) return false
    if (search && !item.name.toLowerCase().includes(search.toLowerCase()) && !item.sku.toLowerCase().includes(search.toLowerCase())) return false
    return true
  }), [search, category])

  const cheapestVendor = (item) => item.vendors.reduce((a, b) => a.price < b.price ? a : b)
  const priceRange = (item) => ({ min: Math.min(...item.vendors.map(v => v.price)), max: Math.max(...item.vendors.map(v => v.price)) })
  const savings = (item) => { const r = priceRange(item); return r.max > 0 ? Math.round((1 - r.min / r.max) * 100) : 0 }

  const addToBOM = (item, vendor) => {
    if (!currentBOM) { setAddedAlert('no_bom'); return }
    const lineItem = {
      id: 'li_cat_' + Date.now(),
      lineNo: (currentBOM.lineItems?.length || 0) + 1,
      category: item.category, description: item.name, unit: item.unit,
      qty: 1, unitPrice: vendor.price, extPrice: vendor.price,
      vendor: vendor.name, status: 'draft',
    }
    const newItems = [...(currentBOM.lineItems || []), lineItem]
    dispatch(saveBOM({ ...currentBOM, lineItems: newItems, totalValue: newItems.reduce((s, i) => s + i.extPrice, 0), updatedAt: new Date().toISOString() }))
    setAddedAlert(item.name + ' (' + vendor.name + ')')
    setTimeout(() => setAddedAlert(null), 3000)
  }

  const exportCatalogCSV = () => {
    const rows = [['Name', 'SKU', 'Category', 'Unit', 'Cheapest Vendor', 'Cheapest Price', 'Market Max', 'Savings %']]
    filtered.forEach(item => {
      const cv = cheapestVendor(item)
      const pr = priceRange(item)
      rows.push(['"' + item.name + '"', item.sku, '"' + item.category + '"', item.unit, cv.name, cv.price, pr.max, savings(item) + '%'])
    })
    const csv = rows.map(r => r.join(',')).join('\n')
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'vendor_price_catalog.csv'
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const totalSavingsAvailable = filtered.reduce((s, item) => {
    const r = priceRange(item); return s + (r.max - r.min)
  }, 0)

  return (
    <Box sx={{ bgcolor: '#FAFAFA', p: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', mb: 1.5 }}>
        <Box>
          <Typography sx={{ color: '#D04A02', fontWeight: 700, letterSpacing: '1px', textTransform: 'uppercase', fontSize: '0.6rem' }}>MARKET INTELLIGENCE</Typography>
          <Typography sx={{ fontWeight: 700, color: '#1F2937', fontSize: '1.3rem', fontFamily: '"Playfair Display", serif', lineHeight: 1.2 }}>Vendor Price Selector</Typography>
          <Typography sx={{ color: '#6B7280', fontSize: '0.72rem' }}>{CATALOG.length} services across {new Set(CATALOG.flatMap(c => c.vendors.map(v => v.name))).size} vendors - green = cheapest option</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button size="small" variant="outlined" startIcon={<Download sx={{ fontSize: 14 }} />}
            onClick={exportCatalogCSV}
            sx={{ textTransform: 'none', fontSize: '0.72rem', borderColor: '#6B7280', color: '#6B7280' }}>
            Export Catalog
          </Button>
          {currentBOM && (
            <Button size="small" variant="contained" startIcon={<AutoAwesome sx={{ fontSize: 14 }} />}
              onClick={() => navigate('/chat')}
              sx={{ textTransform: 'none', fontSize: '0.72rem', bgcolor: '#D04A02', '&:hover': { bgcolor: '#A33A00' } }}>
              Active BOM: {currentBOM.name.split(' - ')[0]}
            </Button>
          )}
        </Box>
      </Box>

      {addedAlert === 'no_bom' && (
        <Alert severity="warning" sx={{ mb: 1.5, fontSize: '0.75rem', py: 0.5 }}
          action={<Button size="small" onClick={() => navigate('/chat')} sx={{ fontSize: '0.65rem' }}>Create BOM</Button>}>
          No active BOM loaded. Create or load a BOM in AI Chat first, then come back to add catalog items.
        </Alert>
      )}
      {addedAlert && addedAlert !== 'no_bom' && (
        <Alert severity="success" sx={{ mb: 1.5, fontSize: '0.75rem', py: 0.5 }}>
          Added <strong>{addedAlert}</strong> to BOM: <strong>{currentBOM?.name}</strong>
        </Alert>
      )}

      {/* KPIs */}
      <Grid container spacing={1.25} sx={{ mb: 1.5 }}>
        {[
          { label: 'CATALOG ITEMS', value: CATALOG.length, color: '#3B82F6' },
          { label: 'VENDORS', value: new Set(CATALOG.flatMap(c => c.vendors.map(v => v.name))).size, color: '#8B5CF6' },
          { label: 'AVG SAVINGS POTENTIAL', value: Math.round(CATALOG.reduce((s, i) => s + savings(i), 0) / CATALOG.length) + '%', color: '#10B981' },
          { label: 'CURRENT FILTER', value: filtered.length + ' items', color: '#D04A02' },
        ].map(({ label, value, color }) => (
          <Grid item xs={6} md={3} key={label}>
            <Paper sx={{ p: 1.25, borderTop: '3px solid ' + color }}>
              <Typography sx={{ ...SL, mb: 0.3 }}>{label}</Typography>
              <Typography sx={{ fontWeight: 700, fontFamily: '"Playfair Display", serif', fontSize: '1.3rem', color, lineHeight: 1.1 }}>{value}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>

      {/* Filters */}
      <Box sx={{ display: 'flex', gap: 1, mb: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField size="small" placeholder="Search service name or SKU..."
          value={search} onChange={e => setSearch(e.target.value)}
          InputProps={{ startAdornment: <Search sx={{ fontSize: 16, color: '#9CA3AF', mr: 0.5 }} /> }}
          sx={{ bgcolor: 'white', minWidth: 260, '& .MuiInputBase-input': { fontSize: '0.78rem', py: '6px' } }} />
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
          {CATEGORIES.map(c => (
            <Chip key={c} label={c} size="small" onClick={() => setCategory(c)}
              sx={{ fontSize: '0.65rem', height: 24, cursor: 'pointer', bgcolor: category === c ? '#D04A02' : 'white', color: category === c ? 'white' : '#374151', border: '1px solid ' + (category === c ? '#D04A02' : '#E5E7EB'), fontWeight: category === c ? 700 : 400 }} />
          ))}
        </Box>
      </Box>

      {/* Catalog table */}
      <Paper sx={{ border: '1px solid #E5E7EB', overflow: 'hidden' }}>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                {['Service', 'SKU', 'Category', 'Unit', 'Vendor Quotes', 'Price Range', 'Savings Potential', 'Add to BOM'].map(h => (
                  <TableCell key={h} sx={{ fontSize: '0.58rem', fontWeight: 700, textTransform: 'uppercase', py: 0.6, color: '#6B7280' }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {filtered.map(item => {
                const cv = cheapestVendor(item)
                const pr = priceRange(item)
                const savingPct = savings(item)
                return (
                  <TableRow key={item.id} sx={{ '&:hover': { bgcolor: '#FAFAFA' } }}>
                    <TableCell sx={{ py: 0.6 }}>
                      <Typography sx={{ fontSize: '0.75rem', fontWeight: 600, color: '#1F2937' }}>{item.name}</Typography>
                    </TableCell>
                    <TableCell sx={{ fontSize: '0.62rem', color: '#6B7280', py: 0.6 }}>{item.sku}</TableCell>
                    <TableCell sx={{ py: 0.6 }}>
                      <Chip label={item.category} size="small" sx={{ fontSize: '0.6rem', height: 18 }} />
                    </TableCell>
                    <TableCell sx={{ fontSize: '0.65rem', color: '#6B7280', py: 0.6 }}>{item.unit}</TableCell>
                    <TableCell sx={{ py: 0.6 }}>
                      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.4 }}>
                        {item.vendors.map(v => {
                          const isCheapest = v.name === cv.name && v.price === cv.price
                          return (
                            <Box key={v.name} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, p: '2px 6px', borderRadius: 1, bgcolor: isCheapest ? '#F0FDF4' : 'transparent', border: isCheapest ? '1px solid #A7F3D0' : '1px solid transparent' }}>
                              {isCheapest && <TrendingDown sx={{ fontSize: 12, color: '#10B981' }} />}
                              <Typography sx={{ fontSize: '0.65rem', fontWeight: isCheapest ? 700 : 400, color: isCheapest ? '#065F46' : '#374151', flex: 1 }}>{v.name}</Typography>
                              <Typography sx={{ fontSize: '0.68rem', fontWeight: 700, color: isCheapest ? '#10B981' : '#374151' }}>{fmt(v.price)}</Typography>
                              <Typography sx={{ fontSize: '0.55rem', color: '#9CA3AF' }}>{v.quotes}q</Typography>
                              <Tooltip title={'Add to BOM (' + v.name + ')'}><IconButton size="small" onClick={() => addToBOM(item, v)} sx={{ p: 0.2, color: '#D04A02', '&:hover': { bgcolor: '#FDF3ED' } }}><Add sx={{ fontSize: 12 }} /></IconButton></Tooltip>
                            </Box>
                          )
                        })}
                      </Box>
                    </TableCell>
                    <TableCell sx={{ py: 0.6 }}>
                      <Typography sx={{ fontSize: '0.68rem', color: '#10B981', fontWeight: 700 }}>{fmt(pr.min)}</Typography>
                      <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF' }}>to {fmt(pr.max)}</Typography>
                    </TableCell>
                    <TableCell sx={{ py: 0.6 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                        <Box sx={{ flex: 1, height: 5, bgcolor: '#F3F4F6', borderRadius: 1, overflow: 'hidden', minWidth: 50 }}>
                          <Box sx={{ width: savingPct + '%', height: '100%', bgcolor: savingPct > 15 ? '#10B981' : savingPct > 8 ? '#F59E0B' : '#E5E7EB' }} />
                        </Box>
                        <Typography sx={{ fontSize: '0.68rem', fontWeight: 700, color: savingPct > 15 ? '#10B981' : savingPct > 8 ? '#F59E0B' : '#6B7280', minWidth: 28 }}>
                          {savingPct}%
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell sx={{ py: 0.6 }}>
                      <Button size="small" variant="outlined" startIcon={<Add sx={{ fontSize: 11 }} />}
                        onClick={() => addToBOM(item, cv)}
                        sx={{ textTransform: 'none', fontSize: '0.62rem', borderColor: '#10B981', color: '#10B981', py: 0.2, px: 0.75, '&:hover': { bgcolor: '#F0FDF4' } }}>
                        Best price
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  )
}
"""

with open(r'c:\Users\singh_y\workspace\it-contracting-dashboard\frontend\src\pages\VendorPriceSelectorPage.jsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('VendorPriceSelectorPage.jsx written, lines:', content.count('\n'))
