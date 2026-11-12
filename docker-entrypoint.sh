#!/bin/bash
set -euo pipefail

# First-run config lives next to the application. The shipped template is the
# file the app documents and merges into a user's config.
CONFIG_TEMPLATE="${CONFIG_TEMPLATE:-/app/config.template.yaml}"
CONFIG_FILE="${CONFIG_FILE:-/app/local/config/config.yaml}"

ensure_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "No config found, copying template configuration..."
        mkdir -p "$(dirname "$CONFIG_FILE")"
        cp "$CONFIG_TEMPLATE" "$CONFIG_FILE"
        echo "Config created at $CONFIG_FILE"
        echo "Please edit this file with your actual configuration values."
    fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    ensure_config
    exec "$@"
fi
