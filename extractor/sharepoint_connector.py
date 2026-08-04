# extractor/sharepoint_connector.py
# ═══════════════════════════════════════════════
# Handles all SharePoint connectivity via
# Microsoft Graph API — authentication,
# folder listing and file downloading
# ═══════════════════════════════════════════════

import requests
import time
from config import (
    AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET,
    AZURE_TENANT_ID,
    SHAREPOINT_SITE_URL,
    SHAREPOINT_BASE_PATH,
    FOLDER_TO_CATEGORY,
    MAX_RETRIES,
)


class SharePointConnector:

    def __init__(self):
        self.token    = None
        self.site_id  = None
        self.drive_id = None
        self.headers  = {}

    # ══════════════════════════════════════
    #  AUTHENTICATION
    # ══════════════════════════════════════
    def connect(self):
        """
        Authenticate with Microsoft Graph API
        using Azure App Registration credentials
        """
        print("🔐 Authenticating with Microsoft Graph...")

        url = (
            f"https://login.microsoftonline.com/"
            f"{AZURE_TENANT_ID}/oauth2/v2.0/token"
        )
        data = {
            "client_id":     AZURE_CLIENT_ID,
            "client_secret": AZURE_CLIENT_SECRET,
            "scope":         "https://graph.microsoft.com/.default",
            "grant_type":    "client_credentials",
        }

        r = requests.post(url, data=data, timeout=30)
        r.raise_for_status()

        self.token = r.json()["access_token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type":  "application/json",
        }

        print("✅ Authentication successful")
        self._get_site_info()

    def _get_site_info(self):
        """Get SharePoint site ID and drive ID"""

        # Parse site URL
        url_clean = SHAREPOINT_SITE_URL.replace("https://", "")
        parts     = url_clean.split("/", 1)
        host      = parts[0]
        sp_path   = parts[1] if len(parts) > 1 else ""

        # Get site
        r = requests.get(
            f"https://graph.microsoft.com/v1.0"
            f"/sites/{host}:/{sp_path}",
            headers=self.headers,
            timeout=30
        )
        r.raise_for_status()
        self.site_id = r.json()["id"]
        print(f"   Site ID: {self.site_id[:30]}...")

        # Get default drive
        r2 = requests.get(
            f"https://graph.microsoft.com/v1.0"
            f"/sites/{self.site_id}/drive",
            headers=self.headers,
            timeout=30
        )
        r2.raise_for_status()
        self.drive_id = r2.json()["id"]
        print(f"   Drive ID: {self.drive_id[:30]}...")

    # ══════════════════════════════════════
    #  FOLDER LISTING
    # ══════════════════════════════════════
    def list_all_category_files(self):
        """
        List all files across all category folders.
        Returns dict: { category: [file_info, ...] }
        """
        all_files = {}

        for folder_name, category in FOLDER_TO_CATEGORY.items():
            print(f"\n📁 Scanning: {folder_name}")
            folder_path = f"{SHAREPOINT_BASE_PATH}/{folder_name}"
            files = self._list_folder_recursive(folder_path)
            all_files[category] = files
            print(f"   Found {len(files)} files")
            time.sleep(0.5)

        return all_files

    def _list_folder_recursive(self, folder_path, depth=0):
        """
        Recursively list all files in a folder
        including subfolders
        """
        if depth > 3:
            return []  # Max depth protection

        files = []

        try:
            encoded = requests.utils.quote(folder_path)
            r = requests.get(
                f"https://graph.microsoft.com/v1.0"
                f"/sites/{self.site_id}"
                f"/drive/root:/{encoded}:/children"
                f"?$top=200",
                headers=self.headers,
                timeout=30
            )

            if r.status_code == 404:
                print(f"   ⚠️  Folder not found: {folder_path}")
                return []

            r.raise_for_status()
            items = r.json().get("value", [])

            for item in items:
                if "file" in item:
                    # It's a file
                    files.append({
                        "name":         item["name"],
                        "download_url": item.get(
                            "@microsoft.graph.downloadUrl", ""
                        ),
                        "size":         item.get("size", 0),
                        "modified":     item.get(
                            "lastModifiedDateTime", ""
                        ),
                        "path":         folder_path,
                        "web_url":      item.get("webUrl", ""),
                        "id":           item.get("id", ""),
                    })

                elif "folder" in item:
                    # It's a subfolder — recurse
                    sub_path = f"{folder_path}/{item['name']}"
                    sub_files = self._list_folder_recursive(
                        sub_path, depth + 1
                    )
                    files.extend(sub_files)

        except requests.exceptions.RequestException as e:
            print(f"   ❌ Error listing folder: {e}")

        return files

    # ══════════════════════════════════════
    #  FILE DOWNLOAD
    # ══════════════════════════════════════
    def download_file(self, file_info):
        """
        Download file bytes from SharePoint.
        Retries up to MAX_RETRIES times on failure.
        """
        download_url = file_info.get("download_url", "")
        filename     = file_info.get("name", "unknown")

        if not download_url:
            raise ValueError(f"No download URL for {filename}")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = requests.get(
                    download_url,
                    timeout=120,
                    stream=True
                )
                r.raise_for_status()
                return r.content

            except requests.exceptions.RequestException as e:
                if attempt == MAX_RETRIES:
                    raise
                print(
                    f"   ⚠️  Download attempt {attempt} failed: {e}"
                    f" — retrying..."
                )
                time.sleep(2 ** attempt)  # Exponential backoff

    def get_file_metadata(self, file_id):
        """Get extra metadata for a file by ID"""
        try:
            r = requests.get(
                f"https://graph.microsoft.com/v1.0"
                f"/sites/{self.site_id}"
                f"/drive/items/{file_id}",
                headers=self.headers,
                timeout=30
            )
            r.raise_for_status()
            return r.json()
        except Exception:
            return {}

    def test_connection(self):
        """Quick test to verify connection works"""
        try:
            self.connect()
            base_path = SHAREPOINT_BASE_PATH
            encoded   = requests.utils.quote(base_path)
            r = requests.get(
                f"https://graph.microsoft.com/v1.0"
                f"/sites/{self.site_id}"
                f"/drive/root:/{encoded}:/children"
                f"?$top=5",
                headers=self.headers,
                timeout=30
            )
            r.raise_for_status()
            items = r.json().get("value", [])
            print(f"✅ Connection test passed")
            print(f"   Found {len(items)} items in base folder")
            for item in items:
                print(f"   → {item['name']}")
            return True
        except Exception as e:
            print(f"❌ Connection test failed: {e}")
            return False
