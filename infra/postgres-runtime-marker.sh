#!/bin/sh
set -eu

# The official entrypoint runs this only after fresh initdb. Creating this marker
# before initdb would make PGDATA nonempty and prevent safe initialization.
printf '%s\n' alpine3.24-pg17 > "$PGDATA/.altvia-runtime-family"
