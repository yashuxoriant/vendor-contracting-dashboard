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
from typing import Callable, Dict, Any, Optional, Tuple, List
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
    BOMPhase.GENERATE: ["site_count", "conveyance_status"],                          # Need count + conveyance decision
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


def _parse_numeric(value: Any, default: float = 0.0) -> float:
    """
    Safely coerce a value to float, handling AI-formatted strings like '$350,720' or '1,200.50'.
    Strips currency symbols, commas, and spaces before parsing. Returns default on failure.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = str(value).replace("$", "").replace(",", "").replace(" ", "").strip()
        return float(cleaned) if cleaned else default
    except (TypeError, ValueError):
        return default


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
        qty = _parse_numeric(item.get("qty") or item.get("quantity"), default=1.0) or 1.0
        up = _parse_numeric(item.get("unit_price"), default=0.0)
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
    prior_total = _parse_numeric((bom.get("totals") or {}).get("total_otc"), default=0.0)
    if prior_total and abs(prior_total - computed_total) > 0.5:
        warnings.append(
            f"⚠️ Total corrected: previous total_otc ${prior_total:,.0f} did not match line-item sum ${computed_total:,.0f}."
        )

    totals = dict(bom.get("totals") or {})
    totals["hardware"] = round(hw, 2)
    totals["software"] = round(sw, 2)
    totals["services"] = round(svc, 2)
    totals["total_otc"] = computed_total
    totals["tco_3year"] = _parse_numeric(totals.get("tco_3year"), default=0.0) or round(computed_total * 1.4, 2)
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


def _extract_fields_from_message(message: str, agent_state: Dict, from_ai: bool = False) -> Dict:
    """
    Deterministically extract intake fields from a user message.
    Updates agent_state in-place; returns updated dict.
    Real-life example: user says "TSA exit for 10 sites, Cisco standard, Day 1 March 15"
    Set from_ai=True when processing AI response text — skips assumption extractors
    to prevent AI phrasing from poisoning user-confirmed state.
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
        elif re.search(
            r"greenfield|fresh.install|new.deploy|net.new|brand.new"
            r"|no.existing|from.scratch|new.build|brand.new.deploy",
            m,
        ):
            # Greenfield / new build — nothing to convey, buy everything new
            agent_state["conveyance_status"] = "not_conveying"
        elif re.search(r"convey|transfer|coming.with|brings.with|inheriting", m):
            if re.search(r"eol|end.of.life|eos|end.of.support|outdated|old", m):
                agent_state["conveyance_status"] = "conveying_eol"
            else:
                agent_state["conveyance_status"] = "conveying_active"
        elif re.search(r"shared|multi.tenant|common.infra", m):
            agent_state["conveyance_status"] = "shared"
        elif re.search(r"\bdedicated\b|\bstand.?alone\b|\bour.own\b|\bnew.build\b", m):
            # Dedicated sites → buyer gets own infrastructure, nothing conveying
            agent_state["conveyance_status"] = "not_conveying"

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

    # Site size / scale classification — qualitative (small / medium / large / FF)
    # Captures phrases like "small sites", "full floor", "FF", "same size" so the
    # Users / Scale intake checkbox ticks even without a numeric user count.
    if not agent_state.get("site_size"):
        if re.search(r"\bfull.?floor\b|\bff\b|\bmedium\s+(?:branch|site|office)\b", m):
            agent_state["site_size"] = "medium"
        elif re.search(r"\bsmall\s+(?:branch|site|office|format)\b|\bss\b|\bsame\s+size\b", m):
            agent_state["site_size"] = "small"
        elif re.search(r"\blarge\s+(?:branch|site|office)\b|\bheadquarters\b|\bhq\b", m):
            agent_state["site_size"] = "large"

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
            else:
                # Quarter notation: "Q3 2025", "Q4-2026", "end of Q2", "year end 2025"
                dm3 = re.search(
                    r"\bq[1-4][\s\-/]*20\d{2}\b"
                    r"|end\s+of\s+(?:q[1-4]|year|20\d{2})"
                    r"|year[\s\-]?end\s*20\d{2}",
                    m, re.I,
                )
                if dm3:
                    agent_state["required_by_date"] = dm3.group(0)

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

    # Hardware (CPE / SD-WAN / WAN layer) explicitly conveying.
    # NOTE: Only set this when the user EXPLICITLY says a hardware layer (CPE/router/SD-WAN)
    # is conveying. Do NOT auto-derive from conveyance_status — conveyance_status may refer
    # to circuits, LAN, or other layers while the CPE layer is net-new.
    if not agent_state.get("hardware_conveying"):
        if re.search(
            r"(?:cpe|router|hardware|equipment|sd.wan|wan.cpe).*convey"
            r"|convey.*(?:cpe|router|hardware|equipment|sd.wan|wan.cpe)"
            r"|existing.*cisco.*convey|convey.*existing.*cisco",
            m,
        ):
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

    # ── Assumption confirmation extractors ─────────────────────────────────────
    # These only run on USER messages. When from_ai=True (AI response processing),
    # skip entirely to prevent AI phrasing (e.g. "DNA Essentials") from being
    # treated as user confirmation and silently answering unasked questions.
    if not from_ai:
        # SFP transceiver type
        if agent_state.get("sfp_type_confirmed") is None:
            if re.search(r"\bfiber\b|\blc\b|\bsingle.mode\b|\bsmf\b|\bmmf\b|\bom\d\b", m):
                agent_state["sfp_type_confirmed"] = "fiber"
            elif re.search(r"\bcopper\b|\brj.?45\b|\bcat\s*\d\b", m):
                agent_state["sfp_type_confirmed"] = "copper"

        # Spares kit
        if agent_state.get("spares_kit_confirmed") is None:
            if re.search(r"(yes|include|add|need).{0,20}spare|(spare).{0,20}(yes|include|add|need)", m):
                agent_state["spares_kit_confirmed"] = True
            elif re.search(r"(no|exclude|skip|don.t.need).{0,20}spare|(spare).{0,20}(no|exclude|skip)", m):
                agent_state["spares_kit_confirmed"] = False

        # DNA license tier (Cisco only)
        if agent_state.get("dna_tier_confirmed") is None:
            if re.search(r"\badvantage\b", m):
                agent_state["dna_tier_confirmed"] = "advantage"
            elif re.search(r"\bessentials\b", m):
                agent_state["dna_tier_confirmed"] = "essentials"

        # Rack mount kits
        if agent_state.get("rack_kit_confirmed") is None:
            if re.search(r"(yes|include|procure|add).{0,20}rack|(rack).{0,20}(yes|include|procure)", m):
                agent_state["rack_kit_confirmed"] = True
            elif re.search(r"(no|site.provides|exclude|skip).{0,20}rack|(rack).{0,20}(no|site.provides|exclude)|site\s+provides|racks?\s+exist", m):
                agent_state["rack_kit_confirmed"] = False

        # OOB console servers
        if agent_state.get("oob_console_confirmed") is None:
            if re.search(r"(yes|include|need|add).{0,20}(oob|console.server|out.of.band)", m):
                agent_state["oob_console_confirmed"] = True
            elif re.search(r"(no|exclude|skip|separate|handled).{0,20}(oob|console.server|out.of.band)|(oob|console.server).{0,20}(no|exclude|handled)", m):
                agent_state["oob_console_confirmed"] = False

        # Smart Hands
        if agent_state.get("smart_hands_confirmed") is None:
            if re.search(r"(yes|include|need|add).{0,20}(smart.hands|on.site|install|racking)", m):
                agent_state["smart_hands_confirmed"] = True
            elif re.search(r"(no|internal|exclude|skip|handle|separate).{0,20}(smart.hands|on.site.install|racking)|(smart.hands).{0,20}(no|internal|handle)|internal\s+team|we\s+handle|handled\s+internally", m):
                agent_state["smart_hands_confirmed"] = False

        # SD-WAN controller plane — cloud-hosted vs on-prem
        if agent_state.get("controller_plane_confirmed") is None:
            if re.search(r"\bon.?prem\b|\bon.?premises\b|\bucs\b|\bhypervisor\b|\bvmware\b|\besxi\b|\bself.host", m):
                agent_state["controller_plane_confirmed"] = "on-prem"
            elif re.search(r"\bcloud.hosted\b|\bsaas\b|\bcloud\s+vmanage\b|\bcisco\s+cloud\b|\bhosted\s+by\s+cisco\b", m):
                agent_state["controller_plane_confirmed"] = "cloud"

    # Accumulate explicitly requested hardware layers across turns.
    # Stored in agent_state so scope persists through the full conversation.
    existing_layers: set = set(agent_state.get("requested_layers") or [])
    for pattern, category in _SCOPE_PATTERNS:
        if re.search(pattern, m):
            existing_layers.add(category)
    if existing_layers:
        agent_state["requested_layers"] = sorted(existing_layers)

    return agent_state


