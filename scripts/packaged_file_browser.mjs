// Real packaged browser -> API -> signed worker -> private download/MIME review.
// Credentials arrive only on stdin. Never emit raw Playwright failure diagnostics.
import { strict as assert } from "node:assert";
import { createHash, X509Certificate } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import { browserGet, emitBrowserFailure, initialDiagnostic, scanStates } from "./packaged_file_browser_support.mjs";

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
const diagnostic = initialDiagnostic();
try {
  browser = await chromium.launch({ args: [`--ignore-certificate-errors-spki-list=${pin}`, "--host-resolver-rules=MAP workspace.altvia.test 127.0.0.1"] });
  diagnostic.phase = "context";
  const context = await browser.newContext({ baseURL: p.origin, ignoreHTTPSErrors: false });
  diagnostic.phase = "cookie";
  await context.addCookies([{ name: "__Host-altvia_session", value: p.session, url: p.origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const page = await context.newPage();
  let errors = 0; page.on("pageerror", () => { errors++; diagnostic.page_errors = Math.min(errors, 1000); });
  if (p.incoming) {
    diagnostic.phase = "incoming_navigate";
    await page.goto(`/service-desk/mail-cases/${p.incoming.case_id}`);
    const group = page.getByRole("group", { name: "Arquivos recebidos", exact: true });
    await expect(group).toBeVisible();
    await expect(group.locator('input[type="file"],input[type="checkbox"]')).toHaveCount(0);
    const original = await browserGet(page, `/api/v1/mail-cases/${p.incoming.case_id}`);
    diagnostic.http_status = original.status; assert.equal(original.status, 200);
    assert.equal(original.body.files.status, "complete");
    assert.equal(original.body.files.extraction_version, 1);
    const ids = original.body.files.items.map(file => file.id);
    assert.equal(ids.length, p.incoming.files.length);
    diagnostic.phase = "incoming_review";
    await page.getByLabel("Assunto do novo chamado", { exact: true }).fill("Reviewed packaged incoming files");
    await page.getByRole("button", { name: "Revisar criacao", exact: true }).click();
    for (const [slot, file] of p.incoming.files.entries()) {
      diagnostic.file_slot = slot + 1; diagnostic.phase = "scan_metadata";
      await expect.poll(async () => {
        const meta = await browserGet(page, `/api/v1/attachments/${ids[slot]}`);
        diagnostic.http_status = meta.status;
        diagnostic.scan_state = scanStates.includes(meta.body?.state) ? meta.body.state : "invalid";
        assert.equal(meta.status, 200); return meta.body.state;
      }, { timeout: 150000 }).toBe(file.state);
      diagnostic.phase = "refresh_files";
      await group.getByRole("button", { name: "Atualizar arquivos recebidos", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Revisar inclusao da mensagem", exact: true })).toBeVisible();
      if (file.state === "ready") {
        diagnostic.phase = "download";
        const downloaded = page.waitForEvent("download");
        await group.getByRole("button", { name: `Baixar ${file.filename}`, exact: true }).click();
        const download = await downloaded; assert.equal(download.suggestedFilename(), file.filename);
        assert.deepEqual(await readFile(await download.path()), Buffer.from(file.body));
      } else {
        diagnostic.phase = "rejected_block";
        await expect(group.getByRole("button", { name: `Baixar ${file.filename}`, exact: true })).toHaveCount(0);
        const denied = await browserGet(page, `/api/v1/attachments/${ids[slot]}/content`);
        diagnostic.http_status = denied.status; assert.equal(denied.status, 409);
      }
    }
    diagnostic.phase = "incoming_promote";
    const promoted = page.waitForResponse(response => response.url().endsWith(`/mail-cases/${p.incoming.case_id}/promotion`) && response.request().method() === "POST");
    await page.getByRole("button", { name: "Confirmar criacao", exact: true }).click();
    const response = await promoted; diagnostic.http_status = response.status(); assert.equal(response.status(), 201);
    const receipt = await response.json();
    await page.getByRole("link", { name: "Abrir chamado confirmado", exact: true }).click();
    diagnostic.phase = "incoming_conversation";
    await page.waitForURL(`**/service-desk/tickets/${receipt.ticket_id}`);
    await expect(group).toBeVisible();
    const incoming = await browserGet(page, `/api/v1/tickets/${receipt.ticket_id}/incoming-messages/${receipt.incoming_message_id}`);
    diagnostic.http_status = incoming.status; assert.equal(incoming.status, 200);
    assert.deepEqual(incoming.body.files.items.map(file => file.id), ids);
    assert.equal(incoming.body.case_id, p.incoming.case_id);
    diagnostic.phase = "download";
    const downloaded = page.waitForEvent("download");
    await group.getByRole("button", { name: `Baixar ${p.incoming.files[0].filename}`, exact: true }).click();
    assert.deepEqual(await readFile(await (await downloaded).path()), Buffer.from(p.incoming.files[0].body));
    assert.equal(errors, 0);
    diagnostic.phase = "close"; await context.close();
    console.log(JSON.stringify({ ids, ticket_id: receipt.ticket_id, incoming_id: receipt.incoming_message_id,
      native_incoming_browser: true, frozen_review_current_files: true, exact_incoming_download: true }));
  } else {
  diagnostic.phase = "navigate";
  await page.goto(`/service-desk/tickets/${p.ticket_id}`);
  const ids = [];
  for (const [slot, file] of p.files.entries()) {
    diagnostic.file_slot = slot + 1; diagnostic.http_status = 0; diagnostic.scan_state = "unknown";
    const label = file.purpose === "note" ? "nota interna" : "resposta publica";
    const group = page.getByRole("group", { name: `Arquivos para ${label}`, exact: true });
    diagnostic.phase = "select_file";
    await page.getByLabel(`Arquivo para ${label}`, { exact: true }).setInputFiles({ name: file.filename, mimeType: "text/plain", buffer: Buffer.from(file.body) });
    const uploaded = page.waitForResponse(response => response.url().includes(`/tickets/${p.ticket_id}/attachments?`) && response.request().method() === "POST");
    diagnostic.phase = "upload";
    await group.getByRole("button", { name: `Enviar arquivo para ${label}`, exact: true }).click();
    const response = await uploaded; diagnostic.http_status = response.status(); assert.equal(response.status(), 201);
    const receipt = await response.json(); ids.push(receipt.attachment_id);
    assert.equal(receipt.sha256, createHash("sha256").update(file.body).digest("hex"));
    const expected = file.filename.startsWith("eicar-") ? "rejected" : "ready";
    diagnostic.phase = "scan_metadata";
    await expect.poll(async () => {
      const meta = await browserGet(page, `/api/v1/attachments/${receipt.attachment_id}`);
      diagnostic.http_status = meta.status;
      diagnostic.scan_state = scanStates.includes(meta.body?.state) ? meta.body.state : "invalid";
      assert.equal(meta.status, 200); return meta.body.state;
    }, { timeout: 150000 }).toBe(expected);
    diagnostic.phase = "refresh_files";
    await group.getByRole("button", { name: `Atualizar arquivos para ${label}`, exact: true }).click();
    if (expected === "rejected") {
      diagnostic.phase = "rejected_block";
      await expect(group.getByLabel(`Incluir ${file.filename}`, { exact: true })).toBeDisabled();
      const blocked = await browserGet(page, `/api/v1/attachments/${receipt.attachment_id}/content`);
      diagnostic.http_status = blocked.status; assert.equal(blocked.status, 409);
    } else {
      diagnostic.phase = "download";
      const downloaded = page.waitForEvent("download");
      await group.getByRole("button", { name: `Baixar ${file.filename}`, exact: true }).click();
      const download = await downloaded; assert.equal(download.suggestedFilename(), file.filename);
      assert.deepEqual(await readFile(await download.path()), Buffer.from(file.body));
      if (file.purpose === "note") { diagnostic.phase = "select_note"; await group.getByLabel(`Incluir ${file.filename}`, { exact: true }).check(); }
    }
  }
  diagnostic.phase = "note_fill";
  await page.getByLabel("Nota interna", { exact: true }).fill(p.private_marker);
  const noted = page.waitForResponse(response => response.url().endsWith(`/tickets/${p.ticket_id}/notes`) && response.request().method() === "POST");
  diagnostic.phase = "note_save";
  await page.getByRole("button", { name: "Registrar nota interna", exact: true }).click();
  const noteResponse = await noted; diagnostic.http_status = noteResponse.status(); assert.equal(noteResponse.status(), 201);
  // A saved note advances the parent. Start the independent public draft from
  // the new authoritative version; selecting a file also binds draft intent.
  diagnostic.phase = "note_reload";
  await page.reload();
  diagnostic.phase = "select_public";
  await page.getByRole("group", { name: "Arquivos para resposta publica", exact: true })
    .getByLabel(`Incluir ${p.files[0].filename}`, { exact: true }).check();
  diagnostic.phase = "draft_fill";
  await page.getByLabel("Texto da resposta", { exact: true }).fill(p.public_marker);
  diagnostic.phase = "draft_review";
  await page.getByRole("button", { name: "Revisar rascunho", exact: true }).click();
  const draft = page.getByRole("group", { name: "Revisar rascunho de resposta", exact: true });
  await expect(draft.locator(".attachment-names li")).toHaveCount(1);
  const saved = page.waitForResponse(response => response.url().endsWith(`/tickets/${p.ticket_id}/messages`) && response.request().method() === "POST");
  diagnostic.phase = "draft_save";
  await page.getByRole("button", { name: "Salvar rascunho", exact: true }).click();
  const message = await saved; diagnostic.http_status = message.status(); assert.equal(message.status(), 201);
  const messageId = (await message.json()).message_id;
  diagnostic.phase = "send_review";
  await page.getByRole("button", { name: "Revisar envio", exact: true }).click();
  const review = page.getByRole("region", { name: "Revisar envio de resposta", exact: true });
  await expect(review.locator(".attachment-names li")).toHaveCount(1);
  const deliveryPath = `/api/v1/tickets/${p.ticket_id}/messages/${messageId}/delivery`;
  const sent = page.waitForResponse(response => response.url().endsWith(deliveryPath) && response.request().method() === "POST");
  diagnostic.phase = "send_confirm";
  await page.getByRole("button", { name: "Confirmar envio", exact: true }).click();
  const delivery = await sent; diagnostic.http_status = delivery.status(); assert.equal(delivery.status(), 201);
  assert.deepEqual(delivery.request().postDataJSON().attachment_ids, [ids[0]]);
  assert.equal(errors, 0);
  diagnostic.phase = "complete";
  await delay(50);
  const deliveryId = (await delivery.json()).delivery_id;
  diagnostic.phase = "close"; await context.close();
  console.log(JSON.stringify({ ids, ticket_id: p.ticket_id, message_id: messageId, delivery_id: deliveryId, delivery_path: deliveryPath, native_browser_upload: true, actual_worker_scan: true, clean_and_eicar: true, exact_private_download: true, private_note_link: true, explicit_public_send_review: true }));
  }
} catch (error) {
  // Do not print error.message/stack: native locator diagnostics can contain
  // session, filename and fill/body arguments. Preserve a fixed failure code.
  await emitBrowserFailure(work, diagnostic, error);
} finally {
  try { await browser?.close(); }
  catch (error) { if (!process.exitCode) { diagnostic.phase = "close"; await emitBrowserFailure(work, diagnostic, error); } }
}
