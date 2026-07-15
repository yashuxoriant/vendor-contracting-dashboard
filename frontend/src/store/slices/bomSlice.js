import { createSlice } from '@reduxjs/toolkit'

const mkId = () => `li_${Date.now()}_${Math.random().toString(36).slice(2,7)}`

const SEED = [
  {
    id:'bom_001', name:'Panasonic - Data Center COLO', project:'Panasonic',
    category:'Data Center / COLO', status:'active', version:3,
    createdAt:'2026-01-10T09:00:00Z', updatedAt:'2026-03-15T14:22:00Z',
    createdBy:'AI Chat', totalValue:487200,
    lineItems:[
      { id:'li_001_01', lineNo:1, category:'Hosting',           description:'Full Rack 42U Colocation Space',   unit:'/rack/mo', qty:8,  unitPrice:2800,  extPrice:22400,  vendor:'Equinix',    status:'quoted'  },
      { id:'li_001_02', lineNo:2, category:'Hosting',           description:'Power Feed 20A 208V Dual Circuit', unit:'/rack/mo', qty:8,  unitPrice:480,   extPrice:3840,   vendor:'Equinix',    status:'quoted'  },
      { id:'li_001_03', lineNo:3, category:'Network & Telecom', description:'Cross-Connect 10GbE Single-Mode',  unit:'/port/mo', qty:12, unitPrice:325,   extPrice:3900,   vendor:'Equinix',    status:'quoted'  },
      { id:'li_001_04', lineNo:4, category:'Network & Telecom', description:'MPLS Circuit 1Gbps Primary',       unit:'/ckt/mo',  qty:4,  unitPrice:4200,  extPrice:16800,  vendor:'NTT Data',   status:'quoted'  },
      { id:'li_001_05', lineNo:5, category:'Network & Telecom', description:'MPLS Circuit 500Mbps Backup',      unit:'/ckt/mo',  qty:4,  unitPrice:2800,  extPrice:11200,  vendor:'NTT Data',   status:'quoted'  },
      { id:'li_001_06', lineNo:6, category:'Cybersecurity',     description:'DDoS Mitigation Service',          unit:'/mo',      qty:1,  unitPrice:1800,  extPrice:1800,   vendor:'NTT Data',   status:'quoted'  },
      { id:'li_001_07', lineNo:7, category:'Cybersecurity',     description:'Security Operations Center 24x7',  unit:'/mo',      qty:1,  unitPrice:5500,  extPrice:5500,   vendor:'NTT Data',   status:'quoted'  },
      { id:'li_001_08', lineNo:8, category:'Hosting',           description:'Backup Storage 100TB',             unit:'/mo',      qty:3,  unitPrice:2100,  extPrice:6300,   vendor:'NTT DOCOMO', status:'pending' },
      { id:'li_001_09', lineNo:9, category:'Hosting',           description:'Disaster Recovery Orchestration',  unit:'/mo',      qty:1,  unitPrice:3200,  extPrice:3200,   vendor:'NTT Data',   status:'pending' },
      { id:'li_001_10', lineNo:10,category:'Service Management',description:'Remote Hands Support 8hrs/mo',     unit:'/mo',      qty:1,  unitPrice:640,   extPrice:640,    vendor:'Equinix',    status:'quoted'  },
    ],
    history:[
      { version:1, timestamp:'2026-01-10T09:00:00Z', action:'Created via AI Chat',     changes:'Initial BOM - 8 line items from requirements',        user:'AI Assistant', totalValue:421000 },
      { version:2, timestamp:'2026-02-08T11:30:00Z', action:'Updated MPLS quantities', changes:'MPLS circuits 2â†’4 for APAC expansion',                user:'Analyst',      totalValue:455000 },
      { version:3, timestamp:'2026-03-15T14:22:00Z', action:'Added DR services',       changes:'Added items 8 - 10: Backup, DR orchestration, RemoteHands', user:'AI Assistant', totalValue:487200 },
    ],
  },
  {
    id:'bom_002', name:'Panasonic - SD-WAN 30 Sites', project:'Panasonic',
    category:'SD-WAN', status:'active', version:2,
    createdAt:'2026-02-01T10:00:00Z', updatedAt:'2026-02-28T16:45:00Z',
    createdBy:'AI Chat', totalValue:312450,
    lineItems:[
      { id:'li_002_01', lineNo:1, category:'Network & Telecom', description:'SD-WAN Edge Appliance Cisco Viptela',   unit:'/device',  qty:30,   unitPrice:4800,  extPrice:144000, vendor:'CDW',      status:'quoted'  },
      { id:'li_002_02', lineNo:2, category:'Network & Telecom', description:'SD-WAN Orchestration Platform annual',  unit:'/year',    qty:1,    unitPrice:14500, extPrice:14500,  vendor:'Cisco',    status:'quoted'  },
      { id:'li_002_03', lineNo:3, category:'Network & Telecom', description:'Broadband Primary Circuit 300Mbps',     unit:'/site/mo', qty:30,   unitPrice:420,   extPrice:12600,  vendor:'NTT Data', status:'quoted'  },
      { id:'li_002_04', lineNo:4, category:'Network & Telecom', description:'LTE Backup Circuit',                    unit:'/site/mo', qty:30,   unitPrice:180,   extPrice:5400,   vendor:'NTT Data', status:'quoted'  },
      { id:'li_002_05', lineNo:5, category:'Cybersecurity',     description:'NGFW Appliance Palo Alto PA-220',       unit:'/device',  qty:30,   unitPrice:5200,  extPrice:156000, vendor:'CDW',      status:'quoted'  },
      { id:'li_002_06', lineNo:6, category:'Cybersecurity',     description:'ZTNA Zero Trust Network Access',        unit:'/user/mo', qty:1500, unitPrice:12,    extPrice:18000,  vendor:'Zscaler',  status:'pending' },
      { id:'li_002_07', lineNo:7, category:'Service Management',description:'SD-WAN Professional Services',          unit:'/site',    qty:30,   unitPrice:2800,  extPrice:84000,  vendor:'NTT Data', status:'pending' },
      { id:'li_002_08', lineNo:8, category:'Network & Telecom', description:'Network Monitoring & Reporting',        unit:'/site/mo', qty:30,   unitPrice:380,   extPrice:11400,  vendor:'NTT Data', status:'draft'   },
    ],
    history:[
      { version:1, timestamp:'2026-02-01T10:00:00Z', action:'Created via AI Chat',  changes:'Initial SD-WAN BOM for 20 sites',              user:'AI Assistant', totalValue:228000 },
      { version:2, timestamp:'2026-02-28T16:45:00Z', action:'Expanded to 30 sites', changes:'Sites 20â†’30; added ZTNA & monitoring services', user:'Analyst',      totalValue:312450 },
    ],
  },
  {
    id:'bom_003', name:'Idemia - Cybersecurity Refresh', project:'Idemia',
    category:'Cybersecurity', status:'active', version:2,
    createdAt:'2026-01-20T14:00:00Z', updatedAt:'2026-04-02T09:15:00Z',
    createdBy:'Analyst', totalValue:248600,
    lineItems:[
      { id:'li_003_01', lineNo:1, category:'Cybersecurity', description:'EDR - CrowdStrike Falcon',              unit:'/ep/yr',    qty:500, unitPrice:180,   extPrice:90000,  vendor:'CDW',      status:'quoted'  },
      { id:'li_003_02', lineNo:2, category:'Cybersecurity', description:'SIEM - Splunk Enterprise',              unit:'/yr',       qty:1,   unitPrice:48000, extPrice:48000,  vendor:'NTT Data', status:'quoted'  },
      { id:'li_003_03', lineNo:3, category:'Cybersecurity', description:'Vuln Management - Tenable.io',          unit:'/asset/yr', qty:500, unitPrice:45,    extPrice:22500,  vendor:'CDW',      status:'quoted'  },
      { id:'li_003_04', lineNo:4, category:'IaAM',          description:'PAM - CyberArk',                        unit:'/user/yr',  qty:120, unitPrice:185,   extPrice:22200,  vendor:'NTT Data', status:'quoted'  },
      { id:'li_003_05', lineNo:5, category:'IaAM',          description:'MFA - Okta',                            unit:'/user/mo',  qty:600, unitPrice:8.50,  extPrice:5100,   vendor:'CDW',      status:'quoted'  },
      { id:'li_003_06', lineNo:6, category:'Cybersecurity', description:'Web Application Firewall (WAF)',         unit:'/domain/mo',qty:3,   unitPrice:1200,  extPrice:3600,   vendor:'NTT Data', status:'pending' },
      { id:'li_003_07', lineNo:7, category:'Cybersecurity', description:'Penetration Testing Annual Engagement',  unit:'/yr',       qty:1,   unitPrice:22000, extPrice:22000,  vendor:'NTT Data', status:'quoted'  },
      { id:'li_003_08', lineNo:8, category:'Cybersecurity', description:'Security Awareness Training - KnowBe4', unit:'/user/yr',  qty:600, unitPrice:28,    extPrice:16800,  vendor:'CDW',      status:'pending' },
      { id:'li_003_09', lineNo:9, category:'Cybersecurity', description:'Incident Response Retainer 40hrs',       unit:'/yr',       qty:1,   unitPrice:18500, extPrice:18500,  vendor:'NTT Data', status:'pending' },
    ],
    history:[
      { version:1, timestamp:'2026-01-20T14:00:00Z', action:'Created manually',      changes:'Initial cybersec BOM based on audit findings', user:'Security Analyst', totalValue:188000 },
      { version:2, timestamp:'2026-04-02T09:15:00Z', action:'Added IR & SAT items', changes:'Added items 8 - 9 after risk assessment',        user:'AI Assistant',      totalValue:248600 },
    ],
  },
  {
    id:'bom_004', name:'Tenneco - Network Refresh EU', project:'Tenneco',
    category:'Network Equipment', status:'draft', version:1,
    createdAt:'2026-05-15T11:00:00Z', updatedAt:'2026-05-15T11:00:00Z',
    createdBy:'AI Chat', totalValue:295440,
    lineItems:[
      { id:'li_004_01', lineNo:1, category:'Network & Telecom',  description:'Cisco Catalyst 9300 48P PoE+ Switch', unit:'/unit',    qty:18, unitPrice:7800,  extPrice:140400, vendor:'CDW',          status:'draft' },
      { id:'li_004_02', lineNo:2, category:'Network & Telecom',  description:'Cisco ASR 1001-X Core Router',        unit:'/unit',    qty:4,  unitPrice:12500, extPrice:50000,  vendor:'CDW',          status:'draft' },
      { id:'li_004_03', lineNo:3, category:'Cybersecurity',      description:'Cisco Meraki MX85 Security Appliance',unit:'/unit',    qty:4,  unitPrice:3900,  extPrice:15600,  vendor:'CDW',          status:'draft' },
      { id:'li_004_04', lineNo:4, category:'Network & Telecom',  description:'Fiber Optic Patch Panel 24-Port',     unit:'/unit',    qty:12, unitPrice:380,   extPrice:4560,   vendor:'PC Connection',status:'draft' },
      { id:'li_004_05', lineNo:5, category:'Hosting',            description:'Network Rack Cabinet 42U with PDU',   unit:'/unit',    qty:6,  unitPrice:1950,  extPrice:11700,  vendor:'PC Connection',status:'draft' },
      { id:'li_004_06', lineNo:6, category:'Hosting',            description:'UPS Power Backup 3kVA',               unit:'/unit',    qty:6,  unitPrice:2400,  extPrice:14400,  vendor:'PC Connection',status:'draft' },
      { id:'li_004_07', lineNo:7, category:'Service Management', description:'Cisco SmartNet Support 5Y NBD',        unit:'/unit/yr', qty:22, unitPrice:1850,  extPrice:40700,  vendor:'CDW',          status:'draft' },
      { id:'li_004_08', lineNo:8, category:'Service Management', description:'Installation & Commissioning',         unit:'/site',    qty:4,  unitPrice:4500,  extPrice:18000,  vendor:'NTT Data',     status:'draft' },
    ],
    history:[
      { version:1, timestamp:'2026-05-15T11:00:00Z', action:'Created via AI Chat', changes:'Initial network refresh BOM for 4 EU sites', user:'AI Assistant', totalValue:295440 },
    ],
  },
]

