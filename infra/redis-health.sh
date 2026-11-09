#!/bin/sh
set -eu
# Keep the secret in this short-lived process environment, never command arguments.
REDISCLI_AUTH=$(cat /run/secrets/redis_password)
export REDISCLI_AUTH
reply=$(redis-cli --no-auth-warning -h 127.0.0.1 ping)
test "$reply" = PONG
