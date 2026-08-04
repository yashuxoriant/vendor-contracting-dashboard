# MASTER PLAN — IT BOM Contracting Agent
## Full-Stack AI-Powered BOM Creation System
### As of: June 30, 2026 | Built on: Avijeet's Codebase

---

## SECTION 1 — CODEBASE REALITY CHECK (What Actually Exists)

### What Is Built and Working ✅

| Module | File(s) | Status | Notes |
|---|---|---|---|
| Frontend Shell | `frontend/src/App.jsx` | ✅ Working | React + MUI + Redux, 6 routes |
| Overview / Analytics Dashboard | `OverviewPage.jsx` | ✅ Working | Hardcoded data, charts, KPI cards |
| BOM Library | `BOMLibraryPage.jsx` | ✅ Working | CRUD, inline edit, compare, CSV export |
| Chat / BOM Creation | `ChatPage.jsx` | ✅ Working (shallow) | Template-based keyword matching only |
| Vendor Price Selector | `VendorPriceSelectorPage.jsx` | ✅ Working | Hardcoded catalog, add-to-BOM |
| RFQ Builder | `RFQBuilderPage.jsx` | ✅ Working | Cart-based, CSV export |
| Quote Extractor | `QuoteExtractorPage.jsx` | ✅ Exists | File upload UI |
| FastAPI Backend | `backend/main.py` | ✅ Runs | CORS, GZip, error handlers, timing |
| Backend Chat API | `backend/api/chat.py` | ⚠️ Stub | Starts sessions, TODO: real AI call |
| Backend BOM API | `backend/api/bom.py` | ⚠️ Stub | CRUD over mock Cosmos DB |
| Backend Analytics API | `backend/api/analytics.py` | ⚠️ Stub | Returns hardcoded dummy data |
| Mock Cosmos DB | `backend/db/mock_cosmos_client.py` | ✅ Works | In-memory, seeds sample data |
| Real Cosmos DB Client | `backend/db/cosmos_client.py` | ⚠️ Wired | Needs real Azure credentials |
| DB Schemas | `backend/db/schemas.py` | ✅ Complete | Full Pydantic models: BOM, LineItem, ChatSession |
| Config / Settings | `backend/config.py` | ✅ Complete | All env vars, feature flags, dummy defaults |
| SharePoint Connector | `extractor/sharepoint_connector.py` | ⚠️ Built | Microsoft Graph API auth written, NOT connected to Xoriant |
| Quote Extractor Pipeline | `extractor/` (8 files) | ✅ Built | Hybrid: heuristic → LLM validate → categorize → enrich |
| AI Extractor | `extractor/ai_extractor.py` | ✅ Built | OpenAI/Groq JSON extraction from uploaded documents |
| AI Validator | `extractor/ai_validator.py` | ⚠️ Built | Needs EOL/EOS data source |
| LLM Router | `extractor/llm_router.py` | ✅ Built | Groq → Llama → OpenAI failover |

### What Is NOT Built ❌

| Feature | Priority | Complexity |
|---|---|---|
| 10-Phase guided BOM wizard (hybrid chat) | 🔴 P0 | High |
| 3-party approval workflow (Buyer/Seller/Technical) | 🔴 P0 | Medium |
| Audit logging (every action, change, approval) | 🔴 P0 | Medium |
| EOL/EOS hardware validation with live market data | 🔴 P0 | High |
| SharePoint connected to Xoriant drive (golden BOMs) | 🔴 P0 | Medium |
| Real Azure OpenAI wired into chat flow | 🔴 P0 | Medium |
| Excel export (proper .xlsx, not CSV) | 🔴 P0 | Low |
| Data Center BOM category (10-phase scoping) | 🔴 P0 | High |
| Authentication / User identity (20 PwC users) | 🟡 P1 | Medium |
| KPI dashboard: BOM cycle time tracking | 🟡 P1 | Medium |
| Email notification on BOM status change | 🟡 P1 | Low |
| Golden BOM reference retrieval (RAG pattern) | 🟡 P1 | High |
| Vendor quote comparison (multi-vendor same SKU) | 🟡 P1 | Medium |
| BOM version history with diff view | 🟡 P1 | Medium |

---

## SECTION 2 — DOMAIN KNOWLEDGE (The Brain of the Agent)

### 2.1 What Is a BOM in This Context?

A Bill of Materials (BOM) in IT contracting is a structured line-item document that specifies:
- **What** to buy (SKU, make/model, description)
- **How much** to buy (quantity)
- **From whom** (vendor: CDW, Entity, etc.)
- **At what price** (unit price, extended price)
- **For how long** (term: 1yr, 3yr, one-time)
- **Who approved it** (3-party sign-off)

