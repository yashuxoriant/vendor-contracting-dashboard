"""
BOM SharePoint Delta Pipeline
Polls Microsoft Graph for new/changed files in the SharePoint BOMs folder,
downloads them, and runs the full ingest pipeline (extract → embed → index).

This is the it-contracting-dashboard equivalent of ma-workstream's
ingest_backend/delta_pipeline.py.

Entry points:
  run_bom_delta_pipeline()  — one-shot run (called by scheduler or manually)
  start_scheduler()         — start APScheduler background job
  stop_scheduler()          — stop scheduler cleanly on shutdown

Configuration (via .env / config.py):
  SHAREPOINT_SITE_URL                — e.g. https://tenant.sharepoint.com/sites/Hub
  SHAREPOINT_TENANT_ID               — AAD tenant id
  SHAREPOINT_CLIENT_ID               — app registration client id
  SHAREPOINT_CLIENT_SECRET           — app registration secret
  SHAREPOINT_DRIVE_PATH              — folder in Shared Documents (default: "BOMs")
  SHAREPOINT_POLL_INTERVAL_MINUTES   — 0 = disabled, e.g. 15 = poll every 15 min
  AZURE_STORAGE_CONNECTION_STRING    — used for delta-state blob persistence
"""
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── APScheduler (optional — only used when poll interval > 0) ─────────────────
_scheduler = None
_consecutive_failures = 0
_MAX_CONSECUTIVE_FAILURES = 5


def _run_with_backoff() -> None:
    """
    Scheduler-facing wrapper that tracks consecutive failures.
    After _MAX_CONSECUTIVE_FAILURES successive errors, it logs a critical alert
    and skips subsequent runs until a successful run resets the counter.
    This prevents log flooding during sustained Graph API outages.
    """
    global _consecutive_failures
    if _consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
        logger.critical(
            "BOMDeltaPipeline: %d consecutive failures — skipping run (check SharePoint/Graph connectivity)",
            _consecutive_failures,
        )
        return
    result = run_bom_delta_pipeline(force_full_sync=False)
    if result.get("status") in ("ok", "skipped"):
        if _consecutive_failures > 0:
            logger.info("BOMDeltaPipeline: recovered after %d failures", _consecutive_failures)
        _consecutive_failures = 0
    else:
        _consecutive_failures += 1
        logger.warning(
            "BOMDeltaPipeline: failure %d/%d | errors: %s",
            _consecutive_failures, _MAX_CONSECUTIVE_FAILURES,
            result.get("errors", [])[:3],
        )


def start_scheduler() -> None:
    """Start the APScheduler background job if polling is enabled in config."""
    global _scheduler
    try:
        from config import get_settings
        interval = get_settings().sharepoint_poll_interval_minutes
        if interval <= 0:
            logger.info("BOMDeltaPipeline: polling disabled (SHAREPOINT_POLL_INTERVAL_MINUTES=0)")
            return

        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(
            _run_with_backoff,    # use backoff wrapper instead of direct call
            trigger=IntervalTrigger(minutes=interval),
            id="bom_delta_pipeline",
            name="BOM SharePoint Delta Pipeline",
            max_instances=1,
            coalesce=True,  # skip missed runs instead of stacking
        )
        _scheduler.start()
        logger.info(
            "BOMDeltaPipeline: scheduler started — polling every %d minute(s)", interval
        )
    except Exception as exc:
        logger.warning("BOMDeltaPipeline: could not start scheduler: %s", exc)


