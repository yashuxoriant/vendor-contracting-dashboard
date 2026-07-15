"""
app/agents/bom_creation_agent.py
─────────────────────────────────
LangGraph-based BOM creation workflow for one conversational turn.

Graph topology
──────────────
    START
      │
      ▼
  build_context ── loads skill instructions, assembles LLM messages
      │
      ▼
  call_llm ── async call via framework/agents/llm_client.py (acall_llm)
      │
      ├─ has response? ──► extract_bom ── parse ```json...``` block
      │                        │
      └─ empty response? ──► rule_fallback ── BOMOrchestrator._rule_based()
                               │
                               ▼
                         compute_progress ── integer 0–100
                               │
                               ▼
                         state_extraction ── heuristic + LLM field extraction (Step 10)
                               │
                              END

Public interface
────────────────
    agent = BOMCreationAgent()
    response_text, bom_data, progress, complete = await agent.run(session_doc, message)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys

# ── Ensure project root is on sys.path ────────────────────────────────────
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root not in sys.path:
    sys.path.insert(0, _root)

from langgraph.graph import END, START, StateGraph

from framework.agents.state import BOMGraphState
from framework.agents.supervisor import route_after_llm

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Node: build_context
# ─────────────────────────────────────────────────────────────────────────────

async def _build_context_node(state: BOMGraphState) -> dict:
    """
    Load category skill instructions and assemble the LLM message list.
    Relies on:
        app.agents.bom_prompt_config.make_prompt_config
        framework.agents.prompt_builder.build_llm_messages
        framework.instructions.store.load_skill
    """
    from app.agents.bom_prompt_config import make_prompt_config          # noqa: PLC0415
    from framework.agents.prompt_builder import build_llm_messages       # noqa: PLC0415
    from framework.instructions.store import load_skill                  # noqa: PLC0415

    session_doc: dict = state["session_doc"]
    category: str = (
        state.get("category")
        or session_doc.get("context", {}).get("category", "Data Center / COLO")
    )

    skill_text = load_skill(category)
    config = make_prompt_config(session_doc, skill_text=skill_text)
    system_prompt, messages = build_llm_messages(config, session_doc)

    return {
        "category": category,
        "system_prompt": system_prompt,
        "messages": messages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node: call_llm
# ─────────────────────────────────────────────────────────────────────────────

async def _call_llm_node(state: BOMGraphState) -> dict:
    """
    Call the LLM (non-streaming) and store the response text.
    Falls back gracefully to an empty string on error — route_after_llm
    will then divert to rule_fallback.
    """
    from framework.agents.llm_client import acall_llm  # noqa: PLC0415

    try:
        response_text = await acall_llm(
            state["messages"],
            state["system_prompt"],
        )
    except Exception as exc:
        logger.warning("acall_llm raised an exception: %s", exc)
        response_text = ""

    return {"response_text": response_text or ""}


# ─────────────────────────────────────────────────────────────────────────────
# Node: extract_bom
# ─────────────────────────────────────────────────────────────────────────────

def _extract_bom_node(state: BOMGraphState) -> dict:
    """
    Scan response_text for a ```json...``` BOM block.
    Sets bom_data + complete flags.
    """
    text: str = state.get("response_text", "")
    bom_data = None
    complete = False

    match = re.search(r"```json\s*([\s\S]*?)```", text)
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if "line_items" in parsed and parsed["line_items"]:
                bom_data = parsed
                complete = True
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    return {"bom_data": bom_data, "complete": complete, "used_fallback": False}


# ─────────────────────────────────────────────────────────────────────────────
# Node: rule_fallback
# ─────────────────────────────────────────────────────────────────────────────

def _rule_fallback_node(state: BOMGraphState) -> dict:
    """
    Generate a rule-based response when the LLM returns nothing.
    Uses BOMOrchestrator._rule_based() — the existing production fallback.
    """
    try:
        from ai.agents.orchestrator import BOMOrchestrator  # noqa: PLC0415

        session_doc: dict = state["session_doc"]
        category: str = state.get("category", "Data Center / COLO")
        phase: int = session_doc.get("context", {}).get("current_phase", 1) or 1
        history: list = session_doc.get("conversation", [])
        user_turns = sum(1 for m in history if m.get("role") == "user")

        orch = BOMOrchestrator()
        fallback_text = orch._rule_based(category, phase, state["message"], user_turns)
    except Exception as exc:
        logger.warning("Rule-based fallback also failed: %s", exc)
        fallback_text = (
            "I'm unable to connect to the AI service right now. "
            "Please verify your API credentials and try again."
        )

    return {
        "response_text": fallback_text,
        "bom_data": None,
        "complete": False,
        "used_fallback": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node: compute_progress
# ─────────────────────────────────────────────────────────────────────────────

def _compute_progress_node(state: BOMGraphState) -> dict:
    """
    Calculate integer progress (0–100) based on conversation depth and
    whether a complete BOM was produced.
    """
    session_doc: dict = state["session_doc"]
    category: str = state.get("category", "Data Center / COLO")
    complete: bool = state.get("complete", False)

    history: list = session_doc.get("conversation", [])
    user_count = sum(1 for m in history if m.get("role") == "user")

    if complete:
        progress = 100
    elif category == "Data Center / COLO":
        progress = min(90, user_count * 9)
    else:
        progress = min(90, user_count * 18)

    return {"progress": progress}


# ─────────────────────────────────────────────────────────────────────────────
# Node: state_extraction  (Step 10)
# ─────────────────────────────────────────────────────────────────────────────

async def _state_extraction_node(state: BOMGraphState) -> dict:
    """
    Extract structured BOM decision fields from the conversation so far.

    Uses:
      framework/agents/state_extractor.py  (heuristic + LLM strategies)
      app/agents/bom_extraction_config.py  (BOM_EXTRACTION_SCHEMA)

    The extracted fields are merged into session_doc["context"]["agent_state"]
    so they persist across turns (via the outer session Cosmos update in chat.py).
    Only None-valued fields from prior turns are re-attempted.
    """
    from app.agents.bom_extraction_config import BOM_EXTRACTION_SCHEMA  # noqa: PLC0415
    from framework.agents.state_extractor import aextract              # noqa: PLC0415

    session_doc: dict = state["session_doc"]
    conversation: list = session_doc.get("conversation", [])

    # Prior extracted state (from earlier turns stored in Cosmos)
    existing_agent_state: dict = (
        session_doc.get("context", {}).get("agent_state") or {}
    )

    try:
        extracted = await aextract(
            conversation=conversation,
            schema=BOM_EXTRACTION_SCHEMA,
            existing_state=existing_agent_state,
            use_llm=True,
        )
    except Exception as exc:
        logger.warning("state_extraction node failed: %s", exc)
        extracted = existing_agent_state

    # Merge back into session_doc so the caller (chat.py) can persist it
    updated_session_doc = dict(session_doc)
    context = dict(updated_session_doc.get("context") or {})
    context["agent_state"] = extracted
    updated_session_doc["context"] = context

    return {"session_doc": updated_session_doc}


# ─────────────────────────────────────────────────────────────────────────────
# Graph assembly (compiled once at module import)
# ─────────────────────────────────────────────────────────────────────────────

def _compile_graph() -> StateGraph:
    builder = StateGraph(BOMGraphState)

    builder.add_node("build_context", _build_context_node)
    builder.add_node("call_llm", _call_llm_node)
    builder.add_node("extract_bom", _extract_bom_node)
    builder.add_node("rule_fallback", _rule_fallback_node)
    builder.add_node("compute_progress", _compute_progress_node)
    builder.add_node("state_extraction", _state_extraction_node)

    builder.add_edge(START, "build_context")
    builder.add_edge("build_context", "call_llm")
    builder.add_conditional_edges(
        "call_llm",
        route_after_llm,
        {"extract_bom": "extract_bom", "rule_fallback": "rule_fallback"},
    )
    builder.add_edge("extract_bom", "compute_progress")
    builder.add_edge("rule_fallback", "compute_progress")
    builder.add_edge("compute_progress", "state_extraction")
    builder.add_edge("state_extraction", END)

    return builder.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _compile_graph()
    return _graph


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

class BOMCreationAgent:
    """
    Async single-turn BOM creation agent backed by a LangGraph state machine.

    Usage
    ─────
        agent = BOMCreationAgent()
        response_text, bom_data, progress, complete = await agent.run(
            session_doc, message
        )

    The agent is stateless; a new instance per request is fine.  The underlying
    LangGraph is compiled once at module load (via _get_graph() singleton).
    """

    async def run(
        self,
        session_doc: dict,
        message: str,
    ) -> tuple[str, dict | None, int, bool]:
        """
        Execute one conversational turn of the BOM creation pipeline.

        Parameters
        ──────────
        session_doc : Full session document (plain dict from Cosmos / mock).
        message     : The user's latest message.

        Returns
        ───────
        (response_text, bom_data, progress, complete)
        """
        graph = _get_graph()

        initial_state: BOMGraphState = {
            "session_doc": session_doc,
            "message": message,
            "category": session_doc.get("context", {}).get("category", "Data Center / COLO"),
            # Pre-zeroed output fields (LangGraph merges partial returns from nodes)
            "system_prompt": "",
            "messages": [],
            "response_text": "",
            "bom_data": None,
            "complete": False,
            "progress": 0,
            "used_fallback": False,
        }

        final_state: BOMGraphState = await graph.ainvoke(initial_state)

        return (
            final_state.get("response_text", ""),
            final_state.get("bom_data"),
            final_state.get("progress", 0),
            final_state.get("complete", False),
        )
