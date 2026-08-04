"""
framework/agents/supervisor.py
──────────────────────────────
Domain-agnostic conditional-edge (routing) functions for LangGraph graphs.

These functions inspect BOMGraphState and return the name of the next node,
allowing LangGraph's conditional_edges to branch the graph.
"""

from __future__ import annotations


def route_after_llm(state: dict) -> str:
    """
    Conditional edge executed after the call_llm node.

    Returns
    ───────
    "extract_bom"   — LLM produced a non-empty response; attempt JSON extraction.
    "rule_fallback" — LLM returned nothing (no credentials / timeout); use
                      rule-based response instead.
    """
    if state.get("response_text", "").strip():
        return "extract_bom"
    return "rule_fallback"
