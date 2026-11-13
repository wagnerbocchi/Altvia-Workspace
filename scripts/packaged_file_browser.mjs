// Real packaged browser -> API -> signed worker -> private download/MIME review.
// Credentials arrive only on stdin. Never emit raw Playwright failure diagnostics.
import { strict as assert } from "node:assert";
import { createHash, X509Certificate } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

assert.equal(process.env.ALTVIA_ALLOW_CONTAINER_TEST, "1");
const root = fileURLToPath(new URL("../", import.meta.url));
const work = resolve(process.argv[2]);
assert.match(work.replaceAll("\\", "/"), /\/\.superpowers\/container-tests\/altvia-test-[a-f0-9]{10}$/);
let raw = "";
for await (const chunk of process.stdin) { raw += chunk; assert.ok(raw.length <= 32768); }
const p = JSON.parse(raw);
const url = new URL(p.origin);
assert.equal(url.hostname, "workspace.altvia.test"); assert.equal(url.protocol, "https:");
const cert = new X509Certificate(await readFile(resolve(work, "secrets/tls_cert")));
const pin = createHash("sha256").update(cert.publicKey.export({ type: "spki", format: "der" })).digest("base64");
const webRequire = createRequire(new URL("../apps/web/package.json", import.meta.url));
const { chromium, expect } = webRequire("@playwright/test");
let browser;
try {
  browser = await chromium.launch({ args: [`--ignore-certificate-errors-spki-list=${pin}`, "--host-resolver-rules=MAP workspace.altvia.test 127.0.0.1"] });
  const context = await browser.newContext({ baseURL: p.origin, ignoreHTTPSErrors: false });
  await context.addCookies([{ name: "__Host-altvia_session", value: p.session, url: p.origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const page = await context.newPage();
  let errors = 0; page.on("pageerror", () => errors++);
  await page.goto(`/service-desk/tickets/${p.ticket_id}`);
  const ids = [];
  for (const file of p.files) {
    const label = file.purpose === "note" ? "nota interna" : "resposta publica";
    const group = page.getByRole("group", { name: `Arquivos para ${label}`, exact: true });
    await page.getByLabel(`Arquivo para ${label}`, { exact: true }).setInputFiles({ name: file.filename, mimeType: "text/plain", buffer: Buffer.from(file.body) });
    const uploaded = page.waitForResponse(response => response.url().includes(`/tickets/${p.ticket_id}/attachments?`) && response.request().method() === "POST");
    await group.getByRole("button", { name: `Enviar arquivo para ${label}`, exact: true }).click();
    const response = await uploaded; assert.equal(response.status(), 201);
    const receipt = await response.json(); ids.push(receipt.attachment_id);
    assert.equal(receipt.sha256, createHash("sha256").update(file.body).digest("hex"));
    const expected = file.filename.startsWith("eicar-") ? "rejected" : "ready";
    await expect.poll(async () => {
      const meta = await page.request.get(`/api/v1/attachments/${receipt.attachment_id}`);
      assert.equal(meta.status(), 200); return (await meta.json()).state;
    }, { timeout: 150000 }).toBe(expected);
    await group.getByRole("button", { name: `Atualizar arquivos para ${label}`, exact: true }).click();
    if (expected === "rejected") {
      await expect(group.getByLabel(`Incluir ${file.filename}`, { exact: true })).toBeDisabled();
      assert.equal((await page.request.get(`/api/v1/attachments/${receipt.attachment_id}/content`)).status(), 409);
    } else {
      const downloaded = page.waitForEvent("download");
      await group.getByRole("button", { name: `Baixar ${file.filename}`, exact: true }).click();
      const download = await downloaded; assert.equal(download.suggestedFilename(), file.filename);
      assert.deepEqual(await readFile(await download.path()), Buffer.from(file.body));
      if (file.purpose === "note") await group.getByLabel(`Incluir ${file.filename}`, { exact: true }).check();
    }
  }
  await page.getByLabel("Nota interna", { exact: true }).fill(p.private_marker);
  const noted = page.waitForResponse(response => response.url().endsWith(`/tickets/${p.ticket_id}/notes`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "Registrar nota interna", exact: true }).click();
  assert.equal((await noted).status(), 201);
  // A saved note advances the parent. Start the independent public draft from
  // the new authoritative version; selecting a file also binds draft intent.
  await page.reload();
  await page.getByRole("group", { name: "Arquivos para resposta publica", exact: true })
    .getByLabel(`Incluir ${p.files[0].filename}`, { exact: true }).check();
  await page.getByLabel("Texto da resposta", { exact: true }).fill(p.public_marker);
  await page.getByRole("button", { name: "Revisar rascunho", exact: true }).click();
  const draft = page.getByRole("group", { name: "Revisar rascunho de resposta", exact: true });
  await expect(draft.locator(".attachment-names li")).toHaveCount(1);
  const saved = page.waitForResponse(response => response.url().endsWith(`/tickets/${p.ticket_id}/messages`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "Salvar rascunho", exact: true }).click();
  const message = await saved; assert.equal(message.status(), 201);
  const messageId = (await message.json()).message_id;
  await page.getByRole("button", { name: "Revisar envio", exact: true }).click();
  const review = page.getByRole("region", { name: "Revisar envio de resposta", exact: true });
  await expect(review.locator(".attachment-names li")).toHaveCount(1);
  const deliveryPath = `/api/v1/tickets/${p.ticket_id}/messages/${messageId}/delivery`;
  const sent = page.waitForResponse(response => response.url().endsWith(deliveryPath) && response.request().method() === "POST");
  await page.getByRole("button", { name: "Confirmar envio", exact: true }).click();
  const delivery = await sent; assert.equal(delivery.status(), 201);
  assert.deepEqual(delivery.request().postDataJSON().attachment_ids, [ids[0]]);
  assert.equal(errors, 0);
  await delay(50);
  const deliveryId = (await delivery.json()).delivery_id;
  await context.close();
  console.log(JSON.stringify({ ids, ticket_id: p.ticket_id, message_id: messageId, delivery_id: deliveryId, delivery_path: deliveryPath, native_browser_upload: true, actual_worker_scan: true, clean_and_eicar: true, exact_private_download: true, private_note_link: true, explicit_public_send_review: true }));
} catch (error) {
  // Do not print error.message/stack: native locator diagnostics can contain
  // session, filename and fill/body arguments. Preserve a fixed failure code.
  console.error(`Packaged file browser proof failed (${error?.name === "AssertionError" ? "assertion" : "browser"}).`);
  process.exitCode = 1;
} finally { await browser?.close(); }
