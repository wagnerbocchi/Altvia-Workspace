import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const origin = "https://127.0.0.1:3443";
const root = fileURLToPath(new URL("../../../", import.meta.url));
const python = resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const body = Buffer.from("Browser original private attachment bytes\n");
const publicFiles = (page: Page) => page.getByRole("group", { name: "Arquivos para resposta publica", exact: true });
const noteFiles = (page: Page) => page.getByRole("group", { name: "Arquivos para nota interna", exact: true });
const headers = (csrf: string, version = 1) => ({ Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${version}"`, "Idempotency-Key": crypto.randomUUID() });
function scan(id: string, result = "clean") {
  execFileSync(python, ["scripts/browser_file_fixture.py", id, result], { cwd: root, env: process.env, stdio: "pipe" });
}
async function upload(page: Page, id: string, name = "browser-file-public.txt", purpose = "public", bytes = body, owner = "tickets") {
  const input = page.getByLabel(`Arquivo para ${purpose === "public" ? "resposta publica" : purpose === "note" ? "nota interna" : "comentario interno"}`, { exact: true });
  await input.setInputFiles({ name, mimeType: "text/plain", buffer: bytes });
  const response = page.waitForResponse(response => response.url().includes(`/api/v1/${owner}/${id}/attachments?`) && response.request().method() === "POST");
  await page.getByRole("button", { name: `Enviar arquivo para ${purpose === "public" ? "resposta publica" : purpose === "note" ? "nota interna" : "comentario interno"}`, exact: true }).click();
  const result = await response; expect(result.status()).toBe(201);
  const fileId = (await result.json()).attachment_id as string;
  await expect(page.getByRole("button", { name: "Recuperar arquivo", exact: true })).toHaveCount(0);
  await expect(page.getByLabel(`Incluir ${name}`, { exact: true })).toBeDisabled();
  return fileId;
}
async function ready(page: Page, fileId: string, name: string, purpose = "public") {
  scan(fileId);
  await page.getByRole("button", { name: `Atualizar arquivos para ${purpose === "public" ? "resposta publica" : purpose === "note" ? "nota interna" : "comentario interno"}`, exact: true }).click();
  await expect(page.getByLabel(`Incluir ${name}`, { exact: true })).toBeEnabled();
  await page.getByLabel(`Incluir ${name}`, { exact: true }).check();
}
async function capture(page: Page, name: string, focus = publicFiles(page)) {
  const folder = resolve(root, ".impeccable/review/private-files-task4"); await mkdir(folder, { recursive: true });
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(el => el.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      await expect(page.locator("html")).toHaveCSS("color-scheme", theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await focus.scrollIntoViewIfNeeded();
      await page.screenshot({ path: resolve(folder, `${name}-${size}-${theme}-viewport.png`) });
      await page.screenshot({ path: resolve(folder, `${name}-${size}-${theme}-full.png`), fullPage: true });
    }
  }
}
async function login(page: Page, kind = "AUTHOR") {
  await page.context().addCookies([{ name: "__Host-altvia_session", value: process.env[`ALTVIA_E2E_NOTE_${kind}_SESSION`]!, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const response = await page.request.get("/api/v1/auth/me");
  expect(response.status()).toBe(200);
  return (await response.json()).csrf_token as string;
}
async function ticket(page: Page, csrf: string) {
  const response = await page.request.post("/api/v1/tickets", { headers: { Origin: origin, "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID() }, data: {
    queue_id: process.env.ALTVIA_E2E_NOTE_QUEUE_ID, client_id: process.env.ALTVIA_E2E_TICKET_CLIENT_ID, requester_id: process.env.ALTVIA_E2E_TICKET_REQUESTER_ID,
    subject: `Delivery synthetic files ${crypto.randomUUID()}`, priority: "medium",
  } });
  expect(response.status()).toBe(201); return (await response.json()).ticket_id as string;
}

test("@files native selection keeps public and private purposes separate", async ({ page }) => {
  const id = await ticket(page, await login(page));
  await page.goto(`/service-desk/tickets/${id}`);
  await expect(page.getByLabel("Arquivo para resposta publica", { exact: true })).toHaveAttribute("type", "file");
  await expect(page.getByLabel("Arquivo para nota interna", { exact: true })).toHaveAttribute("type", "file");
});

test("@files real S3 upload scan download ordered draft review and MIME send", async ({ page }) => {
  test.setTimeout(120_000);
  const id = await ticket(page, await login(page));
  execFileSync(python, ["scripts/browser_delivery_fixture.py", id], { cwd: root, env: process.env, stdio: "pipe" });
  await page.goto(`/service-desk/tickets/${id}`);
  const first = "browser-file-primeiro.txt", second = "browser-file-segundo.txt";
  const one = await upload(page, id, first), two = await upload(page, id, second);
  await expect(publicFiles(page)).toContainText("Em quarentena - aguardando verificacao");
  expect((await page.request.get(`/api/v1/attachments/${one}/content`)).status()).toBe(409);
  await capture(page, "quarantine");
  await ready(page, two, second); await ready(page, one, first);
  await capture(page, "ready");
  const downloaded = page.waitForEvent("download");
  await publicFiles(page).getByRole("button", { name: `Baixar ${first}`, exact: true }).click();
  const download = await downloaded; expect(download.suggestedFilename()).toBe(first);
  expect(await readFile((await download.path())!)).toEqual(body);
  expect((await (await page.request.get(`/api/v1/tickets/${id}`)).json()).version).toBe(1);
  await page.getByLabel("Texto da resposta", { exact: true }).fill("E2E-FILE-MIME original public response");
  await page.getByRole("button", { name: "Revisar rascunho", exact: true }).focus(); await page.keyboard.press("Enter");
  const draftReview = page.getByRole("group", { name: "Revisar rascunho de resposta", exact: true });
  expect(await draftReview.locator(".attachment-names li").allTextContents()).toEqual([expect.stringContaining(second), expect.stringContaining(first)]);
  await page.getByRole("button", { name: "Salvar rascunho", exact: true }).click();
  await expect(page.getByRole("button", { name: "Revisar rascunho", exact: true })).toBeEnabled();
  const messages = (await (await page.request.get(`/api/v1/tickets/${id}/messages`)).json()).items;
  expect(messages).toHaveLength(1); expect(messages[0].attachments.map((file: { id: string }) => file.id)).toEqual([two, one]);
  await page.getByRole("button", { name: "Revisar envio", exact: true }).click();
  const sendReview = page.getByRole("region", { name: "Revisar envio de resposta", exact: true });
  expect(await sendReview.locator(".attachment-names li").allTextContents()).toEqual([expect.stringContaining(second), expect.stringContaining(first)]);
  await capture(page, "send-review", sendReview);
  const sent = page.waitForRequest(request => request.url().endsWith(`/messages/${messages[0].id}/delivery`) && request.method() === "POST");
  await page.getByRole("button", { name: "Confirmar envio", exact: true }).focus(); await page.keyboard.press("Enter");
  expect((await sent).postDataJSON().attachment_ids).toEqual([two, one]);
  await expect.poll(async () => (await (await page.request.get(`/api/v1/tickets/${id}/messages/${messages[0].id}/delivery`)).json()).state, { timeout: 45_000 }).toBe("accepted");
  const wires = (await readFile(process.env.ALTVIA_E2E_SMTP_CAPTURE!, "utf8")).trim().split("\n").map(line => JSON.parse(line));
  const wire = wires.find(item => item.body.includes("multipart/mixed") && item.body.includes(second));
  expect(wire).toBeTruthy(); expect(wire.body.indexOf(second)).toBeLessThan(wire.body.indexOf(first)); expect(wire.body).toContain(body.toString("base64"));
});

for (const committed of [false, true]) test(`@files uncertain binary upload ${committed} replays original bytes headers and key through failed metadata`, async ({ page }) => {
  test.setTimeout(60_000);
  const id = await ticket(page, await login(page)); await page.goto(`/service-desk/tickets/${id}`);
  const pattern = `**/api/v1/tickets/${id}/attachments?*`;
  let original: object | null = null, attempts = 0;
  await page.route(pattern, async route => {
    if (route.request().method() !== "POST") return route.continue();
    const request = route.request(), current = { url: request.url(), bytes: request.postDataBuffer(), key: request.headers()["idempotency-key"], version: request.headers()["if-match"], sha: request.headers()["x-file-sha256"] };
    expect(current.bytes).toEqual(body); expect(current.sha).toBe(createHash("sha256").update(body).digest("hex")); attempts++;
    if (!original) { original = current; if (committed) await route.fetch(); return route.abort("failed"); }
    expect(current).toEqual(original); return route.continue();
  });
  await page.getByLabel("Arquivo para resposta publica", { exact: true }).setInputFiles({ name: "browser-file-retido.txt", mimeType: "text/plain", buffer: body });
  await page.getByRole("button", { name: "Enviar arquivo para resposta publica", exact: true }).click();
  const recover = page.getByRole("button", { name: "Recuperar arquivo", exact: true }); await expect(recover).toBeVisible();
  if (committed) await capture(page, "recovery");
  let metadataFailures = 0;
  await page.route("**/api/v1/attachments/*", route => { metadataFailures++; return route.abort("failed"); });
  await recover.click(); await expect.poll(() => metadataFailures).toBe(1); await expect(recover).toBeEnabled(); await expect(publicFiles(page)).toContainText("browser-file-retido.txt");
  await page.getByRole("button", { name: "Atualizar arquivos para resposta publica", exact: true }).click();
  await expect(page.getByRole("button", { name: "Revisar rascunho", exact: true })).toBeDisabled();
  await page.unroute("**/api/v1/attachments/*"); await recover.click();
  await expect(recover).toHaveCount(0); await expect(page.getByRole("button", { name: "Revisar rascunho", exact: true })).toBeEnabled();
  expect(attempts).toBe(3);
  expect((await (await page.request.get(`/api/v1/tickets/${id}/attachments?purpose=public`)).json()).items).toHaveLength(1);
});

test("@files private note links never enter public review or unauthorized reads", async ({ page }) => {
  test.setTimeout(90_000);
  const csrf = await login(page), id = await ticket(page, csrf); await page.goto(`/service-desk/tickets/${id}`);
  const name = "browser-file-private-note.txt", identifier = await upload(page, id, name, "note"); await ready(page, identifier, name, "note");
  await page.getByLabel("Nota interna", { exact: true }).fill("Private note with original file");
  await page.getByRole("button", { name: "Registrar nota interna", exact: true }).click();
  await expect(page.getByRole("list", { name: "Notas internas", exact: true })).toContainText(name);
  await expect(page.getByLabel("Nota interna", { exact: true })).toHaveValue("");
  expect((await page.request.post(`/api/v1/tickets/${id}/messages`, { headers: headers(csrf, 2), data: { body_text: "Wrong purpose", attachment_ids: [identifier] } })).status()).toBe(404);
  await login(page, "NONE"); const privateReads: string[] = [];
  page.on("request", request => { if (request.url().includes(`/${id}/notes`) || request.url().includes(`/${id}/attachments?`) && request.url().includes("purpose=note")) privateReads.push(request.url()); });
  await page.goto(`/service-desk/tickets/${id}`); await expect(publicFiles(page)).toBeVisible();
  await expect(noteFiles(page)).toHaveCount(0); await expect(page.getByText(name, { exact: true })).toHaveCount(0);
  expect(privateReads).toEqual([]); expect((await page.request.get(`/api/v1/attachments/${identifier}`)).status()).toBe(404); expect((await page.request.get(`/api/v1/attachments/${identifier}/content`)).status()).toBe(404);
});

test("@files protocol rejection and eight failed attempts expose honest retry states", async ({ page }) => {
  test.setTimeout(120_000);
  const id = await ticket(page, await login(page)); await page.goto(`/service-desk/tickets/${id}`);
  const bad = await upload(page, id, "browser-file-eicar.txt", "public", Buffer.from("X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"));
  scan(bad, "infected"); await publicFiles(page).getByRole("button", { name: "Atualizar arquivos para resposta publica", exact: true }).click();
  await expect(publicFiles(page)).toContainText("Rejeitado - uso bloqueado"); await expect(page.getByLabel("Incluir browser-file-eicar.txt", { exact: true })).toBeDisabled();
  expect((await page.request.get(`/api/v1/attachments/${bad}/content`)).status()).toBe(409);
  const failed = await upload(page, id, "browser-file-failed.txt"); scan(failed, "failed");
  await publicFiles(page).getByRole("button", { name: "Atualizar arquivos para resposta publica", exact: true }).click();
  await expect(publicFiles(page)).toContainText("Verificacao falhou"); await capture(page, "rejected-failed");
  let retryIntent: object | null = null, retryAttempts = 0;
  await page.route(`**/api/v1/attachments/${failed}/scan-retries`, async route => {
    const request = route.request(), intent = { body: request.postData(), version: request.headers()["if-match"], key: request.headers()["idempotency-key"] }; retryAttempts++;
    if (retryAttempts === 1) { retryIntent = intent; expect((await route.fetch()).status()).toBe(201); return route.abort("failed"); }
    expect(intent).toEqual(retryIntent); return route.continue();
  });
  await page.getByRole("button", { name: "Verificar novamente browser-file-failed.txt", exact: true }).click();
  const recoverRetry = page.getByRole("button", { name: "Recuperar arquivo", exact: true }); await expect(recoverRetry).toBeVisible();
  const retried = page.waitForResponse(response => response.url().endsWith(`/attachments/${failed}/scan-retries`) && response.request().method() === "POST");
  await recoverRetry.click(); expect((await retried).status()).toBe(200); await expect(recoverRetry).toHaveCount(0); expect(retryAttempts).toBe(2);
  await expect(page.getByRole("button", { name: "Verificar novamente browser-file-failed.txt", exact: true })).toHaveCount(0);
  await ready(page, failed, "browser-file-failed.txt");
});

test("@files work comment persists its own ready files and is read-only to viewers", async ({ page }) => {
  test.setTimeout(90_000);
  await page.context().addCookies([{ name: "__Host-altvia_session", value: process.env.ALTVIA_E2E_WORK_MANAGER_SESSION!, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const csrf = (await (await page.request.get("/api/v1/auth/me")).json()).csrf_token;
  const response = await page.request.post("/api/v1/work-items", { headers: headers(csrf), data: { project_id: process.env.ALTVIA_E2E_WORK_PROJECT_ID, title: `Browser file work ${crypto.randomUUID()}`, work_type: "one_off", priority: "medium" } });
  expect(response.status()).toBe(201); const id = (await response.json()).work_item_id;
  await page.goto(`/work-items/${id}`);
  const name = "browser-file-work.txt", identifier = await upload(page, id, name, "work", body, "work-items"); await ready(page, identifier, name, "work");
  await page.getByLabel("Comentário interno", { exact: true }).fill("Internal work with file"); await page.getByRole("button", { name: "Registrar comentário", exact: true }).click();
  const comments = page.getByRole("list", { name: "Comentários internos", exact: true }); await expect(comments).toContainText(name);
  expect((await (await page.request.get(`/api/v1/work-items/${id}/comments`)).json()).items[0].attachments.map((file: { id: string }) => file.id)).toEqual([identifier]);
  await page.context().addCookies([{ name: "__Host-altvia_session", value: process.env.ALTVIA_E2E_WORK_READER_SESSION!, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  await page.reload(); await expect(comments).toContainText(name); await expect(page.getByLabel("Arquivo para comentario interno", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: `Baixar ${name}`, exact: true }).first()).toBeEnabled();
});

test("@files actual held scanner claim exposes scanning before a ready result", async ({ page }) => {
  test.setTimeout(90_000);
  const id = await ticket(page, await login(page)); await page.goto(`/service-desk/tickets/${id}`);
  const identifier = await upload(page, id, "browser-file-scanning.txt");
  const child = spawn(python, ["scripts/browser_file_fixture.py", identifier, "clean", "--hold", "20"], { cwd: root, env: process.env, stdio: "pipe" });
  const completed = new Promise<number | null>((resolve, reject) => { child.once("exit", resolve); child.once("error", reject); });
  await expect.poll(async () => (await (await page.request.get(`/api/v1/attachments/${identifier}`)).json()).state).toBe("scanning");
  await publicFiles(page).getByRole("button", { name: "Atualizar arquivos para resposta publica", exact: true }).click();
  await expect(publicFiles(page)).toContainText("Verificando seguranca"); await expect(page.getByLabel("Incluir browser-file-scanning.txt", { exact: true })).toBeDisabled();
  await capture(page, "scanning"); expect(await completed).toBe(0);
  await publicFiles(page).getByRole("button", { name: "Atualizar arquivos para resposta publica", exact: true }).click();
  await expect(page.getByLabel("Incluir browser-file-scanning.txt", { exact: true })).toBeEnabled();
});

test("@files resource denial retains binary intent until original authority is restored", async ({ page, browser }) => {
  const manager = await browser.newContext({ baseURL: origin, ignoreHTTPSErrors: true });
  try {
    const managerPage = await manager.newPage(), csrf = await login(managerPage), id = await ticket(managerPage, csrf), path = `/api/v1/tickets/${id}`;
    expect((await managerPage.request.patch(path, { headers: headers(csrf), data: { assignee_id: process.env.ALTVIA_E2E_NOTE_READER_ID } })).status()).toBe(200);
    await login(page, "READER"); await page.goto(`/service-desk/tickets/${id}`);
    let attempts = 0; let original: object | null = null;
    await page.route(`**${path}/attachments?*`, async route => {
      if (route.request().method() !== "POST") return route.continue();
      const request = route.request(), current = { data: request.postDataBuffer(), key: request.headers()["idempotency-key"], version: request.headers()["if-match"] };
      attempts++;
      if (attempts === 1) { original = current; const response = await route.fetch(); expect(response.status()).toBe(201); return route.abort("failed"); }
      expect(current).toEqual(original); return route.continue();
    });
    await page.getByLabel("Arquivo para resposta publica", { exact: true }).setInputFiles({ name: "browser-file-revoked.txt", mimeType: "text/plain", buffer: body });
    await page.getByRole("button", { name: "Enviar arquivo para resposta publica", exact: true }).click();
    const recover = page.getByRole("button", { name: "Recuperar arquivo", exact: true }); await expect(recover).toBeVisible();
    expect((await managerPage.request.patch(path, { headers: headers(csrf, 2), data: { assignee_id: null } })).status()).toBe(200);
    const denied = page.waitForResponse(response => response.url().includes(path + "/attachments?") && response.request().method() === "POST");
    await recover.click(); expect((await denied).status()).toBe(403);
    await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
    await expect(recover).toBeVisible(); await expect(publicFiles(page)).toContainText("browser-file-revoked.txt");
    expect((await managerPage.request.patch(path, { headers: headers(csrf, 3), data: { assignee_id: process.env.ALTVIA_E2E_NOTE_READER_ID } })).status()).toBe(200);
    await recover.click(); await expect(recover).toHaveCount(0); expect(attempts).toBe(3);
  } finally { await manager.close(); }
});

test("@files uncertain draft keeps the exact ordered file review through replay and failed receipt read", async ({ page }) => {
  const id = await ticket(page, await login(page)); await page.goto(`/service-desk/tickets/${id}`);
  const name = "browser-file-draft-recovery.txt", identifier = await upload(page, id, name); await ready(page, identifier, name);
  await page.getByLabel("Texto da resposta", { exact: true }).fill("File draft recovery"); await page.getByRole("button", { name: "Revisar rascunho", exact: true }).click();
  let attempts = 0, original: object | null = null;
  await page.route(`**/api/v1/tickets/${id}/messages`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    const request = route.request(), intent = { body: request.postData(), key: request.headers()["idempotency-key"], version: request.headers()["if-match"] }; attempts++;
    if (attempts === 1) { original = intent; await route.fetch(); return route.abort("failed"); }
    expect(intent).toEqual(original); expect(request.postDataJSON().attachment_ids).toEqual([identifier]); return route.continue();
  });
  await page.getByRole("button", { name: "Salvar rascunho", exact: true }).click(); const verify = page.getByRole("button", { name: "Verificar rascunho", exact: true }); await expect(verify).toBeVisible();
  await expect(page.getByRole("group", { name: "Revisar rascunho de resposta", exact: true })).toContainText(name);
  await page.route(`**/api/v1/tickets/${id}/messages/*`, route => route.abort("failed")); await verify.click();
  await expect(page.getByRole("button", { name: "Revisar rascunho", exact: true })).toBeDisabled();
  await page.unroute(`**/api/v1/tickets/${id}/messages/*`); await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Revisar rascunho", exact: true })).toBeEnabled(); expect(attempts).toBe(2);
  const saved = (await (await page.request.get(`/api/v1/tickets/${id}/messages`)).json()).items;
  expect(saved).toHaveLength(1); expect(saved[0].attachments.map((file: { id: string }) => file.id)).toEqual([identifier]);
});

for (const phase of ["UPLOAD", "DOWNLOAD"]) test(`@files real session end disposes in-flight ${phase.toLowerCase()} without releasing private bytes`, async ({ page }) => {
  test.setTimeout(90_000);
  const id = await ticket(page, await login(page)); await page.goto(`/service-desk/tickets/${id}`);
  const name = `browser-file-session-${phase.toLowerCase()}.txt`;
  let identifier: string | null = null;
  if (phase === "DOWNLOAD") { identifier = await upload(page, id, name); await ready(page, identifier, name); }
  await page.context().addCookies([{ name: "__Host-altvia_session", value: process.env[`ALTVIA_E2E_FILE_${phase}_SESSION`]!, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  await page.reload(); await expect(publicFiles(page)).toBeVisible();
  const csrf = (await (await page.request.get("/api/v1/auth/me")).json()).csrf_token;
  let release: () => void = () => {}, reached = false, downloads = 0;
  const gate = new Promise<void>(done => { release = done; });
  page.on("download", () => { downloads++; });
  const pattern = phase === "UPLOAD" ? `**/api/v1/tickets/${id}/attachments?*` : `**/api/v1/attachments/${identifier}/content`;
  await page.route(pattern, async route => {
    if (phase === "UPLOAD" && route.request().method() !== "POST") return route.continue();
    const response = await route.fetch(); expect(response.status()).toBe(phase === "UPLOAD" ? 201 : 200);
    reached = true; await gate;
    try { await route.fulfill({ response }); } catch { /* Session cleanup aborts the original request. */ }
  });
  if (phase === "UPLOAD") {
    await page.getByLabel("Arquivo para resposta publica", { exact: true }).setInputFiles({ name, mimeType: "text/plain", buffer: body });
    await page.getByRole("button", { name: "Enviar arquivo para resposta publica", exact: true }).click();
  } else await publicFiles(page).getByRole("button", { name: `Baixar ${name}`, exact: true }).click();
  await expect.poll(() => reached).toBe(true);
  if (phase === "UPLOAD") await capture(page, "sending");
  expect((await page.request.delete("/api/v1/auth/sessions/current", { headers: { Origin: origin, "X-CSRF-Token": csrf } })).status()).toBe(204);
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Acesse seu workspace", exact: true })).toBeVisible();
  release(); await page.unrouteAll({ behavior: "wait" });
  await expect(publicFiles(page)).toHaveCount(0); await expect(page.getByText(name, { exact: true })).toHaveCount(0); expect(downloads).toBe(0);
  expect(await page.evaluate(() => ({ local: Object.keys(localStorage).filter(key => key !== "theme"), session: sessionStorage.length }))).toEqual({ local: [], session: 0 });
  await login(page); await page.reload(); await expect(publicFiles(page)).toBeVisible();
  await expect(page.getByRole("button", { name: "Recuperar arquivo", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Arquivo para resposta publica", { exact: true })).toHaveValue("");
});

test("@files viewer can download current public files without upload or note metadata", async ({ page }) => {
  test.setTimeout(90_000);
  const id = await ticket(page, await login(page)); await page.goto(`/service-desk/tickets/${id}`);
  const name = "browser-file-viewer.txt", identifier = await upload(page, id, name); await ready(page, identifier, name);
  await login(page, "VIEWER"); await page.reload();
  await expect(publicFiles(page)).toContainText("Acesso de consulta"); await expect(page.getByLabel("Arquivo para resposta publica", { exact: true })).toHaveCount(0); await expect(noteFiles(page)).toHaveCount(0);
  await expect(publicFiles(page).getByRole("button", { name: `Baixar ${name}`, exact: true })).toBeEnabled();
  await capture(page, "read-only");
});

test("@files work comment keeps reviewed files and version until explicit conflict discard", async ({ page }) => {
  test.setTimeout(60_000);
  await page.context().addCookies([{ name: "__Host-altvia_session", value: process.env.ALTVIA_E2E_WORK_MANAGER_SESSION!, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const csrf = (await (await page.request.get("/api/v1/auth/me")).json()).csrf_token;
  const response = await page.request.post("/api/v1/work-items", { headers: headers(csrf), data: { project_id: process.env.ALTVIA_E2E_WORK_PROJECT_ID, title: `Browser file work ${crypto.randomUUID()}`, work_type: "one_off", priority: "medium" } });
  expect(response.status()).toBe(201); const id = (await response.json()).work_item_id;
  await page.goto(`/work-items/${id}`); const name = "browser-file-work-conflict.txt";
  const identifier = await upload(page, id, name, "work", body, "work-items"); await ready(page, identifier, name, "work");
  await page.getByLabel("Comentário interno", { exact: true }).fill("Original reviewed work comment");
  expect((await page.request.patch(`/api/v1/work-items/${id}`, { headers: headers(csrf), data: { priority: "high" } })).status()).toBe(200);
  const conflict = page.waitForResponse(response => response.url().endsWith(`/work-items/${id}/comments`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "Registrar comentário", exact: true }).click(); const result = await conflict;
  expect(result.status()).toBe(409); expect(result.request().headers()["if-match"]).toBe('"1"'); expect(result.request().postDataJSON().attachment_ids).toEqual([identifier]);
  await expect(page.getByLabel("Incluir " + name, { exact: true })).toBeChecked(); await expect(page.getByLabel("Comentário interno", { exact: true })).toHaveValue("Original reviewed work comment");
  await page.getByRole("button", { name: "Recarregar e descartar edição", exact: true }).click();
  await expect(page.getByLabel("Comentário interno", { exact: true })).toHaveValue(""); await expect(page.getByLabel("Incluir " + name, { exact: true })).not.toBeChecked();
  await page.getByLabel("Incluir " + name, { exact: true }).check(); await page.getByLabel("Comentário interno", { exact: true }).fill("New explicitly reviewed comment");
  await page.getByRole("button", { name: "Registrar comentário", exact: true }).click(); await expect(page.getByRole("list", { name: "Comentários internos", exact: true })).toContainText("New explicitly reviewed comment");
});
