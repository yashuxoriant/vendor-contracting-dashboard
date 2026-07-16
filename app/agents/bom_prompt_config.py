"""
app/agents/bom_prompt_config.py — BOM domain prompt configuration.

Architecture
────────────
The BOM creation agent is a two-tier design:

  Tier 1 — BOM Agent (orchestrator)
    System prompt = Shared.md + BOMAgent.md
    Drives the 13-step intake pipeline (Steps 1–8):
      ask M&A phase → category → vendor qualification → generic fields → completeness check
    Does NOT generate BOM line items itself.

  Tier 2 — Category Skill File (specialist)
    Injected into the system prompt at Step 9 when intake is substantially complete.
    Drives BOM generation for the specific category
    (Skill_DataCenter.md, Skill_Network_Telecom.md, etc.)

  Transition trigger:
    When the extracted agent_state covers ≥ INTAKE_SUFFICIENT_FIELDS from
    BOM_EXTRACTION_DECISION_KEYS, the skill file is injected and Claude
    switches from "ask intake questions" mode to "generate BOM" mode.

Public API:
  make_prompt_config(session_doc, *, skill_text, ...) → PromptConfig
  make_session_block(session_doc)  → str
  build_bom_context(loaded_bom)    → str
  CATEGORY_ADDENDA                 → dict (kept for backward-compat)
"""

from __future__ import annotations

import json
from typing import Any

from framework.agents.prompt_builder import PromptConfig
from app.memory_config import step_label, missing_decision_keys, BOM_EXTRACTION_DECISION_KEYS

# Minimum number of intake fields that must be known before the skill file is
# injected.  15 total keys; requiring 10 allows up to 5 unknowns (flagged as
# assumptions) — consistent with BOMAgent.md Step 7 rule.
INTAKE_SUFFICIENT_FIELDS: int = 10


# ---------------------------------------------------------------------------
# Re-export so callers can import everything from one place
# ---------------------------------------------------------------------------

__all__ = [
    "INTAKE_SUFFICIENT_FIELDS",
    "build_bom_context",
    "make_session_block",
    "make_prompt_config",
    "is_intake_complete",
]


# ---------------------------------------------------------------------------
# BOM context block builder
# ---------------------------------------------------------------------------


def build_bom_context(loaded_bom: dict[str, Any]) -> str:
    """
    Render a structured "LOADED BOM" context block from *loaded_bom*.

    Pre-computes totals, category breakdown, vendor breakdown, and ranked
    item list so the LLM never needs to perform arithmetic.  Numbers are
    always provided as pre-computed values with an explicit RULE comment.

    Returns empty string if *loaded_bom* is falsy.
    """
    if not loaded_bom:
        return ""

    items: list[dict] = loaded_bom.get("lineItems", [])

    lines = "\n".join(
        f"  {i.get('lineNo', '?')}. [{i.get('category', '')}] {i.get('description', '')} "
        f"| qty:{i.get('qty', 1)} "
        f"| unit_price:${i.get('unitPrice', 0):,.2f} "
        f"| LINE_TOTAL:${i.get('extPrice', 0):,.2f} "
        f"| vendor:{i.get('vendor', '')}"
        for i in items
    )

    grand_total: float = sum(i.get("extPrice") or 0 for i in items)

    by_category: dict[str, float] = {}
    by_vendor: dict[str, float] = {}
    for i in items:
        cat = i.get("category") or "Other"
        ven = i.get("vendor") or "Unknown"
        ext = i.get("extPrice") or 0
        by_category[cat] = by_category.get(cat, 0) + ext
        by_vendor[ven] = by_vendor.get(ven, 0) + ext

    cat_breakdown = "\n".join(
        f"    {c}: ${v:,.0f}"
        for c, v in sorted(by_category.items(), key=lambda x: -x[1])
    )
    ven_breakdown = "\n".join(
        f"    {v}: ${s:,.0f}"
        for v, s in sorted(by_vendor.items(), key=lambda x: -x[1])
    )
    ranked = sorted(items, key=lambda x: x.get("extPrice") or 0, reverse=True)
    ranking = "\n".join(
        f"    {idx + 1}. {i.get('description', '')} — ${i.get('extPrice', 0):,.0f} "
        f"(vendor:{i.get('vendor', '')})"
        for idx, i in enumerate(ranked)
    )

    sep = "=" * 60
    return (
        f"\n\n{sep}\nLOADED BOM — ANSWER ALL QUESTIONS USING THIS DATA\n{sep}\n"
        f"Name: {loaded_bom.get('name', '')}\n"
        f"Status: {loaded_bom.get('status', '')}\n"
        f"Version: v{loaded_bom.get('version', 1)}\n"
        f"GRAND TOTAL (pre-computed): ${grand_total:,.0f}\n"
        f"Item Count: {len(items)}\n\n"
        f"SPEND BY CATEGORY (pre-computed, do not recalculate):\n{cat_breakdown}\n\n"
        f"SPEND BY VENDOR (pre-computed, do not recalculate):\n{ven_breakdown}\n\n"
        f"ITEMS RANKED BY LINE_TOTAL HIGH to LOW (pre-computed):\n{ranking}\n\n"
        f"RULE: For ALL numeric questions use ONLY the pre-computed values above. "
        f"Do NOT recalculate.\n\n"
        f"FULL LINE ITEMS (for detail questions):\n{lines}\n"
    )


