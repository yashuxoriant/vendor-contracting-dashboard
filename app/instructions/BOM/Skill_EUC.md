# Skill: End User Computing (EUC)
<!-- Categories: End User Computing, EUC, Laptops, Access Points -->
<!-- Invoked by: BOMAgent Step 9 when workstream_category resolves to EUC or Laptops -->

## Purpose

Produce a complete, vendor-ready BOM for end user computing devices and supporting infrastructure in M&A Day-1 / TSA Exit scenarios.
Covers: laptops, desktops, monitors, docking stations, peripherals, MDM/imaging services, and deployment services.

---

## 5-Question Intake Flow

Ask all five before generating the BOM:

1. **User count and role profiles** — How many users total? What role breakdown: Executive, Developer, Standard Office Worker, Call Centre, Warehouse/Field?
2. **Operating system preference** — Windows 11, macOS, or both? Any ChromeOS or Linux requirements?
3. **MDM platform** — Microsoft Intune, Jamf (for Mac), or other? Is the MDM platform being set up fresh or migrated?
4. **Existing assets** — What devices exist today? Which are conveying vs. being replaced? Average age and spec of current fleet?
5. **Day 1 cutover date and procurement timeline** — When do users need devices in hand? How many locations/ship-to addresses?

---

## Role-Based Device Profiles

| Role | Device Profile | Recommended SKU Band |
|---|---|---|
| Executive | 13–14" premium ultrabook, 32 GB RAM, 1 TB SSD | Dell XPS 13/14, Apple MacBook Pro 14", Lenovo ThinkPad X1 Carbon |
| Developer | 14–16", 32–64 GB RAM, 1–2 TB SSD, dedicated GPU optional | Dell Precision 5470, Apple MacBook Pro 16", Lenovo ThinkPad P16s |
| Standard Office | 14–15.6", 16 GB RAM, 512 GB SSD | Dell Latitude 5440/5450, HP EliteBook 845/855, Lenovo ThinkPad E14 |
| Call Centre | Desktop thin client or 15" value laptop, 8–16 GB RAM, 256 GB SSD | Dell Wyse 5070, HP t655, Lenovo ThinkCentre M70q |
| Warehouse / Field | Rugged or semi-rugged, drop-rated, 8 GB RAM, 256 GB SSD | Panasonic Toughbook 55, Dell Latitude 5430 Rugged |

---

## Mandatory BOM Line Items

Every EUC BOM must include:

1. **Laptops/Desktops** — primary device per user (role-matched profile)
2. **Monitors** — 1 per standard office user; 2 for developers and executives (24–27", 1080p or 2K minimum)
3. **Docking Stations** — 1 per office-based user (USB-C/Thunderbolt; brand-matched to device)
4. **Peripherals** — keyboard + mouse per user (wired for call centre; wireless for standard office)
5. **MDM Licenses** — Microsoft Intune (per device) or Jamf Pro (per device, macOS/iOS)
6. **Imaging & Deployment Services** — zero-touch provisioning (Autopilot/DEP); include professional services line
7. **Device Management Setup** — if MDM platform is new: include implementation services (per-platform)
8. **3-year warranty + accidental damage protection** on every device (mandatory — do not omit)
9. **Asset tagging and inventory labelling** (services line item)

---

## Optional Add-Ons (include if applicable)

- **Headsets** — for call centre roles or Teams/Zoom-heavy users (Poly Voyager, Jabra Evolve)
- **Webcams** — if laptops do not have built-in camera ≥ 1080p (rare but check)
- **Power adapters (spares)** — 10% of fleet as spares kit
- **Device lockers/cabinets** — for hot-desk environments (optional services line)
- **Cellular/LTE laptops** — for field users in locations without reliable Wi-Fi

---

## Sizing Rules

- Headcount: procure devices for **confirmed headcount + 5% buffer** for onboarding and breakage
- Monitors: if users are hot-desking, procure monitors for **desk count** not headcount
- MDM licenses: include all employee devices + 10% for contractors/service accounts
- Deployment services: estimate 45 min per standard device; 2 hours per developer device (includes apps install)

---

## Lead Times

| Item | Typical Lead Time |
|---|---|
| Standard laptops (stock SKUs) | 2–4 weeks |
| Configure-to-order laptops | 4–8 weeks |
| Rugged/semi-rugged devices | 6–12 weeks |
| Monitors and peripherals | 1–3 weeks |
| MDM licenses (SaaS) | 1–2 days |
| Deployment services (scheduling) | 2–3 weeks from device receipt |

---

## Vendor Hierarchy

Dell Technologies (direct or CDW) → HP (direct or CDW) → Apple (direct or Apple Business) → Lenovo (CDW/SHI) → Panasonic (rugged, direct)

Dual-quote required for any single line item > $50,000.

---

## BOM Output Notes

- `order_sequence`: 3 for all hardware devices; 5 for licenses and professional services
- `category`: use "Laptops", "Desktops", "Monitors", "Peripherals", "MDM", or "Deployment Services"
- `eol_flag`: set to `true` if existing conveyed devices are > 4 years old or past manufacturer support
- `notes`: include role profile, ship-to location, and zero-touch provisioning method
- Always include a `warnings` entry if Day 1 date minus procurement lead time < today + 2 weeks