const bomSlice = createSlice({
  name: 'bom',
  initialState: { currentBOM: null, activeBOMForRFQ: null, bomList: SEED, loading: false, error: null },
  reducers: {
    setCurrentBOM:      (s, a) => { s.currentBOM = a.payload },
    setActiveBOMForRFQ: (s, a) => { s.activeBOMForRFQ = a.payload },
    saveBOM: (s, a) => {
      const bom = { ...a.payload, updatedAt: new Date().toISOString() }
      const idx = s.bomList.findIndex(b => b.id === bom.id)
      if (idx >= 0) s.bomList[idx] = bom; else s.bomList.unshift(bom)
      s.currentBOM = bom
    },
    addLineItem: (s, a) => {
      if (!s.currentBOM) return
      const item = { ...a.payload, id: mkId(), lineNo: s.currentBOM.lineItems.length + 1, status: 'draft' }
      s.currentBOM.lineItems.push(item)
      s.currentBOM.totalValue = s.currentBOM.lineItems.reduce((t, i) => t + (i.extPrice || 0), 0)
    },
    updateLineItem: (s, a) => {
      if (!s.currentBOM) return
      const { id, updates } = a.payload
      const item = s.currentBOM.lineItems.find(i => i.id === id)
      if (item) {
        Object.assign(item, updates)
        item.extPrice = (item.qty || 1) * (item.unitPrice || 0)
        s.currentBOM.totalValue = s.currentBOM.lineItems.reduce((t, i) => t + (i.extPrice || 0), 0)
      }
    },
    removeLineItem: (s, a) => {
      if (!s.currentBOM) return
      s.currentBOM.lineItems = s.currentBOM.lineItems.filter(i => i.id !== a.payload)
      s.currentBOM.lineItems.forEach((i, idx) => { i.lineNo = idx + 1 })
      s.currentBOM.totalValue = s.currentBOM.lineItems.reduce((t, i) => t + (i.extPrice || 0), 0)
    },
    deleteBOM: (s, a) => {
      s.bomList = s.bomList.filter(b => b.id !== a.payload)
      if (s.currentBOM?.id === a.payload) s.currentBOM = null
    },
    resetToSeed: (s) => {
      s.bomList = SEED
      if (s.currentBOM && !SEED.find(b => b.id === s.currentBOM.id)) s.currentBOM = null
    },
    archiveBOM: (s, a) => { const b = s.bomList.find(x => x.id === a.payload); if (b) b.status = 'archived' },
    setBOMList: (s, a) => { s.bomList = a.payload },
    setLoading:  (s, a) => { s.loading = a.payload },
    setError:    (s, a) => { s.error = a.payload },
  },
})

export const { setCurrentBOM, setActiveBOMForRFQ, saveBOM, deleteBOM, resetToSeed, addLineItem, updateLineItem, removeLineItem, archiveBOM, setBOMList, setLoading, setError } = bomSlice.actions
export { SEED }
export default bomSlice.reducer

