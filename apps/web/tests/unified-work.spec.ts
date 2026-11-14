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
  if (!token) throw Error("Guarded personal work session required");
  await page.context().addCookies([{ name: "__Host-altvia_session", value: token, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const response = await page.request.get("/api/v1/auth/me");
  expect(response.status()).toBe(200);
  return await response.json() as { id: string; csrf_token: string };
}
const headers = (csrf: string, version = 1) => ({ Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${version}"`, "Idempotency-Key": crypto.randomUUID() });
async function pair(page: Page, term: string, actor: Awaited<ReturnType<typeof login>>, owner = actor.id) {
  const ticket = await page.request.post("/api/v1/tickets", { headers: headers(actor.csrf_token), data: { queue_id: queue, client_id: client, requester_id: requester, subject: `${term} chamado`, priority: "critical", assignee_id: actor.id } });
  expect(ticket.status()).toBe(201);
  const work = await page.request.post("/api/v1/work-items", { headers: headers(actor.csrf_token), data: { project_id: project, title: `${term} tarefa`, priority: "low", work_type: "one_off", owner_id: owner, assignee_ids: [owner] } });
  expect(work.status()).toBe(201);
  const ids = { ticket: (await ticket.json()).ticket_id as string, work: (await work.json()).work_item_id as string };
  const linked = await page.request.post(`/api/v1/tickets/${ids.ticket}/work-items`, { headers: { ...headers(actor.csrf_token), "If-Match-Work-Item": '"1"' }, data: { work_item_id: ids.work } });
  expect(linked.status()).toBe(201);
  return ids;
}
async function filter(page: Page, term: string) {
  await page.getByLabel("Buscar no meu trabalho", { exact: true }).fill(term);
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
}
const rows = (page: Page) => page.getByRole("list", { name: "Fila unificada", exact: true });

test("@unified-work default queue represents linked tickets once and retains legacy tasks", async ({ page }) => {
  const actor = await login(page);
  const term = `Pessoal${crypto.randomUUID().replaceAll("-", "")}`;
  const ids = await pair(page, term, actor);
  const exact = await (await page.request.get(`/api/v1/tickets/${ids.ticket}`)).json();
  const projection = await (await page.request.get("/api/v1/my-work/unified", { params: { q: term } })).json();
  expect(projection.items[0].linked_tickets[0].number).toBe(exact.number);
  await page.goto("/my-work");
  await expect(page.getByRole("button", { name: "Fila unificada", exact: true })).toHaveAttribute("aria-pressed", "true");
  await filter(page, term);
  await expect(rows(page).getByRole("listitem")).toHaveCount(1);
  await expect(rows(page).getByRole("link", { name: `${term} tarefa`, exact: true })).toHaveAttribute("href", `/work-items/${ids.work}`);
  await expect(rows(page).getByRole("link", { name: new RegExp(`${term} chamado`) })).toHaveAttribute("href", `/service-desk/tickets/${ids.ticket}`);
  await expect(rows(page).getByRole("link", { name: `Chamado #${exact.number} · ${term} chamado`, exact: true })).toBeVisible();
  await expect(rows(page)).toContainText("Estado do chamado: Novo");
  await page.getByLabel("Registros", { exact: true }).selectOption("ticket");
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
  await expect(rows(page).getByRole("listitem")).toHaveCount(1);
  await expect(rows(page)).not.toContainText(`${term} tarefa`);
  await page.getByRole("button", { name: "Somente tarefas", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByLabel("Buscar tarefas", { exact: true }).fill(term);
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
  await expect(page.getByRole("list", { name: "Minhas tarefas", exact: true }).getByRole("link", { name: `${term} tarefa`, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Fila unificada", exact: true }).click();
  await expect(page.getByLabel("Buscar no meu trabalho", { exact: true })).toHaveValue("");
});

test("@unified-work complete-set suppression survives pagination and submitted filter changes", async ({ page }) => {
  const actor = await login(page);
  const term = `Paginas${crypto.randomUUID().replaceAll("-", "")}`;
  for (let index = 0; index < 11; index++) {
    const created = await page.request.post("/api/v1/work-items", { headers: headers(actor.csrf_token), data: { project_id: project, title: `${term} ${index}`, priority: "high", work_type: "one_off", owner_id: actor.id } });
    expect(created.status()).toBe(201);
  }
  await pair(page, term, actor);
  await page.goto("/my-work");
  await filter(page, term);
  await expect(rows(page).getByRole("listitem")).toHaveCount(10);
  await expect(rows(page)).not.toContainText(`${term} chamado`);
  await page.getByRole("button", { name: "Proximos registros", exact: true }).click();
  await expect(rows(page).getByRole("listitem")).toHaveCount(2);
  await expect(rows(page)).toContainText(`${term} chamado`);
  await page.getByLabel("Buscar no meu trabalho", { exact: true }).fill("SemCorrespondenciaPessoal");
  await expect(rows(page).getByRole("listitem")).toHaveCount(2);
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
  await expect(page.getByText("Nenhum registro corresponde aos filtros.", { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Páginas de registros", exact: true })).toContainText("Página 1");
});

test("@unified-work hidden ticket badges stay private after session replacement", async ({ page }) => {
  const actor = await login(page);
  const term = `Privado${crypto.randomUUID().replaceAll("-", "")}`;
  const owner = process.env.ALTVIA_E2E_LINK_WORK_ONLY_ID!;
  await pair(page, term, actor, owner);
  await page.goto("/my-work");
  await filter(page, term);
  await expect(rows(page)).toContainText(`${term} chamado`);
  let captured = false, settled = false;
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/my-work/unified?**", async route => {
    if (captured) return route.continue();
    const response = await route.fetch();
    captured = true;
    await gate;
    await route.fulfill({ response });
    settled = true;
  });
  try {
    await page.getByRole("button", { name: "Atualizar fila", exact: true }).click();
    await expect.poll(() => captured).toBe(true);
    await login(page, "WORK_ONLY");
    await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
    await expect(page.getByLabel("Buscar no meu trabalho", { exact: true })).toHaveValue("");
    await filter(page, term);
    await expect(rows(page)).toContainText(`${term} tarefa`);
    release();
    await expect.poll(() => settled).toBe(true);
    await expect(page.getByRole("main")).not.toContainText(`${term} chamado`);
  } finally { release(); }
});

test("@unified-work visible origin cap and independent statuses lead to real details", async ({ page }) => {
  const actor = await login(page);
  const term = `Origens${crypto.randomUUID().replaceAll("-", "")}`;
  const ids = await pair(page, term, actor);
  for (let index = 0; index < 3; index++) {
    const ticket = await page.request.post("/api/v1/tickets", { headers: headers(actor.csrf_token), data: { queue_id: queue, client_id: client, requester_id: requester, subject: `${term} origem ${index}`, priority: "high", assignee_id: actor.id } });
    expect(ticket.status()).toBe(201);
    const id = (await ticket.json()).ticket_id;
    const work = await (await page.request.get(`/api/v1/work-items/${ids.work}`)).json();
    expect((await page.request.post(`/api/v1/tickets/${id}/work-items`, { headers: { ...headers(actor.csrf_token), "If-Match-Work-Item": `"${work.version}"` }, data: { work_item_id: ids.work } })).status()).toBe(201);
  }
  for (const status of ["in_progress", "done"]) {
    const work = await (await page.request.get(`/api/v1/work-items/${ids.work}`)).json();
    expect((await page.request.post(`/api/v1/work-items/${ids.work}/transitions`, { headers: headers(actor.csrf_token, work.version), data: { target_status: status } })).status()).toBe(200);
  }
  await page.goto("/my-work");
  await filter(page, term);
  await expect(rows(page).getByRole("listitem")).toHaveCount(1);
  await expect(rows(page)).toContainText("Concluída");
  await expect(rows(page).getByRole("link").filter({ hasText: /^Chamado #/ })).toHaveCount(3);
  const more = rows(page).getByRole("link", { name: "Consultar demais chamados vinculados", exact: true });
  await expect(more).toHaveAttribute("href", `/work-items/${ids.work}`);
  await more.click();
  const origins = page.getByRole("region", { name: "Chamados vinculados", exact: true });
  await expect(origins.getByRole("listitem")).toHaveCount(4);
  await expect(origins.getByText("Estado do chamado: Novo", { exact: true })).toHaveCount(4);
});

test("@unified-work failed refresh hides cached rows and retry restores real records", async ({ page }) => {
  const actor = await login(page);
  const term = `Retomar${crypto.randomUUID().replaceAll("-", "")}`;
  await pair(page, term, actor);
  await page.goto("/my-work");
  await filter(page, term);
  await expect(rows(page)).toContainText(`${term} tarefa`);
  await page.route("**/api/v1/my-work/unified?**", route => route.abort());
  await page.getByRole("button", { name: "Atualizar fila", exact: true }).click();
  await expect(page.getByRole("button", { name: "Tentar carregar novamente", exact: true })).toBeVisible();
  await expect(rows(page)).toHaveCount(0);
  await page.unroute("**/api/v1/my-work/unified?**");
  await page.getByRole("button", { name: "Tentar carregar novamente", exact: true }).click();
  await expect(rows(page)).toContainText(`${term} tarefa`);
  const folder = fileURLToPath(new URL("../../../.impeccable/review/unified-work/", import.meta.url));
  await mkdir(folder, { recursive: true });
  for (const width of [1440, 390]) for (const theme of ["light", "dark"]) {
    await page.setViewportSize({ width, height: 1000 });
    if (await page.locator("html").evaluate(element => element.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (width === 1440) {
      const select = await page.getByLabel("Registros", { exact: true }).boundingBox();
      const disclosure = await page.locator(".unified-filters summary").boundingBox();
      expect(select).not.toBeNull(); expect(disclosure).not.toBeNull();
      expect(Math.abs(select!.y + select!.height / 2 - disclosure!.y - disclosure!.height / 2)).toBeLessThanOrEqual(2);
    }
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    await page.screenshot({ path: `${folder}/queue-${width}-${theme}.png`, fullPage: true });
  }
});
