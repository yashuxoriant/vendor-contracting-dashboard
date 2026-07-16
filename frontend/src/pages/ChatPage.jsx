import { useState, useRef, useEffect, useCallback } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, TextField, IconButton, Paper, Chip, Button,
  Avatar, Tooltip, LinearProgress, Snackbar, Alert,
  Dialog, DialogContent, DialogTitle, DialogActions,
} from '@mui/material'
import {
  Send, Add, AutoAwesome, Save, Build, Download,
  Person, FolderOpen, CloudDone, CloudOff, RateReview, DeleteOutline, Close,
} from '@mui/icons-material'
import { saveBOM, deleteBOM, setCurrentBOM, setActiveBOMForRFQ } from '../store/slices/bomSlice'
import { pushNotification } from '../store/slices/notificationsSlice'
import { chatApi, bomApi } from '../services/api'

const PHASE_NAMES = [
  '', // 0-indexed, phase 1 = index 1
  'Scope & Constraints',
  'Seller Inventory',
  'Compute Sizing',
  'Storage Sizing',
  'Network Sizing',
  'Power & Physical',
  'Build BOM',
  'Approvals',
  'Validate',
  'Procurement',
]

// Phase-specific quick-reply suggestions
const PHASE_CHIPS = [
  [],
  ['SD-WAN for 30 sites', 'Data Center for Panasonic', 'Cybersecurity for Idemia'],
  ['5 sites, 200 users per site', '10 branch offices'],
  ['Dual-socket server 256GB RAM', 'VM-based compute cluster'],
  ['100TB primary storage', 'NVMe SSD for latency-sensitive'],
  ['10Gbps WAN uplink', '1Gbps LAN switching'],
  ['5kW per rack', 'Diesel generator backup'],
  ['Finalise BOM now', 'Add Cisco SmartNet from CDW'],
  ['Save BOM', 'Send to RFQ Builder'],
  ['Validate BOM', 'Export as Excel'],
  ['Export as Excel', 'Send to RFQ'],
]

const TEMPLATES = {
  'Data Center / COLO': [
    { desc:'Full Rack 42U Colocation Space',    cat:'Hosting',           unit:'/rack/mo', price:2800,  vendor:'Equinix'     },
    { desc:'Power Feed 20A 208V Dual Circuit',  cat:'Hosting',           unit:'/rack/mo', price:480,   vendor:'Equinix'     },
    { desc:'Cross-Connect 10GbE Single-Mode',   cat:'Network & Telecom', unit:'/port/mo', price:325,   vendor:'Equinix'     },
    { desc:'MPLS Circuit 1Gbps Primary',        cat:'Network & Telecom', unit:'/ckt/mo',  price:4200,  vendor:'NTT Data'    },
    { desc:'MPLS Circuit 500Mbps Backup',       cat:'Network & Telecom', unit:'/ckt/mo',  price:2800,  vendor:'NTT Data'    },
    { desc:'DDoS Mitigation Service',           cat:'Cybersecurity',     unit:'/mo',      price:1800,  vendor:'NTT Data'    },
    { desc:'Security Operations Center 24x7',   cat:'Cybersecurity',     unit:'/mo',      price:5500,  vendor:'NTT Data'    },
    { desc:'Backup Storage 100TB',              cat:'Hosting',           unit:'/mo',      price:2100,  vendor:'NTT DOCOMO'  },
    { desc:'Disaster Recovery Orchestration',   cat:'Hosting',           unit:'/mo',      price:3200,  vendor:'NTT Data'    },
    { desc:'Remote Hands Support 8hrs/month',   cat:'Service Management',unit:'/mo',      price:640,   vendor:'Equinix'     },
  ],
  'SD-WAN': [
    { desc:'SD-WAN Edge Appliance Cisco Viptela',  cat:'Network & Telecom', unit:'/device',  price:4800,  vendor:'CDW'      },
    { desc:'SD-WAN Orchestration Platform annual', cat:'Network & Telecom', unit:'/year',    price:14500, vendor:'Cisco'    },
    { desc:'Broadband Primary Circuit 300Mbps',    cat:'Network & Telecom', unit:'/site/mo', price:420,   vendor:'NTT Data' },
    { desc:'LTE Backup Circuit',                   cat:'Network & Telecom', unit:'/site/mo', price:180,   vendor:'NTT Data' },
    { desc:'NGFW Appliance Palo Alto PA-220',      cat:'Cybersecurity',     unit:'/device',  price:5200,  vendor:'CDW'      },
    { desc:'ZTNA Zero Trust Network Access',       cat:'Cybersecurity',     unit:'/user/mo', price:12,    vendor:'Zscaler'  },
    { desc:'SD-WAN Professional Services',         cat:'Service Management',unit:'/site',    price:2800,  vendor:'NTT Data' },
    { desc:'Network Monitoring & Reporting',       cat:'Network & Telecom', unit:'/site/mo', price:380,   vendor:'NTT Data' },
  ],
  'Cybersecurity': [
    { desc:'EDR - CrowdStrike Falcon',              cat:'Cybersecurity', unit:'/ep/yr',    price:180,   vendor:'CDW'      },
    { desc:'SIEM - Splunk Enterprise',              cat:'Cybersecurity', unit:'/yr',       price:48000, vendor:'NTT Data' },
    { desc:'Vulnerability Management - Tenable.io', cat:'Cybersecurity', unit:'/asset/yr', price:45,    vendor:'CDW'      },
    { desc:'PAM - CyberArk',                       cat:'IaAM',          unit:'/user/yr',  price:185,   vendor:'NTT Data' },
    { desc:'MFA - Okta',                           cat:'IaAM',          unit:'/user/mo',  price:8.5,   vendor:'CDW'      },
    { desc:'Web Application Firewall (WAF)',        cat:'Cybersecurity', unit:'/domain/mo',price:1200,  vendor:'NTT Data' },
    { desc:'Penetration Testing Annual',            cat:'Cybersecurity', unit:'/yr',       price:22000, vendor:'NTT Data' },
    { desc:'Security Awareness Training KnowBe4',  cat:'Cybersecurity', unit:'/user/yr',  price:28,    vendor:'CDW'      },
    { desc:'Incident Response Retainer 40hrs',      cat:'Cybersecurity', unit:'/yr',       price:18500, vendor:'NTT Data' },
  ],
  'Network Equipment': [
    { desc:'Cisco Catalyst 9300 48P PoE+ Switch', cat:'Network & Telecom',  unit:'/unit',    price:7800,  vendor:'CDW'           },
    { desc:'Cisco ASR 1001-X Core Router',        cat:'Network & Telecom',  unit:'/unit',    price:12500, vendor:'CDW'           },
    { desc:'Cisco Meraki MX85 Security Appliance',cat:'Cybersecurity',      unit:'/unit',    price:3900,  vendor:'CDW'           },
    { desc:'Fiber Optic Patch Panel 24-Port',     cat:'Network & Telecom',  unit:'/unit',    price:380,   vendor:'PC Connection' },
    { desc:'Network Rack Cabinet 42U with PDU',   cat:'Hosting',           unit:'/unit',    price:1950,  vendor:'PC Connection' },
    { desc:'UPS Power Backup 3kVA',               cat:'Hosting',           unit:'/unit',    price:2400,  vendor:'PC Connection' },
    { desc:'Cisco SmartNet Support 5Y NBD',        cat:'Service Management',unit:'/unit/yr', price:1850,  vendor:'CDW'           },
    { desc:'Installation & Commissioning',         cat:'Service Management',unit:'/site',    price:4500,  vendor:'NTT Data'      },
  ],
  'M365 & Power Platform': [
    { desc:'Microsoft 365 E3 License',          cat:'M365 & Power Platform', unit:'/user/mo', price:36,    vendor:'CDW'      },
    { desc:'M365 E5 Security Add-on',           cat:'M365 & Power Platform', unit:'/user/mo', price:12,    vendor:'CDW'      },
    { desc:'Power BI Premium Capacity',         cat:'M365 & Power Platform', unit:'/mo',      price:4995,  vendor:'CDW'      },
    { desc:'Power Apps Per-App Plan',           cat:'M365 & Power Platform', unit:'/user/mo', price:10,    vendor:'CDW'      },
    { desc:'SharePoint Intranet Setup',         cat:'M365 & Power Platform', unit:'/impl',    price:15000, vendor:'NTT Data' },
    { desc:'Teams Direct Routing (PSTN)',       cat:'M365 & Power Platform', unit:'/user/mo', price:18,    vendor:'NTT Data' },
    { desc:'Azure Active Directory P2',         cat:'IaAM',                  unit:'/user/mo', price:9,     vendor:'CDW'      },
    { desc:'M365 Migration & Onboarding',       cat:'Service Management',    unit:'/user',    price:85,    vendor:'NTT Data' },
  ],
  'Cloud Infrastructure': [
    { desc:'Azure ExpressRoute 1Gbps metered',  cat:'Network & Telecom', unit:'/ckt/mo', price:8500,  vendor:'NTT Data'   },
    { desc:'Azure Virtual WAN Hub',             cat:'Network & Telecom', unit:'/mo',     price:3200,  vendor:'NTT DOCOMO' },
    { desc:'Azure Backup 100TB Vault',          cat:'Hosting',           unit:'/mo',     price:2100,  vendor:'NTT DOCOMO' },
    { desc:'Azure Sentinel SIEM 500GB/day',     cat:'Cybersecurity',     unit:'/mo',     price:4200,  vendor:'NTT DOCOMO' },
    { desc:'Azure Defender for Cloud',          cat:'Cybersecurity',     unit:'/srv/mo', price:15,    vendor:'Microsoft'  },
    { desc:'Azure IAM & Conditional Access',    cat:'IaAM',              unit:'/mo',     price:2400,  vendor:'Microsoft'  },
    { desc:'Cloud Governance & Landing Zone',   cat:'Service Management',unit:'/impl',   price:45000, vendor:'NTT Data'   },
    { desc:'Cloud FinOps & Cost Management',    cat:'Service Management',unit:'/mo',     price:3500,  vendor:'NTT Data'   },
  ],
}

const CATEGORIES = Object.keys(TEMPLATES)
const PROJECTS = ['Panasonic', 'Idemia', 'Tenneco']

function detectCategory(msg) {
  const m = msg.toLowerCase()
  if (m.match(/data.?cent|colo/)) return 'Data Center / COLO'
  if (m.match(/sd.?wan|wan|branch/)) return 'SD-WAN'
  if (m.match(/cyber|security|siem|edr|firewall|soc/)) return 'Cybersecurity'
  if (m.match(/network equip|switch|router|cisco cat|asr|patch/)) return 'Network Equipment'
  if (m.match(/m365|365|office|teams|sharepoint|power.?bi/)) return 'M365 & Power Platform'
  if (m.match(/cloud|azure|aws|expressroute|landing zone/)) return 'Cloud Infrastructure'
  return null
}
function detectProject(msg) {
  const m = msg.toLowerCase()
  if (m.includes('panasonic')) return 'Panasonic'
  if (m.includes('idemia')) return 'Idemia'
  if (m.includes('tenneco')) return 'Tenneco'
  return null
}
function extractQty(msg) {
  const m = msg.match(/(\d+)\s*(site|rack|server|device|user|node|location)/i)
  return m ? parseInt(m[1]) : 1
}
function buildBOM(project, category, qty = 1) {
  const items = TEMPLATES[category] || TEMPLATES['Data Center / COLO']
  const lineItems = items.map((t, i) => ({
    id: 'li_' + Date.now() + '_' + i, lineNo: i + 1,
    category: t.cat, description: t.desc, unit: t.unit,
    qty, unitPrice: t.price, extPrice: t.price * qty,
    vendor: t.vendor, status: 'draft',
  }))
  const total = lineItems.reduce((s, i) => s + i.extPrice, 0)
  return {
    id: 'bom_draft_' + Date.now(),
    name: project + ' - ' + category,
    project, category, status: 'draft', version: 1,
    createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
    createdBy: 'AI Chat', lineItems, totalValue: total,
    history: [{ version: 1, timestamp: new Date().toISOString(), action: 'Created via AI Chat', changes: lineItems.length + ' services generated', user: 'AI Assistant', totalValue: total }],
  }
}

