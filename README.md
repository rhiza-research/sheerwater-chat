# Sheerwater Chat

Web chat interface for the [Sheerwater](https://github.com/rhiza-research/sheerwater) weather forecast benchmarking platform. Connects to [sheerwater-mcp](https://github.com/rhiza-research/sheerwater-mcp) to give LLMs access to forecast evaluation tools.

## Architecture

```
User ──▶ Ingress (nginx) ──▶ sheerwater-chat ──▶ sheerwater-mcp (via Tailscale)
              │                     │                      │
              │                     ▼                      ▼
              │                 Anthropic API         Sheerwater / Nuthatch
              │                     │                   (GCS buckets)
              ▼                     ▼
          Keycloak (OIDC)      SQLite (PVC)
```

- **Authentication**: Keycloak OIDC (confidential client with PKCE)
- **LLM**: Anthropic Claude API, proxied through this server
- **MCP**: Connects to sheerwater-mcp over SSE for tool use
- **Storage**: SQLite on a PersistentVolumeClaim for chat history

## Local Development

### Docker Compose (recommended)

Starts the full stack: Keycloak, sheerwater-mcp, and sheerwater-chat.

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY=sk-...

docker compose up
```

Then open http://localhost:8080. Keycloak admin is at http://localhost:8180 (admin/admin).

The compose file mounts `src/` for live reloading and uses a pre-configured Keycloak realm (`keycloak/realm.json`).

### Without Docker

```bash
uv sync --dev
pre-commit install
```

Start the sheerwater-mcp server:
```bash
cd ../sheerwater-mcp
uv run sheerwater-mcp --transport sse --port 8000
```

Start the chat server:
```bash
uv run sheerwater-chat
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `KEYCLOAK_URL` | Keycloak server URL (internal) | — |
| `KEYCLOAK_PUBLIC_URL` | Keycloak URL for browser redirects | — |
| `KEYCLOAK_REALM` | Keycloak realm name | — |
| `KEYCLOAK_CLIENT_ID` | OAuth client ID | — |
| `KEYCLOAK_CLIENT_SECRET` | OAuth client secret | — |
| `MCP_SERVER_URL` | URL of sheerwater-mcp server | `http://localhost:8000` |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `SECRET_KEY` | Session signing secret | — |
| `DATABASE_URL` | SQLite or PostgreSQL URL | `sqlite:///./sheerwater_chat.db` |
| `BASE_URL` | Application base URL | `http://localhost:8080` |

## Deployment

Deployed to the rhiza GKE cluster via ArgoCD.

- **Namespace**: `sheerwater-chat` (owned by Terraform — secrets must exist before the app deploys)
- **Helm chart**: [`chart/`](chart/)
- **Container image**: `ghcr.io/rhiza-research/sheerwater-chat` (built by GitHub Actions on push to `main`)
- **Secrets**: Terraform creates a K8s secret (`sheerwater-chat-secrets`) containing `KEYCLOAK_CLIENT_SECRET`, `ANTHROPIC_API_KEY`, and `SECRET_KEY`
- **Ingress**: Public via nginx ingress with TLS

### Infrastructure (in the [infrastructure](https://github.com/rhiza-research/infrastructure) repo)

- `terraform/20-gke-cluster/sheerwater-chat.tf` — namespace, secrets, ArgoCD Application
- `terraform/20-gke-cluster/dns-sheerwater.tf` — DNS record
- `terraform/modules/keycloak/main.tf` — Keycloak OIDC client registration
