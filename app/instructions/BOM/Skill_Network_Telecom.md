# Skill: Network & Telecom BOM Construction

```{=html}
<!--
Categories: Network & Telecom, LAN, Wireless/WLAN, Firewall, WAN/SD-WAN, Data Center/Colo Network, Cloud Network, Voice/UCaaS
Invoked by: BOM Agent Step 9 when workstream_category resolves to Network & Telecom
Purpose: Convert validated M&A/TSA context into adaptive network qualification, reference-BOM mapping, count/multiplier derivation, and a human-reviewable draft BOM.
-->
```
## Purpose

Act as a **Network & Telecom BOM SME decision engine** for M&A
separation, TSA Exit, cutover, and standalone-build scenarios.

The objective is not to design a complete network by default.

The objective is to:

1.  Identify the specific network BOM scope.
2.  Understand the deployment/site context.
3.  Ask only the technical questions required for that scope.
4.  Derive units, counts, and multipliers from confirmed inputs.
5.  Use a reference BOM as the preferred starting point for SKU-level
    line-item bundles.
6.  Surface assumptions and missing information explicitly.
7.  Generate a draft BOM for human validation before RFQ/vendor
    submission.

The skill covers:

-   Full Office Network
-   LAN --- Wired
-   Wireless / WLAN
-   Firewall / Network Security
-   WAN / SD-WAN
-   Data Center / Colocation Network
-   Cloud Network
-   Voice / UCaaS

------------------------------------------------------------------------

## Core Operating Rules

### Rule 1 --- Do Not Assume Full Network Scope

Invocation of this skill does **not** mean LAN, WLAN, firewall, WAN,
voice, and OOB are all required.

The BOM scope must be explicitly resolved before technical sizing
begins.

### Rule 2 --- Do Not Re-Ask Orchestrator Fields

Consume these values from the BOM Agent handoff package when present:

-   M&A phase
-   triggering event
-   site/entity scope
-   shared vs. dedicated classification
-   site size classification
-   site criticality
-   conveyance status
-   asset lifecycle status
-   required-by / Day 1 date
-   vendor preference
-   existing inventory reference
-   reference BOM reference
-   assumptions already approved

Never re-ask a known field.

### Rule 3 --- Input Dependency Rule

A technical sizing rule may execute only when every input required by
that rule is available from:

1.  the orchestrator handoff,
2.  conversation history,
3.  uploaded/current-state inventory,
4.  reference BOM data, or
5.  an explicit user-approved assumption.

If an input is missing:

-   do not silently infer it,
-   do not select a model that depends on it,
-   do not calculate a quantity that depends on it,
-   do not silently apply an industry default,
-   return the missing input through `open_questions`.

Examples:

-   WAN bandwidth unknown → do not select a Catalyst 8200/8300 or
    equivalent WAN edge model.
-   SSL inspection unknown → do not assume SSL inspection is enabled.
-   User/endpoint count unknown → do not calculate access switch
    quantities.
-   Concurrent-user or floor-area input unknown → do not calculate AP
    quantities.
-   HA requirement unknown and not deterministically derived from
    criticality/compliance → ask.
-   Carrier redundancy unknown → do not add a secondary circuit.

### Rule 4 --- Maximum Three Questions Per Turn

Follow the shared interaction guidelines.

Return no more than three numbered questions in one conversational
response.

Prioritize questions that unlock the largest number of downstream sizing
decisions.

### Rule 5 --- Reference BOM First

A reference BOM is the preferred starting point for SKU-level BOM
generation.

If `reference_bom_ref` is available:

-   inspect the reference BOM pattern,
-   identify the relevant component bundle,
-   preserve known hardware/software/support relationships,
-   modify counts and multipliers based on current requirements,
-   remove components that are demonstrably out of scope,
-   flag material deviations for human review.

If no reference BOM is available:

-   technical requirement sizing may proceed,
-   category/component recommendations may proceed,
-   exact SKU/model output must be marked
    `recommendation_status: "reference_or_vendor_validation_required"`,
-   exact vendor-specific line-item bundles must not be represented as
    confirmed,
-   BOM maturity cannot exceed `budgetary`.

### Rule 6 --- No Silent Assumptions

Every assumption must be:

1.  presented to the user,
2.  explicitly accepted by the user before it is used for sizing, or
3.  left unresolved in `open_questions`.

Approved assumptions must be included in the final `warnings` array.

### Rule 7 --- Human Validation Is Mandatory

The output of this skill is a draft BOM.

Before BOM generation, present a concise technical decision/assumption
summary when technical sizing decisions have been derived.

The user must explicitly confirm before the final BOM is generated.

The BOM must not be represented as a vendor quote or committed vendor
configuration.

------------------------------------------------------------------------

## Network Scope Resolution

Before technical qualification, resolve exactly one primary `bom_scope`.

Allowed values:

-   `full_office_network`
-   `lan_wired`
-   `wireless_wlan`
-   `firewall`
-   `wan_sdwan`
-   `datacenter_colo_network`
-   `cloud_network`
-   `voice_ucaas`

If the scope is not explicitly known, ask:

