FROM python:3.12-slim

# Bring in the uv binary from Astral's published image (pinned for reproducibility).
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /bin/

WORKDIR /app

# Container-friendly uv settings: precompile bytecode for faster cold starts and
# copy (rather than hardlink) packages into the venv so it works across layers.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies as their own cached layer, using only the manifest + lock.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY scripts ./scripts

# Run everything out of the project virtualenv uv created.
ENV PATH="/app/.venv/bin:$PATH"

ENV DATA_DIR=/app/data
VOLUME ["/app/data"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
