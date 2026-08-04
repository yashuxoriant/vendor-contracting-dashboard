"""Write all enhanced frontend files for the IT Contracting Dashboard"""
import os

BASE = r'c:\Users\singh_y\workspace\it-contracting-dashboard\frontend\src'

def w(rel, content):
    path = os.path.join(BASE, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.lstrip('\n'))
    print(f'  ✓ {rel}')

# ─────────────────────────────────────────────────────────────────────────────
# 1. Layout.jsx — light sidebar
# ─────────────────────────────────────────────────────────────────────────────
w('components/Layout.jsx', r"""
import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Box, Tooltip, IconButton, Chip, Button, Typography } from '@mui/material'
import {
  Dashboard as DashboardIcon,
  CompareArrows as CompareIcon,
  Receipt as ReceiptIcon,
  Build as BuildIcon,
  AutoAwesome as ChatIcon,
  LibraryBooks as LibraryIcon,
  FileDownload, Refresh, ChevronLeft, ChevronRight,
} from '@mui/icons-material'

const NAV_W = 220
const NAV_C = 52

const menuItems = [
  { text: 'Overview', Icon: DashboardIcon, path: '/overview' },
  { text: 'BOM Library', Icon: LibraryIcon, path: '/bom-library' },
  { text: 'AI BOM Assistant', Icon: ChatIcon, path: '/chat' },
  { text: 'Vendor Price Selector', Icon: CompareIcon, path: '/vendor-selector' },
  { text: 'Quote Extractor', Icon: ReceiptIcon, path: '/quote-extractor' },
  { text: 'RFQ Builder', Icon: BuildIcon, path: '/rfq-builder' },
]

export default function Layout({ children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  return (
    <Box sx={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>

      {/* ── Light Sidebar ── */}
      <Box sx={{
        width: collapsed ? NAV_C : NAV_W, flexShrink: 0,
        bgcolor: '#FFFFFF', borderRight: '1px solid #E5E7EB',
        display: 'flex', flexDirection: 'column',
        transition: 'width 0.2s ease', overflow: 'hidden', zIndex: 100,
      }}>
        {/* PwC logo */}
        <Box sx={{
          display: 'flex', alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          gap: collapsed ? 0 : 1.25, px: collapsed ? 0 : 1.5, py: 1.25,
          minHeight: 56, flexShrink: 0, borderBottom: '1px solid #F3F4F6',
        }}>
          <Typography onClick={() => navigate('/overview')} sx={{
            fontFamily: '"Playfair Display", Georgia, serif',
            fontWeight: 800, color: '#D04A02',
            fontSize: collapsed ? '1.05rem' : '1.6rem',
            letterSpacing: '-1px', lineHeight: 1, cursor: 'pointer',
            flexShrink: 0, whiteSpace: 'nowrap', userSelect: 'none',
          }}>
            {collapsed ? 'pw' : 'pwc'}
          </Typography>
          {!collapsed && <>
            <Box sx={{ width: 1, height: 26, bgcolor: '#E5E7EB', flexShrink: 0 }} />
            <Box sx={{ overflow: 'hidden', flex: 1 }}>
              <Typography sx={{ fontWeight: 700, fontSize: '0.7rem', color: '#1F2937', lineHeight: 1.2, whiteSpace: 'nowrap' }}>
                IT Contracting
              </Typography>
              <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF', whiteSpace: 'nowrap' }}>
                Intelligence Platform
              </Typography>
            </Box>
          </>}
        </Box>

        {/* Section label */}
        {!collapsed && (
          <Box sx={{ px: 1.75, pt: 1.25, pb: 0.25 }}>
            <Typography sx={{ fontSize: '0.55rem', fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.8px' }}>
              Navigation
            </Typography>
          </Box>
        )}

        {/* Nav items */}
        <Box sx={{ flex: 1, pb: 1, overflowY: 'auto', overflowX: 'hidden' }}>
          {menuItems.map(({ text, Icon, path }) => {
            const active = location.pathname === path || (location.pathname === '/' && path === '/overview')
            const el = (
              <Box
                key={path}
                onClick={() => navigate(path)}
                sx={{
                  display: 'flex', alignItems: 'center', gap: 1.25,
                  px: collapsed ? 0 : 1.5, py: 0.85, mx: 0.6, mb: 0.2,
                  borderRadius: '6px', cursor: 'pointer',
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  bgcolor: active ? '#FDF3ED' : 'transparent',
                  borderLeft: !collapsed && active ? '3px solid #D04A02' : '3px solid transparent',
                  '&:hover': { bgcolor: active ? '#FDF3ED' : '#F9FAFB' },
                  transition: 'background 0.12s',
                }}
              >
                <Icon sx={{ fontSize: 17, color: active ? '#D04A02' : '#6B7280', flexShrink: 0 }} />
                {!collapsed && (
                  <Typography sx={{
                    fontSize: '0.75rem', fontWeight: active ? 700 : 500,
                    color: active ? '#D04A02' : '#374151',
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', lineHeight: 1.3,
                  }}>
                    {text}
                  </Typography>
                )}
              </Box>
            )
            return collapsed
              ? <Tooltip key={path} title={text} placement="right" arrow>{el}</Tooltip>
              : el
          })}
        </Box>

        {/* Status + collapse */}
        <Box sx={{ borderTop: '1px solid #F3F4F6', p: 1 }}>
          {!collapsed && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75, px: 0.5 }}>
              <Box sx={{
                width: 6, height: 6, bgcolor: '#10B981', borderRadius: '50%', flexShrink: 0,
                animation: 'navpulse 2s infinite',
                '@keyframes navpulse': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.4 } },
              }} />
              <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF' }}>48 Records · Demo Mode</Typography>
            </Box>
          )}
          <Tooltip title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} placement="right" arrow>
            <IconButton size="small" onClick={() => setCollapsed(c => !c)}
              sx={{ width: '100%', borderRadius: '6px', py: 0.5, color: '#9CA3AF', '&:hover': { bgcolor: '#F3F4F6', color: '#374151' } }}>
              {collapsed ? <ChevronRight sx={{ fontSize: 17 }} /> : <ChevronLeft sx={{ fontSize: 17 }} />}
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* ── Right: topbar + content ── */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0, bgcolor: '#FAFAFA' }}>
        <Box sx={{ height: 44, flexShrink: 0, bgcolor: 'white', borderBottom: '1px solid #E5E7EB', display: 'flex', alignItems: 'center', px: 2, gap: 1.5 }}>
          <Typography sx={{ fontWeight: 600, fontSize: '0.78rem', color: '#6B7280', flex: 1 }}>
            Vendor Benchmarking &amp; Sourcing Platform
          </Typography>
          <Chip label="● Live Demo" size="small" sx={{ bgcolor: '#D1FAE5', color: '#065F46', fontWeight: 700, fontSize: '0.6rem', height: 22, '& .MuiChip-label': { px: 1 } }} />
          <Button size="small" variant="outlined" startIcon={<Refresh sx={{ fontSize: '13px !important' }} />}
            sx={{ textTransform: 'none', fontSize: '0.7rem', fontWeight: 600, color: '#374151', borderColor: '#E5E7EB', py: 0.3, '&:hover': { borderColor: '#D04A02', color: '#D04A02' } }}>
            Refresh
          </Button>
          <Button size="small" variant="contained" startIcon={<FileDownload sx={{ fontSize: '13px !important' }} />}
            sx={{ textTransform: 'none', fontSize: '0.7rem', fontWeight: 600, bgcolor: '#D04A02', py: 0.3, '&:hover': { bgcolor: '#A33A00' } }}>
            Export
          </Button>
        </Box>
        <Box component="main" sx={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
          {children}
        </Box>
      </Box>
    </Box>
  )
}
""")

