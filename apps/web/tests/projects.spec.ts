import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const origin = "https://127.0.0.1:3443";
const shots = fileURLToPath(new URL("../../../.impeccable/review/projects/", import.meta.url));
const email = process.env.ALTVIA_E2E_PROJECT_ADMIN_EMAIL!;
const password = process.env.ALTVIA_E2E_PROJECT_ADMIN_PASSWORD!;

test.beforeAll(async ({ request }) => {
  const login = await request.post("/api/v1/auth/sessions", { data: {
    email: process.env.ALTVIA_E2E_ADMIN_EMAIL!, password: process.env.ALTVIA_E2E_ADMIN_PASSWORD!,
  }, headers: { Origin: origin } });
  expect(login.status()).toBe(201);
  const people = (await (await request.get("/api/v1/users?limit=100")).json()).items;
  const manager = people.find((person: { email: string }) => person.email === email);
  const detail = await (await request.get(`/api/v1/users/${manager.id}`)).json();
  expect((await request.post(`/api/v1/users/${manager.id}/platform-admin`, { data: { enabled: true }, headers: {
    Origin: origin, "X-CSRF-Token": (await login.json()).csrf_token,
    "Idempotency-Key": crypto.randomUUID(), "If-Match": `"${detail.version}"`,
  } })).status()).toBe(200);
});

async function login(page: Page) {
  const response = await page.request.post("/api/v1/auth/sessions", { data: { email, password }, headers: { Origin: origin } });
  expect(response.status()).toBe(201);
  return (await response.json()).user;
}
async function headers(page: Page, version?: number) {
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  return { Origin: origin, "X-CSRF-Token": me.csrf_token, "Idempotency-Key": crypto.randomUUID(),
    ...(version ? { "If-Match": `"${version}"` } : {}) };
}
async function selectTeam(page: Page, id: string) {
  const control = page.getByLabel("Equipe responsável", { exact: true });
  await expect(control.locator("option")).not.toHaveCount(1);
  const nav = page.getByRole("navigation", { name: "Páginas de equipe responsável", exact: true });
  for (let attempt = 0; attempt < 10; attempt++) {
    if (await control.locator(`option[value="${id}"]`).count()) { await control.selectOption(id); return; }
    const response = page.waitForResponse(result => result.url().includes("/api/v1/teams?") && result.ok());
    await nav.getByRole("button", { name: "Próximas equipes", exact: true }).click();
    const rows = (await (await response).json()).items;
    const active = rows.find((row: { active: boolean }) => row.active);
    if (active) await expect(control.locator(`option[value="${active.id}"]`)).toHaveCount(1);
  }
  throw Error("Fixture team not found in bounded selection");
}
async function captures(page: Page, prefix: string) {
  await mkdir(shots, { recursive: true });
  for (const [device, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      await page.evaluate(value => { document.documentElement.dataset.theme = value; document.documentElement.classList.toggle("dark", value === "dark"); }, theme);
      await page.evaluate(() => window.scrollTo(0, 0));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: `${shots}/${prefix}-${device}-${theme}.png`, fullPage: true });
    }
  }
}

test("@projects operational areas persist and retain deliberate archived state", async ({ page }) => {
  await login(page);
  await page.goto("/operational-areas");
  await expect(page.getByRole("heading", { name: "Áreas operacionais", exact: true })).toBeVisible();
  const name = `Área de validação ${crypto.randomUUID().slice(0, 8)}`;
  await page.getByLabel("Nome da nova área").fill(name);
  await page.getByRole("button", { name: "Cadastrar área", exact: true }).click();
  const row = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name, exact: true }) });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Renomear área", exact: true }).click();
  await row.getByLabel("Nome da área", { exact: true }).fill(name + " revisada");
  await row.getByRole("button", { name: "Salvar nome", exact: true }).click();
  const renamed = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: name + " revisada", exact: true }) });
  await renamed.getByRole("button", { name: "Arquivar área", exact: true }).click();
  await renamed.getByRole("button", { name: "Confirmar arquivamento", exact: true }).click();
  await expect(renamed.getByText("Área arquivada", { exact: true })).toBeVisible();
  await page.reload();
  await expect(renamed.getByText("Área arquivada", { exact: true })).toBeVisible();
  await renamed.getByRole("button", { name: "Restaurar área", exact: true }).click();
  await expect(renamed.getByText("Área ativa", { exact: true })).toBeVisible();
  await captures(page, "areas");
});