const fmt = (v) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)

// BOM modification commands — always handled locally (backend has no in-memory BOM state)
function isLocalBOMCmd(msg, hasBOM = false) {
  const m = msg.toLowerCase().trim()
  return (
    // Explicit item-level updates: "change item 2 qty to 8", "update item 3 price to $500"
    /^(change|update|set|modify|adjust)\s+(item\s+)?\d+/.test(m) ||
    // Remove: "remove item 5", "delete item 3"
    /^(remove|delete|drop)\s+(item\s+)?\d+/.test(m) ||
    // Add — any phrasing: "add", "include", "insert", "i want to add", "can you add"
    /^(add|include|insert|append)\s+/.test(m) ||
    /\b(add|include|insert)\s+(a\s+)?(new\s+)?(item|service|product|tool|software|license)/i.test(m) ||
    // "modify/update this BOM by adding..."
    /\b(modify|update|change)\s+(this\s+)?(bom|list)\s+(by\s+)?(adding|including|inserting)/i.test(m) ||
    // Save / confirm — ONLY intercept when a draft BOM is in the panel.
    // Without this guard, "confirmed" during agent intake would be swallowed locally.
    (hasBOM && /^(save|confirm|done|ok|yes|looks good|perfect)/.test(m)) ||
    // Export — only meaningful when a BOM exists
    (hasBOM && /^(export|download|csv|excel)/.test(m)) ||
    // Analysis — only meaningful when a BOM exists
    (hasBOM && /^(analyz|insight|saving|cost|cheaper|break|summary|show\s+(cost|spend))/.test(m)) ||
    // List BOMs — always local (reads Redux store)
    /^(show|list)\s+(my\s+)?(bom|all)/.test(m) ||
    // Load / RFQ
    /^(load|open|edit)\s+/.test(m) ||
    /^(send\s+to\s+rfq|rfq)/.test(m)
  )
}

// Parse an item-add request from many natural language phrasings:
// "add CrowdStrike Falcon EDR at $345"
// "add new item in BOM - CrowdStrike Falcon EDR amount - $345"
// "modify this BOM by adding this new item name - CrowdStrike Falcon EDR amount - $345"
function parseAddItem(rawMsg) {
  let m = rawMsg

  // Strip command preamble
  m = m.replace(/^.*(add|include|insert|append)\s+(this\s+)?(new\s+)?(item\s+)?(in\s+(bom|list)\s*[-:–]?\s*)?/i, '')
  m = m.replace(/^.*(modify|update|change)\s+(this\s+)?(bom|list)\s+(by\s+)?(adding|including)\s+(this\s+)?(new\s+)?(item\s+)?(name\s*[-:–]?\s*)?/i, '')
  m = m.replace(/^(name\s*[-:–]?\s*)/i, '')
  m = m.trim()

  // Extract price: "at $345", "amount - $345", "price: $345", "cost $345", "$345"
  const priceM = m.match(/(?:at|amount|price|cost|for)\s*[-:–]?\s*\$?([\d,]+(?:\.\d+)?)/i)
    || m.match(/\$\s*([\d,]+(?:\.\d+)?)/i)
  const price = priceM ? parseFloat(priceM[1].replace(/,/g, '')) : 0

  // Extract vendor: "from CDW", "vendor: CDW"
  const vendorM = m.match(/(?:^|\s)(?:from|vendor[:.]?\s*)([\w][\w\s]{1,30}?)(?=\s+(?:at|amount|price|cost|\$)|$)/i)
  const vendor = vendorM ? vendorM[1].trim() : 'CDW'

  // Description: strip price/vendor parts from what remains
  let desc = m
    .replace(/(?:from|vendor[:.]?\s*)[\w][\w\s]{1,30}?(?=\s+(?:at|amount|price|cost|\$)|$)/i, '')
    .replace(/(?:at|amount|price|cost|for)\s*[-:–]?\s*\$?[\d,]+(?:\.\d+)?/i, '')
    .replace(/\$\s*[\d,]+(?:\.\d+)?/i, '')
    .replace(/[-–,]+$/, '')
    .trim()

  // Capitalise
  if (desc) desc = desc.charAt(0).toUpperCase() + desc.slice(1)
  return { desc, vendor, price }
}

