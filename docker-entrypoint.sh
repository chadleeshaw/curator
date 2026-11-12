#!/bin/bash
set -euo pipefail

# The image starts as root so it can fix ownership of mounted volumes, then
# drops to PUID:PGID. UID or GID 0 is refused.
: "${PUID:=1000}"
: "${PGID:=1000}"

# First-run config lives next to the application. The shipped template is the
# file the app documents and merges into a user's config.
CONFIG_TEMPLATE="${CONFIG_TEMPLATE:-/app/config.template.yaml}"
CONFIG_FILE="${CONFIG_FILE:-/app/local/config/config.yaml}"

# Writable volume directories only. The application tree stays owned by root.
DATA_DIRS="${DATA_DIRS:-/app/local/config /app/local/data /app/local/downloads /app/local/cache /app/local/logs}"

refuse_root_ids() {
    if [ "$PUID" = "0" ] || [ "$PGID" = "0" ]; then
        echo "Refusing to run as root. Set PUID and PGID to a non-root user." >&2
        exit 1
    fi
}

ensure_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "No config found, copying template configuration..."
        mkdir -p "$(dirname "$CONFIG_FILE")"
        cp "$CONFIG_TEMPLATE" "$CONFIG_FILE"
        echo "Config created at $CONFIG_FILE"
        echo "Please edit this file with your actual configuration values."
    fi
}

prepare_runtime_user() {
    if ! getent group "$PGID" >/dev/null 2>&1; then
        groupadd --non-unique --gid "$PGID" "curatorg${PGID}"
    fi
    if ! getent passwd "$PUID" >/dev/null 2>&1; then
        useradd --non-unique --uid "$PUID" --gid "$PGID" \
            --no-create-home --shell /usr/sbin/nologin "curatoru${PUID}"
    fi
    for dir in $DATA_DIRS; do
        if [ -d "$dir" ]; then
            chown -R "$PUID:$PGID" "$dir"
        fi
    done
}

drop_privileges() {
    export HOME=/tmp
    exec setpriv --reuid "$PUID" --regid "$PGID" --clear-groups -- "$@"
}

main() {
    refuse_root_ids
    ensure_config
    prepare_runtime_user
    drop_privileges "$@"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
