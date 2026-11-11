import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const origin = "https://127.0.0.1:3443";
const queue = process.env.ALTVIA_E2E_QUEUE_ACCESS_ID!;
const email = process.env.ALTVIA_E2E_QUEUE_ACCESS_TARGET_EMAIL!;
const path = `/service-desk/queues/${queue}/members`;
const api = `/api/v1/ticket-queues/${queue}`;
async function login(page: Page, kind = "MANAGER") {
  const token = process.env[`ALTVIA_E2E_QUEUE_ACCESS_${kind}_SESSION`];
  if (!token) throw Error("Guarded member session required");
  await page.context().addCookies([{ name: "__Host-altvia_session", value: token, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const response = await page.request.get("/api/v1/auth/me");
  expect(response.status()).toBe(200);
  return (await response.json()).csrf_token as string;
}
const headers = (csrf: string, version: number) => ({ Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${version}"`, "Idempotency-Key": crypto.randomUUID() });
const member = (page: Page) => page.getByRole("list", { name: "Membros da fila", exact: true }).getByRole("listitem").filter({ hasText: "Fila TARGET" });
async function openAdd(page: Page) {
  await page.getByRole("button", { name: "Adicionar membro", exact: true }).click();
  await page.getByLabel("E-mail da conta", { exact: true }).fill(email);
  await page.getByLabel("Papel na fila", { exact: true }).selectOption("agent");
  await page.getByRole("button", { name: "Revisar acesso", exact: true }).click();
}
async function remove(page: Page) {
  await member(page).getByRole("button", { name: "Remover acesso", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Remover acesso direto?", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Confirmar remocao", exact: true }).click();
  await expect(member(page)).toHaveCount(0);
}
async function capture(page: Page, name: string) {
  const shots = fileURLToPath(new URL("../../../.impeccable/review/queue-access/", import.meta.url));
  await mkdir(shots, { recursive: true });
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    if (name === "refresh-error") await expect(page.getByRole("list", { name: "Membros da fila", exact: true })).toHaveCount(0);
    if (width === 390 && name !== "refresh-error") {
      const text = await page.getByRole("list", { name: "Membros da fila", exact: true }).locator(".record-text").first().boundingBox();
      expect(text!.width).toBeGreaterThanOrEqual(200);
    }
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(element => element.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      await expect(page.locator("html")).toHaveCSS("color-scheme", theme);
      await page.evaluate(() => scrollTo(0, 0));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: `${shots}/${name}-${size}-${theme}.png`, fullPage: true });
    }
  }
}

test("@queue-access persisted add role change removal and accessible views", async ({ page }) => {
  await login(page);
  await page.goto(`/service-desk/queues/${queue}`);
  await page.getByRole("link", { name: "Administrar membros", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Membros da fila", exact: true })).toBeVisible();
  await openAdd(page);
  await capture(page, "add");
  await page.getByRole("button", { name: "Conceder acesso", exact: true }).click();
  await expect(member(page)).toContainText("Agente");
  await member(page).getByRole("button", { name: "Alterar papel", exact: true }).click();
  await page.getByLabel("Novo papel", { exact: true }).selectOption("viewer");
  await capture(page, "role");
  await page.getByRole("button", { name: "Salvar papel", exact: true }).click();
  await expect(member(page)).toContainText("Consulta");
  await page.reload();
  await expect(member(page)).toContainText("Consulta");
  await capture(page, "directory");
  await member(page).getByRole("button", { name: "Remover acesso", exact: true }).click();
  await capture(page, "confirmation");
  await page.getByRole("button", { name: "Cancelar alteracao", exact: true }).click();
  await remove(page);
  await page.reload();
  await expect(member(page)).toHaveCount(0);
});

for (const committed of [false, true]) test(`@queue-access uncertain add ${committed ? "committed" : "uncommitted"} survives failed parent read`, async ({ page }) => {
  await login(page); await page.goto(path); await openAdd(page);
  let first = true;
  let original: { body: string | null; key: string | undefined; version: string | undefined } | undefined;
  await page.route(`**${api}/members`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    const request = route.request();
    const intent = { body: request.postData(), key: request.headers()["idempotency-key"], version: request.headers()["if-match"] };
    if (first) {
      first = false; original = intent;
      if (committed) await route.fetch();
      await route.abort("failed");
    } else { expect(intent).toEqual(original); await route.continue(); }
  });
  await page.getByRole("button", { name: "Conceder acesso", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar concessao", exact: true })).toBeVisible();
  await page.route(`**${api}`, route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Atualizar membros", exact: true }).click();
  await expect(page.getByRole("button", { name: "Conceder acesso", exact: true })).toBeDisabled();
  await expect(page.getByLabel("E-mail da conta", { exact: true })).toHaveValue(email);
  await page.unroute(`**${api}`);
  await page.getByRole("button", { name: "Verificar concessao", exact: true }).click();
  await expect(member(page)).toContainText("Agente");
  await expect(page.getByRole("button", { name: "Adicionar membro", exact: true })).toBeEnabled();
  await remove(page);
});

test("@queue-access stale reviewed version requires explicit reload", async ({ page }) => {
  const csrf = await login(page); await page.goto(path); await openAdd(page);
  const row = await (await page.request.get(api)).json();
  expect((await page.request.patch(api, { data: { name: row.name + " revisado" }, headers: headers(csrf, row.version) })).status()).toBe(200);
  await page.getByRole("button", { name: "Conceder acesso", exact: true }).click();
  await expect(page.getByText("Os dados foram alterados em outra sessao. Recarregue para revisar.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Conceder acesso", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Recarregar para revisar", exact: true }).click();
  await expect(page.getByRole("button", { name: "Adicionar membro", exact: true })).toBeEnabled();
  await expect(member(page)).toHaveCount(0);
});

for (const role of ["VIEWER", "AGENT"]) test(`@queue-access ${role} cannot write and hidden scope exposes no roster`, async ({ page }) => {
  await login(page, role); await page.goto(path);
  await expect(page.getByText("Acesso somente para consulta.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Adicionar membro", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Remover acesso", exact: true })).toHaveCount(0);
  await login(page, "HIDDEN"); await page.reload();
  await expect(page.getByText("Esta fila nao esta disponivel para sua conta.", { exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Membros da fila", exact: true })).toHaveCount(0);
});

test("@queue-access confirmed grant stays blocked after failed authoritative refresh", async ({ page }) => {
  await login(page); await page.goto(path); await openAdd(page);
  await page.route(`**${api}`, route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Conceder acesso", exact: true }).click();
  await expect(page.getByText("Solicitacao confirmada. Confira o acesso atual na lista.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Conceder acesso", exact: true })).toBeDisabled();
  await expect(page.getByText("N\u00e3o foi poss\u00edvel carregar os dados. Confira a conex\u00e3o e tente novamente.", { exact: true })).toBeVisible();
  await capture(page, "refresh-error");
  await page.unroute(`**${api}`);
  await page.getByRole("button", { name: "Conferir acesso atual", exact: true }).click();
  await expect(page.getByRole("button", { name: "Adicionar membro", exact: true })).toBeEnabled();
  await expect(member(page)).toContainText("Agente");
  await remove(page);
});

test("@queue-access self removal requires confirmation and a fresh login", async ({ page }) => {
  await login(page, "SELF"); await page.goto(path);
  const row = page.getByRole("listitem").filter({ hasText: "Fila SELF" });
  await row.getByRole("button", { name: "Remover acesso", exact: true }).click();
  await expect(page.getByText("Sua sessao sera encerrada. Sera necessario entrar novamente.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Confirmar remocao", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Acesse seu workspace", exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Membros da fila", exact: true })).toHaveCount(0);
  const denied = await page.request.get(`${api}/members`); expect(denied.status()).toBe(401);
});

test("@queue-access known-email self demotion sends nothing before explicit reviewed confirmation", async ({ page }) => {
  await login(page); await page.goto(path);
  let posts = 0;
  page.on("request", request => { if (request.url().endsWith(`${api}/members`) && request.method() === "POST") posts++; });
  await page.getByRole("button", { name: "Adicionar membro", exact: true }).click();
  await page.getByLabel("E-mail da conta", { exact: true }).fill(process.env.ALTVIA_E2E_QUEUE_ACCESS_MANAGER_EMAIL!);
  await page.getByLabel("Papel na fila", { exact: true }).selectOption("viewer");
  await page.getByRole("button", { name: "Revisar acesso", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Confirmar papel na fila?", exact: true })).toBeFocused();
  expect(posts).toBe(0);
  await expect(page.getByText("Se esta for sua conta, sera necessario entrar novamente. A configuracao da fila tem permissao independente.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Conceder acesso", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Acesse seu workspace", exact: true })).toBeVisible();
  expect(posts).toBe(1);
});