The BOM is the foundation of the RFQ → Quote → PO → Procurement chain.

---

### 2.2 The 10-Phase BOM Methodology (Client-Confirmed)

This is the expert knowledge the AI agent must internalize and guide users through:

#### Phase 1: Scope & Constraints
- What lands in DC vs. stays cloud/SaaS/co-lo?
- Any specialized hardware (AS400, bare metal, GPU)?
- Physical site: existing server room, co-lo, or greenfield?
- Power and cooling specs (gates everything)
- Day 1 cutover date (drives all lead times backward)

#### Phase 2: Seller Inventory
- Application-to-server mapping from Seller
- Conveyed vs. non-conveyed servers
- Age, spec, warranty of conveyed hardware
- EOL OS or hardware flagged for modernization (NOT migrated as-is)
- Current rack layout and power draw per rack

#### Phase 3: Compute Sizing
- Per-app: CPU cores, RAM, storage IOPS, network bandwidth, HA requirements
- Consolidation ratio: typically 8:1 to 15:1 (VMware/Hyper-V)
- Minimum 3 nodes for HA cluster
- 20–30% headroom added

#### Phase 4: Storage Sizing
- Tier 1 (SSD/NVMe): databases, ERP, latency-sensitive
- Tier 2 (SAS/SATA): file shares, archives, backup targets
- RAID overhead: +20–25%
- Backup/snapshot: 2–3× primary storage
- Architecture choice: SAN / NAS / HCI / DAS
- Storage network: FC vs iSCSI vs NVMe-oF

#### Phase 5: Network Sizing
- Core/distribution/access layer architecture
- ToR (Top-of-Rack) switch count = rack count
- Uplink sizing: 10G / 25G / 100G
- WAN/DC uplink: MPLS, DIA circuits
- East-west microsegmentation requirements
- OOB (out-of-band) management network
- Firewall: throughput, CPS, VPN capacity
- Load balancer: externally facing apps

#### Phase 6: Power & Physical
- Total power draw calculation
- PUE factor: 1.4–1.6 typical on-prem
- UPS: N+1 configuration
- PDUs per rack
- Rack count and layout (raised floor vs overhead cabling)
- CRAC/CRAH cooling sizing
- Generator requirements

#### Phase 7: Build the BOM
Structure by these categories:
1. **Compute** — server make/model, CPU, RAM, NIC, qty
2. **Storage** — array, capacity, tier, controllers, qty
3. **Networking** — ToR switches, core, OOB, firewalls, LBs
4. **Cabling** — fiber, copper, patch panels, cable management
5. **Physical** — racks, PDUs, KVM, rails
6. **Power** — UPS, PDUs, strips
7. **Software Licenses** — hypervisor, storage OS, network OS, mgmt
8. **Maintenance Contracts** — 3–5 year hardware support on everything
9. **Spares** — 10% of critical components (drives, NICs, PSUs)

#### Phase 8: Approvals (3-Party Rule — HARD REQUIREMENT)
- ✅ Seller IT team reviewed and approved
- ✅ Buyer IT team reviewed and approved
- ✅ SI (System Integrator / JBR or internal) reviewed and approved
- All 3 must be YES before BOM is considered final

#### Phase 9: Validate & Pressure-Test
- SI/hardware vendor review before ordering
- Application owners review (they catch missed requirements)
- Lead times: networking + servers = 8–20 weeks in constrained markets
- Dual vendor quotes (Dell/HPE/Lenovo for compute; Cisco/Aruba/Juniper for networking)
- Site physical readiness confirmation

#### Phase 10a: Procurement
- Legal entity identification (who is signing the PO)
- Buyer IT approval process for multi-million dollar POs
- Approver chain and speed
- Pre-requisite paperwork: MSA, NDAs with vendors

#### Phase 10b: Order Sequencing
1. Racks, PDUs, physical infrastructure
2. Networking gear
3. Compute and storage
4. Cables and accessories (order early, always arrives late)
5. Software licenses (parallel track, needed before go-live)

---

### 2.3 Categories the Agent Must Handle