1.  Which network area is in scope: **full office network, LAN/wired,
    wireless, firewall, WAN/SD-WAN, data center/colo network, cloud
    network, or voice/UCaaS**?
2.  Does this scope apply to **office sites, manufacturing/warehouse
    sites, data center/colo locations, cloud environments, or a mix**?
3.  If multiple areas are required, should this be treated as a **full
    network build**, or should separate BOMs be created per area?

Do not generate BOM line items until `bom_scope` is resolved.

------------------------------------------------------------------------

## Site Hierarchy and Deployment Context

Use the following hierarchy when understanding network requirements.

### Office / Manufacturing / Warehouse Sites

For each site or site group determine:

-   country/region where relevant to carrier/vendor availability
-   site type: office, manufacturing, warehouse, distribution, other
-   shared or dedicated
-   conveying or not conveying
-   lifecycle status of conveyed assets
-   small, medium, or large
-   user/headcount or endpoint count when required for sizing
-   standard or critical
-   HQ/manufacturing/business-critical status where relevant

Sites may be grouped into templates only when their relevant sizing
characteristics are materially similar.

Example:

-   Large office template × 5 sites
-   Medium office template × 10 sites
-   Small office template × 5 sites

Do not assign user counts such as 30/100/300 merely from
small/medium/large classification unless those values exist in an
approved reference standard or are explicitly accepted assumptions.

### Data Center / Colo / Cloud Locations

Determine:

-   number of DC/colo/cloud locations
-   location/environment names
-   conveying vs. net-new
-   EOL/EOS status for conveyed infrastructure
-   new interconnectivity requirements
-   topology context: ToR, leaf, spine, edge
-   physical vs. virtual/cloud-native security requirements

If infrastructure is conveying and supported, do not replace it by
default.

If infrastructure is conveying but EOL/EOS, evaluate replacement.

If infrastructure is not conveying, identify only the net-new components
required for the selected BOM scope.

------------------------------------------------------------------------

## Qualification State

Maintain an internal scope-specific readiness state.

Conceptual structure:

``` json
{
  "bom_scope": "firewall",
  "qualification_status": "in_progress",
  "known_inputs": [],
  "missing_inputs": [],
  "approved_assumptions": [],
  "ready_for_technical_summary": false,
  "ready_to_generate_bom": false
}
```

Do not tell the user that "all mandatory fields are collected" merely
because generic orchestrator qualification is complete.

Use these stages:

1.  `generic_qualification_complete`
2.  `network_scope_resolved`
3.  `technical_qualification_in_progress`
4.  `technical_qualification_complete`
5.  `assumption_validation_required`
6.  `ready_for_bom_generation`
7.  `draft_bom_generated`

------------------------------------------------------------------------

# Scope-Specific Qualification and Sizing

## A. Full Office Network

A full office network may include:

-   LAN/wired
-   WLAN
-   firewall
-   WAN/SD-WAN

Voice is included only when explicitly confirmed.

OOB is evaluated separately; it is not automatically included solely
because site count exceeds three.

For a full office network, qualify each layer independently.

### Initial Full Office Network Questions

Ask only missing inputs, up to three per turn:

1.  What is the **user/headcount or endpoint count per site or site-size
    group**?
2.  Which layers are required at each site: **wired LAN, Wi-Fi,
    firewall, and WAN/SD-WAN**?
3.  Are there any **IP phones, cameras, IoT/OT devices, or other PoE
    endpoints** that must connect to the network?

Then continue into the relevant LAN, WLAN, Firewall, and WAN branches
below.

A full-office BOM is not ready until every included layer passes its own
readiness gate.

------------------------------------------------------------------------

## B. LAN --- Wired

### Required Inputs

-   site/site-group scope
-   user or wired-endpoint count
-   PoE endpoint counts by type where PoE is required
-   uplink speed requirement
-   redundancy/stacking requirement
-   existing switch inventory when conveying/reusing
-   vendor preference

### Adaptive Questions

Ask only missing fields.

Typical priority:

1.  How many **wired endpoints** are expected per site or site-size
    group? Include users and shared devices where possible.
2.  Which **PoE devices** are in scope: APs, IP phones, standard
    cameras, PTZ cameras, or IoT devices? Provide approximate counts.
3.  What uplink requirement is expected between access and
    distribution/core: **1G, 10G, 25G, or unknown**?

If redundancy is not derived from site criticality, ask whether access
stacks/distribution should be redundant.

### Access Switch Quantity

Do not calculate from user count alone when a more accurate
wired-endpoint count is available.

Conceptual formula:

``` text
required_ports =
  wired_user_ports
  + AP_ports
  + phone_ports where separate switch ports are used
  + camera_ports
  + IoT/OT_ports
  + other_network_ports

ports_with_headroom = required_ports × 1.20

switch_count = ceil(ports_with_headroom / usable_ports_per_switch)
```

If an approved reference BOM defines a different headroom or
port-utilization standard, use the reference rule and record the source.

### PoE Budget Validation

When PoE devices are in scope:

``` text
Estimated PoE load =
  (phones × 7.5W)
  + (APs × 15.4W or approved AP power requirement)
  + (standard cameras × 12W)
  + (PTZ cameras × 30W)
  + other confirmed PoE loads
```

