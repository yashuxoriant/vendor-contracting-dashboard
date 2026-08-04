"""
SharePoint Client — SharePoint REST API + Microsoft Graph API fallback
Uploads files to the PWC_Vendor_Contracting_Hub SharePoint document library.

Primary path  : SharePoint REST API (scope: https://{tenant}.sharepoint.com/.default)
                ← does NOT require Sites.ReadWrite.All admin consent
Fallback path : Microsoft Graph API  (scope: https://graph.microsoft.com/.default)
                ← requires Sites.ReadWrite.All with admin consent
"""
import logging
import mimetypes
import requests
from urllib.parse import quote
from typing import Optional

logger = logging.getLogger(__name__)


class SharePointClient:
    """Upload / list documents in a SharePoint document library."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, site_url: str, drive_path: str = "BOMs"):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.site_url = site_url.rstrip("/")
        self.drive_path = drive_path  # default subfolder under Shared Documents
        self._sp_token: Optional[str] = None   # SharePoint-scoped
        self._graph_token: Optional[str] = None  # Graph-scoped
        self._drive_id: Optional[str] = None

    # ── Helpers ───────────────────────────────────────────────────────────

    @property
    def _sp_host(self) -> str:
        """e.g. 'xoriant.sharepoint.com'"""
        return self.site_url.replace("https://", "").split("/")[0]

    @property
    def _site_relative_path(self) -> str:
        """Server-relative path, e.g. '/sites/PWC_Vendor_Contracting_Hub'"""
        without_scheme = self.site_url.replace("https://", "")
        _, _, path = without_scheme.partition("/")
        return "/" + path.strip("/")

    # ── Token acquisition ────────────────────────────────────────────────

    def _get_token(self, resource_scope: str) -> str:
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        resp = requests.post(url, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": resource_scope,
            "grant_type": "client_credentials",
        }, timeout=30)
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _sp_token_cached(self) -> str:
        if not self._sp_token:
            scope = f"https://{self._sp_host}/.default"
            self._sp_token = self._get_token(scope)
            logger.info("SharePoint: acquired SP-scoped token (host=%s)", self._sp_host)
        return self._sp_token

    def _graph_token_cached(self) -> str:
        if not self._graph_token:
            self._graph_token = self._get_token("https://graph.microsoft.com/.default")
            logger.info("SharePoint: acquired Graph-scoped token")
        return self._graph_token

    # ── Upload via SharePoint REST API (primary) ──────────────────────────

    def _upload_rest(self, file_content: bytes, filename: str, folder_path: str) -> dict:
        """
        Upload using SharePoint REST API — no admin consent required.
        folder_path is the subfolder under the default document library,
        e.g. 'BOMs' → stored in 'Shared Documents/BOMs'.
        """
        token = self._sp_token_cached()
        # Build the server-relative URL for the target folder
        site_rel = self._site_relative_path   # e.g. /sites/PWC_Vendor_Contracting_Hub
        lib_rel = f"{site_rel}/Shared Documents/{folder_path.strip('/')}"
        lib_rel_enc = quote(lib_rel)
        safe_name = quote(filename)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        upload_url = (
            f"{self.site_url}/_api/web"
            f"/GetFolderByServerRelativeUrl('{lib_rel_enc}')"
            f"/Files/add(url='{safe_name}',overwrite=true)"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "Accept": "application/json;odata=verbose",
        }
        resp = requests.post(upload_url, headers=headers, data=file_content, timeout=60)
        if resp.status_code == 404:
            # Folder may not exist — try creating it first, then retry
            self._ensure_folder_rest(token, site_rel, f"Shared Documents/{folder_path.strip('/')}")
            resp = requests.post(upload_url, headers=headers, data=file_content, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        server_relative = result.get("d", {}).get("ServerRelativeUrl", "")
        web_url = f"https://{self._sp_host}{server_relative}" if server_relative else ""
        logger.info("SharePoint REST: uploaded '%s' → %s", filename, web_url)
        return {"filename": filename, "folder": folder_path, "web_url": web_url, "size": len(file_content), "id": ""}

    def _ensure_folder_rest(self, token: str, site_rel: str, folder_rel: str):
        """Create the folder hierarchy under the document library if missing."""
        url = f"{self.site_url}/_api/web/folders"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json;odata=verbose",
            "Accept": "application/json;odata=verbose",
            "X-RequestDigest": "bypass",   # not required with OAuth app-only
        }
        body = {"__metadata": {"type": "SP.Folder"}, "ServerRelativeUrl": f"{site_rel}/{folder_rel}"}
        try:
            requests.post(url, headers=headers, json=body, timeout=30)
        except Exception as exc:
            logger.warning("Could not create folder: %s", exc)

    # ── Upload via Graph API (fallback) ───────────────────────────────────

    def _get_drive_id(self) -> str:
        if self._drive_id:
            return self._drive_id
        token = self._graph_token_cached()
        hdrs = {"Authorization": f"Bearer {token}"}
        site_rel = self._site_relative_path   # /sites/PWC_Vendor_Contracting_Hub
        site_url = f"https://graph.microsoft.com/v1.0/sites/{self._sp_host}:{site_rel}"
        r = requests.get(site_url, headers=hdrs, timeout=30)
        r.raise_for_status()
        site_id = r.json()["id"]
        r2 = requests.get(
            f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive",
            headers=hdrs, timeout=30,
        )
        r2.raise_for_status()
        self._drive_id = r2.json()["id"]
        return self._drive_id

    def _upload_graph(self, file_content: bytes, filename: str, folder_path: str) -> dict:
        drive_id = self._get_drive_id()
        token = self._graph_token_cached()
        safe_folder = quote(folder_path, safe="/")
        safe_file = quote(filename, safe="")
        upload_url = (
            f"https://graph.microsoft.com/v1.0"
            f"/drives/{drive_id}/root:/{safe_folder}/{safe_file}:/content"
        )
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        hdrs = {"Authorization": f"Bearer {token}", "Content-Type": content_type}
        r = requests.put(upload_url, headers=hdrs, data=file_content, timeout=60)
        r.raise_for_status()
        item = r.json()
        logger.info("SharePoint Graph: uploaded '%s' → %s", filename, item.get("webUrl", ""))
        return {"filename": filename, "folder": folder_path, "web_url": item.get("webUrl", ""), "size": item.get("size", len(file_content)), "id": item.get("id", "")}

    # ── Public API ────────────────────────────────────────────────────────

    def upload_file(
        self,
        file_content: bytes,
        filename: str,
        folder_path: str = "BOMs",
    ) -> dict:
        """
        Upload *file_content* to SharePoint. Tries REST API first, falls back to Graph API.
        Returns dict with filename, folder, web_url, size, id.
        """
        # Primary: SharePoint REST API
        try:
            return self._upload_rest(file_content, filename, folder_path)
        except Exception as rest_err:
            logger.warning("SharePoint REST upload failed (%s) — trying Graph API", rest_err)

        # Fallback: Graph API
        return self._upload_graph(file_content, filename, folder_path)

    def list_folder(self, folder_path: str = "BOMs") -> list:
        """List files in a SharePoint folder. Returns a list of file info dicts."""
        try:
            token = self._sp_token_cached()
            site_rel = self._site_relative_path
            lib_rel = quote(f"{site_rel}/Shared Documents/{folder_path.strip('/')}")
            url = f"{self.site_url}/_api/web/GetFolderByServerRelativeUrl('{lib_rel}')/Files"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json;odata=verbose",
            }
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 404:
                return []
            r.raise_for_status()
            items = r.json().get("d", {}).get("results", [])
            return [
                {
                    "name": i["Name"],
                    "size": i.get("Length", 0),
                    "web_url": f"https://{self._sp_host}{i['ServerRelativeUrl']}",
                    "modified": i.get("TimeLastModified", ""),
                    "is_folder": False,
                }
                for i in items
            ]
        except Exception as exc:
            logger.error("SharePoint list_folder failed: %s", exc)
            return []


# ── Singleton factory ─────────────────────────────────────────────────────

_client: Optional[SharePointClient] = None


def get_sharepoint_client() -> Optional[SharePointClient]:
    """
    Returns a SharePointClient if credentials are configured, else None.
    The caller checks for None and falls back to mock/local behaviour.
    """
    global _client
    if _client:
        return _client
    from config import get_settings
    s = get_settings()
    if s.use_dummy_sharepoint:
        logger.info("SharePoint: USE_DUMMY_SHAREPOINT=true — using mock")
        return None
    if not all([s.sharepoint_tenant_id, s.sharepoint_client_id,
                s.sharepoint_client_secret, s.sharepoint_site_url]):
        logger.warning("SharePoint: missing credentials — cannot connect")
        return None
    _client = SharePointClient(
        tenant_id=s.sharepoint_tenant_id,
        client_id=s.sharepoint_client_id,
        client_secret=s.sharepoint_client_secret,
        site_url=s.sharepoint_site_url,
        drive_path=s.sharepoint_drive_path,
    )
    return _client
