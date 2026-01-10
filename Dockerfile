FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p \
    /app/local/config \
    /app/local/data \
    /app/local/downloads \
    /app/local/cache \
    /app/local/logs

# Make entrypoint script executable
RUN chmod +x /app/docker-entrypoint.sh

# Environment variables with defaults
ENV CURATOR_CONFIG_PATH=/app/local/config/config.yaml \
    CURATOR_DB_PATH=/app/local/config/periodicals.db \
    CURATOR_DOWNLOAD_DIR=/app/local/downloads \
    CURATOR_ORGANIZE_DIR=/app/local/data \
    CURATOR_CACHE_DIR=/app/local/cache \
    CURATOR_LOG_FILE=/app/local/logs/periodical_manager.log \
    CURATOR_LOG_LEVEL=INFO \
    CURATOR_PORT=8000 \
    CURATOR_HOST=0.0.0.0

# Volumes for persistent data
VOLUME ["/app/local/config", "/app/local/data", "/app/local/downloads", "/app/local/cache", "/app/local/logs"]

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/health')" || exit 1

# Set entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Run the application
CMD ["python", "main.py"]
