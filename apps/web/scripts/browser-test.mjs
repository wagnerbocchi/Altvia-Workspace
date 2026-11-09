// Local test gateway only. This is not a production ingress or TLS configuration.
import { spawn } from "node:child_process";
import { createServer } from "node:https";
import { request } from "node:http";
import { createRequire } from "node:module";
import { createServer as createTcpServer } from "node:net";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import selfsigned from "selfsigned";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const web = resolve(root, "apps/web");
const require = createRequire(new URL("../package.json", import.meta.url));
if (process.env.ALTVIA_ALLOW_TEST_DB !== "1") throw Error("Explicit test DB opt-in required");
if (process.env.ALTVIA_PUBLIC_ORIGIN !== "https://127.0.0.1:3443") throw Error("Test origin required");
const children = [];
const run = (command, args, cwd = root) => {
  const child = spawn(command, args, { cwd, env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" }, stdio: "inherit" });
  children.push(child);
  return child;
};
const result = child => new Promise((done, reject) => {
  child.once("error", reject);
  child.once("exit", code => code === 0 ? done() : reject(Error(`Child exited ${code}`)));
});
const uv = process.platform === "win32" ? "uv.exe" : "uv";
let gateway;
try {
  for (const port of [3000, 8000, 3443]) {
    await new Promise((done, reject) => {
      const probe = createTcpServer();
      probe.once("error", () => reject(Error(`Test port ${port} is already in use`)));
      probe.listen(port, "127.0.0.1", () => probe.close(done));
    });
  }
  await result(run(uv, ["run", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"]));
  await result(run(uv, ["run", "python", "scripts/browser_fixture.py"]));
  process.loadEnvFile(resolve(root, ".env.browser-session"));
  const python = resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  run(python, ["-m", "uvicorn", "altvia.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8000", "--no-proxy-headers", "--no-access-log"]);
  run(process.execPath, [require.resolve("next/dist/bin/next"), "start", "--hostname", "127.0.0.1"], web);
  const certificates = await selfsigned.generate([{ name: "commonName", value: "localhost" }], {
    keySize: 2048, algorithm: "sha256", extensions: [{ name: "subjectAltName", altNames: [
      { type: 7, ip: "127.0.0.1" }, { type: 2, value: "localhost" },
    ] }],
  });
  gateway = createServer({ key: certificates.private, cert: certificates.cert }, (incoming, outgoing) => {
    const upstream = request({ hostname: "127.0.0.1", port: incoming.url.startsWith("/api/v1/") ? 8000 : 3000,
      path: incoming.url, method: incoming.method, headers: incoming.headers }, response => {
      outgoing.writeHead(response.statusCode, response.headers); response.pipe(outgoing);
    });
    upstream.on("error", () => { outgoing.writeHead(502); outgoing.end(); });
    incoming.on("aborted", () => upstream.destroy());
    incoming.pipe(upstream);
  });
  await new Promise(done => gateway.listen(3443, "127.0.0.1", done));
  for (const url of ["http://127.0.0.1:3000", "http://127.0.0.1:8000/api/v1/health/ready"]) {
    let ready = false;
    for (let attempt = 0; attempt < 60; attempt++) {
      try { if ((await fetch(url)).ok) { ready = true; break; } } catch { /* starting */ }
      await delay(500);
    }
    if (!ready) throw Error("Test service did not become ready");
  }
  await result(run(process.execPath, [require.resolve("@playwright/test/cli"), "test"], web));
} finally {
  gateway?.closeAllConnections(); gateway?.close();
  for (const child of children.reverse()) if (child.exitCode === null) {
    if (process.platform === "win32") {
      // Windows venv launchers create a child interpreter; close the whole tree.
      await new Promise(done => {
        const cleanup = spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
        cleanup.once("exit", done); cleanup.once("error", done);
      });
    } else {
      child.kill("SIGTERM");
      await new Promise(done => child.once("exit", done));
    }
  }
}
