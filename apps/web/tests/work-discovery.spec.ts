import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { loginWork } from "./work-session";

const project = process.env.ALTVIA_E2E_WORK_PROJECT_ID!;
const shots = fileURLToPath(new URL("../../../.impeccable/review/work-discovery/", import.meta.url));
async function task(page: Page, title: string, owner: string, ongoing = false) {
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const response = await page.request.post("/api/v1/work-items", { data: {
    project_id: project, title, description: "Pesquisa de manutenção em rede privada",
    priority: "high", work_type: ongoing ? "ongoing" : "one_off",
    owner_id: owner, assignee_ids: [owner],
  }, headers: { Origin: "https://127.0.0.1:3443", "X-CSRF-Token": me.csrf_token, "Idempotency-Key": crypto.randomUUID() } });
  expect(response.status()).toBe(201);
  return (await response.json()).work_item_id as string;
}
async function filter(page: Page, q: string) {
  await page.getByLabel("Buscar tarefas", { exact: true }).fill(q);
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
}
async function capture(page: Page, name: string) {
  await mkdir(shots, { recursive: true });
  await expect(page.getByRole("status").filter({ hasText: /^Carregando/ })).toHaveCount(0);
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      await page.evaluate(value => { document.documentElement.classList.toggle("dark", value === "dark"); scrollTo(0, 0); }, theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (size === "desktop" && name.endsWith("board")) {
        const lanes = await page.locator(".task-column h3").evaluateAll(elements => elements.map(element => {
          const { x, y, bottom } = element.getBoundingClientRect();
          return { x, y, bottom };
        }));
        expect(lanes).toHaveLength(5);
        expect(new Set(lanes.map(lane => lane.x)).size).toBe(5);
        expect(new Set(lanes.map(lane => lane.y)).size).toBe(1);
        expect(lanes.every(lane => lane.bottom < 1000)).toBe(true);
      }
      try {
        expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      } catch (error) {
        for (const [index, candidate] of page.context().pages().entries()) {
          if (candidate === page || candidate.isClosed()) continue;
          const raw = await candidate.evaluate(() => (window as unknown as { partialResults?: string }).partialResults);
          if (raw) await writeFile(`${shots}/axe-diagnostic-${index}.json`, raw);
        }
        throw error;
      }
      await page.screenshot({ path: `${shots}/${name}-${size}-${theme}.png`, fullPage: true });
    }
  }
}

test("@discovery project search and independently paged board use real tasks", async ({ page }) => {
  const user = await loginWork(page, "MANAGER");
  const term = `Fila${crypto.randomUUID().replaceAll("-", "")}`;
  for (let n = 0; n < 12; n++) await task(page, `${term} ${n}`, user.id);
  await task(page, `${term} contínua`, user.id, true);
  await page.goto(`/projects/${project}/work`);
  await filter(page, term);
  const list = page.getByRole("list", { name: "Tarefas do projeto", exact: true });
  await expect(list.getByRole("listitem")).toHaveCount(10);
  await page.getByRole("navigation", { name: "Páginas de tarefas", exact: true }).getByRole("button", { name: "Próximas tarefas", exact: true }).click();
  await expect(list.getByRole("listitem")).toHaveCount(3);
  await page.getByText("Filtros adicionais", { exact: true }).click();
  await page.getByLabel("Prioridade da tarefa", { exact: true }).selectOption("low");
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
  await expect(page.getByText("Nenhuma tarefa corresponde aos filtros.", { exact: true })).toBeVisible();
  await page.getByLabel("Prioridade da tarefa", { exact: true }).selectOption("");
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
  await expect(list.getByRole("listitem")).toHaveCount(10);
  await page.getByText("Filtros adicionais", { exact: true }).click();
  await page.getByRole("button", { name: "Quadro", exact: true }).click();
  const todo = page.getByRole("region", { name: "A fazer", exact: true });
  const active = page.getByRole("region", { name: "Em andamento", exact: true });
  await expect(todo.getByRole("listitem")).toHaveCount(10);
  await expect(active.getByRole("listitem")).toHaveCount(1);
  await todo.getByRole("button", { name: "Próximas tarefas", exact: true }).click();
  await expect(todo.getByRole("listitem")).toHaveCount(2);
  await expect(active.getByRole("listitem")).toHaveCount(1);
  await todo.getByRole("button", { name: "Tarefas anteriores", exact: true }).click();
  await capture(page, "board");
  await todo.getByRole("link").first().click();
  await page.getByLabel("Próximo estado", { exact: true }).selectOption("in_progress");
  await page.getByRole("button", { name: "Alterar estado", exact: true }).click();
  await expect(page.locator(".admin-intro")).toContainText("Em andamento");
});