function exportBOMasCSV(bom) {
  const headers = ['Line No', 'Description', 'Category', 'Unit', 'Qty', 'Unit Price (USD)', 'Ext Price (USD)', 'Vendor', 'Status']
  const rows = bom.lineItems.map(i => [
    i.lineNo,
    '"' + i.description.replace(/"/g, '""') + '"',
    '"' + i.category.replace(/"/g, '""') + '"',
    '"' + i.unit.replace(/"/g, '""') + '"',
    i.qty,
    i.unitPrice,
    i.extPrice,
    '"' + i.vendor.replace(/"/g, '""') + '"',
    i.status,
  ])
  const summaryRow = ['', '', '', '', 'TOTAL', '', bom.totalValue, '', '']
  const csv = [headers.join(','), ...rows.map(r => r.join(',')), summaryRow.join(',')].join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = bom.name.replace(/[^a-zA-Z0-9 _-]/g, '') + '_BOM.csv'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function getAIResponse(userMsg, currentBOM, bomList, ctx) {
  const msg = userMsg.toLowerCase().trim()
  const cat = detectCategory(msg)
  const proj = detectProject(msg)
  const qty = extractQty(msg)

  if (msg.match(/^(save|confirm|done|ok|yes|looks good|perfect|approve)/)) {
    if (currentBOM) return {
      type: 'saved',
      text: 'BOM **"' + currentBOM.name + '"** saved to the BOM Library with **' + currentBOM.lineItems.length + ' line items** totalling **' + fmt(currentBOM.totalValue) + '**.\n\nYou can view it in the BOM Library or send it to RFQ Builder.',
      bom: currentBOM, actions: ['library', 'rfq'],
    }
    return { type: 'text', text: "No active BOM to save. Try: Create a Data Center BOM for Panasonic" }
  }

  if (msg.match(/rfq|send to rfq/)) {
    if (currentBOM) return { type: 'rfq', text: 'BOM **"' + currentBOM.name + '"** is ready for the RFQ Builder.', bom: currentBOM, actions: ['rfq'] }
  }

  // ── Add item to BOM — handles many natural-language phrasings ───────────
  const isAddIntent = (
    /^(add|include|insert|append)\s+/i.test(userMsg) ||
    /\b(add|include|insert)\s+(a\s+)?(new\s+)?(item|service|product|tool|software|license)/i.test(userMsg) ||
    /\b(modify|update|change)\s+(this\s+)?(bom|list)\s+(by\s+)?(adding|including|inserting)/i.test(userMsg)
  )
  if (isAddIntent) {
    if (!currentBOM) return {
      type: 'text',
      text: 'Please create or load a BOM first, then I can add items.\n\nTry: **Create a Data Center BOM for Panasonic**',
    }
    const { desc, vendor, price } = parseAddItem(userMsg)
    if (!desc || desc.length < 2) return {
      type: 'text',
      text: 'I couldn\'t identify the item name. Try:\n- **Add CrowdStrike Falcon EDR at $345**\n- **Add 5x Cisco Switch from CDW at $7800**',
    }
    // qty from message e.g. "add 5x" or "add 5 units of"
    const qtyM = userMsg.match(/(?:^|\s)(\d+)\s*x\s+/i) || userMsg.match(/add\s+(\d+)\s+/i)
    const addQty = qtyM ? parseInt(qtyM[1]) : 1
    const newItem = {
      id: 'li_' + Date.now(),
      lineNo: currentBOM.lineItems.length + 1,
      category: detectCategory(desc) || detectCategory(userMsg) || 'General',
      description: desc,
      unit: '/unit', qty: addQty, unitPrice: price, extPrice: price * addQty,
      vendor, status: 'draft',
    }
    const newItems = [...currentBOM.lineItems, newItem]
    const newBOM = {
      ...currentBOM, lineItems: newItems,
      totalValue: newItems.reduce((s, i) => s + i.extPrice, 0),
      updatedAt: new Date().toISOString(),
    }
    const priceNote = price
      ? `unit price **${fmt(price)}**`
      : `price **TBD** — set it with: *Change item ${newItem.lineNo} price to $XXXX*`
    return {
      type: 'updated',
      text: `Added **Item ${newItem.lineNo}: ${desc}**\n- Qty: ${addQty} · Vendor: ${vendor} · ${priceNote}\n\nBOM now has **${newItems.length} items** — revised total: **${fmt(newBOM.totalValue)}**`,
      bom: newBOM,
    }
  }

  // Update price of item N
  const priceMatch = msg.match(/(?:change|update|set)\s+(?:item\s+)?(\d+)\s+(?:price|unit.?price)\s+(?:to|=)\s+\$?([\d,]+)/i)
  if (priceMatch && currentBOM) {
    const lineNo = parseInt(priceMatch[1])
    const newPrice = parseFloat(priceMatch[2].replace(/,/g, '')) || 0
    const item = currentBOM.lineItems.find(i => i.lineNo === lineNo)
    if (item) {
      const updated = { ...item, unitPrice: newPrice, extPrice: newPrice * item.qty }
      const newItems = currentBOM.lineItems.map(i => i.lineNo === lineNo ? updated : i)
      const newBOM = { ...currentBOM, lineItems: newItems, totalValue: newItems.reduce((s, i) => s + i.extPrice, 0), updatedAt: new Date().toISOString() }
      return { type: 'updated', text: 'Updated **Item ' + lineNo + '** (' + item.description + '): unit price set to **' + fmt(newPrice) + '**. Line total: **' + fmt(updated.extPrice) + '**\n\nRevised BOM total: **' + fmt(newBOM.totalValue) + '**', bom: newBOM }
    }
  }

  if (msg.match(/export|download|csv/)) {
    if (currentBOM) {
      exportBOMasCSV(currentBOM)
      return { type: 'text', text: 'Exported **"' + currentBOM.name + '"** as CSV with all ' + currentBOM.lineItems.length + ' line items (Line No, Description, Category, Unit, Qty, Unit Price, Ext Price, Vendor, Status).' }
    }
    return { type: 'text', text: 'Please load or create a BOM first, then I can export it.' }
  }

  if (msg.match(/analyz|insight|saving|cost|cheaper|break.?down|summary/)) {
    if (!currentBOM) return { type: 'text', text: 'Please create or load a BOM first, then I can analyze it.' }
    const cats = currentBOM.lineItems.reduce((a, i) => { a[i.category] = (a[i.category] || 0) + i.extPrice; return a }, {})
    const topCat = Object.entries(cats).sort((a, b) => b[1] - a[1])[0]
    const vendors = [...new Set(currentBOM.lineItems.map(i => i.vendor))]
    return {
      type: 'analysis',
      text: 'Analysis: **' + currentBOM.name + '**\n\nTotal: **' + fmt(currentBOM.totalValue) + '** | ' + currentBOM.lineItems.length + ' services | ' + vendors.length + ' vendors',
      breakdown: cats,
      insights: [
        'Highest spend: ' + (topCat?.[0] || '') + ' at ' + fmt(topCat?.[1] || 0) + ' (' + (((topCat?.[1] || 0) / currentBOM.totalValue) * 100).toFixed(0) + '% of total)',
        'Vendor concentration: ' + vendors.slice(0, 2).join(', ') + ' - consider alternate quotes for cost reduction',
        'Quick win: Request volume discount for quantities over 10 on recurring monthly services',
        currentBOM.lineItems.filter(i => i.status === 'draft').length + ' items still in draft status - review before sending to RFQ',
      ],
    }
  }

  const qtyMatch = msg.match(/(?:change|update|set)\s+(?:item\s+)?(\d+)\s+(?:qty|quantity)\s+(?:to|=)\s+(\d+)/i)
  if (qtyMatch && currentBOM) {
    const lineNo = parseInt(qtyMatch[1])
    const newQty = parseInt(qtyMatch[2])
    const item = currentBOM.lineItems.find(i => i.lineNo === lineNo)
    if (item) {
      const updated = { ...item, qty: newQty, extPrice: item.unitPrice * newQty }
      const newItems = currentBOM.lineItems.map(i => i.lineNo === lineNo ? updated : i)
      const newBOM = { ...currentBOM, lineItems: newItems, totalValue: newItems.reduce((s, i) => s + i.extPrice, 0), updatedAt: new Date().toISOString() }
      return { type: 'updated', text: 'Updated **Item ' + lineNo + '** (' + item.description + '): qty ' + item.qty + ' -> ' + newQty + '. Line total: **' + fmt(updated.extPrice) + '**\n\nRevised BOM total: **' + fmt(newBOM.totalValue) + '**', bom: newBOM }
    }
  }

  const vendorMatch = msg.match(/(?:change|update|set)\s+(?:item\s+)?(\d+)\s+vendor\s+(?:to)?\s+([\w\s]+)/i)
  if (vendorMatch && currentBOM) {
    const lineNo = parseInt(vendorMatch[1])
    const newVendor = vendorMatch[2].trim()
    const item = currentBOM.lineItems.find(i => i.lineNo === lineNo)
    if (item) {
      const newItems = currentBOM.lineItems.map(i => i.lineNo === lineNo ? { ...i, vendor: newVendor } : i)
      const newBOM = { ...currentBOM, lineItems: newItems, updatedAt: new Date().toISOString() }
      return { type: 'updated', text: 'Updated **Item ' + lineNo + '** (' + item.description + '): vendor ' + item.vendor + ' -> ' + newVendor, bom: newBOM }
    }
  }

  const removeMatch = msg.match(/(?:remove|delete|drop)\s+(?:item\s+)?(\d+)/i)
  if (removeMatch && currentBOM) {
    const lineNo = parseInt(removeMatch[1])
    const item = currentBOM.lineItems.find(i => i.lineNo === lineNo)
    if (item) {
      const newItems = currentBOM.lineItems.filter(i => i.lineNo !== lineNo).map((i, idx) => ({ ...i, lineNo: idx + 1 }))
      const newBOM = { ...currentBOM, lineItems: newItems, totalValue: newItems.reduce((s, i) => s + i.extPrice, 0), updatedAt: new Date().toISOString() }
      return { type: 'updated', text: 'Removed **Item ' + lineNo + '**: ' + item.description + '. BOM now has **' + newItems.length + ' items** totalling **' + fmt(newBOM.totalValue) + '**.', bom: newBOM }
    }
  }

  if (msg.match(/show|list|my bom|all bom|existing bom/)) {
    if (bomList.length === 0) return { type: 'text', text: 'No saved BOMs yet. Try: Create a SD-WAN BOM for Panasonic with 20 sites' }
    return { type: 'bom_list', text: 'Your **' + bomList.length + ' saved BOMs**:', boms: bomList.slice(0, 6) }
  }

  const loadMatch = bomList.find(b =>
    msg.includes(b.name.toLowerCase()) ||
    msg.includes(b.project.toLowerCase() + ' ' + b.category.toLowerCase().split('/')[0].trim())
  )
  if (loadMatch && msg.match(/load|open|edit|update|show me/)) {
    return {
      type: 'loaded',
      text: 'Loaded **"' + loadMatch.name + '"** (v' + loadMatch.version + ') - **' + loadMatch.lineItems.length + ' items**, ' + fmt(loadMatch.totalValue) + '.\n\nYou can now:\n- Change item 3 qty to 8\n- Remove item 6\n- Analyze this BOM\n- Export as CSV\n- Save',
      bom: loadMatch,
    }
  }

  if (msg.match(/create|build|new bom|generate|need|setup|make|prepare|start|begin|want|help.*bom|bom.*for|bom.*create|bom.*build|put together|draft|put.*together/) || cat || proj) {
    if (!proj && !ctx.project) {
      return { type: 'options', text: 'Which **project** is this BOM for?', field: 'project', options: PROJECTS.map(p => ({ label: p, action: 'project:' + p })) }
    }
    if (!cat && !ctx.category) {
      const project = proj || ctx.project
      return { type: 'options', text: 'Creating BOM for **' + project + '**. What type of services?', field: 'category', options: CATEGORIES.map(c => ({ label: c, action: 'category:' + c })) }
    }
    const project = proj || ctx.project || 'New Project'
    const category = cat || ctx.category || 'Data Center / COLO'
    const bom = buildBOM(project, category, qty)
    return {
      type: 'bom_created',
      text: 'Created BOM: **"' + bom.name + '"**\n\n**' + bom.lineItems.length + ' services** auto-populated from industry templates.\nEstimated total: **' + fmt(bom.totalValue) + '**\n\nThe BOM is live in the right panel.\n\nWhat you can do:\n- Change item 4 qty to 8\n- Remove item 7\n- Change item 2 vendor to CDW\n- Analyze this BOM\n- Save (to BOM Library)\n- Export as CSV',
      bom,
    }
  }

  return {
    type: 'help',
    text: 'I am your **AI BOM Assistant**. I can help you:\n\n- **Create** BOMs: Create a Data Center BOM for Panasonic with 8 racks\n- **Add items**: Add 5x Cisco Catalyst 9300 from CDW at $7800\n- **Update** items: Change item 3 qty to 15 | Change item 2 price to $4500 | Remove item 6\n- **Change vendor**: Change item 4 vendor to NTT Data\n- **Analyze**: Analyze cost savings on this BOM\n- **Load**: Load Panasonic SD-WAN BOM\n- **Show all**: Show my BOMs\n- **Export**: Export as CSV\n- **Save & send**: Save | Send to RFQ',
    suggestions: [
      'Create a Data Center BOM for Panasonic',
      'Add 10x Cisco Catalyst 9300 from CDW at $7800',
      'Create Cybersecurity BOM for Idemia',
      'Show my BOMs',
    ],
  }
}

// Convert backend BOM (snake_case line_items) to frontend BOM (camelCase lineItems)
function backendBOMtoFrontend(backendBOM, projectName) {
  if (!backendBOM || !backendBOM.line_items) return null
  const lineItems = backendBOM.line_items.map((item, i) => ({
    id: 'li_ai_' + Date.now() + '_' + i,
    lineNo: item.line_number || i + 1,
    category: item.category || 'General',
    description: item.description || '',
    unit: item.unit || '/unit',
    // backend template uses 'qty', BOM schema uses 'quantity' — handle both
    qty: item.qty || item.quantity || 1,
    unitPrice: item.unit_price || 0,
    // backend template uses 'ext_price', schema uses 'extended_price'
    extPrice: item.ext_price || item.extended_price || (item.unit_price || 0) * (item.qty || item.quantity || 1),
    vendor: item.vendor || '',
    status: item.eol_flag ? 'eol_flagged' : (item.status || 'draft'),
    sku: item.sku || '',
    term: item.term || item.unit || 'one-time',
    orderSeq: item.order_sequence || '',
    notes: item.notes || '',
  }))
  const totalValue = lineItems.reduce((s, i) => s + i.extPrice, 0)
  const cat = backendBOM.category || 'Data Center / COLO'
  const proj = backendBOM.project || projectName || 'New Project'
  return {
    id: 'bom_ai_' + Date.now(),
    name: backendBOM.name || (proj + ' — ' + cat + ' BOM'),
    project: proj,
    category: cat,
    status: 'draft', version: 1,
    createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
    createdBy: 'AI Agent',
    lineItems, totalValue,
    warnings: backendBOM.warnings || [],
    approvalsRequired: backendBOM.approvals_required || ['Buyer IT', 'Seller IT', 'SI Technical Team'],
    history: [{ version: 1, timestamp: new Date().toISOString(), action: 'Generated by AI Agent', changes: lineItems.length + ' line items', user: 'AI Assistant', totalValue }],
  }
}

// Export BOM as Excel via backend, fall back to CSV
async function exportBOMExcel(bom, dispatchFn) {
  try {
    const bomId = bom.id || 'chat_bom'
    const backendPayload = {
      name: bom.name, project: bom.project, category: bom.category,
      status: bom.status, version: bom.version, created_at: bom.createdAt,
      line_items: bom.lineItems.map(i => ({
        line_number: i.lineNo, category: i.category, description: i.description,
        sku: i.sku || '', qty: i.qty, unit: i.unit, unit_price: i.unitPrice,
        extended_price: i.extPrice, vendor: i.vendor, term: i.term || 'one-time',
        eol_flag: i.status === 'eol_flagged', order_sequence: i.orderSeq || '',
      })),
      totals: { total_otc: bom.totalValue, hardware: 0, software: 0, services: 0, tco_3year: 0 },
      warnings: bom.warnings || [],
    }
    const blob = await bomApi.exportChatBOMExcel(bomId, backendPayload)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = bom.name.replace(/[^a-zA-Z0-9 _-]/g, '') + '_BOM.xlsx'
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch {
    // Fallback to CSV
    exportBOMasCSV(bom)
  }
}

// ── BOM domain options shown in the picker modal ─────────────────────────
const BOM_DOMAINS = [
  { key: 'Data Center / COLO',    label: 'Data Center / COLO',    icon: '🏢', desc: 'DC builds, colocation, server infra' },
  { key: 'SD-WAN',                label: 'SD-WAN / WAN',          icon: '🌐', desc: 'SD-WAN edges, MPLS, branch networking' },
  { key: 'Cybersecurity',         label: 'Cybersecurity',         icon: '🔒', desc: 'EDR, SIEM, PAM, Zero Trust, WAF' },
  { key: 'End User Computing',    label: 'End User Computing',    icon: '💻', desc: 'Laptops, VDI, peripherals, EUC fleet' },
  { key: 'M365 & Power Platform', label: 'M365 & Power Platform', icon: '☁️', desc: 'Microsoft 365, Teams, SharePoint' },
  { key: 'Network Equipment',     label: 'Network Equipment',     icon: '🔌', desc: 'Switches, routers, firewalls, APs' },
  { key: 'Cloud Infrastructure',  label: 'Cloud Infrastructure',  icon: '⚡', desc: 'Azure, AWS, hybrid cloud landing zones' },
]

// Steps used to compute live progress % in the BOM Preview panel sidebar.
// Progress = (steps answered / total steps) * 100
const INTAKE_STEPS = [
  { key: 'ma_phase',              label: 'M&A Phase' },
  { key: 'workstream_category',   label: 'Category' },
  { key: 'conveyance_status',     label: 'Conveyance Status' },
  { key: 'site_count',            label: 'Sites in Scope' },
  { key: 'user_count',            label: 'Users per Site' },
  { key: 'required_by_date',      label: 'Required-By Date' },
  { key: 'vendor_standard',       label: 'Preferred Vendor' },
  { key: 'site_criticality',      label: 'Site Criticality' },
]

export default function ChatPage() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const bomList = useSelector(s => s.bom.bomList)
  const savedCurrentBOM = useSelector(s => s.bom.currentBOM)

  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [currentBOM, setLocalBOM] = useState(savedCurrentBOM || null)
  const [ctx, setCtx] = useState({ project: null, category: null })
  const msgEndRef = useRef(null)
  const backendWarnedRef = useRef(false)
  const sendingRef = useRef(false)
  const backendFailCount = useRef(0)   // consecutive backend failures; mode only disabled after 2+

  // Backend AI state
  const [sessionId, setSessionId]       = useState(null)
  const [backendMode, setBackendMode]   = useState(false)
  const [phaseProgress, setPhaseProgress] = useState(0)
  const [backendChecked, setBackendChecked] = useState(false)
  const [toast, setToast] = useState({ open: false, msg: '', severity: 'info' })

  // Domain picker + live intake progress tracking
  const [domainPickerOpen, setDomainPickerOpen] = useState(false)
  const [intakeFields, setIntakeFields] = useState({})   // collected step fields for sidebar progress
  const [confirmDeleteEntry, setConfirmDeleteEntry] = useState(null) // {type:'chat'|'bom', item}

  // Chat history (from backend — persisted in Cosmos + ADLS)
  const [chatHistory, setChatHistory] = useState([])

  // Derive current phase (1-10) from progress percentage
  const currentPhase = phaseProgress > 0 ? Math.max(1, Math.min(10, Math.ceil(phaseProgress / 10))) : 0
  const phaseName = PHASE_NAMES[currentPhase] || ''
  const phaseChips = PHASE_CHIPS[currentPhase] || []

  // Tombstone: session IDs the user has deleted — persisted in localStorage so
  // they don't reappear after backend re-fetch on reload
  const HIDDEN_KEY = 'chat_hidden_sessions'
  const loadHidden = () => { try { return new Set(JSON.parse(localStorage.getItem(HIDDEN_KEY) || '[]')) } catch { return new Set() } }
  const addHidden  = (id) => { const s = loadHidden(); s.add(id); localStorage.setItem(HIDDEN_KEY, JSON.stringify([...s])) }
  const clearHidden = () => localStorage.removeItem(HIDDEN_KEY)
  const filterSessions = (sessions) => {
    const hidden = loadHidden()
    return sessions.filter(s => !hidden.has(s.session_id) && (s.message_count || 0) > 0)
  }

  // On mount: check backend + load chat history + restore previous session
  useEffect(() => {
    chatApi.ping().then(online => {
      setBackendMode(online)
      setBackendChecked(true)
      if (online) {
        backendWarnedRef.current = false
        chatApi.getHistory('demo_user', 50)
          .then(sessions => setChatHistory(filterSessions(sessions)))
          .catch(() => {})
        // Restore session from localStorage so context persists across page refresh AND tab close
        const savedSid = localStorage.getItem('chat_session_id') || sessionStorage.getItem('chat_session_id')
        if (savedSid) {
          setSessionId(savedSid)
          localStorage.setItem('chat_session_id', savedSid)

          // 1. Immediately restore from localStorage cache (fast, survives backend restart)
          const cached = (() => {
            try {
              const raw = localStorage.getItem('chat_conv_' + savedSid)
              if (!raw) return null
              return JSON.parse(raw).map((m, i) => ({ id: 'c_' + i, ...m }))
            } catch (_) { return null }
          })()
          if (cached?.length) {
            setMessages(cached)
          }

          // 2. Then try backend for fresher data
          chatApi.getTranscript(savedSid, 'demo_user')
            .then(transcript => {
              // Backend returns { messages: [...] } — NOT conversation
              const conv = (transcript?.messages || []).filter(m => m.role !== 'assistant' || true)
              if (conv.length > 0) {
                const fromBackend = conv.map((m, i) => ({
                  id: 'restored_' + i,
                  role: m.role === 'assistant' ? 'ai' : m.role,
                  type: 'text',
                  text: m.content || '',
                }))
                // Only override local cache if backend has MORE messages
                const cacheLen = cached?.length || 0
                if (fromBackend.length > cacheLen) {
                  setMessages(fromBackend)
                }
              }
            })
            .catch(() => {
              // Backend can't find session (restarted/evicted) — keep localStorage cache, don't wipe the session ID
              if (!cached?.length) {
                localStorage.removeItem('chat_session_id')
                sessionStorage.removeItem('chat_session_id')
              }
            })
        }
      }
    })
  }, [])

  // Reload history whenever a session completes (new BOM created via backend)
  const refreshHistory = () => {
    if (backendMode) {
      chatApi.getHistory('demo_user', 50)
        .then(sessions => setChatHistory(filterSessions(sessions)))
        .catch(() => {})
    }
  }

  // ── Conversation + BOM-Session-Map localStorage cache ───────────────────
  // CONV_CACHE_PREFIX: conversation per sessionId (survives backend restarts)
  // BOM_SESSION_MAP_KEY: stable bomId→sessionId map (survives page refresh +
  //   backend restart so any BOM, including seed BOMs, restores its conversation)
  const CONV_CACHE_PREFIX = 'chat_conv_'
  const BOM_SESSION_MAP_KEY = 'bom_session_map'

  const saveBOMSession = (bomId, sid) => {
    if (!bomId || !sid) return
    try {
      const map = JSON.parse(localStorage.getItem(BOM_SESSION_MAP_KEY) || '{}')
      map[bomId] = sid
      localStorage.setItem(BOM_SESSION_MAP_KEY, JSON.stringify(map))
    } catch (_) {}
  }
  const lookupBOMSession = (bomId) => {
    if (!bomId) return null
    try { return JSON.parse(localStorage.getItem(BOM_SESSION_MAP_KEY) || '{}')[bomId] || null }
    catch (_) { return null }
  }
  const removeBOMSession = (bomId) => {
    if (!bomId) return
    try {
      const map = JSON.parse(localStorage.getItem(BOM_SESSION_MAP_KEY) || '{}')
      delete map[bomId]
      localStorage.setItem(BOM_SESSION_MAP_KEY, JSON.stringify(map))
    } catch (_) {}
  }

  const saveConvCache = (sid, msgs) => {
    if (!sid || !msgs?.length) return
    try {
      const payload = msgs.map(m => ({ role: m.role, type: m.type || 'text', text: m.text || '' }))
      localStorage.setItem(CONV_CACHE_PREFIX + sid, JSON.stringify(payload))
    } catch (_) {}
  }
  const loadConvCache = (sid) => {
    try {
      const raw = localStorage.getItem(CONV_CACHE_PREFIX + sid)
      if (!raw) return null
      return JSON.parse(raw).map((m, i) => ({ id: 'c_' + i, ...m }))
    } catch (_) { return null }
  }

  // Fully reset session state then load a historical chat transcript.
  // linkedBom: optional BOM from Redux to set immediately (used when restoring
  // a session via a BOM sidebar item that has creatingSessionId set).
  const switchToSession = (sessionItem, linkedBom = null) => {
    // --- reset all active-session state ---
    const restoredBom = linkedBom || null
    setLocalBOM(restoredBom)
    dispatch(setCurrentBOM(restoredBom))
    setCtx({ project: restoredBom?.project || null, category: restoredBom?.category || null })
    setPhaseProgress(sessionItem.progress || (restoredBom ? 100 : 0))
    setIntakeFields({})
    setIsTyping(false)
    sendingRef.current = false
    setInput('')

    const sid = sessionItem.session_id
    setSessionId(sid)
    localStorage.setItem('chat_session_id', sid)
    sessionStorage.setItem('chat_session_id', sid)

    setMessages([{ id: 'loading', role: 'ai', type: 'text', text: '_Loading conversation…_' }])

    chatApi.getTranscript(sid).then(data => {
      const fromBackend = (data.messages || []).map((m, i) => ({
        id: 'h_' + i,
        role: m.role === 'assistant' ? 'ai' : m.role,
        type: 'text',
        text: m.content || '',
      }))
      // Prefer the localStorage cache when it has MORE turns than the backend
      // returned. ADLS historically only held the welcome message; the stream
      // endpoint now re-archives after every turn, but the local cache (written
      // in onDone) is always the most complete source and must never be
      // overwritten by a shorter transcript.
      const cached      = loadConvCache(sid)
      const backendLen  = fromBackend.length
      const cacheLen    = cached?.length || 0
      const toShow      = cacheLen > backendLen ? cached : (fromBackend.length ? fromBackend : null)
      if (toShow?.length) {
        setMessages(toShow)
        // Only update the cache when the backend returned at least as many
        // messages — prevents a welcome-only ADLS response wiping a good cache.
        if (backendLen >= cacheLen && fromBackend.length) saveConvCache(sid, toShow)
      } else {
        setMessages([{ id: 'empty', role: 'ai', type: 'text', text: 'Session loaded — no messages found.' }])
      }
      if (data.bom) {
        setLocalBOM(data.bom)
        dispatch(setCurrentBOM(data.bom))
      }
    }).catch(() => {
      // Backend unreachable or session evicted — restore from localStorage cache
      const cached = loadConvCache(sid)
      if (cached?.length) {
        setMessages(cached)
        setToast({ open: true, msg: 'Restored from local cache (backend session expired)', severity: 'info' })
      } else {
        setMessages([{ id: 'err', role: 'ai', type: 'text', text: 'Could not load session transcript.' }])
        setToast({ open: true, msg: 'Could not load session transcript', severity: 'error' })
      }
    })
  }

  // Handle domain selection from the picker modal.
  // Pre-starts a backend session with domain_preselected=true so the skill
  // file is loaded from turn 1, and sets up the welcome message.
  const handleDomainSelect = async (category) => {
    setDomainPickerOpen(false)
    setLocalBOM(null)
    dispatch(setCurrentBOM(null))
    setCtx({ category, project: null })
    setSessionId(null)
    setPhaseProgress(0)
    setIntakeFields({})
    sessionStorage.removeItem('chat_session_id')

    const domainObj = BOM_DOMAINS.find(d => d.key === category) || { icon: '📋' }
    setMessages([{
      id: Date.now(), role: 'ai', type: 'text',
      text: `${domainObj.icon} **${category} BOM** selected.\n\nI've loaded the ${category} skill file and qualification checklist.\n\n**Step 1 — M&A Phase:** What phase is this engagement in?\n\n- **Day-1 Readiness** — minimum viable cutover to legally close\n- **TSA Exit / Cutover** — active migration off TSA-provided services\n- **Full Integration / Standalone Build** — post-TSA steady-state build-out`,
    }])

    if (backendMode) {
      try {
        const resp = await chatApi.startSession(category, 'New Project', 'demo_user', null, true)
        setSessionId(resp.session_id)
        localStorage.setItem('chat_session_id', resp.session_id)
        sessionStorage.setItem('chat_session_id', resp.session_id)
      } catch (_) {
        // Session will be created lazily on first message send
      }
    }
  }

  useEffect(() => {
    const welcome = savedCurrentBOM
      ? { id: 1, role: 'ai', type: 'loaded', text: 'Loaded **"' + savedCurrentBOM.name + '"** (v' + savedCurrentBOM.version + ') - **' + savedCurrentBOM.lineItems.length + ' items**, ' + fmt(savedCurrentBOM.totalValue) + '. What would you like to do?', bom: savedCurrentBOM }
      : { id: 1, role: 'ai', type: 'help', text: 'Hello! I am your **AI BOM Assistant**.\n\nI can create, update, analyze and manage your Bills of Materials in real-time. Just describe what you need in plain English.', suggestions: ['Create a Data Center BOM for Panasonic', 'Create SD-WAN BOM for 30 sites', 'Create Cybersecurity BOM for Idemia', 'Show my BOMs'] }
    setMessages([welcome])
    if (savedCurrentBOM) setLocalBOM(savedCurrentBOM)
  }, [])

  useEffect(() => { msgEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, isTyping])

  const addMsg = (msg) => setMessages(prev => [...prev, { id: Date.now() + Math.random(), ...msg }])

  const handleSend = useCallback(async (text) => {
    const userText = (text || input).trim()
    if (!userText) return
    if (sendingRef.current) return   // already processing — ignore duplicate trigger
    sendingRef.current = true
    setInput('')
    addMsg({ role: 'user', type: 'text', text: userText })
    setIsTyping(true)

    // ── Always handle BOM modification commands locally ────────────────────
    // The backend has no knowledge of the in-memory BOM; these commands are
    // handled by getAIResponse which operates on the currentBOM state directly.
    if (isLocalBOMCmd(userText, !!currentBOM)) {
      await new Promise(r => setTimeout(r, 350))
      setIsTyping(false)
      const resp = getAIResponse(userText, currentBOM, bomList, ctx)
      if (resp.bom) {
        setLocalBOM(resp.bom)
        dispatch(setCurrentBOM(resp.bom))
      }
      if (resp.type === 'saved' && resp.bom) {
        dispatch(saveBOM(resp.bom))
        dispatch(pushNotification({ type: 'bom_saved', title: 'BOM Saved', message: `${resp.bom.name} saved to BOM Library. Ready to send for approval.`, link: '/bom-library' }))
      }
      if (resp.type === 'bom_created' && resp.bom) {
        dispatch(pushNotification({ type: 'bom_created', title: 'BOM Created', message: `${resp.bom.name} — ${resp.bom.lineItems.length} items · ${fmt(resp.bom.totalValue)}`, link: '/bom-library' }))
      }
      addMsg({ role: 'ai', ...resp })
      sendingRef.current = false
      return
    }

    // ── Try backend AI for BOM creation / multi-phase questions ──────────
    if (backendMode) {
      try {
        let sid = sessionId
        // Start a session if we don't have one yet
        if (!sid) {
          const cat  = detectCategory(userText) || savedCurrentBOM?.category || 'Data Center / COLO'
          const proj = detectProject(userText) || savedCurrentBOM?.project || 'New Project'
          const startResp = await chatApi.startSession(cat, proj, 'demo_user', savedCurrentBOM || null)
          sid = startResp.session_id
          setSessionId(sid)
          localStorage.setItem('chat_session_id', sid)
          sessionStorage.setItem('chat_session_id', sid)  // persist for page-refresh resume
          // Link this new session to the currently loaded BOM (if any) so clicking
          // the BOM in the sidebar later will restore this conversation.
          if (currentBOM?.id) saveBOMSession(currentBOM.id, sid)
          // Store welcome — only show it if the next sendMessage doesn't produce a BOM
          // (avoids showing "Hello! I am your AI..." immediately before a BOM creation msg)
          var pendingWelcome = startResp.message
        }
        // ── Streaming call — no timeout, tokens arrive as they stream ──────
        const streamingMsgId = Date.now() + Math.random()
        addMsg({ role: 'ai', type: 'text', text: '', id: streamingMsgId, streaming: true })
        let streamedText = ''
        await chatApi.sendMessageStream(
          sid, userText, 'demo_user',
          (token) => {
            streamedText += token
            setMessages(prev => prev.map(m =>
              m.id === streamingMsgId ? { ...m, text: streamedText } : m
            ))
          },
          (finalEvt) => {
            setIsTyping(false)
            setPhaseProgress(finalEvt.progress || 0)

            // ── Parse intake fields from streamed text ────────────────────────
            if (finalEvt.agent_state && Object.keys(finalEvt.agent_state).length) {
              // Backend sends authoritative agent_state — use it directly
              setIntakeFields(prev => ({ ...prev, ...finalEvt.agent_state }))
            } else if (finalEvt.intake_fields) {
              setIntakeFields(prev => ({ ...prev, ...finalEvt.intake_fields }))
            } else {
              const updates = {}
              // Priority 1: parse the agent’s Markdown intake summary table
              // Rows look like: | M&A Phase | TSA Exit / Cutover |
              const tableRows = [...streamedText.matchAll(/\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|/g)]
              tableRows.forEach(([, field, value]) => {
                const f = field.toLowerCase()
                const v = value.trim()
                if (v && v !== 'Value' && v !== '---') {
                  if (/m.?a phase|^phase$/i.test(f))                          updates.ma_phase = v
                  if (/workstream|^category$|domain/i.test(f))                updates.workstream_category = v
                  if (/conveyance|conveying/i.test(f))                        updates.conveyance_status = v
                  if (/site.*scope|sites in scope|site count|number of site/i.test(f)) updates.site_count = v
                  if (/user.*site|user.*count|user per site/i.test(f))        updates.user_count = v
                  if (/required.by|timeline|cutover date/i.test(f))           updates.required_by_date = v
                  if (/preferred vendor|vendor standard/i.test(f))            updates.vendor_standard = v
                  if (/criticality|site.*critical|ha\s*pair/i.test(f))        updates.site_criticality = v
                }
              })
              // Priority 2: heuristic scan for when no table present
              const txt = streamedText.toLowerCase()
              if (!updates.ma_phase            && /tsa exit|day.?1|full integration|standalone/i.test(txt))         updates.ma_phase = true
              if (!updates.workstream_category  && /sd.?wan|data center|cybersecurity|end user|m365|network equipment/i.test(txt)) updates.workstream_category = true
              if (!updates.site_count           && /\d+\s*site|\d+\s*branch|\d+\s*location/i.test(txt))            updates.site_count = true
              if (!updates.vendor_standard      && /cisco|meraki|palo alto|fortinet|juniper/i.test(txt))            updates.vendor_standard = true
              if (!updates.required_by_date     && /december|january|february|march|q[1-4]\s*20\d\d/i.test(txt))   updates.required_by_date = true
              if (Object.keys(updates).length) setIntakeFields(prev => ({ ...prev, ...updates }))
            }

            // ── Auto-trigger BOM generation when skill invoked but no JSON returned ───
            // Detect: agent confirmed all fields and said “Invoking the … Skill File now”
            // but output prose only. Auto-send “generate” which matches CONFIRM regex
            // (≥4 user turns) → backend sets force_generation=True → LLM outputs JSON.
            const skillInvokedPhrase = /invoking.*skill file|all fields confirmed.*invoking|skill file.*now/i.test(streamedText)
            if (skillInvokedPhrase && !finalEvt.bom && !streamedText.includes('```json')) {
              setTimeout(() => { if (!sendingRef.current) handleSend('generate') }, 900)
            }

            let aiBOM = null
            // Use backend-extracted BOM, or fall back to parsing it from the streamed text
            let bomSource = finalEvt.bom
            if (!bomSource && streamedText) {
              // Try complete fence first
              const m = streamedText.match(/```json\s*([\s\S]*?)```/)
              if (m) { try { bomSource = JSON.parse(m[1].trim()) } catch (_) {} }
              // Try truncated fence (max_tokens hit mid-JSON) — recover last complete line_items
              if (!bomSource) {
                const mTrunc = streamedText.match(/```json\s*([\s\S]*)/)
                if (mTrunc) {
                  try {
                    const partial = mTrunc[1].trim()
                    const nameMatch = partial.match(/"name":\s*"([^"]+)"/)
                    const projMatch = partial.match(/"project":\s*"([^"]+)"/)
                    const catMatch  = partial.match(/"category":\s*"([^"]+)"/)
                    const itemsMatch = partial.match(/"line_items":\s*(\[[\s\S]*)/)
                    if (itemsMatch && nameMatch) {
                      let itemsStr = itemsMatch[1]
                      const lastObj = itemsStr.lastIndexOf('}')
                      if (lastObj > 0) itemsStr = itemsStr.slice(0, lastObj + 1) + ']'
                      const recovered = JSON.parse(
                        '{"name":' + JSON.stringify(nameMatch[1]) +
                        ',"project":' + JSON.stringify(projMatch?.[1] || '') +
                        ',"category":' + JSON.stringify(catMatch?.[1] || '') +
                        ',"line_items":' + itemsStr +
                        ',"totals":{"hardware":0,"software":0,"services":0,"total_otc":0,"tco_3year":0}' +
                        ',"warnings":["⚠️ BOM truncated — partial output recovered. Increase token limit for full BOM."]' +
                        ',"approvals_required":["Buyer IT","Seller IT","SI Technical Team"]}'
                      )
                      if (recovered.line_items?.length > 0) bomSource = recovered
                    }
                  } catch (_) {}
                }
              }
            }
            if (bomSource) {
              const proj = detectProject(userText) || 'New Project'
              aiBOM = backendBOMtoFrontend(bomSource, proj)
              // Tag the BOM with the session that generated it so clicking it
              // in the sidebar can restore the full conversation.
              if (aiBOM && sid) {
                aiBOM.creatingSessionId = sid
                saveBOMSession(aiBOM.id, sid)  // persist to localStorage (survives page refresh)
              }
              if (aiBOM) { setLocalBOM(aiBOM); dispatch(setCurrentBOM(aiBOM)) }
            }
            if ((finalEvt.complete || (aiBOM && aiBOM.lineItems?.length > 0)) && aiBOM) {
              // Always save to Redux immediately (works offline too)
              dispatch(saveBOM(aiBOM))
              // Persist to Cosmos via backend (best-effort)
              bomApi?.create?.(aiBOM)
                .then(() => setToast({ open: true, msg: 'BOM saved to library', severity: 'success' }))
                .catch(() => setToast({ open: true, msg: 'BOM created (saved locally — sync to backend failed)', severity: 'warning' }))
              const cats = [...new Set(aiBOM.lineItems.map(li => li.category))]
              const displayText = (
                `✅ Created **${aiBOM.name}**\n\n` +
                `**${aiBOM.lineItems.length} line items** | Total: **${fmt(aiBOM.totalValue)}**\n` +
                `Categories: ${cats.join(' · ')}\n\n` +
                `The BOM is live in the panel on the right. You can:\n` +
                `- Change item 2 qty to 8\n- Remove item 5\n- Analyze cost savings\n- Export as CSV\n- Save to BOM Library`
              )
              setMessages(prev => {
                const next = prev.map(m =>
                  m.id === streamingMsgId ? { ...m, text: displayText, type: 'bom_created', bom: aiBOM, actions: ['library', 'rfq'], streaming: false } : m
                )
                // Cache conversation so it survives backend restarts
                saveConvCache(sid, next)
                return next
              })
            } else {
              setMessages(prev => {
                const next = prev.map(m =>
                  m.id === streamingMsgId ? { ...m, streaming: false } : m
                )
                saveConvCache(sid, next)
                return next
              })
            }
          }
        )
        backendFailCount.current = 0   // reset failure counter on success
        sendingRef.current = false
        return
      } catch (err) {
        const errMsg = err?.message || ''
        // ── 404 = backend session expired (restart wiped in-memory Cosmos) ────
        // Clear the stale session ID so the NEXT message creates a fresh session
        // rather than permanently disabling backendMode.
        if (errMsg.includes('404') || errMsg.toLowerCase().includes('session not found')) {
          console.warn('Backend session expired — will create new session on next message')
          setSessionId(null)
          sessionStorage.removeItem('chat_session_id')
          // Remove the stale mapping so the BOM gets linked to the new session
          if (currentBOM?.id) {
            try {
              const map = JSON.parse(localStorage.getItem(BOM_SESSION_MAP_KEY) || '{}')
              delete map[currentBOM.id]
              localStorage.setItem(BOM_SESSION_MAP_KEY, JSON.stringify(map))
            } catch (_) {}
          }
          setToast({ open: true, msg: 'Session expired — reconnecting…', severity: 'info' })
          // Fall through to local mode for this message only (next will use new session)
        } else {
          // Backend call failed — fall through to local logic for THIS message only
          // Only permanently disable backendMode after 2 consecutive failures to avoid
          // a single transient error killing the entire AI session.
          console.warn('Backend AI error:', errMsg)
          backendFailCount.current += 1
          if (backendFailCount.current >= 2) {
            setBackendMode(false)
          }
          if (!backendWarnedRef.current) {
            backendWarnedRef.current = true
            setToast({ open: true, msg: backendFailCount.current >= 2 ? 'AI backend unavailable — using local mode' : 'AI request failed — retrying locally for this message', severity: 'warning' })
          }
        }
      }
    }

    // ── Local rule-based fallback ─────────────────────────────────────────
    setTimeout(() => {
      setIsTyping(false)
      const resp = getAIResponse(userText, currentBOM, bomList, ctx)
      if (resp.bom) { setLocalBOM(resp.bom); dispatch(setCurrentBOM(resp.bom)) }
      if (resp.type === 'saved' && resp.bom) {
        dispatch(saveBOM(resp.bom))
        dispatch(pushNotification({ type: 'bom_saved', title: 'BOM Saved', message: `${resp.bom.name} saved to BOM Library. Ready to send for approval.`, link: '/bom-library' }))
      }
      if (resp.type === 'bom_created' && resp.bom) {
        dispatch(pushNotification({ type: 'bom_created', title: 'BOM Created', message: `${resp.bom.name} — ${resp.bom.lineItems.length} items · ${fmt(resp.bom.totalValue)}`, link: '/bom-library' }))
      }
      // When creating a NEW BOM while one already exists → insert a session divider
      // and reset the backend session so the next creation gets a fresh context
      if (resp.type === 'bom_created' && currentBOM) {
        addMsg({ role: 'divider', type: 'divider', prevBOM: currentBOM.name })
        setSessionId(null)
        setIntakeFields({})
        sessionStorage.removeItem('chat_session_id')  // new BOM = fresh session
      }
      addMsg({ role: 'ai', ...resp })
      sendingRef.current = false
    }, 600 + Math.random() * 400)
  }, [input, backendMode, sessionId, currentBOM, bomList, ctx, dispatch])

  const handleOption = (action) => {
    if (action.startsWith('project:')) {
      const project = action.replace('project:', '')
      setCtx(c => ({ ...c, project }))
      handleSend(project + ' project')
    } else if (action.startsWith('category:')) {
      const category = action.replace('category:', '')
      setCtx(c => ({ ...c, category }))
      handleSend(category)
    }
  }

  const renderText = (text) => {
    if (!text) return null
    // Pre-process: strip complete and incomplete ```json``` fences (handles truncated AI output)
    const cleaned = text
      .replace(/```json[\s\S]*?```/g, '')        // complete json fences
      .replace(/```[\s\S]*?```/g, '')             // other complete fences
      .replace(/```json[\s\S]*/g, '\n*(BOM JSON captured — see preview panel on the right)*')  // truncated json fence
      .replace(/```[\s\S]*/g, '')                 // other truncated fences
      .trim()
    const lines = cleaned.split('\n')
    const elements = []
    let i = 0
    while (i < lines.length) {
      const line = lines[i]
      // Heading 1/2
      if (/^#{1,2}\s/.test(line)) {
        elements.push(
          <Typography key={i} sx={{ fontSize: '0.82rem', fontWeight: 700, color: 'inherit', mt: 0.5, lineHeight: 1.4 }}>
            {renderInline(line.replace(/^#+\s*/, ''))}
          </Typography>
        )
        i++; continue
      }
      // Horizontal rule
      if (/^[\-=]{3,}$/.test(line.trim())) {
        elements.push(<Box key={i} sx={{ borderTop: '1px solid rgba(0,0,0,0.12)', my: 0.5 }} />)
        i++; continue
      }
      // Bullet / numbered list
      if (/^[\-\*]\s/.test(line) || /^\d+\.\s/.test(line)) {
        const listItems = []
        while (i < lines.length && (/^[\-\*]\s/.test(lines[i]) || /^\d+\.\s/.test(lines[i]))) {
          listItems.push(lines[i].replace(/^[\-\*\d]+\.?\s*/, ''))
          i++
        }
        elements.push(
          <Box key={'list-' + i} component="ul" sx={{ pl: 2, my: 0.25, '& li': { fontSize: '0.78rem', lineHeight: 1.7, color: 'inherit' } }}>
            {listItems.map((li, j) => <li key={j}>{renderInline(li)}</li>)}
          </Box>
        )
        continue
      }
      // Empty line → small gap
      if (!line.trim()) {
        elements.push(<Box key={i} sx={{ height: 4 }} />)
        i++; continue
      }
      // Normal paragraph
      elements.push(
        <Typography key={i} sx={{ fontSize: '0.78rem', lineHeight: 1.6, color: 'inherit' }}>
          {renderInline(line)}
        </Typography>
      )
      i++
    }
    return elements
  }

  const renderInline = (text) => {
    // Split on **bold**, *italic*, `code`
    const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/)
    return parts.map((p, j) => {
      if (p.startsWith('**') && p.endsWith('**')) return <strong key={j}>{p.slice(2, -2)}</strong>
      if (p.startsWith('*') && p.endsWith('*')) return <em key={j}>{p.slice(1, -1)}</em>
      if (p.startsWith('`') && p.endsWith('`')) return (
        <Box key={j} component="code" sx={{ bgcolor: 'rgba(0,0,0,0.06)', px: 0.5, borderRadius: 0.5, fontFamily: 'monospace', fontSize: '0.74rem' }}>{p.slice(1, -1)}</Box>
      )
      return p
    })
  }

  const isAI = (m) => m.role === 'ai'

  return (
    <Box sx={{ display: 'flex', height: 'calc(100vh - 44px)', bgcolor: '#F9FAFB', overflow: 'hidden' }}>

      {/* Left: Sessions + History Sidebar */}
      <Box sx={{ width: 220, flexShrink: 0, bgcolor: 'white', borderRight: '1px solid #F3F4F6', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Box sx={{ p: 1.25, borderBottom: '1px solid #F3F4F6' }}>
          <Button fullWidth variant="contained" size="small" startIcon={<Add sx={{ fontSize: 14 }} />}
            onClick={() => setDomainPickerOpen(true)}
            sx={{ textTransform: 'none', fontSize: '0.72rem', fontWeight: 700, bgcolor: '#D04A02', '&:hover': { bgcolor: '#A33A00' } }}>
            + New BOM Chat
          </Button>
        </Box>

        {/* ── Unified History (chat sessions + saved BOMs merged, newest first) */}
        <Box sx={{ px: 1, pt: 1, pb: 0.25, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography sx={{ fontSize: '0.55rem', fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.7px' }}>
            History &amp; Saved BOMs
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.25, alignItems: 'center' }}>
            {backendMode && <Tooltip title="Synced with Azure ADLS + Cosmos DB"><CloudDone sx={{ fontSize: 11, color: '#10B981' }} /></Tooltip>}
            {(chatHistory.length > 0) && (
              <Tooltip title="Clear all chat history">
                <IconButton size="small" onClick={() => { clearHidden(); chatHistory.forEach(s => addHidden(s.session_id)); setChatHistory([]) }}
                  sx={{ p: 0.2, color: '#9CA3AF', '&:hover': { color: '#EF4444' } }}>
                  <DeleteOutline sx={{ fontSize: 12 }} />
                </IconButton>
              </Tooltip>
            )}
          </Box>
        </Box>
        <Box sx={{ flex: 1, overflowY: 'auto', px: 1, pb: 1 }}>
          {/* Merge chat sessions + saved BOMs into one time-sorted list */}
          {(() => {
            const chatItems = chatHistory.map(s => ({
              key: 'chat_' + s.session_id,
              type: 'chat',
              label: s.category || s.project || 'Chat Session',
              sub: s.message_count + ' msgs',
              date: s.updated_at || '',
              active: s.session_id === sessionId,
              raw: s,
            }))
            const bomItems = bomList.map(b => ({
              key: 'bom_' + b.id,
              type: 'bom',
              label: b.name,
              sub: b.status,
              date: b.updatedAt || b.createdAt || '',
              active: currentBOM?.id === b.id,
              raw: b,
            }))
            const all = [...chatItems, ...bomItems].sort((a, b) => (b.date > a.date ? 1 : -1))
            if (all.length === 0) return (
              <Typography sx={{ fontSize: '0.65rem', color: '#9CA3AF', textAlign: 'center', mt: 2 }}>
                No history yet. Start a chat to create your first BOM.
              </Typography>
            )
            return all.map(item => {
              const ST = { active: '#D1FAE5', draft: '#FEF3C7', review: '#DBEAFE', approved: '#F3E8FF' }
              const statusBg = item.type === 'bom' ? (ST[item.sub] || '#F3F4F6') : (item.active ? '#FDF3ED' : 'white')
              const dateStr = item.date ? new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''
              return (
                <Box key={item.key}
                  sx={{ position: 'relative', p: '6px 7px', mb: 0.4, borderRadius: '6px', cursor: 'pointer',
                    border: '1px solid ' + (item.active ? '#FBBF9F' : '#F3F4F6'),
                    bgcolor: item.active ? '#FDF3ED' : 'white',
                    '&:hover': { bgcolor: '#F9FAFB', '& .del-entry': { opacity: 1 } } }}
                  onClick={() => {
                    if (item.type === 'chat') {
                      switchToSession(item.raw)
                    } else {
                      const bom = item.raw
                      // Check both the in-memory tag (new BOMs this session) and the
                      // persistent localStorage map (survives page refresh + backend restart).
                      const linkedSid = bom.creatingSessionId || lookupBOMSession(bom.id)
                      if (linkedSid) {
                        switchToSession({ session_id: linkedSid, progress: 100 }, bom)
                      } else {
                        // No prior session for this BOM — show it and start fresh.
                        // A session will be created lazily on the first message send.
                        setLocalBOM(bom)
                        dispatch(setCurrentBOM(bom))
                        setSessionId(null)
                        sessionStorage.removeItem('chat_session_id')
                        setIntakeFields({})
                        setPhaseProgress(0)
                        setMessages([{
                          id: Date.now(), role: 'ai', type: 'loaded',
                          text: `Loaded **"${bom.name}"** (v${bom.version || 1}) — **${(bom.lineItems || []).length} items**, ${fmt(bom.totalValue || 0)}. What would you like to do?`,
                          bom,
                        }])
                      }
                    }
                  }}>
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.5 }}>
                    <Box sx={{ fontSize: '0.65rem', mt: '1px', opacity: 0.6, flexShrink: 0 }}>
                      {item.type === 'chat' ? '💬' : '📄'}
                    </Box>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography sx={{ fontSize: '0.67rem', fontWeight: 600, color: item.active ? '#D04A02' : '#1F2937', lineHeight: 1.2, pr: 1.5 }} noWrap>
                        {item.label}
                      </Typography>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.2 }}>
                        {item.type === 'bom'
                          ? <Chip label={item.sub} size="small" sx={{ fontSize: '0.5rem', height: 13, bgcolor: statusBg, color: '#374151' }} />
                          : <Typography sx={{ fontSize: '0.56rem', color: '#9CA3AF' }}>{item.sub}</Typography>}
                        <Typography sx={{ fontSize: '0.55rem', color: '#9CA3AF' }}>{dateStr}</Typography>
                      </Box>
                    </Box>
                  </Box>
                  <IconButton className="del-entry" size="small"
                    onClick={e => {
                      e.stopPropagation()
                      setConfirmDeleteEntry({ type: item.type, item })
                    }}
                    sx={{ opacity: 0, position: 'absolute', top: 3, right: 3, p: 0.15, color: '#EF4444',
                      transition: 'opacity 0.15s', '&:hover': { bgcolor: '#FEE2E2' } }}>
                    <DeleteOutline sx={{ fontSize: 11 }} />
                  </IconButton>
                </Box>
              )
            })
          })()}
        </Box>
      </Box>

      {/* Center: Chat */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        <Box sx={{ flexShrink: 0, bgcolor: 'white', borderBottom: '1px solid #F3F4F6' }}>
          <Box sx={{ height: 44, display: 'flex', alignItems: 'center', px: 2, gap: 1.5 }}>
            <AutoAwesome sx={{ fontSize: 18, color: '#D04A02' }} />
            <Box sx={{ flex: 1 }}>
              <Typography sx={{ fontWeight: 700, fontSize: '0.82rem', color: '#1F2937', lineHeight: 1 }}>AI BOM Assistant</Typography>
              <Typography sx={{ fontSize: '0.6rem', color: '#9CA3AF' }}>Create - Update - Analyze - Export</Typography>
            </Box>
            {backendChecked && (
              <Tooltip title={backendMode ? 'AI Backend connected — 10-phase BOM methodology active' : 'Backend offline — using local templates'}>
                <Chip
                  icon={backendMode ? <CloudDone sx={{ fontSize: '12px !important' }} /> : <CloudOff sx={{ fontSize: '12px !important' }} />}
                  label={backendMode ? 'AI Active' : 'Local Mode'}
                  size="small"
                  sx={{ fontSize: '0.58rem', height: 18, cursor: 'default',
                    bgcolor: backendMode ? '#D1FAE5' : '#FEF3C7',
                    color: backendMode ? '#065F46' : '#92400E',
                    '& .MuiChip-icon': { color: 'inherit' },
                  }}
                />
              </Tooltip>
            )}
          </Box>
          {backendMode && phaseProgress > 0 && (
            <Box sx={{ px: 2, pb: 0.75 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.25 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                  <Typography sx={{ fontSize: '0.58rem', fontWeight: 700, color: '#0369A1', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Phase {currentPhase}</Typography>
                  {phaseName && <Typography sx={{ fontSize: '0.58rem', color: '#6B7280' }}>— {phaseName}</Typography>}
                </Box>
                <Typography sx={{ fontSize: '0.58rem', color: '#0369A1' }}>{phaseProgress}%</Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={phaseProgress}
                sx={{ height: 3, borderRadius: 2, bgcolor: '#E0F2FE', '& .MuiLinearProgress-bar': { bgcolor: phaseProgress === 100 ? '#10B981' : '#0284C7', borderRadius: 2 } }}
              />
            </Box>
          )}
        </Box>

        <Box sx={{ flex: 1, overflowY: 'auto', p: 1.5, display: 'flex', flexDirection: 'column', gap: 1 }}>
          {messages.map(msg => {
            // ── Session divider between BOM conversations ──────────────────────
            if (msg.type === 'divider') return (
              <Box key={msg.id} sx={{ display: 'flex', alignItems: 'center', gap: 1, my: 0.75 }}>
                <Box sx={{ flex: 1, height: '1px', bgcolor: '#E5E7EB' }} />
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.2 }}>
                  <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', whiteSpace: 'nowrap' }}>
                    ↑ {msg.prevBOM || 'Previous BOM'} session
                  </Typography>
                  <Box sx={{ height: '1px', width: '100%', bgcolor: '#E5E7EB' }} />
                  <Typography sx={{ fontSize: '0.58rem', color: '#D04A02', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', whiteSpace: 'nowrap' }}>
                    ↓ New BOM session
                  </Typography>
                </Box>
                <Box sx={{ flex: 1, height: '1px', bgcolor: '#E5E7EB' }} />
              </Box>
            )
            return (
            <Box key={msg.id} sx={{ display: 'flex', justifyContent: isAI(msg) ? 'flex-start' : 'flex-end', alignItems: 'flex-start', gap: 0.75 }}>
              {isAI(msg) && (
                <Avatar sx={{ width: 26, height: 26, bgcolor: '#D04A02', flexShrink: 0 }}>
                  <AutoAwesome sx={{ fontSize: 13 }} />
                </Avatar>
              )}
              <Box sx={{ maxWidth: '80%' }}>
                <Box sx={{
                  bgcolor: isAI(msg) ? 'white' : '#D04A02',
                  color: isAI(msg) ? '#1F2937' : 'white',
                  border: isAI(msg) ? '1px solid #F3F4F6' : 'none',
                  borderRadius: isAI(msg) ? '4px 12px 12px 12px' : '12px 4px 12px 12px',
                  p: 1.25, boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                }}>
                  {renderText(msg.text)}

                  {msg.options && (
                    <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {msg.options.map(opt => (
                        <Chip key={opt.action} label={opt.label} size="small" onClick={() => handleOption(opt.action)}
                          sx={{ fontSize: '0.68rem', height: 22, cursor: 'pointer', bgcolor: '#FDF3ED', color: '#D04A02', fontWeight: 600, border: '1px solid #FBBF9F', '&:hover': { bgcolor: '#D04A02', color: 'white' } }} />
                      ))}
                    </Box>
                  )}

                  {msg.suggestions && (
                    <Box sx={{ mt: 1 }}>
                      <Typography sx={{ fontSize: '0.62rem', color: '#9CA3AF', mb: 0.5 }}>Try asking:</Typography>
                      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.4 }}>
                        {msg.suggestions.map(s => (
                          <Box key={s} onClick={() => !isTyping && !sendingRef.current && handleSend(s)}
                            sx={{ fontSize: '0.7rem', color: '#3B82F6', cursor: isTyping ? 'default' : 'pointer', p: '4px 8px', borderRadius: '4px', bgcolor: '#EFF6FF', opacity: isTyping ? 0.5 : 1, '&:hover': { bgcolor: isTyping ? '#EFF6FF' : '#DBEAFE' } }}>
                            {s}
                          </Box>
                        ))}
                      </Box>
                    </Box>
                  )}

                  {msg.boms && (
                    <Box sx={{ mt: 1 }}>
                      {msg.boms.map(b => (
                        <Box key={b.id} onClick={() => handleSend('Load ' + b.name)}
                          sx={{ display: 'flex', justifyContent: 'space-between', p: '4px 8px', borderRadius: 1, mb: 0.4, bgcolor: '#F9FAFB', cursor: 'pointer', '&:hover': { bgcolor: '#F3F4F6' } }}>
                          <Typography sx={{ fontSize: '0.68rem', fontWeight: 600 }}>{b.name}</Typography>
                          <Typography sx={{ fontSize: '0.65rem', color: '#D04A02', fontWeight: 700 }}>{fmt(b.totalValue)}</Typography>
                        </Box>
                      ))}
                    </Box>
                  )}

                  {msg.breakdown && (
                    <Box sx={{ mt: 1 }}>
                      {Object.entries(msg.breakdown).sort((a, b) => b[1] - a[1]).map(([cat, val]) => (
                        <Box key={cat} sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 0.4 }}>
                          <Typography sx={{ fontSize: '0.65rem', flex: 1 }} noWrap>{cat}</Typography>
                          <Box sx={{ width: 80, height: 5, bgcolor: '#F3F4F6', borderRadius: 1, overflow: 'hidden' }}>
                            <Box sx={{ width: ((val / (currentBOM?.totalValue || 1)) * 100) + '%', height: '100%', bgcolor: '#D04A02' }} />
                          </Box>
                          <Typography sx={{ fontSize: '0.65rem', fontWeight: 700, minWidth: 52, textAlign: 'right' }}>{fmt(val)}</Typography>
                        </Box>
                      ))}
                      {msg.insights && (
                        <Box sx={{ mt: 0.75, bgcolor: '#F9FAFB', borderRadius: 1, p: 1 }}>
                          {msg.insights.map((ins, i) => (
                            <Typography key={i} sx={{ fontSize: '0.68rem', lineHeight: 1.7, color: '#374151' }}>{ins}</Typography>
                          ))}
                        </Box>
                      )}
                    </Box>
                  )}

                  {msg.actions && (
                    <Box sx={{ mt: 1, display: 'flex', gap: 0.75 }}>
                      {msg.actions.includes('library') && (
                        <Button size="small" variant="outlined" startIcon={<FolderOpen sx={{ fontSize: 12 }} />}
                          onClick={() => navigate('/bom-library')}
                          sx={{ fontSize: '0.65rem', py: 0.3, textTransform: 'none', borderColor: '#D04A02', color: '#D04A02' }}>
                          View in Library
                        </Button>
                      )}
                      {msg.actions.includes('rfq') && (
                        <Button size="small" variant="contained" startIcon={<Build sx={{ fontSize: 12 }} />}
                          onClick={() => { if (currentBOM) dispatch(setActiveBOMForRFQ(currentBOM)); navigate('/rfq-builder') }}
                          sx={{ fontSize: '0.65rem', py: 0.3, textTransform: 'none', bgcolor: '#3B82F6', '&:hover': { bgcolor: '#1D4ED8' } }}>
                          Send to RFQ
                        </Button>
                      )}
                    </Box>
                  )}
                </Box>
              </Box>
              {!isAI(msg) && (
                <Avatar sx={{ width: 26, height: 26, bgcolor: '#374151', flexShrink: 0 }}>
                  <Person sx={{ fontSize: 13 }} />
                </Avatar>
              )}
            </Box>
          )})}

          {isTyping && (
            <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center' }}>
              <Avatar sx={{ width: 26, height: 26, bgcolor: '#D04A02' }}><AutoAwesome sx={{ fontSize: 13 }} /></Avatar>
              <Paper sx={{ px: 1.5, py: 1, border: '1px solid #F3F4F6' }}>
                <Box sx={{ display: 'flex', gap: 0.5 }}>
                  {[0, 1, 2].map(i => (
                    <Box key={i} sx={{ width: 5, height: 5, borderRadius: '50%', bgcolor: '#9CA3AF',
                      animation: 'bounce 1s ' + (i * 0.15) + 's infinite',
                      '@keyframes bounce': { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-4px)' } },
                    }} />
                  ))}
                </Box>
              </Paper>
            </Box>
          )}
          <div ref={msgEndRef} />
        </Box>

        <Box sx={{ p: 1.5, bgcolor: 'white', borderTop: '1px solid #F3F4F6' }}>
          {/* Phase-specific quick chips */}
          {phaseChips.length > 0 && (
            <Box sx={{ mb: 1, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
              {phaseChips.map(chip => (
                <Chip key={chip} label={chip} size="small" disabled={isTyping} onClick={() => !isTyping && handleSend(chip)}
                  sx={{ fontSize: '0.65rem', height: 20, cursor: 'pointer', bgcolor: '#F0F9FF', color: '#0369A1',
                    border: '1px solid #BAE6FD', '&:hover': { bgcolor: '#0369A1', color: 'white' } }} />
              ))}
            </Box>
          )}
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
            <TextField
              multiline maxRows={4} fullWidth
              placeholder="Ask me to create, update, or analyze a BOM..."
              value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !sendingRef.current) { e.preventDefault(); handleSend() } }}
              sx={{ bgcolor: '#F9FAFB', '& .MuiInputBase-input': { fontSize: '0.8rem', py: '8px' }, '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#E5E7EB' }, '&:hover fieldset': { borderColor: '#D04A02' }, '&.Mui-focused fieldset': { borderColor: '#D04A02' } } }}
            />
            <IconButton onClick={() => handleSend()} disabled={!input.trim() || isTyping}
              sx={{ width: 40, height: 40, bgcolor: '#D04A02', color: 'white', borderRadius: '8px', flexShrink: 0, '&:hover': { bgcolor: '#A33A00' }, '&.Mui-disabled': { bgcolor: '#F3F4F6', color: '#9CA3AF' } }}>
              <Send sx={{ fontSize: 18 }} />
            </IconButton>
          </Box>
          <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF', mt: 0.5, textAlign: 'center' }}>
            Press Enter to send | Shift+Enter for new line
          </Typography>
        </Box>
      </Box>

      {/* Right: Live BOM Preview */}
      <Box sx={{ width: 300, flexShrink: 0, bgcolor: 'white', borderLeft: '1px solid #F3F4F6', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Box sx={{ p: 1.25, borderBottom: '1px solid #F3F4F6', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography sx={{ fontWeight: 700, fontSize: '0.75rem', color: '#1F2937' }}>
            {currentBOM ? 'Live BOM Preview' : 'BOM Preview'}
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
            {currentBOM && <>
              <Tooltip title="Save BOM"><IconButton size="small" onClick={() => handleSend('save')} sx={{ color: '#10B981' }}><Save sx={{ fontSize: 15 }} /></IconButton></Tooltip>
              <Tooltip title="Send to RFQ"><IconButton size="small" onClick={() => { dispatch(setActiveBOMForRFQ(currentBOM)); navigate('/rfq-builder') }} sx={{ color: '#3B82F6' }}><Build sx={{ fontSize: 15 }} /></IconButton></Tooltip>
              <Tooltip title="Export as Excel"><IconButton size="small" onClick={() => exportBOMExcel(currentBOM, dispatch)} sx={{ color: '#6B7280' }}><Download sx={{ fontSize: 15 }} /></IconButton></Tooltip>
            </>}
            {!currentBOM && phaseProgress >= 85 && (
              <Tooltip title="Intake complete — click to generate BOM JSON">
                <IconButton size="small" onClick={() => { if (!sendingRef.current) handleSend('generate') }}
                  sx={{ color: '#D04A02',
                    animation: 'bomPulse 1.6s ease-in-out infinite',
                    '@keyframes bomPulse': { '0%,100%': { opacity: 1, transform: 'scale(1)' }, '50%': { opacity: 0.55, transform: 'scale(0.88)' } } }}>
                  <AutoAwesome sx={{ fontSize: 15 }} />
                </IconButton>
              </Tooltip>
            )}
          </Box>
        </Box>

        {!currentBOM ? (
          (() => {
            const answeredCount = INTAKE_STEPS.filter(s => intakeFields[s.key]).length
            const pct = Math.round((answeredCount / INTAKE_STEPS.length) * 100)
            const hasProgress = answeredCount > 0 || phaseProgress > 0
            const displayPct = phaseProgress > 0 ? phaseProgress : pct
            return hasProgress ? (
              // ── Intake progress tracker (shown while gathering fields, before BOM generated)
              <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', p: 1.5, overflow: 'hidden' }}>
                <Box sx={{ mb: 1.5 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                    <Typography sx={{ fontSize: '0.68rem', fontWeight: 700, color: '#1F2937' }}>Intake Progress</Typography>
                    <Typography sx={{ fontSize: '0.68rem', fontWeight: 700, color: '#D04A02' }}>{displayPct}%</Typography>
                  </Box>
                  <LinearProgress variant="determinate" value={displayPct}
                    sx={{ height: 6, borderRadius: 3, bgcolor: '#FEF3C7',
                      '& .MuiLinearProgress-bar': { bgcolor: displayPct === 100 ? '#10B981' : '#D04A02', borderRadius: 3 } }} />
                  <Typography sx={{ fontSize: '0.6rem', color: '#9CA3AF', mt: 0.5 }}>
                    {answeredCount}/{INTAKE_STEPS.length} qualification fields collected
                  </Typography>
                </Box>
                <Box sx={{ flex: 1, overflowY: 'auto' }}>
                  {INTAKE_STEPS.map(step => {
                    const done = !!intakeFields[step.key]
                    return (
                      <Box key={step.key} sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.6,
                        borderBottom: '1px solid #F9FAFB' }}>
                        <Box sx={{ width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
                          bgcolor: done ? '#D1FAE5' : '#F3F4F6',
                          display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <Typography sx={{ fontSize: '0.6rem', color: done ? '#10B981' : '#9CA3AF', fontWeight: 700, lineHeight: 1 }}>
                            {done ? '✓' : '·'}
                          </Typography>
                        </Box>
                        <Typography sx={{ fontSize: '0.68rem', color: done ? '#065F46' : '#6B7280',
                          fontWeight: done ? 600 : 400, lineHeight: 1.3 }}>
                          {step.label}
                        </Typography>
                      </Box>
                    )
                  })}
                </Box>
                <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                  {phaseProgress >= 85 && (
                    <Button fullWidth size="small" variant="contained"
                      onClick={() => { if (!sendingRef.current) handleSend('generate') }}
                      disabled={isTyping}
                      sx={{ textTransform: 'none', fontSize: '0.68rem', fontWeight: 700,
                        bgcolor: '#D04A02', '&:hover': { bgcolor: '#A33A00' }, py: 0.6,
                        borderRadius: '8px' }}>
                      ⚡ Generate BOM Now
                    </Button>
                  )}
                  <Box sx={{ p: 1, bgcolor: '#FDF3ED', borderRadius: '8px', border: '1px dashed #FBBF9F' }}>
                    <Typography sx={{ fontSize: '0.62rem', color: '#92400E', textAlign: 'center', lineHeight: 1.5 }}>
                      {phaseProgress >= 85
                        ? 'Intake complete — type “confirmed” or click Generate'
                        : 'BOM will appear here once all qualification questions are answered'}
                    </Typography>
                  </Box>
                </Box>
              </Box>
            ) : (
              // ── Empty state (no session active)
              <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', p: 2, textAlign: 'center' }}>
                <AutoAwesome sx={{ fontSize: 32, color: '#E5E7EB', mb: 1 }} />
                <Typography sx={{ fontSize: '0.75rem', color: '#9CA3AF', lineHeight: 1.5 }}>
                  Your BOM will appear here as you build it in the chat
                </Typography>
                <Typography sx={{ fontSize: '0.65rem', color: '#C4C9D0', mt: 0.5 }}>
                  Try: Create a Data Center BOM for Panasonic
                </Typography>
              </Box>
            )
          })()
        ) : (
          <>
            <Box sx={{ px: 1.5, pt: 1.25, pb: 0.75, borderBottom: '1px solid #F9FAFB' }}>
              <Typography sx={{ fontWeight: 700, fontSize: '0.78rem', color: '#1F2937', lineHeight: 1.2 }}>{currentBOM.name}</Typography>
              <Box sx={{ display: 'flex', gap: 0.75, mt: 0.5, flexWrap: 'wrap' }}>
                <Chip label={currentBOM.status} size="small" sx={{ fontSize: '0.58rem', height: 16, bgcolor: currentBOM.status === 'active' ? '#D1FAE5' : '#FEF3C7', color: currentBOM.status === 'active' ? '#065F46' : '#92400E' }} />
                <Chip label={'v' + currentBOM.version} size="small" sx={{ fontSize: '0.58rem', height: 16, bgcolor: '#F3F4F6', color: '#374151' }} />
                <Chip label={currentBOM.lineItems.length + ' items'} size="small" sx={{ fontSize: '0.58rem', height: 16, bgcolor: '#DBEAFE', color: '#1E40AF' }} />
              </Box>
            </Box>

            <Box sx={{ flex: 1, overflowY: 'auto', px: 1.25, py: 0.75 }}>
              {currentBOM.lineItems.map(item => (
                <Box key={item.id} sx={{ display: 'flex', gap: 0.75, py: 0.6, borderBottom: '1px solid #F9FAFB', alignItems: 'flex-start' }}>
                  <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF', fontWeight: 700, minWidth: 14, pt: 0.2 }}>{item.lineNo}</Typography>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography sx={{ fontSize: '0.68rem', fontWeight: 500, lineHeight: 1.25, color: '#1F2937' }} noWrap>{item.description}</Typography>
                    <Typography sx={{ fontSize: '0.58rem', color: '#9CA3AF' }}>{item.vendor} - qty {item.qty} - {item.unit}</Typography>
                  </Box>
                  <Typography sx={{ fontSize: '0.68rem', fontWeight: 700, color: '#374151', flexShrink: 0 }}>
                    {fmt(item.extPrice)}
                  </Typography>
                </Box>
              ))}
            </Box>

            <Box sx={{ p: 1.25, borderTop: '1px solid #F3F4F6', bgcolor: '#FAFAFA' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, color: '#1F2937' }}>Total Value</Typography>
                <Typography sx={{ fontSize: '0.85rem', fontWeight: 700, fontFamily: '"Playfair Display", serif', color: '#D04A02' }}>
                  {fmt(currentBOM.totalValue)}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', gap: 0.75, mb: 0.75 }}>
                <Button fullWidth size="small" variant="contained" onClick={() => handleSend('save')}
                  sx={{ textTransform: 'none', fontSize: '0.68rem', fontWeight: 700, bgcolor: '#D04A02', '&:hover': { bgcolor: '#A33A00' }, py: 0.5 }}>
                  Save BOM
                </Button>
                <Button fullWidth size="small" variant="outlined" onClick={() => { dispatch(setActiveBOMForRFQ(currentBOM)); navigate('/rfq-builder') }}
                  sx={{ textTransform: 'none', fontSize: '0.68rem', fontWeight: 700, borderColor: '#3B82F6', color: '#3B82F6', py: 0.5 }}>
                  RFQ
                </Button>
              </Box>
              <Button fullWidth size="small" variant="outlined"
                startIcon={<Download sx={{ fontSize: 13 }} />}
                onClick={() => exportBOMExcel(currentBOM, dispatch)}
                sx={{ textTransform: 'none', fontSize: '0.68rem', fontWeight: 600, borderColor: '#E5E7EB', color: '#6B7280', py: 0.4 }}>
                Export Excel ({currentBOM.lineItems.length} items)
              </Button>
              <Button fullWidth size="small" variant="outlined"
                startIcon={<RateReview sx={{ fontSize: 13 }} />}
                onClick={() => {
                  if (currentBOM) {
                    dispatch(saveBOM({ ...currentBOM, status: currentBOM.status === 'draft' ? 'review' : currentBOM.status }))
                    navigate(`/bom-review/${currentBOM.id}`)
                  }
                }}
                sx={{ mt: 0.5, textTransform: 'none', fontSize: '0.68rem', fontWeight: 600, borderColor: '#8B5CF6', color: '#8B5CF6', py: 0.4 }}>
                Send to Review
              </Button>
            </Box>
          </>
        )}
      </Box>

      {/* ── Delete Confirmation Dialog ────────────────────────────────── */}
      <Dialog open={!!confirmDeleteEntry} onClose={() => setConfirmDeleteEntry(null)} maxWidth="xs" fullWidth
        PaperProps={{ sx: { borderRadius: '12px' } }}>
        <DialogTitle sx={{ pb: 0.5, display: 'flex', alignItems: 'center', gap: 1 }}>
          <DeleteOutline sx={{ color: '#EF4444', fontSize: 20 }} />
          <Typography sx={{ fontWeight: 700, fontSize: '0.95rem' }}>
            {confirmDeleteEntry?.type === 'chat' ? 'Delete Chat Session' : 'Delete BOM'}
          </Typography>
        </DialogTitle>
        <DialogContent sx={{ pt: 1 }}>
          <Typography sx={{ fontSize: '0.82rem', color: '#374151' }}>
            {confirmDeleteEntry?.type === 'chat'
              ? <>Remove <strong>{confirmDeleteEntry.item.label}</strong> from chat history?</>
              : <>Permanently delete <strong>{confirmDeleteEntry?.item.label}</strong>? This will also remove it from the BOM Library.</>
            }
          </Typography>
          <Typography sx={{ fontSize: '0.74rem', color: '#6B7280', mt: 0.75 }}>
            This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 2, pb: 1.5 }}>
          <Button size="small" onClick={() => setConfirmDeleteEntry(null)}
            sx={{ textTransform: 'none', fontSize: '0.72rem' }}>Cancel</Button>
          <Button size="small" variant="contained"
            onClick={() => {
              const { type, item } = confirmDeleteEntry
              if (type === 'chat') {
                addHidden(item.raw.session_id)
                setChatHistory(prev => prev.filter(s => s.session_id !== item.raw.session_id))
              } else {
                dispatch(deleteBOM(item.raw.id))
                bomApi.delete?.(item.raw.id)  // best-effort backend delete
              }
              setConfirmDeleteEntry(null)
            }}
            sx={{ bgcolor: '#EF4444', '&:hover': { bgcolor: '#DC2626' }, textTransform: 'none', fontSize: '0.72rem' }}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Domain Picker Dialog ─────────────────────────────────────── */}
      <Dialog open={domainPickerOpen} onClose={() => setDomainPickerOpen(false)}
        maxWidth="sm" fullWidth
        PaperProps={{ sx: { borderRadius: '14px', p: 0.5 } }}>
        <DialogTitle sx={{ pb: 0.5, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <Box>
            <Typography sx={{ fontSize: '0.9rem', fontWeight: 700, color: '#1F2937', lineHeight: 1.2 }}>
              Select BOM Domain
            </Typography>
            <Typography sx={{ fontSize: '0.68rem', color: '#6B7280', fontWeight: 400, mt: 0.25, lineHeight: 1.4 }}>
              Choose a category — the matching skill file will be loaded and domain-specific questions asked.
            </Typography>
          </Box>
          <IconButton size="small" onClick={() => setDomainPickerOpen(false)}
            sx={{ color: '#9CA3AF', mt: -0.5, mr: -0.5 }}>
            <Close sx={{ fontSize: 16 }} />
          </IconButton>
        </DialogTitle>
        <DialogContent sx={{ pt: 1, pb: 2 }}>
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
            {BOM_DOMAINS.map(domain => (
              <Box key={domain.key}
                onClick={() => handleDomainSelect(domain.key)}
                sx={{
                  p: 1.5, borderRadius: '10px',
                  border: '1.5px solid #E5E7EB', cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  '&:hover': {
                    borderColor: '#D04A02', bgcolor: '#FDF3ED',
                    transform: 'translateY(-2px)',
                    boxShadow: '0 4px 12px rgba(208,74,2,0.14)',
                  },
                }}>
                <Box sx={{ fontSize: '1.5rem', mb: 0.75, lineHeight: 1 }}>{domain.icon}</Box>
                <Typography sx={{ fontSize: '0.73rem', fontWeight: 700, color: '#1F2937', lineHeight: 1.25 }}>
                  {domain.label}
                </Typography>
                <Typography sx={{ fontSize: '0.62rem', color: '#6B7280', mt: 0.3, lineHeight: 1.4 }}>
                  {domain.desc}
                </Typography>
              </Box>
            ))}
          </Box>
        </DialogContent>
      </Dialog>

      {/* Toast notifications */}
      <Snackbar open={toast.open} autoHideDuration={4000}
        onClose={() => setToast(t => ({ ...t, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        <Alert severity={toast.severity} onClose={() => setToast(t => ({ ...t, open: false }))} sx={{ fontSize: '0.8rem' }}>
          {toast.msg}
        </Alert>
      </Snackbar>
    </Box>
  )
}
