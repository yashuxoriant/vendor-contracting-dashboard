"""
framework/agents/state.py
─────────────────────────
Domain-agnostic LangGraph state definition for the BOM creation workflow.

Each node in the graph receives the full BOMGraphState and returns a partial
dict that LangGraph merges (last-write-wins for scalar fields).
"""

from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class BOMGraphState(TypedDict, total=False):
    """
    Mutable state that flows through the BOM creation LangGraph.

    Fields
    ──────
    session_doc     Full session document as a plain dict (from Cosmos / mock).
    message         The current user message being processed.
    category        BOM category string (e.g. "Data Center / COLO").

    system_prompt   Assembled system prompt string (set by build_context node).
    messages        List of {role, content} dicts to send to the LLM.

    response_text   Raw text returned by the LLM (or rule-based fallback).
    bom_data        Parsed BOM JSON dict if a complete BOM was detected, else None.
    complete        True when a valid BOM JSON block was detected and parsed.
    progress        Integer 0–100 representing pipeline progress.
    used_fallback   True when the rule-based fallback was used instead of the LLM.
    """

    # ── Input fields ────────────────────────────────────────────────────────
    session_doc: dict[str, Any]
    message: str
    category: str

    # ── LLM call fields (populated by build_context) ────────────────────────
    system_prompt: str
    messages: list[dict[str, str]]

    # ── Output fields (populated by extract_bom / rule_fallback / compute_progress)
    response_text: str
    bom_data: Optional[dict[str, Any]]
    complete: bool
    progress: int
    used_fallback: bool

    # ── Extraction fields (populated by state_extraction node — Step 10) ───
    extracted_state: Optional[dict[str, Any]]  # merged BOM decision fields
