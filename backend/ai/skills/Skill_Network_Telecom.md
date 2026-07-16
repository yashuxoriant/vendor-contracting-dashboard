# Skill: Network & Telecom
<!-- Categories: SD-WAN, Network Equipment, Access Points, WAN, LAN, Wireless, Voice -->
<!-- Invoked by: BOMAgent Step 9 when workstream_category is Network & Telecom, SD-WAN, Network Equipment, or Access Points -->

## Purpose

Produce a complete, vendor-ready BOM for network and telecom infrastructure in M&A Day-1 / TSA Exit scenarios.
Covers: LAN switching, WAN/SD-WAN routers, wireless access points, firewalls (network layer), voice/UCaaS, and OOB management.

---

## Decision Rules — Enforce Before Every BOM

These are deterministic rules. Apply them to every network BOM regardless of user instructions.

```
IF site_criticality = "critical"
  → ALL network layers (core switch, distribution, firewall, WAN router) MUST be HA pairs
  → Single-unit designs for critical sites are a guaranteed Buyer IT rejection

IF user_count_per_site > 500 OR compliance IN [PCI-DSS, HIPAA, SOC 2, CMMC]
  → Firewall MUST be an HA pair (two appliances, same model)
  → Single firewall for a compliant or large site → add BLOCKING warning

IF SSL_inspection_required = true
  → Select firewall platform with 2× the throughput calculated from traffic sizing
  → SSL inspection reduces rated throughput by 60–80% on entry-level appliances

IF WAN_bandwidth = unknown
  → CANNOT size SD-WAN router model or circuit cost
  → Cap BOM maturity at ROM; add BLOCKING warning

IF Day1_date = unknown
  → All lead-time risk flags are disabled
  → Add HIGH warning: "Lead-time risk cannot be assessed without Day 1 date"

IF total_PoE_load_per_switch > 0.8 × switch_PoE_rating
  → Upgrade switch to next PoE tier; do NOT accept an oversubscribed PoE design

IF conveyance_status = "conveying" AND asset_lifecycle_status NOT IN ["eol", "eos"]
  → Do NOT include replacement hardware for conveyed assets
  → Include only integration, licensing, and ongoing support contract line items

IF carrier_circuit_required = true (new site, new address, or new standalone entity)
  → Add CRITICAL warning: "Carrier provisioning required — 12–20 weeks for MPLS;
     initiate vendor engagement immediately regardless of other lead times"

IF site_count > 3
  → Add OOB console server with cellular/LTE backup per remote site (mandatory)
```

---

## 6-Question Intake Flow

> **Note:** Conveyance status and M&A phase are consumed from the BOMAgent orchestrator handoff package (Steps 3–9). Do NOT re-ask these — doing so is a Rule 2 violation.

Ask in this order. Each answer unlocks the next sizing dimension:

**Q1 — User count** *(unlocks port density, AP count, firewall session sizing)*
How many users per site? Provide a per-site breakdown if counts differ across locations.

**Q2 — Site count and type** *(unlocks topology design and total hardware quantities)*
How many sites? Are they offices, data centers, or warehouses? Any remote/home workers requiring VPN?

**Q3 — WAN bandwidth and redundancy** *(unlocks SD-WAN router model and circuit cost)*
Required WAN bandwidth per site? Active/active or active/passive redundancy? Existing carrier contracts?

**Q4 — Compliance and vendor preference** *(unlocks HA requirements and firewall tier)*
Any compliance requirements (PCI-DSS, HIPAA, SOC 2, CMMC)? Preferred vendor: Cisco, Fortinet, Aruba, or competitive?

**Q5 — Existing infrastructure** *(unlocks replacement vs. integration scope)*
What switching/routing/wireless equipment exists today? Approximate model and age?
*(Conveyance status — whether this equipment transfers in the deal — is already known from the orchestrator handoff. Use that value; do not re-ask.)*

