#!/bin/sh
set -eu

# A libc change can invalidate collation-dependent indexes. Never adopt a legacy
# cluster by merely switching its image; require logical restore into a new volume.
command="${1:-}"
if [ "$command" = postgres ] || [ "${command#-}" != "$command" ]; then
    if [ -s "$PGDATA/PG_VERSION" ] &&
       [ "$(cat "$PGDATA/.altvia-runtime-family" 2>/dev/null || true)" != alpine3.24-pg17 ]; then
        echo 'Refusing unmarked PostgreSQL data; restore logically into a fresh volume (ADR-0013).' >&2
        exit 1
    fi
fi
exec /usr/local/bin/docker-entrypoint.sh "$@"
