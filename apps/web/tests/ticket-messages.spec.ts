import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const origin = "https://127.0.0.1:3443";
const queue = process.env.ALTVIA_E2E_NOTE_QUEUE_ID!;
const client = process.env.ALTVIA_E2E_TICKET_CLIENT_ID!;
const requester = process.env.ALTVIA_E2E_TICKET_REQUESTER_ID!;
async function login(page: Page, kind = "AUTHOR") {
  const token = process.env[`ALTVIA_E2E_NOTE_${kind}_SESSION`];
  if (!token) throw Error("Guarded draft session required");
  await page.context().addCookies([{ name: "__Host-altvia_session", value: token, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const result = await page.request.get("/api/v1/auth/me");
  expect(result.status()).toBe(200);
  return (await result.json()).csrf_token as string;
}
const headers = (csrf: string, version = 1) => ({ Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${version}"`, "Idempotency-Key": crypto.randomUUID() });
async function ticket(page: Page, csrf: string) {
  const result = await page.request.post("/api/v1/tickets", { headers: headers(csrf), data: { queue_id: queue, client_id: client, requester_id: requester, subject: `Respostas ${crypto.randomUUID()}`, priority: "medium" } });
  expect(result.status()).toBe(201);
  return (await result.json()).ticket_id as string;
}
const list = (page: Page) => page.getByRole("list", { name: "Rascunhos de resposta", exact: true });
const form = (page: Page) => page.getByRole("region", { name: "Preparar resposta", exact: true });
async function review(page: Page, body: string) {
  await page.getByLabel("Texto da resposta", { exact: true }).fill(body);
  await page.getByRole("button", { name: "Revisar rascunho", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Revisar rascunho de resposta", exact: true })).toBeFocused();
}
async function capture(page: Page, state: string) {
  const root = fileURLToPath(new URL("../../../.impeccable/review/ticket-messages/", import.meta.url));
  await mkdir(root, { recursive: true });
  await expect(page.getByRole("status").filter({ hasText: /^Carregando/ })).toHaveCount(0);
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(element => element.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      await expect(page.locator("html")).toHaveCSS("color-scheme", theme);
      await page.evaluate(() => scrollTo(0, 0));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: `${root}/${state}-${size}-${theme}.png`, fullPage: true });
    }
  }
}

for (const committed of [false, true]) test(`@messages reassignment denial ${committed} preserves original intent for restored authority`, async ({ page, browser }) => {
  const manager = await browser.newContext({ baseURL: origin, ignoreHTTPSErrors: true });
  try {
    const managerPage = await manager.newPage();
    const managerCsrf = await login(managerPage);
    const id = await ticket(managerPage, managerCsrf);
    const api = `/api/v1/tickets/${id}`;
    expect((await managerPage.request.patch(api, { headers: headers(managerCsrf), data: { assignee_id: process.env.ALTVIA_E2E_NOTE_READER_ID! } })).status()).toBe(200);
    await login(page, "READER");
    await page.goto(`/service-desk/tickets/${id}`);
    await review(page, "Resposta retida apos reatribuicao");
    let original: { body: string | null; key: string | undefined; version: string | undefined } | undefined;
    let attempts = 0;
    await page.route(`**${api}/messages`, async route => {
      if (route.request().method() !== "POST") return route.continue();
      const request = route.request();
      const intent = { body: request.postData(), key: request.headers()["idempotency-key"], version: request.headers()["if-match"] };
      attempts++;
      if (attempts === 1) { original = intent; if (committed) await route.fetch(); await route.abort("failed"); }
      else { expect(intent).toEqual(original); await route.continue(); }
    });
    await page.getByRole("button", { name: "Salvar rascunho", exact: true }).click();
    const verify = page.getByRole("button", { name: "Verificar rascunho", exact: true });
    await expect(verify).toBeVisible();
    expect((await managerPage.request.patch(api, { headers: headers(managerCsrf, committed ? 3 : 2), data: { assignee_id: null } })).status()).toBe(200);
    const denied = page.waitForResponse(response => response.url().endsWith(api + "/messages") && response.request().method() === "POST");
    await verify.click();
    expect((await denied).status()).toBe(403);
    await expect(form(page)).toContainText("Resposta retida apos reatribuicao");
    await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
    await expect(form(page)).toContainText("Resposta retida apos reatribuicao");
    await expect(page.getByRole("button", { name: "Salvar rascunho", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true })).toBeVisible();
    if (committed) await capture(page, "reassigned");
    expect(attempts).toBe(2);
    expect((await (await managerPage.request.get(api + "/messages")).json()).items).toHaveLength(committed ? 1 : 0);
    expect((await managerPage.request.patch(api, { headers: headers(managerCsrf, committed ? 4 : 3), data: { assignee_id: process.env.ALTVIA_E2E_NOTE_READER_ID! } })).status()).toBe(200);
    await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
    const restored = page.waitForResponse(response => response.url().endsWith(api + "/messages") && response.request().method() === "POST");
    await verify.click();
    expect((await restored).status()).toBe(committed ? 200 : 409);
    if (!committed) {
      await expect(form(page)).toContainText("Resposta retida apos reatribuicao");
      await page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true }).click();
    }
    await expect(page.getByLabel("Texto da resposta", { exact: true })).toHaveValue("");
    await expect(page.getByRole("button", { name: "Revisar rascunho", exact: true })).toBeEnabled();
    expect(attempts).toBe(3);
    expect((await (await managerPage.request.get(api + "/messages")).json()).items).toHaveLength(committed ? 1 : 0);
  } finally { await manager.close(); }
});

for (const status of [401, 403]) test(`@messages real session boundary ${status} still removes private intent`, async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  await page.goto(`/service-desk/tickets/${id}`);
  await review(page, "Texto privado encerrado com a sessao");
  await page.route(`**/api/v1/tickets/${id}/messages`, route => route.request().method() === "POST"
    ? route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ code: status === 401 ? "unauthenticated" : "csrf_rejected" }) })
    : route.continue());
  await page.getByRole("button", { name: "Salvar rascunho", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Verifique seu acesso", exact: true })).toBeVisible();
  await expect(form(page)).toHaveCount(0);
  await expect(page.getByText("Texto privado encerrado com a sessao", { exact: true })).toHaveCount(0);
  expect((await (await page.request.get(`/api/v1/tickets/${id}/messages`)).json()).items).toEqual([]);
});

