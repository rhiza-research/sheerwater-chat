"""Configuration for sheerwater-chat."""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # Keycloak OIDC settings
    keycloak_url: str
    keycloak_realm: str
    keycloak_client_id: str
    keycloak_client_secret: str

    # MCP server settings
    mcp_server_url: str

    # Anthropic API
    anthropic_api_key: str

    # App settings
    secret_key: str
    database_path: str
    base_url: str

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            keycloak_url=os.environ["KEYCLOAK_URL"],
            keycloak_realm=os.environ["KEYCLOAK_REALM"],
            keycloak_client_id=os.environ["KEYCLOAK_CLIENT_ID"],
            keycloak_client_secret=os.environ["KEYCLOAK_CLIENT_SECRET"],
            mcp_server_url=os.environ.get("MCP_SERVER_URL", "http://localhost:8000"),
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            secret_key=os.environ["SECRET_KEY"],
            database_path=os.environ.get("DATABASE_PATH", "sheerwater_chat.db"),
            base_url=os.environ.get("BASE_URL", "http://localhost:8080"),
        )
