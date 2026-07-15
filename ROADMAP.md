# ROADMAP — IT BOM Contracting Agent
## Single Source of Truth | Consolidated from: MASTER_PLAN + Client Feedback + Code Gap Analysis
### Last Updated: 2026-06-30

---

## PART 1 — CODEBASE REALITY CHECK

### Built & Working ✅

| Module | File(s) | Status | Notes |
|---|---|---|---|
| Frontend shell | `frontend/src/App.jsx` | ✅ | React + MUI + Redux, 6 routes registered |
| Overview / Analytics | `OverviewPage.jsx` | ✅ | Hardcoded data, Chart.js, KPI cards, live BOM alerts from Redux |
| BOM Library | `BOMLibraryPage.jsx` | ✅ | Inline edit, compare, CSV export, approval status buttons |
| AI Chat / BOM Creation | `ChatPage.jsx` | ✅ (shallow) | Keyword-matching only, no backend call, local template engine |
| Vendor Price Selector | `VendorPriceSelectorPage.jsx` | ✅ | 12-item hardcoded catalog, add-to-BOM dispatches Redux |
| RFQ Builder | `RFQBuilderPage.jsx` | ✅ | Cart-based, CSV export, pre-populates from activeBOMForRFQ |
| Quote Extractor | `QuoteExtractorPage.jsx` | ✅ | Client-side CSV/JSON parse, map-to-BOM, confidence scoring |
| FastAPI backend | `backend/main.py` | ✅ | CORS, GZip, error handlers, request timing middleware |
| DB schemas | `backend/db/schemas.py` | ✅ | Full Pydantic: BOM, LineItem, BOMTotals, ChatSession, Template, User |
| Config / feature flags | `backend/config.py` | ✅ | All env vars, USE_DUMMY_* flags, dual AI support |
| Mock Cosmos DB | `backend/db/mock_cosmos_client.py` | ✅ | In-memory dict, seeds sample user + template, resets on restart |
| Real Cosmos DB client | `backend/db/cosmos_client.py` | ⚠️ | Written, needs real Azure credentials |
| SharePoint connector | `extractor/sharepoint_connector.py` | ⚠️ | Microsoft Graph auth written, NOT connected to Xoriant drive |
| Extractor pipeline | `extractor/` (8 files) | ✅ | Hybrid: heuristic → LLM validate → categorize → web enrich |
| LLM router | `extractor/llm_router.py` | ✅ | Groq → Llama → OpenAI failover |

### Stubs / Incomplete ⚠️

| Module | File | Problem |
|---|---|---|
| Backend chat API | `backend/api/chat.py` | Rule-based fallback only; Azure OpenAI path exists but untested end-to-end |
| Backend BOM API | `backend/api/bom.py` | CRUD works against mock; API signature mismatch with mock (see bugs below) |
| Analytics API | `backend/api/analytics.py` | All 4 endpoints return hardcoded dummy numbers |
| Templates API | `backend/api/templates.py` | Queries mock DB; only 1 template seeded |
| Excel export | `backend/api/bom.py` `export_bom_excel` | Returns JSON not .xlsx; TODO comment in code |
| Frontend → backend connection | All pages | Pages read Redux only; none call the backend API at runtime |
| Auth | `frontend/src/store/slices/authSlice.js` | State defined, never populated; Bearer token injection commented out |
| React Query | `frontend/src/main.jsx` | Wired in providers but zero `useQuery`/`useMutation` calls exist anywhere |

### Not Built ❌

| Feature | Client Requirement Source |
|---|---|
| 3-party approval workflow (Buyer / Seller / SI) | Q6 — "all 3 must agree BOM is final" |
| Audit logging (every action, edit, approval) | Q12 — "Yes, audit logging required" |
| 10-phase guided BOM wizard | Q3/Q4 — full 10-phase methodology provided by client |
| Category-specific question flows (7 categories) | Q4 — each category has distinct scoping questions |
| EOL/EOS SKU validation with replacement recommendations | Q15 — "agent should recommend changes accordingly" |
| Real Excel (.xlsx) export | Q5 — "Excel. I've provided you the BOMs" |
| SharePoint → Xoriant drive → golden BOM retrieval | Q1 — "use Xoriant SharePoint drive" |
| KPI cycle-time tracking (2 weeks → 3 days) | Q11 — "time to finalize BOM reduced to days" |
| User authentication (20 PwC users) | Q10 — "our PwC team, 20 users" |
| Agent architecture (Orchestrator, Gatherer, Filler etc.) | IMPLEMENTATION_PLAN Phase 2 — never built |
| PDF export | `backend/api/bom.py` returns HTTP 501 |

### Known Bugs 🐛

