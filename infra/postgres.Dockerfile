# Rebuild the upstream privilege-drop helper with a patched, baseline Go runtime.
FROM golang@sha256:0fd028db9bdd4f01657bc8047c209b04d8ce19b853d776bd6f1e76a41729b936 AS gosu
ENV CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOAMD64=v1 GOTOOLCHAIN=local
WORKDIR /src
RUN wget -O /tmp/gosu.tar.gz https://codeload.github.com/tianon/gosu/tar.gz/refs/tags/1.19 \
    && echo 'cd9719b775dbfedae53923c9b0dc792b66d42c51e0b36652ed6f747fbadc0164  /tmp/gosu.tar.gz' | sha256sum -c - \
    && tar -xzf /tmp/gosu.tar.gz --strip-components=1
# Keep upstream source, with explicit corrected transitive modules and checksums.
COPY infra/gosu.go.mod go.mod
COPY infra/gosu.go.sum go.sum
RUN go mod download \
    && go mod verify \
    && go test -mod=readonly ./... github.com/moby/sys/user \
    && go build -mod=readonly -trimpath -ldflags='-d -w' -o /out/gosu . \
    && go version -m /out/gosu

FROM postgres@sha256:4717f90960a225c2d1c5dac50508c401230f693ff626e06e84e6db0a68ded508
RUN apk add --no-cache --upgrade zlib=1.4-r0 krb5-libs=1.22.3-r0 libxslt=1.1.43-r4
COPY --from=gosu /out/gosu /usr/local/bin/gosu
COPY infra/start-postgres.sh /usr/local/bin/altvia-postgres-entrypoint.sh
COPY infra/postgres-runtime-marker.sh /docker-entrypoint-initdb.d/00-altvia-runtime.sh
RUN chmod 755 /usr/local/bin/altvia-postgres-entrypoint.sh /docker-entrypoint-initdb.d/00-altvia-runtime.sh
RUN gosu --version && gosu postgres id \
    && gosu postgres sh -ec 'test "$(id -u)" = 70; test "$(id -g)" = 70; test "$HOME" = /var/lib/postgresql' \
    && gosu postgres:postgres id \
    && gosu 70:70 sh -ec 'test "$(id -u)" = 70; test "$(id -g)" = 70' \
    && gosu postgres:0 sh -ec 'test "$(id -u)" = 70; test "$(id -g)" = 0' \
    && ! gosu altvia-unknown-user true
ENTRYPOINT ["/usr/local/bin/altvia-postgres-entrypoint.sh"]
CMD ["postgres"]
