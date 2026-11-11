import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const origin = "https://127.0.0.1:3443";
const directory = "/service-desk/tickets";
const queue = process.env.ALTVIA_E2E_TICKET_QUEUE_ID!;
const client = process.env.ALTVIA_E2E_TICKET_CLIENT_ID!;
const requester = process.env.ALTVIA_E2E_TICKET_REQUESTER_ID!;
const agent = process.env.ALTVIA_E2E_TICKET_AGENT_ID!;

async function login(page: Page, kind = "MANAGER") {
  const token = process.env[`ALTVIA_E2E_TICKET_${kind}_SESSION`];
  if (!token) throw Error("Guarded ticket session required");
  await page.context().addCookies([{ name: "__Host-altvia_session", value: token, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const response = await page.request.get("/api/v1/auth/me");
  expect(response.status()).toBe(200);
  return (await response.json()).csrf_token as string;
}
const headers = (csrf: string, version = 1) => ({ Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${version}"`, "Idempotency-Key": crypto.randomUUID() });
async function create(page: Page, csrf: string, subject = `Chamado ${crypto.randomUUID()}`) {
  const response = await page.request.post("/api/v1/tickets", { headers: headers(csrf), data: { queue_id: queue, client_id: client, requester_id: requester, subject, priority: "high" } });
  expect(response.status()).toBe(201);
  return (await response.json()).ticket_id as string;
}
async function fillCreation(page: Page, captureForm = false) {
  await page.goto(directory + "/new");
  await page.getByLabel("Fila do chamado", { exact: true }).selectOption(queue);
  await page.getByLabel("Cliente do chamado", { exact: true }).selectOption(client);
  const field = page.getByLabel("Solicitante", { exact: true });
  await expect(field).toBeEnabled();
  if (await field.locator(`option[value="${requester}"]`).count() === 0) {
    await page.getByRole("button", { name: "Proximos solicitantes", exact: true }).click();
  }
  await field.selectOption(requester);
  await page.getByLabel("Assunto", { exact: true }).fill("Servidor <script>texto</script>");
  await page.getByLabel("Descricao", { exact: true }).fill("Conexao indisponivel <b>texto literal</b>");
  if (captureForm) await capture(page, "create");
  await page.getByRole("button", { name: "Revisar chamado", exact: true }).click();
}
async function capture(page: Page, name: string) {
  const root = fileURLToPath(new URL("../../../.impeccable/review/tickets/", import.meta.url));
  await mkdir(root, { recursive: true });
  await expect(page.getByRole("status").filter({ hasText: /^Carregando/ })).toHaveCount(0);
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(element => element.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      await expect(page.locator("html")).toHaveCSS("color-scheme", theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: `${root}/${name}-${size}-${theme}.png`, fullPage: true });
    }
  }
}

test("@tickets persisted manual create edit assignment and all state paths", async ({ page }) => {
  await login(page, "CONFIG");
  const api = `/api/v1/ticket-queues/${queue}`;
  await page.goto(`/service-desk/queues/${queue}`);
  await page.getByRole("button", { name: "Editar fluxo", exact: true }).click();
  await page.getByLabel("Permitir fechamento manual", { exact: true }).check();
  await page.getByLabel("Permitir reabertura", { exact: true }).check();
  await capture(page, "workflow");
  await page.getByRole("button", { name: "Salvar fluxo", exact: true }).click();
  await expect.poll(async () => (await (await page.request.get(api)).json()).allow_reopen).toBe(true);
  await login(page);
  await fillCreation(page, true);
  await expect(page.getByRole("region", { name: "Revisar chamado", exact: true }).getByText("Solicitante com identidade nao verificada.", { exact: true })).toBeVisible();
  await capture(page, "review");
  await page.getByRole("button", { name: "Criar chamado", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/service-desk\/tickets\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: "Servidor <script>texto</script>", exact: true })).toBeVisible();
  await expect(page.getByText("Conexao indisponivel <b>texto literal</b>", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Editar chamado", exact: true }).click();
  await page.getByLabel("Responsavel", { exact: true }).selectOption(agent);
  await page.getByLabel("Prioridade", { exact: true }).selectOption("critical");
  await capture(page, "edit");
  await page.getByRole("button", { name: "Salvar chamado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toBeEnabled();
  for (const status of ["open", "pending_customer", "open", "pending_third_party", "resolved", "closed", "open"]) {
    await page.getByLabel("Proximo estado", { exact: true }).selectOption(status);
    await page.getByLabel("Motivo", { exact: true }).fill("Motivo de validacao");
    await page.getByRole("button", { name: "Alterar estado", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "Alteracao confirmada." })).toBeVisible();
    await expect(page.getByLabel("Proximo estado", { exact: true })).toHaveValue("");
  }
  await page.reload();
  await expect(page.getByRole("list", { name: "Historico de estados", exact: true }).getByRole("listitem")).toHaveCount(8);
  await expect(page.getByText("Chamados AGENT", { exact: true })).toBeVisible();
  await capture(page, "detail");
  await page.getByRole("link", { name: "Voltar aos chamados", exact: true }).click();
  await page.getByLabel("Busca nos chamados", { exact: true }).fill("Servidor");
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
  await expect(page.getByRole("list", { name: "Chamados disponiveis", exact: true })).toContainText("Servidor <script>texto</script>");
  await capture(page, "inbox");
});

for (const committed of [false, true]) test(`@tickets uncertain create ${committed} retains original intent through failed choices`, async ({ page }) => {
  await login(page); await fillCreation(page);
  let first = true;
  let original: { body: string | null; key: string | undefined } | undefined;
  await page.route("**/api/v1/tickets", async route => {
    if (route.request().method() !== "POST") return route.continue();
    const intent = { body: route.request().postData(), key: route.request().headers()["idempotency-key"] };
    if (first) { first = false; original = intent; if (committed) await route.fetch(); await route.abort("failed"); }
    else { expect(intent).toEqual(original); await route.continue(); }
  });
  await page.getByRole("button", { name: "Criar chamado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar criacao", exact: true })).toBeVisible();
  await page.route("**/api/v1/ticket-choices/queues?*", route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Atualizar opcoes", exact: true }).click();
  await expect(page.getByRole("button", { name: "Criar chamado", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Verificar criacao", exact: true }).click();
  await expect(page).toHaveURL(/\/service-desk\/tickets\/[0-9a-f-]+$/);
});

for (const kind of ["claim", "transition"] as const) test(`@tickets uncertain ${kind} retains key version and body`, async ({ page }) => {
  const csrf = await login(page);
  const id = await create(page, csrf);
  const api = `/api/v1/tickets/${id}`;
  await page.goto(`${directory}/${id}`);
  let first = true;
  let original: { body: string | null; key: string | undefined; version: string | undefined } | undefined;
  await page.route(`**${api}/${kind === "claim" ? "claim" : "transitions"}`, async route => {
    const request = route.request();
    const intent = { body: request.postData(), key: request.headers()["idempotency-key"], version: request.headers()["if-match"] };
    if (first) { first = false; original = intent; await route.fetch(); await route.abort("failed"); }
    else { expect(intent).toEqual(original); await route.continue(); }
  });
  if (kind === "transition") await page.getByLabel("Proximo estado", { exact: true }).selectOption("open");
  await page.getByRole("button", { name: kind === "claim" ? "Assumir chamado" : "Alterar estado", exact: true }).click();
  const verify = page.getByRole("button", { name: kind === "claim" ? "Verificar atribuicao" : "Verificar mudanca de estado", exact: true });
  await expect(verify).toBeVisible();
  await page.route(`**${api}`, route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toBeDisabled();
  await page.unroute(`**${api}`);
  await verify.click();
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toBeEnabled();
  const value = await (await page.request.get(api)).json();
  expect(value.version).toBe(2);
});

test("@tickets confirmed receipt requires authoritative refresh and stale edit explicit review", async ({ page }) => {
  const csrf = await login(page);
  const id = await create(page, csrf);
  const api = `/api/v1/tickets/${id}`;
  await page.goto(`${directory}/${id}`);
  await expect(page.getByRole("button", { name: "Assumir chamado", exact: true })).toBeEnabled();
  await page.route(`**${api}`, route => route.request().method() === "GET" ? route.fulfill({ status: 503, body: "{}" }) : route.continue());
  await page.getByRole("button", { name: "Assumir chamado", exact: true }).click();
  await expect(page.getByText("Operacao confirmada. Atualize o chamado antes de continuar.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toBeDisabled();
  await capture(page, "refresh-error");
  await page.unroute(`**${api}`);
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await page.getByRole("button", { name: "Editar chamado", exact: true }).click();
  await page.getByLabel("Assunto", { exact: true }).fill("Edicao obsoleta");
  expect((await page.request.patch(api, { headers: headers(csrf, 2), data: { subject: "Edicao concorrente" } })).status()).toBe(200);
  await page.getByRole("button", { name: "Salvar chamado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Edicao concorrente", exact: true })).toBeVisible();
});

test("@tickets agent must claim viewer reads and configuration has no ticket grant", async ({ page }) => {
  const csrf = await login(page);
  const id = await create(page, csrf);
  await login(page, "AGENT");
  await page.goto(`${directory}/${id}`);
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Assumir chamado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Editar chamado", exact: true }).click();
  await expect(page.getByLabel("Responsavel", { exact: true })).toHaveCount(0);
  await login(page, "VIEWER"); await page.reload();
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Historico de estados", exact: true })).toBeVisible();
  await login(page, "CONFIG"); await page.reload();
  await expect(page.getByText("Este chamado nao esta disponivel para sua conta.", { exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Historico de estados", exact: true })).toHaveCount(0);
});

test("@tickets decimal number paging and empty filters preserve creation authority", async ({ page }) => {
  const csrf = await login(page);
  const marker = `Paginacao ${crypto.randomUUID()}`;
  const ids = [];
  for (let index = 0; index < 11; index++) ids.push(await create(page, csrf, `${marker} item ${index}`));
  const exact = await (await page.request.get(`/api/v1/tickets/${ids[10]}`)).json();
  expect(typeof exact.number).toBe("string");
  expect(BigInt(exact.number)).toBeGreaterThan(9007199254740991n);
  await page.goto(`${directory}/${ids[10]}`);
  await expect(page.getByText(`Chamado ${exact.number} - Novo`, { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Voltar aos chamados", exact: true }).click();
  await page.getByLabel("Busca nos chamados", { exact: true }).fill(marker);
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
  const list = page.getByRole("list", { name: "Chamados disponiveis", exact: true });
  await expect(list.getByRole("listitem")).toHaveCount(10);
  await page.getByRole("button", { name: "Proximos chamados", exact: true }).click();
  await expect(list.getByRole("listitem")).toHaveCount(1);
  await page.getByLabel("Estado", { exact: true }).selectOption("closed");
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
  await expect(page.getByText("Nenhum chamado disponivel nesta pagina com estes filtros.", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Novo chamado", exact: true })).toBeVisible();
});

test("@tickets requester paging preserves selection and agent avoids assignee directory", async ({ page }) => {
  await login(page, "AGENT");
  const forbiddenReads: string[] = [];
  page.on("request", request => { if (request.method() === "GET" && request.url().includes("/assignees")) forbiddenReads.push(request.url()); });
  await page.goto(directory + "/new");
  await page.getByLabel("Fila do chamado", { exact: true }).selectOption(queue);
  await page.getByLabel("Cliente do chamado", { exact: true }).selectOption(client);
  const field = page.getByLabel("Solicitante", { exact: true });
  await expect(field).toBeEnabled();
  const chosen = await field.locator("option").nth(1).getAttribute("value");
  await field.selectOption(chosen!);
  await page.getByRole("button", { name: "Proximos solicitantes", exact: true }).click();
  await expect(field).toHaveValue(chosen!);
  await page.getByRole("button", { name: "Solicitantes anteriores", exact: true }).click();
  await expect(field).toHaveValue(chosen!);
  await page.getByLabel("Assunto", { exact: true }).fill("Solicitante paginado");
  await page.getByRole("button", { name: "Revisar chamado", exact: true }).click();
  await page.getByRole("button", { name: "Criar chamado", exact: true }).click();
  await expect(page).toHaveURL(/\/service-desk\/tickets\/[0-9a-f-]+$/);
  expect(forbiddenReads).toEqual([]);
});

test("@tickets prepared transition keeps reviewed version across authoritative refresh", async ({ page }) => {
  const csrf = await login(page);
  const id = await create(page, csrf);
  const api = `/api/v1/tickets/${id}`;
  expect((await page.request.post(api + "/transitions", { headers: headers(csrf), data: { target_status: "open" } })).status()).toBe(200);
  await page.goto(`${directory}/${id}`);
  await page.getByLabel("Proximo estado", { exact: true }).selectOption("resolved");
  await page.getByLabel("Motivo", { exact: true }).fill("Resolucao revisada na versao 2");
  expect((await page.request.patch(api, { headers: headers(csrf, 2), data: { subject: "Novo contexto do atendimento" } })).status()).toBe(200);
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Novo contexto do atendimento", exact: true })).toBeVisible();
  const sent = page.waitForRequest(request => request.url().endsWith(api + "/transitions") && request.method() === "POST");
  await page.getByRole("button", { name: "Alterar estado", exact: true }).click();
  expect((await sent).headers()["if-match"]).toBe('"2"');
  await expect(page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true })).toBeVisible();
  expect((await (await page.request.get(api)).json()).status).toBe("open");
});

test("@tickets acknowledged creation stays locked during slow detail navigation", async ({ page }) => {
  await login(page); await fillCreation(page);
  let release!: () => void;
  const navigation = new Promise<void>(resolve => { release = resolve; });
  await page.route(/\/service-desk\/tickets\/[0-9a-f-]+(?:\?.*)?$/, async route => {
    await navigation; await route.continue();
  });
  const response = page.waitForResponse(value => value.url().endsWith("/api/v1/tickets") && value.request().method() === "POST");
  await page.getByRole("button", { name: "Criar chamado", exact: true }).click();
  expect((await response).status()).toBe(201);
  try {
    await expect(page.getByRole("button", { name: "Criar chamado", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Voltar a edicao", exact: true })).toBeDisabled();
    await expect(page.getByRole("link", { name: "Abrir chamado criado", exact: true })).toBeVisible();
  } finally { release(); }
  await expect(page).toHaveURL(/\/service-desk\/tickets\/[0-9a-f-]+$/);
});
