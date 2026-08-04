# Skill: Data Center, Colocation & Cloud Infrastructure
<!-- Categories: Data Center / COLO, Cloud Infrastructure, EOL Replacement -->
<!-- Invoked by: BOMAgent Step 9 when workstream_category resolves to Data Center / COLO, Cloud Infrastructure, or EOL Replacement -->

## Purpose

Produce a complete, vendor-ready BOM for data center builds, colocation deployments, and cloud infrastructure in M&A Day-1 / TSA Exit scenarios.
Uses the full 11-phase DC methodology.

---

## 11-Phase Intake and Sizing Flow

You must collect answers for **Phases 1, 2, 3, 4, and 5** before generating the BOM.
Do NOT generate the BOM on the first response — always ask Phase 1 questions first.

### Phase 1 — Scope & Constraints
- Which workloads land in the DC? What stays cloud/SaaS/co-lo?
- Specialised hardware: AS/400, GPU clusters, bare-metal requirements?
- Physical site type: new build, existing DC, co-lo cage?
- Power/cooling constraints and available capacity?
- **HARD Day 1 cutover date** (drives all lead-time calculations)
- Compliance/regulatory constraints: PCI, HIPAA, SOC 2, GDPR?

### Phase 2 — Seller Inventory Assessment
- App-to-server mapping: which apps run where today?
- Conveyed vs. non-conveyed assets (what transfers in the deal)?
- Age, spec, and warranty status of existing hardware
- EOL/EOS hardware → flag immediately for replacement sizing
- Current rack count, peak power draw (kW), cooling load
- Existing network topology and uplink capacities

### Phase 3 — Compute Sizing *(Approval Phase A)*
- Per-application: vCPU, RAM, IOPS, bandwidth, HA requirements
- Virtualisation consolidation ratio: 8:1–15:1 (VMware/Hyper-V)
- **Minimum 3 nodes for HA (N+1); recommend 4+ for live migration headroom**
- Headroom: +20–30% for growth; +15% for backup workloads
- GPU compute: separate sizing for AI/ML workloads
- Output: server count, model, specs, vendor, unit price, extended price

### Phase 4 — Storage Sizing *(Approval Phase B)*
- Tier 1 (NVMe/SSD): databases, ERP, latency-sensitive apps — target < 1 ms
- Tier 2 (SAS/SATA): file shares, archive, VMs — target < 5 ms
- RAID overhead: +20–25% raw vs. usable; mirror vs. parity trade-offs
- Backup sizing: 2–3× primary usable + dedup/compression ratio (2:1–5:1)
- Architecture choice: SAN, NAS, HCI (Nutanix/vSAN), DAS — document rationale
- Output: storage array model, raw/usable capacity, IOPS spec, vendor, price

### Phase 5 — Network Sizing *(Approval Phase C)*
- Layer 2/3 architecture: core, distribution, access tiers
- Top-of-Rack (ToR) switches: 1 per rack minimum; uplinks 10G/25G/100G
- North–south traffic: WAN/DC uplink sizing (MPLS, dark fibre, internet)
- East–west traffic: inter-rack bandwidth for VM live-migration and storage
- Out-of-band (OOB) management network: dedicated or VRF-based
- Firewall: throughput Gbps, CPS, concurrent sessions, VPN tunnels
- Load balancers: VIPs, SSL offload, throughput
- Output: switch models, firewall model, qty, rack placement, price

### Phase 6 — Power & Physical Infrastructure *(Approval Phase D)*
- Total IT load: sum all device TDPs + 20% contingency
- PUE target: 1.4–1.6 (factor into cooling capacity)
- UPS: N+1 configuration; kVA = IT load × 1.25
- PDUs: redundant A+B feeds per rack; horizontal vs. vertical
- Rack count: 2U servers → 40 per 42U rack; allow 30% for cables/patch
- CRAC/CRAH cooling: match to heat load; in-row vs. perimeter
- Generator: size to full DC load + 10% headroom

### Phase 7 — Build the BOM
Order categories:
1. Physical/Racks (`order_sequence=1`): racks, PDUs, cables
2. Networking (`order_sequence=2`): switches, firewalls, load balancers
3. Compute/Storage (`order_sequence=3`): servers, storage arrays
4. Cabling (`order_sequence=4`): fibre, copper, patch panels
5. Software Licenses (`order_sequence=5`): hypervisor, monitoring, backup SW

**Mandatory additions:**
- Maintenance contracts (3–5 yr) on **every** hardware line item
- Spares Kit: 10% of drives, NICs, PSUs

### Phase 8 — EOL & Risk Validation
- Flag any SKU with EOS date < Day 1 + 3 years as **WARNING**
- Flag any SKU already past EOS as **CRITICAL** — must replace
- Dual-quote requirement: any line item > $50K needs two vendor quotes
- Lead times: networking 8–14 weeks, compute 10–18 weeks, storage 12–20 weeks
- Warn if (Day 1 date) − (longest lead time) < today + 2 weeks buffer

### Phase 9 — Pricing & Vendor Strategy
- Preferred vendors: CDW → PC Connection → SHI → Dell Direct → Cisco Direct
- Always use net/street pricing — never list price
- Note when pricing assumes volume/deal-reg discount

### Phase 10 — Order Sequencing & Approval Readiness
- Verify `order_sequence` 1–5 assigned to every line item
- Confirm 3-party approval sign-off list: Buyer IT, Seller IT, SI / JBR
- Identify long-lead items needing PO before final approval (de-risk)

### Phase 11 — Approval Workflow
Sequential with full reset on any change request:
- **Buyer IT** → **Seller IT** → **SI / JBR**
- Any change request by any party restarts from Buyer IT

---

## Mandatory Business Rules

1. Flag EOL/EOS hardware with ⚠️ WARNING and recommend replacement SKU
2. Maintenance contract line for **every** hardware item (3–5 yr minimum)
3. Spares Kit line: 10% of drives, NICs, PSUs
4. Lead-time warning if Day 1 minus longest lead time < today + 2 weeks
5. Dual-quote flag for any single line item > $50K
6. 3-party sequential approval (Buyer IT → Seller IT → SI) is non-negotiable
7. Any change request restarts the entire approval cycle from Buyer IT
8. Never use list price — always net/street pricing
9. Always include `order_sequence` 1–5 on every line item
10. Minimum 3 compute nodes for HA; document consolidation ratio used
11. Do NOT generate the BOM JSON on the first message — ask Phase 1 questions first
12. For Data Center/COLO: collect answers for Phases 1, 3, 4, and 5 before generating

---

## Cloud Infrastructure Variant

When `workstream_category = "Cloud Infrastructure"`:
- Replace physical compute/storage/network with Azure IaaS/PaaS line items
- Include Azure Reserved Instances (1-yr or 3-yr) to reduce cost
- Size ExpressRoute circuit bandwidth or VPN Gateway SKU
- Include landing zone setup services (if applicable)
- Output `order_sequence` = 3 for all cloud compute; 5 for platform services

---

## EOL Replacement Variant

When `workstream_category = "EOL Replacement"`:
- Prioritise identifying EOS/EOL dates from the inventory before anything else
- Always recommend current-gen replacement SKUs
- Flag hardware already past EOS as **CRITICAL** in the `warnings` array
- Generate the BOM immediately — EOL replacements have urgency; do not wait for all Phase 1–6 data