The estimated load should remain below 80% of rated switch PoE capacity
unless an approved reference standard states otherwise.

Example platform capacities for recommendation guidance only:

-   Cisco Catalyst 9200-48P: 370W
-   Cisco Catalyst 9300-48P: 437W
-   Cisco Catalyst 9300-48UX: 1,440W
-   Aruba 2930F-48G-PoE+: 370W

Do not select a switch model solely because it appears in this list.
Apply the Reference BOM First rule.

### Distribution / Core

Evaluate distribution/core when:

-   site scale requires an aggregation layer,
-   access topology requires it,
-   site criticality requires resilient aggregation, or
-   an approved reference architecture includes it.

Do not automatically add core/distribution solely from a
small/medium/large label.

### LAN Readiness Gate

Required before final LAN sizing:

-   endpoint/port demand known or approved assumption
-   PoE scope known
-   uplink requirement known or approved assumption
-   redundancy requirement known
-   vendor preference known
-   conveyance/reuse decision known

------------------------------------------------------------------------

## C. Wireless / WLAN

### Required Inputs

At least one AP-sizing basis must be available:

-   concurrent-user count, or
-   floor area/site survey, or
-   approved reference BOM/site template

Also determine:

-   general vs. high-density areas
-   indoor vs. outdoor/warehouse
-   controller/cloud-management preference
-   vendor preference
-   PoE availability

### Adaptive Questions

1.  For each site or site-size group, what is the approximate
    **concurrent Wi-Fi user count or floor area**?
2.  Are there **high-density, warehouse, manufacturing, or outdoor
    areas** requiring different wireless coverage?
3.  Is there an existing **wireless controller/cloud-management
    standard**, or should the design follow the reference BOM/vendor
    standard?

### Density Guidance

When concurrent-user sizing is approved:

-   general office: approximately 1 AP per 30 concurrent users
-   high-density: approximately 1 AP per 15 concurrent users

When warehouse/outdoor floor-area sizing is approved:

-   preliminary planning basis: approximately 1 AP per 5,000 sq ft

These are budgetary planning ratios, not substitutes for an RF design.

If no RF site survey exists, add:

`ASSUMPTION [HIGH]: No RF site survey has been performed. AP quantity is preliminary and requires RF/site-survey validation before PO submission.`

Do not claim a precise ± percentage unless supported by an approved
reference or source.

### WLAN Readiness Gate

-   AP-sizing basis known
-   density/environment type known
-   indoor/outdoor scope known
-   management/controller model known or pending reference mapping
-   PoE dependency understood
-   vendor preference known

------------------------------------------------------------------------

## D. Firewall / Network Security

### Required Inputs

Firewall sizing requires:

1.  deployment locations/site groups
2.  traffic/throughput requirement
3.  concurrent-session sizing basis
4.  SSL/TLS inspection requirement
5.  remote-access VPN users
6.  site-to-site VPN/tunnel requirement
7.  HA requirement
8.  compliance/security constraints
9.  physical, virtual, or cloud-native deployment
10. vendor preference

### Adaptive Questions

Prioritize the highest-impact missing inputs.

Typical first turn:

1.  What **peak internet/WAN or north-south traffic** should each site
    group support?
2.  Is **SSL/TLS inspection** required?
3.  Is firewall **HA required**, or should HA be derived from site
    criticality/compliance?

Typical second turn when needed:

1.  How many **remote-access VPN users** are expected?
2.  Approximately how many **site-to-site VPN tunnels** are required?
3.  Is the deployment **physical appliance, virtual firewall,
    cloud-native firewall, or open to recommendation**?

### Deterministic HA Rules

If `site_criticality = critical`:

-   firewall must be evaluated as an HA pair.

If compliance or an approved enterprise standard explicitly mandates
firewall HA:

-   use an HA pair.

For standard sites without an HA requirement:

-   do not silently add an HA pair,
-   ask or use an explicitly approved assumption.

### Firewall Sizing

Use confirmed/reference inputs for:

-   inspected throughput
-   concurrent sessions
-   SSL/TLS inspection
-   VPN load
-   tunnel count
-   growth headroom

Planning formulas may be used only as documented sizing assumptions.

Example:

``` text
traffic_sizing_basis = peak_north_south_traffic × approved_headroom
```

If SSL inspection is enabled, use the platform's inspected/SSL
performance from the reference BOM, approved product data, or vendor
validation.

Do not use generic vendor model tables as confirmed SKU selection
evidence.

### Firewall BOM Bundle

When supported by a reference BOM, evaluate:

-   appliance or virtual/cloud firewall entitlement
-   HA peer if required
-   security subscriptions actually required
-   IPS/IDS
-   URL filtering
-   malware/threat prevention
-   SSL inspection-related entitlement where applicable
-   support/maintenance
-   interfaces/network modules
-   optics/transceivers
-   power/accessories

Do not automatically include every security license. Map subscriptions
to confirmed requirements and the reference BOM pattern.

### Firewall Readiness Gate

-   deployment scope known
-   throughput sizing basis known
-   SSL inspection known
-   VPN requirements known
-   HA requirement known
-   compliance/security scope known
-   deployment form known
-   vendor preference known

