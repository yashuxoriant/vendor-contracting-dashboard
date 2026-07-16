"""
SharePoint Upload API
POST /api/sharepoint/upload  — upload a file to the SharePoint document library
GET  /api/sharepoint/files   — list files in a folder
"""
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from db.sharepoint_client import get_sharepoint_client

logger = logging.getLogger(__name__)
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
    file: UploadFile = File(...),
    folder: str = Form(default="BOMs"),
):
    """Upload a document to SharePoint. Returns the web URL of the uploaded file."""
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

    sp = get_sharepoint_client()
    if sp is None:
        # Graceful mock response when SharePoint is disabled
        logger.info("SharePoint mock: would upload '%s' to folder '%s'", file.filename, folder)
        return {
            "success": True,
            "mock": True,
            "filename": file.filename,
            "folder": folder,
            "web_url": f"https://xoriant.sharepoint.com/sites/PWC_Project_Planning_Hub/Shared%20Documents/PWC_Vendor_Contracting_Hub/{file.filename}",
            "message": "SharePoint is in demo mode — file was not actually uploaded.",
        }

    # Use the configured drive_path as folder if caller passed generic default
    effective_folder = folder if folder != "BOMs" else sp.drive_path
    try:
        result = sp.upload_file(content, file.filename, folder_path=effective_folder)
        return {"success": True, "mock": False, **result}
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
