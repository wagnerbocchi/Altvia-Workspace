import { test, expect, type Page, type BrowserContext } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const adminEmail = process.env.ALTVIA_E2E_ADMIN_EMAIL!;
const adminPassword = process.env.ALTVIA_E2E_ADMIN_PASSWORD!;
const email = process.env.ALTVIA_E2E_EMAIL!;
const password = process.env.ALTVIA_E2E_PASSWORD!;
if (!adminEmail || !adminPassword) throw Error("Guarded admin browser fixture required");
const origin = "https://127.0.0.1:3443";
const root = fileURLToPath(new URL("../../../", import.meta.url));
const shots = fileURLToPath(new URL("../../../.impeccable/review/teams/", import.meta.url));
let adminCookies: Awaited<ReturnType<BrowserContext["cookies"]>>;

test.beforeAll(async ({ request }) => {
  // One real authenticated session per suite; do not weaken login throttling.
  expect((await request.post("/api/v1/auth/sessions", { data: { email: adminEmail, password: adminPassword },
    headers: { Origin: origin } })).status()).toBe(201);
  adminCookies = (await request.storageState()).cookies;
});
test.beforeEach(async ({ context }) => { await context.addCookies(adminCookies); });

async function signIn(page: Page, administrative = true) {
  await page.goto("/");
  if (!administrative) {
    await page.getByLabel("E-mail", { exact: true }).fill(email);
    await page.getByLabel("Senha", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Entrar", exact: true }).click();
  }
  await expect(page.getByRole("heading", { name: "Minha conta" })).toBeVisible();
}

async function createTeam(page: Page, name: string) {
  await page.goto("/admin/teams");
  await page.getByLabel("Nome da nova equipe").fill(name);
  await page.getByRole("button", { name: "Criar equipe", exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  return page.url().split("/").at(-1)!;
}

async function headers(page: Page, version?: number) {
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  return { Origin: origin, "X-CSRF-Token": me.csrf_token,
    ...(version === undefined ? {} : { "If-Match": `"${version}"` }) };
}

test("@teams administrative lifecycle persists, preserves history and uses real account selection", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Administrar equipes" }).click();
  await expect(page.getByRole("heading", { name: "Equipes", exact: true })).toBeVisible();
  const name = `Equipe Operacao ${crypto.randomUUID().slice(0, 8)}`;
  const id = await createTeam(page, name);
  await page.getByRole("button", { name: "Renomear equipe" }).click();
  await page.getByLabel("Nome da equipe", { exact: true }).fill(name + " revisada");
  await page.getByRole("button", { name: "Salvar nome" }).click();
  await expect(page.getByRole("heading", { name: name + " revisada", exact: true })).toBeVisible();
  const choice = page.getByRole("radio", { name: new RegExp(email.replaceAll(".", "\\.")) });
  for (let attempt = 0; attempt < 4; attempt++) {
    await expect(page.getByRole("group", { name: "Conta para adicionar" })).toBeVisible();
    if (await choice.count()) break;
    await page.getByRole("button", { name: "Próximas contas" }).click();
  }
  await choice.check();
  await page.getByRole("button", { name: "Adicionar participante", exact: true }).click();
  await expect(page.getByRole("list", { name: "Participantes da equipe" })
    .getByText("Operacao Altvia - Validacao", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Arquivar equipe", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar arquivamento" }).click();
  await expect(page.getByText("Equipe arquivada", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Adicionar participante", exact: true })).toBeDisabled();
  await page.reload();
  await expect(page.getByRole("list", { name: "Participantes da equipe" })
    .getByText("Operacao Altvia - Validacao", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Restaurar equipe", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar restauração" }).click();
  await expect(page.getByText("Equipe ativa", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Remover Operacao Altvia - Validacao da equipe" }).click();
  await page.getByRole("button", { name: "Confirmar remoção" }).click();
  await expect(page.getByText("Nenhum participante nesta equipe.", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: name + " revisada", exact: true })).toBeVisible();
  const stored = await page.request.get(`/api/v1/teams/${id}`);
  expect(stored.status()).toBe(200);
  expect((await stored.json()).active).toBe(true);
});

test("@teams lost POST acknowledgement reuses one intent and creates one persisted team", async ({ page }) => {
  await signIn(page);
  await page.goto("/admin/teams");
  const name = `Confirmacao ${crypto.randomUUID().slice(0, 8)}`;
  const keys: string[] = [];
  let created = "";
  let first = true;
  await page.route("**/api/v1/teams", async route => {
    if (route.request().method() !== "POST") return route.continue();
    keys.push(route.request().headers()["idempotency-key"]);
    const response = await route.fetch();
    if (first) {
      first = false;
      created = (await response.json()).id;
      return route.abort("failed");
    }
    expect(response.status()).toBe(200);
    await route.fulfill({ response });
  });
  await page.getByLabel("Nome da nova equipe").fill(name);
  await page.getByRole("button", { name: "Criar equipe", exact: true }).click();
  await expect(page.getByText("Não foi possível confirmar a gravação.", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Nome da nova equipe")).toBeDisabled();
  await mkdir(shots, { recursive: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${shots}/uncertain-create-mobile.png`, fullPage: true });
  await page.getByRole("button", { name: "Verificar resultado" }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  expect(page.url()).toContain(created);
  expect(keys.length).toBe(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[0] === keys[1]).toBe(true);
  const rows = await (await page.request.get("/api/v1/teams?limit=100")).json();
  expect(rows.items.filter((row: { name: string }) => row.name === name)).toHaveLength(1);
});

test("@teams changed versions preserve edits until explicit reload and HTML-like names stay text", async ({ page }) => {
  await signIn(page);
  const name = `Revisao ${crypto.randomUUID().slice(0, 8)}`;
  const id = await createTeam(page, name);
  await page.getByRole("button", { name: "Renomear equipe" }).click();
  await page.getByLabel("Nome da equipe", { exact: true }).fill("Minha edicao nao enviada");
  const current = await (await page.request.get(`/api/v1/teams/${id}`)).json();
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const newer = name + " alterada em outra sessao";
  expect((await page.request.patch(`/api/v1/teams/${id}`, { data: { name: newer },
    headers: { Origin: origin, "X-CSRF-Token": me.csrf_token, "If-Match": `"${current.version}"` },
  })).status()).toBe(200);
  await page.getByRole("button", { name: "Salvar nome" }).click();
  await expect(page.getByText("Os dados foram alterados em outra sessão.", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Nome da equipe", { exact: true })).toHaveValue("Minha edicao nao enviada");
  await expect(page.getByRole("button", { name: "Salvar nome" })).toBeDisabled();
  await mkdir(shots, { recursive: true });
  await page.screenshot({ path: `${shots}/version-conflict-desktop.png`, fullPage: true });
  await page.getByRole("button", { name: "Recarregar e descartar edição" }).click();
  await expect(page.getByLabel("Nome da equipe", { exact: true })).toHaveValue(newer);
  const literal = "Equipe <img src=x onerror=alert(1)> " + crypto.randomUUID().slice(0, 8);
  await page.getByLabel("Nome da equipe", { exact: true }).fill(literal);
  await page.getByRole("button", { name: "Salvar nome" }).click();
  await expect(page.getByRole("heading", { name: literal, exact: true })).toBeVisible();
  expect(await page.locator("img[src=x]").count()).toBe(0);
});

test("@teams ordinary accounts cannot administer or inherit private cached team data", async ({ page }) => {
  await signIn(page);
  const name = `Privada ${crypto.randomUUID().slice(0, 8)}`;
  await createTeam(page, name);
  await page.request.post("/api/v1/auth/sessions", { data: { email, password }, headers: { Origin: origin } });
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  // Concurrent private reads can challenge the old identity before /me settles.
  await expect(page.getByText(name, { exact: true })).toHaveCount(0);
  if (await page.getByRole("button", { name: "Verificar acesso", exact: true }).count()) {
    await page.getByRole("button", { name: "Verificar acesso", exact: true }).click();
  }
  await expect(page.getByRole("heading", { name: "Acesso restrito" })).toBeVisible();
  await expect(page.getByText(name, { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Renomear equipe" })).toHaveCount(0);
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Administrar equipes" })).toHaveCount(0);
  expect((await page.request.get("/api/v1/users")).status()).toBe(403);
});

test("@teams administrative pages render with real data on desktop/mobile in both themes", async ({ page }) => {
  await signIn(page);
  const name = "Equipe de validacao com nome longo " + "Operacao ".repeat(10);
  await createTeam(page, name.trim());
  await mkdir(shots, { recursive: true });
  for (const [size, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844]] as const) {
    await page.setViewportSize({ width, height });
    for (const theme of ["light", "dark"]) {
      await page.evaluate(theme => localStorage.setItem("theme", theme), theme);
      await page.reload();
      await expect(page.getByRole("heading", { name: name.trim(), exact: true })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Adicionar participante", exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: `${shots}/${size}-${theme}.png`, fullPage: true });
    }
  }
  await page.goto("/admin/teams");
  for (const [size, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844]] as const) {
    await page.setViewportSize({ width, height });
    for (const theme of ["light", "dark"]) {
      await page.evaluate(theme => localStorage.setItem("theme", theme), theme);
      await page.reload();
      await expect(page.getByRole("list", { name: "Equipes cadastradas" })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: `${shots}/directory-${size}-${theme}.png`, fullPage: true });
    }
  }
});

test("@teams uncertain membership replays its original version after a concurrent rename", async ({ page }) => {
  await signIn(page);
  const id = await createTeam(page, `Membros ${crypto.randomUUID().slice(0, 8)}`);
  await expect(page.getByRole("group", { name: "Conta para adicionar" })).toBeVisible();
  const available = page.locator('input[name="member-account"]:enabled').first();
  const userId = await available.inputValue();
  const requests: { key: string; version: string }[] = [];
  let first = true;
  await page.route(`**/api/v1/teams/${id}/members`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    const request = route.request();
    requests.push({ key: request.headers()["idempotency-key"], version: request.headers()["if-match"] });
    const response = await route.fetch();
    if (first) { first = false; expect(response.status()).toBe(201); return route.abort("failed"); }
    expect(response.status()).toBe(200);
    await route.fulfill({ response });
  });
  await available.check();
  await page.getByRole("button", { name: "Adicionar participante", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar resultado" })).toBeVisible();
  await page.route(`**/api/v1/teams/${id}/members?*`, route => route.abort());
  await page.route(`**/api/v1/teams/${id}`, route => route.abort());
  const failedDetail = page.waitForEvent("requestfailed", { predicate: request => request.url().endsWith(`/teams/${id}`) });
  const failedRoster = page.waitForEvent("requestfailed", { predicate: request => request.url().includes(`/teams/${id}/members?`) });
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await Promise.all([failedDetail, failedRoster]);
  const readRecovery = page.getByRole("button", { name: "Tentar carregar novamente" }).first();
  await expect(readRecovery).toBeVisible();
  await page.unroute(`**/api/v1/teams/${id}/members?*`);
  await page.unroute(`**/api/v1/teams/${id}`);
  await readRecovery.click();
  await expect(page.getByRole("button", { name: "Verificar resultado" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Adicionar participante", exact: true })).toBeDisabled();
  const current = await (await page.request.get(`/api/v1/teams/${id}`)).json();
  expect((await page.request.patch(`/api/v1/teams/${id}`, { data: { name: "Nome atual apos inclusao" },
    headers: await headers(page, current.version) })).status()).toBe(200);
  await page.getByRole("button", { name: "Verificar resultado" }).click();
  await expect(page.getByRole("heading", { name: "Nome atual apos inclusao", exact: true })).toBeVisible();
  expect(requests).toHaveLength(2);
  expect(requests[0]).toEqual(requests[1]);
  expect(requests[0].version).toBe('"1"');
  const stored = await (await page.request.get(`/api/v1/teams/${id}/members`)).json();
  expect(stored.items.map((row: { user_id: string }) => row.user_id)).toEqual([userId]);
});

test("@teams transient identity failure preserves an uncertain POST through explicit recovery", async ({ page }) => {
  await signIn(page);
  await page.goto("/admin/teams");
  const name = `Retida ${crypto.randomUUID().slice(0, 8)}`;
  const keys: string[] = [];
  await page.route("**/api/v1/teams", async route => {
    if (route.request().method() !== "POST") return route.continue();
    keys.push(route.request().headers()["idempotency-key"]);
    const response = await route.fetch();
    if (keys.length === 1) return route.abort("failed");
    await route.fulfill({ response });
  });
  await page.getByLabel("Nome da nova equipe").fill(name);
  await page.getByRole("button", { name: "Criar equipe", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar resultado" })).toBeVisible();
  await page.route("**/api/v1/auth/me", route => route.abort());
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await expect(page.getByRole("heading", { name: "Conexão indisponível" })).toBeVisible();
  await page.unroute("**/api/v1/auth/me");
  await page.getByRole("button", { name: "Tentar novamente", exact: true }).click();
  await expect(page.getByLabel("Nome da nova equipe")).toHaveValue(name);
  await expect(page.getByLabel("Nome da nova equipe")).toBeDisabled();
  await page.getByRole("button", { name: "Verificar resultado" }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});

test("@teams initial detail network error offers retry and confirmed writes await fresh snapshots", async ({ page }) => {
  await signIn(page);
  const name = `Leitura ${crypto.randomUUID().slice(0, 8)}`;
  const id = await createTeam(page, name);
  await page.route(`**/api/v1/teams/${id}`, route => route.abort());
  await page.reload();
  await expect(page.getByRole("button", { name: "Tentar carregar novamente" })).toBeVisible();
  await page.unroute(`**/api/v1/teams/${id}`);
  await page.getByRole("button", { name: "Tentar carregar novamente" }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let saved = false;
  await page.route(`**/api/v1/teams/${id}`, async route => {
    if (route.request().method() === "PATCH") {
      const response = await route.fetch(); saved = true;
      return route.fulfill({ response });
    }
    if (saved) await gate;
    await route.continue();
  });
  await page.getByRole("button", { name: "Arquivar equipe", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar arquivamento" }).click();
  await expect(page.getByRole("status")).toContainText("Solicitação confirmada");
  await expect(page.getByRole("button", { name: "Renomear equipe" })).toBeDisabled();
  release();
  await expect(page.getByText("Equipe arquivada", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Renomear equipe" })).toBeEnabled();
});

test("@teams uncertain PATCH requires review and focus refresh preserves the unsent edit", async ({ page }) => {
  await signIn(page);
  const id = await createTeam(page, `Transporte ${crypto.randomUUID().slice(0, 8)}`);
  await page.getByRole("button", { name: "Renomear equipe" }).click();
  const input = page.getByLabel("Nome da equipe", { exact: true });
  await expect(input).toBeFocused();
  await input.fill("Nome confirmado apos resposta perdida");
  const refreshed = page.waitForResponse("**/api/v1/auth/me");
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await refreshed;
  await expect(input).toHaveValue("Nome confirmado apos resposta perdida");
  await expect(input).toBeFocused();
  let patches = 0;
  await page.route(`**/api/v1/teams/${id}`, async route => {
    if (route.request().method() !== "PATCH") return route.continue();
    patches++;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    await route.abort("failed");
  });
  await page.getByRole("button", { name: "Salvar nome" }).click();
  await expect(page.getByRole("button", { name: "Recarregar e descartar edição" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Verificar resultado" })).toHaveCount(0);
  await expect(input).toBeDisabled();
  await page.getByRole("button", { name: "Recarregar e descartar edição" }).click();
  await expect(input).toBeEnabled();
  await expect(input).toHaveValue("Nome confirmado apos resposta perdida");
  expect(patches).toBe(1);
});

for (const replacement of ["subject", "same-subject-session"] as const) {
test(`@teams late creation response cannot navigate a replacement ${replacement}`, async ({ page }) => {
  await signIn(page);
  await page.goto("/admin/teams");
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let committed!: () => void;
  const saved = new Promise<void>(resolve => { committed = resolve; });
  await page.route("**/api/v1/teams", async route => {
    if (route.request().method() !== "POST") return route.continue();
    const response = await route.fetch();
    expect(response.status()).toBe(201); committed();
    await gate;
    await route.fulfill({ response });
  });
  await page.getByLabel("Nome da nova equipe").fill("Resposta da sessao anterior");
  await page.getByRole("button", { name: "Criar equipe", exact: true }).click();
  await saved;
  expect((await page.request.post("/api/v1/auth/sessions", { data: replacement === "subject" ? { email, password }
    : { email: adminEmail, password: adminPassword },
    headers: { Origin: origin } })).status()).toBe(201);
  const refreshed = page.waitForResponse("**/api/v1/auth/me");
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await refreshed;
  await expect.poll(() => page.locator("#new-team-name").evaluateAll(nodes => nodes.every(
    node => (node as HTMLInputElement).value !== "Resposta da sessao anterior"))).toBe(true);
  if (await page.getByRole("button", { name: "Verificar acesso", exact: true }).count()) {
    await page.getByRole("button", { name: "Verificar acesso", exact: true }).click();
  }
  const heading = replacement === "subject" ? "Acesso restrito" : "Equipes";
  await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
  release();
  await page.unrouteAll({ behavior: "wait" });
  await expect(page).toHaveURL(/\/admin\/teams$/);
  await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
  if (replacement === "subject") await expect(page.getByText("Resposta da sessao anterior", { exact: true })).toHaveCount(0);
});
}

test("@teams bounded team and roster pages expose inactive accounts without selecting them", async ({ page }) => {
  await signIn(page);
  const id = await createTeam(page, `Paginada ${crypto.randomUUID().slice(0, 8)}`);
  const users = (await (await page.request.get("/api/v1/users?limit=100")).json()).items;
  let version = 1;
  for (const user of users.filter((row: { active: boolean }) => row.active).slice(0, 12)) {
    const response = await page.request.post(`/api/v1/teams/${id}/members`, { data: { user_id: user.id },
      headers: { ...await headers(page, version), "Idempotency-Key": crypto.randomUUID() } });
    expect(response.status()).toBe(201); version++;
  }
  for (let index = 0; index < 11; index++) {
    expect((await page.request.post("/api/v1/teams", { data: { name: "Pagina " + index },
      headers: { ...await headers(page), "Idempotency-Key": crypto.randomUUID() } })).status()).toBe(201);
  }
  await page.reload();
  const roster = page.getByRole("list", { name: "Participantes da equipe" });
  await expect(roster.getByRole("listitem")).toHaveCount(10);
  await page.getByRole("button", { name: "Próximos participantes" }).click();
  await expect(roster.getByRole("listitem")).toHaveCount(2);
  await page.getByRole("button", { name: "Participantes anteriores" }).click();
  await expect(roster.getByRole("listitem")).toHaveCount(10);
  const inactive = page.getByRole("radio", { name: /browser-roster-13@example.invalid/ });
  await expect(page.getByRole("group", { name: "Conta para adicionar" })).toBeVisible();
  if (!(await inactive.count())) await page.getByRole("button", { name: "Próximas contas" }).click();
  await expect(inactive).toBeDisabled();
  await page.getByRole("link", { name: "Voltar às equipes" }).click();
  const teams = page.getByRole("list", { name: "Equipes cadastradas" });
  await expect(teams.getByRole("listitem")).toHaveCount(10);
  await page.getByRole("button", { name: "Próximas equipes" }).click();
  await expect(teams.getByRole("listitem").first()).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Páginas de equipes" })).toContainText("Página 2");
  await page.goto(`/admin/teams/${crypto.randomUUID()}`);
  await expect(page.getByText("Equipe não encontrada ou acesso indisponível.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Renomear equipe" })).toHaveCount(0);
});

test("@teams account-inactive conflict refreshes the existing-account selection", async ({ page }) => {
  await signIn(page);
  await createTeam(page, `Conta alterada ${crypto.randomUUID().slice(0, 8)}`);
  const choice = page.getByRole("radio", { name: /browser-roster-12@example.invalid/ });
  await expect(page.getByRole("group", { name: "Conta para adicionar" })).toBeVisible();
  if (!(await choice.count())) await page.getByRole("button", { name: "Próximas contas" }).click();
  await choice.check();
  execFileSync(process.platform === "win32" ? "uv.exe" : "uv", ["run", "python", "scripts/browser_fixture.py"], {
    cwd: root, env: { ...process.env, ALTVIA_E2E_DISABLE_ROSTER: "1" }, stdio: "pipe",
  });
  await page.getByRole("button", { name: "Adicionar participante", exact: true }).click();
  await expect(page.getByText("Esta conta foi desativada.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Recarregar dados", exact: true }).click();
  await expect(choice).toBeDisabled();
  await expect(choice).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Adicionar participante", exact: true })).toBeDisabled();
});

test("@teams Unicode names use the API code-point limit rather than UTF-16 length", async ({ page }) => {
  await signIn(page);
  await page.goto("/admin/teams");
  let creates = 0;
  page.on("request", request => { if (request.method() === "POST" && request.url().endsWith("/api/v1/teams")) creates++; });
  await page.getByLabel("Nome da nova equipe").fill("Equipe " + "𠮷".repeat(144));
  await page.getByRole("button", { name: "Criar equipe", exact: true }).click();
  await expect(page.getByText("Use um nome de 1 a 150 caracteres.")).toBeVisible();
  expect(creates).toBe(0);
  const name = "Equipe " + "𠮷".repeat(143);
  const id = await createTeam(page, name);
  expect(creates).toBe(1);
  expect((await (await page.request.get(`/api/v1/teams/${id}`)).json()).name).toBe(name);
});