| Bug | Location | Detail |
|---|---|---|
| API signature mismatch | `backend/api/bom.py` + `mock_cosmos_client.py` | `bom.py` calls `cosmos_client.get_bom(bom_id)` with 1 arg; mock requires 2 (`bom_id, project_name`). Runtime crash on first `GET /api/bom/{id}`. |
| `BOM.updated_at` field missing | `backend/db/schemas.py` + `backend/api/bom.py` | `update_bom()` sets `bom.updated_at` but `BOM` schema only has `modified_at` — field name mismatch. |
| `BOM.notes` field missing | `backend/api/bom.py` | `BOMUpdateRequest` has `notes` field; `BOM` schema has no `notes` field. |
| Unrouted pages | `frontend/src/App.jsx` | `BOMReviewPage.jsx`, `DashboardPage.jsx`, `OverviewPage_new.jsx` exist in `pages/` but are not registered in routing. |
| `uiSlice.sidebarOpen` unused | `frontend/src/components/Layout.jsx` | Sidebar collapse uses local `useState`; Redux `uiSlice.sidebarOpen` is never read or written. |
| LangChain/LangGraph installed but unused | `backend/requirements.txt` | `langchain`, `langchain-community`, `langgraph` are listed as dependencies but imported nowhere in the codebase. |

---

## PART 2 — CLIENT REQUIREMENTS MAPPING

### From Client Q&A Session (2026-06-30)

| # | Client Answer | Maps To | Priority |
|---|---|---|---|
| Q1 | Use Xoriant SharePoint for golden BOMs | SharePoint connector → backend golden BOM seed | P0 |
| Q2 | Start with Vendor Contracting | Full chat → BOM → approval → RFQ → Excel chain | P0 |
| Q3/Q4 | 10-phase DC methodology, 7 categories | AI system prompt redesign + phase state machine | P0 |
| Q5 | Excel format, CDW/Entity template | Real `.xlsx` with openpyxl | P0 |
| Q6 | 3-party signoff: Buyer + Seller + SI | `BOMApproval` schema + approval state machine | P0 |
| Q7 | Pain: email back-and-forth, wrong SKUs | Structured workflow + SKU validation | P0 |
| Q8 | Target: 2 weeks → 3 days | KPI tracking on `created_at → approved_at` | P1 |
| Q9 | Hybrid chat + wizard | Phase progress bar + structured question cards in ChatPage | P0 |
| Q10 | 20 PwC users | JWT/Azure AD auth, 20 seeded users | P1 |
| Q11 | KPI = time to finalize BOM | Analytics dashboard with cycle time | P1 |
| Q12 | Audit logging required | `AuditEvent` schema, log every mutation | P0 |
| Q13/Q14 | Vendors receive by email, Excel only | Excel export only, no vendor API integration needed | P0 |
| Q15 | AI must flag EOL/EOS, recommend alternatives | EOL data source + validate_bom checks | P0 |
| Q16 | Xoriant Azure subscription, Avijeet's codebase | Wire real Azure credentials via `.env` | P1 |

---

## PART 3 — DOMAIN KNOWLEDGE (AI Agent Brain)

### The 10-Phase BOM Methodology (Client-Confirmed)

#### Phase 1: Scope & Constraints
- What lands in DC vs. stays in cloud/SaaS/co-lo? (eliminates false requirements early)
- Any specialized hardware — AS400, bare metal, GPU, high-memory?
- Physical site type — existing server room, co-lo, or greenfield build?
- Power and cooling specs (gates rack density, UPS sizing, HVAC)
- Day 1 cutover date (drives all lead times backward)

#### Phase 2: Seller Inventory
- Application-to-server mapping from Seller
- Conveyed vs. non-conveyed servers
- Age, spec, warranty status of conveyed hardware
- EOL OS or hardware → flagged for modernization, NOT migrated as-is
- Current rack layout and power draw per rack (baseline for new DC design)

#### Phase 3: Compute Sizing
- Per-app: CPU cores, RAM, storage IOPS, network bandwidth, HA requirements
- Consolidation ratio: 8:1 to 15:1 (VMware/Hyper-V)
- Minimum 3 nodes for HA cluster
- 20–30% headroom on all sizing

#### Phase 4: Storage Sizing
- Tier 1 (SSD/NVMe): databases, ERP, latency-sensitive
- Tier 2 (SAS/SATA HDD): file shares, archives, backup targets
- RAID overhead: +20–25%
- Backup/snapshot storage: 2–3× primary
- Architecture: SAN / NAS / HCI / DAS
- Storage network: FC vs iSCSI vs NVMe-oF

#### Phase 5: Network Sizing
- Core / distribution / access layer architecture
- ToR switch count = rack count
- Uplink sizing: 10G / 25G / 100G
- DC uplink to WAN: MPLS, DIA circuits
- Microsegmentation / east-west traffic requirements
- OOB management network (separate from production)
- Firewall: throughput, CPS, VPN capacity
- Load balancer: externally facing apps

