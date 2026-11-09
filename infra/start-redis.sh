#!/bin/sh
set -eu
umask 077
password=$(cat /run/secrets/redis_password)
case "$password" in
    ''|*[!A-Za-z0-9_-]*)
        printf '%s\n' 'Redis secret must be a generated URL-safe value.' >&2
        exit 1
        ;;
esac
if test "${#password}" -lt 32 || test "${#password}" -gt 128; then
    printf '%s\n' 'Redis secret length invalid.' >&2
    exit 1
fi
config=$(mktemp /tmp/altvia-redis.XXXXXX)
trap 'rm -f "$config"' EXIT HUP INT TERM
printf '%s\n' 'bind 0.0.0.0' 'port 6379' 'protected-mode yes' 'save ""' \
    'appendonly no' 'maxmemory 64mb' 'maxmemory-policy noeviction' \
    'daemonize no' 'logfile ""' 'loglevel warning' 'dir /tmp' \
    'rename-command CONFIG ""' 'rename-command ACL ""' 'rename-command MODULE ""' \
    'rename-command FLUSHALL ""' 'rename-command FLUSHDB ""' > "$config"
printf 'requirepass %s\n' "$password" >> "$config"
unset password
exec redis-server "$config"
