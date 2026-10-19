# syntax=docker/dockerfile:1

# =============================================================================
# Stage 1: Builder (compiles dependencies in isolated environment)
# =============================================================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Build isolated virtual environment
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# =============================================================================
# Stage 2: Production Runner (minimal attack surface, non-root execution)
# =============================================================================
FROM python:3.11-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Only install curl for health checks (compilers are excluded from runtime image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Security best practice: run as non-root system user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Copy application code with non-root ownership
COPY --chown=appuser:appgroup backend/ ./backend/
COPY --chown=appuser:appgroup config/ ./config/
COPY --chown=appuser:appgroup rag/ ./rag/
COPY --chown=appuser:appgroup scraper/ ./scraper/
# data/ is excluded from Docker build context (.dockerignore)
# Mount a Railway Volume at /app/data and re-run the ingest script to populate it.
COPY --chown=appuser:appgroup main.py .

# Switch to non-root user
USER appuser

# Expose default port
EXPOSE 8000

# Docker container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/ || exit 1

# Launch uvicorn with exec to guarantee proper POSIX signal propagation
# Also ensure data subdirectories exist (populated via Railway Volume + ingest script)
CMD ["sh", "-c", "mkdir -p /app/data/raw /app/data/processed /app/data/chroma_db && exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
