#!/bin/bash
set -e

# Copy sample config if config doesn't exist (first run or empty volume)
if [ ! -f /app/local/config/config.yaml ]; then
    echo "No config found, copying sample configuration..."
    cp /app/config.sample.yaml /app/local/config/config.yaml
    echo "Config created at /app/local/config/config.yaml"
    echo "Please edit this file with your actual configuration values."
fi

# Execute the main command
exec "$@"
