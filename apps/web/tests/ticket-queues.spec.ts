import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const origin = "https://127.0.0.1:3443";
const directory = "/service-desk/queues";
const team = process.env.ALTVIA_E2E_QUEUE_TEAM_ID!;
const fixture = process.env.ALTVIA_E2E_QUEUE_ID!;

async function login(page: Page, kind = "MANAGER") {
  await page.context().addCookies([{ name: "__Host-altvia_session", value: process.env[`ALTVIA_E2E_WORK_${kind}_SESSION`]!, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const response = await page.request.get("/api/v1/auth/me");
  expect(response.status()).toBe(200);
  return (await response.json()).csrf_token as string;
}
function headers(csrf: string, version = 1) {
  return { Origin: origin, "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID(), "If-Match": `"${version}"` };
}
async function create(page: Page, csrf: string, name: string) {
  const response = await page.request.post("/api/v1/ticket-queues", { headers: headers(csrf), data: { team_id: team, name } });
  expect(response.status()).toBe(201);
  return (await response.json()).queue_id as string;
}
async function capture(page: Page, state: string) {
  const root = fileURLToPath(new URL("../../../.impeccable/review/ticket-queues/", import.meta.url));
  await mkdir(root, { recursive: true });
  await expect(page.getByRole("heading", { name: state === "directory" ? "Filas de atendimento" : "Dados da fila", exact: true })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: /^Carregando/ })).toHaveCount(0);
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(element => element.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      await expect(page.locator("html")).toHaveCSS("color-scheme", theme);
      await page.evaluate(() => scrollTo(0, 0));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: `${root}/${state}-${size}-${theme}.png`, fullPage: true });
    }
  }
}

test("@queues manager operates real queue and category lifecycle with literal text", async ({ page }) => {
  await login(page); await page.goto(directory);
  await page.getByLabel("Equipe da fila", { exact: true }).selectOption(team);
  await page.getByLabel("Nome da nova fila", { exact: true }).fill("Atendimento <script>texto</script>");
  await capture(page, "directory");
  await page.getByLabel("Nome da nova fila", { exact: true }).focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Equipe da fila", { exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Cadastrar fila", exact: true })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Atendimento <script>texto</script>", exact: true })).toBeVisible();
  await page.getByLabel("Nome da nova categoria", { exact: true }).fill("Apoio externo");
  await page.getByRole("button", { name: "Cadastrar categoria", exact: true }).click();
  const categories = page.getByRole("list", { name: "Categorias da fila", exact: true });
  await expect(categories).toContainText("Apoio externo");
  await page.reload(); await capture(page, "detail");
  await categories.getByRole("button", { name: "Renomear categoria", exact: true }).click();
  await categories.getByLabel("Nome da categoria", { exact: true }).fill("Apoio revisado");
  await capture(page, "category-edit");
  await categories.getByRole("button", { name: "Salvar nome", exact: true }).click();
  await expect(categories).toContainText("Apoio revisado");
  await categories.getByRole("button", { name: "Arquivar categoria", exact: true }).click();
  await categories.getByRole("button", { name: "Confirmar arquivamento", exact: true }).click();
  const queueReload = page.waitForResponse(response => response.request().method() === "GET" && /\/api\/v1\/ticket-queues\/[^/]+$/.test(new URL(response.url()).pathname));
  await categories.getByRole("button", { name: "Restaurar categoria", exact: true }).click();
  await (await queueReload).finished();
  await expect(categories.getByRole("button", { name: "Arquivar categoria", exact: true })).toBeVisible();
  const details = page.getByRole("region", { name: "Dados da fila", exact: true });
  await details.getByRole("button", { name: "Arquivar fila", exact: true }).click();
  await details.getByRole("button", { name: "Confirmar arquivamento", exact: true }).click();
  await expect(page.getByText("Fila arquivada", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Nome da nova categoria", { exact: true })).toHaveCount(0);
  await details.getByRole("button", { name: "Restaurar fila", exact: true }).click();
  await page.reload(); await expect(categories).toContainText("Apoio revisado");
  await expect(page.locator("script").filter({ hasText: /^texto$/ })).toHaveCount(0);
});

for (const committed of [false, true]) test(`@queues uncertain create ${committed} retains team name and key through paging failure`, async ({ page }) => {
  await login(page); await page.goto(directory);
  const field = page.getByLabel("Nome da nova fila", { exact: true });
  await page.getByLabel("Equipe da fila", { exact: true }).selectOption(team);
  const name = `Fila incerta ${committed}`; await field.fill(name);
  let original: object | undefined;
  await page.route("**/api/v1/ticket-queues", async route => {
    if (route.request().method() !== "POST") return route.continue();
    const intent = { body: route.request().postData(), key: route.request().headers()["idempotency-key"] };
    if (!original) { original = intent; if (committed) await route.fetch(); await route.abort("failed"); }
    else { expect(intent).toEqual(original); await route.continue(); }
  });
  await page.getByRole("button", { name: "Cadastrar fila", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar cadastro", exact: true })).toBeVisible();
  await page.route("**/api/v1/ticket-queues?*", route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Proximas filas", exact: true }).click();
  await expect(field).toBeDisabled(); await expect(field).toHaveValue(name);
  await expect(page.getByLabel("Equipe da fila", { exact: true })).toHaveValue(team);
  await page.unroute("**/api/v1/ticket-queues?*");
  await page.getByRole("button", { name: "Verificar cadastro", exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
});

test("@queues stale queue draft survives failed read recovery", async ({ page }) => {
  const csrf = await login(page);
  const id = await create(page, csrf, "Fila em revisao");
  await page.goto(`${directory}/${id}`);
  await page.getByRole("button", { name: "Renomear fila", exact: true }).click();
  const field = page.getByLabel("Nome da fila", { exact: true }); await field.fill("Rascunho local");
  expect((await page.request.patch(`/api/v1/ticket-queues/${id}`, { headers: headers(csrf), data: { name: "Nome remoto" } })).status()).toBe(200);
  await page.getByRole("button", { name: "Salvar nome", exact: true }).click();
  await expect(page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true })).toBeVisible();
  await page.route(`**/api/v1/ticket-queues/${id}`, route => route.request().method() === "GET" ? route.fulfill({ status: 503, body: "{}" }) : route.continue());
  await page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true }).click();
  await expect(page.getByText("Nao foi possivel atualizar. A edicao continua bloqueada.", { exact: true })).toBeVisible();
  await expect(field).toHaveValue("Rascunho local"); await expect(field).toBeDisabled();
  await capture(page, "recovery");
  await page.unroute(`**/api/v1/ticket-queues/${id}`);
  await page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true }).click();
  await expect(field).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Nome remoto", exact: true })).toBeVisible();
});

