import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests", fullyParallel: false, workers: 1, retries: 0,
  testIgnore: process.env.ALTVIA_REDESIGN_CAPTURE === "1" ? [] : ["**/workspace-captures.spec.ts"],
  reporter: "list", timeout: 30_000,
  use: { baseURL: "https://127.0.0.1:3443", ignoreHTTPSErrors: true,
    trace: "off", screenshot: "off", video: "off" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
