"""
BOM Orchestrator — Sprint 2
Routes conversation to the correct specialist agent based on category and current phase.
Entry point called by backend/api/chat.py → _process_message().
"""
import logging
import json
import re
from typing import Dict, Any, Optional, Tuple

from ai.client import call_ai
from ai.prompts.system_base import get_system_prompt

logger = logging.getLogger(__name__)


def _retrieve_bom_context(query: str, bom_id: Optional[str] = None, top_k: int = 5) -> str:
    """
    Search the Azure Search BOM index for chunks semantically similar to the query.
    Returns a formatted string to inject into the system prompt, or empty string if
    the search service is unavailable or returns no results.
    """
    try:
        from services.search_service import search_bom_context
        results = search_bom_context(query=query, top_k=top_k, bom_id=bom_id)
        if not results:
            return ""
        lines = [
            f"[Source: {r.get('filename','unknown')} | Vendor: {r.get('vendor','')} "
            f"| Score: {r.get('score', 0):.2f}]\n{r['chunk_text']}"
            for r in results
        ]
        return (
            "\n\n" + "═" * 60 + "\nRELEVANT BOM DATA (retrieved from indexed BOMs)\n"
            + "═" * 60 + "\n"
            + "\n\n".join(lines)
        )
    except Exception as exc:
        logger.debug("BOM context retrieval skipped: %s", exc)
        return ""


