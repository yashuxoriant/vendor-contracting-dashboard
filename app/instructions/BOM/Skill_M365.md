# Skill: Microsoft 365 & Power Platform
<!-- Categories: M365 & Power Platform, Microsoft 365 -->
<!-- Invoked by: BOMAgent Step 9 when workstream_category resolves to M365 & Power Platform -->

## Purpose

Produce a complete, vendor-ready BOM for Microsoft 365 licensing, Power Platform, and associated migration services in M&A Day-1 / TSA Exit scenarios.
Covers: M365 license tiers, Exchange/Teams/SharePoint migration, Power BI Premium, Power Apps, Azure AD (Entra ID), and Intune.

---

## 5-Question Intake Flow

Ask all five before generating the BOM:

1. **User count** — How many licensed users total? Any guest/external users or shared mailboxes?
2. **License tier** — M365 E3 or E5? Any users requiring F1/F3 (Frontline Workers)? Is Power BI Premium Per User (PPU) or Premium Per Capacity (P-SKU) needed?
3. **Migration scope** — What workloads are being migrated to the new M365 tenant? (Exchange mailboxes, Teams channels/data, SharePoint sites, OneDrive data?)
4. **Source environment** — Is the source Microsoft Exchange on-premises, another M365 tenant (tenant-to-tenant), Google Workspace, or a hybrid?
5. **Go-live date** — Is this a hard cutover or phased migration? What is the Day 1 date for email and Teams?

---

## License Tier Selection Guide

| Scenario | Recommended License |
|---|---|
| Standard office users, no advanced security | **M365 E3** |
| Users requiring Defender for Endpoint P2, Entra ID P2, Purview DLP | **M365 E5** |
| Frontline / shift workers (manufacturing, retail, field) | **M365 F3** |
| Power BI for < 50 analytical users | **Power BI Pro** (per user) |
| Power BI for > 50 users or embedded scenarios | **Power BI Premium Per User (PPU)** |
| Enterprise BI at scale / shared capacity | **Power BI Premium P1/P2 capacity** |
| Advanced Teams Phone System | Add **Teams Phone Standard** license per user |

---

## Migration Service Sizing

| Migration Type | Tooling | Typical Duration |
|---|---|---|
| Exchange → M365 (cutover/hybrid) | Microsoft FastTrack (free ≥ 150 seats) or BitTitan MigrationWiz | 2–8 weeks |
| Tenant-to-tenant M365 migration | Quest On Demand Migration or BitTitan | 4–16 weeks |
| Google Workspace → M365 | MigrationWiz or Simeon Cloud | 4–12 weeks |
| SharePoint on-prem → SPO | ShareGate or Metalogix | 4–12 weeks |
| Teams data migration | Quest Migration for Teams | 2–6 weeks |

---

## Mandatory BOM Line Items

Every M365 BOM must include:

1. **M365 licenses** — correct tier × user count (include 5% headroom for onboarding buffer)
2. **Power BI licenses** — Per User or Premium tier based on analytical user count
3. **Azure AD (Entra ID) P1 or P2** — P1 if not already included in E3/E5; P2 if PAM or Entra ID Governance is required
4. **Microsoft Intune** — device management (included in E3/E5; list separately if purchased standalone)
5. **FastTrack migration services** — document as $0 line item (Microsoft-funded for ≥ 150 seats) or professional services fee for < 150 seats
6. **Migration tooling licenses** — if third-party tooling required (BitTitan, Quest, ShareGate)
7. **Professional services — migration** — tenant setup, identity federation, mailbox cutover, SPO migration
8. **DNS cutover and MX record change services** — if not handled by internal IT
9. **Year 2 and Year 3 annual license renewal costs** (TCO transparency)
10. **Parallel-run cost** — if source mailbox/Teams environment must stay live during migration (document overlap period)

---

## Key Rules

- **FastTrack eligibility**: Microsoft FastTrack is free for ≥ 150 seats for Exchange, Teams, and SharePoint migrations. Always include as a $0 line item and note eligibility.
- **License transfer (tenant-to-tenant)**: Microsoft does not allow direct license transfer between tenants. New licenses must be procured; flag the old license cancellation date in `notes`.
- **Email coexistence period**: always include a coexistence period cost (routing both tenants' mail) if migration is phased over > 2 weeks.
- **Entra ID (Azure AD) tenant setup**: include new tenant configuration services if the standalone entity needs a new Azure AD tenant.
- **MFA enforcement**: document whether MFA is being enforced at cutover; include Authenticator app rollout in the migration services scope.

---

## Lead Times

| Item | Typical Lead Time |
|---|---|
| M365 license provisioning | 1–3 business days |
| Migration tooling setup | 3–5 business days |
| Exchange/Teams migration (per 1000 mailboxes) | 2–4 weeks |
| SharePoint migration (per TB) | 1–2 weeks |
| New Entra ID tenant setup | 1–2 weeks |

---

## Vendor Hierarchy

Microsoft Direct (CSP) → CDW (Microsoft CSP partner) → SHI → PC Connection

Dual-quote required for any single line item > $50,000 (typically applicable to Premium capacity SKUs).

---

## BOM Output Notes

- `order_sequence`: 5 for all M365 licenses, migration services, and tooling
- `category`: use "M365 License", "Power BI", "Migration Services", "Identity (Entra ID)", or "Intune" as appropriate
- `eol_flag`: flag any users still on Office 2016/2019 perpetual without a path to M365 cloud
- `notes`: include license type (E3/E5/F3), source environment, and FastTrack eligibility status
- Include a `warnings` entry if the migration timeline is < 8 weeks and mailbox count > 500 (high risk of cutover issues)
