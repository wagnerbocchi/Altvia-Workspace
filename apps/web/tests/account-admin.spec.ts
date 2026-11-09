import { test, expect, type Page, type BrowserContext } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const origin = "https://127.0.0.1:3443";
const adminEmail = process.env.ALTVIA_E2E_ADMIN_EMAIL!;
const adminPassword = process.env.ALTVIA_E2E_ADMIN_PASSWORD!;
const syntheticPassword = "Account browser proof 2026!";
const shots = fileURLToPath(new URL("../../../.impeccable/review/accounts/", import.meta.url));
let adminCookies: Awaited<ReturnType<BrowserContext["cookies"]>>;

test.beforeAll(async ({ request }) => {
  expect((await request.post("/api/v1/auth/sessions", { data: { email: adminEmail, password: adminPassword },
    headers: { Origin: origin } })).status()).toBe(201);
  adminCookies = (await request.storageState()).cookies;
});
test.beforeEach(async ({ context }) => { await context.addCookies(adminCookies); });

async function createAccount(page: Page, name = `Conta ${crypto.randomUUID().slice(0, 8)}`) {
  await page.goto("/admin/users");
  const email = `proof-${crypto.randomUUID()}@example.invalid`;
  await page.getByLabel("Nome da nova conta", { exact: true }).fill(name);
  await page.getByLabel("E-mail da nova conta", { exact: true }).fill(email);
  await page.getByLabel("Senha inicial", { exact: true }).fill(syntheticPassword);
  await page.getByRole("button", { name: "Criar conta", exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  return page.url().split("/").at(-1)!;
}

test("@accounts real account status password and admin lifecycle persists", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Administrar contas" }).click();
  const id = await createAccount(page);
  await page.getByRole("button", { name: "Desativar conta", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar desativação", exact: true }).click();
  await expect(page.getByText("Conta desativada", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Conta desativada", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Ativar conta", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar ativação", exact: true }).click();
  await expect(page.getByText("Conta ativa", { exact: true })).toBeVisible();
  await page.getByLabel("Nova senha", { exact: true }).fill(syntheticPassword + "changed");
  await page.getByRole("button", { name: "Redefinir senha", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar nova senha", exact: true }).click();
  await expect(page.getByLabel("Nova senha", { exact: true })).toHaveValue("");
  await page.getByRole("button", { name: "Conceder administração", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar concessão", exact: true }).click();
  await expect(page.getByText("Administrador da plataforma", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Revogar administração", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar revogação", exact: true }).click();
  await expect(page.getByText("Sem administração da plataforma", { exact: true })).toBeVisible();
  const account = await (await page.request.get(`/api/v1/users/${id}`)).json();
  expect(account.version).toBe(6);
});

test("@accounts lost create reply replays original intent and clears credential input", async ({ page }) => {
  let calls = 0;
  const keys: string[] = [];
  await page.route("**/api/v1/users", async route => {
    if (route.request().method() !== "POST") return route.continue();
    keys.push(route.request().headers()["idempotency-key"]);
    const response = await route.fetch();
    if (++calls === 1) await route.abort("failed"); else await route.fulfill({ response });
  });
  await page.goto("/admin/users");
  await page.getByLabel("Nome da nova conta").fill("Resposta perdida");
  await page.getByLabel("E-mail da nova conta").fill(`lost-${crypto.randomUUID()}@example.invalid`);
  await page.getByLabel("Senha inicial").fill(syntheticPassword);
  await page.getByRole("button", { name: "Criar conta", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar resultado" })).toBeVisible();
  await expect(page.getByLabel("Senha inicial")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Criar conta", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Verificar resultado" }).click();
  await expect(page.getByRole("heading", { name: "Resposta perdida", exact: true })).toBeVisible();
  expect(calls).toBe(2); expect(keys[0]).toBeTruthy(); expect(keys[0]).toBe(keys[1]);
  expect(await page.evaluate(() => JSON.stringify({ local: localStorage, session: sessionStorage,
    html: document.documentElement.outerHTML }))).not.toContain(syntheticPassword);
});

test("@accounts scoped role grant and revoke use existing teams without roster grant", async ({ page }) => {
  const id = await createAccount(page);
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const name = `Escopo ${crypto.randomUUID().slice(0, 8)}`;
  const team = await (await page.request.post("/api/v1/teams", { data: { name }, headers: {
    Origin: origin, "X-CSRF-Token": me.csrf_token, "Idempotency-Key": crypto.randomUUID(),
  } })).json();
  await page.reload();
  const choice = page.getByRole("radio", { name: new RegExp(name) });
  await expect(page.getByRole("group", { name: "Equipe para acesso" })).toBeVisible();
  if (!(await choice.count())) await page.getByRole("button", { name: "Próximas equipes" }).click();
  await choice.check();
  await page.getByRole("button", { name: "Conceder acesso à equipe", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar acesso", exact: true }).click();
  const roles = page.getByRole("list", { name: "Acessos concedidos" });
  await expect(roles).toContainText(name);
  expect((await (await page.request.get(`/api/v1/teams/${team.id}/members`)).json()).items).toHaveLength(0);
  expect((await (await page.request.get(`/api/v1/users/${id}/team-roles`)).json()).items).toHaveLength(1);
  await roles.getByRole("button", { name: "Revogar acesso", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar revogação", exact: true }).click();
  await expect(page.getByText("Nenhum acesso a equipes concedido.")).toBeVisible();
});

test("@accounts last administrator has actionable refusal and ordinary accounts have no admin queries", async ({ page, browser }) => {
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  await page.goto(`/admin/users/${me.id}`);
  await page.getByRole("button", { name: "Revogar administração", exact: true }).click();
  await expect(page.getByText("Sua sessão será encerrada.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Confirmar revogação", exact: true }).click();
  await expect(page.getByText("Mantenha pelo menos um administrador ativo.", { exact: false })).toBeVisible();
  const ordinaryEmail = `denied-${crypto.randomUUID()}@example.invalid`;
  expect((await page.request.post("/api/v1/users", { data: {
    email: ordinaryEmail, display_name: "Conta sem acesso administrativo", password: syntheticPassword,
  }, headers: { Origin: origin, "X-CSRF-Token": me.csrf_token,
    "Idempotency-Key": crypto.randomUUID() } })).status()).toBe(201);
  const ordinary = await browser.newContext({ ignoreHTTPSErrors: true });
  const plain = await ordinary.newPage();
  let privateReads = 0;
  plain.on("request", request => { if (/\/api\/v1\/(users|teams)/.test(request.url())) privateReads++; });
  await plain.goto("/admin/users");
  await plain.getByLabel("E-mail", { exact: true }).fill(ordinaryEmail);
  await plain.getByLabel("Senha", { exact: true }).fill(syntheticPassword);
  await plain.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(plain.getByRole("heading", { name: "Acesso restrito" })).toBeVisible();
  expect(privateReads).toBe(0);
  await ordinary.close();
});

test("@accounts responsive themed account pages have keyboard access and no serious axe violations", async ({ page }) => {
  await mkdir(shots, { recursive: true });
  await createAccount(page, "Conta de validação visual");
  for (const theme of ["light", "dark"]) {
    await page.evaluate(value => localStorage.setItem("theme", value), theme);
    await page.reload();
    await expect(page.getByText("Conta ativa", { exact: true })).toBeVisible();
    for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
      await page.setViewportSize({ width, height: 1000 });
      await expect(page.getByRole("button", { name: "Desativar conta", exact: true })).toBeEnabled();
      await page.screenshot({ path: `${shots}/${size}-${theme}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations.filter(row => ["serious", "critical"].includes(row.impact ?? ""))).toEqual([]);
    }
  }
});

test("@accounts lost password reply survives independent read recovery and replays once", async ({ page }) => {
  const id = await createAccount(page);
  const keys: string[] = [];
  let posts = 0;
  await page.route(`**/api/v1/users/${id}/password`, async route => {
    keys.push(route.request().headers()["idempotency-key"]);
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    if (++posts === 1) await route.abort("failed"); else await route.fulfill({ response });
  });
  await page.getByLabel("Nova senha", { exact: true }).fill(syntheticPassword + " recovery");
  await page.getByRole("button", { name: "Redefinir senha", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar nova senha", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar resultado" })).toBeVisible();
  await expect(page.getByLabel("Nova senha", { exact: true })).toHaveValue("");
  await page.route(`**/api/v1/users/${id}`, route => route.abort());
  const failedRead = page.waitForEvent("requestfailed", { predicate: request => request.url().endsWith(`/users/${id}`) });
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await failedRead;
  const retry = page.getByRole("button", { name: "Tentar carregar novamente" }).first();
  await expect(retry).toBeVisible();
  await page.unroute(`**/api/v1/users/${id}`);
  await retry.click();
  await expect(page.getByRole("button", { name: "Verificar resultado" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Desativar conta", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Verificar resultado" }).click();
  await expect(page.getByRole("button", { name: "Desativar conta", exact: true })).toBeEnabled();
  expect(posts).toBe(2); expect(keys[0]).toBe(keys[1]);
  expect((await (await page.request.get(`/api/v1/users/${id}`)).json()).version).toBe(2);
});

test("@accounts stale confirmation requires reload rather than overwriting current account", async ({ page }) => {
  const id = await createAccount(page);
  await page.getByRole("button", { name: "Desativar conta", exact: true }).click();
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  expect((await page.request.post(`/api/v1/users/${id}/password`, {
    data: { password: syntheticPassword }, headers: { Origin: origin, "X-CSRF-Token": me.csrf_token,
      "If-Match": '"1"', "Idempotency-Key": crypto.randomUUID() },
  })).status()).toBe(200);
  await page.getByRole("button", { name: "Confirmar desativação", exact: true }).click();
  await expect(page.getByText("Os dados foram alterados em outra sessão.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Desativar conta", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Recarregar dados", exact: true }).click();
  await expect(page.getByRole("button", { name: "Desativar conta", exact: true })).toBeEnabled();
  await expect(page.getByText("Conta ativa", { exact: true })).toBeVisible();
});

test("@accounts resetting own password disposes session and returns to real login", async ({ page, browser }) => {
  const id = await createAccount(page);
  const account = await (await page.request.get(`/api/v1/users/${id}`)).json();
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  expect((await page.request.post(`/api/v1/users/${id}/platform-admin`, {
    data: { enabled: true }, headers: { Origin: origin, "X-CSRF-Token": me.csrf_token,
      "If-Match": '"1"', "Idempotency-Key": crypto.randomUUID() },
  })).status()).toBe(200);
  const separate = await browser.newContext({ ignoreHTTPSErrors: true });
  const own = await separate.newPage();
  await own.goto(`/admin/users/${id}`);
  await own.getByLabel("E-mail", { exact: true }).fill(account.email);
  await own.getByLabel("Senha", { exact: true }).fill(syntheticPassword);
  await own.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(own.getByRole("heading", { name: account.display_name, exact: true })).toBeVisible();
  await own.getByLabel("Nova senha", { exact: true }).fill(syntheticPassword + " own");
  await own.getByRole("button", { name: "Redefinir senha", exact: true }).click();
  await expect(own.getByText("Sua sessão será encerrada.", { exact: false })).toBeVisible();
  await own.getByRole("button", { name: "Confirmar nova senha", exact: true }).click();
  await expect(own.getByRole("heading", { name: "Acesse seu workspace", exact: true })).toBeVisible();
  expect((await own.request.get("/api/v1/auth/me")).status()).toBe(401);
  await expect(own.getByLabel("Senha", { exact: true })).toHaveValue("");
  await separate.close();
});
