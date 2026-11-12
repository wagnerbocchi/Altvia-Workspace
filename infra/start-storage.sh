#!/bin/sh
set -eu
umask 077
# Only file paths occur in argv. Never enable gateway request/debug logging.
ROOT_ACCESS_KEY_ID=$(cat /run/secrets/storage_root_access)
ROOT_SECRET_ACCESS_KEY=$(cat /run/secrets/storage_root_secret)
test -n "$ROOT_ACCESS_KEY_ID" && test -n "$ROOT_SECRET_ACCESS_KEY"
export ROOT_ACCESS_KEY_ID ROOT_SECRET_ACCESS_KEY
exec versitygw --port :8443 --cert /run/secrets/storage_cert \
    --key /run/secrets/storage_key --admin-path-prefix /_owner \
    --iam-dir /data/iam --list-buckets-scope owned --quiet --log-level silent \
    --max-connections 32 --max-requests 8 --health /_health posix --fsync \
    --object-lock-mode flock --dir-perms 0700 --file-perms 0600 \
    --concurrency 8 /data/objects