# ---------------------------------------------------------------------------
# Session block builder
# ---------------------------------------------------------------------------


def is_intake_complete(agent_state: dict) -> bool:
    """Return True when enough intake fields are known to invoke the skill file."""
    missing = missing_decision_keys(agent_state)
    return len(missing) <= (len(BOM_EXTRACTION_DECISION_KEYS) - INTAKE_SUFFICIENT_FIELDS)


def make_session_block(session_doc: dict[str, Any]) -> str:
    """
    Render the "CURRENT SESSION" context block injected into every LLM call.

    Shows:
      - Category, project, M&A phase
      - Current pipeline step (from agent_state)
      - Collected intake fields (known vs. still missing)
      - Loaded BOM context if present
    """
    context: dict = session_doc.get("context") or {}
    agent_state: dict = context.get("agent_state") or {}

    category   = context.get("category") or "Data Center / COLO"
    project    = (context.get("requirements") or {}).get("project") or "New Project"
    phase      = context.get("current_phase") or 1

    current_step = agent_state.get("current_step") or "01_ma_phase"

    lines: list[str] = [
        f"Category: {category}",
        f"Project:  {project}",
        f"BOM Pipeline Step: {current_step} — {step_label(current_step)}",
    ]

    # When the domain was pre-selected from the UI picker, Step 2 is already done.
    # Tell the agent to skip "what category are you in?" and go straight to Step 3.
    domain_preselected = context.get("domain_preselected", False)
    if domain_preselected:
        lines.append(
            f"\nDOMAIN PRE-SELECTED BY USER: '{category}' was chosen from the domain picker before "
            f"this session started. BOMAgent pipeline steps are adjusted:\n"
            f"  - Step 1 (M&A Phase): Still required — ask if not yet answered.\n"
            f"  - Step 2 (Category): ALREADY CONFIRMED = '{category}'. Do NOT ask again.\n"
            f"  - Step 3+ onward: Proceed with {category}-specific qualification questions.\n"
            f"Do not ask 'what technology category' or 'what type of BOM' — it is already set."
        )

    # Show collected intake fields so the agent doesn't re-ask answered questions
    known_fields = {
        k: v for k, v in agent_state.items()
        if k in BOM_EXTRACTION_DECISION_KEYS and v is not None
    }
    missing = missing_decision_keys(agent_state)

    if known_fields:
        lines.append("\nCOLLECTED INTAKE FIELDS (do NOT re-ask these):")
        for k, v in known_fields.items():
            lines.append(f"  ✓ {k}: {v}")

    if missing:
        lines.append("\nSTILL MISSING (ask about these next, max 3 per turn):")
        for k in missing[:6]:  # show first 6 only to keep context tight
            lines.append(f"  ✗ {k}")

    # Loaded BOM context (for review/analysis mode)
    loaded_bom = (context.get("requirements") or {}).get("loaded_bom")
    bom_context = build_bom_context(loaded_bom)

    session_block = "\n".join(lines)
    if bom_context:
        session_block += bom_context

    return session_block


# ---------------------------------------------------------------------------
# Generic intake package builder (injected with skill file at Step 9)
# ---------------------------------------------------------------------------

def _build_intake_package(agent_state: dict) -> str:
    """
    Render the structured intake package that BOMAgent Step 9 passes to the
    skill file.  Only included in the prompt when intake is complete.
    """
    fields = {k: agent_state.get(k) for k in BOM_EXTRACTION_DECISION_KEYS}
    return (
        "\n\n════════════════════════════════════════════════════\n"
        "INTAKE PACKAGE — passed from BOM Agent to Skill File\n"
        "════════════════════════════════════════════════════\n"
        + json.dumps(fields, indent=2, default=str)
        + "\n\nInstruction: Use the above intake package to generate "
          "the complete category BOM. Follow the Skill File methodology exactly."
    )


# ---------------------------------------------------------------------------
# make_prompt_config  — the single public entry point
# ---------------------------------------------------------------------------


