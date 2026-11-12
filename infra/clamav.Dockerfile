# Alpine APK verifies vendor signatures; no --allow-untrusted or tiny AV database.
FROM alpine@sha256:0f49f331d9212aff11b932863be4eb01cdf962969aa86dab7d1ee21ac6f5f52b
RUN apk add --no-cache clamav-daemon=1.4.6-r0 freshclam=1.4.6-r0 clamav-clamdscan=1.4.6-r0 clamav-scanner=1.4.6-r0 zlib=1.4-r0 \
    && addgroup -g 10001 altvia && adduser -D -H -u 10001 -G altvia altvia \
    && mkdir -p /var/lib/clamav /run/clamav /usr/share/altvia-clamav \
    && chown 10001:10001 /var/lib/clamav /run/clamav \
    && chmod 700 /var/lib/clamav /run/clamav \
    && clamd --version && freshclam --version \
    && apk info -v > /usr/share/altvia-clamav/packages.txt \
    && apk audit --system > /usr/share/altvia-clamav/package-audit.txt \
    && find /usr/lib -type f -name '*.so*' -exec sha256sum '{}' ';' > /usr/share/altvia-clamav/native.sha256
ENV TZ=UTC
COPY infra/clamd.conf infra/freshclam.conf /etc/clamav/
COPY infra/start-clamd.sh infra/start-freshclam.sh /usr/local/bin/
USER 10001:10001
HEALTHCHECK --interval=10s --timeout=5s --start-period=120s --retries=30 \
    CMD ["clamdscan", "--config-file=/etc/clamav/clamd.conf", "--ping=1"]
ENTRYPOINT ["/bin/sh", "/usr/local/bin/start-clamd.sh"]
