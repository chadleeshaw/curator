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

# Install runtime dependencies (without cache mount to avoid lock issues)
# PaddleOCR requires OpenCV which needs these graphics/X11 libraries
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    poppler-utils \
    libglib2.0-0 \
    libgomp1 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libfontconfig1 \
    libice6 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Set PaddleOCR environment variables for CPU compatibility
ENV HOME=/root \
    USE_GPU=False \
    DISABLE_MODEL_SOURCE_CHECK=True \
    FLAGS_cpu_deterministic=true

# Note: PaddleOCR models will be downloaded on first use to avoid build-time
# CPU instruction compatibility issues. Models are cached in /root/.paddleocr
# If you want to pre-download models during build (only if your build and runtime
# CPUs are compatible), uncomment the following:
# RUN python3 -c "from paddleocr import PaddleOCR; \
#     ocr = PaddleOCR(use_angle_cls=True, lang='en'); \
#     print('PaddleOCR models downloaded')"

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
    CURATOR_HOST=0.0.0.0 \
    USE_GPU=False \
    DISABLE_MODEL_SOURCE_CHECK=True

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
