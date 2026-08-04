import { useState, useMemo, useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Grid, Paper, Chip, Button, IconButton, TextField,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Alert, Tooltip, InputAdornment, LinearProgress, CircularProgress,
} from '@mui/material'
import {
  Search, TrendingDown, TrendingUp, Add, AutoAwesome, Download,
  CheckCircle, Info, Refresh, Warning,
} from '@mui/icons-material'
import { setCurrentBOM, saveBOM } from '../store/slices/bomSlice'
import { catalogApi } from '../services/api'

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

const CATEGORIES_DEFAULT = ['All', ...new Set(CATALOG.map(c => c.category))]

// Normalise a backend catalog item (flat schema from catalog API) into the
// multi-vendor format the page expects.
function normaliseCatalogItem(item, idx) {
  // Already in multi-vendor format — use as-is
  if (Array.isArray(item.vendors) && item.vendors.length > 0) return item

  const name = item.description || item.name || item.sku || ''
  if (!name) return null  // skip unnamed items

  return {
    id:       item.id || item.sku || `cat-${idx}`,
    name,
    sku:      item.sku || item.part_number || '',
    category: item.category || 'General',
    unit:     item.unit || '/unit',
    vendors:  [{
      name:   item.vendor || 'Unknown',
      price:  item.unit_price || item.unitPrice || item.price || 0,
      quotes: item.quotes || 1,
      region: item.region || 'US',
    }],
  }
}