def _get_missing_fields(agent_state: Dict) -> List[str]:
    """
    Returns a list of human-readable labels for required intake fields
    that have not yet been populated in agent_state.
    Used by dynamic phase addendums to ask only what is truly missing.
    """
    _REQUIRED_LABELS = [
        ("workstream_category", "IT subcategory (Data Center / Network / Cybersecurity / etc.)"),
        ("conveyance_status",   "Is existing equipment conveying, or is this a new/greenfield build?"),
        ("site_count",         "How many sites / locations are in scope?"),
    ]
    return [
        label for field, label in _REQUIRED_LABELS
        if not agent_state.get(field)
    ]


# ── Assumption checklist — items AI commonly adds without explicit user confirmation ──
# Each entry: (agent_state_key, question_text, condition_fn)
# condition_fn(agent_state) -> bool: return True when this question is relevant
# for this specific deployment context.  Questions that evaluate to False are
# silently skipped — neither asked nor generated in the BOM.
# State values: None = not yet asked, True/str = confirmed include, False = confirmed exclude.
_ASSUMPTION_CHECKLIST: List[Tuple[str, str, Callable]] = [
    (
        "sfp_type_confirmed",
        "SFP transceivers — fiber (LC single-mode) or copper (RJ-45) handoff at each site?",
        # Only relevant when WAN routers or LAN switches are in scope
        lambda s: bool({"WAN Router", "LAN Switch"} & set(s.get("requested_layers") or [])),
    ),
    (
        "spares_kit_confirmed",
        "Spares kit (10% of device fleet) — include in BOM or exclude?",
        # Always relevant for any hardware procurement
        lambda s: True,
    ),
    (
        "dna_tier_confirmed",
        "Cisco DNA license tier — Advantage (full analytics/AIOps) or Essentials (~35% cheaper)?",
        # Only relevant for Cisco deployments
        lambda s: "cisco" in (s.get("vendor_standard") or "").lower(),
    ),
    (
        "rack_kit_confirmed",
        "Rack mount kits & cable management — procure as part of this BOM or site provides?",
        # Skip for DC/COLO — racks are always procured there, not a question
        lambda s: (s.get("workstream_category") or "").lower() not in ("data center / colo",),
    ),
    (
        "oob_console_confirmed",
        "OOB (out-of-band) console servers for remote site management — include or handled separately?",
        # Only relevant when WAN routers are in scope (branch/remote site deployments)
        lambda s: "WAN Router" in (s.get("requested_layers") or []),
    ),
    (
        "smart_hands_confirmed",
        "Smart Hands / on-site racking & installation labour — include in BOM or internal teams handle?",
        # Skip when all hardware is conveying — nothing to install
        lambda s: s.get("conveyance_status") != "conveying_active",
    ),
    (
        "controller_plane_confirmed",
        "SD-WAN controller plane — cloud-hosted (Cisco vManage SaaS) or on-prem (UCS/ESXi VM)?",
        # Only relevant for SD-WAN deployments that need a new controller
        lambda s: (
            "WAN Router" in (s.get("requested_layers") or [])
            and not s.get("hardware_conveying")
        ),
    ),
]


