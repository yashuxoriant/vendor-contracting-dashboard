"""
Application Configuration
Loads settings from environment variables and Azure Key Vault
"""

from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field
import os

# Resolve .env relative to this file so it loads regardless of CWD.
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    app_name: str = "IT BOM Creation System"
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    
    # Feature Flags - Use dummy data when Azure/SharePoint not available
    use_dummy_cosmos: bool = Field(default=True, alias="USE_DUMMY_COSMOS")
    use_dummy_adls: bool = Field(default=True, alias="USE_DUMMY_ADLS")
    use_dummy_sharepoint: bool = Field(default=True, alias="USE_DUMMY_SHAREPOINT")
    use_dummy_claude: bool = Field(default=False, alias="USE_DUMMY_CLAUDE")
    use_azure_openai: bool = Field(default=False, alias="USE_AZURE_OPENAI")
    
    # Server
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        alias="ALLOWED_ORIGINS"
    )
    
    # Azure AD (optional when using dummy data)
    azure_tenant_id: str = Field(default="dummy-tenant-id", alias="AZURE_TENANT_ID")
    azure_client_id: str = Field(default="dummy-client-id", alias="AZURE_CLIENT_ID")
    azure_client_secret: str = Field(default="dummy-client-secret", alias="AZURE_CLIENT_SECRET")
    
    # Azure Cosmos DB (optional when using dummy data)
    cosmos_db_endpoint: str = Field(default="https://dummy.documents.azure.com:443/", alias="COSMOS_DB_ENDPOINT")
    cosmos_db_key: str = Field(default="dummy-cosmos-key", alias="COSMOS_DB_KEY")
    cosmos_db_database: str = Field(default="it-bom-db", alias="COSMOS_DB_DATABASE")
    
    # Cosmos DB Containers
    cosmos_container_sessions: str = Field(default="sessions")
    cosmos_container_boms: str = Field(default="boms")
    cosmos_container_patterns: str = Field(default="patterns")
    cosmos_container_templates: str = Field(default="templates")
    cosmos_container_analytics: str = Field(default="analytics")
    cosmos_container_users: str = Field(default="users")
    
    # Azure Data Lake Storage (optional when using dummy data)
    adls_account_name: str = Field(default="dummystorage", alias="ADLS_ACCOUNT_NAME")
    adls_account_key: str = Field(default="dummy-storage-key", alias="ADLS_ACCOUNT_KEY")
    adls_container_raw_boms: str = Field(default="raw-boms", alias="ADLS_CONTAINER_RAW_BOMS")
    adls_container_processed: str = Field(default="processed-boms", alias="ADLS_CONTAINER_PROCESSED")
    adls_container_templates: str = Field(default="templates", alias="ADLS_CONTAINER_TEMPLATES")
    adls_container_exports: str = Field(default="exports", alias="ADLS_CONTAINER_EXPORTS")
    adls_container_chat_history: str = Field(default="chat-history", alias="ADLS_CONTAINER_CHAT_HISTORY")

    # SMTP email notifications (optional — leave blank to log to console only)
    smtp_host:     str = Field(default="", alias="SMTP_HOST")
    smtp_port:     int = Field(default=587, alias="SMTP_PORT")
    smtp_user:     str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from:     str = Field(default="noreply@it-contracting-dashboard.com", alias="SMTP_FROM")
    
    # Azure Key Vault (optional when using dummy data)
    keyvault_url: str = Field(default="https://dummy-keyvault.vault.azure.net/", alias="KEYVAULT_URL")
    
    # Anthropic Claude — primary AI model
    anthropic_api_key: str = Field(default="dummy-api-key", alias="ANTHROPIC_API_KEY")
    claude_model_default: str = Field(default="claude-opus-4-6")
    claude_model_fast: str = Field(default="claude-haiku-4-5")
    claude_model_complex: str = Field(default="claude-opus-4-6")
    claude_max_tokens: int = Field(default=4096)
    claude_temperature: float = Field(default=0.3)

    # Direct OpenAI API (alternative when no Azure/Anthropic credentials)
    openai_api_key: str = Field(default="dummy-openai-key", alias="OPENAI_API_KEY")
    openai_model_default: str = Field(default="gpt-4o", alias="OPENAI_MODEL_DEFAULT")
    
    # Azure OpenAI (alternative to Anthropic Claude)
    azure_openai_endpoint: str = Field(default="https://dummy.openai.azure.com/", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(default="dummy-azure-openai-key", alias="AZURE_OPENAI_API_KEY")
    azure_openai_chat_deployment: str = Field(default="gpt-4", alias="AZURE_OPENAI_CHAT_DEPLOYMENT")
    azure_openai_api_version: str = Field(default="2024-02-15-preview", alias="AZURE_OPENAI_API_VERSION")
    azure_openai_chat_endpoint: str = Field(default="", alias="AZURE_OPENAI_CHAT_ENDPOINT")
    azure_openai_max_tokens: int = Field(default=4096)
    azure_openai_temperature: float = Field(default=0.3)
    
    # SharePoint / Microsoft Graph API (optional when using dummy data)
    sharepoint_site_url: str = Field(default="https://dummy.sharepoint.com/sites/dummy", alias="SHAREPOINT_SITE_URL")
    sharepoint_client_id: str = Field(default="dummy-sp-client-id", alias="SHAREPOINT_CLIENT_ID")
    sharepoint_client_secret: str = Field(default="dummy-sp-client-secret", alias="SHAREPOINT_CLIENT_SECRET")
    sharepoint_tenant_id: str = Field(default="", alias="SHAREPOINT_TENANT_ID")
    sharepoint_drive_path: str = Field(default="BOMs", alias="SHAREPOINT_DRIVE_PATH")

    # Azure Storage connection string (used by delta-state persistence + Blob triggers)
    adls_connection_string: str = Field(
        default="",
        alias="AZURE_STORAGE_CONNECTION_STRING",
    )

    # SharePoint delta polling interval in minutes (0 = disabled)
    sharepoint_poll_interval_minutes: int = Field(
        default=0, alias="SHAREPOINT_POLL_INTERVAL_MINUTES"
    )

    # Azure AI Search (optional — falls back to in-memory mock when not configured)
    azure_search_endpoint: str = Field(default="", alias="AZURE_SEARCH_ENDPOINT")
    azure_search_admin_key: str = Field(default="", alias="AZURE_SEARCH_ADMIN_KEY")

    # Azure OpenAI Embedding model (used by BOM ingest pipeline)
    azure_openai_embedding_deployment: str = Field(
        default="text-embedding-3-large", alias="AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
    )
    use_dummy_search: bool = Field(default=False, alias="USE_DUMMY_SEARCH")
    
    # Email (SendGrid) (optional when using dummy data)
    sendgrid_api_key: str = Field(default="dummy-sendgrid-key", alias="SENDGRID_API_KEY")
    from_email: str = Field(default="noreply@dummy.com", alias="FROM_EMAIL")
    
    # JWT
    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_minutes: int = Field(default=60)
    
    # Rate Limiting
    rate_limit_per_minute: int = Field(default=60)
    
    class Config:
        env_file = _ENV_FILE
        case_sensitive = False
        extra = "ignore"  # ignore unknown env vars (e.g. SHAREPOINT_DRIVE_PATH)


_settings: "Settings | None" = None


def get_settings() -> Settings:
    """Get application settings (lazy-init singleton)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
