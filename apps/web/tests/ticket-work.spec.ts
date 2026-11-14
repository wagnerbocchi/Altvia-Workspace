import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const origin = "https://127.0.0.1:3443";
const project = process.env.ALTVIA_E2E_LINK_PROJECT_ID!;
const queue = process.env.ALTVIA_E2E_LINK_QUEUE_ID!;
const client = process.env.ALTVIA_E2E_LINK_CLIENT_ID!;
const requester = process.env.ALTVIA_E2E_LINK_REQUESTER_ID!;

async function login(page: Page, kind = "MANAGER") {
  const token = process.env[`ALTVIA_E2E_LINK_${kind}_SESSION`];
  if (!token) throw Error("Guarded link session required");
  await page.context().addCookies([{ name: "__Host-altvia_session", value: token, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const response = await page.request.get("/api/v1/auth/me");
  expect(response.status()).toBe(200);
  return (await response.json()).csrf_token as string;
}
const headers = (csrf: string, ticketVersion = 1, workVersion = 1, key = crypto.randomUUID()) => ({ Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${ticketVersion}"`, "If-Match-Work-Item": `"${workVersion}"`, "Idempotency-Key": key });
async function createPair(page: Page, csrf: string) {
  const subject = `Atendimento ${crypto.randomUUID()}`;
  const title = `Tarefa <b>literal</b> ${crypto.randomUUID()}`;
  const ticket = await page.request.post("/api/v1/tickets", { headers: headers(csrf), data: { queue_id: queue, client_id: client, requester_id: requester, subject, priority: "high" } });
  expect(ticket.status()).toBe(201);
  const work = await page.request.post("/api/v1/work-items", { headers: headers(csrf), data: { project_id: project, title, work_type: "one_off", priority: "medium" } });
  expect(work.status()).toBe(201);
  return { ticket: (await ticket.json()).ticket_id as string, work: (await work.json()).work_item_id as string, subject, title };
}
type Pair = Awaited<ReturnType<typeof createPair>>;
const panel = (page: Page) => page.getByRole("region", { name: "Tarefas vinculadas", exact: true });
const linked = (page: Page) => page.getByRole("list", { name: "Tarefas vinculadas", exact: true });
async function review(page: Page, pair: Pair) {
  await page.goto(`/service-desk/tickets/${pair.ticket}`);
  await panel(page).getByRole("button", { name: "Vincular tarefa", exact: true }).click();
  // Native PostgreSQL websearch is token search, not literal HTML-like equality.
  // Keep the complete literal title assertion on the returned authorized row.
  await page.getByLabel("Buscar tarefa para vincular", { exact: true }).fill(pair.title.split(" ").at(-1)!);
  await page.getByRole("button", { name: "Buscar tarefas", exact: true }).click();
  await page.getByRole("list", { name: "Tarefas para vincular", exact: true }).getByRole("listitem").filter({ hasText: pair.title }).getByRole("button", { name: "Revisar vinculo", exact: true }).click();
  await expect(page.getByRole("region", { name: "Revisar vinculacao", exact: true })).toContainText(pair.title);
  await expect(page.getByRole("heading", { name: "Revisar vinculacao", exact: true })).toBeFocused();
}
async function snapshots(page: Page, pair: Pair) {
  const ticket = await (await page.request.get(`/api/v1/tickets/${pair.ticket}`)).json();
  const work = await (await page.request.get(`/api/v1/work-items/${pair.work}`)).json();
  return { ticket, work };
}
async function changeLink(page: Page, csrf: string, pair: Pair, operation: "link" | "unlink") {
  const { ticket, work } = await snapshots(page, pair);
  const options = { headers: headers(csrf, ticket.version, work.version) };
  const response = operation === "link"
    ? await page.request.post(`/api/v1/tickets/${pair.ticket}/work-items`, { ...options, data: { work_item_id: pair.work } })
    : await page.request.delete(`/api/v1/tickets/${pair.ticket}/work-items/${pair.work}`, options);
  expect(response.status()).toBe(operation === "link" ? 201 : 204);
}
async function capture(page: Page, name: string) {
  const root = fileURLToPath(new URL("../../../.impeccable/review/ticket-work/", import.meta.url));
  await mkdir(root, { recursive: true });
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(el => el.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      await expect(page.locator("html")).toHaveCSS("color-scheme", theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({ path: `${root}/${name}-${size}-${theme}.png`, fullPage: true });
    }
  }
}

test("@ticket-work persisted reciprocal links preserve both lifecycles", async ({ page }) => {
  test.setTimeout(120_000);
  const csrf = await login(page);
  const pair = await createPair(page, csrf);
  for (const [version, status] of [[1, "in_progress"], [2, "done"]] as const) {
    expect((await page.request.post(`/api/v1/work-items/${pair.work}/transitions`, { headers: headers(csrf, version), data: { target_status: status } })).status()).toBe(200);
  }
  const before = await snapshots(page, pair);
  await page.goto(`/service-desk/tickets/${pair.ticket}`);
  await expect(page.getByRole("region", { name: "Tarefas vinculadas", exact: true })).toBeVisible();
  await capture(page, "empty");
  await review(page, pair);
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toBeDisabled();
  await expect(page.getByLabel("Arquivo para resposta publica", { exact: true })).toBeDisabled();
  await expect(page.getByLabel("Arquivo para nota interna", { exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Cancelar revisao", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Tarefas vinculadas", exact: true })).toBeFocused();
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toBeEnabled();
  await page.getByRole("list", { name: "Tarefas para vincular", exact: true }).getByRole("button", { name: "Revisar vinculo", exact: true }).click();
  await capture(page, "review");
  await page.getByRole("button", { name: "Confirmar vinculacao", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(linked(page)).toContainText(pair.title);
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toBeEnabled();
  await capture(page, "linked");
  const after = await snapshots(page, pair);
  expect(after.ticket.version).toBe(before.ticket.version + 1);
  expect(after.work.version).toBe(before.work.version + 1);
  for (const field of ["status", "assignee_id", "priority", "resolved_at", "closed_at"]) expect(after.ticket[field]).toEqual(before.ticket[field]);
  for (const field of ["status", "owner_id", "assignee_ids", "priority", "due", "completed_at"]) expect(after.work[field]).toEqual(before.work[field]);
  await linked(page).getByRole("link", { name: pair.title, exact: true }).click();
  const reciprocal = page.getByRole("region", { name: "Chamados vinculados", exact: true });
  await expect(reciprocal).toContainText(pair.subject);
  await expect(reciprocal).toContainText("Estado do chamado: Novo");
  await reciprocal.getByRole("button", { name: "Desvincular chamado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Editar tarefa", exact: true })).toBeDisabled();
  await expect(page.getByLabel("Arquivo para comentario interno", { exact: true })).toBeDisabled();
  await capture(page, "reciprocal-unlink");
  await page.getByRole("button", { name: "Confirmar desvinculacao", exact: true }).click();
  await expect(reciprocal).toContainText("Nenhum chamado vinculado disponivel nesta pagina.");
  expect((await (await page.request.get(`/api/v1/tickets/${pair.ticket}/work-items`)).json()).items).toEqual([]);
  const unlinked = await snapshots(page, pair);
  expect(unlinked.ticket.status).toBe(before.ticket.status);
  expect(unlinked.work.status).toBe(before.work.status);
});

for (const operation of ["link", "unlink"] as const) test(`@ticket-work delayed ${operation} recovery preserves ${operation === "unlink" ? "relink (RF1)" : "subsequent unlink"}`, async ({ page }) => {
  const csrf = await login(page);
  const pair = await createPair(page, csrf);
  if (operation === "unlink") await changeLink(page, csrf, pair, "link");
  if (operation === "link") await review(page, pair);
  else {
    await page.goto(`/service-desk/tickets/${pair.ticket}`);
    await linked(page).getByRole("button", { name: "Desvincular tarefa", exact: true }).click();
  }
  const path = `/api/v1/tickets/${pair.ticket}/work-items${operation === "unlink" ? `/${pair.work}` : ""}`;
  let original: object | undefined, attempts = 0;
  await page.route(`**${path}`, async route => {
    if (route.request().method() === "GET") return route.continue();
    const request = route.request();
    const intent = { method: request.method(), body: request.postData(), key: request.headers()["idempotency-key"], ticketVersion: request.headers()["if-match"], workVersion: request.headers()["if-match-work-item"] };
    attempts++;
    if (attempts === 1) { original = intent; await route.fetch(); await route.abort("failed"); }
    else { expect(intent).toEqual(original); await route.continue(); }
  });
  await page.getByRole("button", { name: operation === "link" ? "Confirmar vinculacao" : "Confirmar desvinculacao", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar vinculo", exact: true })).toBeVisible();
  if (operation === "unlink") await capture(page, "uncertain-unlink");
  await changeLink(page, csrf, pair, operation === "unlink" ? "link" : "unlink");
  const beforeReplay = await snapshots(page, pair);
  await page.route(`**/api/v1/tickets/${pair.ticket}/work-items?*`, route => route.fulfill({ status: 503, body: "{}" }));
  await panel(page).getByRole("button", { name: "Atualizar tarefas vinculadas", exact: true }).click();
  await expect(page.getByRole("button", { name: operation === "link" ? "Confirmar vinculacao" : "Confirmar desvinculacao", exact: true })).toBeDisabled();
  await page.unroute(`**/api/v1/tickets/${pair.ticket}/work-items?*`);
  await page.getByRole("button", { name: "Verificar vinculo", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toBeEnabled();
  expect(attempts).toBe(2);
  expect(await snapshots(page, pair)).toEqual(beforeReplay);
  expect((await (await page.request.get(`/api/v1/tickets/${pair.ticket}/work-items`)).json()).items.map((row: { work_item_id: string }) => row.work_item_id)).toEqual(operation === "unlink" ? [pair.work] : []);
});

for (const failure of ["work-503", "ticket-404", "work-403", "list-503"] as const) test(`@ticket-work acknowledged write blocks until both refreshes succeed (RF5) ${failure}`, async ({ page }) => {
  test.setTimeout(90_000);
  const csrf = await login(page);
  const pair = await createPair(page, csrf);
  await review(page, pair);
  const failedPath = failure === "ticket-404" ? `/api/v1/tickets/${pair.ticket}` : failure === "list-503" ? `/api/v1/work-items/${pair.work}/tickets?*` : `/api/v1/work-items/${pair.work}`;
  let posts = 0;
  page.on("request", request => { if (request.method() === "POST" && request.url().endsWith(`/tickets/${pair.ticket}/work-items`)) posts++; });
  await page.route(`**${failedPath}`, route => route.fulfill({ status: failure.endsWith("404") ? 404 : failure.endsWith("403") ? 403 : 503, contentType: "application/json", body: JSON.stringify({ code: failure.endsWith("403") ? "forbidden" : "not_found" }) }));
  await page.getByRole("button", { name: "Confirmar vinculacao", exact: true }).click();
  const retry = page.getByRole("button", { name: "Atualizar registros vinculados", exact: true });
  await expect(retry).toBeEnabled();
  await expect(panel(page)).not.toContainText(pair.title);
  if (failure === "ticket-404") {
    await expect(page.getByRole("heading", { name: pair.subject, exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Dados do chamado", exact: true })).toHaveCount(0);
  } else await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toBeDisabled();
  await retry.click();
  await expect(panel(page).getByRole("alert").filter({ hasText: "Novas alteracoes continuam bloqueadas" })).toBeVisible();
  expect(posts).toBe(1);
  if (failure === "ticket-404") await capture(page, "acknowledged-parent-denied");
  await page.unroute(`**${failedPath}`);
  await retry.click();
  await expect(linked(page)).toContainText(pair.title);
  await expect(page.getByRole("button", { name: "Editar chamado", exact: true })).toBeEnabled();
  expect(posts).toBe(1);
  expect((await snapshots(page, pair)).ticket.version).toBe(2);
});

for (const side of ["ticket", "work"] as const) test(`@ticket-work stale ${side} version requires explicit successful reload and review`, async ({ page }) => {
  const csrf = await login(page);
  const pair = await createPair(page, csrf);
  await review(page, pair);
  const response = await page.request.patch(`/api/v1/${side === "ticket" ? "tickets" : "work-items"}/${pair[side]}`, { headers: headers(csrf), data: { priority: "critical" } });
  expect(response.status()).toBe(200);
  const request = page.waitForRequest(request => request.method() === "POST" && request.url().endsWith(`/tickets/${pair.ticket}/work-items`));
  await page.getByRole("button", { name: "Confirmar vinculacao", exact: true }).click();
  expect((await request).headers()["if-match"]).toBe('"1"');
  expect((await request).headers()["if-match-work-item"]).toBe('"1"');
  const reload = panel(page).getByRole("button", { name: /Recarregar e descartar/ });
  await expect(reload).toBeVisible();
  await page.route(`**/api/v1/work-items/${pair.work}`, route => route.fulfill({ status: 503, body: "{}" }));
  await reload.click();
  await expect(page.getByRole("button", { name: "Confirmar vinculacao", exact: true })).toBeDisabled();
  await page.unroute(`**/api/v1/work-items/${pair.work}`);
  await reload.click();
  await expect(page.getByRole("heading", { name: "Revisar vinculacao", exact: true })).toHaveCount(0);
  await page.getByRole("list", { name: "Tarefas para vincular", exact: true }).getByRole("button", { name: "Revisar vinculo", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar vinculacao", exact: true }).click();
  await expect(linked(page)).toContainText(pair.title);
});

test("@ticket-work session replacement disposes pending pair (RF4/RF5)", async ({ page }) => {
  const csrf = await login(page);
  const pair = await createPair(page, csrf);
  await review(page, pair);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const path = `/api/v1/tickets/${pair.ticket}/work-items`;
  let posts = 0;
  await page.route(`**${path}`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    posts++;
    const reply = await route.fetch();
    await gate; await route.fulfill({ response: reply });
  });
  await page.getByRole("button", { name: "Confirmar vinculacao", exact: true }).click();
  await expect.poll(async () => (await snapshots(page, pair)).ticket.version).toBe(2);
  await login(page, "VIEWER");
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  // The native identity observer replaces the private QueryClient and children.
  await expect(page.getByRole("button", { name: "Confirmar vinculacao", exact: true })).toHaveCount(0);
  release();
  await expect(linked(page)).toContainText(pair.title);
  await expect(page.getByRole("button", { name: "Verificar vinculo", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Atualizar registros vinculados", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Vincular tarefa", exact: true })).toHaveCount(0);
  expect(posts).toBe(1);
  expect(await page.evaluate(() => Object.keys(sessionStorage))).toEqual([]);
});

test("@ticket-work read-only and hidden counterparts expose no relationship metadata", async ({ page }) => {
  const csrf = await login(page);
  const pair = await createPair(page, csrf);
  await changeLink(page, csrf, pair, "link");
  await login(page, "VIEWER"); await page.goto(`/service-desk/tickets/${pair.ticket}`);
  await expect(linked(page)).toContainText(pair.title);
  await expect(panel(page).getByRole("button", { name: "Desvincular tarefa", exact: true })).toHaveCount(0);
  await expect(panel(page).getByRole("button", { name: "Vincular tarefa", exact: true })).toHaveCount(0);
  await login(page, "TICKET_ONLY"); await page.reload();
  await expect(panel(page)).toContainText("Nenhuma tarefa vinculada disponivel nesta pagina.");
  await expect(page.getByText(pair.title, { exact: true })).toHaveCount(0);
  const hiddenWork = await (await page.request.get(`/api/v1/tickets/${pair.ticket}/work-items?limit=1`)).json();
  expect(hiddenWork).toEqual({ can_link: true, items: [], next_cursor: null });
  await login(page, "WORK_ONLY"); await page.goto(`/work-items/${pair.work}`);
  const workPanel = page.getByRole("region", { name: "Chamados vinculados", exact: true });
  await expect(workPanel).toContainText("Nenhum chamado vinculado disponivel nesta pagina.");
  await expect(workPanel).not.toContainText(pair.subject);
  expect(await (await page.request.get(`/api/v1/work-items/${pair.work}/tickets?limit=1`)).json()).toEqual({ items: [], next_cursor: null });
});

test("@ticket-work agent needs both assignments; closed ticket and archived project block new effects", async ({ page }) => {
  const csrf = await login(page);
  const pair = await createPair(page, csrf);
  const agent = process.env.ALTVIA_E2E_LINK_AGENT_ID!;
  expect((await page.request.patch(`/api/v1/tickets/${pair.ticket}`, { headers: headers(csrf), data: { assignee_id: agent } })).status()).toBe(200);
  await login(page, "AGENT");
  expect((await (await page.request.get(`/api/v1/tickets/${pair.ticket}/work-item-choices`)).json()).items.some((row: { work_item_id: string }) => row.work_item_id === pair.work)).toBe(false);
  await login(page);
  expect((await page.request.patch(`/api/v1/work-items/${pair.work}`, { headers: headers(csrf), data: { owner_id: agent } })).status()).toBe(200);
  const agentCsrf = await login(page, "AGENT");
  await review(page, pair);
  await page.getByRole("button", { name: "Confirmar vinculacao", exact: true }).click();
  await expect(linked(page)).toContainText(pair.title);
  for (const [version, status] of [[3, "open"], [4, "resolved"]] as const) {
    expect((await page.request.post(`/api/v1/tickets/${pair.ticket}/transitions`, { headers: headers(agentCsrf, version), data: { target_status: status, reason: "Validacao sintetica" } })).status()).toBe(200);
  }
  expect((await page.request.post(`/api/v1/tickets/${pair.ticket}/transitions`, { headers: headers(agentCsrf, 5), data: { target_status: "closed", reason: "Validacao sintetica" } })).status()).toBe(409);
  await login(page);
  expect((await page.request.post(`/api/v1/tickets/${pair.ticket}/transitions`, { headers: headers(csrf, 5), data: { target_status: "closed", reason: "Validacao sintetica" } })).status()).toBe(200);
  await page.reload();
  await expect(linked(page)).toContainText(pair.title);
  await expect(panel(page).getByRole("button", { name: "Desvincular tarefa", exact: true })).toHaveCount(0);
  await login(page);
  const projectRow = await (await page.request.get(`/api/v1/projects/${project}`)).json();
  expect((await page.request.patch(`/api/v1/projects/${project}`, { headers: headers(csrf, projectRow.version), data: { active: false } })).status()).toBe(200);
  try {
    await page.goto(`/work-items/${pair.work}`);
    const workPanel = page.getByRole("region", { name: "Chamados vinculados", exact: true });
    await expect(workPanel).toContainText(pair.subject);
    await expect(workPanel.getByRole("button", { name: "Desvincular chamado", exact: true })).toHaveCount(0);
  } finally {
    const archived = await (await page.request.get(`/api/v1/projects/${project}`)).json();
    expect((await page.request.patch(`/api/v1/projects/${project}`, { headers: headers(csrf, archived.version), data: { active: true } })).status()).toBe(200);
  }
});

test("@ticket-work paged search and list read recovery preserve native controls", async ({ page }) => {
  test.setTimeout(90_000);
  const csrf = await login(page);
  const pair = await createPair(page, csrf);
  const marker = `Paginado ${crypto.randomUUID()}`;
  const workIds: string[] = [];
  for (let index = 0; index < 11; index++) {
    const response = await page.request.post("/api/v1/work-items", { headers: headers(csrf), data: { project_id: project, title: `${marker} ${index}`, work_type: "one_off", priority: "medium" } });
    expect(response.status()).toBe(201);
    workIds.push((await response.json()).work_item_id);
  }
  await page.goto(`/service-desk/tickets/${pair.ticket}`);
  await panel(page).getByRole("button", { name: "Vincular tarefa", exact: true }).click();
  await page.getByLabel("Buscar tarefa para vincular", { exact: true }).fill(marker);
  await page.getByRole("button", { name: "Buscar tarefas", exact: true }).click();
  const section = page.getByRole("region", { name: "Escolher tarefa existente", exact: true });
  await expect(section.getByRole("listitem")).toHaveCount(10);
  await section.getByRole("button", { name: "Próximas tarefas", exact: true }).click();
  await expect(section.getByRole("listitem")).toHaveCount(1);
  for (const work of workIds) await changeLink(page, csrf, { ...pair, work }, "link");
  await panel(page).getByRole("button", { name: "Atualizar tarefas vinculadas", exact: true }).click();
  await expect(linked(page).getByRole("listitem")).toHaveCount(10);
  await panel(page).getByRole("navigation", { name: "Páginas de tarefas", exact: true }).first().getByRole("button", { name: "Próximas tarefas", exact: true }).click();
  await expect(linked(page).getByRole("listitem")).toHaveCount(1);
  await page.route(`**/api/v1/tickets/${pair.ticket}/work-items?*`, route => route.fulfill({ status: 503, body: "{}" }));
  await panel(page).getByRole("button", { name: "Atualizar tarefas vinculadas", exact: true }).click();
  await expect(panel(page).getByRole("alert")).toBeVisible();
  await capture(page, "read-error");
  await page.unroute(`**/api/v1/tickets/${pair.ticket}/work-items?*`);
  await panel(page).getByRole("button", { name: "Tentar carregar novamente", exact: true }).click();
  await expect(linked(page).getByRole("listitem")).toHaveCount(1);
});

for (const status of [404, 403]) test(`@ticket-work acknowledged DELETE retains work-side read recovery after parent ${status}`, async ({ page }) => {
  const csrf = await login(page);
  const pair = await createPair(page, csrf);
  await changeLink(page, csrf, pair, "link");
  await page.goto(`/work-items/${pair.work}`);
  const section = page.getByRole("region", { name: "Chamados vinculados", exact: true });
  await section.getByRole("button", { name: "Desvincular chamado", exact: true }).click();
  let deletes = 0;
  page.on("request", request => { if (request.method() === "DELETE" && request.url().endsWith(`/work-items/${pair.work}`)) deletes++; });
  const failed = `**/api/v1/work-items/${pair.work}`;
  await page.route(failed, route => route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ code: status === 403 ? "forbidden" : "not_found" }) }));
  await page.getByRole("button", { name: "Confirmar desvinculacao", exact: true }).click();
  const retry = page.getByRole("button", { name: "Atualizar registros vinculados", exact: true });
  await expect(retry).toBeEnabled();
  await expect(page.getByText(pair.title, { exact: true })).toHaveCount(0);
  await expect(page.getByText(pair.subject, { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Dados da tarefa", exact: true })).toHaveCount(0);
  await retry.click();
  await expect(section.getByRole("alert").filter({ hasText: "Novas alteracoes continuam bloqueadas" })).toBeVisible();
  expect(deletes).toBe(1);
  await page.unroute(failed);
  await retry.click();
  await expect(page.getByRole("button", { name: "Editar tarefa", exact: true })).toBeEnabled();
  await expect(section).toContainText("Nenhum chamado vinculado disponivel nesta pagina.");
  expect(deletes).toBe(1);
});

test("@ticket-work session replacement disposes acknowledged pair and read recovery", async ({ page }) => {
  const csrf = await login(page);
  const pair = await createPair(page, csrf);
  await review(page, pair);
  let posts = 0;
  page.on("request", request => { if (request.method() === "POST" && request.url().endsWith(`/tickets/${pair.ticket}/work-items`)) posts++; });
  const path = `**/api/v1/work-items/${pair.work}`;
  await page.route(path, route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Confirmar vinculacao", exact: true }).click();
  await expect(page.getByRole("button", { name: "Atualizar registros vinculados", exact: true })).toBeEnabled();
  await login(page, "VIEWER");
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await expect(page.getByRole("button", { name: "Atualizar registros vinculados", exact: true })).toHaveCount(0);
  await page.unroute(path);
  await expect(linked(page)).toContainText(pair.title);
  await expect(panel(page).getByRole("button", { name: "Vincular tarefa", exact: true })).toHaveCount(0);
  expect(posts).toBe(1);
});

test("@ticket-work counterpart revocation disposes private state and hides existing links after login", async ({ page, browser }) => {
  const csrf = await login(page);
  const pair = await createPair(page, csrf);
  await changeLink(page, csrf, pair, "link");
  const viewer = await browser.newPage({ baseURL: origin, ignoreHTTPSErrors: true });
  const account = process.env.ALTVIA_E2E_LINK_VIEWER_ID!;
  try {
    await login(viewer, "VIEWER");
    await viewer.goto(`/service-desk/tickets/${pair.ticket}`);
    await expect(linked(viewer)).toContainText(pair.title);
    const parent = await (await page.request.get(`/api/v1/projects/${project}`)).json();
    expect((await page.request.delete(`/api/v1/projects/${project}/members/${account}`, { headers: headers(csrf, parent.version) })).status()).toBe(204);
    await viewer.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
    await expect(viewer.getByRole("heading", { name: "Acesse seu workspace", exact: true })).toBeVisible();
    await expect(viewer.getByText(pair.title, { exact: true })).toHaveCount(0);
    const logged = await viewer.request.post("/api/v1/auth/sessions", { headers: { Origin: origin }, data: { email: process.env.ALTVIA_E2E_LINK_VIEWER_EMAIL, password: process.env.ALTVIA_E2E_LINK_VIEWER_PASSWORD } });
    expect(logged.status()).toBe(201);
    await viewer.reload();
    await expect(panel(viewer)).toContainText("Nenhuma tarefa vinculada disponivel nesta pagina.");
    expect(await (await viewer.request.get(`/api/v1/tickets/${pair.ticket}/work-items?limit=1`)).json()).toEqual({ can_link: false, items: [], next_cursor: null });
    expect((await viewer.request.get(`/api/v1/work-items/${pair.work}`)).status()).toBe(404);
  } finally { await viewer.close(); }
});
