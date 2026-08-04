"""
framework/agents/state_extractor.py
────────────────────────────────────
Domain-agnostic structured-field extractor for conversational agents.

Two extraction strategies are provided, always tried in order:

1. **Heuristic** (zero-cost, no LLM call)
   Scans the full conversation text with per-field regex patterns.
   Returns every value it can find without calling an LLM.

2. **LLM-assisted** (higher quality, needs credentials)
   Sends a compact extraction prompt to the LLM asking it to return
   a JSON object mapping field keys → extracted values.
   Only called for fields the heuristic left as None.

Public API
──────────
    from framework.agents.state_extractor import (
        ExtractionField,
        ExtractionSchema,
        extract_heuristic,
        aextract,
    )

OWASP note:
    User conversation text is passed to the LLM only inside clearly-delimited
    <conversation> tags so that it cannot override the extraction instruction.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExtractionField:
    """
    Describes one structured field to extract from conversation history.

    Attributes
    ──────────
    key         Unique field identifier (matches the key in the returned dict).
    description Human-readable prompt hint sent to the LLM extractor.
    patterns    Ordered list of compiled regex patterns tried by the heuristic
                extractor.  First match wins.  Each pattern should have a
                named group ``value`` capturing the extracted text.
    normalise   Optional callable applied to the raw matched string before it
                is stored.  Use for case-folding, date-parsing, etc.
    """

    key: str
    description: str
    patterns: list[re.Pattern] = field(default_factory=list)
    normalise: Optional[Any] = None  # callable(str) -> str


@dataclass
class ExtractionSchema:
    """
    A named collection of ExtractionField objects.

    Attributes
    ──────────
    name    Short identifier used in log messages (e.g. "bom_decision").
    fields  Ordered list of fields to extract.
    """

    name: str
    fields: list[ExtractionField] = field(default_factory=list)

    def field_map(self) -> dict[str, ExtractionField]:
        return {f.key: f for f in self.fields}


# ─────────────────────────────────────────────────────────────────────────────
# Heuristic extractor  (synchronous, no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def extract_heuristic(
    conversation: list[dict[str, str]],
    schema: ExtractionSchema,
    existing_state: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Scan *conversation* with the regex patterns defined in *schema*.

    Parameters
    ──────────
    conversation    List of {role, content} dicts.
    schema          ExtractionSchema with fields + patterns.
    existing_state  Any already-extracted values; already-set fields are
                    skipped (avoids overwriting good data with a re-scan).

    Returns a dict with the same keys as schema.fields.  Values are either
    the extracted string (normalised if a normalise callable is provided)
    or None when the heuristic found nothing.
    """
    existing = existing_state or {}

    # Concatenate all message content into a single searchable string.
    # Include role markers so patterns can target "user said X" vs agent said.
    corpus = "\n".join(
        f"[{m.get('role','?').upper()}]: {m.get('content','')}"
        for m in conversation
    )

    result: dict[str, Any] = {}

    for f in schema.fields:
        key = f.key
        # Skip if already captured in a previous turn
        if existing.get(key) is not None:
            result[key] = existing[key]
            continue

        found = None
        for pat in f.patterns:
            m = pat.search(corpus)
            if m:
                try:
                    found = m.group("value").strip()
                except IndexError:
                    found = m.group(0).strip()
                if f.normalise:
                    try:
                        found = f.normalise(found)
                    except Exception:
                        pass
                break

        result[key] = found

    return result


# ─────────────────────────────────────────────────────────────────────────────
# LLM-assisted extractor  (async)
# ─────────────────────────────────────────────────────────────────────────────

_EXTRACTION_SYSTEM = (
    "You are a structured-data extraction assistant. "
    "Your only job is to extract specific fields from a conversation transcript "
    "and return them as a JSON object. "
    "Rules:\n"
    "  • Return ONLY valid JSON — no commentary, no markdown fences.\n"
    "  • Use null for fields you cannot determine from the conversation.\n"
    "  • Never invent values.  Only extract what is explicitly stated.\n"
    "  • Keep values concise (one phrase or sentence maximum).\n"
    "  • Do not interpret or transform dates — copy them verbatim.\n"
)

def _build_extraction_prompt(
    conversation: list[dict[str, str]],
    fields_to_extract: list[ExtractionField],
    history_window: int = 20,
) -> str:
    """
    Build the user-turn message asking the LLM to extract specific fields.

    The conversation is enclosed in <conversation> tags to prevent injection
    from user content overriding the extraction instruction.
    """
    recent = conversation[-history_window:]
    conv_text = "\n".join(
        f"{m.get('role','?').upper()}: {m.get('content','')}"
        for m in recent
    )

    fields_desc = "\n".join(
        f'  "{f.key}": {f.description}'
        for f in fields_to_extract
    )

    return (
        f"Extract the following fields from the conversation below.\n\n"
        f"Fields to extract:\n{fields_desc}\n\n"
        f"Return a JSON object with exactly these keys.  "
        f"Use null for anything not determinable.\n\n"
        f"<conversation>\n{conv_text}\n</conversation>"
    )


async def aextract(
    conversation: list[dict[str, str]],
    schema: ExtractionSchema,
    existing_state: Optional[dict[str, Any]] = None,
    *,
    use_llm: bool = True,
    history_window: int = 20,
) -> dict[str, Any]:
    """
    Extract structured fields from *conversation*.

    Strategy:
      1. Heuristic pass — fills as many fields as regex patterns allow.
      2. LLM pass (if *use_llm* is True) — asks the LLM for any remaining
         None fields.  No LLM call is made if all fields are already filled.

    Parameters
    ──────────
    conversation    List of {role, content} dicts (full history).
    schema          ExtractionSchema describing what to extract.
    existing_state  Previously extracted values from earlier turns.  Already-
                    set fields are never overwritten.
    use_llm         Set False to force heuristic-only extraction (e.g. tests).
    history_window  Max recent messages passed to the LLM extraction prompt.

    Returns
    ───────
    Merged dict of {key: value | None} for every field in schema.
    """
    # ── Pass 1: heuristic ──────────────────────────────────────────────────
    state = extract_heuristic(conversation, schema, existing_state)

    if not use_llm:
        return state

    # ── Pass 2: LLM for remaining Nones ───────────────────────────────────
    missing_fields = [f for f in schema.fields if state.get(f.key) is None]
    if not missing_fields:
        logger.debug("state_extractor[%s]: all fields satisfied by heuristic", schema.name)
        return state

    try:
        from framework.agents.llm_client import acall_llm  # noqa: PLC0415

        prompt = _build_extraction_prompt(conversation, missing_fields, history_window)
        raw = await acall_llm(
            messages=[{"role": "user", "content": prompt}],
            system=_EXTRACTION_SYSTEM,
            max_tokens=512,
            temperature=0.0,
        )

        if raw:
            # Strip any accidental markdown fences the LLM may have added
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
            cleaned = re.sub(r"```\s*$", "", cleaned.strip())
            parsed: dict = json.loads(cleaned)
            for f in missing_fields:
                val = parsed.get(f.key)
                if val is not None:
                    if f.normalise:
                        try:
                            val = f.normalise(str(val))
                        except Exception:
                            pass
                    state[f.key] = val

    except json.JSONDecodeError as exc:
        logger.warning(
            "state_extractor[%s]: LLM returned non-JSON: %s", schema.name, exc
        )
    except Exception as exc:
        logger.warning(
            "state_extractor[%s]: LLM extraction failed: %s", schema.name, exc
        )

    return state