**Q6 — Day 1 cutover date** *(unlocks all lead-time risk calculations)*
Hard date when the network must be fully operational on the standalone entity.

**Conditional Q7 — Voice/UCaaS** *(ask only when Q1 implies office users)*
Are IP phones being deployed? If yes, how many? Will the standalone entity use Teams Phone, Webex Calling, Zoom Phone, or an on-prem call manager (Cisco UCM, Avaya)?

---

## Vendor-Ready BOM Gate

Before labeling a BOM as `vendor_ready`, ALL of the following must be confirmed (not assumed):

| Input | Why Mandatory |
|---|---|
| User count per site | Controls port density, AP count, firewall sessions |
| WAN bandwidth per site | Controls SD-WAN router model and circuit cost |
| Conveyance status (from handoff) | Determines replacement vs. integration scope |
| Compliance scope (PCI/HIPAA/SOC2 or "none") | Controls firewall HA requirement |
| Day 1 cutover date | Required for all lead-time risk flags |
| Site criticality (critical/standard) | Controls full HA vs. standard design |

If **any** of the above are unknown → generate as `budgetary` or `rom`, never `vendor_ready`.
If **3 or more** are unknown → do not generate the BOM; ask for the missing inputs first.

---

## Sizing Rules

### SD-WAN / WAN Routers
- Minimum **2 routers per site** for HA (active/passive or active/active ECMP)
- Size throughput at **1.5× peak measured WAN utilisation** + 25% growth headroom
- SD-WAN software licenses: per-device, 3-year term minimum
- Primary reference SKUs: Cisco Catalyst 8300/8200 series, Fortinet FortiGate 200F/400F
- Dual ISP uplinks required for sites with > 100 users or latency-sensitive applications

### LAN Switching
- Access layer: 1 switch per 48 users (allow 20% spare ports); always stack in pairs for redundancy
- Distribution/core: required for sites > 200 users; 10G uplinks between access and distribution
- Core/DC: 25G/100G spine-leaf for data center contexts
- **PoE Budget Validation** (mandatory when IP phones, APs, or cameras are in scope):

  ```
  Per-switch PoE load = (phones × 7.5W) + (APs × 15.4W) + (std cameras × 12W) + (PTZ cameras × 30W)
  Rule: load must be < 80% of switch rated capacity

  Platform capacities:
  - Cisco Catalyst 9200-48P:   370W total PoE
  - Cisco Catalyst 9300-48P:   437W total PoE
  - Cisco Catalyst 9300-48UX: 1,440W total PoE  (PoE++ / 90W ports)
  - Aruba 2930F-48G-PoE+:      370W total PoE

  If estimated load exceeds 80% → upgrade to next tier.
  Include in line item notes: "PoE budget: [load]W / [capacity]W per switch"
  ```

### Wireless Access Points
- **General office:** 1 AP per 30 concurrent users
- **High-density** (conference rooms, trading floors, lecture halls): 1 AP per 15 users
- **Outdoor / warehouse:** 1 AP per 5,000 sq ft (requires outdoor-rated AP)
- Primary reference SKUs: Cisco Catalyst 9130/9120, Aruba AP555/AP535, Meraki MR57
- If **no site survey available**: proceed with density ratios and add:
  `ASSUMPTION [HIGH]: No RF site survey performed — AP count is ±40%. Recommend Ekahau or Cisco DNA Spaces validation before PO submission.`
- Include mounting hardware and PoE injectors if switch PoE budget is insufficient
- Cloud vs. on-prem controller: document decision in BOM `notes`; it affects licensing model

### Firewalls (NGFW)
Firewall sizing requires **four independent inputs** — throughput alone is insufficient:

1. **Throughput:** 2× peak north-south traffic + 30% headroom
2. **Concurrent sessions:** user_count × 1,500 as baseline; higher for contact centers or VDI
3. **SSL inspection:** if enabled, select platform with **2× the throughput** from step 1 above (SSL reduces rated throughput by 60–80%)
4. **VPN:** if > 50 remote users OR > 5 site-to-site tunnels → dedicated VPN concentration or platform upgrade

