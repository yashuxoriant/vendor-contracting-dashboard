"""
BOM Orchestrator — Full State Machine (LangGraph-style, no external dependency)

Architecture:
  User message
    → SessionState loaded from context
    → Phase gate: check what data is missing for current phase
    → Build system prompt (skill file + RAG context + phase instructions)
    → Call AI
    → Post-process: extract BOM, validate, detect phase transition
    → Return (response_text, partial_bom, progress, complete, new_state)

Phases:
  INTAKE    → M&A context: phase (Day1/TSA/Integration), category, project name
  QUALIFY   → Conveying/shared/dedicated, EOL status, Day 1 date
  SCOPE     → Sites, users, HA requirements, vendor preference
  SIZING    → Compute quantities, multipliers, PoE budgets
  GENERATE  → Build the full BOM with all SKU bundles
  VALIDATE  → EOL check, PoE, HA, lead-time warnings
  COMPLETE  → BOM ready for human review
"""
import logging
import json
import re
import hashlib
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum

from ai.client import call_ai
from ai.prompts import system_base as _system_base_mod

def get_system_prompt(category: str = "") -> str:  # thin shim to avoid circular import
    return _system_base_mod.get_system_prompt(category)

logger = logging.getLogger(__name__)


# ── Phase State Machine ──────────────────────────────────────────────────────

class BOMPhase(str, Enum):
    INTAKE   = "intake"     # Gather M&A phase, category, project name
    QUALIFY  = "qualify"    # Conveying/shared/dedicated, EOL status
    SCOPE    = "scope"      # Sites, users, Day 1 date, vendor preference
    SIZING   = "sizing"     # Compute quantities, multipliers, configs
    GENERATE = "generate"   # Build full BOM with SKU bundles
    VALIDATE = "validate"   # EOL, PoE, HA, lead-time validation
    COMPLETE = "complete"   # BOM finalized


# Fields checked at each phase gate (what must be known before advancing)
_PHASE_GATES: Dict[BOMPhase, List[str]] = {
    BOMPhase.INTAKE:   [],                                                          # Always enter
    BOMPhase.QUALIFY:  ["ma_phase", "workstream_category"],                         # Need M&A + category
    BOMPhase.SCOPE:    ["conveyance_status"],                                       # Need conveying decision
    BOMPhase.SIZING:   ["site_count"],                                              # Need site count
    BOMPhase.GENERATE: ["site_count", "required_by_date"],                         # Need count + date
    BOMPhase.VALIDATE: [],                                                          # Auto after generate
    BOMPhase.COMPLETE: [],                                                          # Auto after validate
}

# Phase → progress percentage
_PHASE_PROGRESS: Dict[BOMPhase, int] = {
    BOMPhase.INTAKE:   10,
    BOMPhase.QUALIFY:  25,
    BOMPhase.SCOPE:    40,
    BOMPhase.SIZING:   60,
    BOMPhase.GENERATE: 80,
    BOMPhase.VALIDATE: 90,
    BOMPhase.COMPLETE: 100,
}

# Ordered phase list for transition logic
_PHASE_ORDER = [
    BOMPhase.INTAKE, BOMPhase.QUALIFY, BOMPhase.SCOPE,
    BOMPhase.SIZING, BOMPhase.GENERATE, BOMPhase.VALIDATE, BOMPhase.COMPLETE,
]


def _retrieve_bom_context(query: str, bom_id: Optional[str] = None, top_k: int = 5) -> str:
    """Search indexed BOMs for relevant chunks to inject into the system prompt."""
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
            "\n\n" + "=" * 60 + "\nREFERENCE BOM DATA (from indexed library)\n"
            + "=" * 60 + "\n"
            + "\n\n".join(lines)
        )
    except Exception as exc:
        logger.debug("BOM context retrieval skipped: %s", exc)
        return ""


