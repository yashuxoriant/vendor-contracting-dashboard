# Skill: Applications
<!-- Categories: Applications -->
<!-- Invoked by: BOMAgent Step 9 when workstream_category resolves to Applications -->

## Purpose

Produce a complete, vendor-ready BOM for application licensing, migration services, and application infrastructure in M&A Day-1 / TSA Exit scenarios.
Covers: commercial off-the-shelf (COTS) software licenses, SaaS subscriptions, application migration services, integration middleware, and custom application hosting.

---

## 5-Question Intake Flow

Ask all five before generating the BOM:

1. **Application inventory** — What applications are in scope? Which are conveying from the seller, which need new licensing, and which are being replaced?
2. **User counts per application** — How many named or concurrent users per application? (Drives license tier selection.)
3. **Hosting model** — On-premises (server-based), cloud-hosted (IaaS), or SaaS? Any hybrid?
4. **Integration requirements** — Are there integrations between applications that need to be rebuilt or re-configured at cutover (e.g., ERP ↔ HR, CRM ↔ email)?
5. **Day 1 cutover date and TSA exit timeline** — Which applications must be live on Day 1? Which can run under TSA for a period?

---

## Application Categories and License Types

| Category | Typical License Model | Notes |
|---|---|---|
| ERP (SAP, Oracle, D365) | Named user + module licenses | Include implementation/migration services |
| CRM (Salesforce, HubSpot) | Per-user/seat annual subscription | Include data migration services |
| HR/Payroll (Workday, ADP) | Per-employee annual subscription | Include parallel-run cost during cutover |
| ITSM (ServiceNow, Jira) | Per-agent or per-user annual sub | Include configuration/migration services |
| Finance (NetSuite, QuickBooks) | Per-user or entity-based | Include chart-of-accounts migration |
| Middleware / Integration (MuleSoft, Azure Integration) | Per-API or consumption-based | Include redesign services for broken integrations |
| Custom/bespoke apps | Infrastructure hosting + support contract | Assess lift-and-shift vs. replatform cost |

---

## Mandatory BOM Line Items

Every Applications BOM must include:

1. **Software licenses** — for each application in scope (correct user count + tier)
2. **Annual renewal costs** — Year 2 and Year 3 subscription costs (TCO transparency)
3. **Data migration services** — for each application requiring data transfer at cutover
4. **Integration re-configuration services** — for each broken integration at cutover
5. **Parallel-run overlap cost** — if application must run under TSA while standalone is stood up (document TSA period cost as a line item)
6. **Training services** — if the application is new to end users (estimate hours × rate)
7. **Vendor support contracts** — Premier/Enhanced support for mission-critical applications (separate from base license)

---

## Risk and Compliance Flags

- **TSA dependency**: any application still running under seller's license at Day 1 must be flagged as a TSA risk with the TSA exit date
- **Vendor lock-in**: single-vendor dependency for critical business processes should be flagged in `warnings`
- **Data residency**: if applications process personal data (GDPR, HIPAA), note data residency requirements in `notes`
- **License audit risk**: if conveying software licenses, document the transfer mechanism and vendor approval status

---

## Lead Times

| Item | Typical Lead Time |
|---|---|
| SaaS license provisioning | 1–5 business days |
| Enterprise perpetual license transfer | 2–6 weeks (vendor approval required) |
| ERP/CRM implementation services | 8–24 weeks |
| Data migration services | 4–16 weeks (depends on data volume) |
| Custom app re-hosting | 4–12 weeks |

---

## Vendor Hierarchy (by category)

- ERP: SAP → Oracle → Microsoft (D365)
- CRM: Salesforce → Microsoft (D365 Sales) → HubSpot
- ITSM: ServiceNow → Atlassian (Jira) → Freshservice
- Integration: MuleSoft → Azure Integration Services → Dell Boomi
- Hosting (custom apps): Azure → AWS → on-prem (if mandatory)

---

## BOM Output Notes

- `order_sequence`: 5 for all software licenses, subscriptions, and services
- `category`: use "ERP License", "CRM License", "SaaS Subscription", "Migration Services", "Integration Services", or "Training"
- `eol_flag`: set to `true` if the application version in use is past vendor support end date
- `notes`: include license type (named/concurrent/entity), TSA dependency status, and data residency requirement
- Include a `warnings` entry for every TSA-dependent application listing the TSA exit date