Platform selection guide (SSL inspection enabled):

| Users per site | Recommended Platform |
|---|---|
| < 250, no SSL inspection | FortiGate 200F or PA-820 |
| < 250, with SSL inspection | FortiGate 400F or PA-1410 |
| 250–500, with SSL inspection | FortiGate 600F or PA-3220 |
| > 500, with SSL inspection | FortiGate 1800F or PA-5250 minimum |

Always include IPS/IDS, URL filtering, SSL inspection, and App-ID as separate license line items.

### Voice / UCaaS *(include only when voice scope confirmed via Q7)*
- **IP phones:** recalculate PoE budget for every affected switch after adding phones
- **SBC (Session Border Controller):** required when migrating to Teams Phone, Webex Calling, or Zoom Phone
  - Size: 1 SBC per 200 concurrent calls; N+1 for production
  - Reference SKUs: AudioCodes Mediant 1000B, Ribbon SBC 1000/2000, Cisco CUBE
- **PSTN gateway or SIP trunk:** required if on-prem call manager (Cisco UCM/Avaya) continues post-cutover
- **QoS configuration:** DSCP marking on all switch layers — scope as professional services line item
- **Voice VLAN:** separate VLAN/subnet for voice traffic; note that switch config is in scope

---

## Out-of-Band (OOB) Management

Mandatory when site_count > 3 or when remote cutover configuration is required:

- Console server with 4–16 serial ports per site
- Cellular/LTE backup modem (prevents dark-site scenario if primary WAN fails during cutover)
- Reference SKUs: Opengear OM2224-L4, Lantronix SLC 8000, Cisco C1100 with cellular NIM
- `order_sequence`: 1 — must arrive and be pre-staged before primary network hardware

---

## Mandatory BOM Line Items

| # | Line Item | Condition |
|---|---|---|
| 1 | WAN routers (qty per site × sites) | Always |
| 2 | LAN core/distribution switches | Sites > 200 users |
| 3 | LAN access switches (ports = users × 2–3 + 20% spare) | Always |
| 4 | Wireless APs (density-based count) | If wireless in scope |
| 5 | NGFW / Firewall appliance(s) — HA pair if required | Always |
| 6 | SD-WAN software licenses (3-year minimum) | If SD-WAN deployed |
| 7 | IPS/IDS + URL filtering + SSL inspection licenses | Always with firewall |
| 8 | OOB console server + cellular modem | site_count > 3 |
| 9 | SBC + PSTN gateway | If voice scope confirmed |
| 10 | Mounting hardware + patch cables + SFP transceivers | Always |
| 11 | **3-year SmartNet / hardware maintenance on every hardware line** | Always — mandatory |
| 12 | **Spares kit: 10% of switches + APs** | Always — mandatory |
| 13 | Carrier circuit provisioning (MPLS/broadband) | If new circuits required |
| 14 | Professional services — deployment + cutover support | Always |

---

## Lead Times and Risk Flags

| Item | Typical Lead Time | Risk Flag Threshold | Notes |
|---|---|---|---|
| **MPLS private circuit (new)** | **12–20 weeks** | Flag if Day 1 < 22 weeks away | **Highest-risk item in any network separation** |
| SD-WAN broadband (new address) | 4–8 weeks | Flag if Day 1 < 10 weeks away | |
| Cisco Catalyst switch (high-end) | 16–26 weeks | Flag if Day 1 < 28 weeks away | Supply chain constraints; order early |
| Firewall appliance (PA/FortiGate) | 8–16 weeks | Flag if Day 1 < 18 weeks away | |
| OOB console server | 2–4 weeks | Flag if Day 1 < 6 weeks away | |

---

## Conveying / Shared / Dedicated Decision Tree

