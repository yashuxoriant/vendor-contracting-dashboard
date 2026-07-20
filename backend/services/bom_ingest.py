"""
BOM Ingest Pipeline — Orchestrator
Ties together: file bytes → extractor → embeddings → Azure Search index
               + status tracking in Cosmos DB

Full pipeline:
  1. Receive file bytes + metadata (bom_id, filename, vendor, category)
  2. Upload raw bytes to ADLS (raw-boms container)
  3. Extract text chunks from the file (bom_extractor)
  4. Embed all chunks in batches (embedding_service)
  5. Upsert embedded chunks into Azure Search (search_service)
  6. Write ingest status record to Cosmos DB (bom-ingest-status container)
  7. On error: mark status as 'failed' and re-raise

Designed to be called:
  - Synchronously from a REST endpoint (small files)
  - As a FastAPI BackgroundTask (post-upload, non-blocking)
"""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.bom_extractor import extract_chunks
from services.embedding_service import embed_batch
from services.search_service import (
    BOMChunkDocument,
    category_to_index_name,
    delete_bom_chunks,
    ensure_index,
    upsert_chunks,
)

logger = logging.getLogger(__name__)


# ── Status helpers ─────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chunk_id(bom_id: str, content_hash: str, chunk_index: int) -> str:
    """Version-aware chunk ID: changes when file content changes, preventing stale duplicates."""
    raw = f"{bom_id}::{content_hash[:16]}::{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def _get_ingest_container():
    """Return the Cosmos 'bom-ingest-status' container, or None."""
    try:
        from db import get_cosmos_client
        client = get_cosmos_client()
        if client is None or client.database is None:
            return None
        from azure.cosmos import PartitionKey
        try:
            container = client.database.create_container_if_not_exists(
                id="bom-ingest-status",
                partition_key=PartitionKey(path="/bom_id"),
            )
            return container
        except Exception:
            return client.database.get_container_client("bom-ingest-status")
    except Exception as exc:
        logger.warning("_get_ingest_container: %s", exc)
        return None


def _write_status(bom_id: str, status: str, detail: str = "", extra: dict = None):
    container = _get_ingest_container()
    if container is None:
        return
    try:
        doc = {
            "id": bom_id,
            "bom_id": bom_id,
            "status": status,
            "detail": detail,
            "updated_at": _now(),
            **(extra or {}),
        }
        # Preserve created_at on updates
        try:
            existing = container.read_item(item=bom_id, partition_key=bom_id)
            doc["created_at"] = existing.get("created_at", _now())
        except Exception:
            doc["created_at"] = _now()
        container.upsert_item(doc)
    except Exception as exc:
        logger.warning("_write_status failed: %s", exc)


