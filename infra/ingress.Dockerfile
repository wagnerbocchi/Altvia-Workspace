FROM nginxinc/nginx-unprivileged@sha256:e2a8fca8aa356d66159aaf8a877a9c126773635adf210503eefaaeaffeed6ad7
USER root
# Signed Alpine vendor fixes; exact versions fail closed if no longer available.
RUN apk add --no-cache --upgrade \
    brotli-libs=1.2.1-r0 curl=8.23.0-r0 libcurl=8.23.0-r0 \
    libexpat=2.10.0-r0 musl=1.2.6-r3 musl-utils=1.2.6-r3 zlib=1.4-r0
USER 101:101
