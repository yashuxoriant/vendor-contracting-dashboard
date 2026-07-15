"""
framework/security/guards.py — Prompt injection detection and response sanitisation.

Two public functions:
  check_user_input(text)  → raises PromptInjectionError if the text contains
                            known injection patterns; returns sanitised copy.
  sanitise_llm_output(text) → strips tokens that should never appear in a
                               response sent back to the browser.

Design notes:
  - Pattern matching is intentionally conservative: we prefer false negatives
    (missing a novel injection) over false positives (blocking legitimate user
    messages) at this stage.  High-confidence exact patterns only.
  - All checks are done on the normalised (lower-case, unicode-normalised) form
    of the text; the *original* text is returned / stored in audit events so
    that reviewers see exactly what the user typed.
  - This module must NOT import from `app/` or any domain module.
  - No LLM calls here — guards must be fast and always-on.

OWASP Top-10 relevance:
  A03 Injection, A05 Security Misconfiguration
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class PromptInjectionError(ValueError):
    """
    Raised when a user message triggers an injection heuristic.

    Attributes:
        matched_pattern: human-readable description of the pattern that matched
        original_text: the raw text that was inspected
    """

    def __init__(self, matched_pattern: str, original_text: str) -> None:
        self.matched_pattern = matched_pattern
        self.original_text = original_text
        super().__init__(
            f"Potential prompt injection detected ({matched_pattern}). "
            "The message has been blocked."
        )


# ---------------------------------------------------------------------------
# Detection result (returned for logging / audit; not raised)
# ---------------------------------------------------------------------------


class InjectionCheckResult(NamedTuple):
    clean: bool          # True  → no issues found
    matched: str | None  # None when clean=True, else the matched pattern label
    sanitised: str       # original text (unmodified) when clean; still returned


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """
    Lower-case + NFKC-normalise so homoglyph/Unicode tricks are neutralised.
    E.g. "Ｉｇｎｏｒｅ" → "ignore".
    """
    return unicodedata.normalize("NFKC", text).lower()


# ---------------------------------------------------------------------------
# Injection patterns
#
# Each tuple: (label, compiled_regex)
# Patterns target known jailbreak / system-prompt override techniques.
# Regex flags: re.IGNORECASE is applied to the pre-normalised string, so
# we only need DOTALL for multi-line patterns.
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Classic override instructions
    (
        "ignore-previous-instructions",
        re.compile(
            r"ignore\s+(all\s+)?(previous|prior|above|earlier|the\s+above)\s+"
            r"(instructions?|prompts?|rules?|guidelines?|context)",
            re.IGNORECASE,
        ),
    ),
    (
        "new-instructions-override",
        re.compile(
            r"(disregard|forget|override|bypass|skip)\s+(all\s+)?"
            r"(previous|prior|above|system|your)\s+(instructions?|prompts?|rules?|context)",
            re.IGNORECASE,
        ),
    ),
    # Role-swap attacks
    (
        "you-are-now-override",
        re.compile(
            r"you\s+are\s+now\s+(a\s+|an\s+)?(different|new|evil|jailbroken|unrestricted|"
            r"free|uncensored|DAN|character|persona)",
            re.IGNORECASE,
        ),
    ),
    (
        "act-as-override",
        re.compile(
            r"\bact\s+as\s+(if\s+you\s+(are|were)\s+)?(a\s+|an\s+)?"
            r"(different|new|evil|jailbroken|unrestricted|free|uncensored)",
            re.IGNORECASE,
        ),
    ),
    # System-prompt exfiltration
    (
        "reveal-system-prompt",
        re.compile(
            r"(print|show|display|output|repeat|reveal|tell\s+me|what\s+is)\s+"
            r"(your\s+)?(system\s+prompt|system\s+instructions?|initial\s+instructions?|"
            r"original\s+instructions?|full\s+prompt)",
            re.IGNORECASE,
        ),
    ),
    # Jailbreak keyword clusters
    (
        "jailbreak-keywords",
        re.compile(
            r"\b(jailbreak|jail\s*break|DAN\b|do\s+anything\s+now|unrestricted\s+mode|"
            r"developer\s+mode|god\s+mode|no\s+restrictions|remove\s+all\s+restrictions)\b",
            re.IGNORECASE,
        ),
    ),
    # Instruction-injection via fake role delimiters
    (
        "fake-role-delimiter",
        re.compile(
            r"(<\|?(system|SYSTEM|assistant|ASSISTANT|human|HUMAN|user|USER)\|?>|"
            r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>)",
            re.IGNORECASE,
        ),
    ),
    # Prompt-continuation injection ("continue from here: …")
    (
        "prompt-continuation",
        re.compile(
            r"(continue|complete|finish)\s+(the\s+)?(following\s+)?(from|after|below|here)?\s*:"
            r"\s*(ignore|forget|disregard|override|new\s+instructions?)",
            re.IGNORECASE,
        ),
    ),
]


# ---------------------------------------------------------------------------
# Output sanitisation patterns
#
# These tokens should never appear in text sent back to the browser.
# ---------------------------------------------------------------------------

_OUTPUT_STRIP_PATTERNS: list[re.Pattern[str]] = [
    # System-role delimiters that some models emit when confused
    re.compile(r"<\|?(system|assistant|human|user)\|?>", re.IGNORECASE),
    re.compile(r"\[INST\].*?\[/INST\]", re.DOTALL | re.IGNORECASE),
    re.compile(r"<<SYS>>.*?<</SYS>>", re.DOTALL | re.IGNORECASE),
    # Leaked "SYSTEM PROMPT:" header — anywhere in the line
    re.compile(r"(SYSTEM\s+PROMPT|SYSTEM\s+INSTRUCTIONS?)\s*:.*", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_user_input(text: str) -> str:
    """
    Inspect *text* for prompt injection patterns.

    Returns the original (unmodified) text if no issues are found.
    Raises PromptInjectionError if an injection pattern is matched.

    The caller should catch PromptInjectionError and return an HTTP 400 with
    a generic "message blocked" error body — do NOT echo the matched pattern
    back to the user.

    Example::

        from framework.security.guards import check_user_input, PromptInjectionError

        try:
            safe_text = check_user_input(user_message)
        except PromptInjectionError as exc:
            logger.warning("Injection attempt: %s", exc.matched_pattern)
            raise HTTPException(status_code=400, detail="Message blocked by security policy.")
    """
    if not text or not isinstance(text, str):
        return text or ""

    normalised = _normalise(text)

    for label, pattern in _INJECTION_PATTERNS:
        if pattern.search(normalised):
            logger.warning(
                "Prompt injection detected | pattern=%r | input_length=%d",
                label,
                len(text),
            )
            raise PromptInjectionError(matched_pattern=label, original_text=text)

    return text


def sanitise_llm_output(text: str) -> str:
    """
    Strip tokens from LLM *text* that should never reach the browser.

    Safe to call on every response before sending to the client.
    Returns the cleaned string (may be identical to the input if nothing matched).
    """
    if not text:
        return text or ""

    cleaned = text
    for pattern in _OUTPUT_STRIP_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Collapse any runs of blank lines introduced by stripping
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    if cleaned != text:
        logger.debug("LLM output sanitised: %d chars removed", len(text) - len(cleaned))

    return cleaned.strip()