def _extract_fields_from_message(message: str, agent_state: Dict) -> Dict:
    """
    Deterministically extract intake fields from a user message.
    Updates agent_state in-place; returns updated dict.
    Real-life example: user says "TSA exit for 10 sites, Cisco standard, Day 1 March 15"
    """
    m = message.lower()

    # M&A Phase
    if not agent_state.get("ma_phase"):
        if re.search(r"day.?1|day one|closing|close", m):
            agent_state["ma_phase"] = "Day-1 Readiness"
        elif re.search(r"tsa.?exit|exit\s+tsa|cutover|migration", m):
            agent_state["ma_phase"] = "TSA Exit / Cutover"
        elif re.search(r"integration|standalone|post.tsa|steady.state", m):
            agent_state["ma_phase"] = "Full Integration / Standalone"

    # Category detection
    if not agent_state.get("workstream_category"):
        cat_patterns = [
            (r"data.?cent|colo|colocation",         "Data Center / COLO"),
            (r"sd.?wan|wan.router|branch.router",    "SD-WAN"),
            (r"network.?&.?tel|lan|wlan|wireless|switch|access.point", "Network & Telecom"),
            (r"cyber|firewall|siem|edr|soc.?2|pci|hipaa", "Cybersecurity"),
            (r"m365|office.365|teams|sharepoint|power.bi", "M365 & Power Platform"),
            (r"cloud|azure|aws|gcp|expressroute",   "Cloud Infrastructure"),
            (r"eol|end.of.life|end.of.support|eos", "EOL Replacement"),
            (r"laptop|end.user|euc|vdi",            "End User Computing"),
        ]
        for pat, cat in cat_patterns:
            if re.search(pat, m):
                agent_state["workstream_category"] = cat
                break

    # Conveyance
    if not agent_state.get("conveyance_status"):
        if re.search(r"not.convey|not.transfer|stay\s+with|msp.own|leased|shared", m):
            agent_state["conveyance_status"] = "not_conveying"
        elif re.search(r"convey|transfer|coming.with|brings.with|inheriting", m):
            if re.search(r"eol|end.of.life|eos|end.of.support|outdated|old", m):
                agent_state["conveyance_status"] = "conveying_eol"
            else:
                agent_state["conveyance_status"] = "conveying_active"
        elif re.search(r"shared|multi.tenant|common.infra", m):
            agent_state["conveyance_status"] = "shared"

    # Site count
    if not agent_state.get("site_count"):
        sm = re.search(r"(\d+)\s*(?:site|location|branch|office|data.cent)", m)
        if sm:
            agent_state["site_count"] = int(sm.group(1))

    # User count
    if not agent_state.get("user_count"):
        um = re.search(r"(\d+)\s*(?:user|employee|seat|staff|person)", m)
        if um:
            agent_state["user_count"] = int(um.group(1))

    # Day 1 / Required-by date
    if not agent_state.get("required_by_date"):
        dm = re.search(
            r"(?:day.?1|deadline|required.by|go.live|cutover|by)\s*[-–:]?\s*"
            r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march"
            r"|april|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?",
            m, re.I
        )
        if dm:
            agent_state["required_by_date"] = dm.group(0)
        else:
            dm2 = re.search(r"\b(20\d{2})[-/](0?\d|1[0-2])[-/](0?\d|[12]\d|3[01])\b", message)
            if dm2:
                agent_state["required_by_date"] = dm2.group(0)

    # Vendor preference
    if not agent_state.get("vendor_standard"):
        if re.search(r"\bcisco\b", m):
            agent_state["vendor_standard"] = "Cisco"
        elif re.search(r"\bfortinet\b|\bfortigate\b", m):
            agent_state["vendor_standard"] = "Fortinet"
        elif re.search(r"\baruba\b", m):
            agent_state["vendor_standard"] = "Aruba"
        elif re.search(r"\bjuniper\b|\bjunos\b", m):
            agent_state["vendor_standard"] = "Juniper"
        elif re.search(r"\bpalo.alto\b|\bpan-os\b|\bprisma\b", m):
            agent_state["vendor_standard"] = "Palo Alto"

    # HA / criticality
    if not agent_state.get("site_criticality"):
        if re.search(r"\bcritical\b|\bha\s*pair\b|\bhigh.avail|\bactive.active\b|\bactive.passive\b", m):
            agent_state["site_criticality"] = "critical"
        elif re.search(r"\bstandard\b|\bnon.critical\b|\boffice\b|\bbranch\b", m):
            agent_state["site_criticality"] = "standard"

    # Project / client name — "for Panasonic", "client: Honeywell", "project Falcon"
    if not agent_state.get("project_name"):
        pm = re.search(
            r"(?:for|client[:\s]+|project[:\s]+)\s+([A-Z][a-zA-Z0-9&]+(?:\s+[A-Z][a-zA-Z0-9&]+){0,3})",
            message,
        )
        if pm:
            candidate = pm.group(1).strip()
            _FALSE_POSITIVES = {"cisco", "fortinet", "aruba", "juniper", "palo alto",
                                "new", "standard", "critical", "active", "passive",
                                "this", "the", "a", "an", "day", "march", "april"}
            if candidate.lower() not in _FALSE_POSITIVES:
                agent_state["project_name"] = candidate

    return agent_state


def _detect_phase_transition(
    response_text: str,
    current_phase: BOMPhase,
    agent_state: Dict,
    bom_found: bool,
) -> BOMPhase:
    """
    Determine what phase to move to after the AI responds.
    Priority:
      1. BOM JSON found → VALIDATE (or COMPLETE if valid enough)
      2. All gate fields present → advance to next phase
      3. AI explicitly names a phase → use that
      4. Stay in current phase
    """
    if bom_found:
        return BOMPhase.VALIDATE

    # Check if all gates for NEXT phase are met
    idx = _PHASE_ORDER.index(current_phase) if current_phase in _PHASE_ORDER else 0
    for next_phase in _PHASE_ORDER[idx + 1:]:
        gates = _PHASE_GATES.get(next_phase, [])
        if all(agent_state.get(g) for g in gates):
            return next_phase
        else:
            break  # can't skip — must satisfy gates in order

    # Scan AI text for explicit phase names
    phase_keywords = {
        BOMPhase.QUALIFY:  ["conveyance", "conveying", "dedicated", "shared"],
        BOMPhase.SCOPE:    ["how many sites", "site count", "user count", "required by"],
        BOMPhase.SIZING:   ["sizing", "compute", "port density", "poe budget"],
        BOMPhase.GENERATE: ["building the bom", "generating", "here is your bom"],
    }
    text_lower = response_text.lower()
    for phase, kws in phase_keywords.items():
        if any(kw in text_lower for kw in kws):
            # Only advance if not going backwards
            if _PHASE_ORDER.index(phase) > _PHASE_ORDER.index(current_phase):
                return phase

    return current_phase  # stay put