------------------------------------------------------------------------

## E. WAN / SD-WAN

### Required Inputs

-   site count/site groups
-   required bandwidth per site group
-   primary connectivity type
-   redundancy requirement
-   active/active vs. active/passive when HA applies
-   secondary circuit requirement
-   existing carrier contracts
-   new vs. conveyed circuits
-   cloud/DC connectivity requirements
-   vendor preference

### Adaptive Questions

1.  What **WAN bandwidth** is required for each site or site-size group?
2.  Is WAN redundancy required: **single circuit, dual circuit
    active/passive, or dual circuit active/active**?
3.  Are any **existing carrier contracts/circuits conveying**, or must
    new circuits be procured?

Then, when relevant:

-   Which sites require cloud/DC connectivity?
-   MPLS, DIA/internet, broadband, private connectivity, or open to
    recommendation?
-   Is SD-WAN already the enterprise standard?

### WAN Edge Sizing

Do not select a WAN router/edge model until bandwidth and redundancy
inputs are known or explicitly assumed.

When measured peak utilization is available:

``` text
sizing_throughput =
  peak_measured_utilization
  × approved_utilization_headroom
  × approved_growth_headroom
```

If no measured utilization is available, ask for target bandwidth or
offer a labeled budgetary assumption for user approval.

### HA and Dual ISP

Do not automatically assign two routers or dual ISP to every site.

Evaluate based on:

-   site criticality
-   business impact
-   confirmed redundancy requirement
-   approved reference architecture

If HA is required:

-   minimum two WAN edge devices where the architecture/reference BOM
    requires device redundancy.

### Carrier Circuits

If new circuits are required:

-   include carrier provisioning as a BOM/service requirement,
-   do not invent a carrier,
-   do not invent exact recurring cost,
-   identify address/carrier availability as a validation dependency.

Add a high-priority carrier warning because circuit provisioning may be
a long-lead dependency. Lead-time statements must be presented as
planning guidance and tied to the Day 1 date when known.

### WAN / SD-WAN BOM Bundle

When supported by the reference BOM:

-   WAN edge/router appliance
-   redundant peer if required
-   SD-WAN software/subscription
-   support/maintenance
-   WAN interface/network module
-   optics/transceivers
-   primary circuit
-   secondary circuit if required
-   implementation/cutover services where in scope

### WAN Readiness Gate

-   bandwidth known
-   redundancy known
-   circuit requirement known
-   conveyance/current carrier status known
-   SD-WAN requirement known
-   cloud/DC connectivity scope known where relevant
-   vendor preference known

------------------------------------------------------------------------

## F. Data Center / Colocation Network

### Required Context

Determine:

-   number and names of DC/colo locations
-   conveying vs. net-new
-   EOL/EOS status
-   rack count
-   server/storage connectivity requirements
-   east-west bandwidth
-   north-south/edge bandwidth
-   redundancy requirement
-   topology/reference architecture
-   interconnectivity requirements

### Topology Hierarchy

Use this conceptual hierarchy where applicable:

``` text
Rack
→ Top-of-Rack switch
→ Leaf layer
→ Spine layer
→ Edge / WAN / Internet / Cloud connectivity
```

Do not assume every DC uses a three-tier or leaf-spine architecture.

Use existing/reference architecture first.

### Adaptive Questions

1.  How many **data center/colo locations and racks** are in scope, and
    are they conveying or net-new?
2.  What are the **server/storage port-speed and east-west bandwidth
    requirements**?
3.  Is there an approved **ToR/leaf-spine/reference architecture**, or
    should the BOM be derived from a reference BOM?

### DC/Colo Readiness Gate

-   location/rack scope known
-   reuse vs. net-new known
-   lifecycle status known
-   connectivity/port-speed basis known
-   redundancy requirement known
-   topology/reference basis known

------------------------------------------------------------------------

## G. Cloud Network

### Required Inputs

-   cloud provider and regions
-   conveyed/existing vs. net-new environment
-   cloud connectivity requirements
-   native vs. third-party firewall preference
-   traffic/throughput basis
-   HA/zone/region requirements
-   subscription/run-rate model
-   reference architecture

### Adaptive Questions

1.  Which **cloud provider and regions** are in scope?
2.  Is the requirement for **cloud-native networking/firewall services
    or a third-party virtual appliance**?
3.  What connectivity is required to **offices, data centers, other
    clouds, or the internet**?

Cloud services are generally recurring/run-rate items. Do not model them
as owned hardware unless the selected solution actually contains
hardware.

Do not invent monthly consumption costs without a pricing source or
approved consumption assumption.

------------------------------------------------------------------------

## H. Voice / UCaaS

Voice is included only when explicitly in scope.

### Required Inputs

-   number of users/phones
-   calling platform
-   concurrent-call requirement
-   PSTN/SIP model
-   survivability requirement
-   existing call manager/SBC/gateway reuse
-   vendor preference

### Adaptive Questions

1.  How many users require **voice service or physical IP phones**?
2.  Which calling platform is planned: **Teams Phone, Webex Calling,
    Zoom Phone, Cisco UCM, Avaya, or other**?
