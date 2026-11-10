import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const origin = "https://127.0.0.1:3443";
const shots = fileURLToPath(new URL("../../../.impeccable/review/clients/", import.meta.url));

test.beforeAll(async ({ request }) => {
  // The account suite first proves the last-admin guard with exactly one admin.
  // Elevate this isolated fixture only when the client suite actually starts.
  const login = await request.post("/api/v1/auth/sessions", { data: {
    email: process.env.ALTVIA_E2E_ADMIN_EMAIL!, password: process.env.ALTVIA_E2E_ADMIN_PASSWORD!,
  }, headers: { Origin: origin } });
  expect(login.status()).toBe(201);
  const people = (await (await request.get("/api/v1/users?limit=100")).json()).items;
  const manager = people.find((person: { email: string }) => person.email === process.env.ALTVIA_E2E_CLIENT_ADMIN_EMAIL);
  expect(manager).toBeTruthy();
  const detail = await (await request.get(`/api/v1/users/${manager.id}`)).json();
  const granted = await request.post(`/api/v1/users/${manager.id}/platform-admin`, { data: { enabled: true }, headers: {
    Origin: origin, "X-CSRF-Token": (await login.json()).csrf_token,
    "Idempotency-Key": crypto.randomUUID(), "If-Match": `"${detail.version}"`,
  } });
  expect(granted.status()).toBe(200);
});

for (const mode of ["paging", "recovery"]) {
  test(`@clients @client-submit ${mode} inside a populated form never provisions a client`, async ({ page }) => {
    const login = await page.request.post("/api/v1/auth/sessions", { data: {
      email: process.env.ALTVIA_E2E_CLIENT_ADMIN_EMAIL!, password: process.env.ALTVIA_E2E_CLIENT_ADMIN_PASSWORD!,
    }, headers: { Origin: origin } });
    expect(login.status()).toBe(201);
    const me = (await login.json()).user;
    let creations = 0;
    page.on("request", request => { if (request.method() === "POST" && new URL(request.url()).pathname === "/api/v1/clients") creations++; });
    if (mode === "recovery") await page.route("**/api/v1/users?*", route => route.abort());
    await page.goto("/clients");
    await page.getByLabel("Nome do cliente", { exact: true }).fill("Cadastro ainda não confirmado");
    await page.getByLabel("Gestor inicial", { exact: true }).selectOption(me.id);
    if (mode === "recovery") {
      await expect(page.getByRole("button", { name: "Tentar carregar novamente", exact: true })).toBeVisible();
      await page.unroute("**/api/v1/users?*");
    }
    const response = page.waitForResponse(result => result.url().includes("/api/v1/users?") && result.ok());
    await page.getByRole("button", { name: mode === "paging" ? "Próximas contas" : "Tentar carregar novamente", exact: true }).click();
    await response;
    expect(creations).toBe(0);
    await expect(page.getByRole("button", { name: "Cadastrar cliente", exact: true })).toBeEnabled();
    await expect(page.getByLabel("Nome do cliente", { exact: true })).toHaveValue("Cadastro ainda não confirmado");
  });
}

