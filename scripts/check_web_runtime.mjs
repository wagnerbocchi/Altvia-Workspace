// Capability guard for the immutable standalone service, never an environment dump.
import "./check_web_native.mjs";
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { strict as assert } from "node:assert";

assert.equal(process.versions.node.split(".")[0], "24");
assert.deepEqual(Intl.DateTimeFormat.supportedLocalesOf(["pt-BR"]), ["pt-BR"]);
assert.ok(existsSync(new URL("../apps/web/server.js", import.meta.url)), "Standalone server missing");
assert.ok(existsSync(new URL("../apps/web/.next/BUILD_ID", import.meta.url)), "Build ID missing");
const appRequire = createRequire(new URL("../apps/web/package.json", import.meta.url));
for (const name of ["@playwright/test", "eslint", "typescript"]) {
  assert.throws(() => appRequire.resolve(name), { code: "MODULE_NOT_FOUND" }, `${name} is a build-only tool`);
}
for (const path of ["/usr/bin/npm", "/usr/local/bin/npm", "/usr/bin/corepack", "/usr/local/bin/corepack",
  "/usr/bin/yarn", "/usr/local/bin/yarn", "/usr/local/lib/node_modules/npm"]) {
  assert.equal(existsSync(path), false, "Package installer remains in web runtime");
}
console.log(JSON.stringify({ node: process.versions.node, modules: process.versions.modules,
  zlib: process.versions.zlib, brotli: process.versions.brotli, openssl: process.versions.openssl,
  standalone: "present", sharp: "absent", package_installers: "absent" }));