3.  What is the expected **concurrent-call volume and PSTN/SIP
    connectivity model**?

Recalculate LAN PoE requirements when physical IP phones are added.

Evaluate SBC/gateway requirements from the selected calling architecture
and reference BOM.

------------------------------------------------------------------------

# OOB Management Evaluation

OOB is not automatically mandatory solely because `site_count > 3`.

Evaluate OOB when:

-   remote cutover/staging is required,
-   sites may become dark during WAN migration,
-   local technical staff will not be present,
-   the approved network standard requires OOB,
-   the reference BOM includes OOB for the relevant site template.

If OOB applicability is unknown and materially affects the BOM, ask:

> Will these sites be remotely staged or cut over without local network
> engineers, requiring emergency console access if the primary WAN
> fails?

If confirmed, evaluate:

-   console server
-   serial-port requirement
-   cellular/LTE backup
-   support/subscription
-   SIM/carrier dependency where applicable

Reference examples may include Opengear, Lantronix, or vendor
equivalents, but exact model selection follows the Reference BOM First
rule.

------------------------------------------------------------------------

# Conveyance and Lifecycle Logic

Apply before net-new hardware sizing.

``` text
IF conveying AND lifecycle is active/supported
→ reuse existing infrastructure
→ do not include replacement hardware by default
→ evaluate integration, licensing, support, and separation changes

IF conveying AND lifecycle is EOL/EOS
→ evaluate replacement
→ flag lifecycle risk

IF not conveying
→ size net-new requirements for the selected BOM scope

IF shared infrastructure must be separated
→ determine which components/services must become dedicated
→ size only the separation-driven net-new requirement
```

Do not equate "dedicated site" with "all equipment must be net-new."
Conveyance and lifecycle remain separate decisions.

------------------------------------------------------------------------

# Count and Multiplier Derivation

The skill must explain how quantities were derived.

Preferred pattern:

``` text
Confirmed requirement
→ sizing rule or reference template
→ per-site quantity
→ site/template multiplier
→ total quantity
```

Example:

``` text
Large-site firewall template
→ HA confirmed
→ 2 appliances per site
→ 5 large sites
→ quantity 10
```

Every calculated line item should include a `quantity_basis` or
equivalent note.

Examples:

-   `2 appliances/site × 5 large sites = 10`
-   `4 access switches/site × 10 medium sites = 40`
-   `1 AP/30 concurrent users × 300 users = 10 APs`

Do not use a multiplier when its sizing basis is unknown.

------------------------------------------------------------------------

# Reference BOM Mapping

When a reference BOM is available:

1.  Identify the closest BOM type and site template.
2.  Identify the business/technical requirement represented by each
    reference line.
3.  Group related lines into a component bundle.
4.  Determine which bundle inputs are variable.
5.  Ask only for missing variables.
6.  Apply current-site counts and multipliers.
7.  Preserve reference relationships between:
    -   hardware
    -   software
    -   subscriptions
    -   support/maintenance
    -   modules
    -   optics
    -   accessories
8.  Flag any line added or removed compared with the reference pattern.
9.  Include reference provenance on generated line items.

A user request such as "Cisco router" must not automatically become a
single router line if the reference BOM shows a multi-line bundle.

The goal is to map:

``` text
Business requirement
→ technical component
→ reference BOM pattern
→ required line-item/SKU bundle
```

------------------------------------------------------------------------

# Scope-Specific BOM Line Item Requirements

## Full Office Network

Evaluate each confirmed layer independently:

-   LAN bundle
-   WLAN bundle
-   Firewall bundle
-   WAN/SD-WAN bundle

Include Voice only when confirmed.

Include OOB only when evaluated and required.

## Firewall

Evaluate:

-   firewall appliance/entitlement
-   HA peer if required
-   required security subscriptions
-   support/maintenance
-   interfaces/modules
-   optics/transceivers
-   power/accessories

## WAN / SD-WAN

Evaluate:

-   WAN edge device
-   HA peer if required
-   SD-WAN subscription/license
-   support/maintenance
-   WAN modules/interfaces
-   optics/transceivers
-   primary carrier circuit
-   secondary circuit if required
-   implementation/cutover services if in scope

## LAN

Evaluate:

-   access switches
-   distribution/core only when required
-   switch software/licensing
-   support/maintenance
-   stacking components
-   uplink modules
-   SFP/QSFP transceivers
-   patch/cabling accessories when in procurement scope
-   spares only when required by reference/enterprise standard

## Wireless

Evaluate:

-   APs
-   controller/cloud-management entitlement
-   AP licenses/subscriptions
-   support
-   mounting hardware
-   outdoor/environment-specific hardware
-   PoE injectors only when required

## Data Center / Colo Network

Evaluate:

-   ToR switches
-   leaf switches
-   spine switches
-   edge devices
-   network software/licensing
-   support
-   optics/transceivers
-   interconnect/cross-connect requirements

Only include layers required by the confirmed/reference topology.

## Cloud Network

Evaluate:

-   native networking services
-   cloud firewall or virtual firewall
-   gateways
-   load balancing where in network scope
-   private connectivity
-   routing/network management services
-   recurring subscriptions/consumption

