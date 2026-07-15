"""
Mock/Dummy Cosmos DB Client
In-memory storage for local development without Azure
"""

from typing import Dict, List, Optional, Any
import logging
from datetime import datetime
import uuid

from db.schemas import BOM, ChatSession, Pattern, Template, User, AnalyticsMetric

logger = logging.getLogger(__name__)


class MockCosmosDBClient:
    """Mock Cosmos DB client using in-memory storage"""
    
    def __init__(self):
        """Initialize mock client with empty collections"""
        self.collections = {
            "sessions": {},
            "boms": {},
            "patterns": {},
            "templates": {},
            "analytics": {},
            "users": {},
            "audit": {},
        }
        logger.info("Initialized MockCosmosDBClient (in-memory storage)")
        self._seed_sample_data()
    
    def connect(self):
        """Mock connect - always succeeds"""
        logger.info("Mock Cosmos DB connected (no-op)")
    
    def create_containers_if_not_exist(self):
        """Mock container creation - already exists in memory"""
        logger.info("Mock containers created (no-op)")
    
    def _seed_sample_data(self):
        """Seed with realistic PwC M&A BOM data matching client projects."""
        now = datetime.utcnow()

        # Sample user
        self.collections["users"]["user_001"] = {
            "_id": "user_001", "user_id": "user_001",
            "email": "demo@pwc.com", "name": "Demo User",
            "role": "creator", "preferences": {},
            "created_at": now.isoformat()
        }

        # Sample template
        self.collections["templates"]["tmpl_datacenter"] = {
            "_id": "tmpl_datacenter", "template_id": "tmpl_datacenter",
            "name": "Data Center / COLO", "category": "Data Center",
            "description": "Complete data center infrastructure setup",
            "questions": [
                {"question_id": "q1", "question_text": "How many racks?", "question_type": "number"},
                {"question_id": "q2", "question_text": "HA required?", "question_type": "choice", "options": ["Yes", "No"]},
            ],
            "base_items": [], "rules": {}, "example_boms": [],
            "created_by": "system", "created_at": now.isoformat()
        }

        # ── Seed BOM 1: Panasonic SD-WAN ──────────────────────────────────
        pan_items = [
            {"line_number": 1, "description": "Cisco Catalyst 8300 SD-WAN Router", "sku": "C8300-2N2S-4T2X",
             "category": "Network Equipment", "vendor": "CDW", "quantity": 48, "unit_price": 4850,
             "extended_price": 232800, "term": "one-time", "order_sequence": 2, "eol_flag": False},
            {"line_number": 2, "description": "Cisco SD-WAN Software License (3yr)", "sku": "SDWAN-3Y-LIC",
             "category": "Software Licenses", "vendor": "CDW", "quantity": 48, "unit_price": 1200,
             "extended_price": 57600, "term": "3-year", "order_sequence": 5, "eol_flag": False},
            {"line_number": 3, "description": "FortiGate 200F NGFW", "sku": "FG-200F",
             "category": "Cybersecurity", "vendor": "CDW", "quantity": 12, "unit_price": 8200,
             "extended_price": 98400, "term": "one-time", "order_sequence": 2, "eol_flag": False},
            {"line_number": 4, "description": "3yr Hardware Maintenance — Cisco 8300", "sku": "SMARTNET-C8300-3Y",
             "category": "Maintenance", "vendor": "Cisco Direct", "quantity": 48, "unit_price": 485,
             "extended_price": 23280, "term": "3-year", "order_sequence": 5, "eol_flag": False},
        ]
        pan_total = sum(i["extended_price"] for i in pan_items)
        self.collections["boms"]["bom_panasonic_001"] = {
            "_id": "bom_panasonic_001", "bom_id": "bom_panasonic_001",
            "project_name": "Panasonic", "category": "SD-WAN",
            "line_items": pan_items,
            "totals": {"hardware": 331200, "software": 57600, "services": 23280,
                       "bundled": 0, "subtotal": pan_total, "total_otc": pan_total,
                       "total_run_costs_annual": 0, "tco_3year": pan_total},
            "status": "approved",
            "approvals": [
                {"party": "buyer_it", "approved_by": "Avijeet", "approved_at": now.isoformat(), "status": "approved"},
                {"party": "seller_it", "approved_by": "Panasonic IT", "approved_at": now.isoformat(), "status": "approved"},
                {"party": "si", "approved_by": "JBR Team", "approved_at": now.isoformat(), "status": "approved"},
            ],
            "version": 3, "revision": 3, "approval_cycle": 1, "created_by": "user_001",
            "created_at": (now.replace(day=now.day - 5) if now.day > 5 else now).isoformat(),
            "updated_at": now.isoformat(), "notes": "Final approved BOM — ready for PO."
        }

        # ── Seed BOM 2: Idemia Network Equipment ─────────────────────────
        id_items = [
            {"line_number": 1, "description": "Cisco Catalyst 9300-48P Switch", "sku": "C9300-48P-A",
             "category": "Network Equipment", "vendor": "CDW", "quantity": 12, "unit_price": 6700,
             "extended_price": 80400, "term": "one-time", "order_sequence": 2,
             "eol_flag": True, "eol_warning": "EOS 2028-01-31", "replacement_sku": "C9300X-48P-A"},
            {"line_number": 2, "description": "Cisco Catalyst 9500-48Y4C Core Switch", "sku": "C9500-48Y4C-A",
             "category": "Network Equipment", "vendor": "PC Connection", "quantity": 2, "unit_price": 38500,
             "extended_price": 77000, "term": "one-time", "order_sequence": 2, "eol_flag": False},
            {"line_number": 3, "description": "3yr SmartNet — Catalyst 9300", "sku": "CON-SNT-C9300",
             "category": "Maintenance", "vendor": "Cisco Direct", "quantity": 12, "unit_price": 670,
             "extended_price": 8040, "term": "3-year", "order_sequence": 5, "eol_flag": False},
        ]
        id_total = sum(i["extended_price"] for i in id_items)
        self.collections["boms"]["bom_idemia_001"] = {
            "_id": "bom_idemia_001", "bom_id": "bom_idemia_001",
            "project_name": "Idemia", "category": "Network Equipment",
            "line_items": id_items,
            "totals": {"hardware": 157400, "software": 0, "services": 8040,
                       "bundled": 0, "subtotal": id_total, "total_otc": id_total,
                       "total_run_costs_annual": 0, "tco_3year": id_total},
            "status": "review",
            "approvals": [
                {"party": "buyer_it", "approved_by": "Buyer Team", "approved_at": now.isoformat(), "status": "approved", "locked": False},
                {"party": "seller_it", "status": "pending", "locked": False},
                {"party": "si", "status": "pending", "locked": True},
            ],
            "version": 1, "revision": 1, "approval_cycle": 1, "created_by": "user_001",
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
            "notes": "WARNING: C9300-48P-A is EOL — consider C9300X upgrade."
        }

        # ── Seed BOM 3: Tenneco Cybersecurity ────────────────────────────
        ten_items = [
            {"line_number": 1, "description": "CrowdStrike Falcon Enterprise (1yr)", "sku": "CS-FALCON-ENT",
             "category": "Cybersecurity", "vendor": "CDW", "quantity": 2500, "unit_price": 72,
             "extended_price": 180000, "term": "1-year", "order_sequence": 5, "eol_flag": False},
            {"line_number": 2, "description": "Palo Alto NGFW PA-3440", "sku": "PA-3440",
             "category": "Cybersecurity", "vendor": "CDW", "quantity": 4, "unit_price": 24500,
             "extended_price": 98000, "term": "one-time", "order_sequence": 2, "eol_flag": False},
            {"line_number": 3, "description": "5% Spares — Critical NIC/PSU", "sku": "SPARES-KIT",
             "category": "Spares", "vendor": "Dell", "quantity": 1, "unit_price": 12000,
             "extended_price": 12000, "term": "one-time", "order_sequence": 4, "eol_flag": False},
        ]
        ten_total = sum(i["extended_price"] for i in ten_items)
        self.collections["boms"]["bom_tenneco_001"] = {
            "_id": "bom_tenneco_001", "bom_id": "bom_tenneco_001",
            "project_name": "Tenneco", "category": "Cybersecurity",
            "line_items": ten_items,
            "totals": {"hardware": 98000, "software": 180000, "services": 12000,
                       "bundled": 0, "subtotal": ten_total, "total_otc": ten_total,
                       "total_run_costs_annual": 180000, "tco_3year": ten_total + 360000},
            "status": "draft",
            "approvals": [
                {"party": "buyer_it", "status": "pending", "locked": False},
                {"party": "seller_it", "status": "pending", "locked": True},
                {"party": "si", "status": "pending", "locked": True},
            ],
            "version": 1, "revision": 1, "approval_cycle": 1, "created_by": "user_001",
            "created_at": now.isoformat(), "updated_at": now.isoformat(), "notes": ""
        }

        logger.info("Seeded mock database: 3 BOMs (Panasonic, Idemia, Tenneco), 1 user, 1 template")
    
    # Generic CRUD Operations
    def create_item(self, container_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """Create item in mock storage"""
        item_id = item.get("_id") or item.get("id") or str(uuid.uuid4())
        item["_id"] = item_id
        item["id"] = item_id
        
        self.collections[container_name][item_id] = item
        logger.info(f"Mock created item in {container_name}: {item_id}")
        return item
    
    def read_item(
        self, 
        container_name: str, 
        item_id: str, 
        partition_key: str
    ) -> Optional[Dict[str, Any]]:
        """Read item from mock storage"""
        item = self.collections[container_name].get(item_id)
        if item:
            logger.info(f"Mock read item from {container_name}: {item_id}")
        else:
            logger.warning(f"Mock item not found: {item_id} in {container_name}")
        return item
    
    def update_item(
        self, 
        container_name: str, 
        item_id: str, 
        item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update item in mock storage"""
        item["updated_at"] = datetime.utcnow().isoformat()
        self.collections[container_name][item_id] = item
        logger.info(f"Mock updated item in {container_name}: {item_id}")
        return item
    
    def delete_item(
        self, 
        container_name: str, 
        item_id: str, 
        partition_key: str
    ):
        """Delete item from mock storage"""
        if item_id in self.collections[container_name]:
            del self.collections[container_name][item_id]
            logger.info(f"Mock deleted item from {container_name}: {item_id}")
    
    def query_items(
        self, 
        container_name: str, 
        query: str, 
        parameters: Optional[List[Dict[str, Any]]] = None,
        partition_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Mock query - returns all items in container"""
        # Simplified mock query - just returns all items
        items = list(self.collections[container_name].values())
        logger.info(f"Mock query on {container_name}: returned {len(items)} items")
        return items
    
    # BOM-specific operations (dict-based API used by REST layer)
    def create_bom(self, bom_data: dict) -> dict:
        """Create BOM in mock storage"""
        return self.create_item("boms", bom_data)

    def get_bom(self, bom_id: str) -> Optional[dict]:
        """Get BOM from mock storage"""
        return self.read_item("boms", bom_id, bom_id)

    def update_bom(self, bom_id: str, bom_data: dict) -> dict:
        """Update BOM in mock storage"""
        return self.update_item("boms", bom_id, bom_data)

    def list_boms(self, filters: Optional[dict] = None, limit: int = 100) -> List[dict]:
        """List BOMs from mock storage with optional dict filters"""
        items = list(self.collections["boms"].values())
        if filters:
            if filters.get("category"):
                items = [i for i in items if i.get("category") == filters["category"]]
            if filters.get("status"):
                items = [i for i in items if i.get("status") == filters["status"]]
            if filters.get("user_id"):
                items = [i for i in items if i.get("user_id") == filters["user_id"]]
        return items[:limit]

    # Session-specific operations (dict-based API used by REST layer)
    def create_session(self, session_data: dict) -> dict:
        """Create session in mock storage"""
        return self.create_item("sessions", session_data)

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session from mock storage"""
        return self.read_item("sessions", session_id, session_id)

    def update_session(self, session_id: str, session_data: dict) -> dict:
        """Update session in mock storage"""
        return self.update_item("sessions", session_id, session_data)

    def list_sessions(self, user_id: str = None, limit: int = 50) -> list:
        """List sessions ordered by updated_at desc, optionally filtered by user_id"""
        items = list(self.collections["sessions"].values())
        if user_id:
            items = [s for s in items if s.get("user_id") == user_id]
        items.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        # Return lightweight summary (no full conversation payload)
        return [
            {
                "session_id": s.get("session_id") or s.get("_id"),
                "user_id": s.get("user_id"),
                "status": s.get("status", "active"),
                "created_at": s.get("created_at"),
                "updated_at": s.get("updated_at"),
                "message_count": len(s.get("conversation", [])),
                "context": s.get("context", {}),
            }
            for s in items[:limit]
        ]

    def close(self):
        """Mock close - no-op"""
        logger.info("Mock Cosmos DB closed (no-op)")
