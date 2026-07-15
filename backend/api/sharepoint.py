"""
SharePoint Upload API
POST /api/sharepoint/upload  — upload a file to the SharePoint document library
GET  /api/sharepoint/files   — list files in a folder
"""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from db.sharepoint_client import get_sharepoint_client

logger = logging.getLogger(__name__)

# BOM ingest pipeline — imported lazily so SharePoint still works without search deps
def _trigger_ingest(background_tasks: BackgroundTasks, bom_id: str, filename: str,
                    data: bytes, vendor: str, category: str) -> None:
    try:
        from services.bom_ingest import ingest_bom_background
        background_tasks.add_task(
            ingest_bom_background,
            bom_id=bom_id,
            filename=filename,
            data=data,
            vendor=vendor,
            category=category,
            metadata={"source": "sharepoint_upload"},
        )
        logger.info("BOM ingest pipeline queued | bom_id=%s filename=%s", bom_id, filename)
    except Exception as exc:
        logger.warning("Could not queue ingest pipeline: %s", exc)

router = APIRouter(prefix="/api/sharepoint", tags=["sharepoint"])

_ALLOWED_TYPES = {
    "application/pdf", "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword", "text/csv", "text/plain",
    "application/json",
    "image/png", "image/jpeg",
}
_MAX_BYTES = 20 * 1024 * 1024   # 20 MB


@router.post("/upload")
async def upload_to_sharepoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    folder: str = Form(default="BOMs"),
    bom_id: Optional[str] = Form(default=None),
    vendor: str = Form(default=""),
    category: str = Form(default=""),
):
    """Upload a document to SharePoint and trigger the BOM embedding pipeline."""
    # Validate content type
    ct = file.content_type or "application/octet-stream"
    if ct not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{ct}' is not allowed. Supported: PDF, Excel, Word, CSV, JSON, images.",
        )

    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds 20 MB limit ({len(content) // (1024*1024)} MB uploaded).",
        )

    effective_bom_id = bom_id or str(uuid.uuid4())

    sp = get_sharepoint_client()
    if sp is None:
        # Graceful mock response when SharePoint is disabled
        logger.info("SharePoint mock: would upload '%s' to folder '%s'", file.filename, folder)
        _trigger_ingest(background_tasks, effective_bom_id, file.filename or "bom.xlsx",
                        content, vendor, category)
        return {
            "success": True,
            "mock": True,
            "bom_id": effective_bom_id,
            "filename": file.filename,
            "folder": folder,
            "web_url": f"https://xoriant.sharepoint.com/sites/PWC_Project_Planning_Hub/Shared%20Documents/PWC_Vendor_Contracting_Hub/{file.filename}",
            "message": "SharePoint is in demo mode — file was not actually uploaded. Embedding pipeline started.",
            "ingest_status_url": f"/api/ingest/status/{effective_bom_id}",
        }

    # Use the configured drive_path as folder if caller passed generic default
    effective_folder = folder if folder != "BOMs" else sp.drive_path
    try:
        result = sp.upload_file(content, file.filename, folder_path=effective_folder)
        _trigger_ingest(background_tasks, effective_bom_id, file.filename or "bom.xlsx",
                        content, vendor, category)
        return {
            "success": True,
            "mock": False,
            "bom_id": effective_bom_id,
            "ingest_status_url": f"/api/ingest/status/{effective_bom_id}",
            **result,
        }
    except Exception as exc:
        logger.error("SharePoint upload failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SharePoint upload failed: {exc}",
        )


@router.get("/files")
async def list_sharepoint_files(folder: str = "BOMs"):
    """List files in a SharePoint folder."""
    sp = get_sharepoint_client()
    if sp is None:
        return {"mock": True, "folder": folder, "files": []}
    try:
        files = sp.list_folder(folder_path=folder)
        return {"mock": False, "folder": folder, "files": files}
    except Exception as exc:
        logger.error("SharePoint list failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SharePoint list failed: {exc}",
        )
