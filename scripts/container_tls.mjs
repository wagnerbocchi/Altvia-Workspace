// Synthetic test certificates only. Production TLS material is supplied externally.
import { createRequire } from "node:module";
import { chmod, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const require = createRequire(new URL("../apps/web/package.json", import.meta.url));
const selfsigned = require("selfsigned");
if (process.env.ALTVIA_ALLOW_CONTAINER_TEST !== "1") throw Error("Explicit test opt-in required");
const directory = process.argv[2];
if (!directory) throw Error("Test secret directory required");
const certificate = await selfsigned.generate([{ name: "commonName", value: "workspace.altvia.test" }], {
  keySize: 2048, algorithm: "sha256", extensions: [{ name: "subjectAltName", altNames: [
    { type: 2, value: "workspace.altvia.test" },
  ] }],
});
await writeFile(resolve(directory, "tls_cert"), certificate.cert, { mode: 0o444 });
await writeFile(resolve(directory, "tls_key"), certificate.private, { mode: 0o444 });
// File creation modes are masked by umask; non-root secret mounts need the
// explicit read-only mode inside the caller's private parent directory.
await chmod(resolve(directory, "tls_cert"), 0o444);
await chmod(resolve(directory, "tls_key"), 0o444);
