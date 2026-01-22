"""Keycloak OIDC authentication."""

from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request

from .config import Config


def create_oauth(config: Config) -> OAuth:
    """Create OAuth client configured for Keycloak."""
    oauth = OAuth()

    oauth.register(
        name="keycloak",
        client_id=config.keycloak_client_id,
        client_secret=config.keycloak_client_secret,
        server_metadata_url=(f"{config.keycloak_url}/realms/{config.keycloak_realm}/.well-known/openid-configuration"),
        client_kwargs={"scope": "openid email profile"},
    )

    return oauth


def get_user_from_session(request: Request) -> dict | None:
    """Get user info from session."""
    return request.session.get("user")


def get_user_id(request: Request) -> str | None:
    """Get user ID from session."""
    user = get_user_from_session(request)
    if user:
        return user.get("sub")
    return None


def get_user_email(request: Request) -> str | None:
    """Get user email from session."""
    user = get_user_from_session(request)
    if user:
        return user.get("email")
    return None


def get_user_name(request: Request) -> str | None:
    """Get user display name from session."""
    user = get_user_from_session(request)
    if user:
        return user.get("name") or user.get("preferred_username") or user.get("email")
    return None