#### Phase 6: Power & Physical Infrastructure
- Total power draw across compute + storage + networking
- PUE factor: 1.4–1.6 typical on-prem
- UPS: N+1 configuration
- PDUs per rack
- Rack count and layout (raised floor vs overhead cabling)
- CRAC/CRAH cooling sizing by heat load per rack
- Generator requirements

#### Phase 7: Build the BOM
BOM must be structured by these 9 sub-categories:
1. **Compute** — server make/model, CPU, RAM, NIC, qty
2. **Storage** — array, capacity, tier, controllers, qty
3. **Networking** — ToR switches, core switches, OOB, firewalls, load balancers
4. **Cabling** — fiber, copper, patch panels, cable management
5. **Physical** — racks, PDUs, KVM switches, rails
6. **Power** — UPS units, PDUs, power strips
7. **Software Licenses** — hypervisor, storage OS, network OS, management tooling
8. **Maintenance Contracts** — 3–5 year hardware support on every hardware line item
9. **Spares** — 10% of critical components (drives, NICs, PSUs)

#### Phase 8: Approvals (3-Party Rule — HARD REQUIREMENT)
- ✅ Seller IT team reviewed and approved
- ✅ Buyer IT team reviewed and approved
- ✅ SI (Systems Integrator / JBR or internal) reviewed and approved
- BOM status cannot reach `approved` until all 3 are confirmed in the system

#### Phase 9: Validate & Pressure-Test
- SI / hardware vendor review before ordering
- Application owners review (they catch missed requirements)
- Lead time check: networking + servers = 8–20 weeks in constrained markets
- Dual vendor quotes required for any line item over $50K
- Site physical readiness confirmed before delivery dates

#### Phase 10a: Procurement
- Legal entity signing the PO identified
- Buyer IT approval process documented for multi-million dollar spend
- Approver chain and speed confirmed
- Pre-requisite paperwork in place: MSA, NDAs

#### Phase 10b: Order Sequencing (enforced as a column in Excel export)
1. Racks, PDUs, physical infrastructure first
2. Networking gear second
3. Compute and storage third
4. Cables and accessories (order early — always arrives late)
5. Software licenses (parallel track, needed before go-live)

---

### Category-Specific Question Sets

| Category | Key Scoping Questions |
|---|---|
| **Data Center / COLO** | Rack count, power/cooling specs, conveyed hardware inventory, Day 1 date, co-lo vs greenfield |
| **SD-WAN** | Number of sites, ISP type per site (broadband/MPLS), existing WAN, HA requirements, ZTNA/NGFW needs |
| **Cybersecurity** | Endpoint count, compliance requirements (SOC2/ISO), SIEM daily log volume, existing tooling gaps |
| **Network Equipment** | Building count, port density per floor, PoE requirements, stacking needs, uplink speed |
| **EOL Replacement** | Current hardware age, end-of-support dates, like-for-like vs upgrade, vendor preference |
| **Access Points** | Site survey available?, user density per AP, indoor/outdoor, cloud vs on-prem controller |
| **M365 & Power Platform** | User count by license tier (E3/E5), Power BI Premium need, Teams Direct Routing, migrating from |
| **Cloud Infrastructure** | Azure regions, workload types, ExpressRoute vs VPN, landing zone, subscription structure |
| **Laptops** | User count by role/persona, Windows/macOS, peripheral bundle, MDM platform (Intune/Jamf) |

---

### Business Rules the Agent MUST Enforce

| Rule | Enforcement Point |
|---|---|
| **3-Party Sign-Off** | BOM status → `approved` only when all 3 approvals exist in DB |
| **EOL/EOS Check** | Run on BOM generation and on `POST /api/bom/validate` |
| **Lead Time Warning** | Auto-warn when equipment lead time > 8 weeks given Day 1 date |
| **Dual Quote Requirement** | Flag if only 1 vendor quoted a line item with `extended_price > $50,000` |
| **Spare Parts Rule** | Warn if no spares line (~10%) for critical components (drives, NICs, PSUs) |
| **Maintenance Contract Rule** | Warn if a hardware line item has no corresponding maintenance/support line |
| **Order Sequencing** | Excel export includes `order_sequence` column enforcing Phase 10b sequence |
| **Audit Trail** | Every status change, field edit, and approval logged with user + timestamp |

---

## PART 4 — SCHEMA CHANGES REQUIRED

### 4.1 Add `BOMApproval` to `backend/db/schemas.py`

```python
class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class BOMApproval(BaseModel):
    party: str                          # "buyer_it" | "seller_it" | "si"
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    comments: Optional[str] = None
    status: ApprovalStatus = ApprovalStatus.PENDING

# Add to BOM class:
approvals: List[BOMApproval] = Field(default_factory=lambda: [
    BOMApproval(party="buyer_it"),
    BOMApproval(party="seller_it"),
    BOMApproval(party="si"),
])
notes: Optional[str] = None              # currently missing from BOM schema
updated_at: Optional[datetime] = None    # currently named modified_at — align naming
day_one_date: Optional[datetime] = None  # for lead time warnings (Phase 1)
```

