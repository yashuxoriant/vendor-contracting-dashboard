"""
framework/infra/singletons.py — Thread-safe lazy Azure client registry.

Replaces the bare mutable globals in backend/db/__init__.py with a
double-checked locking pattern backed by threading.Lock.

Rules:
  - This module must NOT import from `app/` or any domain module.
  - It reads settings via app.settings.get_settings() at call time,
    never at import time — so the module is safe to import in tests
    that override env vars before constructing settings.
  - Callers (e.g. backend/db/__init__.py) import the getter functions
    directly; the registry dict is private.

Usage (from anywhere in backend/ or app/):
    from framework.infra.singletons import get_cosmos_client, get_adls_client
    client = get_cosmos_client()
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Private registry
# ---------------------------------------------------------------------------

_lock: threading.Lock = threading.Lock()

# Keys: "cosmos" | "adls"
_registry: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_or_create(key: str, factory: Callable[[], Any]) -> Any:
    """
    Return the cached instance for *key*, or build+cache it via *factory*.

    Uses double-checked locking:
      1. Fast path: object already in registry → return without acquiring lock.
      2. Slow path: acquire lock, re-check (another thread may have won the
         race), then construct and cache.

    The factory callable is expected to both construct **and** connect the
    client (i.e. call .connect() internally).
    """
    # Fast path
    if key in _registry:
        return _registry[key]

    # Slow path
    with _lock:
        if key not in _registry:
            logger.debug("singletons: constructing client for key=%r", key)
            instance = factory()
            _registry[key] = instance

    return _registry[key]


def _reset_registry() -> None:
    """
    Clear all cached singletons.

    Intended for use in tests only — not for production code.
    Acquires the lock so it is safe to call between test cases.
    """
    with _lock:
        _registry.clear()


# ---------------------------------------------------------------------------
# Cosmos DB
# ---------------------------------------------------------------------------

def get_cosmos_client():
    """
    Return the Cosmos DB client singleton (real or mock).

    The concrete type is determined by AppSettings.use_dummy_cosmos:
      True  → MockCosmosDBClient  (no Azure credentials required)
      False → CosmosDBClient      (requires COSMOS_DB_ENDPOINT / KEY)
    """
    def _factory():
        # Deferred imports — keeps this module free of circular import risk
        # and avoids importing Azure SDKs in test environments that mock them.
        from app.settings import get_settings  # noqa: PLC0415
        settings = get_settings()

        if settings.use_dummy_cosmos:
            from db.mock_cosmos_client import MockCosmosDBClient  # noqa: PLC0415
            client = MockCosmosDBClient()
        else:
            from db.cosmos_client import CosmosDBClient  # noqa: PLC0415
            client = CosmosDBClient()

        client.connect()
        return client

    return _get_or_create("cosmos", _factory)


# ---------------------------------------------------------------------------
# Azure Data Lake Storage (ADLS Gen2)
# ---------------------------------------------------------------------------

def get_adls_client():
    """
    Return the ADLS Gen2 client singleton (real or mock).

    The concrete type is determined by AppSettings.use_dummy_adls:
      True  → MockADLSClient  (no Azure credentials required)
      False → ADLSClient      (requires ADLS_ACCOUNT_NAME / KEY)
    """
    def _factory():
        from app.settings import get_settings  # noqa: PLC0415
        settings = get_settings()

        if settings.use_dummy_adls:
            from db.mock_adls_client import MockADLSClient  # noqa: PLC0415
            client = MockADLSClient()
        else:
            from db.adls_client import ADLSClient  # noqa: PLC0415
            client = ADLSClient()

        client.connect()
        return client

    return _get_or_create("adls", _factory)