class BOMOrchestrator:
    """
    Stateless orchestrator — all state lives in the SessionContext dict.
    Call process(session_dict, user_message) → (response_text, partial_bom, progress, complete)
    """

    def process(
        self,
        session: Dict[str, Any],
        message: str,
    ) -> Tuple[str, Optional[Dict], int, bool]:
        """
        Main entry point. Returns (response_text, partial_bom, progress_pct, complete).
        """
        context = session.get("context", {})
        category = context.get("category") or "Data Center / COLO"
        phase = context.get("current_phase", 1)
        phase_data = context.get("phase_data", {})
        requirements = context.get("requirements", {})
        history = session.get("conversation", [])

        # Load skill-aware system prompt (loads skill Markdown file if one exists for
        # this category, otherwise falls back to base + category hint)
        base_prompt = get_system_prompt(category)

        # Retrieve relevant BOM chunks from the embedding index (best-effort)
        bom_id = context.get("bom_id")  # if session is scoped to a specific BOM
        bom_context = _retrieve_bom_context(message, bom_id=bom_id)

        system = (
            base_prompt
            + f"\n\n{'═'*60}\nCURRENT SESSION\n{'═'*60}\n"
            + f"Category: {category}\n"
            + f"Project: {requirements.get('project', 'New Project')}\n"
            + f"Current Phase: {phase}/10\n"
            + f"Phase data collected: {json.dumps(phase_data, default=str)}\n"
            + f"Requirements: {json.dumps(requirements, default=str)}\n"
            + bom_context  # ← injected BOM embedding context
        )

        # Build conversation history (last 14 messages)
        # Normalise role: frontend stores AI messages as "ai" but Claude API requires "assistant"
        # Also ensure strict user/assistant alternation (drop consecutive same-role messages)
        raw_history = history[-14:]
        msgs = []
        for m in raw_history:
            role = m.get("role", "user")
            if role == "ai":
                role = "assistant"
            if role not in ("user", "assistant"):
                continue
            content = (m.get("content") or "").strip()
            if not content:
                continue
            # Enforce alternation: skip if same role as last
            if msgs and msgs[-1]["role"] == role:
                if role == "assistant":
                    msgs[-1]["content"] += "\n" + content  # merge consecutive assistant messages
                continue
            msgs.append({"role": role, "content": content})
        # Claude requires first message to be user; strip leading assistant if needed
        while msgs and msgs[0]["role"] == "assistant":
            msgs.pop(0)

        # Call AI
        response_text = call_ai(msgs, system=system)
        if response_text is None:
            # Rule-based fallback — pass history length so it knows if user is answering
            # user_turn_count = number of user messages already in history
            user_turns = sum(1 for m in history if m.get("role") == "user")
            response_text = self._rule_based(category, phase, message, user_turns)

        # Parse BOM JSON if present
        partial_bom, complete = self._extract_bom(response_text)

        # Remove the raw ```json block from the text the user sees — the BOM is
        # already extracted into partial_bom and will be rendered by the frontend.
        if partial_bom:
            response_text = re.sub(r"```json[\s\S]*?```", "", response_text).strip()
            # If stripping leaves only whitespace, put a clean summary line
            if not response_text:
                response_text = "BOM generated. See the panel on the right for all line items."

        # Advance phase heuristically (AI confirms progress in text)
        new_phase = self._detect_phase_advance(response_text, phase, message)
        context["current_phase"] = new_phase

        # Progress 0–100%: phases 1–7 = 70%, phase 8 = 85%, 9 = 95%, 10 = 100%
        progress = self._phase_to_progress(new_phase, complete)

        return response_text, partial_bom, progress, complete

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _extract_bom(self, text: str) -> Tuple[Optional[Dict], bool]:
        """
        Extract BOM JSON from AI response text.
        Handles both default schema (line_items) and skill file format (bom_line_items).
        Also normalises per-item field aliases so the frontend receives a consistent shape.
        """
        match = re.search(r"```json\s*([\s\S]*?)```", text)
        if not match:
            return None, False
        try:
            data = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            return None, False

        # Normalise top-level key: skill files use "bom_line_items"
        if "bom_line_items" in data and data["bom_line_items"]:
            data["line_items"] = data.pop("bom_line_items")

        items = data.get("line_items", [])
        if not items:
            return None, False

        # Normalise each line item so frontend backendBOMtoFrontend always gets consistent fields
        normalised = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            # qty / quantity alias
            qty = item.get("qty") or item.get("quantity") or 1
            # price fields — skill file may emit null for pricing_required items
            unit_price = item.get("unit_price") or 0
            ext_price = (
                item.get("extended_price")
                or item.get("ext_price")
                or (unit_price * qty if unit_price else 0)
            )
            normalised.append({
                "line_number":    item.get("line_number") or i + 1,
                "category":       item.get("category", "Network Equipment"),
                "description":    item.get("description", ""),
                "sku":            item.get("sku") or item.get("part_number", ""),
                "qty":            qty,
                "quantity":       qty,
                "unit":           item.get("unit", "/unit"),
                "unit_price":     unit_price,
                "extended_price": ext_price,
                "ext_price":      ext_price,
                "vendor":         item.get("vendor", ""),
                "term":           item.get("term", "one-time"),
                "order_sequence": item.get("order_sequence") or item.get("order_seq", ""),
                "eol_flag":       bool(item.get("eol_flag", False)),
                "eol_warning":    item.get("eol_warning", ""),
                "notes":          item.get("notes", ""),
                "ha_role":        item.get("ha_role", ""),
                "site_name":      item.get("site_name", ""),
                "price_basis":    item.get("price_basis", "budgetary_assumption"),
                "quantity_basis": item.get("quantity_basis", ""),
                "recommendation_status": item.get("recommendation_status", ""),
            })
        data["line_items"] = normalised
        return data, True

    def _detect_phase_advance(self, response: str, current_phase: int, message: str) -> int:
        """Simple heuristic: if AI mentions 'Phase X' in response, advance to that phase."""
        for p in range(current_phase + 1, 11):
            if f"Phase {p}" in response or f"phase {p}" in response:
                return p
        return current_phase

    def _phase_to_progress(self, phase: int, complete: bool) -> int:
        if complete:
            return 100
        phase_map = {1: 5, 2: 15, 3: 25, 4: 35, 5: 45, 6: 55, 7: 70, 8: 80, 9: 90, 10: 95}
        return phase_map.get(phase, 5)

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
        explicit_create = bool(create_pat.search(msg))

        # ── Detect info answers (numbers, dates, yes/no) ─────────────────
        has_answer = bool(re.search(
            r"\d+\s*(rack|server|site|node|user|vm|tb|gb|core|vcpu|watt|kw|mw)"
            r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"      # date pattern
            r"|\byes\b|\bno\b|\bvmware\b|\bhyper.?v\b|\baws\b|\bazure\b"
            r"|\bmpls\b|\bdia\b|\bfibre\b|\binternet\b",
            msg, re.I
        ))

        # ── Decision: generate BOM now? ───────────────────────────────────
        # Generate when: explicit intent, phase advanced, or enough turns collected
        # For non-DC categories use a lower threshold (5-question flow is faster)
        is_dc = "data center" in category.lower() or "colo" in category.lower()
        turn_threshold = 2 if is_dc else 1   # DC: ask 2 rounds; others: 1 round

        should_generate = (
            explicit_create
            or phase >= 4
            or user_turns >= turn_threshold
            or (has_answer and user_turns >= 1)
        )

        if should_generate:
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

        # ── Phase questions ────────────────────────────────────────────────
        if is_dc:
            phase_questions = {
                1: (
                    f"I'll help you build a **{category}** BOM for **{project}**.\n\n"
                    "**Phase 1 — Scope & Constraints**\n\n"
                    "1. What is the **Day 1 cutover date** for this project?\n"
                    "2. How many **racks / physical sites** are in scope?\n"
                    "3. Any specialised hardware (GPU, AS400, bare metal, high-memory)?\n\n"
                    "*Say **\"create the BOM\"** to skip ahead and generate a full template immediately.*"
                ),
                2: (
                    "**Phase 2 — Inventory & Sizing**\n\n"
                    "1. How many **servers** are being conveyed (transferred in the deal)?\n"
                    "2. Are any running **EOL operating systems** (Server 2012 or older)?\n"
                    "3. What is the **hypervisor** in use — VMware or Hyper-V?\n\n"
                    "*Say **\"create the BOM now\"** to generate from templates.*"
                ),
            }
            return phase_questions.get(
                phase if phase in phase_questions else 1,
                f"Tell me more about your **{category}** requirements, "
                f"or say **\"create the BOM\"** to generate a complete template now.",
            )
        else:
            # Non-DC: single question round using the 5-question flow
            category_q = {
                "SD-WAN": (
                    "1. How many **sites** will connect via SD-WAN?\n"
                    "2. What **ISP type** per site — MPLS, broadband, or both?\n"
                    "3. Is **HA** required (active/active or active/passive)?\n"
                ),
                "Cybersecurity": (
                    "1. How many **endpoints** need protection?\n"
                    "2. What **compliance** frameworks apply (PCI, HIPAA, SOC 2)?\n"
                    "3. Current tooling gaps — EDR, SIEM, PAM, or email security?\n"
                ),
                "Network Equipment": (
                    "1. Total **port count** required (access layer)?\n"
                    "2. **PoE** required — how many PoE+ ports?\n"
                    "3. Target **uplink speed** — 10G, 25G, or 100G?\n"
                ),
                "M365 & Power Platform": (
                    "1. **User count** — how many E3 vs E5 licenses needed?\n"
                    "2. Is **Power BI Premium** (per capacity or per user) required?\n"
                    "3. Migrating from **Exchange on-prem** or Google Workspace?\n"
                ),
                "Laptops": (
                    "1. **User count** and role breakdown (exec / dev / standard)?\n"
                    "2. **OS preference** — Windows, macOS, or mixed fleet?\n"
                    "3. **MDM platform** already in place — Intune or Jamf?\n"
                ),
            }
            q_block = category_q.get(
                category,
                "1. What is the **scope and scale** (sites, users, devices)?\n"
                "2. Any **compliance** requirements (PCI, HIPAA, SOC 2)?\n"
                "3. Preferred **vendors** or existing contracts to honour?\n"
            )
            return (
                f"I'll help you build a **{category}** BOM for **{project}**.\n\n"
                f"{q_block}\n"
                "*Say **\"create the BOM\"** to skip ahead and generate a full template immediately.*"
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
                {"description": "Okta Identity Cloud — SSO + MFA (per user/yr)",
                 "category": "Security", "qty": 500, "unit_price": 72, "vendor": "Okta"},
                {"description": "Tenable.sc Vulnerability Management (500 assets)",
                 "category": "Security", "qty": 1, "unit_price": 28000, "vendor": "Tenable"},
                {"description": "Security Awareness Training Platform (per user/yr)",
                 "category": "Security", "qty": 500, "unit_price": 15, "vendor": "KnowBe4"},
                {"description": "SOC-as-a-Service — 24×7 MDR (monthly)",
                 "category": "Managed Services", "qty": 12, "unit_price": 18500, "vendor": "Arctic Wolf"},
            ],
        }
        # Pick closest matching template
        items_raw = templates.get(category)
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
