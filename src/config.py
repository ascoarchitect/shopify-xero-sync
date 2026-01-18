"""Configuration management for Shopify-Xero Sync System.

Uses pydantic-settings to load configuration from environment variables
with validation and type coercion.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Shopify Configuration
    shopify_shop_url: str = Field(
        ...,
        description="Shopify store URL (e.g., https://your-store.myshopify.com)"
    )
    shopify_client_id: str = Field(
        ...,
        description="Shopify app client ID (from Dev Dashboard)"
    )
    shopify_client_secret: str = Field(
        ...,
        description="Shopify app client secret (from Dev Dashboard)"
    )
    shopify_access_token: Optional[str] = Field(
        default=None,
        description="Shopify access token (obtained via OAuth, managed automatically)"
    )
    shopify_api_type: str = Field(
        default="graphql",
        description="API type to use: 'rest' or 'graphql' (graphql is faster for bulk operations)"
    )

    # Xero Configuration
    xero_client_id: str = Field(
        ...,
        description="Xero OAuth2 client ID"
    )
    xero_client_secret: str = Field(
        ...,
        description="Xero OAuth2 client secret"
    )
    xero_tenant_id: str = Field(
        ...,
        description="Xero tenant (organization) ID"
    )
    xero_access_token: Optional[str] = Field(
        default=None,
        description="Xero OAuth2 access token (managed automatically)"
    )
    xero_refresh_token: Optional[str] = Field(
        default=None,
        description="Xero OAuth2 refresh token (managed automatically)"
    )

    # Application Settings
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    dry_run: bool = Field(
        default=False,
        description="If true, don't actually update Xero"
    )
    enable_email_marketing: bool = Field(
        default=False,
        description="If true, set all customers to accept email marketing in Shopify"
    )
    database_path: Path = Field(
        default=Path("data/sync.db"),
        description="SQLite database file path"
    )
    log_file: Path = Field(
        default=Path("logs/sync.log"),
        description="Log file path"
    )

    # Performance Tuning
    max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts for failed API calls"
    )
    retry_delay: float = Field(
        default=2.0,
        ge=0.1,
        le=60.0,
        description="Initial delay between retries (seconds)"
    )
    rate_limit_buffer: int = Field(
        default=5,
        ge=0,
        le=20,
        description="Stay this many calls under the rate limit"
    )
    shopify_rate_limit_delay: float = Field(
        default=0.5,
        ge=0.1,
        le=5.0,
        description="Delay between Shopify API calls (seconds)"
    )
    xero_rate_limit_delay: float = Field(
        default=1.0,
        ge=0.1,
        le=5.0,
        description="Delay between Xero API calls (seconds)"
    )

    @field_validator("shopify_shop_url")
    @classmethod
    def validate_shop_url(cls, v: str) -> str:
        """Ensure shop URL is properly formatted."""
        v = v.rstrip("/")
        if not v.startswith("https://"):
            v = f"https://{v}"
        if not v.endswith(".myshopify.com"):
            raise ValueError("Shop URL must end with .myshopify.com")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        v = v.upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v

    @model_validator(mode="after")
    def validate_shopify_auth(self) -> "Settings":
        """Ensure Shopify has either access token or will need OAuth."""
        if not self.shopify_access_token:
            # Access token will be obtained via OAuth flow
            pass
        return self

    @property
    def shopify_api_url(self) -> str:
        """Get the Shopify Admin API base URL."""
        return f"{self.shopify_shop_url}/admin/api/2024-01"

    @property
    def xero_api_url(self) -> str:
        """Get the Xero API base URL."""
        return "https://api.xero.com/api.xro/2.0"

    @property
    def xero_identity_url(self) -> str:
        """Get the Xero identity API URL for OAuth."""
        return "https://identity.xero.com"


def get_settings() -> Settings:
    """Get application settings singleton.

    Returns:
        Settings: Application settings loaded from environment
    """
    return Settings()