def _phase_addendum(phase: BOMPhase, agent_state: Dict) -> str:
    """Return phase-specific instructions to inject into the system prompt."""
    known = {k: v for k, v in agent_state.items() if v}

    if phase == BOMPhase.INTAKE:
        return (
            "\n\n[CURRENT PHASE: INTAKE]\n"
            "Ask ONLY these questions — one message, no more:\n"
            "1. What is the M&A phase? (Day-1 Readiness / TSA Exit / Full Integration)\n"
            "2. What category? (Data Center/COLO, Network & Telecom, SD-WAN, Cybersecurity, M365, Cloud, EOL)\n"
            "3. Project name / client name?\n"
            "Do NOT ask about sites, vendors, or conveyance yet. Collect category first."
        )

    if phase == BOMPhase.QUALIFY:
        cat = known.get("workstream_category", "Network & Telecom")
        return (
            f"\n\n[CURRENT PHASE: QUALIFICATION — {cat}]\n"
            "Apply the Conveying/Shared/Dedicated Decision Tree:\n"
            "STEP 1: Is the infrastructure shared (multi-tenant / MSP-owned) or dedicated?\n"
            "  → Shared: buy NET NEW for all layers. Skip to SCOPE.\n"
            "  → Dedicated: go to STEP 2.\n"
            "STEP 2: Is dedicated equipment conveying (transferring in deal)?\n"
            "  → Not conveying: buy NET NEW.\n"
            "  → Conveying: go to STEP 3.\n"
            "STEP 3: Is conveying equipment EOL/EOS?\n"
            "  → EOL/EOS: generate REPLACEMENT bundle.\n"
            "  → Active: scope = integration only (licenses, maintenance, config changes).\n"
            f"KNOWN SO FAR: {json.dumps(known, default=str)}"
        )

    if phase == BOMPhase.SCOPE:
        return (
            "\n\n[CURRENT PHASE: SCOPE]\n"
            "Collect (ask in one message):\n"
            "1. Number of sites (this is the MULTIPLIER for all quantities)\n"
            "2. Users per site (controls port density, AP count, firewall sessions)\n"
            "3. Hard Day-1 cutover date (drives all lead-time warnings)\n"
            "4. Vendor standard (Cisco / Fortinet / Aruba / Juniper / Palo Alto)\n"
            "5. Site criticality (critical = HA pair mandatory, standard = HA at firewall only)\n"
            f"KNOWN SO FAR: {json.dumps(known, default=str)}"
        )

    if phase == BOMPhase.SIZING:
        sites = known.get("site_count", "?")
        users = known.get("user_count", "?")
        return (
            f"\n\n[CURRENT PHASE: SIZING — {sites} sites, {users} users/site]\n"
            "Compute EXACT quantities now. Use the bundle formulas:\n"
            "- Access switches: CEIL(users/48) per site, stack in pairs\n"
            "- APs: CEIL(users/30) per site (office), 1 per 15 (high-density)\n"
            "- WAN routers: 2 per HA site, 1 per standard site\n"
            "- Firewalls: 2 per site (HA pair always for >250 users or compliance)\n"
            "- quantity_basis: annotate every line as '[qty] per site × [N] sites = [total]'\n"
            f"KNOWN SO FAR: {json.dumps(known, default=str)}"
        )

    if phase == BOMPhase.GENERATE:
        vendor = known.get("vendor_standard", "Cisco")
        sites = known.get("site_count", 1)
        criticality = known.get("site_criticality", "standard")
        return (
            f"\n\n[CURRENT PHASE: BOM GENERATION — {vendor}, {sites} sites, {criticality}]\n"
            "EXPAND EVERY COMPONENT TO ITS FULL SKU BUNDLE NOW.\n"
            "Rule: A single hardware line is ALWAYS wrong. Every component expands to:\n"
            "  Router  → 8 lines  (chassis + IOS + DNA subscription + SmartNet + WAN NIM + SFP + cables + rack kit)\n"
            "  Firewall → 10 lines (appliance + IPS + URL + SSL + AMP + HA peer + support + rack + SFPs + PS)\n"
            "  Switch  → 5 lines  (chassis + license + stacking + SmartNet + SFP uplinks)\n"
            "  AP      → 4 lines  (unit + PoE injector + cloud license + mounting)\n"
            "Output ONLY valid JSON inside ```json...``` fences.\n"
            "Each line item MUST include: quantity_basis, ha_role (if HA pair), price_basis, order_sequence.\n"
            "NEVER output a single 'Cisco Router' line — that fails the Vendor-Ready BOM Gate.\n"
            f"KNOWN SO FAR: {json.dumps(known, default=str)}"
        )

    if phase == BOMPhase.VALIDATE:
        return (
            "\n\n[CURRENT PHASE: VALIDATION]\n"
            "Check and annotate:\n"
            "1. EOL/EOS: flag any SKU where EOS date < Day1 + 3 years\n"
            "2. PoE budget: sum (phones×7.5W + APs×15.4W) vs switch capacity\n"
            "3. HA completeness: critical sites must have HA pair on ALL layers\n"
            "4. Lead-time warnings: flag MPLS (12-20wk), switching (16-26wk), firewalls (8-16wk)\n"
            "5. Dual-quote flag: any line item >$50K needs two vendor quotes\n"
            "After validation, output the FINAL BOM JSON with all warnings populated.\n"
        )

    return ""


