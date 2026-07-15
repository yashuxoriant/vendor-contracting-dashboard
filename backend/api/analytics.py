"""
Analytics API endpoints — Sprint 2
All endpoints query real Cosmos DB data with fallback to seeded mock data.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ── Response Models ───────────────────────────────────────────────────────────

class SpendingDataPoint(BaseModel):
    category: str
    amount: float

class SpendingResponse(BaseModel):
    period: str
    data: List[SpendingDataPoint]
    total: float

class VendorPerformance(BaseModel):
    vendor: str
    total_spend: float
    bom_count: int
    avg_delivery_time_days: int

class VendorPerformanceResponse(BaseModel):
    vendors: List[VendorPerformance]

class PatternData(BaseModel):
    pattern_id: str
    description: str
    frequency: int
    avg_cost: float

class PatternsResponse(BaseModel):
    patterns: List[PatternData]

class TrendDataPoint(BaseModel):
    month: str
    spending: float

class TrendsResponse(BaseModel):
    data: List[TrendDataPoint]

class KPIResponse(BaseModel):
    total_boms: int
    avg_cycle_time_days: float
    target_cycle_time_days: int
    boms_by_status: Dict[str, int]
    boms_pending_approval: int
    eol_warnings: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_all_boms() -> List[Dict[str, Any]]:
    """Fetch all BOMs from Cosmos (real or mock)."""
    from db import get_cosmos_client
    client = get_cosmos_client()
    return client.list_boms({}, limit=500)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/kpi", response_model=KPIResponse)
async def get_kpi():
    """KPI summary: cycle times, approval counts, EOL warnings — from real Cosmos data."""
    try:
        boms = _get_all_boms()
        total = len(boms)

        # Cycle time: created_at → updated_at for approved BOMs
        cycle_times = []
        for b in boms:
            if b.get("status") == "approved" and b.get("created_at") and b.get("updated_at"):
                try:
                    created = datetime.fromisoformat(b["created_at"].replace("Z", ""))
                    updated = datetime.fromisoformat(b["updated_at"].replace("Z", ""))
                    days = (updated - created).days
                    if 0 <= days <= 180:
                        cycle_times.append(days)
                except Exception:
                    pass

        avg_cycle = round(sum(cycle_times) / len(cycle_times), 1) if cycle_times else 0.0

        # Status breakdown
        by_status: Dict[str, int] = defaultdict(int)
        for b in boms:
            by_status[b.get("status", "draft")] += 1

        # Pending approval count (not all 3 parties approved)
        pending_approval = 0
        eol_warnings = 0
        for b in boms:
            approvals = b.get("approvals", [])
            if not all(a.get("status") == "approved" for a in approvals):
                if b.get("status") not in ("draft", "archived"):
                    pending_approval += 1
            for item in b.get("line_items", []):
                if item.get("eol_flag"):
                    eol_warnings += 1

        return KPIResponse(
            total_boms=total,
            avg_cycle_time_days=avg_cycle,
            target_cycle_time_days=3,
            boms_by_status=dict(by_status),
            boms_pending_approval=pending_approval,
            eol_warnings=eol_warnings,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KPI query failed: {e}")


@router.get("/spending", response_model=SpendingResponse)
async def get_spending(period: str = "monthly"):
    """Spending breakdown by category — aggregated from real BOM line items."""
    try:
        boms = _get_all_boms()
        by_category: Dict[str, float] = defaultdict(float)

        for b in boms:
            for item in b.get("line_items", []):
                cat = item.get("category") or "Other"
                by_category[cat] += item.get("extended_price", 0)

        # If nothing in DB yet, use totals-level category split
        if not by_category:
            for b in boms:
                t = b.get("totals", {})
                if t.get("hardware"): by_category["Compute / Hardware"] += t["hardware"]
                if t.get("software"): by_category["Software Licenses"] += t["software"]
                if t.get("services"): by_category["Services"] += t["services"]

        data = [SpendingDataPoint(category=k, amount=v)
                for k, v in sorted(by_category.items(), key=lambda x: -x[1])]
        total = sum(d.amount for d in data)

        return SpendingResponse(period=period, data=data, total=total)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Spending query failed: {e}")


@router.get("/vendors", response_model=VendorPerformanceResponse)
async def get_vendor_performance():
    """Vendor spend and BOM count — aggregated from real BOM line items."""
    try:
        boms = _get_all_boms()
        vendor_spend: Dict[str, float] = defaultdict(float)
        vendor_boms: Dict[str, set] = defaultdict(set)

        for b in boms:
            bom_id = b.get("bom_id", "")
            for item in b.get("line_items", []):
                v = item.get("vendor") or "Unknown"
                vendor_spend[v] += item.get("extended_price", 0)
                vendor_boms[v].add(bom_id)

        # Rough avg delivery time heuristic (order_sequence 1-2 = hardware = longer)
        delivery_map = {
            "CDW": 12, "PC Connection": 11, "Cisco Direct": 15,
            "Dell": 14, "Entity": 10, "IBM BP": 18, "NTT Data": 13,
        }
        vendors = [
            VendorPerformance(
                vendor=v,
                total_spend=round(spend, 2),
                bom_count=len(vendor_boms[v]),
                avg_delivery_time_days=delivery_map.get(v, 12),
            )
            for v, spend in sorted(vendor_spend.items(), key=lambda x: -x[1])
        ]
        return VendorPerformanceResponse(vendors=vendors)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vendor query failed: {e}")


@router.get("/patterns", response_model=PatternsResponse)
async def get_patterns():
    """Common line-item patterns — derived from BOM descriptions in Cosmos."""
    try:
        boms = _get_all_boms()
        desc_count: Dict[str, int] = defaultdict(int)
        desc_cost: Dict[str, float] = defaultdict(float)

        for b in boms:
            for item in b.get("line_items", []):
                key = item.get("sku") or item.get("description", "")[:60]
                if key:
                    desc_count[key] += 1
                    desc_cost[key] += item.get("extended_price", 0)

        top = sorted(desc_count.items(), key=lambda x: -x[1])[:10]
        patterns = [
            PatternData(
                pattern_id=f"pat_{i:03d}",
                description=desc,
                frequency=cnt,
                avg_cost=round(desc_cost[desc] / cnt, 2),
            )
            for i, (desc, cnt) in enumerate(top, 1)
        ]
        return PatternsResponse(patterns=patterns)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Patterns query failed: {e}")


@router.get("/trends", response_model=TrendsResponse)
async def get_trends():
    """Monthly spend trend from BOM created_at timestamps."""
    try:
        boms = _get_all_boms()
        monthly: Dict[str, float] = defaultdict(float)

        for b in boms:
            try:
                created = datetime.fromisoformat(
                    b.get("created_at", "").replace("Z", "")
                )
                key = created.strftime("%b %Y")
                total = b.get("totals", {}).get("total_otc", 0)
                monthly[key] += total
            except Exception:
                pass

        # If DB empty, return last 6 months with zeros so chart doesn't crash
        if not monthly:
            now = datetime.utcnow()
            for i in range(5, -1, -1):
                m = (now.replace(day=1) - timedelta(days=30 * i))
                monthly[m.strftime("%b %Y")] = 0.0

        # Sort chronologically
        def _sort_key(label: str):
            try:
                return datetime.strptime(label, "%b %Y")
            except Exception:
                return datetime.min

        data = [
            TrendDataPoint(month=k, spending=v)
            for k, v in sorted(monthly.items(), key=lambda x: _sort_key(x[0]))
        ]
        return TrendsResponse(data=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trends query failed: {e}")



# Response Models
class SpendingDataPoint(BaseModel):
    category: str
    amount: float


class SpendingResponse(BaseModel):
    period: str
    data: List[SpendingDataPoint]
    total: float


class VendorPerformance(BaseModel):
    vendor: str
    total_spend: float
    bom_count: int
    avg_delivery_time_days: int


class VendorPerformanceResponse(BaseModel):
    vendors: List[VendorPerformance]


class PatternData(BaseModel):
    pattern_id: str
    description: str
    frequency: int
    avg_cost: float


class PatternsResponse(BaseModel):
    patterns: List[PatternData]


class TrendDataPoint(BaseModel):
    month: str
    spending: float


class TrendsResponse(BaseModel):
    data: List[TrendDataPoint]


@router.get("/spending", response_model=SpendingResponse)
async def get_spending(period: str = "monthly"):
    """
    Get spending breakdown by category
    TODO: Query real data from Cosmos DB
    """
    try:
        # Dummy data for now
        dummy_data = [
            SpendingDataPoint(category="Network", amount=850000),
            SpendingDataPoint(category="Compute", amount=650000),
            SpendingDataPoint(category="Storage", amount=400000),
            SpendingDataPoint(category="Software", amount=350000),
            SpendingDataPoint(category="Services", amount=250000),
        ]
        
        total = sum(d.amount for d in dummy_data)
        
        return SpendingResponse(
            period=period,
            data=dummy_data,
            total=total
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get spending data: {str(e)}"
        )


@router.get("/vendors", response_model=VendorPerformanceResponse)
async def get_vendor_performance():
    """
    Get vendor performance metrics
    TODO: Query real data from Cosmos DB
    """
    try:
        # Dummy data
        vendors = [
            VendorPerformance(
                vendor="CDW",
                total_spend=1200000,
                bom_count=15,
                avg_delivery_time_days=12
            ),
            VendorPerformance(
                vendor="Entity",
                total_spend=950000,
                bom_count=12,
                avg_delivery_time_days=10
            ),
            VendorPerformance(
                vendor="Cisco Direct",
                total_spend=650000,
                bom_count=8,
                avg_delivery_time_days=15
            ),
            VendorPerformance(
                vendor="Dell",
                total_spend=450000,
                bom_count=6,
                avg_delivery_time_days=14
            ),
            VendorPerformance(
                vendor="IBM BP",
                total_spend=300000,
                bom_count=4,
                avg_delivery_time_days=18
            ),
        ]
        
        return VendorPerformanceResponse(vendors=vendors)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get vendor performance: {str(e)}"
        )


@router.get("/patterns", response_model=PatternsResponse)
async def get_patterns():
    """
    Get common patterns and bundles
    TODO: Query real patterns from Cosmos DB
    """
    try:
        # Dummy data
        patterns = [
            PatternData(
                pattern_id="pat_001",
                description="Cisco Nexus HA Pair",
                frequency=23,
                avg_cost=85000
            ),
            PatternData(
                pattern_id="pat_002",
                description="VMware + Veeam Bundle",
                frequency=19,
                avg_cost=125000
            ),
            PatternData(
                pattern_id="pat_003",
                description="Dell Server Cluster",
                frequency=15,
                avg_cost=95000
            ),
        ]
        
        return PatternsResponse(patterns=patterns)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get patterns: {str(e)}"
        )


@router.get("/trends", response_model=TrendsResponse)
async def get_trends():
    """
    Get spending trends over time
    TODO: Query real data from Cosmos DB
    """
    try:
        # Generate dummy 6-month trend
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        spending = [420000, 380000, 450000, 520000, 480000, 550000]
        
        data = [
            TrendDataPoint(month=month, spending=spend)
            for month, spend in zip(months, spending)
        ]
        
        return TrendsResponse(data=data)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trends: {str(e)}"
        )
