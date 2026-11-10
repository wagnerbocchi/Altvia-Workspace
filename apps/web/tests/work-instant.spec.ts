import { test, expect, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { loginWork } from "./work-session";

const origin = "https://127.0.0.1:3443";
const project = process.env.ALTVIA_E2E_WORK_PROJECT_ID!;
const shots = fileURLToPath(new URL("../../../.impeccable/review/work-items/", import.meta.url));
async function captureInstant(page: Page, prefix: string) {
  await mkdir(shots, { recursive: true });
  await expect(page.getByRole("status").filter({ hasText: /^Carregando/ })).toHaveCount(0);
  for (const [device, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      await page.evaluate(value => { document.documentElement.classList.toggle("dark", value === "dark"); scrollTo(0, 0); }, theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `${shots}/${prefix}-${device}-${theme}.png`, fullPage: true });
    }
  }
}
async function login(page: Page, kind = "REVIEW_MANAGER") {
  return loginWork(page, kind);
}
async function headers(page: Page, version = 1) {
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  return { Origin: origin, "X-CSRF-Token": me.csrf_token, "Idempotency-Key": crypto.randomUUID(), "If-Match": `"${version}"` };
}

test("@work-instant unrelated edit preserves exact instant and repeated clock occurrence", async ({ browser }) => {
  const context = await browser.newContext({ baseURL: origin, ignoreHTTPSErrors: true, timezoneId: "America/New_York" });
  try {
    const page = await context.newPage(); await login(page);
    for (const instant of ["2026-11-09T12:34:56.789Z", "2026-11-01T06:30:00Z"]) {
      const response = await page.request.post("/api/v1/work-items", { data: { project_id: project, title: "Instante preservado", priority: "medium", work_type: "one_off", due: { precision: "instant", instant } }, headers: await headers(page) });
      expect(response.status()).toBe(201); const id = (await response.json()).work_item_id;
      await page.goto(`/work-items/${id}`);
      await page.getByRole("button", { name: "Editar tarefa", exact: true }).click();
      await page.getByLabel("Título", { exact: true }).fill("Somente título revisado");
      const request = page.waitForRequest(value => value.method() === "PATCH" && value.url().endsWith(`/work-items/${id}`));
      await page.getByRole("button", { name: "Salvar tarefa", exact: true }).click();
      expect((await request).postDataJSON()).not.toHaveProperty("due");
      await expect(page.getByRole("heading", { name: "Somente título revisado", exact: true })).toBeVisible();
      const saved = await (await page.request.get(`/api/v1/work-items/${id}`)).json();
      expect(new Date(saved.due.instant).toISOString()).toBe(new Date(instant).toISOString());
      await expect(page.getByRole("definition").filter({ hasText: "America/New_York" })).toBeVisible();
      if (instant === "2026-11-09T12:34:56.789Z") await captureInstant(page, "instant-detail");
      await page.getByRole("link", { name: "Voltar às tarefas", exact: true }).click();
      await expect(page.getByRole("list", { name: "Tarefas do projeto", exact: true })).toContainText("America/New_York");
      if (instant === "2026-11-09T12:34:56.789Z") await captureInstant(page, "instant-directory");
      await page.goto(`/work-items/${id}`);
      await page.getByRole("button", { name: "Editar tarefa", exact: true }).click();
      await page.getByLabel("Data e hora limite", { exact: true }).fill("2026-11-11T13:14:15.123");
      await page.getByRole("button", { name: "Salvar tarefa", exact: true }).click();
      await expect(page.getByRole("button", { name: "Editar tarefa", exact: true })).toBeVisible();
      expect(new Date((await (await page.request.get(`/api/v1/work-items/${id}`)).json()).due.instant).toISOString()).toBe("2026-11-11T18:14:15.123Z");
      await page.getByRole("button", { name: "Editar tarefa", exact: true }).click();
      await page.getByLabel("Data e hora limite", { exact: true }).fill("2026-11-01T01:30");
      await page.getByRole("button", { name: "Salvar tarefa", exact: true }).click();
      await expect(page.getByText("Esse horário ocorre duas vezes", { exact: false })).toBeVisible();
      await page.getByLabel("Fuso da hora limite", { exact: true }).selectOption("utc");
      await page.getByLabel("Data e hora limite", { exact: true }).fill("2026-11-01T06:30");
      await page.getByRole("button", { name: "Salvar tarefa", exact: true }).click();
      await expect(page.getByRole("button", { name: "Editar tarefa", exact: true })).toBeVisible();
      expect((await (await page.request.get(`/api/v1/work-items/${id}`)).json()).due.instant).toBe("2026-11-01T06:30:00Z");
    }
  } finally { await context.close(); }
});

test("@work-history two contributors remain identifiable with relevant changed fields", async ({ page }) => {
  const manager = await login(page);
  const people = await (await page.request.get(`/api/v1/projects/${project}/work-candidates`)).json();
  const agentId = people.items.find((row: { display_name: string }) => row.display_name === "Agente de revisão").id;
  const created = await page.request.post("/api/v1/work-items", { data: { project_id: project, title: "Histórico atribuível", priority: "low", work_type: "one_off", owner_id: manager.id, assignee_ids: [agentId] }, headers: await headers(page) });
  expect(created.status()).toBe(201); const id = (await created.json()).work_item_id;
  expect((await page.request.post(`/api/v1/work-items/${id}/comments`, { data: { body: "Comentário do gestor" }, headers: await headers(page) })).status()).toBe(201);
  const agent = await login(page, "REVIEW_AGENT");
  expect((await page.request.post(`/api/v1/work-items/${id}/comments`, { data: { body: "Comentário do agente" }, headers: await headers(page, 2) })).status()).toBe(201);
  expect((await page.request.post(`/api/v1/work-items/${id}/transitions`, { data: { target_status: "in_progress" }, headers: await headers(page, 3) })).status()).toBe(200);
  expect((await page.request.patch(`/api/v1/work-items/${id}`, { data: { description: "Mudança atribuída" }, headers: await headers(page, 4) })).status()).toBe(200);
  await login(page); await page.goto(`/work-items/${id}`);
  const comments = page.getByRole("list", { name: "Comentários internos", exact: true });
  await expect(comments.getByRole("listitem").filter({ hasText: "Comentário do gestor" })).toContainText(manager.id);
  await expect(comments.getByRole("listitem").filter({ hasText: "Comentário do agente" })).toContainText(agent.id);
  await expect(page.getByRole("list", { name: "Histórico de estados", exact: true }).getByRole("listitem").filter({ hasText: "A fazer para Em andamento" })).toContainText(agent.id);
  await expect.poll(async () => {
    const response = await page.request.get(`/api/v1/work-items/${id}/activity`);
    return (await response.json()).items.some((row: { details: { changed_fields?: string } }) => row.details.changed_fields?.split(",").includes("description"));
  }, { timeout: 20000 }).toBe(true);
  await page.getByRole("button", { name: "Atualizar atividade", exact: true }).click();
  await expect(page.getByRole("list", { name: "Atividade da tarefa", exact: true })).toContainText("Campos alterados: Descrição");
});
