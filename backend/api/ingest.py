"""
BOM Ingest API
Provides HTTP endpoints to manually trigger or query the BOM embedding pipeline.

Routes:
  POST /api/ingest/bom              — upload a file and trigger the full pipeline
  POST /api/ingest/bom/{bom_id}     — (re-)ingest an already-uploaded BOM by ID
  GET  /api/ingest/status/{bom_id}  — poll the ingest status of a BOM
  DELETE /api/ingest/bom/{bom_id}   — remove all indexed chunks for a BOM
  POST /api/ingest/search           — test semantic search over indexed BOMs
  POST /api/ingest/delta            — manually trigger SharePoint delta pipeline
  GET  /api/ingest/delta/status     — last delta pipeline run summary
"""
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

_ALLOWED_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    "application/vnd.ms-excel",                                            # xls
    "text/csv",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/msword",
    "text/plain",
    "text/markdown",
    "application/octet-stream",  # fallback for unknown MIME
}
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


# ── POST /api/ingest/bom  (upload + pipeline) ──────────────────────────────────

@router.post("/bom")
async def ingest_bom_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    bom_id: Optional[str] = Form(default=None),
    vendor: str = Form(default=""),
    category: str = Form(default=""),
    run_sync: bool = Form(default=False),
):
    """
    Upload a BOM file and trigger the embedding pipeline.

    - run_sync=false (default): returns immediately; pipeline runs in background.
      Poll GET /api/ingest/status/{bom_id} for completion.
    - run_sync=true: waits for the pipeline to complete before responding.
      Suitable for small files and testing.
    """
    ct = file.content_type or "application/octet-stream"
    if ct not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{ct}' is not supported for BOM ingest.",
        )

    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds 20 MB limit.",
        )

    effective_bom_id = bom_id or str(uuid.uuid4())

    from services.bom_ingest import ingest_bom, ingest_bom_background

    if run_sync:
        try:
            result = ingest_bom(
                bom_id=effective_bom_id,
                filename=file.filename or "bom.xlsx",
                data=data,
                vendor=vendor,
                category=category,
                # No sp_file_id/sp_etag for direct uploads — content hash dedup still applies
            )
            return result
        except Exception as exc:
            logger.error("Sync ingest failed: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))
    else:
        background_tasks.add_task(
            ingest_bom_background,
            bom_id=effective_bom_id,
            filename=file.filename or "bom.xlsx",
            data=data,
            vendor=vendor,
            category=category,
        )
        return {
            "bom_id": effective_bom_id,
            "status": "processing",
            "message": "Pipeline started in background. Poll /api/ingest/status/{bom_id} for updates.",
        }


# ── POST /api/ingest/bom/{bom_id}  (re-ingest from ADLS) ──────────────────────

@router.post("/bom/{bom_id}")
async def reingest_bom(
    bom_id: str,
    background_tasks: BackgroundTasks,
):
    """
    Re-trigger the ingest pipeline for an already-uploaded BOM.
    Fetches the raw file from ADLS and re-runs extraction + embedding.
    """
    from services.bom_ingest import get_ingest_status, ingest_bom_background, _write_status
    from services.search_service import delete_bom_chunks, category_to_index_name

    # Read status doc first so we can route deletes to the correct index
    doc = get_ingest_status(bom_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"No ingest record for bom_id={bom_id}")

    # 1. Remove existing indexed chunks from the correct index
    index_name = doc.get("index_name") or category_to_index_name(doc.get("category", ""))
    deleted = delete_bom_chunks(bom_id, index_name)
    logger.info("reingest_bom: removed %d old chunks from '%s' for bom_id=%s",
                deleted, index_name, bom_id)

    # 2. Fetch raw bytes from ADLS
    try:
        from db import get_adls_client
        from config import get_settings
        adls = get_adls_client()
        settings = get_settings()

        filename = doc.get("filename", "bom.xlsx")
        vendor   = doc.get("vendor", "")
        category = doc.get("category", "")
        path     = doc.get("adls_path") or f"{bom_id}/{filename}"

        if adls is None or adls.service_client is None:
            raise HTTPException(status_code=503, detail="ADLS not available — cannot re-ingest")

        fs = adls.service_client.get_file_system_client(settings.adls_container_raw_boms)
        fc = fs.get_file_client(path)
        data = fc.download_file().readall()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch raw BOM from ADLS: {exc}")

    background_tasks.add_task(
        ingest_bom_background,
        bom_id=bom_id,
        filename=filename,
        data=data,
        vendor=vendor,
        category=category,
        sp_file_id=doc.get("sp_file_id", ""),
        # Don't pass sp_etag so ingest_bom does a fresh content-hash check
    )
    return {
        "bom_id": bom_id,
        "status": "reprocessing",
        "message": "Re-ingest started. Poll /api/ingest/status/{bom_id} for updates.",
    }


# ── GET /api/ingest/status/{bom_id} ───────────────────────────────────────────

@router.get("/status/{bom_id}")
async def get_ingest_status_endpoint(bom_id: str):
    """Poll the ingest pipeline status for a BOM."""
    from services.bom_ingest import get_ingest_status
    doc = get_ingest_status(bom_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No ingest record found for bom_id={bom_id}",
        )
    # Remove Cosmos internal fields before returning
    return {k: v for k, v in doc.items() if not k.startswith("_")}


# ── DELETE /api/ingest/bom/{bom_id} ───────────────────────────────────────────

@router.delete("/bom/{bom_id}")
async def delete_bom_index(bom_id: str):
    """Remove all indexed chunks for a BOM from its category-specific search index."""
    from services.search_service import delete_bom_chunks, category_to_index_name
    from services.bom_ingest import get_ingest_status
    # Read the stored index_name so we delete from the right index
    doc = get_ingest_status(bom_id)
    if doc:
        index_name = doc.get("index_name") or category_to_index_name(doc.get("category", ""))
    else:
        index_name = category_to_index_name("")  # falls back to legacy
    deleted = delete_bom_chunks(bom_id, index_name)
    return {"bom_id": bom_id, "chunks_deleted": deleted, "index": index_name}


# ── POST /api/ingest/search  (semantic search for testing) ────────────────────

@router.post("/search")
async def search_bom_index(body: Dict[str, Any]):
    """
    Semantic search over indexed BOM chunks.
    Body: {
      "query": "...",
      "top_k": 5,
      "bom_id": null,
      "category": "Network & Telecom",  // routes to category index
      "vendor": "Cisco"                 // optional vendor filter for precision
    }
    """
    query    = body.get("query", "").strip()
    top_k    = int(body.get("top_k", 5))
    bom_id   = body.get("bom_id")
    category = body.get("category", "")
    vendor   = body.get("vendor") or None

    if not query:
        raise HTTPException(status_code=400, detail="'query' is required")

    from services.search_service import search_bom_context, category_to_index_name
    index_name = category_to_index_name(category)
    results = search_bom_context(
        query=query,
        top_k=top_k,
        bom_id=bom_id,
        index_name=index_name,
        vendor=vendor,
    )
    return {
        "query":         query,
        "index":         index_name,
        "vendor_filter": vendor,
        "results":       results,
        "count":         len(results),
    }


# ── POST /api/ingest/delta  (manual SharePoint delta trigger) ─────────────────

_last_delta_summary: Dict[str, Any] = {}


@router.post("/delta")
async def trigger_delta_pipeline(
    background_tasks: BackgroundTasks,
    force_full_sync: bool = False,
):
    """
    Manually trigger the SharePoint → ADLS → Embedding delta pipeline.
    By default runs incrementally (only changes since last run).
    Set force_full_sync=true to re-process all files.
    """
    def _run(force: bool):
        global _last_delta_summary
        from services.bom_delta_pipeline import run_bom_delta_pipeline
        _last_delta_summary = run_bom_delta_pipeline(force_full_sync=force)

    background_tasks.add_task(_run, force_full_sync)
    return {
        "status": "started",
        "force_full_sync": force_full_sync,
        "message": "Delta pipeline triggered. GET /api/ingest/delta/status for result.",
    }


# ── GET /api/ingest/delta/status ──────────────────────────────────────────────

@router.get("/delta/status")
async def get_delta_status():
    """Return the summary from the last delta pipeline run."""
    if not _last_delta_summary:
        return {"status": "never_run", "message": "No delta pipeline run yet this session."}
    return _last_delta_summary
