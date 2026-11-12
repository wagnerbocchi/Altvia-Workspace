#!/bin/sh
set -eu
umask 077
# Complete signed vendor files are required. CLD is a signed verified update
# container; sigtool verifies its embedded metadata/signature as well as CVD.
for database in main daily bytecode; do
    if test -f "/var/lib/clamav/$database.cvd"; then
        sigtool --info "/var/lib/clamav/$database.cvd" >/dev/null
    else
        test -f "/var/lib/clamav/$database.cld"
        sigtool --info "/var/lib/clamav/$database.cld" >/dev/null
    fi
done
exec clamd --config-file=/etc/clamav/clamd.conf