> **This is Chetan's Rule #1:** "Shared or dedicated? If dedicated, is it conveying? If conveying → don't buy. If not conveying → buy net new. If end of life → buy replacement."

```
FOR EACH site:

  STEP 1 — Is the network infrastructure shared or dedicated to this entity?
    SHARED (e.g., used by multiple tenants, MSP-owned, parent company owned):
      → The standalone entity has NO existing equipment to convey
      → Scope = BUY NET NEW for all layers
      → Do not qualify further — go straight to sizing

    DEDICATED (equipment exclusively used by this entity today):
      → Continue to STEP 2

  STEP 2 — Is the dedicated equipment conveying in the deal?
    CONVEYING = equipment transfers to the standalone entity at Day 1
    NOT CONVEYING = equipment stays with seller / MSP / parent

    NOT CONVEYING:
      → Scope = BUY NET NEW for all layers
      → Same as shared — size fresh

    CONVEYING:
      → Continue to STEP 3

  STEP 3 — Is the conveying equipment EOL or EOS?
    EOL = End of Life (no longer sold, support ended)
    EOS = End of Support / End of Service Life (still runs but vendor support contract not available)

    Check against EOL/EOS database for the specific model.

    CONVEYING + ACTIVE (not EOL/EOS):
      → Do NOT generate replacement hardware line items
      → Scope = integration work only:
          * License migration / transfer fees
          * SmartNet / maintenance contract on conveyed hardware (new contract under standalone entity)
          * Configuration changes (professional services)
          * Any missing layer (e.g., firewall conveying but no WAN router → buy WAN router only)

    CONVEYING + EOL/EOS:
      → Generate REPLACEMENT hardware line items (full bundle per component — see SKU Bundles section)
      → Add annotation: "Replacement required — conveyed hardware is EOL/EOS: [model] [EOL date]"
      → recommendation_status = "replace_eol"

  STEP 4 — How many sites?
    total_quantity = quantity_per_site × number_of_sites
    Annotate each line item: quantity_basis = "[qty] per site × [N] sites = [total]"
    NEVER put just a number without this breakdown when site_count > 1

  STEP 5 — Site criticality
    CRITICAL site (HQ, primary DC, hub site, compliance-regulated):
      → Full HA pair for ALL layers (core switch + firewall + WAN router)
      → quantity_per_site doubles for all HA-affected line items
    STANDARD site:
      → HA at firewall layer only (by default)
      → Single WAN router acceptable if bandwidth < 100Mbps
```

---

## Full SKU Bundles — Complete Component Sets

