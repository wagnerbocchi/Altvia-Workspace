#!/bin/sh
set -eu

# Use the container engine's DNS, including after an API container is recreated.
resolvers=$(awk '$1 == "nameserver" { printf "%s ", $2 }' /etc/resolv.conf)
[ -n "$resolvers" ] || { echo 'No container DNS resolver configured' >&2; exit 1; }
sed "s/@RESOLVERS@/$resolvers/" /etc/nginx/altvia.conf.template > /tmp/nginx.conf
exec nginx -c /tmp/nginx.conf -g 'daemon off;'
