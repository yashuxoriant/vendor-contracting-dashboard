"""
backend/config.py — Thin shim.

All settings are now defined in:
  framework/settings.py  →  BaseAgentSettings  (infrastructure)
  app/settings.py        →  AppSettings        (domain + infrastructure)

This file exists solely to preserve the public interface that existing
backend code depends on:
  from config import settings, get_settings, Settings

Do NOT add new settings here — add them to framework/settings.py or
app/settings.py as appropriate.
"""

import os
import sys

# Ensure the project root (one level above backend/) is on sys.path so that
# the `framework` and `app` packages are importable.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.settings import AppSettings, get_settings  # noqa: E402  (path fixup above)

# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

# `Settings` alias — existing code that does `from config import Settings`
# or uses type annotations `Settings` continues to work unchanged.
Settings = AppSettings

# Module-level singleton — existing code that does `from config import settings`
# or `settings = get_settings()` gets the same cached AppSettings instance.
settings: AppSettings = get_settings()
