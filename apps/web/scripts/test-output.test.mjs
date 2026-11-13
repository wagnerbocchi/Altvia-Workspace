import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { once } from "node:events";
import { PassThrough, Readable } from "node:stream";
import { test } from "node:test";

async function owners() {
  assert.ok(existsSync(new URL("./test-output.mjs", import.meta.url)), "Committed test output protection is missing");
  return import("./test-output.mjs");
}

async function childProof(source) {
  const { spawnSafeTestChild } = await owners();
  const stdout = new PassThrough(), stderr = new PassThrough(), out = [], err = [];
  stdout.on("data", chunk => out.push(chunk)); stderr.on("data", chunk => err.push(chunk));
  const { child, output } = spawnSafeTestChild(process.execPath, ["--input-type=module", "-e", source], {}, { stdout, stderr });
  const [code] = await once(child, "close"); await output;
  return { code, stdout: Buffer.concat(out), stderr: Buffer.concat(err) };
}

test("actual failing child keeps diagnostics and status while hiding dynamic headers on both streams", async () => {
  const result = await childProof(`
    import { randomUUID } from "node:crypto";
    import { setTimeout as delay } from "node:timers/promises";
    process.stdout.write("ordinary diagnostic: expected receipt\\r\\n");
    process.stderr.write("failure stack:\\n  at actual-child:17:3\\n");
    for (const [target, name] of [[process.stdout,"Cookie"],[process.stderr,"X-CSRF-Token"],[process.stdout,"Set-Cookie"],[process.stderr,"Authorization"]]) {
      const secret="synthetic-dynamic-"+randomUUID();
      for (const part of ["    - ",name.slice(0,2),name.slice(2),": ",secret.slice(0,5),secret.slice(5),"\\r\\n"]) {
        target.write(part); await delay(2);
      }
    }
    process.stdout.write("assertion failed: expected201 received409\\n");
    process.stdout.write("broker failed: redis://:synthetic-url-password@127.0.0.1:6379/0\\n");
    process.stderr.write('  "password": "synthetic-json-password"\\n');
    process.stderr.write("remaining stack: test-output.test.mjs:27\\n");
    process.exitCode=7;
  `);
  assert.equal(result.code, 7);
  assert.equal(result.stdout.toString(), "ordinary diagnostic: expected receipt\r\n    - Cookie: [REDACTED]\r\n    - Set-Cookie: [REDACTED]\r\nassertion failed: expected201 received409\nbroker failed: redis://[REDACTED]@127.0.0.1:6379/0\n");
  assert.equal(result.stderr.toString(), "failure stack:\n  at actual-child:17:3\n    - X-CSRF-Token: [REDACTED]\r\n    - Authorization: [REDACTED]\r\n  \"password\": [REDACTED]\nremaining stack: test-output.test.mjs:27\n");
  assert.doesNotMatch(Buffer.concat([result.stdout, result.stderr]).toString(), /synthetic-(dynamic|url|json)-/);
});

test("every byte boundary preserves ordinary UTF8 and binary bytes but masks quoted ANSI and EOF headers", async () => {
  const { createSafeTestOutput } = await owners();
  const input = Buffer.concat([Buffer.from("Diagnostico de ação\r\n"), Buffer.from([255]), Buffer.from(" intact\n\u001b[31m  - \"cOoKiE\": dynamic-cookie\u001b[0m\r\n  x-csrf-token: dynamic-csrf\n  csrf_token: dynamic-json\nAuthorization: dynamic-eof")]);
  const expected = Buffer.concat([Buffer.from("Diagnostico de ação\r\n"), Buffer.from([255]), Buffer.from(" intact\n  - \"cOoKiE\": [REDACTED]\r\n  x-csrf-token: [REDACTED]\n  csrf_token: [REDACTED]\nAuthorization: [REDACTED]")]);
  for (let boundary = 1; boundary < input.length; boundary++) {
    const chunks = [];
    for await (const chunk of Readable.from([input.subarray(0, boundary), input.subarray(boundary)]).pipe(createSafeTestOutput())) chunks.push(chunk);
    assert.deepEqual(Buffer.concat(chunks), expected, `Boundary ${boundary}`);
  }
  const chunks = [];
  for await (const chunk of Readable.from([...input].map(byte => Buffer.from([byte]))).pipe(createSafeTestOutput())) chunks.push(chunk);
  assert.deepEqual(Buffer.concat(chunks), expected);
});

test("actual failed child with an overlong line emits explicit bounded diagnostics and keeps following stderr", async () => {
  const result = await childProof(`
    import { once } from "node:events";
    for(let index=0;index<128;index++) if(!process.stdout.write(Buffer.alloc(32768,120))) await once(process.stdout,"drain");
    process.stdout.write(" Cookie: synthetic-overflow-secret\\ncontinued assertion: expected clean received failed\\n");
    process.stderr.write("full independent stderr stack\\r\\n  at bounded-child:9:2\\r\\n");
    process.exitCode=9;
  `);
  assert.equal(result.code, 9);
  assert.ok(result.stdout.length < 512, "Overlong output must remain bounded");
  assert.match(result.stdout.toString(), /\[overlong test diagnostic line: \d+ bytes omitted\]/);
  assert.match(result.stdout.toString(), /continued assertion: expected clean received failed/);
  assert.doesNotMatch(result.stdout.toString(), /synthetic-overflow-secret/);
  assert.equal(result.stderr.toString(), "full independent stderr stack\r\n  at bounded-child:9:2\r\n");
});
