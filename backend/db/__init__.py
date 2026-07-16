"""
backend/db/__init__.py — Thin shim.

Client construction and caching is now handled by the thread-safe registry in:
    framework/infra/singletons.py

This file keeps the public interface that existing backend code depends on:
    from db import get_cosmos_client, get_adls_client

Do NOT add new client construction logic here.
"""

import os
import sys

# Ensure the project root is on sys.path so framework/ and app/ are importable
# when running uvicorn from inside backend/.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Delegate to the framework singleton registry
from framework.infra.singletons import get_cosmos_client, get_adls_client  # noqa: E402

from db.schemas import (
    BOM, LineItem, BOMTotals, BOMStatus,
    BOMApproval, ApprovalStatus,
    AuditEvent,
    ChatSession, ChatMessage, SessionContext,
    Pattern, BundleRule, QuantityFormula, PricingPattern,
    Template, TemplateQuestion, TemplateItem,
    User, UserRole,
    AnalyticsMetric
)


__all__ = [
    # Client getters
    "get_cosmos_client",
    "get_adls_client",
    
    # BOM Models
    "BOM",
    "LineItem",
    "BOMTotals",
    "BOMStatus",
    
    # Chat Models
    "ChatSession",
    "ChatMessage",
    "SessionContext",
    
    # Pattern Models
    "Pattern",
    "BundleRule",
    "QuantityFormula",
    "PricingPattern",
    
    # Template Models
    "Template",
    "TemplateQuestion",
    "TemplateItem",
    
    # User Models
    "User",
    "UserRole",
    
    # Analytics Models
    "AnalyticsMetric"
]
