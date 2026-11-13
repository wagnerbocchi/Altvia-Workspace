// Test-process diagnostics only; this never changes application HTTP/log owners.
import { spawn } from "node:child_process";
import { Transform, Writable } from "node:stream";
import { pipeline } from "node:stream/promises";

const MAX_LINE_BYTES = 65536;
const header = /(\b(?:cookie|set-cookie|authorization|proxy-authorization|x-csrf-token|csrf_token|session_token|password|secret_key|access_key)\b["']?[ \t]*:[ \t]*)[^\r\n]*/gi;
const credentialUrl = /([a-z][a-z0-9+.-]*:\/\/)[^/\s@]*@/gi;
const ansi = new RegExp(`${String.fromCharCode(27)}\\[[0-?]*[ -/]*[@-~]`, "g");

export function createSafeTestOutput() {
  let parts = [], size = 0, omitted = 0, lastByte;
  const emit = (stream, newline) => {
    if (omitted) {
      // Refuse an unbounded line rather than emit an unchecked prefix. Ordinary
      // diagnostics remain byte-exact; omission is explicit and byte-counted.
      stream.push(`[overlong test diagnostic line: ${omitted} bytes omitted]${newline ? lastByte === 13 ? "\r\n" : "\n" : ""}`);
    } else {
      const raw = Buffer.concat(parts, size);
      const plain = raw.toString("latin1").replace(ansi, "");
      header.lastIndex = 0;
      const filtered = plain.replace(header, "$1[REDACTED]").replace(credentialUrl, "$1[REDACTED]@");
      stream.push(filtered === plain ? raw : Buffer.from(filtered, "latin1"));
      if (newline) stream.push("\n");
    }
    parts = []; size = 0; omitted = 0; lastByte = undefined;
  };
  return new Transform({
    transform(chunk, _encoding, done) {
      const data = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      let start = 0;
      while (start < data.length) {
        const end = data.indexOf(10, start), stop = end < 0 ? data.length : end;
        const part = data.subarray(start, stop);
        if (part.length) lastByte = part.at(-1);
        if (omitted) omitted += part.length;
        else if (size + part.length > MAX_LINE_BYTES) { omitted = size + part.length; parts = []; size = 0; }
        else if (part.length) { parts.push(Buffer.from(part)); size += part.length; }
        if (end >= 0) emit(this, true);
        start = end < 0 ? data.length : end + 1;
      }
      done();
    },
    flush(done) { if (size || omitted) emit(this, false); done(); },
  });
}

export function spawnSafeTestChild(command, args, options = {}, destinations = { stdout: process.stdout, stderr: process.stderr }) {
  const child = spawn(command, args, { ...options, stdio: ["inherit", "pipe", "pipe"] });
  // Each pipeline owns its sink. Never end/destroy the shared parent stream or
  // accumulate pipeline listeners on it across migrations, workers and tests.
  const sink = destination => new Writable({ write(chunk, _encoding, done) { destination.write(chunk, done); } });
  const output = Promise.all([
    pipeline(child.stdout, createSafeTestOutput(), sink(destinations.stdout)),
    pipeline(child.stderr, createSafeTestOutput(), sink(destinations.stderr)),
  ]);
  // Background API/worker output is awaited during runner cleanup. Observe an
  // early rejection now, while retaining the original promise for that gate.
  void output.catch(() => {});
  return { child, output };
}
