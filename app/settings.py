"""
app/settings.py — Domain-specific application settings.

Extends BaseAgentSettings with fields that belong to the BOM / Vendor Contracting
platform but have no place in the reusable framework layer.

Usage:
    from app.settings import get_settings
    settings = get_settings()
    print(settings.sharepoint_site_url)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field

from framework.settings import BaseAgentSettings


class AppSettings(BaseAgentSettings):
    """
    Full application settings = framework infrastructure + domain specifics.

    Still frozen=True (inherited) so this instance is safe for module-level
    caching and concurrent access.
    """

    # ------------------------------------------------------------------
    # Feature flags — domain only
    # ------------------------------------------------------------------
    use_dummy_sharepoint: bool = Field(default=True, alias="USE_DUMMY_SHAREPOINT")

    # ------------------------------------------------------------------
    # SharePoint / Microsoft Graph API
    # ------------------------------------------------------------------
    sharepoint_site_url: str = Field(
        default="https://dummy.sharepoint.com/sites/dummy",
        alias="SHAREPOINT_SITE_URL",
    )
    sharepoint_client_id: str = Field(
        default="dummy-sp-client-id", alias="SHAREPOINT_CLIENT_ID"
    )
    sharepoint_client_secret: str = Field(
        default="dummy-sp-client-secret", alias="SHAREPOINT_CLIENT_SECRET"
    )
    sharepoint_tenant_id: str = Field(default="", alias="SHAREPOINT_TENANT_ID")
    sharepoint_drive_path: str = Field(default="BOMs", alias="SHAREPOINT_DRIVE_PATH")

    # ------------------------------------------------------------------
    # SMTP email notifications (leave blank → console-only logging)
    # ------------------------------------------------------------------
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(
        default="noreply@it-contracting-dashboard.com", alias="SMTP_FROM"
    )

    # ------------------------------------------------------------------
    # SendGrid (alternative transactional email)
    # ------------------------------------------------------------------
    sendgrid_api_key: str = Field(
        default="dummy-sendgrid-key", alias="SENDGRID_API_KEY"
    )
    from_email: str = Field(default="noreply@dummy.com", alias="FROM_EMAIL")


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """
    Return the singleton AppSettings instance.

    Using @lru_cache means the object is constructed once and reused on every
    subsequent call — safe because the model is frozen (immutable).
    """
    return AppSettings()
