// Synthetic private S3 trust only. Production material is supplied externally.
import { isIP } from "node:net";
import { createRequire } from "node:module";
import { chmod, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
const require = createRequire(new URL("../apps/web/package.json", import.meta.url));
if (process.env.ALTVIA_ALLOW_FILE_INFRA_TEST !== "1") throw Error("Explicit file test opt-in required");
const directory = process.argv[2];
if (!directory) throw Error("Private secret directory required");
const address = process.argv[3];
if (address && !isIP(address)) throw Error("Invalid private fixture IP");
const certificate = await require("selfsigned").generate([{ name: "commonName", value: "storage" }], {
  keySize: 2048, algorithm: "sha256",
  extensions: [{ name: "subjectAltName", altNames: [{ type: 2, value: "storage" }, ...(address ? [{ type: 7, ip: address }] : [])] }],
});
for (const [name, data] of Object.entries({ storage_cert: certificate.cert, storage_key: certificate.private, storage_ca: certificate.cert })) {
  await writeFile(resolve(directory, name), data, { mode: 0o444 });
  await chmod(resolve(directory, name), 0o444);
}
