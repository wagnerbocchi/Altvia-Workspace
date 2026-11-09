FROM node@sha256:ec318aabf188af4e5488847eea4b24452650b9917140563e140762526a37f1df AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /opt/altvia
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN corepack enable && pnpm install --frozen-lockfile
COPY apps/web/ apps/web/
COPY scripts/check_web_native.mjs scripts/check_web_native.mjs
RUN node scripts/check_web_native.mjs && pnpm web:build

# Signed distro Node uses maintained shared native libraries, with no npm/yarn.
FROM alpine@sha256:0f49f331d9212aff11b932863be4eb01cdf962969aa86dab7d1ee21ac6f5f52b
RUN apk add --no-cache nodejs=24.22.1-r1 zlib=1.4-r0 brotli-libs=1.2.1-r0 icu-data-full=78.1-r0 \
    && addgroup -g 10001 altvia && adduser -D -H -u 10001 -G altvia altvia
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /opt/altvia
COPY --from=build --chown=10001:10001 /opt/altvia/apps/web/.next/standalone ./
COPY --from=build --chown=10001:10001 /opt/altvia/apps/web/.next/static ./apps/web/.next/static
COPY scripts/check_web_native.mjs scripts/check_web_runtime.mjs ./scripts/
USER 10001:10001
RUN node scripts/check_web_runtime.mjs
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/',{signal:AbortSignal.timeout(3000)}).then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]
CMD ["node", "apps/web/server.js"]