> **Core principle (Chetan's exact words):** "A Cisco router is not one SKU. It always has 8 lines — some are software, some are maintenance. Getting to those 8 lines takes 4–6 weeks. With AI, we get there in 6 hours."

**RULE: Every hardware component MUST generate its complete bundle. Never output a single-line "Cisco Router". Always expand to the full bundle below.**

---

### Bundle 1 — Cisco SD-WAN / WAN Router (8 lines)

Use when: SD-WAN deployment, WAN edge router, branch router for a dedicated/new site.
Reference model: Cisco Catalyst 8300 series (adjust model by bandwidth tier).

| # | Line | SKU Example | Category | Notes |
|---|---|---|---|---|
| 1 | Router chassis (base hardware) | C8300-1N1S-4T2X | Hardware | One per site; HA sites get 2 |
| 2 | IOS XE SD-WAN software license | C8300-SDWAN-LIC | Software License | 3-year term minimum |
| 3 | DNA Advantage / SD-WAN subscription | DNA-SDWAN-A-3Y | SaaS/Subscription | Per-device, co-terminus with hardware contract |
| 4 | SmartNet maintenance (3-year) | CON-SNTP-C83001N | Support Contract | Mandatory on every hardware unit |
| 5 | WAN interface module (per circuit type) | NIM-1GE-CU-SFP or NIM-2T | Interface Module | One per WAN circuit; include one spare |
| 6 | SFP transceiver (per WAN port) | GLC-LH-SMD or SFP-10G-SR | Transceiver | Match fiber type to circuit hand-off |
| 7 | Console cable + power cable | CAB-CONSOLE-USB, PWR-C1-715WAC | Accessories | One set per unit |
| 8 | Rack mount kit | ACS-1900-RM-19 | Accessories | One per unit; confirm rack U availability |

**BOM annotation required:** `ha_role` = "active" or "standby" on each unit line when HA pair.

---

### Bundle 2 — NGFW / Firewall (8–10 lines)

Use when: deploying a next-generation firewall at any site (standalone or HA pair).
Reference model: Fortinet FortiGate 200F / 400F or Palo Alto PA-820 / PA-1410.

| # | Line | SKU Example (Fortinet) | SKU Example (Palo Alto) | Category | Notes |
|---|---|---|---|---|---|
| 1 | Firewall appliance | FG-200F | PA-820 | Hardware | Two units for HA pair |
| 2 | IPS / IDS license | FC-10-0200F-108-02-36 | PAN-PA-820-TP3 | Security License | 3-year; required for NGFW classification |
| 3 | URL filtering license | FC-10-0200F-112-02-36 | PAN-PA-820-URL2-3YR | Security License | 3-year |
| 4 | SSL inspection / deep packet inspection | FC-10-0200F-131-02-36 | Included in TP bundle | Security License | Size appliance at 2× throughput if enabled |
| 5 | Advanced malware protection (AMP/Sandbox) | FC-10-0200F-100-02-36 | PAN-PA-820-DNS-3YR | Security License | Optional but recommended for critical sites |
| 6 | HA peer unit (same model) | FG-200F | PA-820 | Hardware | HA pair only; annotate ha_role = "standby" |
| 7 | Hardware support / FortiCare (3-year) | FC-10-0200F-247-02-36 | PAN-SVC-PREM-820-3YR | Support Contract | One per physical unit |
| 8 | Rack mount kit + power cable | SP-FG200F-RACK | Included | Accessories | |
| 9 | SFP uplinks (to core switch) | SFP-10G-SR (×2 per unit) | SFP-PLUS-SR | Transceiver | Match switch uplink ports |
| 10 | Professional services — firewall policy migration | PS-FW-MIGRATION | — | Services | Scope hours based on ruleset count |

---

### Bundle 3 — LAN Access Switch (5 lines)

Use when: deploying access layer switching (end-user floor switches).
Reference model: Cisco Catalyst 9300-48P (PoE) or Aruba 2930F-48G-PoE+.

| # | Line | SKU Example (Cisco) | SKU Example (Aruba) | Category | Notes |
|---|---|---|---|---|---|
| 1 | Switch chassis | C9300-48P-A | JL260A | Hardware | One per 48 users; stack in pairs |
| 2 | Network advantage license | C9300-48-A | Included | Software License | Required for OSPF, QoS, NetFlow |
| 3 | Stacking cable (if stacked) | STACK-T1-50CM (×2) | J9578A | Accessories | One pair per stack; for 2-switch stacks |
| 4 | SmartNet / Aruba support (3-year) | CON-3SNT-C9300 | H7J35A3 | Support Contract | Per switch chassis |
| 5 | SFP uplink transceivers | SFP-10G-SR (×2) | J9151E (×2) | Transceiver | Two 10G uplinks per switch to distribution |

**PoE annotation required on every access switch line:**
`notes` = "PoE budget: [calculated_load]W / [switch_capacity]W — [headroom]% available"

---

### Bundle 4 — Wireless Access Point (4 lines)

Use when: deploying WiFi coverage at any site (office, warehouse, or outdoor).
Reference model: Cisco Catalyst 9130AXI (indoor) / 9124AXD (outdoor), Aruba AP555.

| # | Line | SKU Example (Cisco) | SKU Example (Aruba) | Category | Notes |
|---|---|---|---|---|---|
| 1 | Access point unit | C9130AXI-B | JZ332A | Hardware | Count = density formula from Sizing Rules |
| 2 | PoE injector (if switch PoE budget full) | AIR-PWRINJ6= | JW629A | Accessories | Include only if switch PoE is over 80% budget |
| 3 | Cloud / controller license | DNA-PREM-AP-3Y | JW635AAE (Aruba Central) | SaaS/Subscription | Per AP, 3-year; do NOT mix on-prem and cloud |
| 4 | Mounting hardware | AIR-AP-BRACKET-2= | JYMQ-0001 | Accessories | Ceiling T-bar or solid ceiling — confirm with facilities |

**Outdoor APs:** replace line 1 with outdoor-rated model (C9124AXD, Aruba AP565); add IP67-rated enclosure line.

---

### Bundle 5 — Distribution / Core Switch (5 lines)

Use when: deploying distribution or core layer switches (sites > 200 users or data center top-of-rack).
Reference model: Cisco Catalyst 9500-24Y4C or Cisco Nexus 93180YC-FX (DC).

| # | Line | SKU Example | Category | Notes |
|---|---|---|---|---|
| 1 | Distribution/core switch chassis | C9500-24Y4C-A | Hardware | One per pair for HA; two for redundant design |
| 2 | Network premier license | C9500-24Y4C-A (license included) or C9500-NW-A | Software License | Required for layer-3 routing, VXLAN |
| 3 | SmartNet (3-year) | CON-3SNT-C9500 | Support Contract | Per chassis |
| 4 | 25G/100G SFP/QSFP transceivers | SFP-25G-SR-S, QSFP-100G-SR4-S | Transceiver | 2× per switch for inter-switch links; 1× per access uplink |
| 5 | Rack mount kit + power cord | — | Accessories | Confirm PDU power type (C13/C19) |

---

### Bundle 6 — SD-WAN / WAN Cisco FortiGate Router (Budget Vendor — 7 lines)

Use when: budget WAN edge, APAC/smaller sites, or Fortinet is the stated vendor standard.
Reference model: FortiGate 200F (WAN) or FortiGate 100F (small branch).

| # | Line | SKU Example | Category | Notes |
|---|---|---|---|---|
| 1 | FortiGate appliance | FG-200F or FG-100F | Hardware | One per site; HA sites get 2 |
| 2 | FortiCare Premium support (3-year) | FC-10-F200F-247-02-36 | Support Contract | Per unit |
| 3 | FortiGuard Enterprise Protection (SD-WAN) | FC-10-F200F-811-02-36 | Security License | Includes IPS, AV, URL, App Control, SD-WAN |
| 4 | WAN interface module / SFP | FG-TRAN-GC or FG-TRAN-SFP+SR | Interface/Transceiver | Per WAN port type |
| 5 | Console cable + power cable | Included / SP-Cable-D9F-C | Accessories | |
| 6 | Rack mount kit | SP-FG200F-RACK | Accessories | |
| 7 | FortiManager license (if centrally managed) | FC-10-FG100-175-02-12 (annual) | Software License | One per deployment if FortiManager in scope |

---

## How to Apply Bundles in a BOM

When a user says "we need routers for 10 sites":

1. Identify the right bundle (e.g., Bundle 1 — Cisco SD-WAN Router)
2. Multiply each line by site count: `quantity = [per-site qty] × 10 sites`
3. Annotate: `quantity_basis = "2 per site × 10 sites = 20"`
4. For HA pair sites: `ha_role` = "active" / "standby" alternating on each unit line
5. Set `order_sequence` = 1 for OOB/console servers, 2 for routers, 3 for switches, 4 for firewalls, 5 for APs, 6 for licenses, 7 for services
6. Tag `price_basis` = "list" until vendor quotes are received; set to "negotiated" after quotes

**Never collapse 8 lines into 1 line.** A BOM with a single "Cisco Router" line will be rejected at the Vendor-Ready BOM Gate above.
| Dark fiber / dedicated wavelength | 16–26 weeks | Flag if Day 1 < 28 weeks away | Initiate immediately |
| Colocation cross-connect | 2–4 weeks | Flag if Day 1 < 6 weeks away | |
| Cisco switches (standard SKU) | 8–14 weeks | Flag if Day 1 < 16 weeks away | |
| Cisco switches (extended config / BTO) | 16–24 weeks | Flag if Day 1 < 26 weeks away | Verify stock with CDW first |
| Fortinet FortiGate appliance | 6–10 weeks | Flag if Day 1 < 12 weeks away | |
| Palo Alto PA-Series appliance | 8–16 weeks | Flag if Day 1 < 18 weeks away | |
| Aruba / Cisco APs | 4–8 weeks | Flag if Day 1 < 10 weeks away | |
| SBC appliance | 6–10 weeks | Flag if Day 1 < 12 weeks away | |
| OOB console server | 2–4 weeks | Flag if Day 1 < 6 weeks away | |
| SD-WAN / firewall software licenses | 1–2 weeks | Low risk — SaaS delivery | |

**Mandatory carrier warning:** If new WAN circuits are required, add this warning to every BOM regardless of Day 1 date:
```json
{
  "severity": "BLOCKING",
  "type": "carrier",
  "message": "Carrier circuit provisioning required. MPLS average 12-20 weeks. Initiate vendor engagement immediately — this is the longest-lead item in any network separation.",
  "field_affected": "WAN circuit line items"
}
```

---

## Vendor Selection Logic

| Scenario | Recommended Channel |
|---|---|
| Total BOM < $250K | CDW or SHI — broad stocking, fast procurement |
| Total BOM $250K–$750K | SHI or PC Connection — negotiate deal-reg discount |
| Total BOM > $750K | Cisco Direct or Fortinet Direct — enterprise pricing with deal-reg |
| Timeline < 10 weeks (urgency) | CDW regardless of value — stocking distributor, fastest fulfillment |
| Any single line item > $50K | Dual-quote mandatory regardless of total BOM value |

Vendor hierarchy (default): **CDW → SHI → PC Connection → Cisco Direct → Fortinet Direct → Aruba/HPE Direct**

---

## BOM Output Format

Follow the standard JSON BOM schema. Required fields for Network & Telecom:

- `bom_maturity`: `"rom"` / `"budgetary"` / `"vendor_ready"` — required on every BOM
- `order_sequence`: 1 = OOB/physical infrastructure; 2 = network hardware; 3 = carrier circuits; 4 = spares; 5 = software/maintenance
- `category`: use `"Network Equipment"`, `"Wireless"`, `"WAN/SD-WAN"`, `"Firewall"`, `"Voice/UCaaS"`, `"OOB Management"`, or `"Connectivity"`
- `eol_flag`: `true` for any SKU with EOS within 3 years of Day 1; `true` for hardware already past EOS (CRITICAL)
- `ha_role`: `"primary"` / `"secondary"` / `"standalone"` — required on every firewall and core switch line item
- `site_name`: required on every hardware line item when site_count > 1; create one line per site per SKU for multi-site BOMs
- `notes`: include PoE budget balance, stack position, HA pair reference, and carrier order reference if known

### Structured Warning Format

Every warning in the `warnings` array must use this structure:

```json
{
  "severity": "BLOCKING | HIGH | MEDIUM | LOW",
  "type": "assumption | lead_time | eol | dual_quote | compliance | carrier",
  "message": "Human-readable description",
  "field_affected": "Which line item, field, or site this affects"
}
```

Severity definitions:
- `BLOCKING`: mandatory input unknown; BOM cannot reach `vendor_ready` until resolved
- `HIGH`: risk that will likely cause Buyer IT rejection if unaddressed
- `MEDIUM`: should be reviewed but does not block approval
- `LOW`: advisory / informational only
