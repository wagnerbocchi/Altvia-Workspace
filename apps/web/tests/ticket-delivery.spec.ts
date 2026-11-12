import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { readFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const origin = "https://127.0.0.1:3443";
async function login(page: Page, kind = "AUTHOR") {
  await page.context().addCookies([{ name: "__Host-altvia_session", value: process.env[`ALTVIA_E2E_NOTE_${kind}_SESSION`]!, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const result = await page.request.get("/api/v1/auth/me");
  expect(result.status()).toBe(200); return (await result.json()).csrf_token as string;
}
const headers = (csrf: string, version: number) => ({ Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${version}"`, "Idempotency-Key": crypto.randomUUID() });
async function setup(page: Page, body: string, verified = true, assigned = false) {
  const csrf = await login(page);
  const created = await page.request.post("/api/v1/tickets", { headers: headers(csrf, 1), data: { queue_id: process.env.ALTVIA_E2E_NOTE_QUEUE_ID, client_id: process.env.ALTVIA_E2E_TICKET_CLIENT_ID, requester_id: process.env.ALTVIA_E2E_TICKET_REQUESTER_ID, subject: `Delivery synthetic ${crypto.randomUUID()}`, priority: "medium" } });
  expect(created.status()).toBe(201);
  const id = (await created.json()).ticket_id;
  const api = `/api/v1/tickets/${id}`;
  let version = 1;
  if (assigned) { expect((await page.request.patch(api, { headers: headers(csrf, version++), data: { assignee_id: process.env.ALTVIA_E2E_NOTE_READER_ID } })).status()).toBe(200); }
  const message = await page.request.post(api + "/messages", { headers: headers(csrf, version++), data: { body_text: body } });
  expect(message.status()).toBe(201);
  const messageId = (await message.json()).message_id;
  if (verified) execFileSync(resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"), ["scripts/browser_delivery_fixture.py", id], { cwd: root, env: process.env, stdio: "pipe" });
  return { csrf, id, api, messageId, version };
}
const deliveryReview = (page: Page) => page.getByRole("region", { name: "Revisar envio de resposta", exact: true });
async function review(page: Page, id: string) {
  await page.goto(`/service-desk/tickets/${id}`);
  await page.getByRole("button", { name: "Revisar envio", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Revisar envio de resposta", exact: true })).toBeFocused();
}
async function capture(page: Page, state: string) {
  const folder = resolve(root, ".impeccable/review/ticket-delivery"); await mkdir(folder, { recursive: true });
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(el => el.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: resolve(folder, `${state}-${size}-${theme}.png`), fullPage: true });
    }
  }
}
async function status(page: Page, api: string, message: string, state: string) {
  await expect.poll(async () => (await (await page.request.get(`${api}/messages/${message}/delivery`)).json()).state, { timeout: 45_000 }).toBe(state);
  await page.getByRole("button", { name: "Atualizar respostas", exact: true }).click();
  await page.getByRole("button", { name: "Atualizar estado do envio", exact: true }).click();
}

test("@delivery real TLS worker accepts exact saved text without private notes; keyboard review and responsive themes", async ({ page }) => {
  test.setTimeout(90_000);
  const body = "E2E-SMTP-ACCEPTED <script>window.injected=true</script>\n" + "x".repeat(200);
  const item = await setup(page, body);
  await review(page, item.id);
  await page.getByLabel("Nota interna", { exact: true }).fill("PRIVATE-NOTE-MUST-NEVER-BE-SENT");
  await expect(deliveryReview(page)).toContainText(body);
  await expect(deliveryReview(page)).toContainText("support@example.invalid");
  await expect(deliveryReview(page)).toContainText("ticket-requester@example.invalid");
  await expect(deliveryReview(page)).not.toContainText("PRIVATE-NOTE");
  await capture(page, "review");
  await page.getByRole("button", { name: "Confirmar envio", exact: true }).focus(); await page.keyboard.press("Enter");
  await status(page, item.api, item.messageId, "accepted");
  await expect(page.getByText("Aceito pelo servidor de e-mail", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Nota interna", { exact: true })).toHaveValue("PRIVATE-NOTE-MUST-NEVER-BE-SENT");
  expect(await page.evaluate(() => "injected" in window)).toBe(false);
  const messages = (await readFile(process.env.ALTVIA_E2E_SMTP_CAPTURE!, "utf8")).trim().split("\n").map(line => JSON.parse(line));
  const sent = messages.find(item => item.body.includes("E2E-SMTP-ACCEPTED"));
  expect(sent).toBeTruthy(); expect(sent.body).not.toContain("PRIVATE-NOTE");
  expect(sent.body).toContain("Content-Type: text/plain");
  const encoded = sent.body.split("\r\n\r\n").slice(1).join("\r\n\r\n").replace(/=\r\n/g, "").replace(/=([0-9A-F]{2})/g, (_: string, hex: string) => String.fromCharCode(parseInt(hex, 16)));
  expect(Buffer.from(encoded, "binary").toString("utf8").replace(/\r\n/g, "\n").trimEnd()).toBe(body);
  expect(sent.envelope).toContain("mail FROM:<support@example.invalid>");
  await page.reload(); await expect(page.getByText("Aceito pelo servidor de e-mail", { exact: true })).toBeVisible();
  await capture(page, "accepted");
});

for (const [marker, state, label] of [["FAILED", "failed", "Envio falhou"], ["UNCERTAIN", "uncertain", "Resultado do envio incerto"]]) test(`@delivery actual SMTP ${state} has no resend`, async ({ page }) => {
  test.setTimeout(70_000);
  const item = await setup(page, `E2E-SMTP-${marker}`); await review(page, item.id);
  await page.getByRole("button", { name: "Confirmar envio", exact: true }).click();
  await status(page, item.api, item.messageId, state);
  await expect(page.getByText(label, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Revisar envio", exact: true })).toHaveCount(0);
  const first = await (await page.request.get(`${item.api}/messages/${item.messageId}/delivery`)).json();
  await page.reload(); await page.getByRole("button", { name: "Atualizar respostas", exact: true }).click();
  const second = await (await page.request.get(`${item.api}/messages/${item.messageId}/delivery`)).json();
  expect(second.delivery_id).toBe(first.delivery_id); expect(second.attempts).toBe(1);
  await capture(page, state);
});

test("@delivery unverified and read-only never offer sending", async ({ page }) => {
  const unverified = await setup(page, "Unverified synthetic", false);
  await page.goto(`/service-desk/tickets/${unverified.id}`);
  await expect(page.getByText(/precisa de uma atestacao valida/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Revisar envio", exact: true })).toHaveCount(0);
  const verified = await setup(page, "Read only synthetic");
  await login(page, "READER"); await page.goto(`/service-desk/tickets/${verified.id}`);
  await expect(page.getByText("Sua conta pode consultar respostas, mas nao enviar neste chamado.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Revisar envio", exact: true })).toHaveCount(0);
});

for (const committed of [false, true]) test(`@delivery HTTP lost result ${committed} replays exact original reviewed intent`, async ({ page }) => {
  test.setTimeout(70_000);
  const item = await setup(page, "Original frozen review"); await review(page, item.id);
  let original: unknown, attempts = 0;
  await page.route(`**${item.api}/messages/${item.messageId}/delivery`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    const req = route.request(); const value = { body: req.postData(), key: req.headers()["idempotency-key"], version: req.headers()["if-match"] };
    if (++attempts === 1) { original = value; if (committed) await route.fetch(); await route.abort("failed"); }
    else { expect(value).toEqual(original); await route.continue(); }
  });
  await page.getByRole("button", { name: "Confirmar envio", exact: true }).click();
  const verify = page.getByRole("button", { name: "Verificar solicitacao de envio", exact: true });
  await expect(verify).toBeVisible();
  await page.route(`**${item.api}`, route => route.abort("failed"));
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(deliveryReview(page)).toContainText("Original frozen review");
  await page.unroute(`**${item.api}`);
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(deliveryReview(page)).toContainText("Original frozen review");
  await verify.click(); await expect(deliveryReview(page)).toHaveCount(0);
  await status(page, item.api, item.messageId, "accepted"); expect(attempts).toBe(2);
});

for (const code of [401, 403]) test(`@delivery session boundary ${code} clears private review`, async ({ page }) => {
  const item = await setup(page, "Private retained delivery review"); await review(page, item.id);
  if (code === 401) await page.context().clearCookies();
  else await page.route(`**${item.api}/messages/${item.messageId}/delivery`, route => route.request().method() === "POST" ? route.continue({ headers: { ...route.request().headers(), "x-csrf-token": "invalid-synthetic-csrf" } }) : route.continue());
  const refused = page.waitForResponse(response => response.url().endsWith(`/messages/${item.messageId}/delivery`) && response.request().method() === "POST");
  await page.getByRole("button", { name: "Confirmar envio", exact: true }).click();
  expect((await refused).status()).toBe(code);
  await expect(page.getByRole("heading", { name: "Verifique seu acesso", exact: true })).toBeVisible();
  await expect(deliveryReview(page)).toHaveCount(0);
});

for (const committed of [false, true]) test(`@delivery ownership loss ${committed} retains disabled original review and protected replay`, async ({ page, browser }) => {
  test.setTimeout(70_000);
  const context = await browser.newContext({ baseURL: origin, ignoreHTTPSErrors: true });
  try {
    const manager = await context.newPage();
    const item = await setup(manager, "Ownership retained saved body", true, true);
    await login(page, "READER"); await review(page, item.id);
    let attempts = 0, original: unknown;
    await page.route(`**${item.api}/messages/${item.messageId}/delivery`, async route => {
      if (route.request().method() !== "POST") return route.continue();
      const req = route.request(); const value = { body: req.postData(), key: req.headers()["idempotency-key"], version: req.headers()["if-match"] };
      if (++attempts === 1) { original = value; if (committed) await route.fetch(); await route.abort("failed"); }
      else { expect(value).toEqual(original); await route.continue(); }
    });
    await page.getByRole("button", { name: "Confirmar envio", exact: true }).click();
    const verify = page.getByRole("button", { name: "Verificar solicitacao de envio", exact: true }); await expect(verify).toBeVisible();
    expect((await manager.request.patch(item.api, { headers: headers(item.csrf, item.version + Number(committed)), data: { assignee_id: null } })).status()).toBe(200);
    const denied = page.waitForResponse(r => r.url().endsWith(`/messages/${item.messageId}/delivery`) && r.request().method() === "POST");
    await verify.click(); expect((await denied).status()).toBe(403);
    await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
    await expect(deliveryReview(page)).toContainText("Ownership retained saved body");
    await expect(page.getByRole("button", { name: "Confirmar envio", exact: true })).toBeDisabled();
    if (committed) await capture(page, "ownership-retained");
    expect((await manager.request.patch(item.api, { headers: headers(item.csrf, item.version + Number(committed) + 1), data: { assignee_id: process.env.ALTVIA_E2E_NOTE_READER_ID } })).status()).toBe(200);
    await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
    const replay = page.waitForResponse(r => r.url().endsWith(`/messages/${item.messageId}/delivery`) && r.request().method() === "POST");
    await verify.click(); expect((await replay).status()).toBe(committed ? 200 : 409);
    if (committed) await expect(deliveryReview(page)).toHaveCount(0);
    else { await expect(deliveryReview(page)).toContainText("Ownership retained saved body"); await page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true }).click(); await expect(deliveryReview(page)).toHaveCount(0); }
    expect(attempts).toBe(3);
    const output = await manager.request.get(`${item.api}/messages/${item.messageId}/delivery`); expect(output.status()).toBe(committed ? 200 : 404);
  } finally { await context.close(); }
});

test("@delivery acknowledged result survives failed authoritative read without another POST", async ({ page }) => {
  test.setTimeout(70_000);
  const item = await setup(page, "Acknowledged original review"); await review(page, item.id);
  let posts = 0, refuseReads = true;
  await page.route(`**${item.api}/messages/${item.messageId}/delivery`, async route => {
    if (route.request().method() === "POST") { posts++; return route.continue(); }
    if (refuseReads) return route.abort("failed");
    return route.continue();
  });
  await page.getByRole("button", { name: "Confirmar envio", exact: true }).click();
  await expect(page.getByText("Solicitacao de envio registrada. Atualize o chamado para consultar o estado confirmado.")).toBeVisible();
  const responseRow = page.getByRole("list", { name: "Rascunhos de resposta", exact: true }).getByRole("listitem");
  await expect(responseRow).toContainText("Solicitacao registrada; estado do envio aguardando confirmacao.");
  await expect(responseRow).not.toContainText("Rascunho - nao enviado");
  await expect(deliveryReview(page)).toContainText("Acknowledged original review");
  await expect(page.getByRole("button", { name: "Confirmar envio", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(deliveryReview(page)).toBeVisible(); expect(posts).toBe(1);
  await capture(page, "acknowledged-read-failure");
  refuseReads = false; await page.getByRole("button", { name: "Confirmar estado deste envio", exact: true }).click();
  await expect(deliveryReview(page)).toHaveCount(0); expect(posts).toBe(1);
  await status(page, item.api, item.messageId, "accepted");
});
