import { useState } from 'react'
import {
  Container,
  Typography,
  Box,
  Grid,
  Card,
  Chip,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Alert,
  Button,
} from '@mui/material'
import { Warning } from '@mui/icons-material'
import { Bar } from 'react-chartjs-2'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend } from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend)

const projects = [
  { name: 'Idemia', files: 9, categories: 3, services: 32, vendors: 4, totalSpend: 122.62, avgQuote: 57.85, bestPrice: 310, color: '#D04A02', timeline: [30, 45, 25] },
  { name: 'Panasonic', files: 31, categories: 5, services: 75, vendors: 8, totalSpend: 331.40, avgQuote: 60.69, bestPrice: 504, color: '#10B981', timeline: [20, 35, 45] },
  { name: 'Tenneco', files: 8, categories: 2, services: 22, vendors: 4, totalSpend: 244, avgQuote: 309, bestPrice: 126, color: '#3B82F6', timeline: [40, 35, 25] },
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
  { vendor: 'NTT Data', Cybersecurity: 2.51, Hosting: 2.98, IaAM: null, 'M365 & Power Platf...': null, 'Network & Telecom': 202.83, 'Service Management...': null, total: 268.32 },
  { vendor: 'CDW', Cybersecurity: null, Hosting: null, IaAM: null, 'M365 & Power Platf...': null, 'Network & Telecom': 175.41, 'Service Management...': null, total: 175.41 },
  { vendor: 'PC Connection', Cybersecurity: null, Hosting: null, IaAM: null, 'M365 & Power Platf...': null, 'Network & Telecom': 131.90, 'Service Management...': null, total: 131.90 },
  { vendor: 'Equinix', Cybersecurity: null, Hosting: 5.12, IaAM: null, 'M365 & Power Platf...': null, 'Network & Telecom': 26.08, 'Service Management...': null, total: 31.20 },
  { vendor: 'NTT DOCOMO', Cybersecurity: null, Hosting: 24.39, IaAM: null, 'M365 & Power Platf...': null, 'Network & Telecom': null, 'Service Management...': null, total: 24.39 },
]

const vendorConcentration = [
  { rank: 1, vendor: 'NTT Data', quotes: 16, categories: 3, spend: 268.32, percentage: 40.3 },
  { rank: 2, vendor: 'CDW', quotes: 8, categories: 2, spend: 175.41, percentage: 26.7 },
  { rank: 3, vendor: 'PC Connection', quotes: 12, categories: 2, spend: 131.90, percentage: 20.1 },
  { rank: 4, vendor: 'Equinix', quotes: 4, categories: 2, spend: 31.20, percentage: 4.8 },
  { rank: 5, vendor: 'NTT DOCOMO', quotes: 5, categories: 2, spend: 24.39, percentage: 3.7 },
]

