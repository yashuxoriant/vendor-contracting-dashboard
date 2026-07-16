# Skill: Identity & Security
<!-- Categories: Cybersecurity, Identity & Security, Security -->
<!-- Invoked by: BOMAgent Step 9 when workstream_category resolves to Cybersecurity, Identity & Security, or Security -->

## Purpose

Produce a complete, vendor-ready BOM for cybersecurity and identity infrastructure in M&A Day-1 / TSA Exit scenarios.
Covers: NGFW, EDR/XDR, SIEM, PAM, IAM/Identity, Email Security, DLP, and Endpoint Protection.

---

## 5-Question Intake Flow

Ask all five before generating the BOM:

1. **Endpoint count and user base** — How many endpoints (laptops, servers, mobile) and users will be in scope for the standalone entity?
2. **Compliance requirements** — Which frameworks apply? (PCI-DSS, HIPAA, SOC 2, ISO 27001, GDPR, NIST CSF, CMMC?)
3. **Current security toolset** — What security tools are in use today? Which are conveying vs. being replaced?
4. **SIEM log volume and data sources** — Estimated log ingestion per day (GB/day)? What sources: AD, firewalls, cloud, endpoints?
5. **Cloud vs. on-premises preference** — Cloud-native SaaS preferred, or on-prem/hybrid deployment required?

---

## Mandatory Security Stack Components

Every Security BOM must address all of the following unless explicitly documented as out of scope:

### Perimeter & Network Security
- **NGFW (Next-Generation Firewall)**: Palo Alto PA-Series, Fortinet FortiGate, or Cisco Firepower
  - HA pair mandatory for production environments; size throughput at 2× peak + 30% headroom
  - Include IPS, URL filtering, SSL inspection, and App-ID licenses
- **Web Application Firewall (WAF)**: if web-facing applications exist in scope

### Endpoint Detection & Response
- **EDR/XDR**: CrowdStrike Falcon, Microsoft Defender for Endpoint, or SentinelOne
  - Size per endpoint count; include server license tier separately from workstation tier
  - 1-year minimum license term; 3-year recommended for cost optimisation

### Identity & Access Management
- **PAM (Privileged Access Management)**: CyberArk, BeyondTrust, or Thycotic
  - Size per number of privileged accounts (typically 5–15% of total user count)
- **MFA/SSO**: Microsoft Entra ID (Azure AD) or Okta
  - Per-user licensing; include all employees + external contractors in scope

### Security Operations
- **SIEM**: Microsoft Sentinel, Splunk, or IBM QRadar
  - Size ingestion tier based on GB/day estimate
  - Include 90-day hot retention + 1-year cold retention storage
- **SOAR** (optional): include if SOC team > 3 analysts

### Email & Collaboration Security
- **Email Security Gateway**: Proofpoint, Mimecast, or Microsoft Defender for Office 365 P2
  - Per-user licensing; include both inbound filtering and outbound DLP
- **Anti-phishing / BEC protection**: mandatory if M365 is in scope

### Data Protection
- **DLP (Data Loss Prevention)**: Purview DLP (if M365), Forcepoint, or Digital Guardian
  - Only include if compliance framework (PCI, HIPAA, GDPR) requires it or user explicitly requests

---

## Sizing Rules

| Component | Sizing Basis |
|---|---|
| NGFW throughput | 2× peak measured traffic + 30% headroom |
| EDR licenses | 1 per endpoint (workstation + server counts separate) |
| PAM accounts | 10% of total user count as baseline; adjust per audit findings |
| SIEM ingestion | Measure or estimate GB/day; add 25% headroom |
| MFA/SSO | 1 license per user + 10% headroom for contractors/service accounts |

---

## Compliance-Specific Add-Ons

| Framework | Mandatory Additional Line Items |
|---|---|
| PCI-DSS | WAF, file integrity monitoring (FIM), vulnerability scanner |
| HIPAA | Encrypted endpoint backup, audit logging with 6-yr retention |
| SOC 2 | Vulnerability management platform, penetration test (services line) |
| GDPR | DLP, data classification tooling |
| CMMC | DoD-approved SIEM, CUI boundary enforcement tools |

---

## Lead Times

| Item | Typical Lead Time |
|---|---|
| NGFW hardware (PA/Fortinet) | 6–12 weeks |
| EDR/XDR licenses (SaaS) | 1–2 weeks |
| PAM software + implementation | 4–8 weeks |
| SIEM implementation (Sentinel/Splunk) | 4–10 weeks |
| MFA/SSO provisioning | 1–3 weeks |

---

## Mandatory BOM Line Items

Every Security BOM must include:
1. NGFW appliance(s) or virtual license
2. EDR/XDR endpoint licenses (workstation + server tiers)
3. MFA/SSO per-user licenses
4. SIEM ingestion tier license + storage
5. Email security per-user license
6. PAM license (if privileged accounts in scope)
7. Professional services — implementation and configuration
8. **3-year maintenance/support on every hardware line item**
9. Annual renewal line items for all SaaS licenses (Year 2 + Year 3)

---

## Vendor Hierarchy

Palo Alto Networks → CrowdStrike → Microsoft (Sentinel/Defender) → Fortinet → SentinelOne → Okta → CyberArk

Dual-quote required for any single line item > $50,000.

---

## BOM Output Notes

- `order_sequence`: 2 for hardware appliances; 5 for licenses and professional services
- `category`: use "Cybersecurity", "Identity", "Endpoint Protection", or "SIEM" as appropriate
- `eol_flag`: flag any appliance with EOS within 3 years of Day 1
- Always include a `warnings` entry if any compliance framework requirement is not covered by the BOM
