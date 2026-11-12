#!/bin/sh
set -eu
umask 077
# Signature validation, temporary replacement and testing belong to freshclam.
# clamd's bounded SelfCheck reloads the read-only definitions; updater has no socket.
exec freshclam --config-file=/etc/clamav/freshclam.conf "$@"
