---
name: network-bom
description: >
  Invoke when the user is building a Network & Telecom BOM in an M&A / TSA-exit
  context. Runs a simple guided interview — Category → Subcategory → sequenced
  questions per branch — then maps answers onto the closest recent historical
  reference BOM to produce a draft quotation BOM for the vendor. Claude does this
  end-to-end; there is no backend. Do not fabricate SKUs or prices.
version: 2.0-simple
category: network
---

# Network BOM Skill (Simple)

## Purpose

Rapidly qualify a Network BOM by following an experienced SME's guided flow, then
build a draft **quotation BOM** from the closest, most-recent historical reference
BOM. The goal is speed: collect the right inputs fast so the vendor/reseller can
price it sooner. Keep the conversation tight — do **not** deep-dive into unneeded
technical detail.

## Operating rules

1. **Assume Day-1.** Do not ask about M&A phase. Running a BOM cycle = Day-1.
2. **Stay in the selected category.** If Network is chosen, never show M365 or other
   categories.
3. **Follow the sequence: Category → Subcategory → branch questions.** Ask a few
   focused questions at a time, not a random deep dive.
4. **Reference BOM first.** Pick the closest-matching, most-recent historical BOM;
   pull indicative prices from it (label them reference-based, pending vendor
   confirmation). Never invent a SKU or price.
5. **Use unit multipliers.** 40 sites = "40 units," not 40 spreadsheets. When an
   **inventory file** is provided, take site/unit counts from it.
6. **Read the reference BOM's line items.** Inspect the chosen reference BOM and ask
   the user only for the specific values that drive its quantities/multipliers.
7. **Draft only.** Human confirms before it goes to the vendor.

## Step 1 — Category

Confirm the category is **Network**.

## Step 2 — Subcategory (exactly three)

- **Office / Branch / Manufacturing Site** (a "site")
- **Colo / Datacenter Network Hub**
- **Cloud Network Hub**

(Colo/DC and Cloud are both "network hubs" — most traffic hubs there before going
out.) Then follow the matching branch below.

## Step 3a — Office / Branch / Manufacturing Site

First establish **dedicated vs shared**, then ask conveyance.

**Dedicated sites:**

- How many dedicated sites are conveying?
- Is the network equipment conveying — **LAN, WLAN, Firewall/Load-balancer, WAN-CPE,
  on-prem WLCs, NAC (Cisco ISE / FortiGate)**? (Note: a WAN-CPE may be a **carrier-
  managed CPE** that must be **returned to the telco** — e.g., AT&T — so it's a
  return, not a purchase.)
- Are the circuits conveying?
- Any EOL/EOS replacements to be done?

Decision logic:

- **Replacing SD-WAN / WAN-CPE?** Yes → create a BOM for it. No → focus on EOL/EOS.
- **Circuit not conveying** → focus on new circuit order/BOMs.
- **Circuit conveying** → focus on contract + cutover-day changes via the telco.

Typical dedicated-site BOMs: **SD-WAN CPE, firewalls, and EOL/EOS
routers / switches / access points.** (Minimum is usually an SD-WAN CPE.)

**Shared sites (you buy more — prioritise this path):**

- Own **router / switch / firewall** (shared before, so buy your own)
- New **on-prem controller / WLC**, if any
- New **circuits**
- New **SD-WAN CPEs**
- At least **one new firewall**

## Step 4 — Technology / vendor

- What technology/vendor is in place? Like-for-like replacement, or a **new
  post-cutover standard**?
- Rule of thumb: if conveying and **not** EOL → keep it, no BOM. If not conveying and
  a standard exists → use the standard. (E.g., standardise on Cisco NAC, but replace
  FortiGate only at EOL.)
- Pick the technology per layer (e.g., Juniper, Meraki wireless, VeloCloud SD-WAN).
- **No reference BOM for that technology?** Say so, then offer typical line items
  from comparable vendors: estimate the ~4 key line items, set quantity × number of
  sites, and total it as units.

## Step 5 — Delivery / logistics inputs

- **Site address** (shipping) and **local IT contact**.
- Possible **site survey** for racking / stacking / power / cabling.
- **Smart-hands BOM** (separate): physical install — mount, power, cable, zip-tie,
  label — so remote teams can configure it.

## Step 3b — Colo / Datacenter Network Hub  &  Step 3c — Cloud Network Hub

Same pattern: conveying vs net-new, EOL/EOS, then the hub's networking items, mapped
to the closest reference BOM. (Keep light until DC/cloud reference BOMs and expert
input are available.)

## Output

A draft quotation BOM containing: subcategory, site/hub scope with unit multipliers,
line items mapped from the reference BOM (with reference provenance), indicative
prices labelled `reference_bom` (pending vendor quote), any assumptions, and an
`open_questions` list for anything missing. Mark it **draft — human validation
required** before sharing with the vendor.

## Learning loop

When the vendor returns a formal quote, reconcile it against the draft, then store
it as a new reference BOM (with date/vendor/scope) so future BOMs prefer it and use
its confirmed prices.
