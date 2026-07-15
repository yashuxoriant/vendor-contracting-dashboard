import { useState, useEffect, useMemo } from 'react'
import { useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import {
  Container, Typography, Box, Grid, Card, Chip, Select, MenuItem, FormControl,
  InputLabel, Paper, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Alert, Button, Collapse, IconButton, Tooltip,
  LinearProgress, Skeleton,
} from '@mui/material'
import { ExpandMore, ExpandLess, Warning, Refresh, TrendingUp, TrendingDown } from '@mui/icons-material'
import { Bar, Line, Doughnut } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, LineElement,
  PointElement, ArcElement, Title, Tooltip as CJSTooltip, Legend,
} from 'chart.js'
import { analyticsApi } from '../services/api'

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, ArcElement, Title, CJSTooltip, Legend)

// ── Formatters ────────────────────────────────────────────────────────────
const fmt = (v) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
const fmtK = (v) => v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${(v / 1e3).toFixed(0)}K` : `$${v}`
const SL = { color: '#1F2937', fontWeight: 700, letterSpacing: '0.6px', textTransform: 'uppercase', mb: 0.75, display: 'block', fontSize: '0.62rem' }
const chartBase = {
  responsive: true, maintainAspectRatio: false,
  plugins: { legend: { display: false }, tooltip: { bodyFont: { size: 10 }, titleFont: { size: 10 } } },
  scales: {
    x: { grid: { display: false }, ticks: { font: { size: 9 } } },
    y: { grid: { color: '#F3F4F6' }, beginAtZero: true, ticks: { font: { size: 9 } } },
  },
}

// ── Fallback data (used when API is unavailable) ─────────────────────────
const FALLBACK_KPI = { total_boms: 3, avg_cycle_time_days: 12, target_cycle_time_days: 10, boms_pending_approval: 1, eol_warnings: 2, boms_by_status: { active: 1, review: 1, draft: 0, approved: 1 } }
const FALLBACK_SPENDING = [
  { category: 'Data Center / COLO', amount: 784200 },
  { category: 'SD-WAN / Network', amount: 325000 },
  { category: 'Cybersecurity', amount: 415000 },
  { category: 'M365 & Power Platform', amount: 87000 },
  { category: 'Cloud Infrastructure', amount: 230000 },
]
const FALLBACK_VENDORS = [
  { vendor: 'NTT Data', total_spend: 268320, bom_count: 3, avg_delivery_time_days: 7, pct: 40.3 },
  { vendor: 'CDW', total_spend: 175410, bom_count: 2, avg_delivery_time_days: 5, pct: 26.7 },
  { vendor: 'PC Connection', total_spend: 131900, bom_count: 2, avg_delivery_time_days: 8, pct: 20.1 },
  { vendor: 'Equinix', total_spend: 31200, bom_count: 1, avg_delivery_time_days: 14, pct: 4.8 },
  { vendor: 'NTT DOCOMO', total_spend: 24390, bom_count: 1, avg_delivery_time_days: 10, pct: 3.7 },
]
const FALLBACK_TRENDS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'].map((month, i) => ({
  month, spending: [420000, 380000, 510000, 625000, 540000, 780000][i],
}))

// ── Static reference data ─────────────────────────────────────────────────
const projects = [
  { name: 'Idemia', files: 9, categories: 3, services: 32, vendors: 4, totalSpend: 122.62, avgQuote: 57.85, bestPrice: 310, color: '#D04A02' },
  { name: 'Panasonic', files: 31, categories: 5, services: 75, vendors: 8, totalSpend: 331.40, avgQuote: 60.69, bestPrice: 504, color: '#10B981' },
  { name: 'Tenneco', files: 8, categories: 2, services: 22, vendors: 4, totalSpend: 244, avgQuote: 309, bestPrice: 126, color: '#3B82F6' },
]

const categories = [
  { name: 'Network & Telecom', color: '#1F2937', files: 18, services: 49, vendors: 4, priceMin: 77, priceMax: 99630, avg: 31120, volatility: 3497 },
  { name: 'Cybersecurity', color: '#D04A02', files: 10, services: 25, vendors: 4, priceMin: 1320, priceMax: 45000, avg: 7630, volatility: 327 },
  { name: 'Hosting', color: '#3B82F6', files: 7, services: 18, vendors: 5, priceMin: 1230, priceMax: 32000, avg: 6640, volatility: 3045 },
  { name: 'M365 & Power Platform', color: '#8B5CF6', files: 5, services: 24, vendors: 3, priceMin: 890, priceMax: 28000, avg: 5880, volatility: 231 },
  { name: 'IaAM', color: '#F59E0B', files: 6, services: 11, vendors: 2, priceMin: 500, priceMax: 12000, avg: 2080, volatility: 117 },
  { name: 'Service Management (SNow)', color: '#10B981', files: 2, services: 5, vendors: 1, priceMin: 1200, priceMax: 4500, avg: 990, volatility: 23 },
]

const heatmapData = [
  { vendor: 'NTT Data', Cybersecurity: 2.51, Hosting: 2.98, IaAM: null, 'M365 & PP': null, 'Network & Telecom': 202.83, 'Svc Mgmt': null, total: 268.32 },
  { vendor: 'CDW', Cybersecurity: null, Hosting: null, IaAM: null, 'M365 & PP': null, 'Network & Telecom': 175.41, 'Svc Mgmt': null, total: 175.41 },
  { vendor: 'PC Connection', Cybersecurity: null, Hosting: null, IaAM: null, 'M365 & PP': null, 'Network & Telecom': 131.90, 'Svc Mgmt': null, total: 131.90 },
  { vendor: 'Equinix', Cybersecurity: null, Hosting: 5.12, IaAM: null, 'M365 & PP': null, 'Network & Telecom': 26.08, 'Svc Mgmt': null, total: 31.20 },
  { vendor: 'NTT DOCOMO', Cybersecurity: null, Hosting: 24.39, IaAM: null, 'M365 & PP': null, 'Network & Telecom': null, 'Svc Mgmt': null, total: 24.39 },
]
const heatmapCols = ['Cybersecurity', 'Hosting', 'IaAM', 'M365 & PP', 'Network & Telecom', 'Svc Mgmt']

const vendorConcentration = [
  { rank: 1, vendor: 'NTT Data', quotes: 16, categories: 3, spend: 268.32, percentage: 40.3 },
  { rank: 2, vendor: 'CDW', quotes: 8, categories: 2, spend: 175.41, percentage: 26.7 },
  { rank: 3, vendor: 'PC Connection', quotes: 12, categories: 2, spend: 131.90, percentage: 20.1 },
  { rank: 4, vendor: 'Equinix', quotes: 4, categories: 2, spend: 31.20, percentage: 4.8 },
  { rank: 5, vendor: 'NTT DOCOMO', quotes: 5, categories: 2, spend: 24.39, percentage: 3.7 },
]

const topServices = [
  { name: 'Global MPLS Network Premium', category: 'Network & Telecom', vendors: 15, quotes: 130, price: '$18.52M' },
  { name: 'Enterprise SOC-as-a-Service', category: 'Cybersecurity', vendors: 8, quotes: 62, price: '$9.84M' },
  { name: 'Colocation Tier-4 Full Rack', category: 'Hosting', vendors: 6, quotes: 44, price: '$6.21M' },
]

export default function OverviewPage() {
  const navigate = useNavigate()
  const bomList = useSelector(s => s.bom?.bomList || [])

  // ── Overview state ──────────────────────────────────────────────────────
  const [selectedProject, setSelectedProject] = useState('All')
  const [region, setRegion] = useState('APAC')
  const [country, setCountry] = useState('All')
  const [dateRange, setDateRange] = useState('All')
  const [alertsOpen, setAlertsOpen] = useState(true)

  // ── Analytics state ─────────────────────────────────────────────────────
  const [period, setPeriod] = useState('monthly')
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [usingFallback, setUsingFallback] = useState(false)
  const [kpi, setKpi] = useState(null)
  const [spending, setSpending] = useState(null)
  const [vendors, setVendors] = useState(null)
  const [trends, setTrends] = useState(null)

  // ── Load analytics data ─────────────────────────────────────────────────
  const load = async () => {
    setLoading(true)
    const results = await Promise.allSettled([
      analyticsApi.kpi(),
      analyticsApi.spending(period),
      analyticsApi.vendors(),
      analyticsApi.trends(),
    ])
    const [kpiR, spendR, vendR, trendR] = results
    setUsingFallback(results.some(r => r.status === 'rejected'))
    setKpi(kpiR.status === 'fulfilled' ? kpiR.value : FALLBACK_KPI)
    setSpending(spendR.status === 'fulfilled' ? spendR.value?.data : FALLBACK_SPENDING)
    setVendors(vendR.status === 'fulfilled' ? vendR.value?.vendors : FALLBACK_VENDORS)
    setTrends(trendR.status === 'fulfilled' ? trendR.value?.data : FALLBACK_TRENDS)
    setLastUpdated(new Date())
    setLoading(false)
  }

  useEffect(() => { load() }, [period])

  // ── Derived analytics values ────────────────────────────────────────────
  const activeKpi = kpi || FALLBACK_KPI
  const activeVendors = vendors || FALLBACK_VENDORS
  const spendData = spending || FALLBACK_SPENDING
  const trendData = trends || FALLBACK_TRENDS
  const totalSpend = spendData.reduce((s, d) => s + d.amount, 0)
  const cycleHealth = activeKpi.avg_cycle_time_days <= activeKpi.target_cycle_time_days

  // ── Chart data ──────────────────────────────────────────────────────────
  const spendingChartData = useMemo(() => {
    const colors = ['#D04A02', '#3B82F6', '#10B981', '#8B5CF6', '#F59E0B', '#1F2937']
    return {
      labels: spendData.map(d => d.category.split(' ')[0]),
      datasets: [{ data: spendData.map(d => d.amount), backgroundColor: colors, borderRadius: 4 }],
    }
  }, [spending])

  const trendsChartData = useMemo(() => ({
    labels: trendData.map(d => d.month),
    datasets: [{
      label: 'BOM Value',
      data: trendData.map(d => d.spending),
      borderColor: '#D04A02', backgroundColor: 'rgba(208,74,2,0.08)',
      tension: 0.4, fill: true, pointRadius: 4, pointBackgroundColor: '#D04A02',
    }],
  }), [trends])

  const statusChartData = useMemo(() => {
    const s = activeKpi.boms_by_status || {}
    const bgColors = ['#D1FAE5', '#DBEAFE', '#FEF3C7', '#F3E8FF', '#F3F4F6']
    return {
      labels: Object.keys(s).map(k => k.charAt(0).toUpperCase() + k.slice(1)),
      datasets: [{ data: Object.values(s), backgroundColor: bgColors, borderWidth: 1, borderColor: '#fff' }],
    }
  }, [kpi])

  // ── Derive live project cards from Redux bomList ────────────────────────
  const PROJ_COLORS = ['#D04A02', '#10B981', '#3B82F6', '#8B5CF6', '#F59E0B']
  const liveProjects = useMemo(() => {
    const groups = {}
    bomList.forEach(b => {
      const key = b.project || 'Other'
      if (!groups[key]) groups[key] = { name: key, boms: [] }
      groups[key].boms.push(b)
    })
    return Object.entries(groups).map(([name, g], i) => {
      const totalVal = g.boms.reduce((s, b) => s + (b.totalValue || 0), 0)
      const allItems = g.boms.flatMap(b => b.lineItems || [])
      const vendorSet = new Set(allItems.map(i => i.vendor).filter(Boolean))
      return {
        name,
        files: g.boms.length,
        categories: new Set(g.boms.map(b => b.category)).size,
        services: allItems.length,
        vendors: vendorSet.size,
        totalSpend: (totalVal / 1e6).toFixed(2),
        avgQuote: g.boms.length ? (totalVal / g.boms.length / 1e6).toFixed(2) : '0.00',
        bestPrice: allItems.length ? Math.round(Math.min(...allItems.map(i => i.unitPrice || 0).filter(p => p > 0)) / 1000) : 0,
        color: PROJ_COLORS[i % PROJ_COLORS.length],
        status: g.boms[0]?.status || 'draft',
      }
    })
  }, [bomList])

  const portfolioProjects = liveProjects.length > 0 ? liveProjects : projects

  // ── Live KPI strip from Redux ───────────────────────────────────────────
  const liveKpis = useMemo(() => {
    const pending = bomList.filter(b => b.status === 'review').length
    const approved = bomList.filter(b => b.status === 'approved').length
    const totalVal = bomList.reduce((s, b) => s + (b.totalValue || 0), 0)
    return { total: bomList.length, pending, approved, totalVal }
  }, [bomList])

  // ── Alerts from Redux BOM state ─────────────────────────────────────────
  const now = new Date()
  const alerts = []
  bomList.forEach(bom => {
    const updatedDays = Math.floor((now - new Date(bom.updatedAt)) / 86400000)
    if (bom.status === 'draft' && updatedDays > 30) alerts.push({ severity: 'warning', bom, msg: `"${bom.name}" has been a Draft for ${updatedDays} days — consider submitting for review.` })
    if (bom.status === 'review' && updatedDays > 7) alerts.push({ severity: 'error', bom, msg: `"${bom.name}" has been In Review for ${updatedDays} days — pending approval.` })
    if (bom.lineItems?.filter(i => i.status === 'quoted').length === 0 && bom.status !== 'archived') alerts.push({ severity: 'info', bom, msg: `"${bom.name}" has 0 quoted items — send to RFQ Builder to get vendor pricing.` })
  })

  return (
    <Box sx={{ bgcolor: '#FAFAFA', minHeight: 'calc(100vh - 42px)', overflowX: 'hidden' }}>
      <Container maxWidth={false} disableGutters sx={{ py: 1.25, px: { xs: 1.5, lg: 2.5 } }}>

        {/* Header */}
        <Box sx={{ mb: 1.25, display: 'flex', alignItems: 'baseline', gap: 2, flexWrap: 'wrap' }}>
          <Box>
            <Box sx={{ color: '#D04A02', fontWeight: 700, letterSpacing: '0.8px', textTransform: 'uppercase', fontSize: '0.6rem', lineHeight: 1 }}>
              EXECUTIVE DASHBOARD
            </Box>
            <Box sx={{ fontWeight: 700, color: '#1F2937', fontSize: '1.3rem', lineHeight: 1.15, fontFamily: '"Playfair Display", serif' }}>
              Portfolio Overview &amp; Spend Intelligence
            </Box>
          </Box>
          <Box sx={{ color: '#6B7280', fontWeight: 500, fontSize: '0.72rem' }}>
            Vendor spend · service coverage · pricing intelligence · approval cycle analytics
          </Box>
          <Box sx={{ flexGrow: 1 }} />
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            {lastUpdated && <Box sx={{ fontSize: '0.62rem', color: '#9CA3AF' }}>Updated {lastUpdated.toLocaleTimeString()}</Box>}
            {usingFallback && <Chip label="Sample data" size="small" sx={{ bgcolor: '#FEF3C7', color: '#92400E', fontSize: '0.58rem', height: 18 }} />}
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel sx={{ fontSize: '0.72rem' }}>Period</InputLabel>
              <Select value={period} onChange={e => setPeriod(e.target.value)} label="Period" sx={{ fontSize: '0.72rem', '.MuiSelect-select': { py: '3px' } }}>
                {['monthly', 'quarterly', 'yearly'].map(p => <MenuItem key={p} value={p} sx={{ fontSize: '0.72rem', textTransform: 'capitalize' }}>{p}</MenuItem>)}
              </Select>
            </FormControl>
            <Tooltip title="Refresh data"><IconButton size="small" onClick={load} disabled={loading} sx={{ color: '#6B7280' }}><Refresh sx={{ fontSize: 16 }} /></IconButton></Tooltip>
          </Box>
        </Box>

        {loading && <LinearProgress sx={{ mb: 1, borderRadius: 1, bgcolor: '#FFE5D0', '& .MuiLinearProgress-bar': { bgcolor: '#D04A02' } }} />}

        {/* Live KPI Cards */}
        <Grid container spacing={1.25} sx={{ mb: 1.75 }}>
          {[
            { label: 'TOTAL BOMs', value: activeKpi.total_boms, sub: `${activeKpi.boms_by_status?.active || 0} active · ${activeKpi.boms_by_status?.approved || 0} approved`, color: '#3B82F6', icon: '📋' },
            { label: 'AVG CYCLE TIME', value: `${activeKpi.avg_cycle_time_days}d`, sub: `Target: ${activeKpi.target_cycle_time_days}d — ${cycleHealth ? '✅ On track' : '⚠️ Over target'}`, color: cycleHealth ? '#10B981' : '#F59E0B', icon: '⏱️', trend: cycleHealth ? 'up' : 'down' },
            { label: 'PENDING APPROVAL', value: activeKpi.boms_pending_approval, sub: 'awaiting party sign-off', color: '#F59E0B', icon: '⏳' },
            { label: 'TOTAL BOM VALUE', value: fmtK(totalSpend), sub: `${activeKpi.eol_warnings} EOL warnings`, color: '#D04A02', icon: '💰', trend: 'up' },
          ].map(({ label, value, sub, color, icon, trend }) => (
            <Grid item xs={6} md={3} key={label}>
              <Paper sx={{ p: 1.5, borderTop: `3px solid ${color}` }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <Box sx={{ flex: 1 }}>
                    <Box sx={{ ...SL, mb: 0.35 }}>{label}</Box>
                    {loading ? <Skeleton width={80} height={30} /> : <Box sx={{ fontWeight: 700, fontFamily: '"Playfair Display", serif', fontSize: '1.4rem', color, lineHeight: 1.1 }}>{value}</Box>}
                    <Box sx={{ fontSize: '0.62rem', color: '#6B7280', mt: 0.35 }}>{sub}</Box>
                  </Box>
                  <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.5 }}>
                    <Box sx={{ fontSize: '1.2rem', opacity: 0.6 }}>{icon}</Box>
                    {trend === 'up' && <TrendingUp sx={{ fontSize: 14, color: '#10B981' }} />}
                    {trend === 'down' && <TrendingDown sx={{ fontSize: 14, color: '#EF4444' }} />}
                  </Box>
                </Box>
              </Paper>
            </Grid>
          ))}
        </Grid>

        {/* Charts Row */}
        <Grid container spacing={1.25} sx={{ mb: 1.75 }}>
          <Grid item xs={12} md={5}>
            <Paper sx={{ p: 1.5, height: 260 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                <Box sx={{ fontWeight: 700, fontSize: '0.78rem' }}>Spend by Category</Box>
                <Box sx={{ fontSize: '0.62rem', color: '#9CA3AF' }}>{fmtK(totalSpend)} total</Box>
              </Box>
              <Box sx={{ height: 198 }}>
                {loading ? <Skeleton variant="rectangular" height={198} /> : (
                  <Bar data={spendingChartData} options={{ ...chartBase, plugins: { ...chartBase.plugins, tooltip: { callbacks: { label: ctx => ` ${fmtK(ctx.raw)}` }, bodyFont: { size: 10 }, titleFont: { size: 10 } } }, scales: { x: { grid: { display: false }, ticks: { font: { size: 8 } } }, y: { grid: { color: '#F3F4F6' }, beginAtZero: true, ticks: { font: { size: 8 }, callback: v => fmtK(v) } } } }} />
                )}
              </Box>
            </Paper>
          </Grid>

          <Grid item xs={12} md={3}>
            <Paper sx={{ p: 1.5, height: 260 }}>
              <Box sx={{ fontWeight: 700, fontSize: '0.78rem', mb: 1 }}>BOM Status</Box>
              {loading ? <Skeleton variant="circular" width={140} height={140} sx={{ mx: 'auto' }} /> : (
                <Box>
                  <Box sx={{ height: 160 }}>
                    <Doughnut data={statusChartData} options={{ responsive: true, maintainAspectRatio: false, cutout: '65%', plugins: { legend: { position: 'bottom', labels: { font: { size: 9 }, boxWidth: 10, padding: 6 } }, tooltip: { bodyFont: { size: 10 } } } }} />
                  </Box>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                    {Object.entries(activeKpi.boms_by_status || {}).map(([k, v]) => (
                      <Chip key={k} label={`${k}: ${v}`} size="small" sx={{ fontSize: '0.55rem', height: 16 }} />
                    ))}
                  </Box>
                </Box>
              )}
            </Paper>
          </Grid>

          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 1.5, height: 260 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                <Box sx={{ fontWeight: 700, fontSize: '0.78rem' }}>BOM Value Trend</Box>
                {(() => {
                  const last = trendData[trendData.length - 1]?.spending || 0
                  const prev = trendData[trendData.length - 2]?.spending || 0
                  const delta = prev > 0 ? ((last - prev) / prev * 100).toFixed(1) : null
                  return delta !== null ? (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25, fontSize: '0.62rem', color: Number(delta) >= 0 ? '#10B981' : '#EF4444', fontWeight: 700 }}>
                      {Number(delta) >= 0 ? <TrendingUp sx={{ fontSize: 12 }} /> : <TrendingDown sx={{ fontSize: 12 }} />}
                      {Math.abs(delta)}%
                    </Box>
                  ) : null
                })()}
              </Box>
              <Box sx={{ height: 198 }}>
                {loading ? <Skeleton variant="rectangular" height={198} /> : (
                  <Line data={trendsChartData} options={{ ...chartBase, plugins: { ...chartBase.plugins, tooltip: { callbacks: { label: ctx => ` ${fmtK(ctx.raw)}` }, bodyFont: { size: 10 }, titleFont: { size: 10 } } }, scales: { x: { grid: { display: false }, ticks: { font: { size: 9 } } }, y: { grid: { color: '#F3F4F6' }, beginAtZero: true, ticks: { font: { size: 9 }, callback: v => fmtK(v) } } } }} />
                )}
              </Box>
            </Paper>
          </Grid>
        </Grid>

        {/* Alerts Panel */}
        {alerts.length > 0 && (
          <Box sx={{ mb: 1.25 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Warning sx={{ fontSize: 14, color: '#F59E0B' }} />
              <Typography sx={{ fontSize: '0.68rem', fontWeight: 700, color: '#92400E' }}>
                {alerts.length} BOM Alert{alerts.length > 1 ? 's' : ''} require attention
              </Typography>
              <IconButton size="small" onClick={() => setAlertsOpen(o => !o)} sx={{ ml: 'auto', p: 0.25 }}>
                {alertsOpen ? <ExpandLess sx={{ fontSize: 16 }} /> : <ExpandMore sx={{ fontSize: 16 }} />}
              </IconButton>
            </Box>
            <Collapse in={alertsOpen}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                {alerts.slice(0, 5).map((a, i) => (
                  <Alert key={i} severity={a.severity} sx={{ py: 0.25, fontSize: '0.7rem' }}
                    action={<Button size="small" onClick={() => navigate('/bom-library')} sx={{ fontSize: '0.6rem', textTransform: 'none' }}>View BOM</Button>}>
                    {a.msg}
                  </Alert>
                ))}
              </Box>
            </Collapse>
          </Box>
        )}

        {/* Filters Row */}
        <Box sx={{ display: 'flex', gap: 0.6, mb: 1.25, flexWrap: 'wrap', alignItems: 'center' }}>
          {[{ label: 'All', count: bomList.length }, ...portfolioProjects.map(p => ({ label: p.name, count: p.files }))].map(({ label, count }) => (
            <Chip key={label} label={`${label} · ${count}`} size="small" onClick={() => setSelectedProject(label)}
              sx={{ bgcolor: selectedProject === label ? '#1F2937' : 'white', color: selectedProject === label ? 'white' : '#6B7280', fontWeight: 700, fontSize: '0.68rem', cursor: 'pointer', border: '1px solid #E5E7EB', height: 24 }} />
          ))}
          <Box sx={{ flexGrow: 1 }} />
          {['Last 30d', 'Last 90d', 'YTD', 'All'].map(r => (
            <Chip key={r} label={r} size="small" onClick={() => setDateRange(r)}
              sx={{ fontSize: '0.62rem', height: 22, cursor: 'pointer', bgcolor: dateRange === r ? '#1F2937' : 'white', color: dateRange === r ? 'white' : '#6B7280', border: '1px solid #E5E7EB', fontWeight: dateRange === r ? 700 : 400 }} />
          ))}
          {[['Region', region, setRegion, ['APAC', 'Americas', 'EMEA'], 110], ['Country', country, setCountry, ['All', 'United States', 'Germany'], 130]].map(([lbl, val, setter, opts, w]) => (
            <FormControl key={lbl} size="small" sx={{ minWidth: w }}>
              <InputLabel sx={{ fontSize: '0.72rem' }}>{lbl}</InputLabel>
              <Select value={val} onChange={e => setter(e.target.value)} label={lbl} sx={{ bgcolor: 'white', fontSize: '0.72rem', '.MuiSelect-select': { py: '3px' } }}>
                {opts.map(o => <MenuItem key={o} value={o} sx={{ fontSize: '0.72rem' }}>{o}</MenuItem>)}
              </Select>
            </FormControl>
          ))}
        </Box>

        {/* Project Portfolio */}
        <Box sx={SL}>PROJECT PORTFOLIO · {liveProjects.length > 0 ? `${liveProjects.length} live projects from Cosmos DB` : 'Loading from backend...'}</Box>
        <Grid container spacing={1.25} sx={{ mb: 1.75 }}>
          {portfolioProjects.map(proj => {
            const statusColors = { active: '#D1FAE5', draft: '#FEF3C7', review: '#DBEAFE', approved: '#F3E8FF' }
            return (
              <Grid item xs={12} md={4} key={proj.name}>
                <Card sx={{ borderLeft: `5px solid ${proj.color}`, cursor: 'pointer', '&:hover': { boxShadow: 3 } }}
                  onClick={() => navigate('/bom-library')}>
                  <Box sx={{ p: 1.25 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.4 }}>
                      <Box sx={{ fontWeight: 700, fontFamily: '"Playfair Display",serif', fontSize: '0.95rem', color: '#1F2937' }}>{proj.name}</Box>
                      <Box sx={{ display: 'flex', gap: 0.5 }}>
                        {proj.status && <Chip label={proj.status} size="small" sx={{ bgcolor: statusColors[proj.status] || '#F3F4F6', color: '#1F2937', fontSize: '0.55rem', height: 16 }} />}
                        <Chip label={`${proj.files} BOMs`} size="small" sx={{ bgcolor: '#D04A02', color: 'white', fontWeight: 700, fontSize: '0.6rem', height: 18 }} />
                      </Box>
                    </Box>
                    <Box sx={{ color: '#6B7280', mb: 0.75, fontSize: '0.67rem' }}>
                      {proj.categories} categories · {proj.services} line items · {proj.vendors} vendors
                    </Box>
                    <Box sx={{ display: 'flex', height: 5, mb: 0.4, borderRadius: 1, overflow: 'hidden' }}>
                      {[30, 45, 25].map((pct, i) => <Box key={i} sx={{ width: `${pct}%`, bgcolor: ['#FFD4B3', '#FFB380', proj.color][i] }} />)}
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.75 }}>
                      {['2024', '2025', '2026'].map(y => <Box key={y} sx={{ color: '#9CA3AF', fontSize: '0.58rem' }}>{y}</Box>)}
                    </Box>
                    <Grid container spacing={0.75}>
                      {[
                        ['TOTAL VALUE', `$${proj.totalSpend}M`, '#1F2937'],
                        ['AVG / BOM', `$${proj.avgQuote}M`, '#D04A02'],
                        ['BEST PRICE', proj.bestPrice > 0 ? `$${proj.bestPrice}K` : '—', '#10B981'],
                      ].map(([lbl, val, clr]) => (
                        <Grid item xs={4} key={lbl}>
                          <Box sx={{ fontWeight: 700, fontFamily: '"Playfair Display",serif', fontSize: '0.9rem', color: clr, lineHeight: 1.1 }}>{val}</Box>
                          <Box sx={{ color: '#6B7280', fontSize: '0.55rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.3px' }}>{lbl}</Box>
                        </Grid>
                      ))}
                    </Grid>
                  </Box>
                </Card>
              </Grid>
            )
          })}
        </Grid>

        {/* Vendor & Category Heatmap */}
        <Box sx={SL}>VENDOR &amp; CATEGORY INTELLIGENCE</Box>
        <Paper sx={{ p: 1.5, mb: 1.75 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.75 }}>
            <Box sx={{ fontWeight: 700, fontSize: '0.78rem' }}>Vendor × Category Spend Heatmap</Box>
          </Box>
          <Grid container spacing={1} sx={{ mb: 0.75 }}>
            <Grid item xs={12} sm={5}>
              <Box sx={{ color: '#6B7280', fontWeight: 700, fontSize: '0.58rem', textTransform: 'uppercase', letterSpacing: '0.5px', mb: 0.4 }}>VENDORS</Box>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.35 }}>
                {['NTT Data 16', 'CDW 8', 'PC Connection 12', 'Equinix 4', 'NTT DOCOMO 5'].map(v => (
                  <Chip key={v} label={v} size="small" sx={{ bgcolor: '#D04A02', color: 'white', fontWeight: 700, fontSize: '0.58rem', height: 16 }} />
                ))}
              </Box>
            </Grid>
            <Grid item xs={12} sm={7}>
              <Box sx={{ color: '#6B7280', fontWeight: 700, fontSize: '0.58rem', textTransform: 'uppercase', letterSpacing: '0.5px', mb: 0.4 }}>CATEGORIES</Box>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.35 }}>
                {['Cybersecurity 16', 'Hosting 7', 'IaAM 9', 'M365 5', 'Network 16', 'Svc Mgmt 2'].map(c => (
                  <Chip key={c} label={c} size="small" sx={{ bgcolor: '#D04A02', color: 'white', fontWeight: 700, fontSize: '0.58rem', height: 16 }} />
                ))}
              </Box>
            </Grid>
          </Grid>
          <TableContainer sx={{ border: '1px solid #E5E7EB', borderRadius: 1 }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: '#1F2937' }}>
                  <TableCell sx={{ color: 'white', fontWeight: 700, fontSize: '0.65rem', minWidth: 120, position: 'sticky', left: 0, bgcolor: '#1F2937', zIndex: 2, py: 0.6 }}>Vendor</TableCell>
                  {heatmapCols.map(col => (
                    <TableCell key={col} sx={{ color: 'white', fontWeight: 700, textAlign: 'center', fontSize: '0.62rem', py: 0.6 }}>{col}</TableCell>
                  ))}
                  <TableCell sx={{ color: 'white', fontWeight: 700, textAlign: 'right', fontSize: '0.65rem', py: 0.6 }}>Total</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {heatmapData.map(row => (
                  <TableRow key={row.vendor} sx={{ '&:hover': { bgcolor: '#FFF7F0' } }}>
                    <TableCell sx={{ fontWeight: 600, fontSize: '0.68rem', position: 'sticky', left: 0, bgcolor: '#FAFAFA', borderRight: '1px solid #E5E7EB', py: 0.4 }}>{row.vendor}</TableCell>
                    {heatmapCols.map(col => (
                      <TableCell key={col} sx={{ textAlign: 'center', fontSize: '0.68rem', py: 0.4, bgcolor: row[col] ? '#FFE5D0' : '#FAFAFA', fontWeight: row[col] ? 700 : 400, color: row[col] ? '#1F2937' : '#CBD5E1', cursor: row[col] ? 'pointer' : 'default' }}>
                        {row[col] ? `$${row[col]}M` : '—'}
                      </TableCell>
                    ))}
                    <TableCell sx={{ textAlign: 'right', fontWeight: 700, fontSize: '0.68rem', py: 0.4 }}>${row.total}M</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>

        {/* Category Deep-Dive + Vendor Concentration */}
        <Grid container spacing={1.25} sx={{ mb: 1.5 }}>
          <Grid item xs={12} md={8}>
            <Paper sx={{ p: 1.5, height: '100%' }}>
              <Box sx={{ fontWeight: 700, fontSize: '0.78rem', mb: 0.75 }}>Category Deep-Dive</Box>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#F3F4F6' }}>
                      {['CATEGORY', 'FILES', 'SERVICES', 'VENDORS', 'PRICE RANGE', 'AVG', 'VOLATILITY'].map(h => (
                        <TableCell key={h} align={h === 'CATEGORY' ? 'left' : 'right'} sx={{ fontWeight: 700, fontSize: '0.58rem', textTransform: 'uppercase', py: 0.4, letterSpacing: '0.2px' }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {categories.map(cat => (
                      <TableRow key={cat.name} sx={{ '&:hover': { bgcolor: '#F9FAFB' } }}>
                        <TableCell sx={{ py: 0.35 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
                            <Box sx={{ width: 6, height: 6, borderRadius: '1px', bgcolor: cat.color, flexShrink: 0 }} />
                            <Box sx={{ fontWeight: 600, fontSize: '0.68rem' }}>{cat.name}</Box>
                          </Box>
                        </TableCell>
                        <TableCell align="right" sx={{ fontSize: '0.68rem', py: 0.35 }}>{cat.files}</TableCell>
                        <TableCell align="right" sx={{ fontSize: '0.68rem', py: 0.35 }}>{cat.services}</TableCell>
                        <TableCell align="right" sx={{ fontSize: '0.68rem', py: 0.35 }}>{cat.vendors}</TableCell>
                        <TableCell align="right" sx={{ py: 0.35 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.4, justifyContent: 'flex-end' }}>
                            <Box sx={{ width: 32, height: 4, background: 'linear-gradient(90deg,#10B981,#F59E0B,#EF4444)', borderRadius: 1 }} />
                            <Box sx={{ fontSize: '0.6rem', fontWeight: 600 }}>${cat.priceMin}–${(cat.priceMax / 1000).toFixed(0)}K</Box>
                          </Box>
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600, fontSize: '0.68rem', py: 0.35 }}>${cat.avg.toLocaleString()}</TableCell>
                        <TableCell align="right" sx={{ py: 0.35 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.4, justifyContent: 'flex-end' }}>
                            <Box sx={{ width: 24, height: 4, bgcolor: '#EF4444', borderRadius: 1 }} />
                            <Box sx={{ fontWeight: 700, color: '#EF4444', fontSize: '0.62rem' }}>{cat.volatility}%</Box>
                          </Box>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          </Grid>

          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 1.5, mb: 1.25 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.6 }}>
                <Box sx={{ fontWeight: 700, fontSize: '0.78rem' }}>Vendor Concentration Risk</Box>
                <Chip label="15 vendors" size="small" sx={{ bgcolor: '#10B981', color: 'white', fontWeight: 700, fontSize: '0.58rem', height: 16 }} />
              </Box>
              <Alert severity="error" sx={{ mb: 1, py: 0.4, '& .MuiAlert-message': { py: 0 } }}>
                <Box sx={{ fontWeight: 700, fontSize: '0.65rem', lineHeight: 1.3 }}>HIGH CONCENTRATION</Box>
                <Box sx={{ fontSize: '0.62rem' }}>Top 5 vendors = 96.1% of total spend</Box>
              </Alert>
              {vendorConcentration.map(v => (
                <Box key={v.vendor} sx={{ mb: 0.75 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.25 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.4 }}>
                      <Box sx={{ fontWeight: 700, color: '#6B7280', fontSize: '0.62rem', minWidth: 8 }}>{v.rank}</Box>
                      <Chip label={v.vendor} size="small" sx={{ bgcolor: '#D04A02', color: 'white', fontWeight: 700, fontSize: '0.58rem', height: 16 }} />
                    </Box>
                    <Box sx={{ fontWeight: 700, fontSize: '0.68rem' }}>${v.spend}M</Box>
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
                    <Box sx={{ flexGrow: 1, height: 4, bgcolor: '#E5E7EB', borderRadius: 1, overflow: 'hidden' }}>
                      <Box sx={{ width: `${v.percentage}%`, height: '100%', bgcolor: '#D04A02' }} />
                    </Box>
                    <Box sx={{ fontWeight: 700, fontSize: '0.62rem', minWidth: 30, textAlign: 'right' }}>{v.percentage}%</Box>
                  </Box>
                  <Box sx={{ color: '#6B7280', fontSize: '0.58rem' }}>{v.quotes} quotes · {v.categories} categories</Box>
                </Box>
              ))}
            </Paper>

            <Paper sx={{ p: 1.5 }}>
              <Box sx={{ fontWeight: 700, fontSize: '0.78rem', mb: 0.75 }}>Top Services by Avg Price</Box>
              {topServices.map((svc, i) => (
                <Box key={i} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 0.75, bgcolor: '#F9FAFB', borderRadius: 1, mb: 0.6 }}>
                  <Box sx={{ flex: 1, mr: 1 }}>
                    <Box sx={{ fontWeight: 600, fontSize: '0.68rem', lineHeight: 1.2 }}>{svc.name}</Box>
                    <Box sx={{ color: '#6B7280', fontSize: '0.58rem' }}>{svc.category} · {svc.vendors} vendors · {svc.quotes} quotes</Box>
                  </Box>
                  <Box sx={{ fontWeight: 700, fontFamily: '"Playfair Display",serif', fontSize: '0.85rem', color: '#D04A02', whiteSpace: 'nowrap' }}>{svc.price}</Box>
                </Box>
              ))}
            </Paper>
          </Grid>
        </Grid>

        {/* Vendor Performance Table */}
        <Paper sx={{ p: 1.5, mb: 1.75 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Box sx={{ fontWeight: 700, fontSize: '0.78rem' }}>Vendor Performance</Box>
            <Box sx={{ fontSize: '0.62rem', color: '#9CA3AF' }}>{activeVendors.length} vendors tracked</Box>
          </Box>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: '#1F2937' }}>
                  {['RANK', 'VENDOR', 'BOMs', 'TOTAL SPEND', '% SHARE', 'AVG DELIVERY', 'STATUS'].map(h => (
                    <TableCell key={h} sx={{ color: 'white', fontWeight: 700, fontSize: '0.58rem', py: 0.6 }} align={h === 'VENDOR' ? 'left' : 'right'}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {loading ? Array(5).fill(0).map((_, i) => (
                  <TableRow key={i}>{Array(7).fill(0).map((_, j) => <TableCell key={j}><Skeleton /></TableCell>)}</TableRow>
                )) : activeVendors.map((v, i) => {
                  const pct = v.pct ?? (totalSpend > 0 ? (v.total_spend / totalSpend * 100).toFixed(1) : 0)
                  const ok = v.avg_delivery_time_days <= 10
                  return (
                    <TableRow key={v.vendor} sx={{ '&:hover': { bgcolor: '#FFF7F0' } }}>
                      <TableCell align="right" sx={{ py: 0.4 }}>
                        <Box sx={{ width: 22, height: 22, borderRadius: '50%', bgcolor: i === 0 ? '#D04A02' : i === 1 ? '#F59E0B' : '#E5E7EB', color: i < 2 ? 'white' : '#6B7280', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.65rem', fontWeight: 700, mx: 'auto' }}>{i + 1}</Box>
                      </TableCell>
                      <TableCell sx={{ py: 0.4, fontWeight: 600, fontSize: '0.72rem' }}>{v.vendor}</TableCell>
                      <TableCell align="right" sx={{ py: 0.4, fontSize: '0.68rem' }}>{v.bom_count}</TableCell>
                      <TableCell align="right" sx={{ py: 0.4, fontWeight: 700, fontSize: '0.72rem' }}>{fmtK(v.total_spend)}</TableCell>
                      <TableCell align="right" sx={{ py: 0.4 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                          <Box sx={{ width: Math.max(8, Number(pct) * 1.2), height: 6, bgcolor: '#D04A02', borderRadius: 1, opacity: 0.7 }} />
                          <Box sx={{ fontSize: '0.68rem', fontWeight: 700 }}>{pct}%</Box>
                        </Box>
                      </TableCell>
                      <TableCell align="right" sx={{ py: 0.4, fontSize: '0.68rem', color: ok ? '#065F46' : '#92400E', fontWeight: ok ? 700 : 400 }}>{v.avg_delivery_time_days}d</TableCell>
                      <TableCell align="right" sx={{ py: 0.4 }}>
                        <Chip size="small" label={ok ? 'On Time' : 'Slow'} sx={{ fontSize: '0.55rem', height: 16, bgcolor: ok ? '#D1FAE5' : '#FEF3C7', color: ok ? '#065F46' : '#92400E' }} />
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>

        {/* BOM Activity Register */}
        {bomList.length > 0 && (
          <Paper sx={{ p: 1.5, mb: 1.5 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Box sx={{ fontWeight: 700, fontSize: '0.78rem' }}>BOM Activity Register</Box>
              <Button size="small" onClick={() => navigate('/bom-library')} sx={{ fontSize: '0.65rem', textTransform: 'none', color: '#D04A02' }}>View All</Button>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                    {['BOM NAME', 'PROJECT', 'CATEGORY', 'ITEMS', 'VALUE', 'STATUS', 'LAST UPDATED'].map(h => (
                      <TableCell key={h} sx={{ fontWeight: 700, fontSize: '0.58rem', color: '#1F2937', letterSpacing: '0.6px', textTransform: 'uppercase', py: 0.5 }}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {bomList.slice(0, 8).map(bom => {
                    const ST = { active: { bg: '#D1FAE5', c: '#065F46' }, draft: { bg: '#FEF3C7', c: '#92400E' }, review: { bg: '#DBEAFE', c: '#1E40AF' }, approved: { bg: '#F3E8FF', c: '#6B21A8' } }
                    const s = ST[bom.status] || { bg: '#F3F4F6', c: '#6B7280' }
                    return (
                      <TableRow key={bom.id} sx={{ '&:hover': { bgcolor: '#FAFAFA' }, cursor: 'pointer' }} onClick={() => navigate('/bom-library')}>
                        <TableCell sx={{ py: 0.4, fontWeight: 600, fontSize: '0.68rem' }}>{bom.name}</TableCell>
                        <TableCell sx={{ py: 0.4, fontSize: '0.65rem', color: '#6B7280' }}>{bom.project || '—'}</TableCell>
                        <TableCell sx={{ py: 0.4, fontSize: '0.65rem' }}>{bom.category || '—'}</TableCell>
                        <TableCell sx={{ py: 0.4, fontSize: '0.68rem', textAlign: 'right' }}>{bom.lineItems?.length || 0}</TableCell>
                        <TableCell sx={{ py: 0.4, fontWeight: 700, fontSize: '0.68rem', textAlign: 'right' }}>{fmt(bom.totalValue || 0)}</TableCell>
                        <TableCell sx={{ py: 0.4 }}><Chip size="small" label={bom.status} sx={{ fontSize: '0.55rem', height: 16, bgcolor: s.bg, color: s.c }} /></TableCell>
                        <TableCell sx={{ py: 0.4, fontSize: '0.62rem', color: '#9CA3AF' }}>{bom.updatedAt ? new Date(bom.updatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        )}

        {/* Approval Cycle Health */}
        <Paper sx={{ p: 1.5, mb: 1.5 }}>
          <Box sx={{ fontWeight: 700, fontSize: '0.78rem', mb: 1 }}>Approval Cycle Health</Box>
          <Grid container spacing={1.5}>
            {[
              { party: 'Buyer IT', target: 3, avg: 2 },
              { party: 'Seller IT', target: 3, avg: 4 },
              { party: 'SI / JBR', target: 4, avg: 6 },
              { party: 'Total Cycle', target: activeKpi.target_cycle_time_days, avg: activeKpi.avg_cycle_time_days },
            ].map(({ party, target, avg }) => {
              const pct = Math.min(100, (avg / Math.max(target, avg)) * 100)
              const ok = avg <= target
              return (
                <Grid item xs={12} sm={6} md={3} key={party}>
                  <Box sx={{ p: 1, border: `1px solid ${ok ? '#D1FAE5' : '#FEF3C7'}`, borderRadius: 1, bgcolor: ok ? '#F0FDF4' : '#FFFBEB' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Box sx={{ fontSize: '0.7rem', fontWeight: 600 }}>{party}</Box>
                      <Box sx={{ fontSize: '0.62rem', color: ok ? '#10B981' : '#F59E0B', fontWeight: 700 }}>{avg}d / {target}d</Box>
                    </Box>
                    <LinearProgress variant="determinate" value={pct} sx={{ height: 5, borderRadius: 1, bgcolor: '#E5E7EB', '& .MuiLinearProgress-bar': { bgcolor: ok ? '#10B981' : '#F59E0B' } }} />
                    <Box sx={{ fontSize: '0.58rem', color: ok ? '#065F46' : '#92400E', mt: 0.4, fontWeight: 600 }}>{ok ? 'On target' : 'Over target'}</Box>
                  </Box>
                </Grid>
              )
            })}
          </Grid>
        </Paper>

      </Container>
    </Box>
  )
}
