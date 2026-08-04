"""
Pydantic Models / Schemas
Data models for the IT BOM Creation System
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from uuid import uuid4


class BOMStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    REVISION_REQUIRED = "revision_required"   # changes requested — needs rebuild
    APPROVED = "approved"
    SENT_TO_VENDOR = "sent_to_vendor"
    ARCHIVED = "archived"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"   # approver wants rebuild; resets cycle
    REJECTED = "rejected"


class UserRole(str, Enum):
    ADMIN = "admin"
    CREATOR = "creator"
    VIEWER = "viewer"


# ============================================================================
# Approval Model
# ============================================================================

class BOMApproval(BaseModel):
    """3-party approval record — Buyer IT / Seller IT / SI"""
    party: str                              # "buyer_it" | "seller_it" | "si"
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    comments: Optional[str] = None
    change_description: Optional[str] = None  # what changes were requested
    status: ApprovalStatus = ApprovalStatus.PENDING
    locked: bool = False                    # True = waiting for prior party


# ============================================================================
# Audit Event
# ============================================================================

class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"audit_{uuid4().hex[:12]}")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: str
    user_name: Optional[str] = None
    action: str       # created | modified | approved | rejected | exported | submitted
    entity_type: str  # bom | session | template
    entity_id: str
    field_changed: Optional[str] = None
    before_value: Optional[Any] = None
    after_value: Optional[Any] = None
    metadata: Dict[str, Any] = {}


# ============================================================================
# BOM Models
# ============================================================================

class LineItem(BaseModel):
    """Individual line item in a BOM"""
    line_number: int
    description: str
    sku: Optional[str] = None
    specification: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    vendor: Optional[str] = None
    vendor_route: Optional[str] = None
    quantity: float
    unit_price: float
    extended_price: float
    currency: str = "USD"
    term: Optional[str] = None
    otc: Optional[float] = None
    run_costs_annual: Optional[float] = None
    support_level: Optional[str] = None
    notes: Optional[str] = None
    explanation: Optional[str] = None
    dependencies: List[int] = []
    # Sprint 2 additions
    order_sequence: Optional[int] = None    # Phase 10b ordering (1–5)
    eol_flag: bool = False                  # True if SKU is end-of-life
    eol_warning: Optional[str] = None       # Human-readable EOL warning
    replacement_sku: Optional[str] = None   # Recommended replacement SKU
    # Sprint 3 — Quantity traceability (driver-based model)
    qty_driver:     Optional[str]   = None   # business object driving the qty: Site, Router, Fleet, AP, etc.
    driver_count:   Optional[float] = None   # count of those driver objects, e.g. 10 (sites), 20 (routers)
    qty_per_driver: Optional[float] = None   # units required per driver, e.g. 1, 2, 0.1 (10% spare)
    qty_basis:      Optional[str]   = None   # human-readable derivation: "10 Sites × 1 Router per Site"
    qty_status:     Optional[str]   = "confirmed"  # "confirmed" | "assumption"


class BOMTotals(BaseModel):
    hardware: float = 0.0
    software: float = 0.0
    services: float = 0.0
    bundled: float = 0.0
    subtotal: float = 0.0
    total_otc: float = 0.0
    arc_annual: float = 0.0           # Annual Recurring Cost
    mrc_monthly: float = 0.0          # Monthly Recurring Cost
    total_run_costs_annual: float = 0.0  # backwards compat — mirrors arc_annual
    tco_3year: float = 0.0
    tco_5year: float = 0.0


class BOMVersion(BaseModel):
    version: int
    created_at: datetime
    created_by: str
    change_description: Optional[str] = None
    changes: List[Dict[str, Any]] = []


class BOM(BaseModel):
    """Complete BOM document"""
    id: Optional[str] = Field(default=None, alias="_id")
    bom_id: str
    project_name: str
    name: Optional[str] = None          # display name: "ABB — Network Equipment BOM Rev 1"
    category: str
    region: Optional[str] = None
    country: Optional[str] = None
    line_items: List[LineItem]
    totals: BOMTotals
    status: BOMStatus = BOMStatus.DRAFT
    version: int = 1
    versions: List[BOMVersion] = []
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Renamed from modified_at → updated_at (ROADMAP §4.4)
    updated_at: Optional[datetime] = None
    modified_by: Optional[str] = None
    notes: Optional[str] = None             # Previously missing — now added
    day_one_date: Optional[datetime] = None # Phase 1: drives lead-time warnings
    approvals: List[BOMApproval] = Field(   # 3-party approval state
        default_factory=lambda: [
            BOMApproval(party="buyer_it"),
            BOMApproval(party="seller_it"),
            BOMApproval(party="si"),
        ]
    )
    metadata: Dict[str, Any] = {}
    revision: int = 1                       # increments each time BOM is rebuilt after changes
    approval_cycle: int = 1                 # how many full restart cycles have occurred
    session_id: Optional[str] = None        # chat session that created this BOM — used to re-link sidebar row

    class Config:
        use_enum_values = True
        populate_by_name = True
        extra = "ignore"      # drop _id, bom_id duplicates, unknown mock fields


# ============================================================================
# Chat Session Models
# ============================================================================

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:12]}")
    metadata: Dict[str, Any] = {}


class SessionContext(BaseModel):
    category: Optional[str] = None
    requirements: Dict[str, Any] = {}
    template_id: Optional[str] = None
    questions_asked: int = 0
    questions_total: int = 5
    progress_percentage: float = 0.0
    # Sprint 2 — phase state machine
    current_phase: int = 1
    phase_data: Dict[str, Any] = {}     # Structured answers per phase
    partial_bom: Optional[Dict[str, Any]] = None
    # Sprint 3 — BOM embedding pipeline
    bom_id: Optional[str] = None        # Scopes vector search to a specific indexed BOM
    domain_preselected: bool = False    # True when user chose domain from the picker UI
    agent_state: Dict[str, Any] = {}   # BOM extraction decision fields (all phases)
    current_phase_name: str = "intake"  # LangGraph phase name: intake/qualify/scope/sizing/generate/validate/complete


class ChatSession(BaseModel):
    """Chat session for BOM creation"""
    id: Optional[str] = Field(default=None, alias="_id")
    session_id: str
    user_id: str
    conversation: List[ChatMessage] = []
    context: SessionContext = Field(default_factory=SessionContext)
    status: str = "active"  # active, completed, abandoned
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    bom_id: Optional[str] = None  # Link to generated BOM
    
    class Config:
        populate_by_name = True


# ============================================================================
# Pattern Models
# ============================================================================

class BundleRule(BaseModel):
    """Bundle rule: if X then Y must be included"""
    if_item: str  # SKU or item type
    then_required: List[str]  # Required SKUs or item types
    confidence: float  # 0.0 to 1.0
    source_boms: List[str] = []  # Files where this pattern was found


class QuantityFormula(BaseModel):
    """Quantity relationship formula"""
    target_item: str  # SKU or item type
    formula: str  # e.g., "servers * 2" for CPUs
    description: str


class PricingPattern(BaseModel):
    """Pricing pattern"""
    pattern_type: str  # "support_percentage", "volume_discount", "term_discount"
    rule: Dict[str, Any]
    confidence: float


class Pattern(BaseModel):
    """Learned pattern from historical BOMs"""
    id: Optional[str] = Field(default=None, alias="_id")
    pattern_id: str
    category: Optional[str] = None
    pattern_type: str  # "bundle", "quantity", "pricing", "dependency"
    bundle_rules: List[BundleRule] = []
    quantity_formulas: List[QuantityFormula] = []
    pricing_patterns: List[PricingPattern] = []
    confidence: float
    source_count: int  # Number of BOMs this pattern was found in
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True


# ============================================================================
# Template Models
# ============================================================================

class TemplateQuestion(BaseModel):
    """Question to ask user"""
    question_id: str
    question_text: str
    question_type: str  # "text", "number", "choice", "multi_choice"
    options: List[str] = []
    validation: Optional[Dict[str, Any]] = None
    help_text: Optional[str] = None


class TemplateItem(BaseModel):
    """Template line item"""
    description: str
    sku: Optional[str] = None
    category: str
    quantity_formula: Optional[str] = None  # Formula or fixed number
    price_source: str  # "historical", "manual", "vendor_api"
    required: bool = True
    conditional: Optional[str] = None  # Condition for inclusion


class Template(BaseModel):
    """BOM Template"""
    id: Optional[str] = Field(default=None, alias="_id")
    template_id: str
    name: str
    category: str
    description: str
    questions: List[TemplateQuestion]
    base_items: List[TemplateItem]
    rules: Dict[str, Any] = {}  # Bundle rules, formulas, etc.
    example_boms: List[str] = []  # Reference BOM IDs
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True


# ============================================================================
# User Models
# ============================================================================

class User(BaseModel):
    """User account"""
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    email: str
    name: str
    role: UserRole = UserRole.CREATOR
    preferences: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    
    class Config:
        use_enum_values = True
        populate_by_name = True


# ============================================================================
# Analytics Models
# ============================================================================

class AnalyticsMetric(BaseModel):
    """Analytics metric"""
    id: Optional[str] = Field(default=None, alias="_id")
    metric_id: str
    metric_type: str  # "spending", "vendor_performance", "pattern_insight", "trend"
    period: str  # "daily", "weekly", "monthly", "quarterly"
    period_start: datetime
    period_end: datetime
    data: Dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
