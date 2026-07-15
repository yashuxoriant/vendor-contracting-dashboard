"""
Package initialization for database module
"""

from config import get_settings
from db.cosmos_client import CosmosDBClient
from db.adls_client import ADLSClient
from db.mock_cosmos_client import MockCosmosDBClient
from db.mock_adls_client import MockADLSClient
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

# Global client instances
_cosmos_client = None
_adls_client = None


def get_cosmos_client():
    """Get Cosmos DB client (real or mock based on settings)"""
    global _cosmos_client
    settings = get_settings()
    
    if _cosmos_client is None:
        if settings.use_dummy_cosmos:
            _cosmos_client = MockCosmosDBClient()
        else:
            _cosmos_client = CosmosDBClient()
        _cosmos_client.connect()
    
    return _cosmos_client


def get_adls_client():
    """Get ADLS client (real or mock based on settings)"""
    global _adls_client
    settings = get_settings()
    
    if _adls_client is None:
        if settings.use_dummy_adls:
            _adls_client = MockADLSClient()
        else:
            _adls_client = ADLSClient()
        _adls_client.connect()
    
    return _adls_client


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
