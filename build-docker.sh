#!/bin/bash
# Fast Docker build script with BuildKit

export DOCKER_BUILDKIT=1
docker build --build-arg BUILDKIT_INLINE_CACHE=1 -t curator:latest .
