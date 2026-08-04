"""
SharePoint Graph Delta Client
Polls Microsoft Graph delta API to detect new/modified/deleted files in a
SharePoint document library folder since the last successful run.

Ported from ma-workstream-planner/ingest_backend/sharepoint_delta.py and
adapted for the it-contracting-dashboard BOM pipeline.

No external dependencies beyond stdlib + azure-storage-blob (already in requirements).
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Files that should never be ingested ───────────────────────────────────────
_SKIP_FILENAMES = {"thumbs.db", ".ds_store", "desktop.ini"}
_SKIP_EXTENSIONS = {".tmp", ".lnk", ".url"}
_MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB


def _is_skippable(item: dict) -> bool:
    name = (item.get("name") or "").strip().lower()
    if name in _SKIP_FILENAMES:
        return True
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if ext in _SKIP_EXTENSIONS:
        return True
    return False


# ── OAuth token (client credentials, cached) ──────────────────────────────────

_token_cache: dict = {}


def get_graph_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Return a cached Microsoft Graph access token (client credentials flow)."""
    now = datetime.now(timezone.utc).timestamp()
    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["token"]

    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    token = data["access_token"]
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
    logger.debug("Graph token refreshed")
    return token


def _graph_get(token: str, url: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ── Drive / folder resolution ─────────────────────────────────────────────────

def resolve_drive_context(token: str, site_url: str) -> tuple[str, str]:
    """Return (site_id, drive_id) for a SharePoint site URL."""
    parsed = urllib.parse.urlparse(site_url.rstrip("/"))
    hostname = parsed.netloc
    site_path = parsed.path
    data = _graph_get(token, f"https://graph.microsoft.com/v1.0/sites/{hostname}:{site_path}")
    site_id = data["id"]

    drives = _graph_get(token, f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives")
    drive_id = None
    for d in drives.get("value", []):
        if d.get("name", "").lower() in ("documents", "shared documents"):
            drive_id = d["id"]
            break
    if not drive_id and drives.get("value"):
        drive_id = drives["value"][0]["id"]
    if not drive_id:
        raise ValueError(f"No drives found for SharePoint site: {site_url}")
    return site_id, drive_id


def resolve_folder_item_id(token: str, drive_id: str, folder_path: str) -> str:
    """Return the Graph item ID for a folder path within a drive."""
    encoded = urllib.parse.quote(folder_path.strip("/"), safe="/")
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{encoded}"
    data = _graph_get(token, url)
    return data["id"]


def item_rel_path(item: dict, base_folder_path: str) -> Optional[str]:
    """
    Return the file path relative to base_folder_path, or None if not resolvable.
    Example: base="BOMs", item path="/drives/xyz/root:/BOMs/Vendor/file.xlsx"
             → "Vendor/file.xlsx"
    """
    parent_ref = item.get("parentReference") or {}
    parent_path = (parent_ref.get("path") or "").replace("/drives/" + (parent_ref.get("driveId") or "") + "/root:", "").strip("/")
    file_name = item.get("name") or ""
    full_path = f"{parent_path}/{file_name}".strip("/") if parent_path else file_name
    base = base_folder_path.strip("/")
    if full_path.startswith(base + "/"):
        return full_path[len(base) + 1:]
    return file_name or None  # fallback: just the filename


# ── Delta state persistence (in ADLS Blob Storage) ───────────────────────────

_DELTA_CONTAINER = "delta-state"


def _get_blob_service():
    """Return an Azure BlobServiceClient or None."""
    try:
        from config import get_settings
        conn_str = get_settings().adls_connection_string
        if not conn_str or "dummy" in conn_str:
            return None
        from azure.storage.blob import BlobServiceClient
        return BlobServiceClient.from_connection_string(conn_str)
    except Exception as exc:
        logger.debug("BlobServiceClient unavailable: %s", exc)
        return None


def _state_blob_name(folder_key: str) -> str:
    safe = folder_key.replace("/", "_").replace(" ", "-").lower()
    return f"bom-delta-{safe}.json"


def load_delta_state(folder_key: str) -> dict:
    """Load persisted delta state (delta_token + last_run) for a folder key."""
    client = _get_blob_service()
    if client is None:
        return {}
    try:
        blob = client.get_blob_client(container=_DELTA_CONTAINER, blob=_state_blob_name(folder_key))
        data = blob.download_blob().readall()
        return json.loads(data)
    except Exception:
        return {}


def save_delta_state(folder_key: str, state: dict) -> None:
    """Persist delta state dict to blob storage."""
    client = _get_blob_service()
    if client is None:
        return
    try:
        # Ensure container exists
        try:
            client.create_container(_DELTA_CONTAINER)
        except Exception:
            pass
        blob = client.get_blob_client(container=_DELTA_CONTAINER, blob=_state_blob_name(folder_key))
        blob.upload_blob(json.dumps(state, default=str), overwrite=True)
    except Exception as exc:
        logger.warning("save_delta_state failed: %s", exc)


# ── Delta fetch ───────────────────────────────────────────────────────────────

class DeltaTokenExpiredError(Exception):
    """Raised when Graph returns 410 Gone (delta token expired)."""


def fetch_delta(
    token: str,
    drive_id: str,
    folder_item_id: str,
    delta_token: Optional[str] = None,
) -> tuple[list[dict], list[dict], str]:
    """
    Fetch changed items in a folder since the last delta token.

    Returns:
        added_modified: list of new/updated Graph drive items
        deleted:        list of deleted Graph drive items
        next_delta_token: opaque token for the next call

    If delta_token is None → full enumeration (first run or after expiry).
    """
    if delta_token:
        url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/items/{folder_item_id}/delta?token={urllib.parse.quote(delta_token)}"
        )
    else:
        url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/items/{folder_item_id}/delta"
        )

    added_modified: list[dict] = []
    deleted: list[dict] = []
    next_link: Optional[str] = url
    delta_link: Optional[str] = None

    while next_link:
        try:
            data = _graph_get(token, next_link)
        except urllib.error.HTTPError as exc:
            if exc.code == 410:
                raise DeltaTokenExpiredError("Delta token expired (410 Gone)") from exc
            raise

        for item in data.get("value", []):
            if "file" not in item and "deleted" not in item:
                continue  # skip folders
            if _is_skippable(item):
                continue
            if "deleted" in item:
                deleted.append(item)
            else:
                added_modified.append(item)

        next_link = data.get("@odata.nextLink")
        if not next_link:
            delta_link = data.get("@odata.deltaLink", "")

    next_token = ""
    if delta_link:
        qs = urllib.parse.urlparse(delta_link).query
        params = urllib.parse.parse_qs(qs)
        next_token = params.get("token", [""])[0]

    logger.info(
        "Delta fetch: added/modified=%d deleted=%d folder=%s",
        len(added_modified), len(deleted), folder_item_id,
    )
    return added_modified, deleted, next_token


def download_item_content(token: str, drive_id: str, item_id: str) -> bytes:
    """Download file bytes for a Graph drive item."""
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()