test("@queues reader consults scoped configuration and unrelated agent is denied", async ({ page }) => {
  await login(page, "READER"); await page.goto(`${directory}/${fixture}`);
  await expect(page.getByRole("heading", { name: "Dados da fila", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Renomear fila", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Cadastrar categoria", exact: true })).toHaveCount(0);
  await login(page, "AGENT"); await page.goto(`${directory}/${fixture}`);
  await expect(page.getByRole("heading", { name: "Fila indisponivel", exact: true })).toBeVisible();
  expect((await page.request.get(`/api/v1/ticket-queues/${fixture}`)).status()).toBe(404);
});

test("@queues category retry uses one immutable creation intent", async ({ page }) => {
  const csrf = await login(page); const id = await create(page, csrf, "Fila de categorias");
  await page.goto(`${directory}/${id}`);
  const field = page.getByLabel("Nome da nova categoria", { exact: true }); await field.fill("Categoria incerta");
  let original: object | undefined;
  await page.route(`**/api/v1/ticket-queues/${id}/categories`, async route => {
    const intent = { body: route.request().postData(), key: route.request().headers()["idempotency-key"] };
    if (!original) { original = intent; await route.fetch(); await route.abort("failed"); }
    else { expect(intent).toEqual(original); await route.continue(); }
  });
  await page.getByRole("button", { name: "Cadastrar categoria", exact: true }).click();
  await expect(field).toBeDisabled();
  await page.getByRole("button", { name: "Verificar cadastro", exact: true }).click();
  await expect(page.getByRole("list", { name: "Categorias da fila", exact: true }).getByRole("heading", { name: "Categoria incerta", exact: true })).toHaveCount(1);
});

for (const failRefresh of [false, true]) test(`@queues parent actions wait for refreshed version after child success ${failRefresh}`, async ({ page }) => {
  const csrf = await login(page);
  const id = await create(page, csrf, `Fila com atualizacao pendente ${failRefresh}`);
  const added = await page.request.post(`/api/v1/ticket-queues/${id}/categories`, { headers: headers(csrf), data: { name: "Categoria inicial" } });
  expect(added.status()).toBe(201);
  await page.goto(`${directory}/${id}`);
  const categories = page.getByRole("list", { name: "Categorias da fila", exact: true });
  await categories.getByRole("button", { name: "Renomear categoria", exact: true }).click();
  await categories.getByLabel("Nome da categoria", { exact: true }).fill("Categoria alterada");
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/api/v1/ticket-queues/${id}`, async route => {
    if (route.request().method() === "GET") {
      await pending;
      if (failRefresh) return route.fulfill({ status: 503, body: "{}" });
    }
    await route.continue();
  });
  const refreshed = page.waitForResponse(response => response.request().method() === "GET" && new URL(response.url()).pathname === `/api/v1/ticket-queues/${id}`);
  try {
    await categories.getByRole("button", { name: "Salvar nome", exact: true }).click();
    await expect(categories.getByRole("heading", { name: "Categoria alterada", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Arquivar fila", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Renomear fila", exact: true })).toBeDisabled();
  } finally { release(); }
  await (await refreshed).finished();
  if (failRefresh) {
    await expect(page.getByRole("button", { name: "Tentar carregar novamente", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Arquivar fila", exact: true })).toBeDisabled();
  }
  await page.unroute(`**/api/v1/ticket-queues/${id}`);
  if (failRefresh) await page.getByRole("button", { name: "Tentar carregar novamente", exact: true }).click();
  await page.getByRole("button", { name: "Arquivar fila", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar arquivamento", exact: true }).click();
  await expect(page.getByText("Fila arquivada", { exact: true })).toBeVisible();
});

test("@queues Unicode name survives reviewed no-op browser editing", async ({ page }) => {
  const csrf = await login(page);
  const name = "\ufeffFornecedor";
  const id = await create(page, csrf, name);
  await page.goto(`${directory}/${id}`);
  await page.getByRole("button", { name: "Renomear fila", exact: true }).click();
  await expect(page.getByLabel("Nome da fila", { exact: true })).toHaveValue(name);
  await page.getByRole("button", { name: "Salvar nome", exact: true }).click();
  await expect(page.getByLabel("Nome da fila", { exact: true })).toHaveCount(0);
  const result = await page.request.get(`/api/v1/ticket-queues/${id}`);
  expect((await result.json()).name).toBe(name);
  await expect((await page.request.get(`/api/v1/ticket-queues/${id}`)).json()).resolves.toMatchObject({ version: 1 });
});
