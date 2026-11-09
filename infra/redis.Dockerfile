# Exact supported Redis source; compile the mandatory binary for the guest baseline.
FROM alpine@sha256:644c1ad8fc45cc581ab1b5ea7ec1bebc9b037fd4801ad697ca124deb3f9c9332 AS build
RUN apk add --no-cache build-base linux-headers
WORKDIR /src
RUN wget -O /tmp/redis.tar.gz https://codeload.github.com/redis/redis/tar.gz/refs/tags/7.4.12 \
    && echo '324ab63d55c607639b419f547b213c62ae39ff50e09870e450a11c272567b84f  /tmp/redis.tar.gz' | sha256sum -c - \
    && tar -xzf /tmp/redis.tar.gz --strip-components=1 \
    && make -C src -j2 MALLOC=libc OPTIMIZATION='-O2 -march=x86-64 -mtune=generic' redis-server redis-cli

FROM alpine@sha256:644c1ad8fc45cc581ab1b5ea7ec1bebc9b037fd4801ad697ca124deb3f9c9332
RUN addgroup -g 10001 altvia && adduser -D -H -u 10001 -G altvia altvia
COPY --from=build /src/src/redis-server /src/src/redis-cli /usr/local/bin/
COPY infra/redis-health.sh infra/start-redis.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/redis-health.sh /usr/local/bin/start-redis.sh
USER 10001:10001
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=10 \
    CMD ["/bin/sh", "/usr/local/bin/redis-health.sh"]
CMD ["/bin/sh", "/usr/local/bin/start-redis.sh"]
