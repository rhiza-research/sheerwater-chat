FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install dependencies
RUN uv sync --frozen --no-dev

# Run the app
CMD ["uv", "run", "sheerwater-chat"]