test("@clients explicit self-delegation, persisted lifecycle and scoped history", async ({ page }) => {
  const email = process.env.ALTVIA_E2E_CLIENT_ADMIN_EMAIL!;
  const password = process.env.ALTVIA_E2E_CLIENT_ADMIN_PASSWORD!;
  const login = await page.request.post("/api/v1/auth/sessions", { data: { email, password }, headers: { Origin: origin } });
  expect(login.status()).toBe(201);
  const me = (await login.json()).user;
  await page.goto("/clients");
  await expect(page.getByRole("heading", { name: "Clientes", exact: true })).toBeVisible();
  const name = `Cliente de validação ${crypto.randomUUID().slice(0, 8)}`;
  await page.getByLabel("Nome do cliente", { exact: true }).fill(name);
  await page.getByLabel("Gestor inicial", { exact: true }).selectOption(me.id);
  await page.getByRole("button", { name: "Cadastrar cliente", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeVisible();
  await page.getByLabel("E-mail", { exact: true }).fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("link", { name, exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Renomear cliente", exact: true }).click();
  const renamed = `${name} atualizado`;
  await page.getByLabel("Nome do cliente", { exact: true }).fill(renamed);
  await page.getByRole("button", { name: "Salvar nome", exact: true }).click();
  await expect(page.getByRole("heading", { name: renamed, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Arquivar cliente", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Arquivar este cliente?", exact: true })).toBeFocused();
  await mkdir(shots, { recursive: true });
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${shots}/confirmation-mobile-light.png`, fullPage: true });
  await page.getByRole("button", { name: "Confirmar arquivamento", exact: true }).click();
  await expect(page.getByText("Cliente arquivado", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Restaurar cliente", exact: true }).click();
  await expect(page.getByText("Cliente ativo", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: renamed, exact: true })).toBeVisible();
  await expect.poll(async () => (await (await page.request.get(`${new URL(page.url()).pathname.replace("/clients/", "/api/v1/clients/")}/activity`)).json()).items.length).toBeGreaterThanOrEqual(4);
  await page.getByRole("button", { name: "Atualizar histórico", exact: true }).click();
  await expect(page.getByText("Cliente cadastrado", { exact: true })).toBeVisible();
  await page.route("**/api/v1/clients/*/activity?*", route => route.abort());
  await page.getByRole("button", { name: "Atualizar histórico", exact: true }).click();
  await expect(page.getByRole("button", { name: "Tentar carregar novamente", exact: true })).toBeVisible();
  await page.unroute("**/api/v1/clients/*/activity?*");
  await page.getByRole("button", { name: "Tentar carregar novamente", exact: true }).click();
  await expect(page.getByText("Cliente cadastrado", { exact: true })).toBeVisible();
  await mkdir(shots, { recursive: true });
  for (const theme of ["light", "dark"]) {
    await page.evaluate(value => localStorage.setItem("theme", value), theme);
    await page.reload();
    await expect(page.getByText("Cliente cadastrado", { exact: true })).toBeVisible();
    for (const [viewport, width] of [["desktop", 1440], ["mobile", 390]] as const) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: `${shots}/${viewport}-${theme}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    }
  }
  await page.getByRole("link", { name: "Voltar aos clientes", exact: true }).click();
  await expect(page).toHaveURL(/\/clients$/);
  for (const theme of ["light", "dark"]) {
    await page.evaluate(value => localStorage.setItem("theme", value), theme);
    await page.reload();
    await expect(page.getByRole("link", { name: renamed, exact: true })).toBeVisible();
    await expect(page.getByText("Carregando gestores...", { exact: true })).toBeHidden();
    for (const [viewport, width] of [["desktop", 1440], ["mobile", 390]] as const) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: `${shots}/directory-${viewport}-${theme}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    }
  }
});

test("@clients lost creation response replays one explicit delegation to another manager", async ({ page }) => {
  const login = await page.request.post("/api/v1/auth/sessions", { data: {
    email: process.env.ALTVIA_E2E_CLIENT_ADMIN_EMAIL!, password: process.env.ALTVIA_E2E_CLIENT_ADMIN_PASSWORD!,
  }, headers: { Origin: origin } });
  expect(login.status()).toBe(201);
  const people = (await (await page.request.get("/api/v1/users?limit=100")).json()).items;
  const manager = people.find((person: { email: string }) => person.email === process.env.ALTVIA_E2E_EMAIL);
  expect(manager).toBeTruthy();
  await page.goto("/clients");
  const select = page.getByLabel("Gestor inicial", { exact: true });
  const managerPage = Math.floor(people.findIndex((person: { id: string }) => person.id === manager.id) / 10);
  for (let index = 0; index < managerPage; index++) {
    await expect(page.getByRole("button", { name: "Próximas contas", exact: true })).toBeEnabled();
    const response = page.waitForResponse(result => result.url().includes("/api/v1/users?") && result.request().method() === "GET" && result.ok());
    await page.getByRole("button", { name: "Próximas contas", exact: true }).click();
    await response;
    await expect(page.getByRole("navigation", { name: "Páginas de contas" })).toContainText(`Página ${index + 2}`);
  }
  await select.selectOption(manager.id);
  const name = `Cadastro com resposta perdida ${crypto.randomUUID().slice(0, 8)}`;
  await page.getByLabel("Nome do cliente", { exact: true }).fill(name);
  const attempts: { key: string | undefined; body: string | null }[] = [];
  let identifier = "";
  await page.route("**/api/v1/clients", async route => {
    if (route.request().method() !== "POST") { await route.continue(); return; }
    attempts.push({ key: route.request().headers()["idempotency-key"], body: route.request().postData() });
    const response = await route.fetch();
    identifier = (await response.json()).client_id;
    if (attempts.length === 1) await route.abort(); else await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Cadastrar cliente", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar cadastro", exact: true })).toBeVisible();
  await expect(page.getByLabel("Nome do cliente", { exact: true })).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${shots}/uncertain-mobile-light.png`, fullPage: true });
  await page.getByRole("button", { name: "Verificar cadastro", exact: true }).click();
  await expect(page.getByText("Cliente cadastrado para o gestor escolhido. Ele precisará entrar novamente para usar o novo acesso.", { exact: true })).toBeVisible();
  expect(attempts).toHaveLength(2);
  expect(attempts[1]).toEqual(attempts[0]);
  expect((await page.request.get(`/api/v1/clients/${identifier}`)).status()).toBe(404);
  const managerLogin = await page.request.post("/api/v1/auth/sessions", { data: {
    email: process.env.ALTVIA_E2E_EMAIL!, password: process.env.ALTVIA_E2E_PASSWORD!,
  }, headers: { Origin: origin } });
  expect(managerLogin.status()).toBe(201);
  await page.reload();
  await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
});

test("@clients real stale edit survives failed read recovery before deliberate discard", async ({ page }) => {
  const login = await page.request.post("/api/v1/auth/sessions", { data: {
    email: process.env.ALTVIA_E2E_CLIENT_ADMIN_EMAIL!, password: process.env.ALTVIA_E2E_CLIENT_ADMIN_PASSWORD!,
  }, headers: { Origin: origin } });
  expect(login.status()).toBe(201);
  const csrf = (await login.json()).csrf_token;
  const row = (await (await page.request.get("/api/v1/clients")).json()).items[0];
  expect(row).toBeTruthy();
  await page.goto(`/clients/${row.id}`);
  await page.getByRole("button", { name: "Renomear cliente", exact: true }).click();
  await page.getByLabel("Nome do cliente", { exact: true }).fill("Minha edição pendente");
  const outside = await page.request.patch(`/api/v1/clients/${row.id}`, { data: { name: "Nome atualizado em outra sessão" }, headers: {
    Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${row.version}"`,
  } });
  expect(outside.status()).toBe(200);
  await page.getByRole("button", { name: "Salvar nome", exact: true }).click();
  const discard = page.getByRole("button", { name: "Recarregar e descartar edição", exact: true });
  await expect(discard).toBeVisible();
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${shots}/version-conflict-mobile-light.png`, fullPage: true });
  await page.route(`**/api/v1/clients/${row.id}`, route => route.abort());
  await discard.click();
  await expect(page.getByRole("button", { name: "Tentar carregar novamente", exact: true })).toBeVisible();
  await page.unroute(`**/api/v1/clients/${row.id}`);
  await page.getByRole("button", { name: "Tentar carregar novamente", exact: true }).click();
  await expect(page.getByLabel("Nome do cliente", { exact: true })).toHaveValue("Minha edição pendente");
  await expect(page.getByRole("button", { name: "Salvar nome", exact: true })).toBeDisabled();
  await discard.click();
  await expect(page.getByRole("heading", { name: "Nome atualizado em outra sessão", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Renomear cliente", exact: true })).toBeEnabled();
});

test("@clients ungranted account gets a real empty directory and safe denied detail", async ({ page }) => {
  const admin = await page.request.post("/api/v1/auth/sessions", { data: {
    email: process.env.ALTVIA_E2E_CLIENT_ADMIN_EMAIL!, password: process.env.ALTVIA_E2E_CLIENT_ADMIN_PASSWORD!,
  }, headers: { Origin: origin } });
  expect(admin.status()).toBe(201);
  const ungrantedEmail = `ungranted-${crypto.randomUUID()}@example.invalid`;
  const account = await page.request.post("/api/v1/users", { data: {
    email: ungrantedEmail, display_name: "Pessoa sem clientes", password: process.env.ALTVIA_E2E_PASSWORD!,
  }, headers: { Origin: origin, "X-CSRF-Token": (await admin.json()).csrf_token, "Idempotency-Key": crypto.randomUUID() } });
  expect(account.status()).toBe(201);
  const login = await page.request.post("/api/v1/auth/sessions", { data: {
    email: ungrantedEmail, password: process.env.ALTVIA_E2E_PASSWORD!,
  }, headers: { Origin: origin } });
  expect(login.status()).toBe(201);
  await page.goto("/clients");
  await expect(page.getByText("Nenhum cliente disponível para sua conta.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Novo cliente", exact: true })).toBeHidden();
  await page.goto(`/clients/${crypto.randomUUID()}`);
  await expect(page.getByText("Este cliente não está disponível para sua conta.", { exact: true })).toBeVisible();
});
