# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install minimal OS dependencies needed for building extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for optimal Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code and data assets
COPY backend/ ./backend/
COPY config/ ./config/
COPY rag/ ./rag/
COPY scraper/ ./scraper/
COPY data/ ./data/

# Expose default port
EXPOSE 8000

# Launch uvicorn listening on 0.0.0.0 and dynamically binding to Railway's $PORT
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