### 4.2 Add `AuditEvent` to `backend/db/schemas.py`

```python
class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"audit_{uuid4().hex[:12]}")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: str
    user_name: Optional[str] = None
    action: str      # "created"|"modified"|"approved"|"rejected"|"exported"|"submitted"
    entity_type: str # "bom"|"session"|"template"
    entity_id: str
    field_changed: Optional[str] = None
    before_value: Optional[Any] = None
    after_value: Optional[Any] = None
    metadata: Dict[str, Any] = {}
```

### 4.3 Fix Cosmos DB API Signature Mismatch (Bug — Fix First)

```python
# backend/api/bom.py — current (broken):
bom_data = cosmos_client.get_bom(bom_id)

# backend/api/bom.py — fix:
bom_data = cosmos_client.get_bom(bom_id, partition_key=bom_id)

# backend/db/mock_cosmos_client.py — make project_name optional:
def get_bom(self, bom_id: str, project_name: str = None) -> Optional[BOM]:
```

### 4.4 Field Naming Alignment

- `BOM.modified_at` → rename to `updated_at` (used in `update_bom()` already)
- `LineItem.quantity` → add alias `qty` for frontend compatibility
- `LineItem.unit_price` → add alias `unitPrice` for frontend compatibility
- `LineItem.extended_price` → add alias `extPrice` for frontend compatibility

---

## PART 5 — AGENT ARCHITECTURE (To Build)

The IMPLEMENTATION_PLAN Phase 2 defined an agent architecture. **None of it has been built.**
LangChain and LangGraph are in `requirements.txt` but unused. Here is the target architecture:

```
backend/ai/
├── client.py              ← Azure OpenAI wrapper (model selection, token counting, retries)
├── prompts/
│   ├── system_base.py     ← 10-phase domain knowledge system prompt
│   ├── data_center.py     ← Data Center category-specific prompt
│   ├── sdwan.py           ← SD-WAN category-specific prompt
│   └── ... (one per category)
├── agents/
│   ├── orchestrator.py    ← Routes to specialist agents, tracks phase (1-10)
│   ├── gatherer.py        ← Asks category-specific questions, extracts structured answers
│   ├── template_filler.py ← Applies answers to templates, calculates quantities
│   ├── pricing_agent.py   ← Historical prices, volume discounts, OTC vs run costs
│   ├── validator_agent.py ← Business rules, EOL checks, dual-quote warnings
│   └── explainer_agent.py ← Explains line items, suggests alternatives
└── tools/
    ├── search_tools.py    ← search_similar_boms(), search_patterns(), search_prices()
    ├── calc_tools.py      ← calculate_tco(), calculate_extended(), apply_discounts()
    └── validation_tools.py← check_eol_status(), check_bundle_rules(), check_quantities()
```

The `orchestrator.py` is the entry point called by `backend/api/chat.py`. It replaces the current `process_chat_message()` function.

---

## PART 6 — SPRINT EXECUTION PLAN

### Sprint 1 (Week 1–2): Foundation — Bugs + Real AI + Audit + Excel
**Goal: Chat sends real GPT-4 messages; every action is logged; Excel downloads work**

#### Task 1.1 — Fix known bugs (Day 1)
- [ ] `backend/api/bom.py`: fix `cosmos_client.get_bom(bom_id)` → add `partition_key` arg
- [ ] `backend/db/mock_cosmos_client.py`: make `project_name` optional in all methods
- [ ] `backend/db/schemas.py`: rename `modified_at` → `updated_at`, add `notes: Optional[str]`
- [ ] `frontend/src/App.jsx`: register `BOMReviewPage`, `DashboardPage` in routing

#### Task 1.2 — Wire Azure OpenAI into `backend/api/chat.py` (Days 1–2)
- [ ] Obtain Azure OpenAI endpoint + key from Avijeet; set `USE_AZURE_OPENAI=True` in `.env`
- [ ] Replace generic system prompt in `_process_with_azure_openai()` with the full 10-phase domain knowledge (Part 3)
- [ ] Add per-category system prompt selection based on `session.category`
- [ ] Test: `curl -X POST localhost:8000/api/bom/start -d '{"category":"Data Center"}'`
- [ ] Test: `curl -X POST localhost:8000/api/bom/chat -d '{"session_id":"...","message":"30 racks"}'`

#### Task 1.3 — Connect frontend ChatPage to backend API (Day 2)
- [ ] `frontend/src/pages/ChatPage.jsx`: call `chatService.startSession(category)` on category select
- [ ] Call `chatService.sendMessage(sessionId, message)` on send instead of local `getAIResponse()`
- [ ] Display `response.response` as AI message bubble
- [ ] Display `response.partial_bom` in the BOM preview panel on the right
- [ ] Keep local template engine as fallback if backend returns error