def _get_unconfirmed_assumptions(agent_state: Dict) -> List[Tuple[str, str]]:
    """
    Returns (field_key, question_text) pairs for assumption items not yet
    answered by the user.  Each entry's condition_fn is evaluated against the
    current agent_state — questions irrelevant to this specific deployment
    context (wrong vendor, wrong category, hardware conveying, etc.) are
    silently skipped.
    Treats True, False, and any string as 'answered' — only None means unasked.
    """
    unconfirmed: List[Tuple[str, str]] = []
    for field, question, condition_fn in _ASSUMPTION_CHECKLIST:
        if not condition_fn(agent_state):
            continue
        if agent_state.get(field) is not None:
            continue
        unconfirmed.append((field, question))
    return unconfirmed


def _extract_assumptions_from_conversation(
    conversation: List[Dict],
    agent_state: Dict,
) -> Dict:
    """
    Re-scan all user turns in the conversation for assumption answers that may
    have been given before the GENERATE phase was reached (e.g. user said
    'fiber connections' in turn 2 long before the questions were formally asked).
    Runs _extract_fields_from_message with from_ai=False on each user turn so
    only genuine user text updates assumption state — AI turns are skipped.
    Safe to call multiple times: extractors are idempotent once a field is set.

    Context-aware: checks the preceding AI turn to resolve bare "yes"/"no" bullet
    answers where the topic keyword only appears in the AI question, not the user reply.
    """
    for idx, turn in enumerate(conversation):
        if turn.get("role") != "user":
            continue
        content = (turn.get("content") or "").strip()
        if not content:
            continue

        # Find the nearest preceding AI turn for context
        prev_ai = ""
        for j in range(idx - 1, -1, -1):
            if conversation[j].get("role") in ("assistant", "ai", "AI"):
                prev_ai = (conversation[j].get("content") or "").lower()
                break

        # Detect bare "no" / "yes" lines (e.g. "- No" as a bullet point answer)
        _bare_no  = bool(re.search(r"(?m)^\s*[-•*]?\s*no\s*$",  content, re.IGNORECASE))
        _bare_yes = bool(re.search(r"(?m)^\s*[-•*]?\s*yes\s*$", content, re.IGNORECASE))

        if prev_ai:
            if agent_state.get("smart_hands_confirmed") is None:
                if re.search(r"smart.hands|installation.serv|racking.*instal|on.site.*instal|labour", prev_ai):
                    if _bare_no:
                        agent_state["smart_hands_confirmed"] = False
                    elif _bare_yes:
                        agent_state["smart_hands_confirmed"] = True

            if agent_state.get("oob_console_confirmed") is None:
                if re.search(r"oob|console.server|out.of.band", prev_ai):
                    if _bare_no:
                        agent_state["oob_console_confirmed"] = False
                    elif _bare_yes:
                        agent_state["oob_console_confirmed"] = True

            if agent_state.get("spares_kit_confirmed") is None:
                if re.search(r"spare|spares.kit", prev_ai):
                    if _bare_no:
                        agent_state["spares_kit_confirmed"] = False
                    elif _bare_yes:
                        agent_state["spares_kit_confirmed"] = True

            if agent_state.get("rack_kit_confirmed") is None:
                if re.search(r"rack.mount|cable.management|rack.kit", prev_ai):
                    if _bare_no:
                        agent_state["rack_kit_confirmed"] = False
                    elif _bare_yes:
                        agent_state["rack_kit_confirmed"] = True

            if agent_state.get("controller_plane_confirmed") is None:
                if re.search(r"vmanage|vbond|vsmart|controller.plane|sd.wan.controller", prev_ai):
                    if re.search(r"\bon.?prem\b|\bon.?premises\b|\bucs\b|\bhypervisor\b|\bvmware\b|\besxi\b", content.lower()):
                        agent_state["controller_plane_confirmed"] = "on-prem"
                    elif re.search(r"\bcloud.hosted\b|\bsaas\b|\bcloud\s+vmanage\b|\bcisco\s+cloud\b", content.lower()):
                        agent_state["controller_plane_confirmed"] = "cloud"

        agent_state = _extract_fields_from_message(content, agent_state, from_ai=False)
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
            # Only advance if not going backwards AND gate fields are satisfied
            if _PHASE_ORDER.index(phase) > _PHASE_ORDER.index(current_phase):
                gates = _PHASE_GATES.get(phase, [])
                if all(agent_state.get(g) for g in gates):
                    return phase

    # ── Implicit SIZING→GENERATE transition ─────────────────────────────────
    # When the AI is in SIZING and its response indicates scope is complete
    # (scope table, "ready to generate", "I now have everything") but no JSON
    # was emitted, advance to GENERATE so the NEXT turn injects the assumption
    # pre-check instructions and JSON schema prompt.
    if current_phase == BOMPhase.SIZING and not bom_found:
        _advance_triggers = [
            "ready to generate", "i now have everything", "all inputs confirmed",
            "scope summary", "let me compile", "generate the bom", "generating the bom",
            "let me generate", "proceed to generate", "scope is confirmed",
            "compile the draft", "compile the bom",
        ]
        if any(t in text_lower for t in _advance_triggers):
            gates = _PHASE_GATES.get(BOMPhase.GENERATE, [])
            if all(agent_state.get(g) for g in gates):
                return BOMPhase.GENERATE

    return current_phase  # stay put