def stop_scheduler() -> None:
    """Gracefully stop the APScheduler on application shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("BOMDeltaPipeline: scheduler stopped")


# ── Core pipeline ──────────────────────────────────────────────────────────────

def run_bom_delta_pipeline(force_full_sync: bool = False) -> Dict[str, Any]:
    """
    One-shot delta pipeline run.

    1. Acquire Graph token
    2. Resolve SharePoint site + drive + BOMs folder item ID
    3. Fetch delta (changes since last run)
    4. For each added/modified file → download → run bom_ingest pipeline
    5. For each deleted file → delete chunks from search index
    6. Persist next delta token

    Returns a summary dict with counts of processed/skipped/failed files.
    """
    from config import get_settings
    settings = get_settings()

    # Guard: skip if SharePoint credentials are placeholders
    if (not settings.sharepoint_site_url
            or "dummy" in settings.sharepoint_site_url
            or not settings.sharepoint_tenant_id
            or "dummy" in settings.sharepoint_tenant_id):
        logger.info("BOMDeltaPipeline: SharePoint not configured — skipping run")
        return {"status": "skipped", "reason": "SharePoint not configured"}

    summary: Dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "processed": 0,
        "skipped": 0,
        "deleted": 0,
        "failed": 0,
        "errors": [],
    }

    from services.sharepoint_delta import (
        DeltaTokenExpiredError,
        download_item_content,
        fetch_delta,
        get_graph_token,
        item_rel_path,
        load_delta_state,
        resolve_drive_context,
        resolve_folder_item_id,
        save_delta_state,
    )
    from services.bom_ingest import get_ingest_status, ingest_bom
    from services.search_service import delete_bom_chunks
    import hashlib

    folder_key = settings.sharepoint_drive_path  # e.g. "PWC_Vendor_Contracting_Hub"

    try:
        # Step 1: token + drive context
        token = get_graph_token(
            settings.sharepoint_tenant_id,
            settings.sharepoint_client_id,
            settings.sharepoint_client_secret,
        )
        _site_id, drive_id = resolve_drive_context(token, settings.sharepoint_site_url)

        # Step 2: resolve folder
        try:
            folder_item_id = resolve_folder_item_id(token, drive_id, folder_key)
        except Exception as exc:
            msg = f"BOMs folder not found in SharePoint ({folder_key}): {exc}"
            logger.warning("BOMDeltaPipeline: %s", msg)
            summary["errors"].append(msg)
            summary["status"] = "failed"
            return summary

        # Step 3: load persisted delta token
        state = load_delta_state(folder_key)
        delta_token = None if force_full_sync else state.get("delta_token")

        # Step 4: fetch changes
        try:
            added_modified, deleted_items, next_token = fetch_delta(
                token, drive_id, folder_item_id, delta_token
            )
        except DeltaTokenExpiredError:
            logger.warning("BOMDeltaPipeline: delta token expired — falling back to full sync")
            added_modified, deleted_items, next_token = fetch_delta(
                token, drive_id, folder_item_id, None
            )

        # Step 5: handle deletions
        for item in deleted_items:
            # Use the SharePoint Graph item ID directly — it's stable and
            # was used as bom_id when the file was originally ingested.
            sp_file_id = item.get("id", "")
            bom_id = sp_file_id
            if not bom_id:
                logger.warning("BOMDeltaPipeline: deleted item has no id, skipping")
                summary["skipped"] += 1
                continue
            try:
                count = delete_bom_chunks(bom_id)
                logger.info("BOMDeltaPipeline: deleted %d chunks | sp_file_id=%s", count, sp_file_id)
                summary["deleted"] += 1
            except Exception as exc:
                summary["errors"].append(f"delete:{sp_file_id}:{exc}")
                summary["failed"] += 1

        # Step 6: handle additions / modifications
        for item in added_modified:
            # Stable identity: SharePoint Graph item ID (survives renames and moves)
            sp_file_id = item.get("id", "")
            sp_etag    = (item.get("eTag") or "").strip('"')  # strip surrounding quotes from Graph
            filename   = item.get("name", "file")
            file_size  = item.get("size") or 0
            rel_path   = item_rel_path(item, folder_key) or filename

            # bom_id = SP Graph item ID (stable, unique, survives renames)
            # Fall back to path hash only if Graph didn't return an ID (shouldn't happen)
            bom_id = sp_file_id if sp_file_id else hashlib.sha256(rel_path.encode()).hexdigest()[:32]

            if file_size > 100 * 1024 * 1024:
                logger.warning("BOMDeltaPipeline: skipping oversized file %s (%d bytes)", rel_path, file_size)
                summary["skipped"] += 1
                continue

            # ── Quick-skip: compare eTag before downloading ────────────────────────
            # The Graph delta API only returns items that changed SINCE the last delta
            # token — so this check is mainly useful during force_full_sync where all
            # items are returned regardless of change.
            if sp_etag:
                existing_status = get_ingest_status(bom_id)
                if (
                    existing_status
                    and existing_status.get("status") == "indexed"
                    and existing_status.get("sp_etag") == sp_etag
                ):
                    logger.info(
                        "BOMDeltaPipeline: eTag unchanged — skipping download | path=%s", rel_path
                    )
                    summary["skipped"] += 1
                    continue

            # ── Download from SharePoint ─────────────────────────────────
            try:
                content = download_item_content(token, drive_id, sp_file_id or bom_id)
            except Exception as exc:
                logger.error("BOMDeltaPipeline: download failed | %s | %s", rel_path, exc)
                summary["errors"].append(f"download:{rel_path}:{exc}")
                summary["failed"] += 1
                continue

            # Derive category, vendor, and path metadata from folder structure.
            # SharePoint layout: PWC_Vendor_Contracting_Hub/{Category}/{filename}
            #                 or PWC_Vendor_Contracting_Hub/{Category}/{Vendor}/{filename}
            # The first subfolder is always the category (e.g. 'SD-WAN', 'Data Center - COLO').
            # If a second subfolder exists it is treated as the vendor.
            parts = rel_path.split("/")
            category    = parts[0] if len(parts) >= 1 else ""
            vendor      = parts[1] if len(parts) > 2 else ""   # optional vendor sub-folder
            folder_path = "/".join(parts[:-1])                  # directory without filename

            try:
                result = ingest_bom(
                    bom_id=bom_id,
                    filename=filename,
                    data=content,
                    vendor=vendor,
                    category=category,
                    sp_file_id=sp_file_id,
                    sp_etag=sp_etag,
                    folder_path=folder_path,
                    sharepoint_path=rel_path,
                    metadata={"source": "delta_pipeline"},
                )
                if result.get("status") == "skipped":
                    logger.info("BOMDeltaPipeline: content hash unchanged — skipped | path=%s", rel_path)
                    summary["skipped"] += 1
                else:
                    logger.info(
                        "BOMDeltaPipeline: ingested %s | chunks=%s",
                        rel_path, result.get("chunks_upserted", "?"),
                    )
                    summary["processed"] += 1
            except Exception as exc:
                logger.error("BOMDeltaPipeline: ingest failed | %s | %s", rel_path, exc)
                summary["errors"].append(f"ingest:{rel_path}:{exc}")
                summary["failed"] += 1

        # Step 7: save next delta token
        save_delta_state(folder_key, {
            "delta_token": next_token,
            "last_run": datetime.now(timezone.utc).isoformat(),
        })

        summary["status"] = "ok"
        summary["completed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(
            "BOMDeltaPipeline: run complete | processed=%d skipped=%d deleted=%d failed=%d",
            summary["processed"], summary["skipped"], summary["deleted"], summary["failed"],
        )
        return summary

    except Exception as exc:
        logger.error("BOMDeltaPipeline: unhandled error: %s", exc, exc_info=True)
        summary["status"] = "failed"
        summary["errors"].append(str(exc))
        return summary
