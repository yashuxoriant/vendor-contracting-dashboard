"""
framework/settings.py — Domain-agnostic base settings.

All infrastructure concerns (LLM, Cosmos, ADLS, Auth, Search) live here.
Domain-specific settings (SharePoint, SMTP, app branding) go in app/settings.py.

Rules:
  - frozen=True  → immutable after construction; safe to cache with @lru_cache
  - No imports from `app/` or any domain module
  - Every field must have a default so the app starts without a full .env file
    (dummies are acceptable for local dev; production *must* override via env/Key Vault)
"""

from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


# ---------------------------------------------------------------------------
# LLM sub-group (used as field documentation — fields are inlined on the model)
# ---------------------------------------------------------------------------
#   Anthropic Claude fields  : anthropic_api_key, claude_model_*, claude_max_tokens,
#                              claude_temperature
#   Direct OpenAI fields     : openai_api_key, openai_model_default
#   Azure OpenAI fields      : azure_openai_*
# ---------------------------------------------------------------------------


class BaseAgentSettings(BaseSettings):
    """
    Frozen base settings for the agentic framework layer.
    Extend this in app/settings.py to add domain-specific fields.
    """

    model_config = ConfigDict(
        frozen=True,         # immutable → safe for @lru_cache / module-level singleton
        env_file=".env",
        case_sensitive=False,
        extra="ignore",      # silently drop unknown env vars
    )

    # ------------------------------------------------------------------
    # Application metadata
    # ------------------------------------------------------------------
    app_name: str = Field(default="IT BOM Creation System")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # ------------------------------------------------------------------
    # Feature flags — local dev safe-mode when Azure services unavailable
    # ------------------------------------------------------------------
    use_dummy_cosmos: bool = Field(default=True, alias="USE_DUMMY_COSMOS")
    use_dummy_adls: bool = Field(default=True, alias="USE_DUMMY_ADLS")
    use_dummy_claude: bool = Field(default=False, alias="USE_DUMMY_CLAUDE")
    use_azure_openai: bool = Field(default=False, alias="USE_AZURE_OPENAI")

    # ------------------------------------------------------------------
    # Server
    # ------------------------------------------------------------------
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        alias="ALLOWED_ORIGINS",
    )

    # ------------------------------------------------------------------
    # Azure AD / Entra ID  (Step 13 will add JWKS RS256 on top of these)
    # ------------------------------------------------------------------
    azure_tenant_id: str = Field(default="dummy-tenant-id", alias="AZURE_TENANT_ID")
    azure_client_id: str = Field(default="dummy-client-id", alias="AZURE_CLIENT_ID")
    azure_client_secret: str = Field(
        default="dummy-client-secret", alias="AZURE_CLIENT_SECRET"
    )

    # ------------------------------------------------------------------
    # Azure Cosmos DB
    # ------------------------------------------------------------------
    cosmos_db_endpoint: str = Field(
        default="https://dummy.documents.azure.com:443/", alias="COSMOS_DB_ENDPOINT"
    )
    cosmos_db_key: str = Field(default="dummy-cosmos-key", alias="COSMOS_DB_KEY")
    cosmos_db_database: str = Field(default="it-bom-db", alias="COSMOS_DB_DATABASE")

    # Container names (no aliases → read from env key matching field name)
    cosmos_container_sessions: str = Field(default="sessions")
    cosmos_container_boms: str = Field(default="boms")
    cosmos_container_patterns: str = Field(default="patterns")
    cosmos_container_templates: str = Field(default="templates")
    cosmos_container_analytics: str = Field(default="analytics")
    cosmos_container_users: str = Field(default="users")

    # ------------------------------------------------------------------
    # Azure Data Lake Storage (ADLS Gen2)
    # ------------------------------------------------------------------
    adls_account_name: str = Field(default="dummystorage", alias="ADLS_ACCOUNT_NAME")
    adls_account_key: str = Field(
        default="dummy-storage-key", alias="ADLS_ACCOUNT_KEY"
    )
    adls_container_raw_boms: str = Field(
        default="raw-boms", alias="ADLS_CONTAINER_RAW_BOMS"
    )
    adls_container_processed: str = Field(
        default="processed-boms", alias="ADLS_CONTAINER_PROCESSED"
    )
    adls_container_templates: str = Field(
        default="templates", alias="ADLS_CONTAINER_TEMPLATES"
    )
    adls_container_exports: str = Field(
        default="exports", alias="ADLS_CONTAINER_EXPORTS"
    )
    adls_container_chat_history: str = Field(
        default="chat-history", alias="ADLS_CONTAINER_CHAT_HISTORY"
    )

    # ------------------------------------------------------------------
    # LLM — Anthropic Claude (primary)
    # ------------------------------------------------------------------
    anthropic_api_key: str = Field(
        default="dummy-api-key", alias="ANTHROPIC_API_KEY"
    )
    claude_model_default: str = Field(default="claude-opus-4-6")
    claude_model_fast: str = Field(default="claude-haiku-4-5")
    claude_model_complex: str = Field(default="claude-opus-4-6")
    claude_max_tokens: int = Field(default=4096)
    claude_temperature: float = Field(default=0.3)

    # ------------------------------------------------------------------
    # LLM — Direct OpenAI (fallback)
    # ------------------------------------------------------------------
    openai_api_key: str = Field(
        default="dummy-openai-key", alias="OPENAI_API_KEY"
    )
    openai_model_default: str = Field(default="gpt-4o", alias="OPENAI_MODEL_DEFAULT")

    # ------------------------------------------------------------------
    # LLM — Azure OpenAI (alternative primary)
    # ------------------------------------------------------------------
    azure_openai_endpoint: str = Field(
        default="https://dummy.openai.azure.com/", alias="AZURE_OPENAI_ENDPOINT"
    )
    azure_openai_api_key: str = Field(
        default="dummy-azure-openai-key", alias="AZURE_OPENAI_API_KEY"
    )
    azure_openai_chat_deployment: str = Field(
        default="gpt-4", alias="AZURE_OPENAI_CHAT_DEPLOYMENT"
    )
    azure_openai_api_version: str = Field(
        default="2024-02-15-preview", alias="AZURE_OPENAI_API_VERSION"
    )
    azure_openai_chat_endpoint: str = Field(
        default="", alias="AZURE_OPENAI_CHAT_ENDPOINT"
    )
    azure_openai_max_tokens: int = Field(default=4096)
    azure_openai_temperature: float = Field(default=0.3)

    # ------------------------------------------------------------------
    # Azure AI Search  (Step 11 — RAG retriever will read these)
    # ------------------------------------------------------------------
    azure_search_endpoint: str = Field(
        default="", alias="AZURE_SEARCH_ENDPOINT"
    )
    azure_search_admin_key: str = Field(
        default="", alias="AZURE_SEARCH_ADMIN_KEY"
    )

    # ------------------------------------------------------------------
    # Azure Key Vault (optional — used by production secret loader)
    # ------------------------------------------------------------------
    keyvault_url: str = Field(
        default="https://dummy-keyvault.vault.azure.net/",
        alias="KEYVAULT_URL",
    )

    # ------------------------------------------------------------------
    # JWT  (HS256 symmetric — Step 13 will layer Entra JWKS RS256 on top)
    # ------------------------------------------------------------------
    jwt_secret_key: str = Field(
        default="dev-secret-change-in-production", alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_minutes: int = Field(default=60)

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------
    rate_limit_per_minute: int = Field(default=60)
