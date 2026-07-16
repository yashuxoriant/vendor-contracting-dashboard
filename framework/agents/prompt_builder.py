"""
framework/agents/prompt_builder.py — Domain-agnostic prompt assembly.

Provides:
  build_llm_messages(config, session_doc) → list[dict]
    Assembles the ``messages`` list for an LLM call:
      [{"role": "system", "content": <system_prompt>},
       {"role": "user"|"assistant", "content": ...}, ...]

  PromptConfig  — dataclass the caller fills in; carries system text,
                  context blocks, and conversation window size.

Design:
  - Zero imports from `app/`.  Domain-specific config is passed in.
  - The system prompt is assembled by concatenating:
      1. base_system   (mandatory — core identity / rules)
      2. skill_block   (optional — injected category skill text)
      3. session_block (always — current session state context)
  - Conversation history is taken from session_doc["conversation"]
    (the key used by the existing ChatSession schema) and trimmed to
    the last *history_window* messages.
  - Anthropic-style (system separate from messages) and OpenAI-style
    (system as first message) output are both supported via the
    ``system_as_first_message`` flag.

OWASP: no user content is interpolated into the system prompt here.
The only dynamic values come from validated session state (category,
project, phase) — never from raw user message text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# PromptConfig  — filled by the domain layer (app/agents/bom_prompt_config.py)
# ---------------------------------------------------------------------------


@dataclass
class PromptConfig:
    """
    Carries everything the prompt builder needs to assemble an LLM call.

    Fields:
        base_system (str):
            The core identity / rules / methodology text.
            Required. Never empty.

        session_block (str):
            A rendered "CURRENT SESSION" section showing category, project,
            current pipeline step, and other structured context.
            Built by the domain layer from the session document.

        skill_block (str):
            Optional injected skill text for the resolved category
            (e.g. the content of Skill_DataCenter.md).
            Empty string when no skill has been resolved yet.

        history_window (int):
            Number of most-recent conversation messages to include.
            Defaults to 14 (7 user + 7 assistant turns).

        system_as_first_message (bool):
            When True, the assembled system text is emitted as the first
            message with role "user" (for OpenAI o-series models that
            don't support a system role).
            When False (default) the system text is returned separately
            as the ``system`` key, and messages contains only human/AI turns.
    """

    base_system: str
    session_block: str = ""
    skill_block: str = ""
    history_window: int = 14
    system_as_first_message: bool = False


# ---------------------------------------------------------------------------
# build_llm_messages
# ---------------------------------------------------------------------------

_SEP = "\n" + "═" * 60 + "\n"


def build_system_prompt(config: PromptConfig) -> str:
    """
    Assemble the full system prompt string from *config*.

    Order:
      1. base_system
      2. skill_block  (if non-empty, wrapped in a "CATEGORY SKILL" section)
      3. session_block (if non-empty, wrapped in a "CURRENT SESSION" section)
    """
    parts: list[str] = [config.base_system.strip()]

    if config.skill_block:
        parts.append(_SEP + "CATEGORY SKILL GUIDANCE\n" + _SEP + config.skill_block.strip())

    if config.session_block:
        parts.append(_SEP + "CURRENT SESSION\n" + _SEP + config.session_block.strip())

    return "\n\n".join(parts)


def build_llm_messages(
    config: PromptConfig,
    session_doc: dict[str, Any],
) -> tuple[str, list[dict[str, str]]]:
    """
    Assemble the ``(system_prompt, messages)`` pair for an LLM call.

    Parameters
    ----------
    config:
        A :class:`PromptConfig` instance built by the domain layer.
    session_doc:
        The raw Cosmos session document (or any dict with a ``conversation``
        list of ``{"role": ..., "content": ...}`` dicts).

    Returns
    -------
    system_prompt : str
        The full assembled system prompt.
    messages : list[dict]
        Conversation history trimmed to ``config.history_window`` entries.
        Each entry is ``{"role": "user"|"assistant", "content": str}``.
        If ``config.system_as_first_message`` is True the system text is
        prepended as ``{"role": "user", "content": system_prompt}`` and an
        empty system_prompt string is returned.

    Example
    -------
    ::

        from framework.agents.prompt_builder import build_llm_messages
        from app.agents.bom_prompt_config import make_prompt_config

        config = make_prompt_config(session_doc)
        system, messages = build_llm_messages(config, session_doc)
        response = call_ai(messages, system=system)
    """
    system_prompt = build_system_prompt(config)

    raw_history: list[dict] = session_doc.get("conversation", [])
    # Keep only the last N messages and normalise keys
    trimmed = raw_history[-config.history_window :]
    messages: list[dict[str, str]] = [
        {"role": m["role"], "content": m.get("content") or ""}
        for m in trimmed
        if m.get("role") in ("user", "assistant")
    ]

    if config.system_as_first_message and system_prompt:
        messages = [{"role": "user", "content": system_prompt}] + messages
        return "", messages

    return system_prompt, messages