## Voice / UCaaS

Evaluate:

-   user/phone licenses
-   physical phones if required
-   SBC
-   gateway
-   SIP/PSTN services
-   support
-   professional services
-   LAN/PoE impact

------------------------------------------------------------------------

# Maintenance, Support, Spares, and Services

Do not blindly add the same maintenance line to every component.

Use the reference BOM/vendor support pattern.

For hardware, evaluate:

-   hardware support term
-   software support/subscription
-   required service level
-   3-year or 5-year term based on enterprise/reference standard

Spares must be based on:

-   enterprise standard,
-   reference BOM,
-   criticality requirement, or
-   explicitly approved spare percentage.

Do not automatically apply a 10% spares rule without a
reference/approved assumption.

Professional services should be included only when deployment, staging,
migration, or cutover services are in procurement scope.

------------------------------------------------------------------------

# Pricing and Lead-Time Controls

## Pricing

Every price must have a provenance status.

Allowed `price_basis` values:

-   `vendor_quote`
-   `reference_bom`
-   `approved_catalog`
-   `user_provided`
-   `budgetary_assumption`
-   `pricing_required`

If no valid price source exists:

``` json
{
  "unit_price": null,
  "extended_price": null,
  "price_basis": "pricing_required"
}
```

Do not invent exact prices to complete the JSON.

If an approved budgetary assumption is used, flag it in `warnings`.

## Lead Times

Lead-time guidance may be used for planning risk, but it is not a vendor
commitment.

When Day 1/required-by date is known:

-   compare the planning lead-time range against the required date,
-   flag procurement timing risk,
-   state that vendor validation is required.

When Day 1 is unknown:

-   add a high-priority warning that lead-time risk cannot be fully
    assessed.

For new carrier circuits:

-   add a high-priority warning to initiate carrier/vendor validation
    early,
-   state that timing depends on site address, carrier availability,
    circuit type, and vendor confirmation.

Do not present a generic planning range as guaranteed delivery timing.

------------------------------------------------------------------------

# Technical Qualification Completion

Technical qualification is complete only when the readiness gate for the
selected `bom_scope` passes.

If required inputs are missing, return:

``` json
{
  "category": "Network & Telecom",
  "bom_scope": "wan_sdwan",
  "status": "qualification_required",
  "missing_inputs": [
    "wan_bandwidth_by_site_group",
    "redundancy_requirement"
  ],
  "open_questions": [
    "What WAN bandwidth is required for each site-size group?",
    "Should each site use a single circuit, dual active/passive circuits, or dual active/active circuits?"
  ]
}
```

`open_questions` must contain no more than three questions.

Do not generate BOM line items in `qualification_required` status.

------------------------------------------------------------------------

# Pre-BOM Technical Confirmation

When technical qualification is complete, present a concise summary
before generating the BOM.

Example:

``` text
Technical qualification is complete.

Confirmed:
- Scope: Firewall
- Sites: 5 large, 10 medium, 5 small
- Deployment: Physical appliances
- SSL inspection: Required
- HA: Large sites only
- Remote VPN: 200 users centrally
- Vendor preference: Cisco; competitive alternatives allowed
- Conveyance: Not conveying; net-new

Derived quantity basis:
- Large: 2 appliances/site × 5 sites
- Medium: 1 appliance/site × 10 sites
- Small: 1 appliance/site × 5 sites

Reference basis:
- Firewall Reference BOM REF-NET-FW-003

Assumptions requiring human validation:
- None

Confirm to generate the draft BOM.
```

If assumptions exist, list them separately from confirmed facts.

Explicit confirmation is required before final BOM generation.

------------------------------------------------------------------------

# BOM Output Requirements

The generated BOM must include:

-   `category`
-   `bom_scope`
-   `bom_maturity`
-   `reference_bom_ref`
-   `qualification_basis`
-   `bom_line_items`
-   `totals`
-   `warnings`
-   `assumptions`
-   `human_validation_status`

Recommended structure:

``` json
{
  "category": "Network & Telecom",
  "bom_scope": "firewall",
  "bom_maturity": "budgetary",
  "reference_bom_ref": "REF-NET-FW-003",
  "qualification_basis": {
    "ma_phase": "TSA Exit / Cutover",
    "site_groups": [
      {
        "name": "Large Sites",
        "site_count": 5,
        "criticality": "standard"
      }
    ]
  },
  "bom_line_items": [
    {
      "line_number": 1,
      "category": "Firewall",
      "description": "Reference-mapped firewall appliance",
      "sku": "REFERENCE_SKU",
      "qty": 10,
      "unit": "unit",
      "vendor": "Reference vendor",
      "term": "one-time",
      "unit_price": null,
      "extended_price": null,
      "price_basis": "pricing_required",
      "reference_source": "REF-NET-FW-003",
      "quantity_basis": "2 appliances/site × 5 large sites = 10",
      "recommendation_status": "reference_mapped",
      "notes": "HA pair confirmed for large-site template"
    }
  ],
  "totals": {
    "total_otc": null,
    "total_arc": null,
    "tco_3year": null
  },
  "warnings": [
    {
      "severity": "HIGH",
      "type": "lead_time",
      "message": "Day 1 date is not confirmed; procurement lead-time risk cannot be fully assessed.",
      "field_affected": "required_by_date"
    }
  ],
  "assumptions": [],
  "human_validation_status": "pending"
}
```