| Category | Key Questions | Primary Vendors |
|---|---|---|
| Data Center / COLO | Rack count, power/cooling, conveyed hardware | Equinix, NTT DOCOMO |
| SD-WAN | Site count, bandwidth needs, HA requirements | Cisco, CDW, NTT Data |
| Cybersecurity | Endpoints, compliance requirements, SIEM volume | CrowdStrike, Palo Alto, CDW |
| Network Equipment | Switch ports needed, PoE requirements, rack depth | Cisco, CDW, PC Connection |
| M365 & Power Platform | User count, E3 vs E5, Power BI Premium | CDW, Microsoft |
| Cloud Infrastructure | Azure regions, workload types, ExpressRoute vs VPN | Microsoft, NTT Data |
| EOL Replacement | Current hardware age, end-of-support dates | Dell, HPE, Lenovo, CDW |
| Laptops | User count, role-based specs, domain join | Dell, HP, Lenovo, CDW |

---

### 2.4 Business Rules the Agent MUST Enforce

1. **3-Party Sign-Off**: BOM cannot move to "Approved" status without Buyer IT, Seller IT, and SI all marking approved
2. **EOL/EOS Check**: Any SKU that is end-of-life must be flagged and replacement recommended
3. **Lead Time Warning**: Automatically warn when equipment lead time > 8 weeks given Day 1 date
4. **Dual Quote Requirement**: Flag if only one vendor quoted a line item over $50K
5. **Spare Parts Rule**: Critical components (drives, NICs, PSUs) must include 10% spares line
6. **Maintenance Contract Requirement**: Every hardware line item must have a corresponding maintenance/support line
7. **Order Sequencing Lock**: Excel export includes order sequence column enforcing Phase 10b sequence
8. **Audit Trail**: Every status change, edit, approval is logged with timestamp and user

---

### 2.5 The Pain Points We Are Solving

| Pain | Root Cause | Our Solution |
|---|---|---|
| 2-week BOM cycle | Email back-and-forth | Structured guided chat → instant BOM draft |
| Incorrect SKUs | Manual lookup, no validation | Catalog with SKU validation + EOL check |
| Missing sign-offs | No workflow enforcement | 3-party approval state machine |
| Wrong/outdated prices | Static spreadsheets | Live catalog with vendor price comparison |
| No audit trail | Email threads | Every action logged with user + timestamp |
| Lost version history | File naming (BOM_v3_FINAL2.xlsx) | Version history built into data model |

---

## SECTION 3 — EXECUTION PLAN

### Sprint Structure (2-Week Sprints)

---

### SPRINT 1 (Weeks 1–2): Foundation & Real AI Connection
**Goal: Get real AI talking through the chat interface**

#### Tasks:
1. **Wire Azure OpenAI into backend `chat.py`**
   - Replace the `# TODO` stub with actual Azure OpenAI GPT-4 call
   - File: `backend/api/chat.py` → `process_chat_message()`
   - Use `settings.azure_openai_endpoint` + `settings.azure_openai_api_key`
   - System prompt = 10-phase BOM domain knowledge (Section 2.2 above)

2. **Connect SharePoint to Xoriant drive**
   - File: `extractor/sharepoint_connector.py` — already built, needs real credentials
   - Set `SHAREPOINT_SITE_URL`, `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_CLIENT_SECRET` in `.env`
   - Load golden BOMs into mock DB as reference templates

3. **Add audit logging middleware**
   - New file: `backend/api/audit.py`
   - Log: user_id, action, bom_id, timestamp, field changed, old value, new value
   - Hook into every PUT/POST endpoint

4. **Excel export (proper .xlsx)**
   - Replace CSV export with `openpyxl` library
   - Match Entity/CDW template format (headers, column widths, totals row)

**Deliverable**: Chat page sends real GPT-4 messages, SharePoint credentials connected, audit log writing, Excel downloads

---

### SPRINT 2 (Weeks 3–4): 10-Phase Guided BOM Wizard
**Goal: Hybrid chat/wizard that walks users through the 10-phase methodology**

#### Tasks:
1. **Hybrid Chat UI overhaul**
   - File: `frontend/src/pages/ChatPage.jsx`
   - Phase progress bar (Phase 1 of 10)
   - Structured question cards + free-text option
   - Real-time partial BOM panel updating as answers come in

2. **Backend phase state machine**
   - File: `backend/api/chat.py`
   - `SessionContext` tracks current phase (1–10)
   - Each phase has predefined questions the AI asks
   - AI extracts answers and populates `partial_bom` progressively

3. **Category-specific question flows**
   - Data Center: ask Phase 1–10 in sequence
   - SD-WAN: condensed 5-question flow
   - Each category mapped to its relevant phases

4. **BOM auto-generation from answers**
   - When Phase 7 reached: AI generates full BOM line items
   - Cross-references golden BOM templates from SharePoint
   - Flags any EOL hardware in generated items

**Deliverable**: User can open Chat, say "Data Center BOM for Panasonic", and be guided through all phases to a complete BOM draft

---

