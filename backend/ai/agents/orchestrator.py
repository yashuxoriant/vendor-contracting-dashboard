"""
BOM Orchestrator — rule-based fallback only.
_rule_based() and _build_template_bom() are called by the LangGraph rule_fallback node
when the LLM returns an empty response.
"""
import logging
import json
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BOMOrchestrator:
    """
    Provides rule-based BOM generation used as a fallback when the LLM is unavailable.
    """

    def _rule_based(self, category: str, phase: int, message: str, user_turns: int = 0) -> str:
        """
        Rule-based fallback when AI is unavailable.
        - Phase 1 questions first turn (user_turns == 0).
        - Phase 2 questions second turn (user_turns == 1) for DC/COLO; other cats skip to BOM.
        - Explicit creation intent at ANY turn → generate immediately.
        - After user has answered 2+ rounds (user_turns >= 2) → generate BOM.
        """
        import re

        msg = message.lower()

        # ── Detect project name from message ─────────────────────────────
        project_map = {
            "panasonic": "Panasonic", "idemia": "Idemia", "tenneco": "Tenneco",
            "honeywell": "Honeywell", "pwc": "PwC", "cisco": "Cisco",
            "microsoft": "Microsoft", "oracle": "Oracle", "aon": "Aon",
        }
        project = next((v for k, v in project_map.items() if k in msg), "New Project")

        # ── Detect explicit BOM creation intent ──────────────────────────
        create_pat = re.compile(
            r"\b(create|build|generate|make|prepare|draft|give me|show me)\b.{0,30}\bbom\b"
            r"|\bnew bom\b|\bgenerate bom\b|\bjust create\b|\bskip\b.{0,20}\bquestion",
            re.I,
        )
        skip_pat = re.compile(r"\bskip\b|\bcreate.*now\b|\bgenerate.*now\b|\bjust.*create\b", re.I)
        strong_intent = bool(create_pat.search(msg))
        skip_questions = bool(skip_pat.search(msg))

        # Phase questions — advance through phases based on user_turns so answers are recognised
        phase_questions = {
            1: (
                f"I'll help you build a **{category}** BOM for **{project}**.\n\n"
                "**Phase 1 — Scope & Constraints**\n\n"
                "1. What is the Day 1 cutover date for this project?\n"
                "2. How many racks / physical sites are in scope?\n"
                "3. Are there any specialized hardware requirements (GPU, AS400, bare metal)?\n\n"
                "*Or say **\"skip questions\"** to generate a template BOM immediately.*"
            ),
            2: (
                f"Thanks — noted for **{project}**.\n\n"
                "**Phase 2 — Seller Inventory**\n\n"
                "1. How many servers are being conveyed from the seller?\n"
                "2. Are any running EOL operating systems (Windows Server 2012 or older)?\n"
                "3. What is the current rack count and peak power draw per rack?\n\n"
                "*Or say **\"skip questions\"** to generate a template BOM now.*"
            ),
            3: (
                "**Phase 3 — Compute Sizing**\n\n"
                "1. How many vCPUs does the largest workload require?\n"
                "2. What is the total RAM requirement across all workloads?\n"
                "3. Is VMware or Hyper-V the hypervisor?\n\n"
                "*Or say **\"skip questions\"** to generate a template BOM now.*"
            ),
        }

        # Generate BOM if user explicitly skips, answered 3+ turns, or phase advanced past 3
        if skip_questions or user_turns >= 3 or phase >= 4:
            bom = self._build_template_bom(category, project)
            bom_json = json.dumps(bom, indent=2)
            item_count = len(bom["line_items"])
            total = bom.get("total_value", sum(
                i.get("qty", 1) * i.get("unit_price", 0) for i in bom["line_items"]
            ))
            note = (
                "\n\n> **Note:** Live AI is currently unavailable — this BOM uses "
                "industry-standard templates. Once AI is configured (add `OPENAI_API_KEY` "
                "or `ANTHROPIC_API_KEY` to backend `.env`), responses will be fully "
                "tailored to your specific requirements."
            )
            return (
                f"I've built a **{category}** BOM for **{project}** "
                f"using industry-standard templates.\n\n"
                f"The BOM contains **{item_count} line items** "
                f"totalling **${total:,.0f}**.\n\n"
                f"Review the items in the right panel. You can ask me to:\n"
                f"- Add or remove specific items\n"
                f"- Adjust quantities or pricing\n"
                f"- Change vendors\n"
                f"- Export or save the BOM\n"
                f"{note}\n\n"
                f"```json\n{bom_json}\n```"
            )

        # Map user_turns to the next phase: 0->Phase1, 1->Phase2, 2->Phase3
        effective_phase = user_turns + 1
        return phase_questions.get(
            effective_phase,
            f"Tell me more about your **{category}** requirements, or say "
            f"**\"skip questions\"** to generate a complete template now.",
        )

    # ── Template BOM builder (rule-based, no AI needed) ───────────────────

    def _build_template_bom(self, category: str, project: str) -> dict:
        """Return a vendor-ready template BOM dict for the given category."""
        templates = {
            "Data Center / COLO": [
                {"description": "Dell PowerEdge R750 Server (2x Xeon Gold, 512GB RAM)",
                 "category": "Compute", "qty": 8, "unit_price": 28500, "vendor": "Dell Technologies"},
                {"description": "NetApp AFF A400 All-Flash Storage Array (50TB raw)",
                 "category": "Storage", "qty": 2, "unit_price": 125000, "vendor": "NetApp"},
                {"description": "Cisco Nexus 93180YC-FX Switch (48x25G + 6x100G)",
                 "category": "Network", "qty": 4, "unit_price": 18750, "vendor": "Cisco"},
                {"description": "Cisco ASR 1002-X Edge Router",
                 "category": "Network", "qty": 2, "unit_price": 22000, "vendor": "Cisco"},
                {"description": "APC Smart-UPS SRT 10kVA UPS",
                 "category": "Power & Physical", "qty": 4, "unit_price": 9800, "vendor": "APC by Schneider"},
                {"description": "42U Server Rack Cabinet with Cable Management",
                 "category": "Power & Physical", "qty": 8, "unit_price": 3200, "vendor": "Panduit"},
                {"description": "VMware vSphere Enterprise Plus (per CPU, 3-yr)",
                 "category": "Software & Licensing", "qty": 16, "unit_price": 5500, "vendor": "VMware"},
                {"description": "Veeam Backup & Replication Enterprise (50 VMs)",
                 "category": "Software & Licensing", "qty": 1, "unit_price": 12000, "vendor": "Veeam"},
                {"description": "Data Center Colocation — Full Cabinet (monthly)",
                 "category": "Managed Services", "qty": 8, "unit_price": 2200, "vendor": "Equinix"},
                {"description": "Remote Hands & Smart Hands Support (40 hrs/mo)",
                 "category": "Managed Services", "qty": 1, "unit_price": 4800, "vendor": "Equinix"},
            ],
            "SD-WAN / Network": [
                {"description": "Cisco Catalyst SD-WAN Edge (2x WAN, 4x LAN)",
                 "category": "Network", "qty": 30, "unit_price": 4200, "vendor": "Cisco"},
                {"description": "Cisco SD-WAN Manager (vManage) — Cloud Hosted",
                 "category": "Software & Licensing", "qty": 1, "unit_price": 45000, "vendor": "Cisco"},
                {"description": "MPLS WAN Circuit 100Mbps (monthly per site)",
                 "category": "Connectivity", "qty": 30, "unit_price": 1800, "vendor": "AT&T"},
                {"description": "Broadband Internet Circuit 500Mbps (monthly)",
                 "category": "Connectivity", "qty": 30, "unit_price": 350, "vendor": "Comcast Business"},
                {"description": "Cisco Umbrella DNS Security (per user/yr)",
                 "category": "Security", "qty": 500, "unit_price": 24, "vendor": "Cisco"},
                {"description": "SD-WAN Professional Services & Deployment",
                 "category": "Professional Services", "qty": 1, "unit_price": 85000, "vendor": "CDW"},
            ],
            "Cybersecurity": [
                {"description": "Palo Alto PA-3220 NGFW (10Gbps throughput)",
                 "category": "Security", "qty": 4, "unit_price": 42000, "vendor": "Palo Alto Networks"},
                {"description": "CrowdStrike Falcon Complete (endpoint, per device/yr)",
                 "category": "Security", "qty": 500, "unit_price": 180, "vendor": "CrowdStrike"},
                {"description": "Splunk Enterprise Security (indexing, 10GB/day)",
                 "category": "Security", "qty": 1, "unit_price": 95000, "vendor": "Splunk"},
                {"description": "Okta Identity Cloud - SSO + MFA (per user/yr)",
                 "category": "Security", "qty": 500, "unit_price": 72, "vendor": "Okta"},
                {"description": "Tenable.sc Vulnerability Management (500 assets)",
                 "category": "Security", "qty": 1, "unit_price": 28000, "vendor": "Tenable"},
                {"description": "Security Awareness Training Platform (per user/yr)",
                 "category": "Security", "qty": 500, "unit_price": 15, "vendor": "KnowBe4"},
                {"description": "SOC-as-a-Service 24x7 MDR (monthly)",
                 "category": "Managed Services", "qty": 12, "unit_price": 18500, "vendor": "Arctic Wolf"},
            ],
            "Network Equipment": [
                {"description": "Cisco Catalyst 9300-48P Access Switch (48p PoE+, stacked pair)",
                 "category": "Network Equipment", "qty": 4, "unit_price": 8500, "vendor": "Cisco/CDW"},
                {"description": "Cisco Catalyst 9300-48T Distribution Switch (48p uplink)",
                 "category": "Network Equipment", "qty": 2, "unit_price": 12000, "vendor": "Cisco/CDW"},
                {"description": "Cisco Catalyst 9500-40X Core Switch (40x10G)",
                 "category": "Network Equipment", "qty": 2, "unit_price": 24000, "vendor": "Cisco/CDW"},
                {"description": "Fortinet FortiGate 400F NGFW (HA Primary)",
                 "category": "Firewall", "qty": 1, "unit_price": 18500, "vendor": "Fortinet/CDW"},
                {"description": "Fortinet FortiGate 400F NGFW (HA Secondary)",
                 "category": "Firewall", "qty": 1, "unit_price": 18500, "vendor": "Fortinet/CDW"},
                {"description": "Cisco Catalyst 9130AX Wireless AP (indoor)",
                 "category": "Wireless", "qty": 20, "unit_price": 1350, "vendor": "Cisco/CDW"},
                {"description": "Cisco DNA Center Wireless Controller License (per AP/yr)",
                 "category": "Software & Licensing", "qty": 20, "unit_price": 220, "vendor": "Cisco"},
                {"description": "Opengear OM2224-L4 OOB Console Server + LTE",
                 "category": "OOB Management", "qty": 2, "unit_price": 2800, "vendor": "CDW"},
                {"description": "3-Year Cisco SmartNet on all switches and firewalls",
                 "category": "Maintenance", "qty": 1, "unit_price": 22000, "vendor": "Cisco"},
                {"description": "Network Spares Kit (10% switches + APs)",
                 "category": "Spares", "qty": 1, "unit_price": 8500, "vendor": "CDW"},
            ],
        }
        # Pick closest matching template — exact match first, then fuzzy
        # Map common category aliases to template keys
        alias_map = {
            "network equipment": "Network Equipment",
            "access points": "Network Equipment",
            "lan": "Network Equipment",
            "wireless": "Network Equipment",
            "sd-wan": "SD-WAN / Network",
            "wan": "SD-WAN / Network",
            "cybersecurity": "Cybersecurity",
            "security": "Cybersecurity",
        }
        items_raw = templates.get(category)
        if items_raw is None:
            # Try alias map first (avoids DC template being used for Network Equipment)
            alias_key = alias_map.get(category.lower())
            if alias_key:
                items_raw = templates.get(alias_key)
        if items_raw is None:
            for key in templates:
                if any(w in category.lower() for w in key.lower().split("/")):
                    items_raw = templates[key]
                    break
        if items_raw is None:
            items_raw = templates["Data Center / COLO"]

        line_items = []
        for i, item in enumerate(items_raw, 1):
            ext = item["qty"] * item["unit_price"]
            line_items.append({
                "line_number": i,
                "description": item["description"],
                "category": item["category"],
                "unit": "/unit",
                "qty": item["qty"],
                "unit_price": item["unit_price"],
                "ext_price": ext,
                "vendor": item["vendor"],
                "status": "draft",
            })

        total = sum(li["ext_price"] for li in line_items)
        return {
            "project": project,
            "category": category,
            "total_value": total,
            "currency": "USD",
            "line_items": line_items,
        }

