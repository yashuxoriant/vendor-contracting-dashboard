"""
BOM management API endpoints — Sprint 1
Added: proper Excel export via openpyxl, audit logging hooks, fixed cosmos client calls.
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import io
import json

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from db import get_cosmos_client, BOM, BOMStatus, BOMApproval, ApprovalStatus

# EOL service — best-effort import (doesn't break if missing)
try:
    from services.eol_service import check_eol_status, check_bom_eol
    _EOL_AVAILABLE = True
except ImportError:
    _EOL_AVAILABLE = False

router = APIRouter(prefix="/api/bom", tags=["bom"])


# Request/Response Models
class BOMListRequest(BaseModel):
    user_id: Optional[str] = None
    category: Optional[str] = None
    status: Optional[BOMStatus] = None
    limit: int = 50


class BOMResponse(BaseModel):
    bom: BOM


class BOMListResponse(BaseModel):
    boms: List[BOM]
    count: int


class BOMUpdateRequest(BaseModel):
    line_items: Optional[List[Dict[str, Any]]] = None
    status: Optional[BOMStatus] = None
    notes: Optional[str] = None


class ValidateResponse(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []


@router.get("/{bom_id}", response_model=BOMResponse)
async def get_bom(bom_id: str):
    """
    Get a specific BOM by ID
    """
    try:
        cosmos_client = get_cosmos_client()
        
        bom_data = cosmos_client.get_bom(bom_id)
        if not bom_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="BOM not found"
            )
        
        return BOMResponse(bom=BOM.model_validate(bom_data))
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get BOM: {str(e)}"
        )


@router.get("", response_model=BOMListResponse)
async def list_boms(
    user_id: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """
    List BOMs with optional filters
    """
    try:
        cosmos_client = get_cosmos_client()
        
        # Build query
        filters = {}
        if user_id:
            filters["user_id"] = user_id
        if category:
            filters["category"] = category
        if status:
            filters["status"] = status
        
        boms_data = cosmos_client.list_boms(filters, limit)
        boms = [BOM.model_validate(bom) for bom in boms_data]
        
        return BOMListResponse(
            boms=boms,
            count=len(boms)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list BOMs: {str(e)}"
        )


@router.put("/{bom_id}", response_model=BOMResponse)
async def update_bom(bom_id: str, request: BOMUpdateRequest):
    """
    Update a BOM
    """
    try:
        cosmos_client = get_cosmos_client()
        
        # Get existing BOM
        bom_data = cosmos_client.get_bom(bom_id)
        if not bom_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="BOM not found"
            )
        
        bom = BOM(**bom_data)
        
        # Update fields
        if request.line_items is not None:
            bom.line_items = request.line_items
        if request.status is not None:
            bom.status = request.status
        if request.notes is not None:
            bom.notes = request.notes
        
        bom.updated_at = datetime.utcnow()
        
        # Save
        cosmos_client.update_bom(bom_id, bom.model_dump())
        
        return BOMResponse(bom=bom)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update BOM: {str(e)}"
        )


@router.post("/validate", response_model=ValidateResponse)
async def validate_bom(bom: BOM):
    """
    Validate a BOM for completeness and correctness
    """
    try:
        errors = []
        warnings = []
        
        # Check required fields
        if not bom.line_items:
            errors.append("BOM must have at least one line item")
        
        # Check line items
        for idx, item in enumerate(bom.line_items):
            if not item.description:
                errors.append(f"Line {idx + 1}: Missing description")
            if item.quantity <= 0:
                errors.append(f"Line {idx + 1}: Quantity must be greater than 0")
            if item.unit_price < 0:
                errors.append(f"Line {idx + 1}: Unit price cannot be negative")
            if item.eol_flag:
                warnings.append(f"Line {idx + 1}: {item.description} is EOL/EOS — consider replacement")
            # Live EOL check via eol_service if SKU is present
            if _EOL_AVAILABLE and item.sku:
                eol_info = check_eol_status(item.sku)
                if eol_info["eos_flag"]:
                    errors.append(f"Line {idx + 1}: SKU {item.sku} — End-of-Support reached. {eol_info['message']}")
                elif eol_info["eol_flag"]:
                    warnings.append(f"Line {idx + 1}: SKU {item.sku} — {eol_info['message']}")
            # Dual-quote warning
            if item.extended_price > 50000 and not item.vendor:
                warnings.append(f"Line {idx + 1}: Item over $50K has no vendor — dual quote required")
        
        # Check totals
        if bom.totals:
            calculated_total = sum(item.extended_price for item in bom.line_items)
            if abs(calculated_total - bom.totals.total_otc) > 0.01:
                warnings.append(
                    f"Total mismatch: Line items sum to ${calculated_total:.2f} "
                    f"but totals show ${bom.totals.total_otc:.2f}"
                )
        
        # 3-party approval warnings
        if hasattr(bom, 'approvals') and bom.approvals:
            pending = [a.party for a in bom.approvals if a.status == "pending"]
            if pending and bom.status == BOMStatus.APPROVED:
                errors.append(f"BOM is marked approved but missing sign-offs from: {', '.join(pending)}")
            elif pending:
                warnings.append(f"Pending approvals: {', '.join(pending)}")  

        return ValidateResponse(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate BOM: {str(e)}"
        )


@router.get("/eol/check/{sku}")
async def check_sku_eol(sku: str):
    """
    Check a single SKU for EOL/EOS status.
    Returns severity, dates, and recommended replacement.
    """
    if not _EOL_AVAILABLE:
        return {"sku": sku, "found": False, "message": "EOL service not available", "severity": "none"}
    result = check_eol_status(sku)
    return result


@router.post("/eol/check-bom")
async def check_bom_eol_endpoint(body: dict):
    """
    Run EOL check on all SKUs in a BOM payload.
    Accepts {"line_items": [...]} and returns enriched items.
    """
    if not _EOL_AVAILABLE:
        return {"line_items": body.get("line_items", []), "eol_count": 0, "eos_count": 0}
    line_items = body.get("line_items", [])
    enriched = check_bom_eol(line_items)
    eol_count = sum(1 for i in enriched if i.get("eol_flag"))
    return {"line_items": enriched, "eol_count": eol_count, "eos_count": 0}


@router.get("/{bom_id}/approvals")
async def get_approvals(bom_id: str):
    """Get current 3-party approval status for a BOM."""
    cosmos_client = get_cosmos_client()
    bom_data = cosmos_client.get_bom(bom_id)
    if not bom_data:
        raise HTTPException(status_code=404, detail="BOM not found")
    return {"bom_id": bom_id, "approvals": bom_data.get("approvals", [])}


class ApprovalRequest(BaseModel):
    party: str          # "buyer_it" | "seller_it" | "si"
    approved_by: str
    action: str = "approve"   # "approve" | "request_changes" | "reject"
    comments: Optional[str] = None
    change_description: Optional[str] = None  # detail of what must change (for request_changes)
    user_id: Optional[str] = "demo_user"

    # Legacy compat — callers that still pass approved: bool map to action
    approved: Optional[bool] = None

    def resolved_action(self) -> str:
        """Normalise legacy 'approved' bool → action string."""
        if self.approved is not None and self.action == "approve":
            return "approve" if self.approved else "request_changes"
        return self.action

# Sequential order enforced: buyer_it → seller_it → si
_APPROVAL_ORDER = ["buyer_it", "seller_it", "si"]
_PARTY_LABEL = {"buyer_it": "Buyer IT", "seller_it": "Seller IT", "si": "SI / JBR"}


@router.post("/{bom_id}/approve")
async def approve_bom(bom_id: str, request: ApprovalRequest):
    """
    Record a 3-party approval action.

    Sequential enforcement:
      - Seller IT cannot act until Buyer IT has approved.
      - SI cannot act until Seller IT has approved.

    Actions:
      - approve          → mark party as approved; advance to next party or finalise BOM.
      - request_changes  → BOM needs a rebuild; all subsequent parties reset to pending;
                           BOM status → revision_required; revision counter incremented.
      - reject           → hard rejection (terminates the BOM; rarely used).

    Reset logic:
      - Any request_changes resets all downstream parties and increments approval_cycle.
      - The BOM creator must rebuild the BOM (create a new version) before re-submission.
    """
    action = request.resolved_action()
    if request.party not in _APPROVAL_ORDER:
        raise HTTPException(status_code=400, detail="party must be buyer_it, seller_it, or si")
    if action not in ("approve", "request_changes", "reject"):
        raise HTTPException(status_code=400, detail="action must be approve, request_changes, or reject")
    if action == "request_changes" and not (request.change_description or request.comments):
        raise HTTPException(status_code=400, detail="change_description or comments required when requesting changes")

    cosmos_client = get_cosmos_client()
    bom_data = cosmos_client.get_bom(bom_id)
    if not bom_data:
        raise HTTPException(status_code=404, detail="BOM not found")

    approvals = bom_data.get("approvals", [
        {"party": "buyer_it", "status": "pending"},
        {"party": "seller_it", "status": "pending", "locked": True},
        {"party": "si",        "status": "pending", "locked": True},
    ])
    # Normalise to list-of-dicts keyed by party
    appr_map = {a["party"]: a for a in approvals}

    # ── Sequential enforcement ───────────────────────────────────────────────
    party_idx = _APPROVAL_ORDER.index(request.party)
    for prior in _APPROVAL_ORDER[:party_idx]:
        if appr_map.get(prior, {}).get("status") != "approved":
            raise HTTPException(
                status_code=409,
                detail=f"{_PARTY_LABEL[prior]} must approve before {_PARTY_LABEL[request.party]} can act."
            )

    now = datetime.utcnow().isoformat()
    revision = bom_data.get("revision", 1)
    approval_cycle = bom_data.get("approval_cycle", 1)

    target = appr_map.get(request.party, {"party": request.party})

    if action == "approve":
        target.update({
            "status": "approved",
            "approved_by": request.approved_by,
            "approved_at": now,
            "comments": request.comments or "",
            "locked": False,
        })
        # Unlock the next party in sequence
        if party_idx + 1 < len(_APPROVAL_ORDER):
            next_party = _APPROVAL_ORDER[party_idx + 1]
            appr_map.get(next_party, {}).update({"locked": False})

    elif action == "request_changes":
        target.update({
            "status": "changes_requested",
            "approved_by": request.approved_by,
            "approved_at": now,
            "comments": request.comments or "",
            "change_description": request.change_description or request.comments or "",
            "locked": False,
        })
        # Reset all downstream parties to pending + re-lock them
        for downstream in _APPROVAL_ORDER[party_idx + 1:]:
            appr_map[downstream] = {
                "party": downstream, "status": "pending",
                "locked": True, "approved_by": None, "approved_at": None,
                "comments": None, "change_description": None,
            }
        # Also reset earlier parties so the full cycle restarts after rebuild
        for prior in _APPROVAL_ORDER[:party_idx]:
            appr_map[prior] = {
                "party": prior, "status": "pending",
                "locked": False, "approved_by": None, "approved_at": None,
                "comments": None, "change_description": None,
            }
        bom_data["status"] = "revision_required"
        revision += 1
        approval_cycle += 1

    elif action == "reject":
        target.update({
            "status": "rejected",
            "approved_by": request.approved_by,
            "approved_at": now,
            "comments": request.comments or "",
        })
        bom_data["status"] = "archived"

    appr_map[request.party] = target
    updated_approvals = list(appr_map.values())
    bom_data["approvals"] = updated_approvals
    bom_data["updated_at"] = now
    bom_data["revision"] = revision
    bom_data["approval_cycle"] = approval_cycle

    # Auto-finalise BOM when all 3 parties approved
    all_approved = all(appr_map.get(p, {}).get("status") == "approved" for p in _APPROVAL_ORDER)
    if all_approved:
        bom_data["status"] = "approved"

    cosmos_client.update_bom(bom_id, bom_data)

    try:
        from api.audit import log_action
        log_action(
            user_id=request.user_id,
            action=action,
            resource_type="bom",
            resource_id=bom_id,
            details={
                "party": request.party, "approved_by": request.approved_by,
                "all_approved": all_approved, "revision": revision,
                "approval_cycle": approval_cycle,
                "change_description": request.change_description,
            },
        )
    except Exception:
        pass

    return {
        "bom_id": bom_id,
        "party": request.party,
        "action": action,
        "all_approved": all_approved,
        "bom_status": bom_data["status"],
        "revision": revision,
        "approval_cycle": approval_cycle,
        "approvals": updated_approvals,
        "message": (
            "BOM fully approved — ready for vendor submission." if all_approved
            else f"Changes requested by {_PARTY_LABEL[request.party]}. BOM must be rebuilt. Cycle #{approval_cycle} restarted."
            if action == "request_changes"
            else f"{_PARTY_LABEL[request.party]} approved. Next: {_PARTY_LABEL.get(_APPROVAL_ORDER[party_idx + 1], 'N/A')}."
            if party_idx + 1 < len(_APPROVAL_ORDER) and action == "approve"
            else f"{_PARTY_LABEL[request.party]} approved."
        ),
    }


@router.get("/{bom_id}/export/excel")
async def export_bom_excel(bom_id: str, user_id: Optional[str] = "demo_user"):
    """
    Export BOM as a properly formatted Excel (.xlsx) file.
    Matches the column layout expected by Entity/CDW vendor templates.
    """
    try:
        cosmos_client = get_cosmos_client()
        bom_data = cosmos_client.get_bom(bom_id)

        # If not in DB, try to get from request body (for chat-generated BOMs not yet saved)
        if not bom_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOM not found")

        wb = _build_excel_workbook(bom_data)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        bom_name = bom_data.get("project_name", bom_id).replace(" ", "_")
        filename = f"{bom_name}_BOM.xlsx"

        # Log the export
        try:
            from api.audit import log_action
            log_action(
                user_id=user_id,
                action="exported",
                resource_type="bom",
                resource_id=bom_id,
                details={"format": "excel", "filename": filename},
            )
        except Exception:
            pass

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Export failed: {str(e)}")


@router.post("/{bom_id}/export/excel")
async def export_bom_excel_from_body(bom_id: str, bom_data: Dict[str, Any], user_id: Optional[str] = "demo_user"):
    """
    Export an arbitrary BOM dict (from chat session) as Excel.
    Used by frontend when the BOM is not yet persisted in the database.
    """
    try:
        wb = _build_excel_workbook(bom_data)
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        bom_name = bom_data.get("name", bom_data.get("project", "BOM")).replace(" ", "_")
        filename = f"{bom_name}.xlsx"

        try:
            from api.audit import log_action
            log_action(user_id=user_id, action="exported", resource_type="bom", resource_id=bom_id,
                       details={"format": "excel", "filename": filename, "source": "chat_session"})
        except Exception:
            pass

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Export failed: {str(e)}")


def _build_excel_workbook(bom_data: dict) -> openpyxl.Workbook:
    """
    Build a properly formatted Excel workbook from a BOM dict.
    Supports both DB BOM objects (line_items as Pydantic) and chat-generated BOMs (line_items as dicts).
    """
    wb = openpyxl.Workbook()
    ws = wb.active

    # ── Colour palette ──
    ORANGE      = "D04A02"
    DARK        = "1F2937"
    LIGHT_GREY  = "F9FAFB"
    WHITE       = "FFFFFF"
    WARN_YELLOW = "FEF3C7"
    WARN_TEXT   = "92400E"

    header_font   = Font(name="Calibri", bold=True, color=WHITE, size=11)
    meta_label    = Font(name="Calibri", bold=True, color=DARK, size=10)
    meta_value    = Font(name="Calibri", color=DARK, size=10)
    item_font     = Font(name="Calibri", size=10)
    total_font    = Font(name="Calibri", bold=True, color=DARK, size=11)
    warn_font     = Font(name="Calibri", color=WARN_TEXT, size=9, italic=True)
    orange_fill   = PatternFill("solid", fgColor=ORANGE)
    grey_fill     = PatternFill("solid", fgColor=LIGHT_GREY)
    warn_fill     = PatternFill("solid", fgColor=WARN_YELLOW)
    thin_border   = Border(
        bottom=Side(style="thin", color="E5E7EB"),
        top=Side(style="thin", color="E5E7EB"),
    )
    center        = Alignment(horizontal="center", vertical="center")
    wrap          = Alignment(wrap_text=True, vertical="top")

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 40
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 10
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 14
    ws.column_dimensions["H"].width = 16
    ws.column_dimensions["I"].width = 8
    ws.column_dimensions["J"].width = 5

    row = 1
    # ── Title bar ──
    ws.merge_cells(f"A{row}:J{row}")
    cell = ws[f"A{row}"]
    cell.value = "BILL OF MATERIALS"
    cell.font = Font(name="Calibri", bold=True, color=WHITE, size=14)
    cell.fill = orange_fill
    cell.alignment = center
    ws.row_dimensions[row].height = 28
    row += 1

    # ── Metadata block ──
    project_name = bom_data.get("project_name") or bom_data.get("project", "—")
    category     = bom_data.get("category", "—")
    bom_name     = bom_data.get("name", f"{project_name} - {category}")
    bom_status   = bom_data.get("status", "draft")
    created_at   = str(bom_data.get("created_at", datetime.utcnow().strftime("%Y-%m-%d")))[:10]
    version      = bom_data.get("version", 1)

    meta = [
        ("BOM Name",  bom_name),
        ("Project",   project_name),
        ("Category",  category),
        ("Status",    bom_status),
        ("Version",   f"v{version}"),
        ("Date",      created_at),
        ("Approvals Required", "Buyer IT  |  Seller IT  |  SI Technical Team"),
    ]
    for label, value in meta:
        ws[f"A{row}"].value = label
        ws[f"A{row}"].font = meta_label
        ws.merge_cells(f"B{row}:E{row}")
        ws[f"B{row}"].value = value
        ws[f"B{row}"].font = meta_value
        row += 1

    row += 1  # blank separator

    # ── Column headers ──
    headers = ["#", "Category", "Description / Specification", "SKU / Part Number",
               "Qty", "Unit", "Unit Price (USD)", "Ext Price (USD)", "Term", "Order Seq"]
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=col_idx, value=h)
        c.font = header_font
        c.fill = PatternFill("solid", fgColor=DARK)
        c.alignment = center
    ws.row_dimensions[row].height = 18
    row += 1

    # ── Line items ──
    raw_items = bom_data.get("line_items", [])

    def _get(item, key, default=""):
        """Works for both dict and Pydantic object."""
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    for i, item in enumerate(raw_items):
        fill = grey_fill if i % 2 == 0 else PatternFill("solid", fgColor=WHITE)
        eol  = bool(_get(item, "eol_flag", False))
        row_fill = warn_fill if eol else fill
        vals = [
            _get(item, "line_number", i + 1),
            _get(item, "category", ""),
            _get(item, "description", ""),
            _get(item, "sku", ""),
            _get(item, "qty", 1),
            _get(item, "unit", "/unit"),
            _get(item, "unit_price", 0),
            _get(item, "extended_price", 0),
            _get(item, "term", "one-time"),
            _get(item, "order_sequence", ""),
        ]
        for col_idx, val in enumerate(vals, start=1):
            c = ws.cell(row=row, column=col_idx, value=val)
            c.font = warn_font if eol else item_font
            c.fill = row_fill
            c.border = thin_border
            if col_idx in (5,):
                c.alignment = center
            if col_idx in (7, 8):
                c.number_format = '"$"#,##0.00'
            if col_idx == 3:
                c.alignment = wrap
        if eol:
            ws.cell(row=row, column=3).value = "⚠ EOL: " + str(_get(item, "description", ""))
        row += 1

    # ── Totals row ──
    totals = bom_data.get("totals", {})
    if isinstance(totals, dict):
        total_otc = totals.get("total_otc", 0) or totals.get("total", 0)
        hw        = totals.get("hardware", 0)
        sw        = totals.get("software", 0)
        svc       = totals.get("services", 0)
        tco3      = totals.get("tco_3year", 0)
    else:
        total_otc = getattr(totals, "total_otc", 0)
        hw        = getattr(totals, "hardware", 0)
        sw        = getattr(totals, "software", 0)
        svc       = getattr(totals, "services", 0)
        tco3      = getattr(totals, "tco_3year", 0)

    row += 1
    totals_data = [
        ("Hardware OTC", hw), ("Software OTC", sw),
        ("Services OTC", svc), ("TOTAL OTC", total_otc), ("3-Year TCO", tco3),
    ]
    for label, val in totals_data:
        ws.merge_cells(f"A{row}:F{row}")
        c_lbl = ws[f"A{row}"]
        c_lbl.value = label
        c_lbl.font = total_font
        c_lbl.fill = PatternFill("solid", fgColor=DARK) if label in ("TOTAL OTC", "3-Year TCO") else grey_fill
        if label in ("TOTAL OTC", "3-Year TCO"):
            c_lbl.font = Font(name="Calibri", bold=True, color=WHITE, size=11)
        ws.merge_cells(f"G{row}:H{row}")
        c_val = ws[f"G{row}"]
        c_val.value = val
        c_val.number_format = '"$"#,##0.00'
        c_val.font = Font(name="Calibri", bold=True, color=DARK if label not in ("TOTAL OTC", "3-Year TCO") else WHITE, size=11)
        c_val.fill = PatternFill("solid", fgColor=DARK) if label in ("TOTAL OTC", "3-Year TCO") else grey_fill
        row += 1

    # ── Warnings / notes ──
    warnings = bom_data.get("warnings", [])
    if warnings:
        row += 1
        ws[f"A{row}"].value = "WARNINGS & FLAGS"
        ws[f"A{row}"].font = Font(name="Calibri", bold=True, color=WARN_TEXT, size=10)
        row += 1
        for w in warnings:
            ws.merge_cells(f"A{row}:J{row}")
            c = ws[f"A{row}"]
            c.value = "⚠  " + str(w)
            c.font = warn_font
            c.fill = warn_fill
            row += 1

    # ── Approval sign-off block ──
    row += 1
    ws.merge_cells(f"A{row}:J{row}")
    ws[f"A{row}"].value = "APPROVAL SIGN-OFF  (all 3 required before BOM is final)"
    ws[f"A{row}"].font = Font(name="Calibri", bold=True, color=WHITE, size=10)
    ws[f"A{row}"].fill = orange_fill
    row += 1
    for approver in ["Buyer IT", "Seller IT", "SI / Technical Team"]:
        ws[f"A{row}"].value = approver
        ws[f"A{row}"].font = meta_label
        ws.merge_cells(f"B{row}:D{row}")
        ws[f"B{row}"].value = "Name:"
        ws[f"E{row}"].value = "Date:"
        ws.merge_cells(f"F{row}:G{row}")
        ws[f"F{row}"].value = "Signature:"
        for col in range(1, 8):
            ws.cell(row=row, column=col).border = thin_border
        row += 1

    ws.freeze_panes = "A13"  # freeze above line items
    ws.title = "BOM"
    return wb