#### Task 1.4 — Audit logging (Days 3–4)
- [ ] Add `AuditEvent` schema to `backend/db/schemas.py` (see Part 4.2)
- [ ] Add `"audit"` container to `backend/db/mock_cosmos_client.py`
- [ ] Create `backend/api/audit.py`:
  - [ ] `log_action(user_id, action, entity_type, entity_id, field, before, after)`
  - [ ] `GET /api/audit` with filters: `bom_id`, `user_id`, `date_from`, `date_to`
- [ ] Hook `log_action()` into every `POST`/`PUT` in `bom.py` and `chat.py`

#### Task 1.5 — Real Excel export with `openpyxl` (Day 5)
- [ ] Add `openpyxl` to `backend/requirements.txt`
- [ ] Rewrite `export_bom_excel()` in `backend/api/bom.py`:
  - Sheet 1: **Summary** — project name, category, status, totals, approval status
  - Sheet 2: **Line Items** — all columns + `order_sequence` column (Phase 10b)
  - Sheet 3: **Version History** — all BOM versions
- [ ] Update `frontend/src/pages/BOMLibraryPage.jsx`: replace client-side CSV with call to `POST /api/bom/export/excel`

**Sprint 1 Deliverable**: Chat → real GPT-4 → BOM generated → saved to backend → every action logged → real .xlsx download

---

### Sprint 2 (Week 3–4): Hybrid 10-Phase BOM Wizard
**Goal: User says "Data Center BOM for Panasonic" and is guided through all 10 phases to a complete BOM**

#### Task 2.1 — Phase state machine in `backend/api/chat.py`
- [ ] Add `current_phase: int = 1` and `phase_data: Dict = {}` to `SessionContext` in `schemas.py`
- [ ] Backend tracks which phase the conversation is in (1–10)
- [ ] Each phase has a predefined question set; AI extracts structured answers and advances phase
- [ ] When Phase 7 data is complete: AI generates full BOM line items

#### Task 2.2 — Build the agent architecture skeleton (Part 5)
- [ ] Create `backend/ai/` directory and `client.py` (Azure OpenAI wrapper)
- [ ] Create `backend/ai/prompts/system_base.py` with the 10-phase knowledge base
- [ ] Create `backend/ai/agents/orchestrator.py` — replaces `process_chat_message()`
- [ ] Create `backend/ai/agents/gatherer.py` — category-specific question logic
- [ ] Wire `orchestrator.py` into `backend/api/chat.py`

#### Task 2.3 — Hybrid UI overhaul in `ChatPage.jsx`
- [ ] Add phase progress bar: "Phase 3 of 10: Compute Sizing"
- [ ] Render structured question cards alongside free-text chat per phase
- [ ] Right panel: real-time partial BOM table updating as AI extracts answers
- [ ] Phase completion checkmarks visible in sidebar

#### Task 2.4 — Register and build `BOMReviewPage.jsx`
- [ ] `frontend/src/App.jsx`: add `<Route path="/bom-review/:bomId" element={<BOMReviewPage />} />`
- [ ] `BOMReviewPage.jsx`: 3-panel approval UI (Buyer IT / Seller IT / SI) — see Sprint 3

#### Task 2.5 — SharePoint golden BOM retrieval
- [ ] Get `SHAREPOINT_SITE_URL`, `CLIENT_ID`, `CLIENT_SECRET` from Surender/Avijeet
- [ ] Test `extractor/sharepoint_connector.py` connection
- [ ] Download golden BOMs into `quotes/` folder, run `extractor/main.py`
- [ ] Seed golden BOMs into `templates` collection in mock Cosmos DB
- [ ] Add golden BOM reference instruction to AI system prompt

**Sprint 2 Deliverable**: Full 10-phase guided flow; golden BOM references used by AI; BOMReviewPage visible in routing

---

### Sprint 3 (Week 5–6): 3-Party Approval Workflow
**Goal: BOM cannot be exported or sent to vendor without all 3 sign-offs**

#### Task 3.1 — Add `BOMApproval` schema
- [ ] `backend/db/schemas.py`: add `ApprovalStatus`, `BOMApproval`, update `BOM` (see Part 4.1)
- [ ] `backend/db/mock_cosmos_client.py`: no changes needed (handles dict storage generically)

#### Task 3.2 — Approval endpoints in `backend/api/bom.py`
- [ ] `POST /api/bom/{bom_id}/approve` — body: `{ party, approved_by, comments, approved: bool }`
  - Updates `BOM.approvals[party].status`
  - If all 3 `APPROVED` → auto-sets `BOM.status = "approved"`
  - Calls `log_action()` for audit
- [ ] `GET /api/bom/{bom_id}/approvals` — returns current state of all 3 approval parties

