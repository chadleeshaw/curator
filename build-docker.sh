#!/bin/bash
# Optimized Docker build script with BuildKit caching

set -e

echo "🚀 Building Docker image with optimized caching..."

# Use BuildKit with maximum caching
export DOCKER_BUILDKIT=1

# Build with cache
docker build \
  --build-arg BUILDKIT_INLINE_CACHE=1 \
  --cache-from curator:latest \
  -t curator:latest \
  .