def _phase_addendum(phase: BOMPhase, agent_state: Dict) -> str:
    """Return phase-specific instructions to inject into the system prompt."""
    known = {k: v for k, v in agent_state.items() if v}

    if phase == BOMPhase.INTAKE:
        known = {k: v for k, v in agent_state.items() if v}
        missing = _get_missing_fields(agent_state)
        known_lines = ""
        if known.get("workstream_category"):
            known_lines += f"\n  ✓ Category: {known['workstream_category']}"
        if known.get("project_name"):
            known_lines += f"\n  ✓ Project/client: {known['project_name']}"
        if known.get("site_count"):
            known_lines += f"\n  ✓ Sites: {known['site_count']}"
        if known.get("conveyance_status"):
            known_lines += f"\n  ✓ Conveyance: {known['conveyance_status']}"
        known_block = (f"\nALREADY KNOWN — do NOT re-ask:{known_lines}") if known_lines else ""
        if not missing:
            return (
                "\n\n[CURRENT PHASE: INTAKE — ALL KEY FIELDS KNOWN]\n"
                "ASSUME Day-1 Readiness — do NOT ask M&A phase.\n"
                f"{known_block}\n"
                "All required intake fields are captured. Acknowledge briefly and advance "
                "to ask conveyance/qualification details.\n"
                "Do NOT re-ask any of the already-known fields above."
            )
        # Build a question list only for fields that are actually missing
        ask_items = []
        if not known.get("workstream_category"):
            ask_items.append("1. Subcategory: Office/Branch/Manufacturing Site | Colo/Datacenter Hub | Cloud Network Hub?")
        if not known.get("conveyance_status") and known.get("workstream_category"):
            ask_items.append(f"{len(ask_items)+1}. Is infrastructure dedicated or shared (multi-tenant/MSP-owned)?")
        if not known.get("project_name"):
            ask_items.append(f"{len(ask_items)+1}. Project/client name?")
        ask_block = "\n".join(ask_items) if ask_items else "Proceed to qualification."
        return (
            f"\n\n[CURRENT PHASE: INTAKE]\n"
            "ASSUME Day-1 Readiness — do NOT ask M&A phase.\n"
            f"{known_block}\n"
            f"Ask ONLY the following (omit any already answered above):\n{ask_block}\n"
            "Do NOT ask about vendors, sites, or conveyance details yet."
        )

    if phase == BOMPhase.QUALIFY:
        cat = known.get("workstream_category", "Network & Telecom")
        subcategory = known.get("subcategory", "")
        missing = _get_missing_fields(agent_state)

        # Build known-fields block so AI never re-asks them
        known_lines = ""
        if known.get("workstream_category"):
            known_lines += f"\n  ✓ Category: {known['workstream_category']}"
        if known.get("conveyance_status"):
            known_lines += f"\n  ✓ Conveyance: {known['conveyance_status']}"
        if known.get("site_count"):
            known_lines += f"\n  ✓ Sites: {known['site_count']}"
        if known.get("vendor_standard"):
            known_lines += f"\n  ✓ Vendor standard: {known['vendor_standard']}"
        if known.get("site_criticality"):
            known_lines += f"\n  ✓ Criticality: {known['site_criticality']}"
        known_block = (f"ALREADY KNOWN — do NOT re-ask:{known_lines}") if known_lines else ""

        # Build the missing-fields ask list dynamically
        still_missing = [
            label for field, label in [
                ("conveyance_status", "Is existing network equipment conveying, or is this a new/greenfield build?"),
                ("site_count",        "How many sites are in scope? (used as the quantity multiplier)"),
            ]
            if not agent_state.get(field)
        ]
        if still_missing:
            ask_lines = "\n".join(f"{i+1}. {q}" for i, q in enumerate(still_missing))
            ask_block = f"Ask ONLY the following unanswered questions:\n{ask_lines}"
        else:
            ask_block = "All key qualification fields are known. Acknowledge and advance to SCOPE."

        return (
            f"\n\n[CURRENT PHASE: QUALIFICATION — {cat} / {subcategory}]\n"
            f"{known_block}\n\n"
            f"{ask_block}\n\n"
            "Conveying decision tree (for context):\n"
            "SHARED sites → buy NET NEW for all layers (router, switch, firewall, WAN-CPE, WLAN). Skip to SCOPE.\n"
            "DEDICATED sites:\n"
            "  → Is network equipment conveying? (LAN, WLAN, Firewall, WAN-CPE, on-prem WLC, NAC)\n"
            "    Note: WAN-CPE may be carrier-managed (AT&T) → return to telco, not a purchase.\n"
            "  → Are circuits conveying?\n"
            "    Circuit NOT conveying → new circuit order BOM needed.\n"
            "    Circuit conveying → contract + cutover-day changes via telco.\n"
            "  → Any EOL/EOS replacements needed?\n"
            "Typical dedicated-site BOMs: SD-WAN CPE, firewalls, EOL routers/switches/APs.\n"
            f"FULL STATE: {json.dumps(known, default=str)}"
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
            "\n"
            "⚠️  CRITICAL CONSTRAINT — DO NOT GENERATE BOM JSON IN THIS PHASE:\n"
            "After computing quantities, summarise the scope in a PLAIN TEXT table only.\n"
            "Do NOT emit a ```json block — the BOM assumption check must happen first.\n"
            "End your response by saying you are ready to generate the BOM and\n"
            "confirming the scope summary.  The orchestrator will then advance the\n"
            "phase and ask the user to confirm assumption items before generating JSON.\n"
            f"KNOWN SO FAR: {json.dumps(known, default=str)}"
        )

    if phase == BOMPhase.GENERATE:
        vendor = known.get("vendor_standard", "Cisco")
        sites = known.get("site_count", 1)
        criticality = known.get("site_criticality", "standard")
        hardware_conveying = known.get("hardware_conveying", False)
        eol_needed = known.get("eol_replacement_needed", False)
        new_circuits = known.get("new_circuits_needed", False)
        # NOTE: Do NOT auto-set hardware_conveying from conveyance_status here.
        # conveyance_status may refer to circuits/LAN layers while CPE is net-new.
        # hardware_conveying is only True when the extractor matched explicit CPE/router language.
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
        # ── PATH A: user has answered assumption questions — generate JSON now ──
        if known.get("pending_assumption_confirmation"):
            return (
                f"\n\n[CURRENT PHASE: BOM GENERATION — ASSUMPTION CONFIRMATION COMPLETE — {vendor}, {sites} sites, {criticality}]\n"
                "The user has just answered your assumption confirmation questions.\n"
                "Parse their responses carefully:\n"
                "  - Items the user said YES to (or gave a specific answer, e.g. 'fiber SFPs') →\n"
                "    include in line_items[] with qty_status='confirmed', using the detail they gave\n"
                "  - Items the user said NO to → exclude entirely from the BOM\n"
                "  - Any item still unresolved → optional_recommendations[] only,\n"
                "    recommendation_type='unconfirmed_assumption'\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "SCOPE DISCIPLINE — still applies\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Include in line_items[] ONLY: layers the user explicitly requested + items they just confirmed YES.\n"
                "  ✓ Support contract (SmartNet/FortiCare) per confirmed hardware unit\n"
                "  ✓ Software license required to operate confirmed hardware\n"
                "  ✗ Items user said NO to → excluded entirely, do not put anywhere\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Every line item MUST have qty_status='confirmed' or qty_status='calculated'.\n"
                "No qty_status='assumption' items should remain — the user resolved them all above.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "EXPAND EVERY REQUESTED COMPONENT TO ITS FULL SKU BUNDLE:\n"
                "  Router  → chassis + IOS + DNA sub (if confirmed tier) + SmartNet + WAN NIM + SFP (if confirmed) + rack kit (if confirmed)\n"
                "  Firewall → appliance + IPS + URL + SSL + AMP + HA peer + support + rack (if confirmed) + SFPs (if confirmed)\n"
                "  Switch  → chassis + license + stacking + SmartNet + SFP uplinks (if confirmed)\n"
                "  AP      → unit + PoE injector + cloud license + mounting (if confirmed)\n"
                "Output ONLY valid JSON inside ```json...``` fences.\n"
                "Each line item MUST include: qty_status, quantity_basis, ha_role (if HA pair), price_basis, order_sequence.\n"
                "NEVER output a single generic line like 'Cisco Router' — that fails the Vendor-Ready BOM Gate.\n"
                f"KNOWN SO FAR: {json.dumps(known, default=str)}"
            )

        # ── PATH B: first entry into GENERATE — ask only unresolved assumption items ──
        unconfirmed = _get_unconfirmed_assumptions(agent_state)
        if not unconfirmed:
            # All assumption items already answered in conversation — generate immediately
            confirmed_summary = []
            for field, question, _ in _ASSUMPTION_CHECKLIST:
                val = agent_state.get(field)
                if val is not None:
                    confirmed_summary.append(f"  ✓ {question.split('—')[0].strip()}: {val}")
            confirmed_block = "\n".join(confirmed_summary) if confirmed_summary else ""
            return (
                f"\n\n[CURRENT PHASE: BOM GENERATION — ALL ASSUMPTIONS RESOLVED — {vendor}, {sites} sites, {criticality}]\n"
                "All assumption items were confirmed during earlier qualification. Generate the BOM now.\n"
                f"CONFIRMED ASSUMPTIONS:\n{confirmed_block}\n\n"
                "Include in line_items[] ONLY: layers explicitly requested + confirmed assumption items.\n"
                "Every line item MUST have qty_status='confirmed' or qty_status='calculated'.\n"
                "Output ONLY valid JSON inside ```json...``` fences.\n"
                "Each line item MUST include: qty_status, quantity_basis, ha_role (if HA pair), price_basis, order_sequence.\n"
                f"KNOWN SO FAR: {json.dumps(known, default=str)}"
            )

        # Build numbered question list from only unresolved items
        questions_block = "\n".join(
            f"  {i+1}. {question}"
            for i, (_, question) in enumerate(unconfirmed)
        )
        return (
            f"\n\n[CURRENT PHASE: BOM GENERATION — ASSUMPTION PRE-CHECK — {vendor}, {sites} sites, {criticality}]\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "MANDATORY: CONFIRM THE FOLLOWING ITEMS BEFORE GENERATING BOM\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Before emitting any BOM JSON you MUST do the following ON THIS TURN:\n"
            "1. Start your response with the EXACT token on its own line: [ASSUMPTION_CHECK]\n"
            "   The orchestrator uses this token to hold BOM generation until the user replies.\n"
            "2. Ask the user ONLY the following unresolved questions (these are the items not yet\n"
            "   confirmed in this conversation — do NOT re-ask anything already answered above):\n"
            f"{questions_block}\n"
            "3. Ask the user to reply with a yes/no or specific detail for each number.\n"
            "4. Do NOT emit any BOM JSON on this turn — wait for the user to answer.\n\n"
            "After the user replies, the system enters ASSUMPTION CONFIRMATION COMPLETE mode\n"
            "and you generate the full BOM honouring their answers.\n\n"
            "SCOPE DISCIPLINE (applied after confirmation):\n"
            "  ✓ Layers the user explicitly requested in conversation\n"
            "  ✓ Items the user confirms YES to (with their specified details)\n"
            "  ✗ Items the user says NO to → excluded from BOM entirely\n"
            "  ✗ Items still unresolved → optional_recommendations[] only\n"
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

        # ── Hard assumption pre-gate (fires BEFORE AI call) ──────────────────
        # Re-scan the full conversation so assumption answers given in early turns
        # (before GENERATE phase was reached) are captured in agent_state.
        # Then: if any assumption items are still unconfirmed, return the question
        # list directly — the AI is never called until all items are resolved.
        # assumptions_gate_passed=True means the user has already answered this
        # cycle; skip the gate so BOM revisions don't re-trigger it.
        #
        # Restricted to SIZING and GENERATE phases only — the gate must NOT fire
        # during QUALIFY or SCOPE. The AI still needs to ask about conveyance
        # details, cutover dates, and scope of other network layers before
        # assumption items become relevant. Firing too early causes assumption
        # questions to appear before the user has finished basic qualification.
        _bom_ready_to_generate = (
            bool(agent_state.get("site_count"))
            and bool(agent_state.get("conveyance_status"))
            and current_phase in (BOMPhase.SIZING, BOMPhase.GENERATE)
        )
        if (
            _bom_ready_to_generate
            and not agent_state.get("pending_assumption_confirmation")
            and not agent_state.get("assumptions_gate_passed")
            and not agent_state.get("pending_change_request")
        ):
            agent_state = _extract_assumptions_from_conversation(
                session.get("conversation", []), agent_state
            )
            _pre_unconfirmed = _get_unconfirmed_assumptions(agent_state)
            if _pre_unconfirmed:
                agent_state["pending_assumption_confirmation"] = True
                _q_block = "\n".join(
                    f"{i+1}. {q}" for i, (_, q) in enumerate(_pre_unconfirmed)
                )
                _gate_response = (
                    "Before I generate the BOM, I need to confirm a few things with you:\n\n"
                    + _q_block
                    + "\n\nPlease reply with yes/no or a specific detail for each number."
                )
                context["agent_state"] = agent_state
                context["current_phase_name"] = current_phase.value
                context["current_phase"] = _PHASE_ORDER.index(current_phase) + 1
                logger.info(
                    "AssumptionPreGate: intercepted GENERATE — %d unconfirmed items, skipping AI call",
                    len(_pre_unconfirmed),
                )
                return _gate_response, None, _PHASE_PROGRESS.get(current_phase, 80), False

        # ── Call AI ────────────────────────────────────────────────────────
        response_text = call_ai(msgs, system=system)
        if response_text is None:
            user_turns = sum(1 for m in history if m.get("role") == "user")
            response_text = self._rule_based(category, current_phase, message, agent_state, user_turns)

        # ── Post-process ───────────────────────────────────────────────────
        # Detect assumption pre-check: AI outputs [ASSUMPTION_CHECK] token to signal
        # it needs the user to confirm/deny assumed items before generating JSON.
        # Hold BOM generation on this turn; resume when user replies.
        if "[ASSUMPTION_CHECK]" in response_text:
            agent_state["pending_assumption_confirmation"] = True
            # Strip the token so the user only sees the clean question text
            response_text = response_text.replace("[ASSUMPTION_CHECK]", "").strip()
            partial_bom, bom_found = None, False
        else:
            # ── Assumption safety net ────────────────────────────────────────────
            # Guard against the AI ignoring the [ASSUMPTION_CHECK] instruction and
            # jumping straight to BOM JSON generation.  When we're in GENERATE phase,
            # the user has NOT yet answered assumption questions, AND the AI produced
            # JSON anyway — strip the JSON and force the assumption pre-check.
            # This prevents SFPs, spares, DNA tier, rack kits, OOB consoles, and
            # Smart Hands from silently appearing in the BOM without user sign-off.
            _safety_net_fired = False
            if (
                not agent_state.get("pending_assumption_confirmation")
                and not agent_state.get("assumptions_gate_passed")
                and not agent_state.get("pending_change_request")
                and re.search(r"```json", response_text)
            ):
                _unconfirmed_safety = _get_unconfirmed_assumptions(agent_state)
                if _unconfirmed_safety:
                    logger.info(
                        "AssumptionSafetyNet: AI skipped [ASSUMPTION_CHECK] in GENERATE phase "
                        "— stripping BOM JSON and enforcing pre-check (%d unconfirmed items)",
                        len(_unconfirmed_safety),
                    )
                    response_text = re.sub(r"```json[\s\S]*?```", "", response_text).strip()
                    agent_state["pending_assumption_confirmation"] = True
                    if not response_text:
                        _q_block = "\n".join(
                            f"{i+1}. {q}" for i, (_, q) in enumerate(_unconfirmed_safety)
                        )
                        response_text = (
                            "Before I generate the BOM, I need to confirm a few items "
                            "with you:\n\n" + _q_block +
                            "\n\nPlease reply with yes/no or a specific detail for each number."
                        )
                    partial_bom, bom_found = None, False
                    _safety_net_fired = True

            if not _safety_net_fired:
                if agent_state.get("pending_assumption_confirmation"):
                    # User has now replied to the assumption questions — clear the flag.
                    # _phase_addendum will enter PATH A (confirmation-complete) on next call.
                    # Set assumptions_gate_passed so the pre-gate does not re-trigger
                    # on subsequent GENERATE calls (e.g. BOM revisions).
                    agent_state["pending_assumption_confirmation"] = False
                    agent_state["assumptions_gate_passed"] = True
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
        # Extract core fields (site count, vendor, etc.) the AI may have echoed back.
        # Pass from_ai=True to skip assumption extractors — AI phrasing must not
        # be treated as user confirmation of SFPs, spares, DNA tier, etc.
        agent_state = _extract_fields_from_message(response_text, agent_state, from_ai=True)
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

        # ── Universal assumption gate ─────────────────────────────────────────
        # Any line item where qty_status="assumption" means the AI added it without
        # explicit user confirmation. Move ALL such items to optional_recommendations[]
        # regardless of category. This is the principle-based enforcement — no
        # pattern-matching needed; it catches SFPs, Smart Hands, and anything else
        # in future that the AI marks as an assumption.
        confirmed_items = [i for i in data["line_items"] if i.get("qty_status") != "assumption"]
        assumed_items   = [i for i in data["line_items"] if i.get("qty_status") == "assumption"]
        if assumed_items:
            optional = data.setdefault("optional_recommendations", [])
            for item in assumed_items:
                optional.append({
                    "description":           item.get("description", ""),
                    "category":              item.get("category", ""),
                    "sku":                   item.get("sku", ""),
                    "qty":                   item.get("qty"),
                    "vendor":                item.get("vendor", ""),
                    "estimated_unit_price":  item.get("unit_price"),
                    "recommendation_reason": (
                        item.get("notes")
                        or "Included as an assumption — not explicitly confirmed in conversation."
                    ),
                    "recommendation_type":   "unconfirmed_assumption",
                })
            data["line_items"] = confirmed_items
            data.setdefault("warnings", []).append(
                f"ℹ️ {len(assumed_items)} assumption item(s) moved to Optional Recommendations "
                "— confirm with the user before adding to the ordered BOM."
            )
            logger.info(
                "AssumptionGate: moved %d item(s) to optional_recommendations: %s",
                len(assumed_items),
                [i.get("description", "") for i in assumed_items],
            )

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
        # Only True when extractor matched explicit CPE/router conveying language.
        hardware_conveying = agent_state.get("hardware_conveying", False)
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