export default function VendorPriceSelectorPage() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const currentBOM = useSelector(s => s.bom.currentBOM)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const [selected, setSelected] = useState([]) // { catalogId, vendorName, qty }
  const [addedAlert, setAddedAlert] = useState(null)

  // Backend catalog state
  const [catalogItems, setCatalogItems] = useState(CATALOG)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogError, setCatalogError] = useState(null)
  const [backendTotal, setBackendTotal] = useState(null)

  const loadCatalog = async () => {
    setCatalogLoading(true); setCatalogError(null)
    try {
      // Clear server-side lru_cache so we get the freshly flattened catalog
      await fetch('/api/catalog/reload', { method: 'POST' }).catch(() => {})
      const resp = await catalogApi.list({ search: search || undefined, category: category !== 'All' ? category : undefined, limit: 200 })
      if (resp?.items?.length > 0) {
        const normalised = resp.items
          .map(normaliseCatalogItem)
          .filter(Boolean)                       // remove null (unnamed items)
          .filter(i => i.vendors[0]?.price > 0)  // remove zero-price items
        if (normalised.length > 0) {
          setCatalogItems([...CATALOG, ...normalised.filter(
            n => !CATALOG.some(c => c.sku === n.sku && n.sku)  // dedup by SKU
          )])
          setBackendTotal(resp.total)
        }
      }
    } catch {
      setCatalogError('Using local catalog — backend unavailable')
    } finally {
      setCatalogLoading(false)
    }
  }

  // Load from backend on mount
  useEffect(() => { loadCatalog() }, [])

  const CATEGORIES = ['All', ...new Set(catalogItems.map(c => c.category))]

  const filtered = useMemo(() => catalogItems.filter(item => {
    if (category !== 'All' && item.category !== category) return false
    if (search && !item.name.toLowerCase().includes(search.toLowerCase()) && !item.sku.toLowerCase().includes(search.toLowerCase())) return false
    return true
  }), [search, category, catalogItems])

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
          <Typography sx={{ color: '#6B7280', fontSize: '0.72rem' }}>
            {catalogItems.length} services across {new Set(catalogItems.flatMap(c => (c.vendors||[]).map(v => v.name))).size} vendors — green = cheapest option
            {backendTotal && backendTotal > catalogItems.length ? ` (${backendTotal} total in catalog)` : ''}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          {catalogLoading && <CircularProgress size={16} sx={{ color: '#D04A02' }} />}
          <Tooltip title="Reload from backend catalog">
            <IconButton size="small" onClick={loadCatalog} sx={{ color: '#6B7280' }}>
              <Refresh sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
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

      {catalogError && (
        <Alert severity="info" icon={<Warning sx={{ fontSize: 16 }} />} sx={{ mb: 1, py: 0.25, fontSize: '0.72rem' }}>
          {catalogError}
        </Alert>
      )}

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

      {/* Filters + Bulk Action bar */}
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
        <Box sx={{ flexGrow: 1 }} />
        {currentBOM && filtered.length > 0 && (
          <Tooltip title={`Add cheapest price for all ${filtered.length} filtered items to ${currentBOM.name}`}>
            <Button size="small" variant="contained" startIcon={<Add sx={{ fontSize: 13 }} />}
              onClick={() => {
                filtered.forEach(item => addToBOM(item, cheapestVendor(item)))
              }}
              sx={{ textTransform: 'none', fontSize: '0.68rem', bgcolor: '#10B981', '&:hover': { bgcolor: '#059669' }, fontWeight: 700 }}>
              Bulk Add Best Prices ({filtered.length})
            </Button>
          </Tooltip>
        )}
      </Box>

      {/* Savings summary bar */}
      {filtered.length > 0 && (
        <Paper sx={{ p: 1, mb: 1.5, bgcolor: '#F0FDF4', border: '1px solid #A7F3D0', display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <TrendingDown sx={{ fontSize: 14, color: '#10B981' }} />
            <Box sx={{ fontSize: '0.7rem', color: '#065F46', fontWeight: 600 }}>
              Best-price total: <strong>{fmt(filtered.reduce((s, i) => s + cheapestVendor(i).price, 0))}</strong>
            </Box>
          </Box>
          <Box sx={{ fontSize: '0.7rem', color: '#065F46' }}>
            vs market max: <strong>{fmt(filtered.reduce((s, i) => s + priceRange(i).max, 0))}</strong>
          </Box>
          <Box sx={{ fontSize: '0.7rem', fontWeight: 700, color: '#10B981' }}>
            Potential savings: <strong>{fmt(totalSavingsAvailable)}</strong> ({Math.round(totalSavingsAvailable / Math.max(1, filtered.reduce((s, i) => s + priceRange(i).max, 0)) * 100)}%)
          </Box>
        </Paper>
      )}

      {/* Catalog table */}
      <Paper sx={{ border: '1px solid #E5E7EB', overflow: 'hidden' }}>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                {['Service', 'SKU / Category', 'Unit', 'Vendor Quotes', 'Price Range', 'Confidence', 'Add to BOM'].map(h => (
                  <TableCell key={h} sx={{ fontSize: '0.58rem', fontWeight: 700, textTransform: 'uppercase', py: 0.6, color: '#6B7280' }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {filtered.map(item => {
                const cv = cheapestVendor(item)
                const pr = priceRange(item)
                const savingPct = savings(item)
                const totalQuotes = item.vendors.reduce((s, v) => s + (v.quotes || 0), 0)
                const confidence = totalQuotes >= 15 ? 'High' : totalQuotes >= 8 ? 'Medium' : 'Low'
                const confColor = confidence === 'High' ? '#065F46' : confidence === 'Medium' ? '#92400E' : '#6B7280'
                const confBg = confidence === 'High' ? '#D1FAE5' : confidence === 'Medium' ? '#FEF3C7' : '#F3F4F6'
                return (
                  <TableRow key={item.id} sx={{ '&:hover': { bgcolor: '#FAFAFA' } }}>
                    <TableCell sx={{ py: 0.6, maxWidth: 200 }}>
                      <Typography sx={{ fontSize: '0.75rem', fontWeight: 600, color: '#1F2937' }} noWrap>{item.name}</Typography>
                      {savingPct >= 15 && <Chip label={`${savingPct}% savings`} size="small" sx={{ fontSize: '0.55rem', height: 14, bgcolor: '#D1FAE5', color: '#065F46', mt: 0.25 }} />}
                    </TableCell>
                    <TableCell sx={{ py: 0.6 }}>
                      <Typography sx={{ fontSize: '0.62rem', color: '#6B7280', fontFamily: 'monospace' }}>{item.sku}</Typography>
                      <Chip label={item.category} size="small" sx={{ fontSize: '0.55rem', height: 16, mt: 0.25 }} />
                    </TableCell>
                    <TableCell sx={{ fontSize: '0.65rem', color: '#6B7280', py: 0.6 }}>{item.unit}</TableCell>
                    <TableCell sx={{ py: 0.6, minWidth: 200 }}>
                      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.4 }}>
                        {item.vendors.map(v => {
                          const isCheapest = v.name === cv.name && v.price === cv.price
                          const pctAboveMin = pr.min > 0 ? ((v.price - pr.min) / pr.min * 100).toFixed(0) : 0
                          return (
                            <Box key={v.name} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, p: '2px 6px', borderRadius: 1, bgcolor: isCheapest ? '#F0FDF4' : 'transparent', border: isCheapest ? '1px solid #A7F3D0' : '1px solid transparent' }}>
                              {isCheapest
                                ? <TrendingDown sx={{ fontSize: 12, color: '#10B981' }} />
                                : <TrendingUp sx={{ fontSize: 12, color: '#9CA3AF' }} />
                              }
                              <Typography sx={{ fontSize: '0.65rem', fontWeight: isCheapest ? 700 : 400, color: isCheapest ? '#065F46' : '#374151', flex: 1 }}>{v.name}</Typography>
                              <Tooltip title={`${v.quotes} quotes · ${v.region}`}>
                                <Box sx={{ fontSize: '0.55rem', color: '#9CA3AF', display: 'flex', alignItems: 'center', gap: 0.25 }}>
                                  {v.quotes}q · {v.region}
                                </Box>
                              </Tooltip>
                              <Typography sx={{ fontSize: '0.68rem', fontWeight: 700, color: isCheapest ? '#10B981' : '#374151' }}>{fmt(v.price)}</Typography>
                              {!isCheapest && Number(pctAboveMin) > 0 && <Chip label={`+${pctAboveMin}%`} size="small" sx={{ fontSize: '0.52rem', height: 13, bgcolor: '#FEF3C7', color: '#92400E' }} />}
                              <Tooltip title={`Add ${v.name} price to BOM`}>
                                <IconButton size="small" onClick={() => addToBOM(item, v)} sx={{ p: 0.2, color: '#D04A02', '&:hover': { bgcolor: '#FDF3ED' } }}>
                                  <Add sx={{ fontSize: 12 }} />
                                </IconButton>
                              </Tooltip>
                            </Box>
                          )
                        })}
                      </Box>
                    </TableCell>
                    <TableCell sx={{ py: 0.6 }}>
                      <Typography sx={{ fontSize: '0.68rem', color: '#10B981', fontWeight: 700 }}>{fmt(pr.min)}</Typography>
                      <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF' }}>to {fmt(pr.max)}</Typography>
                      <Box sx={{ width: 50, height: 4, bgcolor: '#F3F4F6', borderRadius: 1, mt: 0.4, overflow: 'hidden' }}>
                        <Box sx={{ width: savingPct + '%', height: '100%', bgcolor: savingPct > 15 ? '#10B981' : savingPct > 8 ? '#F59E0B' : '#E5E7EB' }} />
                      </Box>
                    </TableCell>
                    <TableCell sx={{ py: 0.6 }}>
                      <Chip size="small" label={confidence} sx={{ fontSize: '0.58rem', height: 18, bgcolor: confBg, color: confColor, fontWeight: 700 }} />
                      <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF', mt: 0.25 }}>{totalQuotes} quotes</Typography>
                    </TableCell>
                    <TableCell sx={{ py: 0.6 }}>
                      <Button size="small" variant="outlined" startIcon={<CheckCircle sx={{ fontSize: 11 }} />}
                        onClick={() => addToBOM(item, cv)}
                        sx={{ textTransform: 'none', fontSize: '0.62rem', borderColor: '#10B981', color: '#10B981', py: 0.2, px: 0.75, '&:hover': { bgcolor: '#F0FDF4' } }}>
                        Best
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
