"""
backend/db/__init__.py — Public interface for database clients and schemas.
"""

from db.cosmos_client import get_cosmos_client
from db.adls_client import get_adls_client

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