def get_ingest_status(bom_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve the ingest status document for a given BOM ID."""
    container = _get_ingest_container()
    if container is None:
        return None
    try:
        return container.read_item(item=bom_id, partition_key=bom_id)
    except Exception:
        return None


# ── ADLS raw upload ────────────────────────────────────────────────────────────

def _upload_raw_to_adls(data: bytes, filename: str, bom_id: str) -> Optional[str]:
    """Upload raw BOM bytes to ADLS raw-boms container. Returns path or None."""
    try:
        from db import get_adls_client
        from config import get_settings
        adls = get_adls_client()
        settings = get_settings()
        if adls is None or adls.service_client is None:
            return None
        path = f"{bom_id}/{filename}"
        fs = adls.service_client.get_file_system_client(settings.adls_container_raw_boms)
        fc = fs.get_file_client(path)
        fc.upload_data(data, overwrite=True)
        logger.info("ADLS: uploaded raw BOM to %s/%s", settings.adls_container_raw_boms, path)
        return path
    except Exception as exc:
        logger.warning("_upload_raw_to_adls failed: %s", exc)
        return None


# ── Main pipeline ──────────────────────────────────────────────────────────────

def ingest_bom(
    *,
    bom_id: str,
    filename: str,
    data: bytes,
    vendor: str = "",
    category: str = "",        # top-level SharePoint folder name (e.g. 'SD-WAN')
    sp_file_id: str = "",      # SharePoint Graph item ID — stable across renames/moves
    sp_etag: str = "",         # SharePoint eTag — stored for quick-skip on subsequent syncs
    folder_path: str = "",     # parent folder(s) relative to drive root, e.g. 'SD-WAN'
    sharepoint_path: str = "", # full relative path within the drive, e.g. 'SD-WAN/quote.xlsx'
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Full ingest pipeline for a single BOM file.

    Args:
        bom_id:     Unique BOM identifier. For SP-sourced files this MUST be the
                    SharePoint Graph item ID so it remains stable across renames.
        filename:   Original filename (drives format detection)
        data:       Raw file bytes
        vendor:     Vendor name (stored as metadata on each chunk)
        category:   BOM category (e.g. 'Data Center', 'SD-WAN')
        sp_file_id: SharePoint Graph item ID (may equal bom_id for delta-pipeline files)
        sp_etag:    SharePoint eTag — persisted so subsequent delta runs can skip unchanged files
        metadata:   Optional extra fields stored in status record

    Returns:
        Status dict: {bom_id, status, chunks_total, chunks_upserted, adls_path, ...}
        status == 'skipped' when content hash is unchanged (idempotent call).
    """
    logger.info("BOMIngest: starting | bom_id=%s filename=%s size=%d bytes",
                bom_id, filename, len(data))

    # Derive the category-specific Azure Search index name
    # e.g. 'SD-WAN' → 'bom-sd-wan', 'Data Center - COLO' → 'bom-data-center-colo'
    index_name = category_to_index_name(category)

    # ── Idempotency: compute content hash and skip if unchanged ────────────────────
    content_hash = hashlib.sha256(data).hexdigest()

    existing = get_ingest_status(bom_id)
    if (
        existing
        and existing.get("status") == "indexed"
        and existing.get("content_hash") == content_hash
    ):
        logger.info(
            "BOMIngest: skipping unchanged content | bom_id=%s hash=%s...",
            bom_id, content_hash[:8],
        )
        return {
            "bom_id":       bom_id,
            "status":       "skipped",
            "reason":       "content unchanged",
            "content_hash": content_hash,
            "filename":     filename,
        }

    _write_status(bom_id, "processing", detail="pipeline started", extra={
        "filename":        filename,
        "vendor":          vendor,
        "category":        category,
        "index_name":      index_name,
        "sp_file_id":      sp_file_id,
        "sp_etag":         sp_etag,
        "folder_path":     folder_path,
        "sharepoint_path": sharepoint_path,
        **(metadata or {}),
    })

    # Step 1 — upload raw to ADLS
    adls_path = _upload_raw_to_adls(data, filename, bom_id)

    # Step 2 — ensure the category-specific Azure Search index exists
    ensure_index(index_name)

    # Step 3 — delete stale chunks from the correct index if this is a re-ingest
    if existing and existing.get("status") == "indexed":
        # Use the stored index_name in case the category changed since last ingest
        prev_index = existing.get("index_name") or index_name
        old_count = delete_bom_chunks(bom_id, prev_index)
        logger.info("BOMIngest: removed %d stale chunks for bom_id=%s from index=%s",
                    old_count, bom_id, prev_index)

    # Step 4 — extract text chunks
    chunks = extract_chunks(data, filename)
    if not chunks:
        _write_status(bom_id, "failed", detail="No extractable content found in file")
        return {"bom_id": bom_id, "status": "failed", "detail": "No extractable content"}

    # Step 5 — embed all chunk texts in batch
    texts = [chunk_text for chunk_text, _ in chunks]
    try:
        embeddings = embed_batch(texts)
    except Exception as exc:
        _write_status(bom_id, "failed", detail=f"Embedding failed: {exc}")
        raise

    # Step 6 — build BOMChunkDocument objects with version-aware IDs
    # Chunk ID = sha256(bom_id::content_hash[:16]::chunk_index)
    # → changes whenever content changes, so old chunks are never silently kept
    effective_sp_file_id = sp_file_id or bom_id
    docs = []
    for i, ((chunk_text, chunk_meta), embedding) in enumerate(zip(chunks, embeddings)):
        docs.append(BOMChunkDocument(
            id=_chunk_id(bom_id, content_hash, i),
            bom_id=bom_id,
            filename=filename,
            vendor=vendor,
            category=category,
            chunk_index=i,
            chunk_text=chunk_text,
            embedding=embedding,
            sp_file_id=effective_sp_file_id,
            content_hash=content_hash,
            sp_etag=sp_etag,
            folder_path=folder_path,
            sharepoint_path=sharepoint_path or filename,
            metadata=chunk_meta,
        ))

    # Step 7 — upsert into the category-specific search index
    try:
        upserted = upsert_chunks(docs, index_name)
    except Exception as exc:
        _write_status(bom_id, "failed", detail=f"Search upsert failed: {exc}")
        raise

    # Step 8 — update status with content hash and index_name for future dedup + routing
    result = {
        "bom_id":           bom_id,
        "status":           "indexed",
        "filename":         filename,
        "vendor":           vendor,
        "category":         category,
        "index_name":       index_name,
        "chunks_total":     len(docs),
        "chunks_upserted":  upserted,
        "adls_path":        adls_path,
        "indexed_at":       _now(),
        "content_hash":     content_hash,
        "sp_file_id":       effective_sp_file_id,
        "sp_etag":          sp_etag,
        "folder_path":      folder_path,
        "sharepoint_path":  sharepoint_path or filename,
    }
    _write_status(bom_id, "indexed", detail=f"{upserted} chunks indexed in {index_name}", extra=result)
    logger.info("BOMIngest: complete | bom_id=%s index=%s chunks=%d/%d",
                bom_id, index_name, upserted, len(docs))
    return result


def ingest_bom_background(
    *,
    bom_id: str,
    filename: str,
    data: bytes,
    vendor: str = "",
    category: str = "",
    sp_file_id: str = "",
    sp_etag: str = "",
    folder_path: str = "",
    sharepoint_path: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Fire-and-forget wrapper for use as a FastAPI BackgroundTask.
    Swallows exceptions so the background task doesn't crash the worker.
    """
    try:
        ingest_bom(
            bom_id=bom_id,
            filename=filename,
            data=data,
            vendor=vendor,
            category=category,
            sp_file_id=sp_file_id,
            sp_etag=sp_etag,
            folder_path=folder_path,
            sharepoint_path=sharepoint_path,
            metadata=metadata,
        )
    except Exception as exc:
        logger.error("ingest_bom_background unhandled error | bom_id=%s | %s", bom_id, exc)
        _write_status(bom_id, "failed", detail=str(exc))