test("@discovery personal queue deduplicates ownership and participation", async ({ page }) => {
  const user = await loginWork(page, "MANAGER");
  const title = `Pessoal${crypto.randomUUID().replaceAll("-", "")}`;
  const id = await task(page, title, user.id);
  await page.goto(`/projects/${project}/work`);
  await page.getByRole("link", { name: "Meu trabalho", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Meu trabalho", exact: true })).toBeVisible();
  await filter(page, title);
  await expect(page.getByLabel("Buscar tarefas", { exact: true })).toHaveValue(title);
  await expect(page.getByRole("link", { name: title, exact: true })).toHaveCount(1);
  await expect(page.getByRole("list", { name: "Minhas tarefas", exact: true }).getByRole("listitem")).toHaveCount(1);
  await capture(page, "personal");
  await page.getByRole("link", { name: title, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/work-items/${id}$`));
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  await loginWork(page, "READER");
  await page.goto("/my-work");
  await filter(page, title);
  await expect(page.getByRole("link", { name: title, exact: true })).toHaveCount(0);
});

test("@discovery a failed column retries without hiding other states", async ({ page }) => {
  const manager = await loginWork(page, "MANAGER");
  await task(page, "Tarefa para verificar recuperação", manager.id);
  await loginWork(page, "READER");
  await page.route("**/api/v1/work-items?**", route => {
    const url = new URL(route.request().url());
    return url.searchParams.get("status") === "blocked" ? route.abort() : route.continue();
  });
  await page.goto(`/projects/${project}/work`);
  await page.getByRole("button", { name: "Quadro", exact: true }).click();
  const blocked = page.getByRole("region", { name: "Bloqueada", exact: true });
  await expect(blocked.getByRole("button", { name: "Tentar carregar novamente", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "A fazer", exact: true }).getByRole("list")).toBeVisible();
  await page.unroute("**/api/v1/work-items?**");
  await blocked.getByRole("button", { name: "Tentar carregar novamente", exact: true }).click();
  await expect(blocked.getByRole("button", { name: "Tentar carregar novamente", exact: true })).toHaveCount(0);
  await page.getByLabel("Buscar tarefas", { exact: true }).focus();
  await page.keyboard.insertText("NadaCorrespondenteNestaFila");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Nenhuma tarefa nesta coluna.", { exact: true })).toHaveCount(5);
  await capture(page, "empty-board");
});

test("@discovery list recovery also recovers creation authority and archive state", async ({ page }) => {
  await loginWork(page, "MANAGER");
  await page.route("**/api/v1/work-items?**", route => route.abort());
  await page.goto(`/projects/${project}/work`);
  await expect(page.getByRole("button", { name: "Tentar carregar novamente", exact: true }).first()).toBeVisible();
  await page.unroute("**/api/v1/work-items?**");
  await page.getByRole("button", { name: "Tentar carregar novamente", exact: true }).first().click();
  await expect(page.getByLabel("Título da nova tarefa", { exact: true })).toBeVisible();
  // A fresh list observation must refresh the independent creation guard too.
  const changed = await (await page.request.get(`/api/v1/projects/${project}`)).json();
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const headers = { Origin: "https://127.0.0.1:3443", "X-CSRF-Token": me.csrf_token, "If-Match": `"${changed.version}"` };
  const archive = await page.request.patch(`/api/v1/projects/${project}`, { data: { active: false }, headers });
  expect(archive.status()).toBe(200);
  try {
    await page.getByRole("button", { name: "Atualizar tarefas", exact: true }).click();
    await expect(page.getByLabel("Título da nova tarefa", { exact: true })).toBeDisabled();
  } finally {
    const version = (await archive.json()).version;
    expect((await page.request.patch(`/api/v1/projects/${project}`, { data: { active: true }, headers: { ...headers, "If-Match": `"${version}"` } })).status()).toBe(200);
  }
});
