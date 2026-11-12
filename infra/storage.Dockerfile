# Immutable upstream source and local patched Go toolchain; no automatic upgrade.
FROM golang@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea AS build
ENV CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOAMD64=v1 GOTOOLCHAIN=local GOMAXPROCS=2
WORKDIR /src
RUN go version | tee /tmp/toolchain.txt \
    && test "$(go env GOVERSION)" = go1.27.4 \
    && wget -O /tmp/versitygw.tar.gz https://codeload.github.com/versity/versitygw/tar.gz/e42ae7ab8107201e64e52ee024824e8cab3683b3 \
    && echo 'c15737f351b857273223e5a9a5fd2073a4f90745901baaf363ef3501964cf556  /tmp/versitygw.tar.gz' | sha256sum -c - \
    && tar -xzf /tmp/versitygw.tar.gz --strip-components=1
# Retain upstream source; narrow verified module correction removes the retired
# openpgp subtree flagged by GO-2026-5932 without changing used crypto APIs.
COPY infra/versitygw.go.mod go.mod
COPY infra/versitygw.go.sum go.sum
RUN go mod download && go mod verify \
    && go build -p=2 -mod=readonly -trimpath -ldflags='-s -w -X main.Version=1.11.0 -X main.Build=e42ae7ab8107201e64e52ee024824e8cab3683b3' -o /out/versitygw ./cmd/versitygw \
    && go version -m /out/versitygw | tee /out/go-build-info.txt \
    && grep -q 'GOAMD64=v1' /out/go-build-info.txt \
    && grep -q 'CGO_ENABLED=0' /out/go-build-info.txt \
    && cp /tmp/toolchain.txt /out/toolchain.txt \
    && sha256sum /out/versitygw > /out/binary.sha256

FROM alpine@sha256:0f49f331d9212aff11b932863be4eb01cdf962969aa86dab7d1ee21ac6f5f52b
RUN apk add --no-cache ca-certificates curl zlib=1.4-r0 \
    && addgroup -g 10001 altvia && adduser -D -H -u 10001 -G altvia altvia \
    && mkdir -p /data/objects /data/iam /usr/share/altvia-storage \
    && chown -R 10001:10001 /data && chmod 700 /data /data/objects /data/iam \
    && apk info -v > /usr/share/altvia-storage/packages.txt
COPY --from=build /out/versitygw /usr/local/bin/versitygw
COPY --from=build /out/*.txt /out/binary.sha256 /usr/share/altvia-storage/
COPY infra/start-storage.sh /usr/local/bin/start-storage.sh
USER 10001:10001
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=20 \
    CMD ["curl", "--fail", "--silent", "--max-time", "2", "--cacert", "/run/secrets/storage_ca", "https://storage:8443/_health"]
ENTRYPOINT ["/bin/sh", "/usr/local/bin/start-storage.sh"]