# ─────────────────────────────────────────────────────────────────────────────
# 2. App.jsx — remove outer Box wrapper, add BOM Library route
# ─────────────────────────────────────────────────────────────────────────────
w('App.jsx', r"""
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import OverviewPage from './pages/OverviewPage'
import BOMLibraryPage from './pages/BOMLibraryPage'
import ChatPage from './pages/ChatPage'
import VendorPriceSelectorPage from './pages/VendorPriceSelectorPage'
import QuoteExtractorPage from './pages/QuoteExtractorPage'
import RFQBuilderPage from './pages/RFQBuilderPage'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/bom-library" element={<BOMLibraryPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/vendor-selector" element={<VendorPriceSelectorPage />} />
        <Route path="/quote-extractor" element={<QuoteExtractorPage />} />
        <Route path="/rfq-builder" element={<RFQBuilderPage />} />
      </Routes>
    </Layout>
  )
}

export default App
""")

# ─────────────────────────────────────────────────────────────────────────────
# 3. bomSlice.js — full data model with seed BOMs + sync actions
# ─────────────────────────────────────────────────────────────────────────────
w('store/slices/bomSlice.js', r"""
import { createSlice } from '@reduxjs/toolkit'

const mkId = () => `bom_${Date.now()}_${Math.random().toString(36).slice(2,7)}`

const SEED = [
  {
    id: 'bom_001', name: 'Panasonic – Data Center COLO', project: 'Panasonic',
    category: 'Data Center / COLO', status: 'active', version: 3,
    createdAt: '2026-01-10T09:00:00Z', updatedAt: '2026-03-15T14:22:00Z',
    createdBy: 'AI Chat', totalValue: 487200,
    lineItems: [
      { id:'li_001_01', lineNo:1, category:'Hosting',              description:'Full Rack 42U Colocation Space',    unit:'/rack/mo',    qty:8,  unitPrice:2800,  extPrice:22400, vendor:'Equinix',   status:'quoted'  },
      { id:'li_001_02', lineNo:2, category:'Hosting',              description:'Power Feed 20A 208V Dual Circuit',  unit:'/rack/mo',    qty:8,  unitPrice:480,   extPrice:3840,  vendor:'Equinix',   status:'quoted'  },
      { id:'li_001_03', lineNo:3, category:'Network & Telecom',    description:'Cross-Connect 10GbE Single-Mode',   unit:'/port/mo',    qty:12, unitPrice:325,   extPrice:3900,  vendor:'Equinix',   status:'quoted'  },
      { id:'li_001_04', lineNo:4, category:'Network & Telecom',    description:'MPLS Circuit 1Gbps Primary',        unit:'/circuit/mo', qty:4,  unitPrice:4200,  extPrice:16800, vendor:'NTT Data',  status:'quoted'  },
      { id:'li_001_05', lineNo:5, category:'Network & Telecom',    description:'MPLS Circuit 500Mbps Backup',       unit:'/circuit/mo', qty:4,  unitPrice:2800,  extPrice:11200, vendor:'NTT Data',  status:'quoted'  },
      { id:'li_001_06', lineNo:6, category:'Cybersecurity',        description:'DDoS Mitigation Service',           unit:'/mo',         qty:1,  unitPrice:1800,  extPrice:1800,  vendor:'NTT Data',  status:'quoted'  },
      { id:'li_001_07', lineNo:7, category:'Cybersecurity',        description:'Security Operations Center 24x7',   unit:'/mo',         qty:1,  unitPrice:5500,  extPrice:5500,  vendor:'NTT Data',  status:'quoted'  },
      { id:'li_001_08', lineNo:8, category:'Hosting',              description:'Backup Storage 100TB',              unit:'/mo',         qty:3,  unitPrice:2100,  extPrice:6300,  vendor:'NTT DOCOMO',status:'pending' },
      { id:'li_001_09', lineNo:9, category:'Hosting',              description:'Disaster Recovery Orchestration',   unit:'/mo',         qty:1,  unitPrice:3200,  extPrice:3200,  vendor:'NTT Data',  status:'pending' },
      { id:'li_001_10', lineNo:10,category:'Service Management',   description:'Remote Hands Support 8hrs/month',   unit:'/mo',         qty:1,  unitPrice:640,   extPrice:640,   vendor:'Equinix',   status:'quoted'  },
    ],
    history: [
      { version:1, timestamp:'2026-01-10T09:00:00Z', action:'Created via AI Chat',      changes:'Initial BOM – 8 line items',               user:'AI Assistant', totalValue:421000 },
      { version:2, timestamp:'2026-02-08T11:30:00Z', action:'Updated MPLS quantities',  changes:'MPLS circuits 2 → 4 (APAC expansion)',      user:'Analyst',      totalValue:455000 },
      { version:3, timestamp:'2026-03-15T14:22:00Z', action:'Added DR services',        changes:'Added items 8–10: Backup, DR, RemoteHands', user:'AI Assistant', totalValue:487200 },
    ],
  },
  {
    id: 'bom_002', name: 'Panasonic – SD-WAN 30 Sites', project: 'Panasonic',
    category: 'SD-WAN', status: 'active', version: 2,
    createdAt: '2026-02-01T10:00:00Z', updatedAt: '2026-02-28T16:45:00Z',
    createdBy: 'AI Chat', totalValue: 312450,
    lineItems: [
      { id:'li_002_01', lineNo:1, category:'Network & Telecom', description:'SD-WAN Edge Appliance Cisco Viptela',     unit:'/device',     qty:30,   unitPrice:4800,  extPrice:144000, vendor:'CDW',       status:'quoted' },
      { id:'li_002_02', lineNo:2, category:'Network & Telecom', description:'SD-WAN Orchestration Platform (annual)',  unit:'/year',       qty:1,    unitPrice:14500, extPrice:14500,  vendor:'Cisco',     status:'quoted' },
      { id:'li_002_03', lineNo:3, category:'Network & Telecom', description:'Broadband Primary Circuit 300Mbps',       unit:'/site/mo',    qty:30,   unitPrice:420,   extPrice:12600,  vendor:'NTT Data',  status:'quoted' },
      { id:'li_002_04', lineNo:4, category:'Network & Telecom', description:'LTE Backup Circuit',                      unit:'/site/mo',    qty:30,   unitPrice:180,   extPrice:5400,   vendor:'NTT Data',  status:'quoted' },
      { id:'li_002_05', lineNo:5, category:'Cybersecurity',     description:'NGFW Appliance Palo Alto PA-220',         unit:'/device',     qty:30,   unitPrice:5200,  extPrice:156000, vendor:'CDW',       status:'quoted' },
      { id:'li_002_06', lineNo:6, category:'Cybersecurity',     description:'ZTNA Zero Trust Network Access',          unit:'/user/mo',    qty:1500, unitPrice:12,    extPrice:18000,  vendor:'Zscaler',   status:'pending'},
      { id:'li_002_07', lineNo:7, category:'Service Management',description:'SD-WAN Professional Services',            unit:'/site',       qty:30,   unitPrice:2800,  extPrice:84000,  vendor:'NTT Data',  status:'pending'},
      { id:'li_002_08', lineNo:8, category:'Network & Telecom', description:'Network Monitoring & Reporting',          unit:'/site/mo',    qty:30,   unitPrice:380,   extPrice:11400,  vendor:'NTT Data',  status:'draft'  },
    ],
    history: [
      { version:1, timestamp:'2026-02-01T10:00:00Z', action:'Created via AI Chat',   changes:'Initial SD-WAN BOM for 20 sites',                user:'AI Assistant', totalValue:228000 },
      { version:2, timestamp:'2026-02-28T16:45:00Z', action:'Expanded to 30 sites', changes:'Sites 20→30; added ZTNA & monitoring services', user:'Analyst',      totalValue:312450 },
    ],
  },
  {
    id: 'bom_003', name: 'Idemia – Cybersecurity Refresh', project: 'Idemia',
    category: 'Cybersecurity', status: 'active', version: 2,
    createdAt: '2026-01-20T14:00:00Z', updatedAt: '2026-04-02T09:15:00Z',
    createdBy: 'Analyst', totalValue: 248600,
    lineItems: [
      { id:'li_003_01', lineNo:1, category:'Cybersecurity', description:'Endpoint Detection & Response (CrowdStrike)',  unit:'/ep/yr',  qty:500, unitPrice:180,   extPrice:90000,  vendor:'CDW',       status:'quoted' },
      { id:'li_003_02', lineNo:2, category:'Cybersecurity', description:'SIEM Platform – Splunk Enterprise',           unit:'/yr',     qty:1,   unitPrice:48000, extPrice:48000,  vendor:'NTT Data',  status:'quoted' },
      { id:'li_003_03', lineNo:3, category:'Cybersecurity', description:'Vulnerability Management – Tenable.io',       unit:'/asset/yr',qty:500,unitPrice:45,    extPrice:22500,  vendor:'CDW',       status:'quoted' },
      { id:'li_003_04', lineNo:4, category:'IaAM',          description:'Privileged Access Mgmt – CyberArk',           unit:'/user/yr',qty:120, unitPrice:185,   extPrice:22200,  vendor:'NTT Data',  status:'quoted' },
      { id:'li_003_05', lineNo:5, category:'IaAM',          description:'Multi-Factor Authentication – Okta',          unit:'/user/mo',qty:600, unitPrice:8.5,   extPrice:5100,   vendor:'CDW',       status:'quoted' },
      { id:'li_003_06', lineNo:6, category:'Cybersecurity', description:'Web Application Firewall (WAF)',               unit:'/domain/mo',qty:3, unitPrice:1200,  extPrice:3600,   vendor:'NTT Data',  status:'pending'},
      { id:'li_003_07', lineNo:7, category:'Cybersecurity', description:'Penetration Testing Annual Engagement',        unit:'/yr',     qty:1,   unitPrice:22000, extPrice:22000,  vendor:'NTT Data',  status:'quoted' },
      { id:'li_003_08', lineNo:8, category:'Cybersecurity', description:'Security Awareness Training – KnowBe4',       unit:'/user/yr',qty:600, unitPrice:28,    extPrice:16800,  vendor:'CDW',       status:'pending'},
      { id:'li_003_09', lineNo:9, category:'Cybersecurity', description:'Incident Response Retainer 40hrs',             unit:'/yr',     qty:1,   unitPrice:18500, extPrice:18500,  vendor:'NTT Data',  status:'pending'},
    ],
    history: [
      { version:1, timestamp:'2026-01-20T14:00:00Z', action:'Created manually',      changes:'Initial cybersecurity BOM based on audit', user:'Security Analyst', totalValue:188000 },
      { version:2, timestamp:'2026-04-02T09:15:00Z', action:'Added IR & SAT items', changes:'Added items 8–9 after risk assessment',    user:'AI Assistant',      totalValue:248600 },
    ],
  },
  {
    id: 'bom_004', name: 'Tenneco – Network Refresh EU', project: 'Tenneco',
    category: 'Network Equipment', status: 'draft', version: 1,
    createdAt: '2026-05-15T11:00:00Z', updatedAt: '2026-05-15T11:00:00Z',
    createdBy: 'AI Chat', totalValue: 295440,
    lineItems: [
      { id:'li_004_01', lineNo:1, category:'Network & Telecom',  description:'Cisco Catalyst 9300 48P PoE+ Switch', unit:'/unit',    qty:18, unitPrice:7800,  extPrice:140400, vendor:'CDW',          status:'draft' },
      { id:'li_004_02', lineNo:2, category:'Network & Telecom',  description:'Cisco ASR 1001-X Core Router',        unit:'/unit',    qty:4,  unitPrice:12500, extPrice:50000,  vendor:'CDW',          status:'draft' },
      { id:'li_004_03', lineNo:3, category:'Cybersecurity',      description:'Cisco Meraki MX85 Security Appliance',unit:'/unit',    qty:4,  unitPrice:3900,  extPrice:15600,  vendor:'CDW',          status:'draft' },
      { id:'li_004_04', lineNo:4, category:'Network & Telecom',  description:'Fiber Optic Patch Panel 24-Port',     unit:'/unit',    qty:12, unitPrice:380,   extPrice:4560,   vendor:'PC Connection',status:'draft' },
      { id:'li_004_05', lineNo:5, category:'Hosting',            description:'Network Rack Cabinet 42U with PDU',   unit:'/unit',    qty:6,  unitPrice:1950,  extPrice:11700,  vendor:'PC Connection',status:'draft' },
      { id:'li_004_06', lineNo:6, category:'Hosting',            description:'UPS Power Backup 3kVA',               unit:'/unit',    qty:6,  unitPrice:2400,  extPrice:14400,  vendor:'PC Connection',status:'draft' },
      { id:'li_004_07', lineNo:7, category:'Service Management', description:'Cisco SmartNet Support 5Y NBD',        unit:'/unit/yr', qty:22, unitPrice:1850,  extPrice:40700,  vendor:'CDW',          status:'draft' },
      { id:'li_004_08', lineNo:8, category:'Service Management', description:'Installation & Commissioning',         unit:'/site',    qty:4,  unitPrice:4500,  extPrice:18000,  vendor:'NTT Data',     status:'draft' },
    ],
    history: [
      { version:1, timestamp:'2026-05-15T11:00:00Z', action:'Created via AI Chat', changes:'Initial network refresh BOM for 4 EU sites', user:'AI Assistant', totalValue:295440 },
    ],
  },
]

const bomSlice = createSlice({
  name: 'bom',
  initialState: {
    currentBOM: null,
    activeBOMForRFQ: null,
    bomList: SEED,
    loading: false,
    error: null,
  },
  reducers: {
    setCurrentBOM: (s, a) => { s.currentBOM = a.payload },
    setActiveBOMForRFQ: (s, a) => { s.activeBOMForRFQ = a.payload },
    saveBOM: (s, a) => {
      const bom = a.payload
      const idx = s.bomList.findIndex(b => b.id === bom.id)
      if (idx >= 0) {
        s.bomList[idx] = bom
      } else {
        s.bomList.unshift(bom)
      }
      s.currentBOM = bom
    },
    addLineItem: (s, a) => {
      if (s.currentBOM) {
        const item = { ...a.payload, id: mkId(), lineNo: s.currentBOM.lineItems.length + 1 }
        s.currentBOM.lineItems.push(item)
        s.currentBOM.totalValue = s.currentBOM.lineItems.reduce((t, i) => t + i.extPrice, 0)
      }
    },
    updateLineItem: (s, a) => {
      const { id, updates } = a.payload
      if (s.currentBOM) {
        const item = s.currentBOM.lineItems.find(i => i.id === id)
        if (item) {
          Object.assign(item, updates)
          if (updates.qty || updates.unitPrice) item.extPrice = item.qty * item.unitPrice
          s.currentBOM.totalValue = s.currentBOM.lineItems.reduce((t, i) => t + i.extPrice, 0)
        }
      }
    },
    removeLineItem: (s, a) => {
      if (s.currentBOM) {
        s.currentBOM.lineItems = s.currentBOM.lineItems.filter(i => i.id !== a.payload)
        s.currentBOM.lineItems.forEach((i, idx) => { i.lineNo = idx + 1 })
        s.currentBOM.totalValue = s.currentBOM.lineItems.reduce((t, i) => t + i.extPrice, 0)
      }
    },
    archiveBOM: (s, a) => {
      const b = s.bomList.find(x => x.id === a.payload)
      if (b) b.status = 'archived'
    },
    setBOMList: (s, a) => { s.bomList = a.payload },
    setLoading: (s, a) => { s.loading = a.payload },
    setError: (s, a) => { s.error = a.payload },
  },
})

export const { setCurrentBOM, setActiveBOMForRFQ, saveBOM, addLineItem, updateLineItem, removeLineItem, archiveBOM, setBOMList, setLoading, setError } = bomSlice.actions
export default bomSlice.reducer
""")

print('\nAll files written successfully.')
print('Run: cd frontend && npm run dev')
