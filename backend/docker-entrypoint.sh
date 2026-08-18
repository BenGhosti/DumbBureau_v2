#!/bin/sh
# Runs once as root before the app starts, purely to make sure the
# bind-mounted APPDATA_DIR is writable by the unprivileged app user (a
# fresh bind mount is typically root:root on the host, regardless of what
# USER the image declares). Then drops privileges permanently via gosu -
# the actual uvicorn process never runs as root.
set -e

APPDATA_DIR="${APPDATA_DIR:-/appdata/dumbbureau}"

mkdir -p "$APPDATA_DIR"
chown -R dumbbureau:dumbbureau "$APPDATA_DIR"

exec gosu dumbbureau "$@"