class BOMOrchestrator:
    """
    Stateless orchestrator — all state in SessionContext.agent_state dict.
    Implements a 7-phase LangGraph-style state machine without external dependencies.

    Real-world flow (Chetan's model):
      Cisco router for 10 sites
        → INTAKE: identify category=Network&Telecom, ma_phase=TSA Exit
        → QUALIFY: dedicated+not-conveying → buy net new
        → SCOPE: 10 sites, 200 users/site, Day1=Q2, Cisco standard, critical
        → SIZING: 2 routers/site × 10 = 20; 10 access switches × 5 lines each...
        → GENERATE: expand to full 8-line bundles → 80 line items total
        → VALIDATE: flag lead times, PoE budgets, SmartNet mandatory
        → COMPLETE: vendor-ready BOM
    """

    def process(
        self,
        session: Dict[str, Any],
        message: str,
    ) -> Tuple[str, Optional[Dict], int, bool]:
        """
        Main entry. Returns (response_text, partial_bom, progress_pct, complete).
        Mutates session["context"]["agent_state"] and session["context"]["current_phase"].
        """
        context = session.get("context", {})
        category = context.get("category") or "Data Center / COLO"
        agent_state = context.get("agent_state", {})
        phase_str = context.get("current_phase_name", BOMPhase.INTAKE.value)

        try:
            current_phase = BOMPhase(phase_str)
        except ValueError:
            current_phase = BOMPhase.INTAKE

        # ── Extract fields deterministically from this message ─────────────
        agent_state = _extract_fields_from_message(message, agent_state)
        # Use category from session context as ground truth
        if category and not agent_state.get("workstream_category"):
            agent_state["workstream_category"] = category

        # ── Build system prompt ───────────────────────────────────────
        base_prompt = get_system_prompt(category)
        bom_id = context.get("bom_id")
        bom_rag = _retrieve_bom_context(message, bom_id=bom_id)

        requirements = context.get("requirements", {})
        project = requirements.get("project", "New Project")
        old_phase_num = context.get("current_phase", 1)

        # Inject project so rule-based never falls back to "your project"
        if not agent_state.get("project_name") and project not in ("", "New Project"):
            agent_state["project_name"] = project

        system = (
            base_prompt
            + "\n\n" + "=" * 60 + "\nACTIVE SESSION\n" + "=" * 60
            + f"\nProject: {project}"
            + f"\nCategory: {category}"
            + f"\nPhase: {current_phase.value.upper()}"
            + f"\nAgent State: {json.dumps(agent_state, default=str)}"
            + _phase_addendum(current_phase, agent_state)
            + bom_rag
        )

        # ── Build message history (strict user/assistant alternation) ──────
        history = session.get("conversation", [])
        raw = history[-16:]  # last 16 = 8 back-and-forths
        msgs: List[Dict] = []
        for m in raw:
            role = m.get("role", "user")
            if role in ("ai", "AI"):
                role = "assistant"
            if role not in ("user", "assistant"):
                continue
            content = (m.get("content") or "").strip()
            if not content:
                continue
            if msgs and msgs[-1]["role"] == role:
                if role == "assistant":
                    msgs[-1]["content"] += "\n" + content
                # For duplicate user messages: SKIP the duplicate (dedup)
                continue
            msgs.append({"role": role, "content": content})
        # Claude requires messages to start with user
        while msgs and msgs[0]["role"] == "assistant":
            msgs.pop(0)

        # ── Call AI ────────────────────────────────────────────────────────
        response_text = call_ai(msgs, system=system)
        if response_text is None:
            user_turns = sum(1 for m in history if m.get("role") == "user")
            response_text = self._rule_based(category, current_phase, message, agent_state, user_turns)

        # ── Post-process ───────────────────────────────────────────────────
        partial_bom, bom_found = self._extract_bom(response_text)

        # Strip JSON block from display text
        display_text = response_text
        if partial_bom:
            display_text = re.sub(r"```json[\s\S]*?```", "", response_text).strip()
            if not display_text:
                display_text = (
                    f"BOM generated: **{len(partial_bom.get('line_items', []))} line items**"
                    f" — see the panel on the right for full details."
                )

        # ── Phase transition ───────────────────────────────────────────────
        # Also extract fields the AI mentioned in its response
        agent_state = _extract_fields_from_message(response_text, agent_state)
        new_phase = _detect_phase_transition(response_text, current_phase, agent_state, bom_found)

        # ── Persist state back to session context ──────────────────────────
        context["agent_state"] = agent_state
        context["current_phase_name"] = new_phase.value
        context["current_phase"] = _PHASE_ORDER.index(new_phase) + 1  # keep numeric compat

        complete = (new_phase == BOMPhase.COMPLETE) or (bom_found and new_phase == BOMPhase.VALIDATE)
        progress = _PHASE_PROGRESS.get(new_phase, 10)

        if complete and partial_bom:
            # Inject final enrichments
            partial_bom["project"] = project
            partial_bom["category"] = category
            partial_bom["ma_phase"] = agent_state.get("ma_phase", "")
            partial_bom["vendor_standard"] = agent_state.get("vendor_standard", "")
            partial_bom["site_count"] = agent_state.get("site_count")
            partial_bom["conveyance_status"] = agent_state.get("conveyance_status", "")

        logger.info(
            "Orchestrator: project=%s category=%s phase=%s→%s complete=%s bom_items=%d",
            project, category, current_phase.value, new_phase.value,
            complete, len(partial_bom.get("line_items", []) if partial_bom else []),
        )

        return display_text, partial_bom, progress, complete

    # ── BOM extraction ────────────────────────────────────────────────────

    def _extract_bom(self, text: str) -> Tuple[Optional[Dict], bool]:
        """
        Extract and normalise BOM JSON from AI response.
        Returns (bom_dict, found_flag).
        """
        match = re.search(r"```json\s*([\s\S]*?)```", text)
        if not match:
            return None, False
        try:
            data = json.loads(match.group(1).strip())
        except json.JSONDecodeError as exc:
            logger.warning("BOM JSON parse failed: %s", exc)
            return None, False

        # Normalise top-level key: skill files emit "bom_line_items"
        if "bom_line_items" in data and data["bom_line_items"]:
            data["line_items"] = data.pop("bom_line_items")

        items = data.get("line_items", [])
        if not items:
            return None, False

        normalised = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            qty = item.get("qty") or item.get("quantity") or 1
            unit_price = item.get("unit_price") or 0
            ext_price = (
                item.get("extended_price")
                or item.get("ext_price")
                or (unit_price * qty if unit_price else 0)
            )
            normalised.append({
                "line_number":    item.get("line_number") or i + 1,
                "category":       item.get("category", ""),
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

        # Recompute totals
        total_otc = sum(
            (n["unit_price"] or 0) * (n["qty"] or 1)
            for n in normalised
        )
        if "totals" not in data or not data["totals"]:
            data["totals"] = {}
        data["totals"]["total_otc"] = data["totals"].get("total_otc") or total_otc

        data["line_items"] = normalised
        return data, True

    # ── Rule-based fallback ───────────────────────────────────────────────

    def _rule_based(
        self,
        category: str,
        phase: BOMPhase,
        message: str,
        agent_state: Dict,
        user_turns: int = 0,
    ) -> str:
        """
        Rule-based responses when AI is unavailable.
        Real-world template: mirrors Chetan's question hierarchy.
        """
        known = {k: v for k, v in agent_state.items() if v}
        # project_name is injected from session requirements before _rule_based is called
        project = known.get("project_name") or category.split("/")[0].strip()

        if phase == BOMPhase.INTAKE:
            return (
                f"I'll help you build a **{category}** BOM for **{project}**.\n\n"
                "To get started, I need three things:\n\n"
                "1. **M&A Phase** — Is this for *Day-1 Readiness*, *TSA Exit*, or *Full Integration*?\n"
                "2. **Project / Client name**\n"
                "3. **Scope confirmation** — new build or replacing existing infrastructure?\n\n"
                "*Say __\"skip\" or \"create the BOM now\"__ to generate a template immediately.*"
            )

        if phase == BOMPhase.QUALIFY:
            return (
                "**Qualification — Conveying & Shared/Dedicated**\n\n"
                "For the network infrastructure:\n\n"
                "1. Is the equipment **shared** (multi-tenant, MSP-owned) or **dedicated** to this entity?\n"
                "2. If dedicated — is it **conveying** (transferring in the deal) or staying with the seller?\n"
                "3. If conveying — is any of it **EOL or EOS** (end of life / end of support)?\n\n"
                "Your answers control what I put in the BOM:\n"
                "- Shared → buy net new\n"
                "- Dedicated, not conveying → buy net new\n"
                "- Conveying, active → integration costs only\n"
                "- Conveying, EOL → replacement bundle"
            )

        if phase == BOMPhase.SCOPE:
            return (
                "**Scope — Sites, Users, and Timeline**\n\n"
                "1. How many **sites**? (This multiplies all quantities)\n"
                "2. **Users per site**? (Controls switch port density, AP count, firewall sizing)\n"
                "3. **Day-1 cutover date**? (Required for lead-time warnings)\n"
                "4. **Vendor standard**? (Cisco, Fortinet, Aruba, Juniper, Palo Alto)\n"
                "5. **Site criticality**? (Critical = mandatory HA pairs on all layers)\n\n"
                "*Example: 10 sites, 200 users each, Day 1 March 15, Cisco standard, critical.*"
            )

        if phase == BOMPhase.SIZING:
            sites = known.get("site_count", "?")
            users = known.get("user_count", "?")
            vendor = known.get("vendor_standard", "Cisco")
            sw = sites * 2 if isinstance(sites, int) else "2 \u00d7 sites"
            return (
                f"**Sizing Confirmation \u2014 {project}**\n\n"
                f"Calculated from **{sites} sites \u00d7 {users} users/site** with **{vendor}** standard:\n\n"
                f"- WAN routers: {sw} total (HA active/standby)\n"
                f"- Firewalls: {sw} total (HA pair per site)\n"
                "- Access switches: CEIL(users/48) per site, stacked pairs\n"
                "- APs: CEIL(users/30) per site\n\n"
                "Reply **\"confirm\"** or **\"generate BOM\"** to build the full vendor-ready BOM."
            )

        # GENERATE / VALIDATE / COMPLETE or user has answered >=4 rounds
        if phase in (BOMPhase.GENERATE, BOMPhase.VALIDATE, BOMPhase.COMPLETE) or user_turns >= 4:
            bom = self._build_template_bom(category, project, agent_state)
            bom_json = json.dumps(bom, indent=2)
            n = len(bom.get("line_items", []))
            total = bom.get("totals", {}).get("total_otc", 0)
            prefix = (
                "\u2705 **Validation complete** \u2014 BOM is vendor-ready.\n\n"
                if phase == BOMPhase.VALIDATE
                else ""
            )
            return (
                f"{prefix}Here is your **{category}** BOM for **{project}**.\n\n"
                f"**{n} line items** — estimated total: **${total:,.0f}**\n\n"
                f"```json\n{bom_json}\n```"
            )

        return (
            f"Tell me more about your **{category}** requirements for **{project}**, "
            "or type **\"create the BOM\"** to generate a complete template now."
        )

    def _build_template_bom(self, category: str, project: str, agent_state: Dict) -> dict:
        """Return a vendor-ready template BOM dict for the given category."""
        sites = agent_state.get("site_count", 1)
        vendor = agent_state.get("vendor_standard", "Cisco")

        def s(qty, per_site=True):
            """Scale quantity by site count."""
            return qty * sites if per_site else qty

        templates: Dict[str, list] = {
            "Data Center / COLO": [
                {"description": "Dell PowerEdge R750 (2x Xeon Gold 6330, 512GB RAM, 2x25G NIC)", "category": "Compute", "qty": s(4), "unit_price": 28500, "vendor": "Dell Technologies", "term": "one-time", "order_sequence": 3},
                {"description": "Dell PowerEdge R750 SmartNet 3yr NBD", "category": "Support Contract", "qty": s(4), "unit_price": 5100, "vendor": "Dell Technologies", "term": "3-year", "order_sequence": 6},
                {"description": "NetApp AFF A400 All-Flash (50TB raw, dual controller)", "category": "Storage", "qty": 1, "unit_price": 125000, "vendor": "NetApp", "term": "one-time", "order_sequence": 3},
                {"description": "NetApp Support Gold 3yr", "category": "Support Contract", "qty": 1, "unit_price": 22500, "vendor": "NetApp", "term": "3-year", "order_sequence": 6},
                {"description": "Cisco Nexus 93180YC-FX ToR Switch (48x25G+6x100G)", "category": "Network", "qty": s(2), "unit_price": 18750, "vendor": "Cisco", "term": "one-time", "order_sequence": 2},
                {"description": "Cisco Nexus 93180YC SmartNet 3yr", "category": "Support Contract", "qty": s(2), "unit_price": 3375, "vendor": "Cisco", "term": "3-year", "order_sequence": 6},
                {"description": "APC Smart-UPS SRT 10kVA UPS N+1", "category": "Power & Physical", "qty": s(2), "unit_price": 9800, "vendor": "APC / Schneider", "term": "one-time", "order_sequence": 1},
                {"description": "42U Server Rack with Blanking Panels + Cable Mgmt", "category": "Power & Physical", "qty": s(4), "unit_price": 3200, "vendor": "Panduit", "term": "one-time", "order_sequence": 1},
                {"description": "VMware vSphere Enterprise Plus (per CPU, 3yr)", "category": "Software License", "qty": s(8), "unit_price": 5500, "vendor": "VMware / Broadcom", "term": "3-year", "order_sequence": 5},
                {"description": "Veeam Backup Enterprise (per VM, 50 VMs)", "category": "Software License", "qty": 1, "unit_price": 12000, "vendor": "Veeam", "term": "3-year", "order_sequence": 5},
                {"description": "Spares Kit: drives, NICs, PSUs (10% of hardware)", "category": "Spares", "qty": 1, "unit_price": 15000, "vendor": "Dell / Cisco", "term": "one-time", "order_sequence": 4},
                {"description": "Deployment & Commissioning Professional Services", "category": "Professional Services", "qty": 1, "unit_price": 45000, "vendor": "NTT Data", "term": "one-time", "order_sequence": 7},
            ],
            "Network & Telecom": [
                # WAN Routers (Bundle 1 — Cisco SD-WAN 8-line bundle)
                {"description": f"Cisco Catalyst 8300-1N1S-4T2X SD-WAN Router (chassis)", "category": "WAN Router", "qty": s(2), "unit_price": 12500, "vendor": vendor, "term": "one-time", "order_sequence": 2, "quantity_basis": f"2 per site × {sites} sites = {s(2)}", "ha_role": "active/standby"},
                {"description": "Cisco IOS XE SD-WAN Software License", "category": "Software License", "qty": s(2), "unit_price": 2400, "vendor": vendor, "term": "3-year", "order_sequence": 5},
                {"description": "Cisco DNA Advantage SD-WAN Subscription (per device, 3yr)", "category": "SaaS/Subscription", "qty": s(2), "unit_price": 1800, "vendor": vendor, "term": "3-year", "order_sequence": 5},
                {"description": "Cisco SmartNet SNTC-8X5XNBD Catalyst 8300 (3yr)", "category": "Support Contract", "qty": s(2), "unit_price": 2250, "vendor": vendor, "term": "3-year", "order_sequence": 6, "notes": "MANDATORY — 3yr SmartNet on every hardware unit"},
                {"description": "NIM-2T WAN Interface Module (T1/E1 or SFP)", "category": "Interface Module", "qty": s(2), "unit_price": 850, "vendor": vendor, "term": "one-time", "order_sequence": 2},
                {"description": "GLC-LH-SMD SFP Transceiver (per WAN port)", "category": "Transceiver", "qty": s(4), "unit_price": 95, "vendor": vendor, "term": "one-time", "order_sequence": 2},
                {"description": "Console Cable + Power Cord Set (per router)", "category": "Accessories", "qty": s(2), "unit_price": 45, "vendor": "CDW", "term": "one-time", "order_sequence": 1},
                {"description": "ACS-1900-RM-19 Rack Mount Kit (per router)", "category": "Accessories", "qty": s(2), "unit_price": 75, "vendor": "CDW", "term": "one-time", "order_sequence": 1},
                # Access Switches (Bundle 3 — 5-line bundle)
                {"description": "Cisco Catalyst C9300-48P-A Access Switch (48P PoE+)", "category": "LAN Switch", "qty": s(2), "unit_price": 8200, "vendor": vendor, "term": "one-time", "order_sequence": 2, "quantity_basis": f"2 per site × {sites} sites = {s(2)}", "notes": "Stack in pairs for redundancy"},
                {"description": "C9300 Network Advantage License", "category": "Software License", "qty": s(2), "unit_price": 1200, "vendor": vendor, "term": "3-year", "order_sequence": 5},
                {"description": "STACK-T1-50CM Stacking Cable Pair", "category": "Accessories", "qty": s(1), "unit_price": 220, "vendor": vendor, "term": "one-time", "order_sequence": 2},
                {"description": "Cisco SmartNet CON-3SNT-C93 (3yr, access switch)", "category": "Support Contract", "qty": s(2), "unit_price": 1476, "vendor": vendor, "term": "3-year", "order_sequence": 6},
                {"description": "SFP-10G-SR Uplink Transceivers ×2 per switch", "category": "Transceiver", "qty": s(4), "unit_price": 125, "vendor": vendor, "term": "one-time", "order_sequence": 2},
                # Firewall (Bundle 2 — condensed 5 key lines)
                {"description": "FortiGate 200F NGFW Appliance (HA pair)", "category": "Firewall", "qty": s(2), "unit_price": 14500, "vendor": "Fortinet", "term": "one-time", "order_sequence": 2, "ha_role": "active/standby"},
                {"description": "FortiGuard Enterprise Protection 3yr (IPS+URL+SSL+AppCtrl)", "category": "Security License", "qty": s(2), "unit_price": 3200, "vendor": "Fortinet", "term": "3-year", "order_sequence": 5},
                {"description": "FortiCare Premium Support 3yr (per unit)", "category": "Support Contract", "qty": s(2), "unit_price": 2600, "vendor": "Fortinet", "term": "3-year", "order_sequence": 6},
                {"description": "Deployment & Cutover Professional Services", "category": "Professional Services", "qty": 1, "unit_price": 25000, "vendor": "NTT Data", "term": "one-time", "order_sequence": 7},
            ],
            "SD-WAN": [
                {"description": "Cisco Catalyst 8300-1N1S-4T2X SD-WAN Router", "category": "WAN Router", "qty": s(2), "unit_price": 12500, "vendor": "Cisco", "term": "one-time", "order_sequence": 2, "quantity_basis": f"2 per site × {sites} sites = {s(2)}"},
                {"description": "Cisco IOS XE SD-WAN License", "category": "Software License", "qty": s(2), "unit_price": 2400, "vendor": "Cisco", "term": "3-year", "order_sequence": 5},
                {"description": "Cisco DNA Advantage Subscription (3yr)", "category": "SaaS/Subscription", "qty": s(2), "unit_price": 1800, "vendor": "Cisco", "term": "3-year", "order_sequence": 5},
                {"description": "Cisco SmartNet 3yr NBD (per router)", "category": "Support Contract", "qty": s(2), "unit_price": 2250, "vendor": "Cisco", "term": "3-year", "order_sequence": 6},
                {"description": "NIM-2T WAN Interface Module", "category": "Interface Module", "qty": s(2), "unit_price": 850, "vendor": "Cisco", "term": "one-time", "order_sequence": 2},
                {"description": "GLC-LH-SMD SFP Transceiver (×2 per router)", "category": "Transceiver", "qty": s(4), "unit_price": 95, "vendor": "Cisco", "term": "one-time", "order_sequence": 2},
                {"description": "Console Cable + Power Cord (per router)", "category": "Accessories", "qty": s(2), "unit_price": 45, "vendor": "CDW", "term": "one-time", "order_sequence": 1},
                {"description": "ACS-1900-RM-19 Rack Mount Kit", "category": "Accessories", "qty": s(2), "unit_price": 75, "vendor": "CDW", "term": "one-time", "order_sequence": 1},
                {"description": "MPLS Circuit 100Mbps Primary (monthly per site)", "category": "Carrier Circuit", "qty": s(1), "unit_price": 1800, "vendor": "AT&T / NTT", "term": "/month"},
                {"description": "Broadband 500Mbps Secondary Circuit (monthly)", "category": "Carrier Circuit", "qty": s(1), "unit_price": 350, "vendor": "Comcast / ISP", "term": "/month"},
                {"description": "OOB Console Server + LTE Modem (per remote site)", "category": "OOB Management", "qty": s(1), "unit_price": 1400, "vendor": "Opengear", "term": "one-time", "order_sequence": 1, "notes": "Mandatory: order_sequence=1 — must arrive before routers"},
                {"description": "SD-WAN Deployment Professional Services", "category": "Professional Services", "qty": 1, "unit_price": 35000, "vendor": "NTT Data", "term": "one-time", "order_sequence": 7},
            ],
            "Cybersecurity": [
                {"description": "Palo Alto PA-1410 NGFW (HA pair per site)", "category": "Firewall", "qty": s(2), "unit_price": 28000, "vendor": "Palo Alto Networks", "term": "one-time", "order_sequence": 2},
                {"description": "PA-1410 Threat Prevention + URL Filtering 3yr", "category": "Security License", "qty": s(2), "unit_price": 6500, "vendor": "Palo Alto Networks", "term": "3-year", "order_sequence": 5},
                {"description": "PAN-SVC-PREM-1410-3YR Premium Support", "category": "Support Contract", "qty": s(2), "unit_price": 5100, "vendor": "Palo Alto Networks", "term": "3-year", "order_sequence": 6},
                {"description": "CrowdStrike Falcon Complete (EDR, per endpoint/yr)", "category": "EDR", "qty": 500, "unit_price": 180, "vendor": "CrowdStrike", "term": "1-year"},
                {"description": "Splunk Enterprise Security (10GB/day indexing)", "category": "SIEM", "qty": 1, "unit_price": 95000, "vendor": "Splunk", "term": "1-year"},
                {"description": "Okta Identity Cloud SSO + MFA (per user/yr)", "category": "IAM", "qty": 500, "unit_price": 72, "vendor": "Okta", "term": "1-year"},
                {"description": "Tenable.io VM (500 assets)", "category": "Vulnerability Mgmt", "qty": 1, "unit_price": 28000, "vendor": "Tenable", "term": "1-year"},
                {"description": "Security Awareness Training KnowBe4 (per user/yr)", "category": "Training", "qty": 500, "unit_price": 15, "vendor": "KnowBe4", "term": "1-year"},
                {"description": "Incident Response Retainer (40 hrs/yr)", "category": "Managed Services", "qty": 1, "unit_price": 18500, "vendor": "NTT Data", "term": "1-year"},
                {"description": "Firewall Ruleset Migration PS", "category": "Professional Services", "qty": 1, "unit_price": 15000, "vendor": "NTT Data", "term": "one-time"},
            ],
        }

        # Use the first matching category template
        items_raw = templates.get(category)
        if not items_raw:
            # Try partial match
            for k, v in templates.items():
                if k.lower() in category.lower() or category.lower() in k.lower():
                    items_raw = v
                    break
        if not items_raw:
            items_raw = templates["Data Center / COLO"]

        items = []
        for i, t in enumerate(items_raw):
            qty = t.get("qty", 1)
            price = t.get("unit_price", 0)
            items.append({
                "line_number": i + 1,
                "description": t["description"],
                "category": t.get("category", "General"),
                "sku": "",
                "qty": qty,
                "quantity": qty,
                "unit": t.get("unit", "/unit"),
                "unit_price": price,
                "extended_price": price * qty,
                "ext_price": price * qty,
                "vendor": t.get("vendor", "CDW"),
                "term": t.get("term", "one-time"),
                "order_sequence": t.get("order_sequence", ""),
                "ha_role": t.get("ha_role", ""),
                "quantity_basis": t.get("quantity_basis", f"1 per site × {sites} sites = {sites}"),
                "notes": t.get("notes", ""),
                "price_basis": "budgetary_assumption",
                "eol_flag": False,
            })

        total = sum(i["unit_price"] * i["qty"] for i in items)
        return {
            "name": f"{project} — {category} BOM",
            "project": project,
            "category": category,
            "revision": 1,
            "bom_maturity": "budgetary",
            "line_items": items,
            "totals": {
                "hardware": total * 0.6,
                "software": total * 0.25,
                "services": total * 0.15,
                "total_otc": total,
                "tco_3year": total * 1.4,
            },
            "warnings": [
                "TEMPLATE BOM: Prices are budgetary estimates only. Validate with vendor quotes before submission.",
                "All hardware line items require SmartNet/maintenance — verify 3yr coverage.",
                "Lead-time risk: confirm Day-1 date against longest lead-time items.",
            ],
            "approvals_required": ["Buyer IT", "Seller IT", "SI Technical Team"],
        }

    # ── Deprecated shims (keep for backward compat with stream endpoint) ────

    def _detect_phase_advance(self, response: str, current_phase: int, message: str) -> int:
        """Shim: numeric phase advance for backward compat with stream_message."""
        for p in range(current_phase + 1, 11):
            if f"Phase {p}" in response or f"phase {p}" in response:
                return p
        return current_phase

    def _phase_to_progress(self, phase: int, complete: bool) -> int:
        if complete:
            return 100
        phase_map = {1: 5, 2: 15, 3: 25, 4: 35, 5: 45, 6: 55, 7: 70, 8: 80, 9: 90, 10: 95}
        return phase_map.get(phase, 5)