// Guard a known incompatible optional dependency, not a substitute for VM tests.
import { createRequire } from "node:module";
const webRequire = createRequire(new URL("../apps/web/package.json", import.meta.url));
const nextRequire = createRequire(webRequire.resolve("next/package.json"));
try {
  nextRequire.resolve("sharp");
  throw new Error("Sharp must be absent: its Linux x64 prebuilt requires SSE4.2");
} catch (error) {
  if (error.code !== "MODULE_NOT_FOUND") throw error;
}
console.log("Known incompatible Sharp optional dependency is absent");