#### Task 3.3 — Approval UI in `BOMReviewPage.jsx`
- [ ] 3 approval panels: Buyer IT / Seller IT / SI
- [ ] Each panel: approver name input, comments textarea, Approve / Reject buttons, timestamp
- [ ] Visual padlock icon on BOM header — locked until all 3 approved
- [ ] Status banner: "2 of 3 approvals received — waiting on SI"
- [ ] `BOMLibraryPage.jsx`: show approval badge (e.g. "2/3") on each BOM card

#### Task 3.4 — Enforce approvals in validate and export
- [ ] `POST /api/bom/validate`: if status is `approved` or `sent_to_vendor`, require all 3 approvals present
- [ ] `POST /api/bom/export/excel`: add "Approval Sign-offs" section to Summary sheet
- [ ] Audit log every approval and every rejection with full details

**Sprint 3 Deliverable**: No BOM reaches "Approved" or gets exported without all 3 sign-offs recorded in the system

---

### Sprint 4 (Week 7–8): EOL/EOS Validation & Backend Catalog API
**Goal: Agent flags discontinued hardware before it reaches vendors; catalog is backend-driven**

#### Task 4.1 — EOL data source
- [ ] Create `backend/data/eol_skus.json` — maintained monthly:
  ```json
  {
    "C9300-48P-A": {
      "eol_date": "2025-01-31",
      "eos_date": "2028-01-31",
      "replacement_sku": "C9300X-48P-A",
      "replacement_desc": "Cisco Catalyst 9300X 48-port PoE+"
    }
  }
  ```
- [ ] Source from: Cisco EoL portal, Dell product lifecycle, HPE support matrix
- [ ] Create `backend/services/eol_service.py` with `check_eol_status(sku: str) -> dict`

#### Task 4.2 — Integrate EOL check into BOM generation
- [ ] After AI generates line items in `chat.py`, run each SKU through `check_eol_status()`
- [ ] Add `eol_warning: bool` and `replacement_sku: str` fields to `LineItem` schema
- [ ] Frontend: render EOL items with orange warning badge in BOM preview panel

#### Task 4.3 — Integrate EOL check into `validate_bom()`
- [ ] `backend/api/bom.py` `validate_bom()`: for each line item with a SKU, call `check_eol_status()`
- [ ] Add warnings for items where `eol_date < today + 12 months`
- [ ] Add errors for items where `eos_date` has already passed

#### Task 4.4 — Backend catalog API
- [ ] Create `backend/api/catalog.py`:
  - [ ] `GET /api/catalog` — query params: `category`, `search`, `page`, `limit`
  - [ ] Load from `catalog_data.json` (extractor output) on startup
  - [ ] Each item includes: name, SKU, category, vendor pricing, EOL status, replacement SKU
- [ ] `frontend/src/pages/VendorPriceSelectorPage.jsx`: replace hardcoded `CATALOG` constant with `GET /api/catalog` call

#### Task 4.5 — Build `template_filler` and `pricing_agent` (Part 5)
- [ ] `backend/ai/agents/template_filler.py` — applies phase answers to generate line items
- [ ] `backend/ai/agents/pricing_agent.py` — cross-references catalog for historical pricing
- [ ] `backend/ai/agents/validator_agent.py` — runs all business rules from Part 3

**Sprint 4 Deliverable**: Any BOM with EOL/EOS hardware shows warnings before reaching vendors; catalog is live from backend

---

### Sprint 5 (Week 9–10): Auth, KPI Dashboard & Production Readiness
**Goal: 20 PwC users with identity; KPI dashboard shows cycle time; system ready for Xoriant Azure**

#### Task 5.1 — JWT authentication
- [ ] Create `backend/api/auth.py`:
  - [ ] `POST /api/auth/login` → validates credentials → returns JWT token
  - [ ] `get_current_user()` dependency for protected endpoints
- [ ] Seed 20 PwC user accounts in mock DB with PwC emails and hashed passwords
- [ ] Add `Depends(get_current_user)` to all `POST`/`PUT` endpoints in `bom.py` and `chat.py`
- [ ] `frontend/src/store/slices/authSlice.js`: wire `setUser()` on successful login response
- [ ] `frontend/src/services/api.js`: uncomment Bearer token injection in request interceptor
- [ ] Create `frontend/src/pages/LoginPage.jsx` with email/password form
- [ ] `frontend/src/App.jsx`: add `/login` route and redirect unauthenticated users

#### Task 5.2 — KPI cycle-time analytics
- [ ] `backend/api/analytics.py`: replace all 4 dummy endpoints with real Cosmos DB queries
- [ ] Track per-BOM: `created_at → approved_at` → compute cycle time in days
- [ ] New queries: avg cycle time, BOMs by status per week, approvals pending, drafts > 30 days
- [ ] `frontend/src/pages/OverviewPage.jsx`: add "Current avg cycle time: X days | Target: 3 days" KPI card

#### Task 5.3 — Audit log viewer UI
- [ ] Create `frontend/src/pages/AuditLogPage.jsx`:
  - Table: timestamp, user, action, BOM name, field changed, before/after values
  - Filters: BOM, user, date range, action type