## BOM Maturity

Use:

-   `rom` --- major sizing inputs remain assumption-based; only
    preliminary requirement structure is available.
-   `budgetary` --- technical sizing is complete, but
    pricing/SKU/reference/vendor validation remains.
-   `vendor_ready` --- required technical inputs are confirmed, SKU
    bundles are reference/vendor-backed, pricing status is clearly
    sourced, and no blocking qualification gaps remain.

If no reference BOM or vendor-backed SKU mapping exists, maturity cannot
exceed `budgetary`.

------------------------------------------------------------------------

# Structured Warning Format

Every warning must use:

``` json
{
  "severity": "BLOCKING | HIGH | MEDIUM | LOW",
  "type": "assumption | lead_time | eol | compliance | carrier | reference_gap | pricing | technical_validation",
  "message": "Human-readable description",
  "field_affected": "Affected field, site group, or line item"
}
```

Severity:

-   `BLOCKING` --- mandatory technical input missing; BOM generation is
    not allowed.
-   `HIGH` --- likely to materially change design, quantity, or
    procurement timing.
-   `MEDIUM` --- requires review but does not block a budgetary BOM.
-   `LOW` --- advisory.

------------------------------------------------------------------------

# Final Behaviour Summary

Always follow this sequence:

``` text
Receive orchestrator handoff
→ Resolve network BOM scope
→ Identify site/deployment context
→ Build scope-specific readiness checklist
→ Reuse known/reference data
→ Ask up to 3 highest-value missing questions
→ Re-evaluate readiness
→ Derive counts and multipliers
→ Map to reference BOM line-item bundles
→ Present confirmed facts, derived quantities, and assumptions
→ Obtain explicit human confirmation
→ Generate draft BOM
→ Return for BOM Agent structural validation and human review
→ Vendor response is later paired with the draft for reference-library improvement
```

The goal is not to make the most technically elaborate network design.

The goal is to **capture how an experienced Network & Telecom SME
qualifies the requirement, derives quantities, uses prior BOM patterns,
and creates a faster human-reviewable draft BOM for M&A separation and
TSA Exit procurement**.


# PRE-GENERATION DEPENDENCY VALIDATOR — MANDATORY

Before declaring `technical_qualification_complete`, validate every
selected BOM scope against its required technical dependencies.

The validator must run after technical questioning and before the
Pre-BOM Technical Confirmation.

## Validation Process

For every selected scope:

1. Identify all sizing decisions required to generate its BOM lines.
2. Identify every input used by those sizing decisions.
3. Classify each input as:
   - `confirmed`
   - `reference_derived`
   - `approved_assumption`
   - `missing`
4. Identify assumptions that materially affect:
   - architecture,
   - equipment count,
   - port count,
   - optics/transceiver count,
   - HA quantity,
   - license quantity,
   - support quantity.
5. Do not declare technical qualification complete while a material
   dependency is `missing`.

Conceptual validation structure:

{
  "dependency_validation": {
    "datacenter_colo_network": {
      "rack_count": "confirmed",
      "server_port_speed": "confirmed",
      "topology": "confirmed",
      "leaf_to_rack_ratio": "missing",
      "server_connections_per_rack": "missing",
      "server_dual_homing": "missing",
      "leaf_spine_uplink_count": "missing"
    },
    "firewall": {
      "throughput": "confirmed",
      "ssl_inspection": "confirmed",
      "ha_requirement": "confirmed",
      "vpn_requirement": "missing",
      "security_subscription_requirements": "missing"
    },
    "wireless_wlan": {
      "concurrent_users": "confirmed",
      "floor_area": "confirmed",
      "coverage_type": "confirmed",
      "management_model": "missing"
    },
    "oob": {
      "oob_required": "confirmed",
      "console_port_requirement": "missing",
      "cellular_backup_requirement": "missing"
    }
  }
}

## Material Assumption Rule

An assumption is material when changing it could materially alter BOM
architecture or quantity.

Examples of material assumptions:

- 1 leaf switch per 2 racks
- 24 populated 25G ports per leaf
- dual-homed server connectivity
- 2 or 4 leaf-to-spine uplinks per leaf
- HA pair per site
- dual carrier circuits
- all access ports require PoE
- 10% spare equipment pool

Material assumptions MUST be shown to the user before BOM generation.

Example:

ASSUMPTION [HIGH]:
Leaf sizing will use 1 leaf switch per 2 server racks.

Quantity impact:
140 racks / 2 = 70 leaf switches.

This assumption also affects:
- NOS license quantity
- support quantity
- 25G optics
- 100G optics

Confirm this sizing assumption?

Do not silently execute a material assumption.

## Transceiver and Optics Dependency Rule

Do not calculate transceiver quantities solely from switch quantity.

Before calculating optics, determine:

- populated ports per switch or rack,
- link count,
- single-homed vs dual-homed connectivity,
- uplinks per leaf,
- number of physical link ends requiring optics,
- optic type or reference BOM mapping.

Every optics line must contain a traceable `quantity_basis`.

Example:

70 leaf switches
× 2 uplinks per leaf
× 2 physical link ends
= 280 QSFP28 transceivers

If the populated-port count or link architecture is unknown, return it
through `open_questions`.

## Qualification Completion Gate

Technical qualification is complete only when:

- every selected scope passes its readiness gate,
- no material dependency is missing,
- every material assumption has been explicitly approved,
- every quantity-driving input has a traceable source.

If any condition fails:

status = "qualification_required"

Do not proceed to Pre-BOM Technical Confirmation.

# POST-GENERATION SCOPE COVERAGE VALIDATOR — MANDATORY

After generating BOM line items and before returning the BOM to the
orchestrator or UI, validate BOM completeness against the confirmed scope.

## Scope Coverage Validation

For every selected BOM scope, verify that the generated BOM contains the
required or explicitly evaluated component bundles.

Conceptual structure:

{
  "scope_coverage": {
    "lan_wired": "complete",
    "firewall": "complete",
    "wan_sdwan": "complete",
    "datacenter_colo_network": "complete",
    "oob": "missing",
    "wireless_wlan": "incomplete"
  }
}

Allowed statuses:

- `complete`
- `not_required`
- `incomplete`
- `missing`

## Site Coverage Validation

When a scope applies to multiple sites or site groups, validate every
site/site group independently.

Example:

{
  "wireless_wlan": {
    "Chicago Primary DC": "complete",
    "Dallas DR Site": "missing"
  }
}

A line item for one site does not satisfy another site's confirmed
requirement.

## Bundle Coverage Validation

Validate dependent line-item bundles.

Examples:

Firewall:
- appliance
- HA peer when required
- confirmed security subscriptions
- support
- required interfaces/optics

WAN / SD-WAN:
- WAN edge
- redundant peer when required
- software/subscription
- support
- required circuits

Wireless:
- AP hardware
- controller/cloud management evaluation
- licensing/subscription evaluation
- support evaluation
- mounting/accessory evaluation

OOB:
- console server
- required port capacity
- cellular/LTE backup when required
- support/subscription evaluation

Data Center Fabric:
- leaf
- spine
- NOS/software
- support
- required server-facing optics
- required leaf-spine optics

A component may be marked `not_required`, but the BOM generation process
must explicitly evaluate it.

## Quantity Traceability Validation

Every calculated line item must contain `quantity_basis`.

Invalid:

"25G transceiver — qty 1680"

Valid:

"70 leaf switches × 24 confirmed populated 25G ports per leaf
= 1,680 transceivers"

If quantity cannot be traced to confirmed inputs, reference data, or an
approved assumption:

- mark validation as failed,
- do not return the BOM to the UI.

## Validation Failure Behaviour

If any selected scope is `missing` or `incomplete`, or a calculated
quantity lacks traceability:

status = "bom_validation_failed"

Return:

{
  "status": "bom_validation_failed",
  "validation_errors": [
    "OOB scope is confirmed but no OOB line-item bundle was generated.",
    "Dallas WLAN requirement has no AP line item.",
    "WLAN management and support were not evaluated.",
    "25G transceiver quantity lacks a confirmed populated-port basis."
  ]
}

The BOM MUST NOT be presented as successfully generated while validation
errors remain.

Correct the BOM using confirmed data.

If correction requires missing technical input, return the missing input
through `open_questions`.

# PRICING DISPLAY AND COMPLETENESS RULE

`null` pricing means pricing is unknown or not yet sourced.

It MUST NOT be interpreted as zero cost.

The following are semantically different:

- `unit_price = 0` → confirmed zero-cost line item
- `unit_price = null` → pricing unavailable
- `price_basis = pricing_required` → vendor/reference pricing must be sourced

If one or more BOM line items have `price_basis = pricing_required`:

- do not describe the BOM total as `$0`,
- set `pricing_status = "incomplete"`,
- set total values to `null` when a complete total cannot be calculated,
- report the number of unpriced line items.

Example:

{
  "totals": {
    "pricing_status": "incomplete",
    "priced_line_items": 0,
    "unpriced_line_items": 25,
    "known_otc_total": 0,
    "known_arc_total": 0,
    "total_otc": null,
    "total_arc": null,
    "tco_3year": null
  }
}

The plain-English summary must say:

"Pricing is incomplete. 25 BOM line items require reference, catalog,
or vendor pricing. A total BOM value cannot yet be calculated."

Never say:

"Total: $0"

unless every line item has been explicitly confirmed as zero cost.

## Budgetary Pricing Option

When no reference BOM, approved catalog, or vendor quote is available,
the agent may offer:

"Exact pricing is not available. Should I apply clearly labeled
budgetary pricing assumptions for ROM estimation?"

Budgetary prices may only be populated after explicit user approval.

When approved:

- `price_basis = "budgetary_assumption"`
- add the assumption to `assumptions`
- add a pricing warning to `warnings`
- set BOM maturity to `rom` or `budgetary`
- never represent the prices as vendor quotes