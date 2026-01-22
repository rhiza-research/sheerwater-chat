# Sheerwater Chat

Web chat interface for testing sheerwater-mcp.

## Setup

```bash
uv sync --dev
pre-commit install
```

## Configuration

Set the following environment variables:

- `KEYCLOAK_URL` - Keycloak server URL
- `KEYCLOAK_REALM` - Keycloak realm name
- `KEYCLOAK_CLIENT_ID` - OAuth client ID
- `KEYCLOAK_CLIENT_SECRET` - OAuth client secret
- `MCP_SERVER_URL` - URL of sheerwater-mcp server (default: http://localhost:8000)
- `ANTHROPIC_API_KEY` - Anthropic API key
- `SECRET_KEY` - Session secret key
- `DATABASE_URL` - Database URL (default: sqlite:///./sheerwater_chat.db, or postgresql://user:pass@host/db)
- `BASE_URL` - Application base URL (default: http://localhost:8080)

## Running

Start the sheerwater-mcp server:
```bash
cd ../sheerwater-mcp
uv run sheerwater-mcp --transport sse --port 8000
```

Start the chat server:
```bash
uv run sheerwater-chat
```
