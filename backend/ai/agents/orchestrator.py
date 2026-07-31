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
    BOMPhase.QUALIFY:  ["workstream_category"],                                     # Need category (ma_phase assumed Day-1)
    BOMPhase.SCOPE:    ["conveyance_status"],                                       # Need conveying decision
    BOMPhase.SIZING:   ["site_count"],                                              # Need site count
    BOMPhase.GENERATE: ["site_count"],                                              # Need count (date optional)
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


# ── Dependency Model & Validator ────────────────────────────────────────────

_BOM_DEPENDENCY_RULES: Dict[str, Dict[str, Any]] = {
    "WAN Router": {
        "children": ["Software License", "SaaS/Subscription", "Support Contract", "Interface Module", "Transceiver", "Accessories", "Spares"],
        "mandatory_support": True,
        "spare_policy": 0.10,
    },
    "Firewall": {
        "children": ["Security License", "Software License", "Support Contract", "Transceiver", "Accessories", "Spares"],
        "mandatory_support": True,
        "spare_policy": 0.10,
    },
    "LAN Switch": {
        "children": ["Software License", "Support Contract", "Transceiver", "Accessories", "Spares"],
        "mandatory_support": True,
        "spare_policy": 0.10,
    },
    "Access Point": {
        "children": ["Software License", "SaaS/Subscription", "Accessories", "Spares"],
        "mandatory_support": False,
        "spare_policy": 0.10,
    },
    "Compute": {
        "children": ["Software License", "Support Contract", "Spares"],
        "mandatory_support": True,
        "spare_policy": 0.10,
    },
    "Storage": {
        "children": ["Software License", "Support Contract", "Spares"],
        "mandatory_support": True,
        "spare_policy": 0.10,
    },
    "Network": {
        "children": ["Support Contract", "Transceiver", "Accessories", "Spares"],
        "mandatory_support": True,
        "spare_policy": 0.10,
    },
}

_HARDWARE_CATEGORIES = {
    "WAN Router", "Firewall", "LAN Switch", "Access Point", "Compute", "Storage", "Network",
    "Power & Physical", "Interface Module", "Transceiver", "Accessories", "Spares", "WAN Circuit",
}
_SOFTWARE_CATEGORIES = {"Software License", "Security License", "SaaS/Subscription"}
_SERVICE_CATEGORIES = {"Support Contract", "Professional Services", "Managed Services", "Training", "Contingency"}

# ── Scope vocabulary: maps user intent keywords → canonical hardware category names ─────
# Vendor-agnostic — patterns match procurement concepts, not brand names.
# Used by both _extract_scope_from_conversation() and _enforce_bom_scope().
_SCOPE_PATTERNS: List[Tuple[str, str]] = [
    (r"\bfirewall|ngfw|utm|next.gen.firewall\b",                      "Firewall"),
    (r"\bwan.router|wan.cpe|branch.router\b",                         "WAN Router"),
    (r"\bsd.?wan\b",                                                   "WAN Router"),
    (r"\blan.switch|access.switch|campus.switch|switching\b",         "LAN Switch"),
    (r"\baccess.point|wireless.ap|\bwlan\b|\bwifi\b",                  "Access Point"),
    (r"\bserver|compute|blade|rack.server\b",                         "Compute"),
    (r"\bstorage|san|nas|all.flash|flash.array\b",                    "Storage"),
    (r"\bcircuit|broadband|mpls|wan.link|internet.link\b",           "WAN Circuit"),
    (r"\bups|power.distribution|\bpdu\b",                             "Power & Physical"),
    (r"\brack|cabinet\b",                                              "Power & Physical"),
]

# Dependency categories — always permitted when their parent hardware is in scope.
# These are never treated as independent scope additions.
_DEPENDENCY_CATEGORIES: set = {
    "Software License", "Security License", "SaaS/Subscription",
    "Support Contract", "Interface Module", "Transceiver", "Accessories", "Spares",
}

# Service categories — always kept regardless of hardware scope.
_ALWAYS_IN_SCOPE_CATEGORIES: set = {
    "Professional Services", "Managed Services", "Training", "Contingency",
}


def _extract_scope_from_conversation(
    conversation: List[Dict],
    agent_state: Dict,
) -> Dict[str, Any]:
    """
    Scan all user-role turns in the conversation to determine which hardware
    categories the user explicitly named.

    Returns:
        {
          "requested_categories": set[str],  e.g. {"Firewall"}
          "scope_explicit":       bool        True when ≥1 layer keyword found
        }

    Only user turns count — AI response text never sets scope.
    agent_state["requested_layers"] is used as a seed (accumulated per turn).
    """
    requested: set = set(agent_state.get("requested_layers") or [])
    for turn in conversation:
        if turn.get("role") != "user":
            continue
        text = (turn.get("content") or "").lower()
        for pattern, category in _SCOPE_PATTERNS:
            if re.search(pattern, text):
                requested.add(category)
    return {
        "requested_categories": requested,
        "scope_explicit": len(requested) > 0,
    }