export default function OverviewPage() {
  const [selectedProject, setSelectedProject] = useState('All')
  const [region, setRegion] = useState('APAC')
  const [country, setCountry] = useState('All')
  const [selectedVendors, setSelectedVendors] = useState([])
  const [selectedCategories, setSelectedCategories] = useState([])

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { display: false } },
      y: { grid: { color: '#F3F4F6' }, beginAtZero: true },
    },
  }

  const categoriesVsQuoteData = {
    labels: categories.map(c => c.name.split(' ')[0]),
    datasets: [{ data: categories.map(c => c.files), backgroundColor: categories.map(c => c.color) }],
  }

  const servicesPerCategoryData = {
    labels: categories.map(c => c.name),
    datasets: [{ data: categories.map(c => c.services), backgroundColor: categories.map(c => c.color) }],
  }

  return (
    <Box sx={{ bgcolor: '#FAFAFA', minHeight: 'calc(100vh - 64px)' }}>
      <Container maxWidth="xl" sx={{ py: 3 }}>
        {/* Header */}
        <Box sx={{ mb: 3 }}>
          <Typography variant="caption" sx={{ color: '#D04A02', fontWeight: 700, letterSpacing: '1.2px', textTransform: 'uppercase' }}>
            EXECUTIVE DASHBOARD
          </Typography>
          <Typography variant="h3" sx={{ fontWeight: 700, color: '#1F2937', mt: 0.5 }}>
            Portfolio Overview
          </Typography>
          <Typography variant="body2" sx={{ color: '#6B7280', fontWeight: 500 }}>
            Strategic view of vendor spend, service coverage and pricing intelligence
          </Typography>
        </Box>

        {/* Project Filters & Region/Country */}
        <Box sx={{ display: 'flex', gap: 1, mb: 3, flexWrap: 'wrap', alignItems: 'center' }}>
          <Chip label="All · 48" onClick={() => setSelectedProject('All')} sx={{ bgcolor: selectedProject === 'All' ? '#1F2937' : 'white', color: selectedProject === 'All' ? 'white' : '#6B7280', fontWeight: 700, cursor: 'pointer', border: '1px solid #E5E7EB' }} />
          {projects.map((p) => (
            <Chip key={p.name} label={`${p.name} · ${p.files}`} onClick={() => setSelectedProject(p.name)} sx={{ bgcolor: selectedProject === p.name ? '#1F2937' : 'white', color: selectedProject === p.name ? 'white' : '#6B7280', fontWeight: 700, cursor: 'pointer', border: '1px solid #E5E7EB' }} />
          ))}
          <Box sx={{ flexGrow: 1 }} />
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Region</InputLabel>
            <Select value={region} onChange={(e) => setRegion(e.target.value)} label="Region" sx={{ bgcolor: 'white' }}>
              <MenuItem value="APAC">APAC</MenuItem>
              <MenuItem value="Americas">Americas</MenuItem>
              <MenuItem value="EMEA">EMEA</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Country</InputLabel>
            <Select value={country} onChange={(e) => setCountry(e.target.value)} label="Country" sx={{ bgcolor: 'white' }}>
              <MenuItem value="All">All Countries</MenuItem>
              <MenuItem value="United States">United States</MenuItem>
              <MenuItem value="Germany">Germany</MenuItem>
            </Select>
          </FormControl>
        </Box>

        {/* Project Portfolio */}
        <Typography variant="caption" sx={{ color: '#1F2937', fontWeight: 700, letterSpacing: '0.8px', textTransform: 'uppercase', mb: 1, display: 'block' }}>
          PROJECT PORTFOLIO · Click to drill in · each card shows full project snapshot
        </Typography>
        <Grid container spacing={2} sx={{ mb: 4 }}>
          {projects.map((project) => (
            <Grid item xs={12} md={4} key={project.name}>
              <Card sx={{ border: `4px solid ${project.color}`, borderLeft: `8px solid ${project.color}`, cursor: 'pointer', '&:hover': { boxShadow: 4 } }}>
                <Box sx={{ p: 2.5 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
                    <Typography variant="h5" sx={{ fontWeight: 700, fontFamily: '"Playfair Display", serif' }}>
                      {project.name}
                    </Typography>
                    <Chip label={`${project.files} files`} size="small" sx={{ bgcolor: '#D04A02', color: 'white', fontWeight: 700 }} />
                  </Box>
                  <Typography variant="caption" sx={{ color: '#6B7280', mb: 2, display: 'block' }}>
                    {project.categories} categories · {project.services} services · {project.vendors} vendors
                  </Typography>
                  
                  {/* Timeline */}
                  <Box sx={{ display: 'flex', gap: 0.5, height: 8, mb: 1.5 }}>
                    {project.timeline.map((pct, idx) => (
                      <Box key={idx} sx={{ width: `${pct}%`, bgcolor: ['#FFD4B3', '#FFB380', project.color][idx], borderRadius: idx === 0 ? '4px 0 0 4px' : idx === 2 ? '0 4px 4px 0' : 0 }} />
                    ))}
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1.5 }}>
                    <Typography variant="caption" sx={{ color: '#9CA3AF', fontSize: '0.70rem' }}>2024</Typography>
                    <Typography variant="caption" sx={{ color: '#9CA3AF', fontSize: '0.70rem' }}>2025</Typography>
                    <Typography variant="caption" sx={{ color: '#9CA3AF', fontSize: '0.70rem' }}>2026</Typography>
                  </Box>

                  {/* Metrics */}
                  <Grid container spacing={1.5}>
                    <Grid item xs={4}>
                      <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: '"Playfair Display", serif', fontSize: '1.35rem', color: '#1F2937' }}>
                        ${project.totalSpend}M
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#6B7280', fontSize: '0.64rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.6px' }}>
                        TOTAL SPEND
                      </Typography>
                    </Grid>
                    <Grid item xs={4}>
                      <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: '"Playfair Display", serif', fontSize: '1.35rem', color: '#D04A02' }}>
                        ${project.avgQuote}M
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#6B7280', fontSize: '0.64rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.6px' }}>
                        AVG QUOTE
                      </Typography>
                    </Grid>
                    <Grid item xs={4}>
                      <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: '"Playfair Display", serif', fontSize: '1.35rem', color: '#10B981' }}>
                        ${project.bestPrice}K
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#6B7280', fontSize: '0.64rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.6px' }}>
                        BEST PRICE
                      </Typography>
                    </Grid>
                  </Grid>
                </Box>
              </Card>
            </Grid>
          ))}
        </Grid>

        {/* AT A GLANCE Charts */}
        <Typography variant="caption" sx={{ color: '#1F2937', fontWeight: 700, letterSpacing: '0.8px', textTransform: 'uppercase', mb: 1.5, display: 'block' }}>
          AT A GLANCE · Simple metrics for quick understanding
        </Typography>
        <Grid container spacing={2} sx={{ mb: 4 }}>
          <Grid item xs={12} md={3}>
            <Paper sx={{ p: 2, height: 260 }}>
              <Typography variant="caption" sx={{ color: '#6B7280', fontSize: '0.75rem', fontWeight: 600, mb: 1, display: 'block' }}>
                Categories vs Quote Volume
              </Typography>
              <Box sx={{ height: 220 }}>
                <Bar data={categoriesVsQuoteData} options={chartOptions} />
              </Box>
            </Paper>
          </Grid>
          <Grid item xs={12} md={3}>
            <Paper sx={{ p: 2, height: 260 }}>
              <Typography variant="caption" sx={{ color: '#6B7280', fontSize: '0.75rem', fontWeight: 600, mb: 1, display: 'block' }}>
                Services per Category
              </Typography>
              <Box sx={{ height: 220 }}>
                <Bar data={servicesPerCategoryData} options={{ ...chartOptions, indexAxis: 'y' }} />
              </Box>
            </Paper>
          </Grid>
          <Grid item xs={12} md={3}>
            <Paper sx={{ p: 2, height: 260 }}>
              <Typography variant="caption" sx={{ color: '#6B7280', fontSize: '0.75rem', fontWeight: 600, mb: 1, display: 'block' }}>
                Vendors by Quote Volume
              </Typography>
              <Box sx={{ height: 220 }}>
                <Bar data={{ labels: vendorConcentration.map(v => v.vendor), datasets: [{ data: vendorConcentration.map(v => v.quotes), backgroundColor: '#D04A02' }] }} options={{ ...chartOptions, indexAxis: 'y' }} />
              </Box>
            </Paper>
          </Grid>
          <Grid item xs={12} md={3}>
            <Paper sx={{ p: 2, height: 260 }}>
              <Typography variant="caption" sx={{ color: '#6B7280', fontSize: '0.75rem', fontWeight: 600, mb: 1, display: 'block' }}>
                Vendors by Avg Price Quoted
              </Typography>
              <Box sx={{ height: 220 }}>
                <Bar data={{ labels: vendorConcentration.map(v => v.vendor), datasets: [{ data: vendorConcentration.map(v => v.spend), backgroundColor: '#3B82F6' }] }} options={{ ...chartOptions, indexAxis: 'y' }} />
              </Box>
            </Paper>
          </Grid>
        </Grid>

        {/* Vendor × Category Spend Heatmap */}
        <Typography variant="caption" sx={{ color: '#1F2937', fontWeight: 700, letterSpacing: '0.8px', textTransform: 'uppercase', mb: 1.5, display: 'block' }}>
          DETAILED INSIGHTS · Deeper analysis for strategic decisions
        </Typography>
        <Paper sx={{ p: 2.5, mb: 4 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 1 }}>
              🔥 Vendor × Category Spend Heatmap
            </Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button size="small" variant="outlined">All</Button>
              <Button size="small" variant="outlined">Clear</Button>
            </Box>
          </Box>
          
          {/* Heatmap Filters */}
          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <Box>
              <Typography variant="caption" sx={{ color: '#6B7280', fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.8px', mb: 0.5, display: 'block' }}>
                🟦 VENDORS
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {['TransMicro', 'Panasonic', 'NTT Data', 'Sify', 'Equinix'].map((v) => (
                  <Chip key={v} label={`${v} ${v === 'NTT Data' ? '16' : v === 'Panasonic' ? '5' : '3'}`} size="small" sx={{ bgcolor: '#D04A02', color: 'white', fontWeight: 700, fontSize: '0.7rem' }} />
                ))}
                <Chip label="ALL" size="small" sx={{ color: '#D04A02', fontWeight: 700 }} />
              </Box>
            </Box>
            <Box sx={{ flexGrow: 1 }}>
              <Typography variant="caption" sx={{ color: '#6B7280', fontWeight: 700, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.8px', mb: 0.5, display: 'block' }}>
                🟩 CATEGORIES
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {['Cybersecurity 16', 'Hosting 7', 'IaAM 9', 'M365 & Power Platform 5', 'Network & Telecom 16', 'Service Management... 2'].map((c) => (
                  <Chip key={c} label={c} size="small" sx={{ bgcolor: '#D04A02', color: 'white', fontWeight: 700, fontSize: '0.7rem' }} />
                ))}
                <Chip label="ALL" size="small" sx={{ color: '#D04A02', fontWeight: 700 }} />
              </Box>
            </Box>
          </Box>

          {/* Heatmap Table */}
          <TableContainer sx={{ border: '1px solid #E5E7EB', borderRadius: 1 }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: '#1F2937' }}>
                  <TableCell sx={{ color: 'white', fontWeight: 700, minWidth: 200, position: 'sticky', left: 0, bgcolor: '#1F2937', zIndex: 2 }}>Vendor</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700, textAlign: 'center' }}>🟧 Cybersecurity</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700, textAlign: 'center' }}>🟦 Hosting</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700, textAlign: 'center' }}>🟨 IaAM</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700, textAlign: 'center' }}>🟪 M365 & Power Platf...</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700, textAlign: 'center' }}>⬛ Network & Telecom</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700, textAlign: 'center' }}>🟩 Service Management...</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700, textAlign: 'right' }}>Total</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {heatmapData.map((row) => (
                  <TableRow key={row.vendor}>
                    <TableCell sx={{ fontWeight: 600, position: 'sticky', left: 0, bgcolor: '#FAFAFA', borderRight: '1px solid #E5E7EB' }}>{row.vendor}</TableCell>
                    {Object.keys(row).filter(k => k !== 'vendor' && k !== 'total').map((key) => (
                      <TableCell key={key} sx={{ textAlign: 'center', bgcolor: row[key] ? '#FFE5D0' : '#FAFAFA', cursor: row[key] ? 'pointer' : 'default', fontWeight: row[key] ? 700 : 400, color: row[key] ? '#1F2937' : '#CBD5E1' }}>
                        {row[key] ? `$${row[key]}M` : '—'}
                      </TableCell>
                    ))}
                    <TableCell sx={{ textAlign: 'right', fontWeight: 700 }}>${row.total}M</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>

        {/* Category Deep-Dive & Vendor Concentration */}
        <Grid container spacing={2} sx={{ mb: 4 }}>
          <Grid item xs={12} md={8}>
            <Paper sx={{ p: 2.5 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 2 }}>
                📊 Category Deep-Dive
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#F3F4F6' }}>
                      <TableCell sx={{ fontWeight: 700, fontSize: '0.68rem', textTransform: 'uppercase' }}>CATEGORY</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.68rem', textTransform: 'uppercase' }}>FILES</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.68rem', textTransform: 'uppercase' }}>SERVICES</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.68rem', textTransform: 'uppercase' }}>VENDORS</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.68rem', textTransform: 'uppercase' }}>PRICE RANGE</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.68rem', textTransform: 'uppercase' }}>AVG</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: '0.68rem', textTransform: 'uppercase' }}>VOLATILITY</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {categories.map((cat) => (
                      <TableRow key={cat.name}>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Box sx={{ width: 8, height: 8, borderRadius: '2px', bgcolor: cat.color }} />
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>{cat.name}</Typography>
                          </Box>
                        </TableCell>
                        <TableCell align="right">{cat.files}</TableCell>
                        <TableCell align="right">{cat.services}</TableCell>
                        <TableCell align="right">{cat.vendors}</TableCell>
                        <TableCell align="right">
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, justifyContent: 'flex-end' }}>
                            <Box sx={{ width: 60, height: 6, background: 'linear-gradient(90deg, #10B981 0%, #F59E0B 50%, #EF4444 100%)', borderRadius: 1 }} />
                            <Typography variant="caption" sx={{ fontSize: '0.7rem', fontWeight: 600 }}>
                              ${cat.priceMin} - ${(cat.priceMax/1000).toFixed(0)}K
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>${cat.avg.toLocaleString()}</TableCell>
                        <TableCell align="right">
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, justifyContent: 'flex-end' }}>
                            <Box sx={{ width: 40, height: 6, bgcolor: '#EF4444', borderRadius: 1 }} />
                            <Typography variant="caption" sx={{ fontWeight: 700, color: '#EF4444' }}>{cat.volatility}%</Typography>
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
            <Paper sx={{ p: 2.5, mb: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                  📍 Vendor Concentration Risk
                </Typography>
                <Chip label="15 vendors" size="small" sx={{ bgcolor: '#10B981', color: 'white', fontWeight: 700 }} />
              </Box>
              <Alert severity="error" sx={{ mb: 2 }}>
                <Typography variant="caption" sx={{ fontWeight: 700, display: 'block' }}>
                  ⚠️ HIGH CONCENTRATION
                </Typography>
                <Typography variant="caption">
                  Top 5 vendors = 96.1% of total spend
                </Typography>
              </Alert>
              
              {vendorConcentration.map((v) => (
                <Box key={v.vendor} sx={{ mb: 1.5 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <Typography variant="caption" sx={{ fontWeight: 700, color: '#6B7280' }}>
                        {v.rank}
                      </Typography>
                      <Chip label={v.vendor} size="small" sx={{ bgcolor: '#D04A02', color: 'white', fontWeight: 700, fontSize: '0.7rem', height: 20 }} />
                    </Box>
                    <Typography variant="caption" sx={{ fontWeight: 700 }}>
                      ${v.spend}M
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ flexGrow: 1, height: 6, bgcolor: '#E5E7EB', borderRadius: 1, overflow: 'hidden' }}>
                      <Box sx={{ width: `${v.percentage}%`, height: '100%', bgcolor: '#D04A02' }} />
                    </Box>
                    <Typography variant="caption" sx={{ fontWeight: 700, minWidth: 40, textAlign: 'right' }}>
                      {v.percentage}%
                    </Typography>
                  </Box>
                  <Typography variant="caption" sx={{ color: '#6B7280', fontSize: '0.68rem' }}>
                    {v.quotes} quotes · {v.categories} categories
                  </Typography>
                </Box>
              ))}
            </Paper>

            <Paper sx={{ p: 2.5 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5 }}>
                💰 Top Services by Average Price
              </Typography>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 1.5, bgcolor: '#F9FAFB', borderRadius: 1 }}>
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>[object Object]</Typography>
                  <Typography variant="caption" sx={{ color: '#6B7280' }}>Cybersecurity · 15 vendors · 130 quotes</Typography>
                </Box>
                <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: '"Playfair Display", serif', color: '#D04A02' }}>
                  $18.52M
                </Typography>
              </Box>
            </Paper>
          </Grid>
        </Grid>
      </Container>
    </Box>
  )
}
