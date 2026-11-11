// Controlled loopback IMAPS certificates only; never production trust material.
import { createRequire } from "node:module";
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
const require = createRequire(new URL("../apps/web/package.json", import.meta.url));
if (process.env.ALTVIA_ALLOW_IMAP_TEST !== "1") throw Error("Explicit IMAP test opt-in required");
const directory = process.argv[2];
if (!directory) throw Error("Private test directory required");
const generated = await require("selfsigned").generate([{ name: "commonName", value: "localhost" }], {
  keySize: 2048, algorithm: "sha256",
  extensions: [{ name: "subjectAltName", altNames: [{ type: 2, value: "localhost" }] }],
});
await writeFile(resolve(directory, "imap_cert"), generated.cert, { mode: 0o600 });
await writeFile(resolve(directory, "imap_key"), generated.private, { mode: 0o600 });