def make_prompt_config(
    session_doc: dict[str, Any],
    *,
    skill_text: str = "",
    history_window: int = 14,
    system_as_first_message: bool = False,
    force_generation: bool = False,
) -> PromptConfig:
    """
    Build a :class:`PromptConfig` ready for :func:`build_llm_messages`.

    Two-tier prompt design
    ──────────────────────
    Tier 1 (always active):
      base_system = Shared.md + BOMAgent.md
      Drives the 13-step intake pipeline — asks questions, tracks fields.

    Tier 2 (active once intake is substantially complete):
      skill_block = category skill file (e.g. Skill_DataCenter.md)
      Plus the collected intake package so the skill has full context.
      Claude switches from "asking mode" to "BOM generation mode".

    Parameters
    ----------
    session_doc:
        Raw Cosmos session document with at least ``context.category``.
    skill_text:
        Content of the resolved category skill .md file.
        Loaded by the caller via ``framework.instructions.store.load_skill()``.
    history_window:
        Number of most-recent conversation turns to include (default 14).
    system_as_first_message:
        Set True for OpenAI o-series models (no system role support).
    force_generation:
        When True, skip the intake field-count check and inject the skill
        file regardless of how many fields have been extracted.  Set by the
        endpoint when the user sends an explicit confirmation word after the
        Step 7 intake summary (e.g. "confirmed", "yes", "looks good").
        Also injects a STEP 9 directive that overrides the Skill File's own
        "ask Phase 1 questions first" instruction so the LLM generates the
        BOM JSON immediately rather than re-asking intake questions already
        gathered during BOMAgent Steps 1-7.
    """
    # ── Tier 1 base: Shared.md + BOMAgent.md ────────────────────────────
    from framework.instructions.store import (    # noqa: PLC0415
        load_shared_instructions,
        load_bom_agent_instructions,
    )
    shared_text    = load_shared_instructions()
    bom_agent_text = load_bom_agent_instructions()
    base_system    = shared_text + "\n\n" + bom_agent_text

    # ── Determine intake completeness ────────────────────────────────────
    context: dict = session_doc.get("context") or {}
    agent_state: dict = context.get("agent_state") or {}
    intake_done = is_intake_complete(agent_state) or force_generation

    # ── Tier 2: inject skill + intake package only when intake is done ───
    if intake_done and skill_text:
        intake_pkg      = _build_intake_package(agent_state)
        effective_skill = skill_text + intake_pkg
    elif intake_done and not skill_text:
        # No skill file mapped for this category yet — still include the
        # intake package so the LLM has the collected fields and falls back
        # to its embedded JSON format rules for generation.
        effective_skill = _build_intake_package(agent_state)
    else:
        effective_skill = ""   # intake still in progress — orchestrator mode only

    # ── Step 9 generation directive ──────────────────────────────────────
    # Skill_*.md files say "Do NOT generate the BOM on the first response —
    # always ask Phase 1 questions first."  When intake is already complete
    # (BOMAgent Steps 1-7 done + user confirmed), suppress that instruction
    # so the LLM outputs the BOM JSON immediately instead of re-asking.
    # Placed at the END of base_system for highest effective priority.
    generation_directive = ""
    if intake_done:
        generation_directive = (
            "\n\n" + "=" * 52 + "\n"
            "STEP 9 ACTIVATED - BOM GENERATION MODE\n"
            + "=" * 52 + "\n"
            "The user has confirmed the intake summary (BOMAgent Step 7 complete).\n"
            "All qualifying fields are in the INTAKE PACKAGE below.\n\n"
            "MANDATORY DIRECTIVE (overrides ALL other instructions above):\n"
            "- Do NOT ask Phase 1, 2, 3, 4, or 5 questions -- already answered.\n"
            "- Do NOT ask any further intake questions. Generate the BOM now.\n"
            "- Disregard BOMAgent.md rule 'you do not generate line items' --\n"
            "  that governs Steps 1-8 only; you are now operating as the Skill File.\n"
            "- Your FIRST output must be the COMPLETE BOM JSON inside ```json...``` fences.\n"
            "- After the closing ``` fence, write a 4-6 sentence plain-English summary:\n"
            "  1. What was sized and why  2. Key risks/warnings\n"
            "  3. Next approval step  4. What would trigger a cycle restart.\n"
            "IMPORTANT: Output the ```json...``` block FIRST. If you output prose first\n"
            "without the JSON block, the BOM will not appear in the user's panel."
        )
        # Append directive to base_system (highest priority — LLM reads
        # the system prompt top-to-bottom; final instructions dominate)
        base_system = base_system + generation_directive

    # ── Session block ────────────────────────────────────────────────────
    session_block = make_session_block(session_doc)

    return PromptConfig(
        base_system=base_system,
        session_block=session_block,
        skill_block=effective_skill,
        history_window=history_window,
        system_as_first_message=system_as_first_message,
    )
