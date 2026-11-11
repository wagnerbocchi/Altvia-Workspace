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
  if (!token) throw Error("Guarded note session required");
  await page.context().addCookies([{ name: "__Host-altvia_session", value: token, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const result = await page.request.get("/api/v1/auth/me");
  expect(result.status()).toBe(200);
  return (await result.json()).csrf_token as string;
}
const headers = (csrf: string, version = 1) => ({ Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${version}"`, "Idempotency-Key": crypto.randomUUID() });
async function ticket(page: Page, csrf: string) {
  const result = await page.request.post("/api/v1/tickets", { headers: headers(csrf), data: { queue_id: queue, client_id: client, requester_id: requester, subject: `Notas ${crypto.randomUUID()}`, priority: "medium" } });
  expect(result.status()).toBe(201);
  return (await result.json()).ticket_id as string;
}
async function capture(page: Page, state: string) {
  const root = fileURLToPath(new URL("../../../.impeccable/review/ticket-notes/", import.meta.url));
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

test("@notes author records a real private plain-text note and reader sees persisted order", async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  await page.goto(`/service-desk/tickets/${id}`);
  await page.getByLabel("Nota interna", { exact: true }).fill("Registro privado <script>texto literal</script>");
  await capture(page, "composition");
  await page.getByRole("button", { name: "Registrar nota interna", exact: true }).focus();
  await page.keyboard.press("Enter");
  const list = page.getByRole("list", { name: "Notas internas", exact: true });
  await expect(list).toContainText("Registro privado <script>texto literal</script>");
  await expect(page.getByLabel("Nota interna", { exact: true })).toHaveValue("");
  await page.reload();
  await expect(list).toContainText("Registro privado <script>texto literal</script>");
  await capture(page, "notes");
  await login(page, "READER"); await page.reload();
  await expect(list).toContainText("Registro privado <script>texto literal</script>");
  await expect(page.getByLabel("Nota interna", { exact: true })).toHaveCount(0);
});

for (const committed of [false, true]) test(`@notes uncertain append ${committed} keeps original body version key through failed read`, async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  const api = `/api/v1/tickets/${id}`;
  await page.goto(`/service-desk/tickets/${id}`);
  await page.getByLabel("Nota interna", { exact: true }).fill("Texto retido na recuperacao");
  let first = true;
  let original: { body: string | null; key: string | undefined; version: string | undefined } | undefined;
  await page.route(`**${api}/notes`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    const request = route.request();
    const intent = { body: request.postData(), key: request.headers()["idempotency-key"], version: request.headers()["if-match"] };
    if (first) { first = false; original = intent; if (committed) await route.fetch(); await route.abort("failed"); }
    else { expect(intent).toEqual(original); await route.continue(); }
  });
  await page.getByRole("button", { name: "Registrar nota interna", exact: true }).click();
  const verify = page.getByRole("button", { name: "Verificar nota interna", exact: true });
  await expect(verify).toBeVisible();
  await page.route(`**${api}`, route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(page.getByLabel("Nota interna", { exact: true })).toHaveValue("Texto retido na recuperacao");
  await expect(page.getByRole("button", { name: "Registrar nota interna", exact: true })).toBeDisabled();
  await page.unroute(`**${api}`);
  await verify.click();
  await expect(page.getByRole("list", { name: "Notas internas", exact: true }).getByRole("listitem")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Registrar nota interna", exact: true })).toBeEnabled();
});

test("@notes acknowledged append remains locked through failed authoritative refresh", async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  const api = `/api/v1/tickets/${id}`;
  await page.goto(`/service-desk/tickets/${id}`);
  await page.getByLabel("Nota interna", { exact: true }).fill("Nota confirmada sem leitura");
  await page.route(`**${api}`, route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Registrar nota interna", exact: true }).click();
  await expect(page.getByText("Nota registrada. Atualize o chamado antes de continuar.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Registrar nota interna", exact: true })).toBeDisabled();
  await capture(page, "refresh-error");
  await page.unroute(`**${api}`);
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Registrar nota interna", exact: true })).toBeEnabled();
  await expect(page.getByRole("list", { name: "Notas internas", exact: true }).getByRole("listitem")).toHaveCount(1);
  expect((await (await page.request.get(api)).json()).version).toBe(2);
});

test("@notes draft retains reviewed version across refetch and requires explicit conflict recovery", async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  const api = `/api/v1/tickets/${id}`;
  await page.goto(`/service-desk/tickets/${id}`);
  await page.getByLabel("Nota interna", { exact: true }).fill("Nota revisada na versao um");
  expect((await page.request.patch(api, { headers: headers(csrf), data: { priority: "critical" } })).status()).toBe(200);
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  const sent = page.waitForRequest(request => request.url().endsWith(api + "/notes") && request.method() === "POST");
  await page.getByRole("button", { name: "Registrar nota interna", exact: true }).click();
  expect((await sent).headers()["if-match"]).toBe('"1"');
  await page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true }).click();
  await expect(page.getByLabel("Nota interna", { exact: true })).toHaveValue("");
  expect((await (await page.request.get(api + "/notes")).json()).items).toEqual([]);
});