- [ ] `frontend/src/App.jsx`: add `/audit` route (visible only to admin role users)

#### Task 5.4 — Wire Redux BOM saves to backend
- [ ] `frontend/src/pages/ChatPage.jsx`: after `dispatch(saveBOM())`, also call `bomService.updateBOM()` or `bomService.createBOM()`
- [ ] `frontend/src/pages/BOMLibraryPage.jsx`: inline cell edits → call `bomService.updateBOM()` after Redux dispatch
- [ ] This closes the loop: BOM data persists to Cosmos DB, not just in-browser Redux memory

#### Task 5.5 — Xoriant Azure deployment
- [ ] Set in `backend/.env`:
  ```
  USE_DUMMY_COSMOS=False
  USE_DUMMY_ADLS=False
  USE_AZURE_OPENAI=True
  COSMOS_DB_ENDPOINT=<from Avijeet>
  COSMOS_DB_KEY=<from Avijeet>
  AZURE_OPENAI_ENDPOINT=<from Avijeet>
  AZURE_OPENAI_API_KEY=<from Avijeet>
  ```
- [ ] Run `extractor/main.py` with Xoriant SharePoint credentials to populate golden BOM catalog
- [ ] Test all endpoints against real Cosmos DB

**Sprint 5 Deliverable**: System production-ready for 20 PwC users on Xoriant Azure; KPI dashboard shows real cycle times

---

## PART 7 — EFFORT & TIMELINE SUMMARY

```
FEATURE                                   SPRINT  EFFORT    FILES TOUCHED
────────────────────────────────────────────────────────────────────────────────
Fix API signature + schema bugs           1       0.5 days  bom.py, mock_cosmos_client.py, schemas.py
Wire Azure OpenAI in chat.py              1       2 days    chat.py, config.py
Connect frontend chat → backend           1       1 day     ChatPage.jsx, bomApi.js
Audit logging                             1       3 days    audit.py, schemas.py, bom.py, chat.py
Real Excel export (.xlsx)                 1       1.5 days  bom.py, requirements.txt, BOMLibraryPage.jsx
────────────────────────────────────────────────────────────────────────────────
Phase state machine (backend)             2       4 days    chat.py, schemas.py
Agent architecture skeleton               2       4 days    backend/ai/ (new directory)
Hybrid wizard UI (frontend)               2       4 days    ChatPage.jsx
Register + build BOMReviewPage            2       1 day     App.jsx, BOMReviewPage.jsx
SharePoint golden BOM retrieval           2       2 days    sharepoint_connector.py, backend startup
────────────────────────────────────────────────────────────────────────────────
BOMApproval schema                        3       1 day     schemas.py
Approval endpoints                        3       2 days    bom.py
Approval UI (BOMReviewPage)               3       3 days    BOMReviewPage.jsx, BOMLibraryPage.jsx
Enforce approvals in validate/export      3       1 day     bom.py
────────────────────────────────────────────────────────────────────────────────
EOL data source + service                 4       2 days    data/eol_skus.json, eol_service.py
EOL check in BOM generation               4       2 days    chat.py, ChatPage.jsx (warning badges)
EOL check in validate_bom()               4       1 day     bom.py
Backend catalog API                       4       2 days    new api/catalog.py
VendorPriceSelectorPage → backend         4       1 day     VendorPriceSelectorPage.jsx
Template filler + pricing agents          4       3 days    backend/ai/agents/
────────────────────────────────────────────────────────────────────────────────
JWT authentication                        5       4 days    new api/auth.py, authSlice.js, api.js, LoginPage.jsx
KPI cycle-time analytics                  5       3 days    analytics.py, OverviewPage.jsx
Audit log viewer UI                       5       2 days    new AuditLogPage.jsx, App.jsx
Wire Redux saves → backend                5       2 days    ChatPage.jsx, BOMLibraryPage.jsx
Xoriant Azure deployment                  5       1 day     .env, startup scripts
────────────────────────────────────────────────────────────────────────────────
TOTAL                                             ~55 developer-days
1 developer full-time:                            ~11 weeks
2 developers:                                     ~6 weeks
```

---

## PART 8 — IMMEDIATE NEXT STEPS (This Week)

### Day 1: Fix bugs + unblock AI
```
1. Fix cosmos_client.get_bom() signature mismatch in bom.py and mock_cosmos_client.py
2. Fix BOM schema: rename modified_at → updated_at, add notes: Optional[str] field
3. Get Azure OpenAI endpoint + API key from Avijeet
4. Set USE_AZURE_OPENAI=True, fill AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY in backend/.env
5. Replace generic system prompt in chat.py with 10-phase domain knowledge
6. Test: POST /api/bom/start → POST /api/bom/chat and verify real GPT-4 response
```