def _enforce_bom_scope(
    bom: Dict[str, Any],
    scope: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Deterministic post-AI scope gate.

    Moves hardware line items that fall outside the user's requested scope from
    line_items[] into optional_recommendations[].  Dependency items (licenses,
    SmartNet, accessories, spares) follow their parent hardware — they are only
    moved when their parent was also moved.

    Rules:
    1. If scope_explicit is False (no layer keyword detected), skip enforcement
       entirely — safe default when user intent is ambiguous.
    2. Hardware in requested_categories → stays in line_items[].
    3. Hardware NOT in requested_categories → moved to optional_recommendations[]
       with recommendation_type="out_of_scope".
    4. Dependency items are classified by tracing qty_driver, dependencies[],
       and description keywords back to their parent hardware category.
    5. Professional Services, Managed Services, Training, Contingency → always kept.

    Mutates bom in-place.  Returns bom.
    """
    if not scope.get("scope_explicit"):
        return bom
    requested: set = scope.get("requested_categories", set())
    if not requested:
        return bom

    items = bom.get("line_items") or []
    optional = list(bom.get("optional_recommendations") or [])

    # ── Pass 1: classify hardware items ──────────────────────────────
    in_scope_hw: set = set()
    out_of_scope_hw: set = set()
    for item in items:
        cat = (item.get("category") or "").strip()
        ln = item.get("line_number")
        if cat in _ALWAYS_IN_SCOPE_CATEGORIES or cat in _DEPENDENCY_CATEGORIES:
            continue  # resolved in pass 2
        if cat not in _HARDWARE_CATEGORIES:
            in_scope_hw.add(ln)  # unknown category → keep
            continue
        if cat in requested:
            in_scope_hw.add(ln)
        else:
            out_of_scope_hw.add(ln)

    # Build lookup: line_number → category for out-of-scope hardware
    oos_cats: Dict[int, str] = {
        item.get("line_number"): (item.get("category") or "")
        for item in items
        if item.get("line_number") in out_of_scope_hw
    }

    # ── Pass 2: classify dependency items by tracing to parent hardware ────
    in_scope_dep: set = set()
    out_of_scope_dep: set = set()
    for item in items:
        cat = (item.get("category") or "").strip()
        ln = item.get("line_number")
        if cat not in _DEPENDENCY_CATEGORIES:
            continue

        driver = (item.get("qty_driver") or "").strip().lower()
        dep_lines = item.get("dependencies") or []
        desc = (item.get("description") or "").lower()

        driver_in = (
            any(driver in r.lower() or r.lower() in driver for r in requested)
            if driver else False
        )
        deps_in  = any(d in in_scope_hw for d in dep_lines) if dep_lines else False
        desc_in  = any(
            re.search(p, desc) for p, c in _SCOPE_PATTERNS if c in requested
        )
        driver_out = (
            any(driver in c.lower() or c.lower() in driver for c in oos_cats.values())
            if driver else False
        )
        deps_out = any(d in out_of_scope_hw for d in dep_lines) if dep_lines else False

        if driver_in or deps_in or desc_in:
            in_scope_dep.add(ln)
        elif (driver_out or deps_out) and not driver_in and not deps_in:
            out_of_scope_dep.add(ln)
        else:
            in_scope_dep.add(ln)  # ambiguous → keep

    # ── Pass 3: split line_items ───────────────────────────────────
    out_all = out_of_scope_hw | out_of_scope_dep
    kept: List[Dict] = []
    moved_count = 0
    for item in items:
        ln = item.get("line_number")
        if ln in out_all:
            optional.append({
                "description":           item.get("description", ""),
                "category":              (item.get("category") or "").strip(),
                "sku":                   item.get("sku", ""),
                "qty":                   item.get("qty"),
                "vendor":                item.get("vendor", ""),
                "estimated_unit_price":  item.get("unit_price"),
                "recommendation_reason": (
                    f"Not in requested scope — user specified: "
                    f"{', '.join(sorted(requested))}. Add explicitly if needed."
                ),
                "recommendation_type":   "out_of_scope",
            })
            moved_count += 1
        else:
            kept.append(item)

    if moved_count:
        bom.setdefault("warnings", [])
        bom["warnings"].append(
            f"ℹ️ Scope filter: {moved_count} line item(s) moved to Optional Recommendations "
            f"— outside requested scope ({', '.join(sorted(requested))})."
        )
        logger.info(
            "ScopeEnforcer: moved %d items to optional_recommendations (requested=%s)",
            moved_count, sorted(requested),
        )

    bom["line_items"] = kept
    bom["optional_recommendations"] = optional
    return bom


def _validate_bom_dependencies(bom: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Deterministic post-processing pass for LLM-generated BOM JSON.
    Ensures quantity/price/totals consistency and emits warnings for orphan or missing dependencies.
    """
    items = bom.get("line_items") or []
    warnings = list(bom.get("warnings") or [])
    if not items:
        bom["warnings"] = warnings
        return bom, warnings

    # 1) Recompute line extended prices and normalise qty
    for item in items:
        qty = item.get("qty") or item.get("quantity") or 1
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            qty = 1.0
        up = item.get("unit_price") or 0
        try:
            up = float(up)
        except (TypeError, ValueError):
            up = 0.0
        item["qty"] = qty
        item["quantity"] = qty
        item["unit_price"] = up
        item["extended_price"] = round(qty * up, 2)
        item["ext_price"] = item["extended_price"]

    # 2) Build parent indices and enrich dependencies[]
    parent_lines: Dict[str, List[int]] = {}
    for item in items:
        cat = (item.get("category") or "").strip()
        if cat in _BOM_DEPENDENCY_RULES:
            parent_lines.setdefault(cat, []).append(int(item.get("line_number") or 0))

    for item in items:
        deps = item.get("dependencies")
        if not isinstance(deps, list):
            deps = []
        cat = (item.get("category") or "").strip()
        driver = (item.get("qty_driver") or "").strip().lower()
        if cat not in _BOM_DEPENDENCY_RULES and not deps and driver:
            for pcat, lines in parent_lines.items():
                pcat_l = pcat.lower()
                if driver in pcat_l or pcat_l in driver:
                    deps = lines
                    break
        item["dependencies"] = deps

    # 3) Orphan / mandatory dependency warnings
    hardware_present = {((item.get("category") or "").strip()) for item in items if (item.get("category") or "").strip() in _BOM_DEPENDENCY_RULES}

    for item in items:
        cat = (item.get("category") or "").strip()
        if cat in {"Software License", "Security License", "SaaS/Subscription", "Support Contract"}:
            if not item.get("dependencies") and not item.get("qty_driver"):
                warnings.append(
                    f"⚠️ Dependency warning: '{item.get('description','')}' (line {item.get('line_number')}) has no traceable hardware parent."
                )

    for pcat in hardware_present:
        rule = _BOM_DEPENDENCY_RULES.get(pcat, {})
        if not rule.get("mandatory_support"):
            continue
        covered = False
        for item in items:
            if (item.get("category") or "") != "Support Contract":
                continue
            text = f"{item.get('description','')} {item.get('qty_driver','')}".lower()
            if pcat.lower() in text or "router" in text and "router" in pcat.lower() or "firewall" in text and "firewall" in pcat.lower() or "switch" in text and "switch" in pcat.lower():
                covered = True
                break
        if not covered:
            warnings.append(
                f"⚠️ Missing mandatory support: hardware category '{pcat}' has no matching support contract line."
            )

    # 4) Recompute totals deterministically
    hw = sw = svc = 0.0
    for item in items:
        ep = float(item.get("extended_price") or 0)
        cat = (item.get("category") or "").strip()
        if cat in _SOFTWARE_CATEGORIES:
            sw += ep
        elif cat in _SERVICE_CATEGORIES:
            svc += ep
        else:
            hw += ep

    computed_total = round(hw + sw + svc, 2)
    prior_total = float((bom.get("totals") or {}).get("total_otc") or 0)
    if prior_total and abs(prior_total - computed_total) > 0.5:
        warnings.append(
            f"⚠️ Total corrected: previous total_otc ${prior_total:,.0f} did not match line-item sum ${computed_total:,.0f}."
        )

    totals = dict(bom.get("totals") or {})
    totals["hardware"] = round(hw, 2)
    totals["software"] = round(sw, 2)
    totals["services"] = round(svc, 2)
    totals["total_otc"] = computed_total
    totals["tco_3year"] = totals.get("tco_3year") or round(computed_total * 1.4, 2)
    bom["totals"] = totals
    bom["warnings"] = warnings
    return bom, warnings


def _retrieve_bom_context(query: str, bom_id: Optional[str] = None, top_k: int = 5, category: Optional[str] = None, vendor: Optional[str] = None) -> str:
    """Search indexed BOMs for relevant chunks to inject into the system prompt."""
    try:
        from services.search_service import search_bom_context, category_to_index_name
        index_name = category_to_index_name(category)
        results = search_bom_context(
            query=query,
            top_k=top_k,
            bom_id=bom_id,
            index_name=index_name,
            vendor=vendor,
        )
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

    # New WAN circuits required — distinct from hardware procurement
    if not agent_state.get("new_circuits_needed"):
        if re.search(
            r"new circuit|order circuit|procure circuit|circuit.required|circuit.needed"
            r"|new.*wan.*circuit|wan.*circuit.*new|broadband.*required|new.*broadband"
            r"|need.*circuit|circuits.*procure",
            m,
        ):
            agent_state["new_circuits_needed"] = True

    # Hardware (CPE / SD-WAN / WAN layer) explicitly conveying
    if not agent_state.get("hardware_conveying"):
        if re.search(
            r"(?:cpe|router|hardware|equipment|sd.wan|wan.cpe).*convey"
            r"|convey.*(?:cpe|router|hardware|equipment|sd.wan|wan.cpe)"
            r"|existing.*cisco.*convey|convey.*existing.*cisco",
            m,
        ):
            agent_state["hardware_conveying"] = True
        # Also set when conveyance_status is conveying_active and category contains SD-WAN/Network
        elif agent_state.get("conveyance_status") == "conveying_active":
            agent_state["hardware_conveying"] = True

    # EOL replacement explicitly needed
    if not agent_state.get("eol_replacement_needed"):
        if re.search(
            r"eol|end.of.life|eos|end.of.support|needs.replacement|replace.*hardware"
            r"|hardware.*replace|outdated",
            m,
        ):
            agent_state["eol_replacement_needed"] = True
        elif agent_state.get("conveyance_status") == "conveying_eol":
            agent_state["eol_replacement_needed"] = True

    # No other network layers to procure (switches, APs, firewalls)
    if not agent_state.get("no_other_layers"):
        if re.search(
            r"no other|no lan|no ap|no firewall|no switch|no access.point"
            r"|circuits.only|only.circuits|just.circuits"
            r"|nothing.else|no.additional.hardware|no.other.hardware",
            m,
        ):
            agent_state["no_other_layers"] = True

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

    # Accumulate explicitly requested hardware layers across turns.
    # Stored in agent_state so scope persists through the full conversation.
    existing_layers: set = set(agent_state.get("requested_layers") or [])
    for pattern, category in _SCOPE_PATTERNS:
        if re.search(pattern, m):
            existing_layers.add(category)
    if existing_layers:
        agent_state["requested_layers"] = sorted(existing_layers)

    return agent_state


def _is_change_request(message: str) -> bool:
    """Return True when the user asks to modify an already-generated BOM."""
    m = message.lower()
    return bool(re.search(
        r"remove|don.t need|not needed|only need|update|change|replace"
        r"|add |without|skip|exclude|drop|revise|rebuild|regenerate"
        r"|redo|re-generate|re-build|also not needed|we don|we do not"
        r"|scratch that|forget the|take out|leave out|modify",
        m,
    ))


def _is_regen_confirmation(message: str) -> bool:
    """Return True when the user confirms generating the revised BOM now."""
    m = message.lower().strip()
    return bool(re.search(
        r"^(yes|yep|yeah|confirm|confirmed|proceed|go ahead|do it|generate|regenerate|"
        r"create|build|apply|submit|ok|okay)\b"
        r"|\b(generate|regenerate|create|build).*(now|bom)\b"
        r"|\b(go ahead|proceed)\b",
        m,
    ))


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
        # If we were already post-generation, this is a revision pass.
        if current_phase in (BOMPhase.VALIDATE, BOMPhase.COMPLETE):
            return BOMPhase.COMPLETE
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
            "ASSUME Day-1 Readiness — do NOT ask M&A phase.\n"
            "Ask ONLY (in one message):\n"
            "1. Subcategory: Office/Branch/Manufacturing Site | Colo/Datacenter Hub | Cloud Network Hub?\n"
            "2. Is infrastructure dedicated or shared (multi-tenant/MSP-owned)?\n"
            "3. Project/client name (if not already known).\n"
            "Do NOT ask about vendors, sites, or conveyance yet."
        )

    if phase == BOMPhase.QUALIFY:
        cat = known.get("workstream_category", "Network & Telecom")
        subcategory = known.get("subcategory", "")
        return (
            f"\n\n[CURRENT PHASE: QUALIFICATION — {cat} / {subcategory}]\n"
            "Follow the skill's conveying decision tree:\n"
            "SHARED sites → buy NET NEW for all layers (router, switch, firewall, WAN-CPE, WLAN). Skip to SCOPE.\n"
            "DEDICATED sites:\n"
            "  → Is network equipment conveying? (LAN, WLAN, Firewall, WAN-CPE, on-prem WLC, NAC)\n"
            "    Note: WAN-CPE may be carrier-managed (AT&T) → return to telco, not a purchase.\n"
            "  → Are circuits conveying?\n"
            "    Circuit NOT conveying → new circuit order BOM needed.\n"
            "    Circuit conveying → contract + cutover-day changes via telco.\n"
            "  → Any EOL/EOS replacements needed?\n"
            "Typical dedicated-site BOMs: SD-WAN CPE, firewalls, EOL routers/switches/APs.\n"
            f"KNOWN SO FAR: {json.dumps(known, default=str)}"
        )

    if phase == BOMPhase.SCOPE:
        conveyance = known.get("conveyance_status", "unknown")
        return (
            f"\n\n[CURRENT PHASE: SCOPE — conveyance={conveyance}]\n"
            "Collect (ask in one message, only what is still unknown):\n"
            "1. Number of sites — this is the MULTIPLIER for all quantities.\n"
            "2. Technology/vendor in place — like-for-like or new post-cutover standard?\n"
            "   Rule: conveying + NOT EOL → keep it, no BOM. Not conveying + standard exists → use standard.\n"
            "   Pick per layer: LAN switching, wireless, SD-WAN/WAN-CPE, firewall (e.g. Cisco, Meraki, VeloCloud).\n"
            "   No reference BOM for that technology → say so, offer ~4 typical line items from comparable vendor.\n"
            "3. Site address + local IT contact (for shipping and smart-hands BOM).\n"
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
        hardware_conveying = known.get("hardware_conveying", False)
        eol_needed = known.get("eol_replacement_needed", False)
        new_circuits = known.get("new_circuits_needed", False)
        # Also honour conveyance_status if hardware_conveying wasn't set explicitly
        if not hardware_conveying and known.get("conveyance_status") == "conveying_active":
            hardware_conveying = True
        if not eol_needed and known.get("conveyance_status") == "conveying_eol":
            eol_needed = True

        # ── CONVEYANCE GUARD ──────────────────────────────────────────────────
        # When hardware is conveying AND not EOL, NO hardware should be procured.
        # Only WAN circuits (if new_circuits_needed) or minimal integration services.
        if hardware_conveying and not eol_needed:
            if new_circuits:
                return (
                    f"\n\n[CURRENT PHASE: BOM GENERATION — WAN CIRCUITS ONLY — {sites} sites]\n"
                    "⚠️  CONVEYANCE GUARD ACTIVE: Existing hardware (SD-WAN CPE, routers, licenses,"
                    " controllers) is CONVEYING and NOT EOL. This is confirmed by the qualification answers.\n\n"
                    "DO NOT generate any of the following — they already exist:\n"
                    "  ✗ Router / WAN-CPE chassis\n"
                    "  ✗ IOS XE / SD-WAN software licenses\n"
                    "  ✗ DNA / vManage / Catalyst Center subscriptions\n"
                    "  ✗ SmartNet / maintenance contracts for conveyed hardware\n"
                    "  ✗ NIM modules, SFP transceivers, rack kits, cable kits\n"
                    "  ✗ Spare routers or spare PSUs\n"
                    "  ✗ Deployment professional services for conveyed equipment\n\n"
                    f"GENERATE ONLY WAN circuit procurement for {sites} sites (carrier: open/competitive):\n"
                    f"  1. Broadband Internet Circuit      qty_driver=Site  driver_count={sites}  qty_per_driver=1\n"
                    f"  2. Circuit Installation Charge     qty_driver=Site  driver_count={sites}  qty_per_driver=1\n"
                    f"  3. Carrier Activation Fee          qty_driver=Site  driver_count={sites}  qty_per_driver=1\n"
                    f"  4. ISP Router/CPE (carrier-managed) qty_driver=Site driver_count={sites}  qty_per_driver=1  (if carrier-provided)\n"
                    f"  5. Project Management              qty_driver=Project  driver_count=1\n"
                    f"  6. Implementation Support          qty_driver=Project  driver_count=1\n"
                    f"  7. Contingency (10%)               qty_driver=Project  driver_count=1\n\n"
                    "Output ONLY valid JSON inside ```json...``` fences.\n"
                    "Each line item MUST include qty_driver, driver_count, qty_per_driver, qty_basis, qty_status.\n"
                    f"KNOWN SO FAR: {json.dumps(known, default=str)}"
                )
            else:
                return (
                    f"\n\n[CURRENT PHASE: BOM GENERATION — INTEGRATION SERVICES ONLY — {sites} sites]\n"
                    "⚠️  CONVEYANCE GUARD ACTIVE: All equipment is conveying and NOT EOL."
                    " No circuits and no new hardware are required.\n\n"
                    "DO NOT generate hardware, licenses, SmartNet, or circuit line items.\n"
                    "Generate ONLY minimal integration/transition services (if applicable):\n"
                    "  - Cutover coordination / change management\n"
                    "  - Contract transfer management (carrier, maintenance reassignment)\n"
                    "  - Project management (optional)\n"
                    "If there is genuinely nothing to procure, output a BOM with a single\n"
                    "'No procurement required — all equipment conveying' informational line.\n\n"
                    "Output ONLY valid JSON inside ```json...``` fences.\n"
                    f"KNOWN SO FAR: {json.dumps(known, default=str)}"
                )
        # ── STANDARD HARDWARE GENERATION ────────────────────────────────────
        # When triggered by a confirmed change request, inject full dependency-analysis header.
        pending_change = known.get("pending_change_request", "")
        if pending_change:
            snapshot = known.get("current_bom_snapshot") or {}
            snapshot_text = json.dumps(snapshot, default=str)
            return (
                f"\n\n[CURRENT PHASE: BOM REVISION — DEPENDENCY-AWARE REGENERATION — {vendor}, {sites} sites, {criticality}]\n"
                f"CONFIRMED CHANGE REQUEST: \"{pending_change}\"\n\n"
                "CURRENT BOM SNAPSHOT (source of truth for revision):\n"
                f"{snapshot_text}\n\n"
                "MANDATORY — perform these steps IN ORDER before emitting JSON:\n\n"
                "STEP 1 — IMPACT ANALYSIS\n"
                "  For every directly modified item, identify ALL dependent items:\n"
                "  • Hardware chassis → licenses, subscriptions, SmartNet, accessories, HA peer, spares\n"
                "  • Quantity change → cascade qty = new_count × qty_per_driver to ALL dependent lines\n"
                "  • Removal → remove chassis AND every line whose qty_driver is that hardware\n"
                "  • Addition → add chassis AND generate full bundle (license + SmartNet + accessories)\n"
                "  • Spares kit → recalculate as 10% of the NEW hardware fleet count\n\n"
                "STEP 2 — RECALCULATE QUANTITIES & PRICES\n"
                "  • extended_price = qty × unit_price — recalculate for every changed line\n"
                "  • Recompute totals: hardware, software, services, total_otc, tco_3year\n"
                "  • Update qty_basis with the new derivation sentence\n\n"
                "STEP 3 — CONSISTENCY VALIDATION\n"
                "  • Every hardware unit must have a support/maintenance line\n"
                "  • No orphaned licenses or contracts for removed hardware\n"
                "  • No stale quantities from the pre-revision BOM\n"
                "  • Increment revision number by 1\n\n"
                "STEP 4 — EMIT REVISED BOM JSON + CHANGE SUMMARY\n"
                "  Output valid JSON inside ```json...``` fences FIRST.\n"
                "  After JSON, summarise: lines removed | lines added | lines recalculated\n"
                "  Flag any new warnings (HA incomplete, spares below 10%, lead-time risk).\n"
                "  SCOPE DISCIPLINE: only add new items the user explicitly requested —\n"
                "  surface any unrequested additions in optional_recommendations[] instead.\n\n"
                "Each line item MUST include: qty_driver, driver_count, qty_per_driver,\n"
                "qty_basis, qty_status, quantity_basis, ha_role (if HA pair), price_basis, order_sequence.\n"
                f"KNOWN SO FAR: {json.dumps(known, default=str)}"
            )
        return (
            f"\n\n[CURRENT PHASE: BOM GENERATION — {vendor}, {sites} sites, {criticality}]\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "SCOPE DISCIPLINE — READ BEFORE GENERATING\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Include in line_items[] ONLY the hardware/software layers the user\n"
            "explicitly requested in the conversation. Do NOT add extra layers.\n"
            "  ✗ If user asked for firewalls only → no routers, no switches, no APs\n"
            "  ✗ If user asked for SD-WAN CPE only → no firewalls, no LAN switches\n"
            "  ✗ If user asked for EDR only → no SIEM, no PAM, no email security\n"
            "  ✗ Do NOT add FortiManager, FortiAnalyzer, vManage, Catalyst Center,\n"
            "    or any management/orchestration platform unless the user named it\n"
            "Mandatory dependencies of REQUESTED hardware ARE allowed in line_items[]:\n"
            "  ✓ Support contract (SmartNet/FortiCare) per requested hardware unit\n"
            "  ✓ Software license required to operate the requested hardware\n"
            "  ✓ Physical accessories (rack kit, cables, SFPs) per requested unit\n"
            "  ✓ Spares kit (10% of requested fleet)\n"
            "Any additional items you think are useful → put in optional_recommendations[]\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "EXPAND EVERY REQUESTED COMPONENT TO ITS FULL SKU BUNDLE:\n"
            "  Router  → 8 lines  (chassis + IOS + DNA subscription + SmartNet + WAN NIM + SFP + cables + rack kit)\n"
            "  Firewall → 10 lines (appliance + IPS + URL + SSL + AMP + HA peer + support + rack + SFPs)\n"
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

    if phase == BOMPhase.COMPLETE:
        known_json = json.dumps(known, default=str)
        pending = known.get("pending_bom_regen", False)
        pending_msg = known.get("pending_change_request", "")
        if pending:
            return (
                "\n\n[CURRENT PHASE: POST-BOM EDIT CONFIRMATION]\n"
                "A change request has been captured and must be confirmed before regenerating BOM JSON.\n\n"
                "For this turn, do NOT emit JSON.\n"
                "1. Acknowledge the requested changes in 1-2 lines.\n"
                "2. Briefly state which dependent items will also be affected (e.g. removing a router\n"
                "   will also remove its license, SmartNet, accessories, and spare entry).\n"
                "3. Ask exactly one confirmation question:\n"
                "   'I've applied the dependency impact analysis. Would you like me to generate the\n"
                "    updated BOM now, or would you like to make any additional changes first?'\n"
                "4. Do NOT emit BOM JSON on this turn — wait for user confirmation.\n\n"
                f"PENDING CHANGE REQUEST: {pending_msg}\n"
                f"KNOWN SO FAR: {known_json}"
            )
        return (
            "\n\n[CURRENT PHASE: POST-BOM Q&A / EDIT MODE]\n"
            "A BOM has already been generated for this session.\n\n"
            "RULES:\n"
            "1. If the user asks a QUESTION (why a line item exists, pricing basis, etc.), answer directly.\n"
            "   Do NOT regenerate the BOM for question-only turns.\n\n"
            "2. If the user requests a CHANGE (remove/add/update/replace/not needed/only need),\n"
            "   acknowledge the requested changes and ask for confirmation before BOM regeneration.\n"
            "   Do NOT output revised BOM JSON until the user confirms generate/regenerate.\n\n"
            "3. Do NOT restart qualification or ask initial intake questions again.\n"
            "   Use the existing session context and current BOM as source of truth.\n\n"
            f"KNOWN SO FAR: {known_json}"
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
        # Assume Day-1 — skill says never ask M&A phase
        if not agent_state.get("ma_phase"):
            agent_state["ma_phase"] = "Day-1 Readiness"
        # Use category from session context as ground truth
        if category and not agent_state.get("workstream_category"):
            agent_state["workstream_category"] = category

        # Post-BOM edit flow (2-step):
        # 1) capture change request and ask for confirmation (no regenerate yet)
        # 2) regenerate only after explicit confirmation
        if current_phase in (BOMPhase.VALIDATE, BOMPhase.COMPLETE):
            if _is_change_request(message) and not _is_regen_confirmation(message):
                agent_state["pending_bom_regen"] = True
                agent_state["pending_change_request"] = message.strip()
                current_phase = BOMPhase.COMPLETE
                logger.info(
                    "Orchestrator: change request captured in phase=%s, awaiting confirmation",
                    phase_str,
                )
            elif agent_state.get("pending_bom_regen") and _is_regen_confirmation(message):
                current_phase = BOMPhase.GENERATE
                logger.info(
                    "Orchestrator: regeneration confirmed in phase=%s, resetting to GENERATE",
                    phase_str,
                )

        # ── Build system prompt ───────────────────────────────────────
        base_prompt = get_system_prompt(category)
        bom_id = context.get("bom_id")
        vendor = agent_state.get("vendor_standard") or None
        bom_rag = _retrieve_bom_context(message, bom_id=bom_id, category=category, vendor=vendor)

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

        # -- Scope enforcement - deterministic post-AI filter -----------------------
        # Runs on every generated BOM before display or persistence.
        # Out-of-scope hardware is moved to optional_recommendations[], not deleted.
        if partial_bom and bom_found:
            _scope = _extract_scope_from_conversation(
                session.get("conversation", []), agent_state
            )
            partial_bom = _enforce_bom_scope(partial_bom, _scope)
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

        complete = (new_phase == BOMPhase.COMPLETE) or (
            bom_found and new_phase in (BOMPhase.VALIDATE, BOMPhase.COMPLETE)
        )
        progress = _PHASE_PROGRESS.get(new_phase, 10)

        if complete and partial_bom:
            previous_snapshot = agent_state.get("current_bom_snapshot") or {}
            previous_revision = int(previous_snapshot.get("revision") or 0)
            has_pending_change = bool(agent_state.get("pending_change_request"))

            # Ensure revision increments on confirmed modification cycles.
            if has_pending_change:
                current_rev = int(partial_bom.get("revision") or 0)
                if current_rev <= previous_revision:
                    partial_bom["revision"] = previous_revision + 1
                    partial_bom.setdefault("warnings", []).append(
                        f"⚠️ Revision auto-corrected to Rev {previous_revision + 1} for confirmed change request."
                    )

            # Inject final enrichments
            partial_bom["project"] = project
            partial_bom["category"] = category
            partial_bom["ma_phase"] = agent_state.get("ma_phase", "")
            partial_bom["vendor_standard"] = agent_state.get("vendor_standard", "")
            partial_bom["site_count"] = agent_state.get("site_count")
            partial_bom["conveyance_status"] = agent_state.get("conveyance_status", "")

            # Persist current BOM snapshot so future revisions are context-accurate.
            agent_state["current_bom_snapshot"] = {
                "name": partial_bom.get("name", ""),
                "revision": partial_bom.get("revision", 1),
                "line_items": partial_bom.get("line_items", []),
                "totals": partial_bom.get("totals", {}),
            }

            # Clear pending regen state after successful revised BOM generation.
            agent_state.pop("pending_bom_regen", None)
            agent_state.pop("pending_change_request", None)

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
                "dependencies":   item.get("dependencies", []),
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
        # Preserve optional_recommendations if the AI emitted them — do not merge into line_items
        if "optional_recommendations" in data and isinstance(data["optional_recommendations"], list):
            data["optional_recommendations"] = data["optional_recommendations"]
        else:
            data.setdefault("optional_recommendations", [])
        data, _ = _validate_bom_dependencies(data)
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

        # ── Conveyance guard — use circuits-only template when hardware is conveying ──
        hardware_conveying = (
            agent_state.get("hardware_conveying", False)
            or agent_state.get("conveyance_status") == "conveying_active"
        )
        eol_needed = (
            agent_state.get("eol_replacement_needed", False)
            or agent_state.get("conveyance_status") == "conveying_eol"
        )
        new_circuits = agent_state.get("new_circuits_needed", False)

        if hardware_conveying and not eol_needed and new_circuits:
            # Circuits-only scenario: procure WAN broadband only
            circuit_price = 350   # broadband /month indicative
            install_price = 500   # one-time install per site
            activation_price = 250
            items_raw = [
                {"description": f"Broadband Internet Circuit (per site/month — competitive ISP)", "category": "WAN Circuit", "qty": sites, "unit_price": circuit_price, "vendor": "TBD — Competitive", "term": "/month", "order_sequence": 1},
                {"description": "Circuit Installation Charge (per site, one-time)", "category": "WAN Circuit", "qty": sites, "unit_price": install_price, "vendor": "TBD — Competitive", "term": "one-time", "order_sequence": 1},
                {"description": "Carrier Activation Fee (per site, one-time)", "category": "WAN Circuit", "qty": sites, "unit_price": activation_price, "vendor": "TBD — Competitive", "term": "one-time", "order_sequence": 1},
                {"description": "ISP-Managed CPE / Modem (carrier-provided, per site)", "category": "WAN Circuit", "qty": sites, "unit_price": 0, "vendor": "TBD — Competitive", "term": "one-time", "order_sequence": 1, "notes": "Carrier-managed — confirm whether included in circuit cost"},
                {"description": "Project Management — Circuit Procurement", "category": "Professional Services", "qty": 1, "unit_price": 4500, "vendor": "Internal / NTT Data", "term": "one-time", "order_sequence": 2},
                {"description": "Implementation Support — Circuit Cutover Coordination", "category": "Professional Services", "qty": 1, "unit_price": 3500, "vendor": "Internal / NTT Data", "term": "one-time", "order_sequence": 2},
                {"description": "Contingency (10% of circuit costs)", "category": "Contingency", "qty": 1, "unit_price": int((circuit_price + install_price + activation_price) * sites * 0.1), "vendor": "—", "term": "one-time", "order_sequence": 3},
            ]
            # Build items directly and return — skip the normal template lookup
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
                    "vendor": t.get("vendor", "TBD"),
                    "term": t.get("term", "one-time"),
                    "order_sequence": t.get("order_sequence", ""),
                    "ha_role": "",
                    "quantity_basis": f"{sites} Sites × 1 per Site" if qty == sites else "Project-level",
                    "qty_driver": "Site" if qty == sites else "Project",
                    "driver_count": sites if qty == sites else 1,
                    "qty_per_driver": 1,
                    "qty_status": "confirmed",
                    "notes": t.get("notes", ""),
                    "price_basis": "budgetary_assumption",
                    "eol_flag": False,
                })
            total = sum(i["unit_price"] * i["qty"] for i in items)
            return {
                "name": f"{project} — WAN Circuits BOM (Conveying CPE)",
                "project": project,
                "category": category,
                "revision": 1,
                "bom_maturity": "budgetary",
                "conveyance_note": "SD-WAN CPE is conveying and not EOL. This BOM covers WAN circuit procurement only.",
                "line_items": items,
                "totals": {
                    "hardware": 0,
                    "software": 0,
                    "services": 8000,
                    "total_otc": total,
                    "tco_3year": total + (circuit_price * sites * 36),
                },
                "warnings": [
                    "TEMPLATE BOM: Prices are budgetary estimates only. Validate with carrier quotes.",
                    "SD-WAN CPE is conveying — no router/license/SmartNet procurement required.",
                    "Confirm SmartNet contract transfer for conveyed Cisco hardware with deal team.",
                    "Broadband circuit lead time: 4–8 weeks. Order before Day-1 minus 10 weeks.",
                ],
                "approvals_required": ["Buyer IT", "Seller IT", "SI Technical Team"],
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
