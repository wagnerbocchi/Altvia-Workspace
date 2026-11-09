#!/bin/sh
set -eu
test "${ALTVIA_ALLOW_TEST_DB:-}" = 1
: "${ALTVIA_CI_REDIS_PASSWORD:?Synthetic CI Redis password required}"
REDIS_TEST_PASSWORD=$ALTVIA_CI_REDIS_PASSWORD
export REDIS_TEST_PASSWORD
# shellcheck disable=SC2016 # Expansion belongs to the disposable container, not the runner shell.
docker run -d --name altvia-ci-redis --read-only --tmpfs /tmp \
    -p 127.0.0.1:6379:6379 -e REDIS_TEST_PASSWORD \
    --health-cmd='REDISCLI_AUTH="$REDIS_TEST_PASSWORD" redis-cli --no-auth-warning ping | grep -qx PONG' \
    --health-interval=1s --health-timeout=3s --health-retries=20 \
    docker.io/library/redis@sha256:e4ee3e03ce8f75471f40937a7c6b2b0e500390b6812fcdf5cb32c01295ded446 \
    sh -ec 'umask 077
printf "bind 0.0.0.0\nport 6379\nprotected-mode yes\nrequirepass %s\nsave \"\"\n" "$REDIS_TEST_PASSWORD" > /tmp/test-redis.conf
unset REDIS_TEST_PASSWORD
exec redis-server /tmp/test-redis.conf'
attempt=0
while test "$attempt" -lt 30; do
    state=$(docker inspect --format '{{.State.Health.Status}}' altvia-ci-redis)
    if test "$state" = healthy; then
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
done
printf '%s\n' 'Isolated test Redis did not become healthy.' >&2
exit 1
