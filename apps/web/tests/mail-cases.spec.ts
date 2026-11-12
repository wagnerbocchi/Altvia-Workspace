import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const origin = "https://127.0.0.1:3443";
function fixture(options: object = {}) {
  return JSON.parse(execFileSync(resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"), ["scripts/browser_incoming_fixture.py"], { cwd: root, env: process.env, input: JSON.stringify(options), encoding: "utf8" }) || "null");
}
async function login(page: Page, kind = "AUTHOR") {
  await page.context().addCookies([{ name: "__Host-altvia_session", value: process.env[`ALTVIA_E2E_NOTE_${kind}_SESSION`]!, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const me = await page.request.get("/api/v1/auth/me"); expect(me.status()).toBe(200); return (await me.json()).csrf_token as string;
}
const headers = (csrf: string, version: number) => ({ Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${version}"`, "Idempotency-Key": crypto.randomUUID() });
const conversation = (page: Page) => page.getByRole("list", { name: "Conversa do chamado", exact: true });
async function reviewCreate(page: Page, caseId: string) {
  await page.goto(`/service-desk/mail-cases/${caseId}`);
  await page.getByLabel("Assunto do novo chamado", { exact: true }).fill("Inbound synthetic reviewed request");
  await expect(page.getByRole("button", { name: "Revisar criacao", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Revisar criacao", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Revisar inclusao da mensagem", exact: true })).toBeFocused();
}
async function create(page: Page, caseId: string) {
  await reviewCreate(page, caseId);
  await page.getByRole("button", { name: "Confirmar criacao", exact: true }).click();
  const link = page.getByRole("link", { name: "Abrir chamado confirmado", exact: true }); await expect(link).toBeVisible();
  return (await link.getAttribute("href"))!.split("/").at(-1)!;
}
async function capture(page: Page, state: string) {
  const folder = resolve(root, ".impeccable/review/mail-cases"); await mkdir(folder, { recursive: true });
  await expect(page.getByRole("status").filter({ hasText: /^Carregando|^Confirmando/ })).toHaveCount(0);
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(el => el.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      await expect(page.locator("html")).toHaveCSS("color-scheme", theme);
      await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); document.querySelectorAll(".incoming-text").forEach(element => { element.scrollTop = 0; }); scrollTo(0, 0); });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (state === "empty" && width === 390) {
        const gap = await page.evaluate(() => document.getElementById("mail-list-heading")!.getBoundingClientRect().top - document.querySelector(".mail-case-toolbar")!.getBoundingClientRect().bottom);
        expect(gap).toBeGreaterThanOrEqual(24);
      }
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: resolve(folder, `${state}-${size}-${theme}.png`), fullPage: true });
      const metrics = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, top: scrollY, height: document.documentElement.scrollHeight, theme: document.documentElement.classList.contains("dark") ? "dark" : "light", elements: [...document.querySelectorAll("h1,h2,.incoming-text,.incoming-text p,.button,.mail-case-toolbar")].map(element => { const style = getComputedStyle(element); const rect = element.getBoundingClientRect(); return { tag: element.tagName, className: element.className, role: element.getAttribute("role"), fontSize: style.fontSize, lineHeight: style.lineHeight, color: style.color, background: style.backgroundColor, padding: style.padding, width: rect.width, height: rect.height, top: rect.top, bottom: rect.bottom, scrollHeight: element.scrollHeight, overflow: style.overflow }; }) }));
      await writeFile(resolve(folder, `${state}-${size}-${theme}.json`), JSON.stringify(metrics, null, 2));
    }
  }
}
test("@incoming real attested case creates exact immutable incoming conversation", async ({ page }) => {
  test.setTimeout(90_000);
  const item = fixture(); await login(page);
  await page.goto(`/service-desk/mail-cases/${item.case_id}`);
  await expect(page.getByRole("heading", { name: "Mensagem recebida", exact: true })).toBeVisible();
  await expect(page.getByText(item.body, { exact: true })).toBeVisible();
  await page.getByLabel("Assunto do novo chamado", { exact: true }).fill("Inbound synthetic reviewed request");
  await page.getByRole("button", { name: "Revisar criacao", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar criacao", exact: true }).click();
  await expect(page.getByRole("link", { name: "Abrir chamado confirmado", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Abrir chamado confirmado", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Conversa", exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Conversa do chamado", exact: true })).toContainText(item.body);
  expect(await page.evaluate(() => "injected" in window)).toBe(false);
  await capture(page, "conversation");
  await page.goto(`/service-desk/mail-cases/${item.case_id}`);
  await expect(page.getByRole("link", { name: "Abrir chamado confirmado", exact: true })).toBeVisible();
  await page.reload(); await expect(page.getByRole("link", { name: "Abrir chamado confirmado", exact: true })).toBeVisible();
  await capture(page, "confirmed");
});

test("@incoming long escaped content and original subject remain whole with keyboard review", async ({ page }) => {
  test.setTimeout(90_000);
  const item = fixture({ subject: "Original " + "s".repeat(900), body: "<script>window.injected=true</script>\n" + "Long received line & <b>plain text</b>\n".repeat(1450) });
  await login(page); await page.goto(`/service-desk/mail-cases/${item.case_id}`);
  await expect(page.getByText(item.subject, { exact: true })).toBeVisible();
  const text = page.getByRole("region", { name: "Texto recebido", exact: true });
  expect(await text.textContent()).toBe(item.body);
  await text.focus(); await page.keyboard.press("End"); await page.keyboard.press("PageDown");
  await expect.poll(() => text.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Revisar criacao", exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("1 a 300");
  await capture(page, "long-text");
  await page.getByLabel("Assunto do novo chamado", { exact: true }).fill("Inbound synthetic deliberate short subject");
  await page.getByRole("button", { name: "Revisar criacao", exact: true }).focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Revisar inclusao da mensagem", exact: true })).toBeFocused();
  await capture(page, "review");
  await page.getByRole("button", { name: "Confirmar criacao", exact: true }).click();
  await page.getByRole("link", { name: "Abrir chamado confirmado", exact: true }).click();
  expect(await conversation(page).getByRole("region").textContent()).toBe(item.body);
  expect(await page.evaluate(() => "injected" in window)).toBe(false);
});

test("@incoming readonly hidden filtered list and reload receipt need no writing choices", async ({ page, browser }) => {
  test.setTimeout(90_000);
  const item = fixture(); await login(page, "VIEWER");
  const choices: string[] = []; page.on("request", req => { if (req.url().includes("ticket-choices") || req.url().includes("/categories")) choices.push(req.url()); });
  await page.goto(`/service-desk/mail-cases/${item.case_id}`);
  await expect(page.getByText(item.body, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Revisar criacao", exact: true })).toHaveCount(0);
  await expect(page.getByText("Nao ha acao disponivel", { exact: false })).toBeVisible();
  await capture(page, "readonly"); expect(choices).toEqual([]);
  await page.goto("/service-desk/mail-cases"); await expect(page.getByRole("list", { name: "Mensagens recebidas", exact: true })).toContainText(item.subject);
  await page.getByLabel("Situacao", { exact: true }).selectOption("revoked");
  await expect(page.getByText("Nenhuma mensagem disponivel", { exact: false })).toBeVisible(); await capture(page, "empty");
  const context = await browser.newContext({ baseURL: origin, ignoreHTTPSErrors: true });
  try {
    const manager = await context.newPage(); await login(manager); const ticket = await create(manager, item.case_id);
    await page.goto(`/service-desk/mail-cases/${item.case_id}`); await page.getByRole("link", { name: "Abrir chamado confirmado", exact: true }).click();
    await expect(conversation(page)).toContainText(item.body); await expect(page.getByLabel("Texto da resposta", { exact: true })).toHaveCount(0);
    fixture({ action: "revoke", case: item.case_id }); await page.reload(); await expect(conversation(page)).toContainText("registro historico foi preservado");
    await login(page, "CONFIG"); await page.goto(`/service-desk/mail-cases/${item.case_id}`);
    await expect(page.locator("main").getByRole("alert")).toContainText("nao esta disponivel"); await expect(page.getByText(item.body, { exact: true })).toHaveCount(0);
    await expect((await page.request.get(`/api/v1/tickets/${ticket}/conversation`)).status()).toBe(404);
  } finally { await context.close(); }
});

test("@incoming actual TLS first reply then correlated append and explicit reopen preserve notes and references", async ({ page }) => {
  test.setTimeout(90_000);
  fixture({ action: "policy" }); const item = fixture(); const csrf = await login(page);
  const ticket = await create(page, item.case_id); const api = `/api/v1/tickets/${ticket}`;
  expect((await page.request.post(api + "/notes", { headers: headers(csrf, 2), data: { body_text: "PRIVATE-PERSISTED-INCOMING-NOTE" } })).status()).toBe(201);
  fixture({ action: "attest", ticket });
  await page.getByRole("link", { name: "Abrir chamado confirmado", exact: true }).click();
  await page.getByLabel("Nota interna", { exact: true }).fill("PRIVATE-INCOMING-NOTE");
  await page.getByLabel("Texto da resposta", { exact: true }).fill("Inbound synthetic first reply");
  await page.getByRole("button", { name: "Revisar rascunho", exact: true }).click(); await page.getByRole("button", { name: "Salvar rascunho", exact: true }).click();
  await page.getByRole("button", { name: "Revisar envio", exact: true }).click(); await page.getByRole("button", { name: "Confirmar envio", exact: true }).click();
  const messages = (await (await page.request.get(api + "/messages")).json()).items;
  await expect.poll(async () => (await (await page.request.get(`${api}/messages/${messages[0].id}/delivery`)).json()).state, { timeout: 45000 }).toBe("accepted");
  const sent = (await readFile(process.env.ALTVIA_E2E_SMTP_CAPTURE!, "utf8")).trim().split("\n").map(line => JSON.parse(line)).find(row => row.body.includes("Inbound synthetic first reply"));
  expect(sent.body).toContain(`In-Reply-To: ${item.message_id}`); expect(sent.body).toContain(`References: ${item.message_id}`); expect(sent.body).not.toContain("PRIVATE-INCOMING-NOTE");
  const reply = fixture({ references: item.message_id, subject: "Reply synthetic", body: "Actual attested incoming reply" });
  await page.goto(`/service-desk/mail-cases/${reply.case_id}`); await page.getByRole("button", { name: "Revisar inclusao", exact: true }).click(); await page.getByRole("button", { name: "Confirmar inclusao", exact: true }).click(); await page.getByRole("link", { name: "Abrir chamado confirmado", exact: true }).click();
  await expect(conversation(page).getByRole("listitem")).toHaveCount(3);
  await expect(conversation(page)).not.toContainText("PRIVATE-PERSISTED-INCOMING-NOTE");
  await expect(page.getByRole("list", { name: "Notas internas", exact: true })).toContainText("PRIVATE-PERSISTED-INCOMING-NOTE");
  await capture(page, "conversation-mixed");
  let row = await (await page.request.get(api)).json();
  for (const target_status of ["open", "resolved", "closed"]) { expect((await page.request.post(api + "/transitions", { headers: headers(csrf, row.version), data: { target_status, reason: "Synthetic explicit lifecycle" } })).status()).toBe(200); row = await (await page.request.get(api)).json(); }
  const closedReply = fixture({ references: item.message_id, subject: "Reopen synthetic", body: "Attested reopening request" });
  await page.goto(`/service-desk/mail-cases/${closedReply.case_id}`); await page.getByRole("button", { name: "Revisar inclusao", exact: true }).click(); await expect(page.locator("main").getByRole("alert")).toContainText("Escolha reabrir");
  await page.getByLabel("Reabrir chamado ao incluir esta mensagem", { exact: true }).check(); await page.getByLabel("Motivo da reabertura", { exact: true }).fill("Reviewed synthetic reopening reason");
  await page.getByRole("button", { name: "Revisar inclusao", exact: true }).click(); await capture(page, "reopen-review"); await page.getByRole("button", { name: "Confirmar inclusao", exact: true }).click(); await page.getByRole("link", { name: "Abrir chamado confirmado", exact: true }).click();
  await expect(conversation(page).getByRole("listitem")).toHaveCount(4); expect((await (await page.request.get(api)).json()).status).toBe("open");
  await page.reload(); await expect(conversation(page)).toContainText("Attested reopening request");
});

for (const committed of [false, true]) test(`@incoming uncertain ${committed ? "committed" : "uncommitted"} creation retains exact original intent`, async ({ page }) => {
  test.setTimeout(90000); const item = fixture({ missing_id: true, subject: "" }); await login(page); await reviewCreate(page, item.case_id);
  let attempts = 0; let original: unknown;
  await page.route(`**/api/v1/mail-cases/${item.case_id}/promotion`, async route => {
    const request = route.request(); const intent = { body: request.postData(), key: request.headers()["idempotency-key"], version: request.headers()["if-match"] };
    if (++attempts === 1) { original = intent; if (committed) await route.fetch(); return route.abort("failed"); }
    expect(intent).toEqual(original); return route.continue();
  });
  await page.getByRole("button", { name: "Confirmar criacao", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar inclusao original", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Atualizar mensagem", exact: true }).click();
  await expect(page.getByRole("button", { name: "Confirmar criacao", exact: true })).toBeDisabled();
  await expect(page.getByRole("link", { name: "Abrir chamado confirmado", exact: true })).toHaveCount(0);
  if (committed) await capture(page, "uncertain");
  await page.getByRole("button", { name: "Verificar inclusao original", exact: true }).click();
  await expect(page.getByRole("link", { name: "Abrir chamado confirmado", exact: true })).toBeVisible(); expect(attempts).toBe(2);
});

test("@incoming acknowledged receipt reads single incoming beyond first conversation page without repost", async ({ page }) => {
  test.setTimeout(90000); const item = fixture(); const csrf = await login(page);
  const ticket = await create(page, item.case_id);
  fixture({ action: "attest", ticket });
  for (let index = 0; index < 10; index++) {
    const row = await (await page.request.get(`/api/v1/tickets/${ticket}`)).json();
    expect((await page.request.post(`/api/v1/tickets/${ticket}/messages`, { headers: headers(csrf, row.version), data: { body_text: `Earlier public draft ${index}` } })).status()).toBe(201);
  }
  const pending = fixture({ references: item.message_id, body: "Incoming beyond page one" });
  await page.goto(`/service-desk/mail-cases/${pending.case_id}`);
  await page.getByRole("button", { name: "Revisar inclusao", exact: true }).click();
  let posts = 0; let refuse = true; let receipt: { ticket_id: string; incoming_message_id: string };
  await page.route(`**/api/v1/mail-cases/${pending.case_id}/promotion`, async route => { posts++; const result = await route.fetch(); receipt = await result.json(); await route.fulfill({ response: result }); });
  await page.route("**/api/v1/tickets/*/incoming-messages/*", route => refuse ? route.abort("failed") : route.continue());
  await page.getByRole("button", { name: "Confirmar inclusao", exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("ainda nao foi possivel ler"); await expect(page.getByRole("link", { name: "Abrir chamado confirmado", exact: true })).toHaveCount(0);
  refuse = false; await page.getByRole("button", { name: "Tentar carregar novamente", exact: true }).click(); await page.getByRole("link", { name: "Abrir chamado confirmado", exact: true }).click();
  await expect(conversation(page).getByRole("listitem")).toHaveCount(10); expect(posts).toBe(1);
  await expect(conversation(page)).not.toContainText(pending.body);
  expect((await page.request.get(`/api/v1/tickets/${ticket}/incoming-messages/${receipt!.incoming_message_id}`)).status()).toBe(200);
  await page.getByRole("button", { name: "Proximas mensagens", exact: true }).click(); await expect(conversation(page)).toContainText(pending.body);
});

for (const committed of [false, true]) test(`@incoming uncertain append retains target version through actual ownership loss ${committed}`, async ({ page, browser }) => {
  test.setTimeout(90000);
  const context = await browser.newContext({ baseURL: origin, ignoreHTTPSErrors: true });
  try {
    const manager = await context.newPage(); const csrf = await login(manager); const item = fixture(); const ticket = await create(manager, item.case_id); const api = `/api/v1/tickets/${ticket}`;
    expect((await manager.request.patch(api, { headers: headers(csrf, 2), data: { assignee_id: process.env.ALTVIA_E2E_NOTE_READER_ID } })).status()).toBe(200);
    fixture({ action: "attest", ticket }); const reply = fixture({ references: item.message_id, body: "Original scoped reply intent" });
    await login(page, "READER"); await page.goto(`/service-desk/mail-cases/${reply.case_id}`); await page.getByRole("button", { name: "Revisar inclusao", exact: true }).click();
    let attempts = 0; let original: unknown;
    await page.route(`**/api/v1/mail-cases/${reply.case_id}/promotion`, async route => { const request = route.request(); const intent = { body: request.postData(), key: request.headers()["idempotency-key"], version: request.headers()["if-match"] }; if (++attempts === 1) { original = intent; if (committed) await route.fetch(); return route.abort("failed"); } expect(intent).toEqual(original); return route.continue(); });
    await page.getByRole("button", { name: "Confirmar inclusao", exact: true }).click();
    const verify = page.getByRole("button", { name: "Verificar inclusao original", exact: true }); await expect(verify).toBeVisible();
    expect((await manager.request.patch(api, { headers: headers(csrf, 3 + Number(committed)), data: { assignee_id: null } })).status()).toBe(200);
    const denied = page.waitForResponse(r => r.url().endsWith(`/mail-cases/${reply.case_id}/promotion`) && r.request().method() === "POST"); await verify.click(); expect((await denied).status()).toBe(403);
    await page.getByRole("button", { name: "Atualizar mensagem", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Revisar inclusao da mensagem", exact: true })).toBeVisible(); await expect(page.getByRole("button", { name: "Confirmar inclusao", exact: true })).toBeDisabled();
    expect((await manager.request.patch(api, { headers: headers(csrf, 4 + Number(committed)), data: { assignee_id: process.env.ALTVIA_E2E_NOTE_READER_ID } })).status()).toBe(200);
    const replay = page.waitForResponse(r => r.url().endsWith(`/mail-cases/${reply.case_id}/promotion`) && r.request().method() === "POST"); await verify.click(); expect((await replay).status()).toBe(committed ? 200 : 409);
    if (committed) await expect(page.getByRole("link", { name: "Abrir chamado confirmado", exact: true })).toBeVisible();
    else { await page.getByRole("button", { name: "Recarregar e descartar revisao", exact: true }).click(); await expect(page.getByRole("heading", { name: "Revisar inclusao da mensagem", exact: true })).toHaveCount(0); }
    expect(attempts).toBe(3);
  } finally { await context.close(); }
});

for (const loss of ["session", "csrf"]) test(`@incoming real ${loss} loss clears original private review`, async ({ page }) => {
  const item = fixture(); await login(page); await reviewCreate(page, item.case_id);
  if (loss === "session") await page.context().clearCookies();
  else await page.route(`**/api/v1/mail-cases/${item.case_id}/promotion`, route => route.continue({ headers: { ...route.request().headers(), "x-csrf-token": "invalid-synthetic-csrf" } }));
  await page.getByRole("button", { name: "Confirmar criacao", exact: true }).click();
  await expect(page.getByRole("heading", { name: loss === "session" ? "Acesse seu workspace" : "Verifique seu acesso", exact: true })).toBeVisible();
  await expect(page.getByText(item.body, { exact: true })).toHaveCount(0);
});

test("@incoming ticket-wide refresh observes external incoming and attestation invalidation", async ({ page }) => {
  const item = fixture(); const csrf = await login(page); const ticket = await create(page, item.case_id);
  fixture({ action: "attest", ticket }); await page.getByRole("link", { name: "Abrir chamado confirmado", exact: true }).click();
  await expect(conversation(page).getByRole("listitem")).toHaveCount(1);
  const reply = fixture({ references: item.message_id, body: "External incoming refreshed through ticket owner" });
  expect((await page.request.post(`/api/v1/mail-cases/${reply.case_id}/promotion`, { headers: headers(csrf, 1), data: { action: "append", ticket_id: ticket, ticket_version: 2, reopen: false } })).status()).toBe(201);
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(conversation(page)).toContainText(reply.body);
  fixture({ action: "revoke", case: item.case_id });
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(conversation(page)).toContainText("registro historico foi preservado");
});