test("@messages real escaped draft requires keyboard review, persists and stays independent of notes", async ({ page }) => {
  test.setTimeout(60_000);
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  await page.goto(`/service-desk/tickets/${id}`);
  await page.getByLabel("Nota interna", { exact: true }).fill("Nota privada nao e resposta");
  await page.getByLabel("Texto da resposta", { exact: true }).fill("Resposta <script>window.injected = true</script>\nSegunda linha " + "x".repeat(100));
  await expect(list(page)).toHaveCount(0);
  await page.getByRole("button", { name: "Revisar rascunho", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Revisar rascunho de resposta", exact: true })).toBeFocused();
  await capture(page, "review");
  await expect(form(page)).not.toContainText("Nota privada nao e resposta");
  await page.getByRole("button", { name: "Voltar ao texto", exact: true }).click();
  await expect(page.getByLabel("Texto da resposta", { exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Revisar rascunho", exact: true }).click();
  await page.getByRole("button", { name: "Salvar rascunho", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(list(page)).toContainText("Resposta <script>window.injected = true</script>");
  await expect(list(page)).toContainText("Rascunho - nao enviado");
  await expect(page.getByLabel("Texto da resposta", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Nota interna", { exact: true })).toHaveValue("Nota privada nao e resposta");
  expect(await page.evaluate(() => "injected" in window)).toBe(false);
  await page.reload();
  await expect(list(page).getByRole("listitem")).toHaveCount(1);
  await capture(page, "saved");
  expect((await (await page.request.get(`/api/v1/tickets/${id}/notes`)).json()).items).toEqual([]);
});

for (const committed of [false, true]) test(`@messages uncertain append ${committed} keeps reviewed body version key through failed read and focus refresh`, async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  const api = `/api/v1/tickets/${id}`;
  await page.goto(`/service-desk/tickets/${id}`);
  await review(page, "Texto retido na recuperacao");
  let first = true;
  let original: { body: string | null; key: string | undefined; version: string | undefined } | undefined;
  await page.route(`**${api}/messages`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    const request = route.request();
    const intent = { body: request.postData(), key: request.headers()["idempotency-key"], version: request.headers()["if-match"] };
    if (first) { first = false; original = intent; if (committed) await route.fetch(); await route.abort("failed"); }
    else { expect(intent).toEqual(original); await route.continue(); }
  });
  await page.getByRole("button", { name: "Salvar rascunho", exact: true }).click();
  const verify = page.getByRole("button", { name: "Verificar rascunho", exact: true });
  await expect(verify).toBeVisible();
  await page.route(`**${api}`, route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "carregar os dados" })).toBeVisible();
  await expect(form(page)).toContainText("Texto retido na recuperacao");
  await expect(page.getByRole("button", { name: "Salvar rascunho", exact: true })).toBeDisabled();
  await page.unroute(`**${api}`);
  await page.evaluate(() => { window.dispatchEvent(new Event("blur")); window.dispatchEvent(new Event("focus")); document.dispatchEvent(new Event("visibilitychange")); });
  await verify.click();
  await expect(list(page).getByRole("listitem")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Revisar rascunho", exact: true })).toBeEnabled();
  expect((await (await page.request.get(api)).json()).version).toBe(2);
});

for (const failedRead of ["ticket", "receipt", "list"]) test(`@messages acknowledged draft stays locked through failed ${failedRead} authoritative read`, async ({ page }) => {
  test.setTimeout(60_000);
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  const api = `/api/v1/tickets/${id}`;
  await page.goto(`/service-desk/tickets/${id}`);
  await review(page, "Rascunho confirmado sem leitura");
  const pattern = failedRead === "ticket" ? `**${api}` : failedRead === "receipt" ? `**${api}/messages/*` : `**${api}/messages?*`;
  await page.route(pattern, route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Salvar rascunho", exact: true }).click();
  await expect(page.getByText("Rascunho salvo, nao enviado. Atualize o chamado antes de continuar.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Revisar rascunho", exact: true })).toBeDisabled();
  if (failedRead === "ticket") await capture(page, "refresh-error");
  await page.unroute(pattern);
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Revisar rascunho", exact: true })).toBeEnabled();
  await expect(list(page).getByRole("listitem")).toHaveCount(1);
  expect((await (await page.request.get(api)).json()).version).toBe(2);
});

test("@messages reviewed version survives authoritative refresh and explicit conflict discard", async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  const api = `/api/v1/tickets/${id}`;
  await page.goto(`/service-desk/tickets/${id}`);
  await review(page, "Resposta na versao um");
  expect((await page.request.patch(api, { headers: headers(csrf), data: { priority: "critical" } })).status()).toBe(200);
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Salvar rascunho", exact: true })).toBeEnabled();
  const sent = page.waitForRequest(request => request.url().endsWith(api + "/messages") && request.method() === "POST");
  await page.getByRole("button", { name: "Salvar rascunho", exact: true }).click();
  expect((await sent).headers()["if-match"]).toBe('"1"');
  await page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true }).click();
  await expect(page.getByLabel("Texto da resposta", { exact: true })).toHaveValue("");
  expect((await (await page.request.get(api + "/messages")).json()).items).toEqual([]);
});

test("@messages no note grant still allows public drafts without a private read", async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  expect((await page.request.post(`/api/v1/tickets/${id}/notes`, { headers: headers(csrf), data: { body_text: "Segredo nao compartilhado" } })).status()).toBe(201);
  await login(page, "NONE");
  const reads: string[] = [];
  page.on("request", request => { if (request.url().includes(`/tickets/${id}/notes`)) reads.push(request.url()); });
  await page.goto(`/service-desk/tickets/${id}`);
  await review(page, "Resposta compartilhada sem notas");
  await page.getByRole("button", { name: "Salvar rascunho", exact: true }).click();
  await expect(list(page)).toContainText("Resposta compartilhada sem notas");
  await expect(page.getByRole("heading", { name: "Notas internas", exact: true })).toHaveCount(0);
  await expect(page.getByText("Segredo nao compartilhado", { exact: true })).toHaveCount(0);
  expect(reads).toEqual([]);
});

test("@messages viewer and unassigned note reader can read drafts but cannot compose", async ({ page }) => {
  test.setTimeout(60_000);
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  expect((await page.request.post(`/api/v1/tickets/${id}/messages`, { headers: headers(csrf), data: { body_text: "Rascunho compartilhado" } })).status()).toBe(201);
  for (const kind of ["VIEWER", "READER"]) {
    await login(page, kind);
    await page.goto(`/service-desk/tickets/${id}`);
    await expect(list(page)).toContainText("Rascunho compartilhado");
    await expect(page.getByRole("heading", { name: "Preparar resposta", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Salvar rascunho", exact: true })).toHaveCount(0);
    if (kind === "VIEWER") await capture(page, "read-only");
  }
});

test("@messages chronological paging and failed list recovery use persisted pages", async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  for (let index = 0; index < 11; index++) expect((await page.request.post(`/api/v1/tickets/${id}/messages`, { headers: headers(csrf, index + 1), data: { body_text: `Resposta ordenada ${index}` } })).status()).toBe(201);
  await page.goto(`/service-desk/tickets/${id}`);
  await expect(list(page).getByRole("listitem")).toHaveCount(10);
  await expect(list(page).getByRole("listitem").first()).toContainText("Resposta ordenada 0");
  await page.getByRole("button", { name: "Proximas respostas", exact: true }).click();
  await expect(list(page).getByRole("listitem")).toHaveCount(1);
  await expect(list(page)).toContainText("Resposta ordenada 10");
  await page.route(`**/api/v1/tickets/${id}/messages?*`, route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Atualizar respostas", exact: true }).click();
  const region = page.getByRole("region", { name: "Respostas", exact: true });
  await expect(region.getByRole("alert")).toBeVisible();
  await page.unroute(`**/api/v1/tickets/${id}/messages?*`);
  await region.getByRole("button", { name: "Tentar carregar novamente", exact: true }).click();
  await expect(list(page)).toContainText("Resposta ordenada 10");
  await page.getByRole("button", { name: "Respostas anteriores", exact: true }).click();
  await expect(list(page).getByRole("listitem")).toHaveCount(10);
});

test("@messages invalid empty and overlong text remains editable before review", async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  await page.goto(`/service-desk/tickets/${id}`);
  await page.getByRole("button", { name: "Revisar rascunho", exact: true }).click();
  await expect(form(page).getByRole("alert")).toHaveText("Use de 1 a 10000 caracteres, sem caracteres nulos.");
  await page.getByLabel("Texto da resposta", { exact: true }).fill("x".repeat(10001));
  await page.getByRole("button", { name: "Revisar rascunho", exact: true }).click();
  await expect(page.getByLabel("Texto da resposta", { exact: true })).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByRole("button", { name: "Salvar rascunho", exact: true })).toHaveCount(0);
  expect((await (await page.request.get(`/api/v1/tickets/${id}/messages`)).json()).items).toEqual([]);
});