### SPRINT 3 (Weeks 5–6): 3-Party Approval Workflow
**Goal: Enforce the Buyer/Seller/SI sign-off business rule**

#### Tasks:
1. **Approval state machine in DB schema**
   - Add to `BOM` schema: `approvals: { buyer_it: null, seller_it: null, si: null }`
   - Status can only become "Approved" when all 3 are non-null

2. **BOM Review Page overhaul**
   - File: `frontend/src/pages/BOMReviewPage.jsx`
   - 3 approval panels: Buyer IT, Seller IT, SI/Technical
   - Each panel: name, role, date, comments, Approve/Reject button
   - Visual lock icon on BOM until all 3 approved

3. **Approval notification flow**
   - When BOM hits "review" status: notify next approver (email stub)
   - Backend: `POST /api/bom/{id}/approve` endpoint with approver role

4. **Audit log for approvals**
   - Every approval/rejection logged: who, when, comments

**Deliverable**: BOM cannot be exported or sent to vendor without 3 approvals in the system

---

### SPRINT 4 (Weeks 7–8): EOL/EOS Validation & SKU Intelligence
**Goal: Agent recommends replacements for discontinued hardware**

#### Tasks:
1. **EOL data source integration**
   - Option A: Scrape/cache Cisco EoL announcements, Dell lifecycle pages
   - Option B: Maintain a JSON file updated monthly with known EOL SKUs
   - File: `extractor/ai_validator.py` — add `check_eol_status(sku)` method

2. **BOM validation on generation**
   - After BOM is generated: run all SKUs through EOL checker
   - Flag EOL items with warning + AI-suggested replacement SKU
   - Show in BOM Library as orange warning badge

3. **SKU catalog expansion**
   - Expand `VendorPriceSelectorPage.jsx` hardcoded catalog → backend-driven
   - `GET /api/catalog?category=&search=` endpoint
   - Catalog includes: SKU, make, model, price, EOL status, replacement SKU

**Deliverable**: Any BOM with EOL/EOS hardware is flagged before it reaches vendors

---

### SPRINT 5 (Weeks 9–10): User Management & KPI Dashboard
**Goal: 20 PwC users with identity + measure the 2-week → 3-day improvement**

#### Tasks:
1. **Basic auth (JWT)**
   - Backend: `POST /api/auth/login` → JWT token
   - Frontend: login page, token stored in Redux/localStorage
   - All API calls require `Authorization: Bearer <token>`
   - 20 users seeded in mock DB with PwC emails

2. **KPI dashboard**
   - Track per-BOM: created_at → approved_at (cycle time in days)
   - Charts: avg cycle time over time, BOMs created per week, approvals pending
   - Target indicator: "Current avg: X days | Target: 3 days"

3. **Audit log viewer**
   - `GET /api/audit?bom_id=&user_id=&date_from=&date_to=`
   - UI in admin panel showing full action history

**Deliverable**: Every user logs in with their identity, KPI dashboard shows cycle time improvement

---

## SECTION 4 — GAP ANALYSIS: Current vs. Required

```
FEATURE                          BUILT?   QUALITY   EFFORT TO COMPLETE
─────────────────────────────────────────────────────────────────────
Chat interface (UI)              ✅ Yes    Medium    2 days (hybrid upgrade)
Chat AI logic (backend)          ❌ Stub   None      5 days (Azure OpenAI wire-up)
10-phase BOM methodology         ❌ None   None      7 days (system prompt + state machine)
SharePoint connection            ⚠️ Wired  Low       2 days (credentials + test)
Golden BOM retrieval (RAG)       ❌ None   None      5 days (vector search or keyword match)
3-party approval workflow        ❌ None   None      5 days
Audit logging                    ❌ None   None      3 days
EOL/EOS validation               ❌ None   None      6 days
Excel export (.xlsx)             ⚠️ CSV    Low       1 day (openpyxl)
Vendor catalog (backend)         ⚠️ Static Low       3 days
User authentication              ❌ None   None      4 days
KPI cycle time tracking          ❌ None   None      3 days
BOM review/approval page         ⚠️ Exists Low       4 days (approval panels)
RFQ Builder                      ✅ Yes    Good      1 day polish
Analytics dashboard              ✅ Yes    Good      1 day (wire real data)
─────────────────────────────────────────────────────────────────────
TOTAL ESTIMATED EFFORT:          ~55 developer-days
At 1 developer full-time:        ~11 weeks
At 2 developers:                 ~6 weeks
```

---

## SECTION 5 — PROBABILITY ASSESSMENT

### Chance of Achieving "2 weeks → 3 days"