test("@projects explicit self-manager relogin and real project lifecycle", async ({ page }) => {
  const me = await login(page);
  const team = await page.request.post("/api/v1/teams", { data: { name: "Equipe do projeto de validação" }, headers: await headers(page) });
  expect(team.status()).toBe(201);
  const teamId = (await team.json()).id;
  const classification = await page.request.post("/api/v1/operational-areas", { data: { name: `Classificação ${crypto.randomUUID().slice(0, 8)}` }, headers: await headers(page) });
  expect(classification.status()).toBe(201);
  const classificationRow = await classification.json();
  await page.goto("/projects");
  const name = `Projeto de validação ${crypto.randomUUID().slice(0, 8)}`;
  await page.getByLabel("Nome do projeto", { exact: true }).fill(name);
  await selectTeam(page, teamId);
  await page.getByLabel("Gestor inicial", { exact: true }).selectOption(me.id);
  await page.getByLabel("Área do projeto", { exact: true }).selectOption(classificationRow.id);
  await captures(page, "directory");
  await page.getByRole("button", { name: "Cadastrar projeto", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeVisible();
  await page.getByLabel("E-mail", { exact: true }).fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("link", { name, exact: true }).click();
  await expect(page.getByText(`Área: ${classificationRow.name}`, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Alterar área", exact: true }).click();
  await page.getByLabel("Área do projeto", { exact: true }).selectOption("");
  await page.getByRole("button", { name: "Salvar área", exact: true }).click();
  await expect(page.getByText("Sem área operacional", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Renomear projeto", exact: true }).click();
  await page.getByLabel("Nome do projeto", { exact: true }).fill(name + " revisado");
  await page.getByRole("button", { name: "Salvar nome", exact: true }).click();
  await expect(page.getByRole("heading", { name: name + " revisado", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Arquivar projeto", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Arquivar este projeto?", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Confirmar arquivamento", exact: true }).click();
  await expect(page.getByText("Projeto arquivado", { exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Restaurar projeto", exact: true }).click();
  await expect(page.getByText("Projeto ativo", { exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Participantes do projeto" })).toContainText(me.display_name);
  await expect.poll(async () => {
    await page.getByRole("button", { name: "Atualizar histórico", exact: true }).click();
    return page.getByText("Projeto cadastrado", { exact: true }).count();
  }).toBe(1);
  await captures(page, "detail");
});

test("@projects lost creation reply reuses original intent through independent read recovery", async ({ page, request }) => {
  const provisioningLogin = await request.post("/api/v1/auth/sessions", { data: {
    email: process.env.ALTVIA_E2E_ADMIN_EMAIL!, password: process.env.ALTVIA_E2E_ADMIN_PASSWORD!,
  }, headers: { Origin: origin } });
  expect(provisioningLogin.status()).toBe(201);
  const provisioningHeaders = { Origin: origin, "X-CSRF-Token": (await provisioningLogin.json()).csrf_token };
  const people = (await (await request.get("/api/v1/users?limit=100")).json()).items;
  const owner = people.find((row: { email: string }) => row.email === email);
  const seededTeam = await request.post("/api/v1/teams", { data: { name: "Equipe para paginação" }, headers: { ...provisioningHeaders, "Idempotency-Key": crypto.randomUUID() } });
  expect(seededTeam.status()).toBe(201);
  const seededTeamId = (await seededTeam.json()).id;
  for (let index = 0; index < 11; index++) {
    expect((await request.post("/api/v1/projects", { data: { name: `Projeto paginado ${index}`, scope_kind: "internal", team_id: seededTeamId, manager_user_id: owner.id }, headers: { ...provisioningHeaders, "Idempotency-Key": crypto.randomUUID() } })).status()).toBe(201);
  }
  const me = await login(page);
  const team = await page.request.post("/api/v1/teams", { data: { name: "Equipe da resposta perdida" }, headers: await headers(page) });
  const teamId = (await team.json()).id;
  await page.goto("/projects");
  await page.getByLabel("Nome do projeto", { exact: true }).fill("Projeto com resposta perdida");
  await selectTeam(page, teamId);
  const manager = page.getByLabel("Gestor inicial", { exact: true });
  await expect.poll(() => manager.locator("option").count()).toBeGreaterThan(2);
  const other = await manager.locator("option").evaluateAll((nodes, self) => nodes.map(node => (node as HTMLOptionElement).value).find(value => value && value !== self)!, me.id);
  await manager.selectOption(other);
  const intents: { key: string | undefined; body: string | null }[] = [];
  let first = true;
  await page.route("**/api/v1/projects", async route => {
    if (route.request().method() !== "POST") return route.continue();
    intents.push({ key: route.request().headers()["idempotency-key"], body: route.request().postData() });
    const response = await route.fetch();
    expect(response.status()).toBe(first ? 201 : 200);
    if (first) { first = false; await route.abort("failed"); } else await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Cadastrar projeto", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar cadastro", exact: true })).toBeVisible();
  await expect(page.getByLabel("Nome do projeto", { exact: true })).toBeDisabled();
  const nextPage = page.waitForResponse(result => result.url().includes("/api/v1/projects?") && result.url().includes("cursor=") && result.ok());
  await page.getByRole("button", { name: "Próximos projetos", exact: true }).click();
  await nextPage;
  await expect(page.getByRole("button", { name: "Verificar cadastro", exact: true })).toBeVisible();
  await page.route("**/api/v1/projects?*", route => route.abort());
  await page.getByRole("button", { name: "Atualizar projetos", exact: true }).click();
  await expect(page.getByRole("button", { name: "Tentar carregar novamente", exact: true })).toBeVisible();
  await page.unroute("**/api/v1/projects?*");
  const recovered = page.waitForResponse(result => result.url().includes("/api/v1/projects?") && result.url().includes("cursor=") && result.ok());
  await page.getByRole("button", { name: "Tentar carregar novamente", exact: true }).click();
  await recovered;
  await expect(page.getByRole("button", { name: "Tentar carregar novamente", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Verificar cadastro", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${shots}/uncertain-mobile-light.png`, fullPage: true });
  await page.getByRole("button", { name: "Verificar cadastro", exact: true }).click();
  await expect(page.getByRole("button", { name: "Cadastrar projeto", exact: true })).toBeEnabled();
  expect(intents).toHaveLength(2);
  expect(intents[1]).toEqual(intents[0]);
});

test("@projects version conflict preserves original edit until deliberate discard", async ({ page }) => {
  const me = await login(page);
  const team = await page.request.post("/api/v1/teams", { data: { name: "Equipe do conflito" }, headers: await headers(page) });
  const created = await page.request.post("/api/v1/projects", { data: { name: "Projeto antes do conflito", scope_kind: "internal", team_id: (await team.json()).id, manager_user_id: me.id }, headers: await headers(page) });
  expect(created.status()).toBe(201);
  const id = (await created.json()).project_id;
  await login(page);
  await page.goto(`/projects/${id}`);
  await page.getByRole("button", { name: "Renomear projeto", exact: true }).click();
  await page.getByLabel("Nome do projeto", { exact: true }).fill("Minha edição ainda não salva");
  expect((await page.request.patch(`/api/v1/projects/${id}`, { data: { name: "Nome de outra sessão" }, headers: await headers(page, 1) })).status()).toBe(200);
  await page.getByRole("button", { name: "Salvar nome", exact: true }).click();
  await expect(page.getByRole("button", { name: "Recarregar e descartar edição", exact: true })).toBeVisible();
  await expect(page.getByLabel("Nome do projeto", { exact: true })).toHaveValue("Minha edição ainda não salva");
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${shots}/conflict-mobile-light.png`, fullPage: true });
  await page.getByRole("button", { name: "Recarregar e descartar edição", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Nome de outra sessão", exact: true })).toBeVisible();
});

test("@projects an existing project manager without creation authority sees only the scoped directory", async ({ page }) => {
  await login(page);
  const ordinaryEmail = `project-reader-${crypto.randomUUID()}@example.invalid`;
  const user = await page.request.post("/api/v1/users", { data: { email: ordinaryEmail, display_name: "Gestor de projeto sem criação", password }, headers: await headers(page) });
  expect(user.status()).toBe(201);
  const team = await page.request.post("/api/v1/teams", { data: { name: "Equipe da consulta" }, headers: await headers(page) });
  const created = await page.request.post("/api/v1/projects", { data: { name: "Projeto já autorizado", scope_kind: "internal", team_id: (await team.json()).id, manager_user_id: (await user.json()).id }, headers: await headers(page) });
  expect(created.status()).toBe(201);
  expect((await page.request.post("/api/v1/auth/sessions", { data: { email: ordinaryEmail, password }, headers: { Origin: origin } })).status()).toBe(201);
  await page.goto("/projects");
  await expect(page.getByRole("link", { name: "Projeto já autorizado", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Novo projeto", exact: true })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${shots}/reader-mobile-light.png`, fullPage: true });
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
});
