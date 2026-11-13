import { strict as assert } from "node:assert";
import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { createServer } from "node:https";
import { once } from "node:events";
import test from "node:test";
import { browserGet, boundedFailure } from "./packaged_file_browser_support.mjs";

const require = createRequire(new URL("../apps/web/package.json", import.meta.url));
const { chromium } = require("@playwright/test");

test("actual mapped-host pinned Chromium transport succeeds while APIRequestContext refuses", async () => {
  const certificate = await require("selfsigned").generate([{ name: "commonName", value: "workspace.altvia.test" }], {
    keySize: 2048, algorithm: "sha256", extensions: [{ name: "subjectAltName", altNames: [{ type: 2, value: "workspace.altvia.test" }] }],
  });
  const { X509Certificate } = await import("node:crypto");
  const cert = new X509Certificate(certificate.cert);
  const pin = createHash("sha256").update(cert.publicKey.export({ type: "spki", format: "der" })).digest("base64");
  // Real HTTPS transport probe only: no fake attachment/scanner/application route.
  const server = createServer({ key: certificate.private, cert: certificate.cert }, (request, response) => {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ reachable: true, cookie_bound: request.headers.cookie === "__Host-altvia_session=synthetic-private-session" }));
  });
  server.listen(0, "127.0.0.1"); await once(server, "listening");
  let browser;
  try {
    const origin = `https://workspace.altvia.test:${server.address().port}`;
    browser = await chromium.launch({ args: [`--ignore-certificate-errors-spki-list=${pin}`, "--host-resolver-rules=MAP workspace.altvia.test 127.0.0.1"] });
    const context = await browser.newContext({ baseURL: origin, ignoreHTTPSErrors: false });
    await context.addCookies([{ name: "__Host-altvia_session", value: "synthetic-private-session", url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
    const page = await context.newPage();
    assert.equal((await page.goto("/")).status(), 200);
    let nodeRejected = false;
    try { await page.request.get("/transport-probe", { timeout: 3000 }); } catch { nodeRejected = true; }
    assert.equal(nodeRejected, true);
    const browserResult = await browserGet(page, "/transport-probe");
    assert.equal(browserResult.status, 200); assert.equal(browserResult.body.reachable, true);
    assert.equal(browserResult.body.cookie_bound, true);
    await context.close();
  } finally { await browser?.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});

test("failure projection drops arbitrary error, state and response disclosure", () => {
  const secret = "private-note-file-name-hash-key-cookie-credential-url";
  const safe = boundedFailure({ phase: secret, file_slot: secret, http_status: secret, scan_state: secret, page_errors: secret, extra: secret }, { name: secret, message: secret, stack: secret });
  assert.equal(JSON.stringify(safe).includes(secret), false);
  assert.deepEqual(safe, { schema: 1, phase: "unknown", file_slot: 0, http_status: 0, scan_state: "invalid", page_errors: 0, error_kind: "browser" });
});
