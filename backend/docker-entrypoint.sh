#!/bin/sh
set -e

# Runs as root, fixes volume-mount ownership for the unprivileged app user,
# then drops privileges and exec's the real command (uvicorn).
#
# The appdata volume is usually mounted from the host with root ownership.
# Without this step the app (running as a non-root user) cannot write the
# SQLite DB, templates, exports or logs and fails at startup.

APP_UID="${APP_UID:-10001}"
APP_GID="${APP_GID:-10001}"
DATA_DIR="${APPDATA_DIR:-/appdata/dumbbureau}"

mkdir -p "$DATA_DIR"

# Scoped chown so a large exports/ tree is not walked more than necessary.
for dir in templates exports logs; do
    mkdir -p "$DATA_DIR/$dir"
    chown -R "$APP_UID:$APP_GID" "$DATA_DIR/$dir"
done
chown "$APP_UID:$APP_GID" "$DATA_DIR"

# The database and its WAL sidecar files may have been created by a previous
# root-run image; hand them over if present.
for f in "$DATA_DIR/db.sqlite" "$DATA_DIR/db.sqlite-wal" "$DATA_DIR/db.sqlite-shm"; do
    if [ -e "$f" ]; then
        chown "$APP_UID:$APP_GID" "$f"
    fi
done

exec gosu "$APP_UID:$APP_GID" "$@"