**Current State Score: 35/100**
The frontend shell is impressive and the extractor pipeline is strong. But the core value — AI-guided BOM creation, real LLM, approval workflow — is all stubs.

**After Sprint 1–2 (4 weeks): 65/100**
With real Azure OpenAI + 10-phase wizard, users can create a BOM draft in hours instead of days. This alone cuts the cycle from 2 weeks to ~5–7 days.

**After Sprint 3–4 (8 weeks): 85/100**
3-party approval workflow + EOL validation eliminates the two biggest causes of rework (missing sign-offs, wrong SKUs). Cycle drops to 3–4 days.

**After Sprint 5 (10 weeks): 90/100**
With user identity, KPI tracking, and audit log, the system is production-ready for 20 PwC users.

**Why not 100%?**
- Lead times from vendors (8–20 weeks) cannot be compressed by software
- The "3-day" target depends on approvers responding within hours — human behavior
- EOL data must be maintained; stale data creates false confidence

### Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Azure OpenAI credentials not available | Medium | High | Use Groq/OpenAI as fallback (already in LLM router) |
| SharePoint credentials not received from Surender | High | Medium | Use local JSON golden BOMs as interim |
| Approvers don't respond within 3 days | Medium | High | Email reminders + escalation timer |
| EOL data goes stale | High | Medium | Monthly refresh job + manual override flag |
| PwC users resist new tool | Low | High | Keep Excel export as safety valve, no forced migration |
| Cosmos DB costs on Azure | Low | Medium | Mock DB works for demo; upgrade when ready |

---

## SECTION 6 — IMMEDIATE NEXT STEPS (This Week)

### Day 1–2: Unblock AI
```
1. Get Azure OpenAI endpoint + API key from Avijeet
2. Set USE_AZURE_OPENAI=true in backend/.env
3. Wire GPT-4 call into backend/api/chat.py → process_chat_message()
4. Test: does the chat page now return real AI responses?
```

### Day 3: Unblock SharePoint
```
1. Get SharePoint app registration credentials from Surender/Avijeet
2. Set SHAREPOINT_SITE_URL, SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET
3. Test extractor/sharepoint_connector.py connection
4. Download golden BOMs into quotes/ folder
```

### Day 4–5: Excel Export + Audit Log
```
1. pip install openpyxl in backend/requirements.txt
2. Replace CSV export with proper .xlsx in bom.py
3. Create backend/api/audit.py with in-memory audit log
4. Hook audit.log_action() into every POST/PUT endpoint
```

---

## SECTION 7 — ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + MUI)                       │
│  OverviewPage → BOMLibraryPage → ChatPage → BOMReviewPage        │
│  VendorPriceSelectorPage → RFQBuilderPage → QuoteExtractorPage   │
└────────────────────────┬────────────────────────────────────────┘
                         │ REST API (axios)
┌────────────────────────▼────────────────────────────────────────┐
│                   BACKEND (FastAPI Python)                        │
│  /api/bom  /api/chat  /api/analytics  /api/audit  /api/auth      │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  AI Agent Layer (Azure OpenAI GPT-4)                     │    │
│  │  - 10-phase system prompt                                │    │
│  │  - Phase state machine                                   │    │
│  │  - BOM generation from answers                          │    │
│  │  - EOL/EOS validation                                   │    │
│  └──────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Data Layer                                              │    │
│  │  - Mock Cosmos DB (dev) / Real Cosmos DB (prod)          │    │
│  │  - SharePoint (Xoriant) → Golden BOM templates           │    │
│  │  - ADLS → Raw quote files storage                        │    │
│  └──────────────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│              EXTRACTOR PIPELINE (Python)                          │
│  SharePoint → File Processor → Heuristic Extractor               │
│  → LLM Validator (Groq/OpenAI) → AI Categorizer → Web Enricher  │
│  → GitHub Pusher → catalog_data.json                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## SECTION 8 — SUCCESS METRICS (KPIs to Track)

| KPI | Current | Target | Measurement |
|---|---|---|---|
| BOM cycle time | 14 days | 3 days | created_at → approved_at per BOM |
| BOM draft creation time | 2–3 days | < 1 hour | created_at → first_draft_at |
| Approval round-trips | 4–6 emails | 1 workflow | approval_count per BOM |
| SKU error rate | ~15% | < 2% | EOL flags caught before vendor submission |
| Vendor quote revision cycles | 2–3 revisions | 0–1 revisions | revision_count per vendor submission |
| User adoption | 0 | 20 PwC users | active_users per week |

---

*This document is the single source of truth for the BOM Agent project. Update after each sprint.*