### Day 2: Connect frontend to backend
```
1. ChatPage.jsx: call chatService.startSession(category) on category chip click
2. ChatPage.jsx: call chatService.sendMessage(sessionId, msg) on message send
3. Display response.response as AI message bubble
4. Display response.partial_bom in BOM preview panel
5. Test full round-trip in browser
```

### Day 3: SharePoint credentials
```
1. Get SHAREPOINT_SITE_URL, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET from Surender/Avijeet
2. Set credentials in extractor/.env
3. Test: python extractor/sharepoint_connector.py
4. Download golden BOMs into quotes/ folder
5. Run: python extractor/main.py — verify catalog_data.json is populated
```

### Day 4: Audit log
```
1. Add AuditEvent to backend/db/schemas.py
2. Add "audit" container to mock_cosmos_client.py
3. Create backend/api/audit.py with log_action() and GET /api/audit endpoint
4. Call log_action() at end of every POST/PUT in bom.py and chat.py
```

### Day 5: Excel export
```
1. pip install openpyxl → add to backend/requirements.txt
2. Rewrite export_bom_excel() in bom.py with openpyxl
3. Sheets: Summary, Line Items (with order_sequence column), Version History
4. Update BOMLibraryPage.jsx to call POST /api/bom/export/excel instead of CSV
```

---

## PART 9 — RISK REGISTER

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Azure OpenAI credentials not received from Avijeet | Medium | High | Use Groq fallback — already in `extractor/llm_router.py` |
| SharePoint credentials not received from Surender | High | Medium | Use local `quotes/` folder with manually downloaded BOMs as interim |
| Approvers don't respond within 3 days (human bottleneck) | Medium | High | Audit log shows pending approvals; add email reminder stub in Sprint 3 |
| EOL data goes stale | High | Medium | Add "EOL data last updated: DATE" banner in UI; schedule monthly refresh |
| Frontend/backend field naming mismatch (`qty` vs `quantity`) | High | Medium | Add Pydantic aliases; document in schemas.py |
| PwC users resist switching from manual Excel | Low | High | Keep Excel export as primary output; no forced migration from existing process |
| Cosmos DB cold-start latency on Azure | Low | Medium | Mock DB works for all dev/demo; upgrade only when production-ready |

---

## PART 10 — SUCCESS METRICS

| KPI | Current Baseline | Target | How Measured |
|---|---|---|---|
| BOM cycle time (full) | 14 days | 3 days | `created_at → approved_at` per BOM in analytics |
| BOM first draft time | 2–3 days | < 1 hour | `created_at` → first line item generated in session |
| Approval round-trips | 4–6 emails | 1 workflow click | `approval_count` per BOM in audit log |
| SKU error rate | ~15% | < 2% | EOL flags caught before vendor submission |
| Vendor quote revision cycles | 2–3 | 0–1 | `revision_count` per vendor submission |
| User adoption | 0 users | 20 PwC users | `active_users` per week from auth logs |

---

## PART 11 — ARCHITECTURE DIAGRAM

```
┌────────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + MUI + Redux)                  │
│                                                                      │
│  OverviewPage  BOMLibraryPage  ChatPage  BOMReviewPage              │
│  VendorPriceSelectorPage  RFQBuilderPage  QuoteExtractorPage        │
│  LoginPage  AuditLogPage                                            │
└───────────────────────────┬────────────────────────────────────────┘
                            │ REST API (Axios)
                            │ Auth: Bearer JWT
┌───────────────────────────▼────────────────────────────────────────┐
│                    BACKEND (FastAPI Python)                          │
│                                                                      │
│  /api/auth    /api/bom    /api/chat                                 │
│  /api/analytics  /api/templates  /api/catalog  /api/audit           │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │             AI Agent Layer (Azure OpenAI GPT-4)               │   │
│  │  orchestrator → gatherer → template_filler                   │   │
│  │  pricing_agent → validator_agent → explainer_agent           │   │
│  │  10-phase system prompt + category-specific prompts          │   │
│  │  EOL/EOS validation service                                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                       Data Layer                              │   │
│  │  Mock Cosmos DB (dev)  ←──────→  Real Cosmos DB (prod)       │   │
│  │  Mock ADLS (dev)       ←──────→  Real ADLS (prod)            │   │
│  │  SharePoint (Xoriant)  →  Golden BOM templates               │   │
│  └──────────────────────────────────────────────────────────────┘   │
└───────────────────────────┬────────────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────────────┐
│                  EXTRACTOR PIPELINE (Python — offline)              │
│                                                                      │
│  SharePoint → file_processor → heuristic_extractor                 │
│  → ai_validator (Groq/OpenAI) → ai_categorizer                     │
│  → web_scraper (optional) → catalog_data.json                      │
└────────────────────────────────────────────────────────────────────┘
```

---

*This document supersedes `MASTER_PLAN.md` and `IMPLEMENTATION_PLAN.md`.*
*Update at the end of each sprint with completed checkboxes and new decisions.*
