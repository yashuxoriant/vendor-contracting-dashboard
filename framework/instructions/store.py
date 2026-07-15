"""
framework/instructions/store.py — Versioned instruction file loader with TTL cache.

Loads instruction and skill .md files from disk (app/instructions/)
and caches their content in-process with a configurable TTL.

Architecture position:
  - This is the disk-path loader (Step 7).
  - Step 15 will extend this with a Blob hot-reload layer; this module's
    interface will not change — callers use load_instruction() regardless.

Public API:
  load_instruction(path)        → str  (file content, cached)
  load_skill(category)          → str  (resolves category → file path → content)
  invalidate(path=None)         → None (clear one entry or the whole cache)
  SKILL_FILE_MAP                → dict[str, str] (category → relative path)

Design:
  - Cache key  = absolute resolved path string
  - Cache value = (content: str, expires_at: float)
  - Default TTL = 300 s (overridable via INSTRUCTION_CACHE_TTL env var)
  - Thread-safe: a single threading.Lock protects cache reads/writes
  - This module must NOT import from `app/` domain modules (only reads files)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTL configuration
# ---------------------------------------------------------------------------

_DEFAULT_TTL: float = float(os.environ.get("INSTRUCTION_CACHE_TTL", "300"))

# ---------------------------------------------------------------------------
# Category → relative path mapping
# Relative to the project root (parent of backend/, framework/, app/)
# ---------------------------------------------------------------------------

SKILL_FILE_MAP: dict[str, str] = {
    # Primary category names (must match session_doc["context"]["category"])
    "Data Center / COLO":           "app/instructions/BOM/Skill_DataCenter.md",
    "Data Center":                  "app/instructions/BOM/Skill_DataCenter.md",
    "SD-WAN":                       "app/instructions/BOM/Skill_Network_Telecom.md",
    "Network Equipment":            "app/instructions/BOM/Skill_Network_Telecom.md",
    "Network & Telecom":            "app/instructions/BOM/Skill_Network_Telecom.md",
    "Cybersecurity":                "app/instructions/BOM/Skill_Security.md",
    "Identity & Security":          "app/instructions/BOM/Skill_Security.md",
    "Security":                     "app/instructions/BOM/Skill_Security.md",
    "End User Computing":           "app/instructions/BOM/Skill_EUC.md",
    "EUC":                          "app/instructions/BOM/Skill_EUC.md",
    "Laptops":                      "app/instructions/BOM/Skill_EUC.md",
    "Access Points":                "app/instructions/BOM/Skill_Network_Telecom.md",
    "Applications":                 "app/instructions/BOM/Skill_Applications.md",
    "M365 & Power Platform":        "app/instructions/BOM/Skill_M365.md",
    "Cloud Infrastructure":         "app/instructions/BOM/Skill_DataCenter.md",
    "EOL Replacement":              "app/instructions/BOM/Skill_DataCenter.md",

    # Special keys for core agent instructions
    "__bom_agent__":                "app/instructions/BOM/BOMAgent.md",
    "__shared__":                   "app/instructions/Shared.md",
}

# ---------------------------------------------------------------------------
# Cache internals
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[str, float]] = {}   # path → (content, expires_at)
_lock = threading.Lock()


def _project_root() -> Path:
    """Return the absolute project root (grandparent of this file's directory)."""
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------


def load_instruction(
    relative_path: str,
    ttl: float = _DEFAULT_TTL,
) -> str:
    """
    Load *relative_path* (relative to project root) and return its content.

    Results are cached for *ttl* seconds.  Returns empty string if the file
    does not exist (never raises FileNotFoundError — callers treat empty as
    "no instruction available").

    Parameters
    ----------
    relative_path:
        Path string relative to the project root, e.g.
        ``"app/instructions/BOM/BOMAgent.md"``.
    ttl:
        Cache lifetime in seconds.  Use 0 to force a fresh read.

    Returns
    -------
    str
        File contents, or ``""`` if the file does not exist.
    """
    abs_path = str((_project_root() / relative_path).resolve())

    now = time.monotonic()

    # Fast path — cache hit
    if ttl > 0:
        with _lock:
            entry = _cache.get(abs_path)
            if entry is not None and entry[1] > now:
                return entry[0]

    # Slow path — read from disk
    try:
        content = Path(abs_path).read_text(encoding="utf-8")
        logger.debug("instruction loaded: %s (%d chars)", relative_path, len(content))
    except FileNotFoundError:
        logger.warning("instruction file not found: %s", abs_path)
        content = ""
    except OSError as exc:
        logger.error("instruction file read error: %s | %s", abs_path, exc)
        content = ""

    if ttl > 0:
        with _lock:
            _cache[abs_path] = (content, now + ttl)

    return content


# ---------------------------------------------------------------------------
# Skill loader — resolves category name → file path → content
# ---------------------------------------------------------------------------


def load_skill(
    category: str,
    ttl: float = _DEFAULT_TTL,
) -> str:
    """
    Load the skill .md content for *category*.

    Uses SKILL_FILE_MAP to resolve the category to a relative path, then
    calls :func:`load_instruction`.

    Returns empty string if the category has no mapping or the file is absent.
    The fallback to CATEGORY_ADDENDA strings remains in bom_prompt_config.py
    and is used whenever this returns empty.
    """
    relative_path = SKILL_FILE_MAP.get(category)
    if not relative_path:
        logger.debug("load_skill: no mapping for category=%r", category)
        return ""
    return load_instruction(relative_path, ttl=ttl)


def load_bom_agent_instructions(ttl: float = _DEFAULT_TTL) -> str:
    """Load the BOMAgent.md top-level orchestration instructions."""
    return load_instruction(SKILL_FILE_MAP["__bom_agent__"], ttl=ttl)


def load_shared_instructions(ttl: float = _DEFAULT_TTL) -> str:
    """Load the Shared.md tone + format rules."""
    return load_instruction(SKILL_FILE_MAP["__shared__"], ttl=ttl)


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def invalidate(relative_path: Optional[str] = None) -> None:
    """
    Remove cache entries.

    Parameters
    ----------
    relative_path:
        If given, evict only this path.
        If None, clear the entire cache (used by Step 15 Blob hot-reload).
    """
    with _lock:
        if relative_path is None:
            _cache.clear()
            logger.debug("instruction cache cleared (all entries)")
        else:
            abs_path = str((_project_root() / relative_path).resolve())
            removed = _cache.pop(abs_path, None)
            if removed:
                logger.debug("instruction cache evicted: %s", relative_path)
