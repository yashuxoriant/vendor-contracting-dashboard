import { useState, useEffect, useMemo } from 'react'
import { useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Grid, Paper, Chip, Button, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Skeleton, IconButton, Tooltip,
  LinearProgress, Select, MenuItem, FormControl, InputLabel,
} from '@mui/material'
import {
  Refresh, TrendingUp, TrendingDown, Analytics as AnalyticsIcon,
} from '@mui/icons-material'
import { Bar, Line, Doughnut } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, LineElement,
  PointElement, ArcElement, Title, Tooltip as CJSTip, Legend,
} from 'chart.js'
import { analyticsApi } from '../services/api'

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, ArcElement, Title, CJSTip, Legend)

const fmt = (v) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
const fmtK = (v) => v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${(v / 1e3).toFixed(0)}K` : `$${v}`
const SL = { fontSize: '0.58rem', fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.7px' }
const chartBase = {
  responsive: true, maintainAspectRatio: false,
  plugins: { legend: { display: false }, tooltip: { bodyFont: { size: 10 }, titleFont: { size: 10 } } },
  scales: {
    x: { grid: { display: false }, ticks: { font: { size: 9 } } },
    y: { grid: { color: '#F3F4F6' }, beginAtZero: true, ticks: { font: { size: 9 } } },
  },
}

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

export default function AnalyticsPage() {
  const navigate = useNavigate()
  const bomList = useSelector(s => s.bom?.bomList || [])
  const [period, setPeriod] = useState('monthly')
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [usingFallback, setUsingFallback] = useState(false)

  const [kpi, setKpi] = useState(null)
  const [spending, setSpending] = useState(null)
  const [vendors, setVendors] = useState(null)
  const [trends, setTrends] = useState(null)

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

  const activeKpi = kpi || FALLBACK_KPI
  const activeVendors = vendors || FALLBACK_VENDORS
  const spendData = spending || FALLBACK_SPENDING
  const trendData = trends || FALLBACK_TRENDS
  const totalSpend = spendData.reduce((s, d) => s + d.amount, 0)
  const cycleHealth = activeKpi.avg_cycle_time_days <= activeKpi.target_cycle_time_days

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

  return (
    <Box sx={{ bgcolor: '#FAFAFA', minHeight: 'calc(100vh - 42px)', overflowX: 'hidden' }}>
      <Box sx={{ py: 1.25, px: { xs: 1.5, lg: 2.5 } }}>

        {/* Header */}
        <Box sx={{ mb: 1.5, display: 'flex', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
          <Box sx={{ flex: 1 }}>
            <Box sx={{ color: '#D04A02', fontWeight: 700, letterSpacing: '0.8px', textTransform: 'uppercase', fontSize: '0.6rem', lineHeight: 1 }}>ANALYTICS</Box>
            <Box sx={{ fontWeight: 700, color: '#1F2937', fontSize: '1.3rem', lineHeight: 1.15, fontFamily: '"Playfair Display", serif' }}>Spend Intelligence</Box>
            <Box sx={{ color: '#6B7280', fontSize: '0.72rem' }}>Live metrics from BOM database · vendor performance · approval cycle analytics</Box>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mt: 0.5 }}>
            {lastUpdated && <Box sx={{ fontSize: '0.62rem', color: '#9CA3AF' }}>Updated {lastUpdated.toLocaleTimeString()}</Box>}
            {usingFallback && <Chip label="Sample data" size="small" sx={{ bgcolor: '#FEF3C7', color: '#92400E', fontSize: '0.58rem', height: 18 }} />}
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel sx={{ fontSize: '0.72rem' }}>Period</InputLabel>
              <Select value={period} onChange={e => setPeriod(e.target.value)} label="Period" sx={{ fontSize: '0.72rem', '.MuiSelect-select': { py: '3px' } }}>
                {['monthly', 'quarterly', 'yearly'].map(p => <MenuItem key={p} value={p} sx={{ fontSize: '0.72rem', textTransform: 'capitalize' }}>{p}</MenuItem>)}
              </Select>
            </FormControl>
            <Tooltip title="Refresh data">
              <IconButton size="small" onClick={load} disabled={loading} sx={{ color: '#6B7280' }}>
                <Refresh sx={{ fontSize: 16 }} />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        {loading && <LinearProgress sx={{ mb: 1, borderRadius: 1, bgcolor: '#FFE5D0', '& .MuiLinearProgress-bar': { bgcolor: '#D04A02' } }} />}

        {/* KPI Cards */}
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

        {/* Vendor Performance */}
        <Paper sx={{ p: 1.5, mb: 1.75 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Box sx={{ fontWeight: 700, fontSize: '0.78rem' }}>🏢 Vendor Performance</Box>
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
              <Box sx={{ fontWeight: 700, fontSize: '0.78rem' }}>📋 BOM Activity Register</Box>
              <Button size="small" onClick={() => navigate('/bom-library')} sx={{ fontSize: '0.65rem', textTransform: 'none', color: '#D04A02' }}>View All →</Button>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ bgcolor: '#F9FAFB' }}>
                    {['BOM NAME', 'PROJECT', 'CATEGORY', 'ITEMS', 'VALUE', 'STATUS', 'LAST UPDATED'].map(h => (
                      <TableCell key={h} sx={{ ...SL, py: 0.5 }}>{h}</TableCell>
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
          <Box sx={{ fontWeight: 700, fontSize: '0.78rem', mb: 1 }}>⏱️ Approval Cycle Health</Box>
          <Grid container spacing={1.5}>
            {[
              { party: 'Buyer IT', target: 3, avg: 2, color: '#3B82F6' },
              { party: 'Seller IT', target: 3, avg: 4, color: '#10B981' },
              { party: 'SI / JBR', target: 4, avg: 6, color: '#8B5CF6' },
              { party: 'Total Cycle', target: activeKpi.target_cycle_time_days, avg: activeKpi.avg_cycle_time_days, color: '#D04A02' },
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
                    <Box sx={{ fontSize: '0.58rem', color: ok ? '#065F46' : '#92400E', mt: 0.4, fontWeight: 600 }}>{ok ? '✅ On target' : '⚠️ Over target'}</Box>
                  </Box>
                </Grid>
              )
            })}
          </Grid>
        </Paper>

      </Box>
    </Box>
  )
}

