import type { NextConfig } from "next";
import { resolve } from "node:path";

const config: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: resolve(import.meta.dirname, "../.."),
  poweredByHeader: false,
  // Prebuilt Sharp/libvips on Linux x64 requires SSE4.2. Excluded at install.
  images: { unoptimized: true },
  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    ] }];
  },
};
export default config;
