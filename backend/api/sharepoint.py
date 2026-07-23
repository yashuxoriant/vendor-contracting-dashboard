"""
SharePoint Upload API
POST /api/sharepoint/upload  — upload a file to the SharePoint document library
GET  /api/sharepoint/files   — list files in a folder
"""
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from db.sharepoint_client import get_sharepoint_client

logger = logging.getLogger(__name__)

# BOM ingest pipeline — imported lazily so SharePoint still works without search deps
def _trigger_ingest(background_tasks: BackgroundTasks, bom_id: str, filename: str,
                    data: bytes, vendor: str, category: str,
                    sp_file_id: str = "", sp_etag: str = "",
                    folder_path: str = "", sharepoint_path: str = "") -> None:
    try:
        from services.bom_ingest import ingest_bom_background
        background_tasks.add_task(
            ingest_bom_background,
            bom_id=bom_id,
            filename=filename,
            data=data,
            vendor=vendor,
            category=category,
            sp_file_id=sp_file_id,
            sp_etag=sp_etag,
            folder_path=folder_path,
            sharepoint_path=sharepoint_path,
            metadata={"source": "sharepoint_upload"},
        )
        logger.info("BOM ingest pipeline queued | bom_id=%s sp_file_id=%s filename=%s",
                    bom_id, sp_file_id or "(none)", filename)
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
    # Resolve the effective folder: always nest category inside the configured drive root
    # Result path: Shared Documents/<drive_path>/<category>/filename
    drive_root = sp.drive_path if sp else "PWC_Vendor_Contracting_Hub"
    if folder and folder not in ("BOMs", ""):
        effective_folder = f"{drive_root}/{folder.strip('/')}"
    else:
        effective_folder = drive_root

    if sp is None:
        # Graceful mock response when SharePoint is disabled
        logger.info("SharePoint mock: would upload '%s' to folder '%s'", file.filename, effective_folder)
        _trigger_ingest(background_tasks, effective_bom_id, file.filename or "bom.xlsx",
                        content, vendor, category,
                        folder_path=effective_folder,
                        sharepoint_path=f"{effective_folder}/{file.filename}")
        return {
            "success": True,
            "mock": True,
            "bom_id": effective_bom_id,
            "filename": file.filename,
            "folder": effective_folder,
            "web_url": f"https://xoriant.sharepoint.com/sites/PWC_Project_Planning_Hub/Shared%20Documents/{effective_folder}/{file.filename}",
            "message": "SharePoint is in demo mode — file was not actually uploaded. Embedding pipeline started.",
            "ingest_status_url": f"/api/ingest/status/{effective_bom_id}",
        }

    try:
        result = sp.upload_file(content, file.filename, folder_path=effective_folder)
        sp_file_id = result.get("id") or ""
        _trigger_ingest(background_tasks, effective_bom_id, file.filename or "bom.xlsx",
                        content, vendor, category,
                        sp_file_id=sp_file_id,
                        folder_path=effective_folder,
                        sharepoint_path=f"{effective_folder}/{file.filename}")
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


@router.post("/upload/batch")
async def upload_batch_to_sharepoint(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    folder: str = Form(default="BOMs"),
    vendor: str = Form(default=""),
    category: str = Form(default=""),
):
    """
    Upload multiple BOM files to SharePoint and trigger the embedding pipeline for each.

    Returns a summary with per-file success/error and ingest_status_url for polling.
    Files are processed independently — one failure does not block the others.
    """
    sp = get_sharepoint_client()
    drive_root = sp.drive_path if sp else "PWC_Vendor_Contracting_Hub"
    effective_folder = (
        f"{drive_root}/{folder.strip('/')}"
        if folder and folder not in ("BOMs", "")
        else drive_root
    )

    results = []
    for file in files:
        effective_bom_id = str(uuid.uuid4())
        entry: dict = {"filename": file.filename, "bom_id": effective_bom_id}
        try:
            ct = file.content_type or "application/octet-stream"
            if ct not in _ALLOWED_TYPES:
                entry["success"] = False
                entry["error"] = f"File type '{ct}' is not allowed."
                results.append(entry)
                continue

            content = await file.read()
            if len(content) > _MAX_BYTES:
                entry["success"] = False
                entry["error"] = f"File exceeds 20 MB limit ({len(content) // (1024 * 1024)} MB)."
                results.append(entry)
                continue

            if sp is None:
                # Mock / demo mode
                logger.info("SharePoint mock batch: would upload '%s'", file.filename)
                _trigger_ingest(
                    background_tasks, effective_bom_id, file.filename or "bom.xlsx",
                    content, vendor, category,
                    folder_path=effective_folder,
                    sharepoint_path=f"{effective_folder}/{file.filename}",
                )
                entry.update({
                    "success": True, "mock": True,
                    "folder": effective_folder,
                    "web_url": (
                        f"https://xoriant.sharepoint.com/sites/PWC_Project_Planning_Hub"
                        f"/Shared%20Documents/{effective_folder}/{file.filename}"
                    ),
                    "ingest_status_url": f"/api/ingest/status/{effective_bom_id}",
                })
            else:
                sp_result = sp.upload_file(content, file.filename, folder_path=effective_folder)
                sp_file_id = sp_result.get("id") or ""
                _trigger_ingest(
                    background_tasks, effective_bom_id, file.filename or "bom.xlsx",
                    content, vendor, category,
                    sp_file_id=sp_file_id,
                    folder_path=effective_folder,
                    sharepoint_path=f"{effective_folder}/{file.filename}",
                )
                entry.update({
                    "success": True, "mock": False,
                    "ingest_status_url": f"/api/ingest/status/{effective_bom_id}",
                    **sp_result,
                })
        except Exception as exc:
            logger.error("Batch upload failed for '%s': %s", file.filename, exc)
            entry["success"] = False
            entry["error"] = str(exc)

        results.append(entry)

    succeeded = sum(1 for r in results if r.get("success"))
    return {
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "folder": effective_folder,
        "results": results,
    }


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
