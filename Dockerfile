# REF: based on https://github.com/astral-sh/uv-docker-example/blob/main/Dockerfile
# and the old_examples/Dockerfile pattern

FROM python:3.12-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first for caching
COPY pyproject.toml /app/pyproject.toml
COPY uv.lock /app/uv.lock

# Install dependencies
RUN uv sync --frozen

# Create symlinks for ray and python to make them accessible system-wide
# This ensures KubeRay operator can find them
RUN ln -s /app/.venv/bin/ray /usr/local/bin/ray && \
    ln -s /app/.venv/bin/python /usr/local/bin/python3.12-venv

# Copy application code
COPY jobs/ /app/jobs/
COPY scripts/ /app/scripts/

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Set Ray-specific environment variables
ENV RAY_DEDUP_LOGS="0"
ENV PYTHONUNBUFFERED="1"

# Create directory for secrets (will be mounted at runtime)
RUN mkdir -p /root/.cloudvolume/secrets

# Default command: Start Ray head node
# This will be overridden in KubeRay configuration
CMD ["ray", "start", "--head", "--port=6379", "--dashboard-host=0.0.0.0", "--block"]
