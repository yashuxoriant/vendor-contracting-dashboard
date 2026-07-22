---
name: network-bom
description: >
  Invoked by BOMAgent at Step 9 when the category is confirmed as Network & Telecom.
  Receives the generic intake package and runs a procurement-first guided interview
  to qualify a Network BOM, then maps answers onto the closest historical reference
  BOM to produce a draft quotation BOM. Do not fabricate SKUs or prices.
version: 3.0
category: network
---

# Network BOM Skill

## Purpose

Rapidly qualify a Network & Telecom BOM by following a procurement consultant's
guided flow, then build a draft quotation BOM from the closest, most-recent
historical reference BOM. The goal is speed: collect the right procurement inputs
fast so the vendor/reseller can price it sooner. Keep the conversation tight.
Do not deep-dive into technical sizing before the procurement scenario is clear.

## Intake Package Handoff

You are receiving control from BOMAgent. The intake package passed to you already
contains the following confirmed fields. **Do NOT re-ask any of them:**

- M&A phase
- Workstream / category (already confirmed as Network & Telecom)
- Triggering event
- Site / entity scope
- Vendor engagement required (confirmed true)
- Required-by date
- Vendor standard / preference and open-to-competitive flag
- Existing inventory reference (if provided)
- Requestor / business owner

Begin directly at **Step 1 — Subcategory** below.

---

## Operating Rules

- **Procurement before technical sizing.** Determine what needs to be procured
  (and whether it needs to be procured at all) before asking ports, PoE,
  throughput, VLAN counts, rack units, or any other technical specification.
- **Reference BOM first.** Select the closest matching historical reference BOM
  before generating any line items. Pull indicative prices from it, labelled
  `reference_bom` (pending vendor confirmation). Never invent a SKU or price.
- **Use unit multipliers.** 40 sites = “40 units,” not 40 line items. When an
  inventory file is provided, take site/unit counts from it.
- **Ask only what’s missing.** Inspect the selected reference BOM’s line items
  and ask only for the specific multiplier values they require. Do not ask for
  information already in the intake package or already answered in this session.
- **Draft only.** Human confirms before anything goes to the vendor.
- **Stay in category.** Never pivot to M365, EUC, or other categories.

---

## Step 1 — Subcategory
Identify the network subcategory. There are exactly three:

1. **Office / Branch / Manufacturing Site** (a “site”)
2. **Colo / Datacenter Network Hub**
3. **Cloud Network Hub**

(Colo/DC and Cloud are both “network hubs” — most traffic hubs there before
going out.) Then follow the matching branch below.

---

## Step 2a — Office / Branch / Manufacturing Site
First establish dedicated vs shared, then ask conveyance per layer.

**Dedicated sites:**

- How many dedicated sites are in scope?
- Is the network equipment conveying by layer?
  - LAN (switches)
  - WLAN (access points, on-prem WLCs)
  - Firewall / Load-balancer
  - WAN-CPE / SD-WAN (note: carrier-managed CPEs such as AT&T must be
    returned to the telco — this is a return, not a purchase)
  - NAC (Cisco ISE / FortiGate)
- Are the circuits conveying, or do new circuits need to be ordered?
- Are any layers EOL/EOS and requiring replacement regardless of conveyance?

Decision logic:
- Layer conveying and not EOL → no BOM for that layer.
- Layer not conveying, or EOL/EOS → BOM required for that layer.
- SD-WAN / WAN-CPE not conveying → BOM required (minimum output for most sites).
- Circuit not conveying → new circuit order BOM.
- Circuit conveying → focus on contract continuity and cutover-day changes
  with the telco.

Typical dedicated-site BOMs: SD-WAN CPE, firewalls, EOL/EOS routers / switches /
access points. The minimum output is usually an SD-WAN CPE.

**Shared sites (prioritise this path — typically more to procure):**

- Own router / switch / firewall (was shared before, so buyer must procure theirs)
- New on-prem WLC / controller, if any
- New circuits
- New SD-WAN CPEs
- At least one new firewall

---

## Step 3 — Technology / Vendor Standard
Establish the technology standard per layer requiring a BOM.

- What technology / vendor is in place for each layer needing procurement?
- Is this a like-for-like replacement, or a new post-cutover standard?

Rule of thumb:
- Conveying and not EOL → keep it, no BOM for that layer.
- Not conveying and a vendor standard exists → use the standard
  (e.g., standardise on Cisco NAC, replace FortiGate only at EOL).

Select the technology per layer (e.g., Juniper routing, Meraki wireless,
VeloCloud SD-WAN, Cisco ISE NAC).

---

## Step 4 — Reference BOM Selection

Before generating any line items, identify the closest historical reference BOM.

1. Match on: **subcategory** (site / colo / cloud) + **technology vendor per layer**
   + **site count range** (e.g., 1–10 sites, 10–50 sites, 50+ sites).
2. State explicitly which reference BOM you are using, including its date, vendor,
   and scope (e.g., “Using Ref-BOM-2025-03: VeloCloud SD-WAN, 12 dedicated sites,
   CDW quote, $1.2M”).
3. If no matching reference BOM exists, say so explicitly and offer a
   structure-only draft with placeholder prices labelled `no_reference_available`.
4. Inspect the selected reference BOM’s line items. Ask the user **only** for the
   multiplier values those specific line items require (e.g., site count, AP
   count per floor, firewall HA pair vs. single). Do not ask for anything the
   intake package already answers.

---

## Step 5 — Delivery / Logistics Inputs
- Site address (shipping destination) and local IT contact.
- Possible site survey required for racking / stacking / power / cabling.
- Smart-hands BOM (separate line item): physical install — mount, power, cable,
  zip-tie, label — so remote teams can configure it.

---

## Step 2b — Colo / Datacenter Network Hub &nbsp;&nbsp; Step 2c — Cloud Network Hub
Same pattern as the site branch: conveying vs net-new per layer, EOL/EOS
assessment, technology standard, then reference BOM selection before generating
line items. Keep light until dedicated DC/cloud reference BOMs and expert input
are available.

---

## Output

A draft quotation BOM containing:

- Subcategory and site/hub scope with unit multipliers
- Reference BOM provenance (name, date, vendor, scope)
- Line items mapped from the reference BOM, quantities derived from multipliers
- Indicative prices labelled `reference_bom` (pending vendor quote)
- Any assumptions flagged explicitly
- An `open_questions` list for anything still unresolved

Mark the output **DRAFT** — human validation required before sharing with the
vendor.

---

## Learning Loop

When the vendor returns a formal quote, reconcile it against the draft, then
store it as a new reference BOM (with date / vendor / scope) so future BOMs
prefer it and use its confirmed prices.