for (const kind of ["NONE", "VIEWER"]) test(`@notes ${kind} receives no private render request or activity`, async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  expect((await page.request.post(`/api/v1/tickets/${id}/notes`, { headers: headers(csrf), data: { body_text: "Segredo restrito" } })).status()).toBe(201);
  await login(page, kind);
  const reads: string[] = [];
  page.on("request", request => { if (request.url().includes(`/tickets/${id}/notes`)) reads.push(request.url()); });
  await page.goto(`/service-desk/tickets/${id}`);
  await expect(page.getByRole("heading", { name: "Dados do chamado", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Notas internas", exact: true })).toHaveCount(0);
  await expect(page.getByText("Segredo restrito", { exact: true })).toHaveCount(0);
  expect(reads).toEqual([]);
  expect((await (await page.request.get(`/api/v1/tickets/${id}/activity`)).json()).items.every((row: { event_type: string }) => row.event_type !== "ticket.note_added")).toBe(true);
});

test("@notes configuration manager explicitly reviews grants and viewer downgrade clears note access", async ({ page }) => {
  await login(page, "CONFIG");
  await page.goto(`/service-desk/queues/${queue}/members`);
  const member = page.getByRole("listitem").filter({ hasText: "Notas DELEGATE" });
  await member.getByRole("button", { name: "Alterar papel", exact: true }).click();
  await page.getByLabel("Acesso a notas internas", { exact: true }).selectOption("write");
  await capture(page, "grant");
  await page.getByRole("button", { name: "Salvar papel", exact: true }).click();
  await expect(member).toContainText("Leitura e escrita de notas");
  await member.getByRole("button", { name: "Alterar papel", exact: true }).click();
  await page.getByLabel("Novo papel", { exact: true }).selectOption("viewer");
  await expect(page.getByLabel("Acesso a notas internas", { exact: true })).toHaveValue("none");
  await page.getByRole("button", { name: "Salvar papel", exact: true }).click();
  await expect(member).toContainText("Sem acesso a notas");
  await page.getByRole("button", { name: "Adicionar membro", exact: true }).click();
  await page.getByLabel("E-mail da conta", { exact: true }).fill(process.env.ALTVIA_E2E_NOTE_DELEGATE_EMAIL!);
  await page.getByLabel("Papel na fila", { exact: true }).selectOption("agent");
  await page.getByLabel("Acesso a notas internas", { exact: true }).selectOption("read");
  await page.getByRole("button", { name: "Revisar acesso", exact: true }).click();
  await expect(page.getByRole("group", { name: "Confirmar papel na fila?", exact: true })).toContainText("Somente leitura de notas");
  await page.getByRole("button", { name: "Conceder acesso", exact: true }).click();
  await expect(member).toContainText("Somente leitura de notas");
});

test("@notes paging retains ordered persisted notes and read failures have recovery", async ({ page }) => {
  const csrf = await login(page);
  const id = await ticket(page, csrf);
  for (let index = 0; index < 11; index++) expect((await page.request.post(`/api/v1/tickets/${id}/notes`, { headers: headers(csrf, index + 1), data: { body_text: `Nota ordenada ${index}` } })).status()).toBe(201);
  await login(page, "READER");
  await page.goto(`/service-desk/tickets/${id}`);
  const list = page.getByRole("list", { name: "Notas internas", exact: true });
  await expect(list.getByRole("listitem")).toHaveCount(10);
  await expect(list.getByRole("listitem").first()).toContainText("Nota ordenada 0");
  await page.getByRole("button", { name: "Proximas notas", exact: true }).click();
  await expect(list.getByRole("listitem")).toHaveCount(1);
  await expect(list).toContainText("Nota ordenada 10");
  await page.route(`**/api/v1/tickets/${id}/notes?*`, route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Atualizar notas", exact: true }).click();
  await expect(page.getByRole("region", { name: "Notas internas", exact: true }).getByRole("alert")).toBeVisible();
  await page.unroute(`**/api/v1/tickets/${id}/notes?*`);
  await page.getByRole("region", { name: "Notas internas", exact: true }).getByRole("button", { name: "Tentar carregar novamente", exact: true }).click();
  await expect(list).toContainText("Nota ordenada 10");
});
