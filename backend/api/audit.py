"""
Audit Logging Module — Sprint 1
Tracks all user actions: BOM creation, edits, approvals, exports, status changes.
In-memory store for dev; swap to Cosmos DB container for production.
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/audit", tags=["audit"])

# In-memory audit log (thread-safe for single-worker; use DB in production)
_audit_log: List[Dict[str, Any]] = []


class AuditEntry(BaseModel):
    id: str
    timestamp: str
    user_id: str
    action: str           # created | updated | approved | rejected | exported | chat_message | status_changed
    resource_type: str    # bom | session | approval | export
    resource_id: str
    details: Dict[str, Any] = {}


def log_action(
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> AuditEntry:
    """
    Record an audit event. Call this from any API endpoint that modifies data.
    Thread-safe for append-only in single-worker deployments.
    """
    entry = AuditEntry(
        id=f"audit_{uuid.uuid4().hex[:10]}",
        timestamp=datetime.utcnow().isoformat() + "Z",
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
    )
    _audit_log.append(entry.model_dump())
    return entry


@router.get("", response_model=List[AuditEntry])
async def list_audit_log(
    resource_id: Optional[str] = Query(None, description="Filter by BOM or session ID"),
    user_id: Optional[str] = Query(None, description="Filter by user"),
    resource_type: Optional[str] = Query(None, description="bom | session | approval | export"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    limit: int = Query(100, le=500),
):
    """Retrieve audit log entries with optional filters. Returns most recent first."""
    results = _audit_log
    if resource_id:
        results = [e for e in results if e["resource_id"] == resource_id]
    if user_id:
        results = [e for e in results if e["user_id"] == user_id]
    if resource_type:
        results = [e for e in results if e["resource_type"] == resource_type]
    if action:
        results = [e for e in results if e["action"] == action]
    sorted_results = sorted(results, key=lambda x: x["timestamp"], reverse=True)
    return [AuditEntry(**e) for e in sorted_results[:limit]]


@router.get("/bom/{bom_id}", response_model=List[AuditEntry])
async def get_bom_audit_trail(bom_id: str):
    """Get full audit trail for a specific BOM — for the approval workflow."""
    results = [e for e in _audit_log if e["resource_id"] == bom_id]
    return [AuditEntry(**e) for e in sorted(results, key=lambda x: x["timestamp"], reverse=True)]


@router.get("/stats")
async def get_audit_stats():
    """Summary stats for the audit dashboard."""
    total = len(_audit_log)
    by_action: Dict[str, int] = {}
    by_user: Dict[str, int] = {}
    for e in _audit_log:
        by_action[e["action"]] = by_action.get(e["action"], 0) + 1
        by_user[e["user_id"]] = by_user.get(e["user_id"], 0) + 1
    return {
        "total_events": total,
        "by_action": by_action,
        "by_user": by_user,
        "latest_event": _audit_log[-1]["timestamp"] if _audit_log else None,
    }
