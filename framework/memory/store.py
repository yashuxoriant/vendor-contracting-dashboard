"""
framework/memory/store.py — Multi-scope conversation memory manager.

Three scopes backed by Cosmos DB:

  SESSION  — the full ChatSession document (conversations list + metadata)
             Container : sessions  (partition key: /user_id)
             get/set delegate to the high-level get_session / update_session /
             create_session methods on the Cosmos client.

  STATE    — structured agent state stored as the ``agent_state`` sub-dict
             WITHIN the session document (same Cosmos partition, no separate doc)
             get/set read the session doc and read/write the ``agent_state`` key.

  SHARED   — cross-session project knowledge stored in the patterns container
             (partition key: /category) with a synthetic category value of
             "shared_memory".  Identified by doc id = shared:<user_id>:<project>.

Design principles:
  - The manager wraps the existing Cosmos client obtained from
    framework.infra.singletons — no new Azure dependency.
  - All reads are shallow dict fetches; the caller owns schema validation.
  - Writes use the high-level client methods where available (get_session /
    update_session) so that both the real and mock clients are supported.
  - Synchronous surface — Step 8 will layer async streaming on top without
    changing this module.
  - This module must NOT import from `app/`; the scope keys and step names
    are pure strings passed by the caller.

OWASP note: doc_ids are constructed only from validated internal values
(session_id, user_id, project). Never interpolate raw user input into a
Cosmos document id.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scope constants (public — app code references these)
# ---------------------------------------------------------------------------

SCOPE_SESSION = "session"   # per-session conversation history (full session doc)
SCOPE_STATE   = "state"     # per-session agent state (sub-key inside session doc)
SCOPE_SHARED  = "shared"    # cross-session project-level knowledge (patterns container)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cosmos():
    """Deferred import of the Cosmos singleton — avoids circular imports."""
    from framework.infra.singletons import get_cosmos_client  # noqa: PLC0415
    return get_cosmos_client()


def _settings():
    from app.settings import get_settings  # noqa: PLC0415
    return get_settings()


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _shared_doc_id(user_id: str, project: str) -> str:
    """Cosmos document id for the SHARED scope of a project."""
    safe_user    = user_id.replace("/", "_").replace("\\", "_")
    safe_project = project.replace("/", "_").replace("\\", "_").replace(" ", "_")
    return f"shared:{safe_user}:{safe_project}"


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------


class MemoryStore:
    """
    Thin wrapper around the Cosmos DB client providing scope-aware
    get / set / append operations.

    Usage::

        from framework.memory.store import MemoryStore, SCOPE_SESSION, SCOPE_STATE

        mem = MemoryStore()

        # Read the full session history doc
        doc = mem.get(SCOPE_SESSION, session_id=session_id)

        # Read only the agent state
        state = mem.get_state(session_id)

        # Write a state update (merged into the session doc's agent_state key)
        mem.set_state(session_id, {"current_step": "03_vendor_qualification"})

        # Append a message to session history
        mem.append_message(session_id=session_id, role="user", content="Hello")
    """

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    def get(
        self,
        scope: str,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        project: str | None = None,
    ) -> dict | None:
        """
        Fetch the document for the given scope.

        Returns the raw dict (or None if not found).
        """
        client = _cosmos()

        if scope == SCOPE_SESSION:
            if not session_id:
                raise ValueError("session_id required for SCOPE_SESSION")
            return client.get_session(session_id)

        if scope == SCOPE_STATE:
            if not session_id:
                raise ValueError("session_id required for SCOPE_STATE")
            doc = client.get_session(session_id)
            if doc is None:
                return None
            # STATE is stored as a sub-dict inside the session document
            return doc.get("agent_state") or None

        if scope == SCOPE_SHARED:
            if not user_id or not project:
                raise ValueError("user_id and project required for SCOPE_SHARED")
            doc_id = _shared_doc_id(user_id, project)
            container = _settings().cosmos_container_patterns
            try:
                results = client.query_items(
                    container,
                    "SELECT * FROM c WHERE c._id = @id OR c.id = @id",
                    [{"name": "@id", "value": doc_id}],
                )
                return results[0] if results else None
            except Exception as exc:
                logger.debug("MemoryStore.get SHARED | doc_id=%s | %s", doc_id, exc)
                return None

        raise ValueError(f"Unknown memory scope: {scope!r}")

    # ------------------------------------------------------------------
    # set  (upsert — merge over existing doc)
    # ------------------------------------------------------------------

    def set(
        self,
        scope: str,
        data: dict[str, Any],
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        project: str | None = None,
    ) -> None:
        """
        Upsert *data* into the document for the given scope.

        For SESSION: merges on top of the existing session document.
        For STATE: merges *data* into the ``agent_state`` sub-dict of the session document.
        For SHARED: upserts a document in the patterns container.
        """
        client = _cosmos()

        if scope == SCOPE_SESSION:
            if not session_id:
                raise ValueError("session_id required for SCOPE_SESSION")
            existing = client.get_session(session_id) or {}
            merged = {**existing, **data, "id": session_id, "_id": session_id, "updated_at": _now_iso()}
            if existing:
                client.update_session(session_id, merged)
            else:
                client.create_session(merged)
            return

        if scope == SCOPE_STATE:
            if not session_id:
                raise ValueError("session_id required for SCOPE_STATE")
            existing_doc = client.get_session(session_id) or {}
            existing_state = existing_doc.get("agent_state") or {}
            merged_state = {**existing_state, **data, "updated_at": _now_iso()}
            merged_doc = {**existing_doc, "agent_state": merged_state,
                          "id": session_id, "_id": session_id, "updated_at": _now_iso()}
            if existing_doc:
                client.update_session(session_id, merged_doc)
            else:
                client.create_session(merged_doc)
            return

        if scope == SCOPE_SHARED:
            if not user_id or not project:
                raise ValueError("user_id and project required for SCOPE_SHARED")
            doc_id = _shared_doc_id(user_id, project)
            container = _settings().cosmos_container_patterns
            existing = self.get(SCOPE_SHARED, user_id=user_id, project=project) or {}
            merged = {
                **existing,
                **data,
                "id": doc_id,
                "_id": doc_id,
                "category": "shared_memory",   # partition key for patterns container
                "updated_at": _now_iso(),
            }
            if existing:
                client.update_item(container, doc_id, merged)
            else:
                client.create_item(container, merged)
            return

        raise ValueError(f"Unknown memory scope: {scope!r}")

    # ------------------------------------------------------------------
    # append_message
    # ------------------------------------------------------------------

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Append a chat message to the session's ``conversation`` list.

        The list is stored under the key ``conversation`` to match the
        existing ChatSession schema so both old and new code can read it.
        """
        doc = self.get(SCOPE_SESSION, session_id=session_id) or {}
        messages: list = doc.get("conversation", [])
        entry: dict[str, Any] = {
            "role": role,
            "content": content,
            "timestamp": _now_iso(),
        }
        if metadata:
            entry["metadata"] = metadata
        messages.append(entry)
        self.set(SCOPE_SESSION, {"conversation": messages}, session_id=session_id)

    # ------------------------------------------------------------------
    # STATE convenience wrappers
    # ------------------------------------------------------------------

    def get_state(self, session_id: str) -> dict[str, Any]:
        """Return the agent state dict for *session_id* (empty dict if none)."""
        return self.get(SCOPE_STATE, session_id=session_id) or {}

    def set_state(self, session_id: str, updates: dict[str, Any]) -> None:
        """Merge *updates* into the agent state for *session_id*."""
        self.set(SCOPE_STATE, updates, session_id=session_id)

    def advance_step(self, session_id: str, new_step: str) -> None:
        """
        Record that the agent has moved to *new_step* in the pipeline.

        Stores both ``current_step`` (latest) and appends to ``step_history``
        (ordered list of all steps visited) for audit / replay.
        """
        state = self.get_state(session_id)
        history: list[str] = state.get("step_history", [])
        history.append(new_step)
        self.set_state(session_id, {
            "current_step": new_step,
            "step_history": history,
            "step_advanced_at": _now_iso(),
        })

    # ------------------------------------------------------------------
    # SHARED convenience wrappers
    # ------------------------------------------------------------------

    def get_shared(self, user_id: str, project: str) -> dict[str, Any]:
        """Return the shared project knowledge doc (empty dict if none)."""
        return self.get(SCOPE_SHARED, user_id=user_id, project=project) or {}

    def set_shared(self, user_id: str, project: str, updates: dict[str, Any]) -> None:
        """Merge *updates* into the shared project knowledge."""
        self.set(SCOPE_SHARED, updates, user_id=user_id, project=project)

