# Optimized multi-stage build with BuildKit cache mounts
# Works for both local builds and GitHub Actions

# Stage 1: Builder
FROM python:3.13-slim AS builder

# Install build dependencies
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements-prod.txt /tmp/requirements.txt

# Install Python packages with pip cache
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user -r /tmp/requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# Install runtime dependencies including Tesseract OCR and unrar (without cache mount to avoid lock issues)
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-fra \
    tesseract-ocr-deu \
    tesseract-ocr-spa \
    tesseract-ocr-ita \
    tesseract-ocr-por \
    tesseract-ocr-rus \
    tesseract-ocr-nld \
    tesseract-ocr-pol \
    tesseract-ocr-ukr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-jpn \
    tesseract-ocr-kor \
    unrar \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Set environment variables
ENV HOME=/root

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p \
    /app/local/config \
    /app/local/data \
    /app/local/downloads \
    /app/local/cache \
    /app/local/logs

# Make entrypoint executable
RUN chmod +x /app/docker-entrypoint.sh

# Environment variables
ENV CURATOR_CONFIG_PATH=/app/local/config/config.yaml \
    CURATOR_DB_PATH=/app/local/config/periodicals.db \
    CURATOR_DOWNLOAD_DIR=/app/local/downloads \
    CURATOR_ORGANIZE_DIR=/app/local/data \
    CURATOR_CACHE_DIR=/app/local/cache \
    CURATOR_LOG_FILE=/app/local/logs/periodical_manager.log \
    CURATOR_LOG_LEVEL=INFO \
    CURATOR_PORT=8000 \
    CURATOR_HOST=0.0.0.0

# Volumes
VOLUME ["/app/local/config", "/app/local/data", "/app/local/downloads", "/app/local/cache", "/app/local/logs"]

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/health')" || exit 1

# Entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "main.py"]
