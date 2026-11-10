import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const project = process.env.ALTVIA_E2E_EXTERNAL_WORK_PROJECT_ID!;
const directory = `/projects/${project}/work`;
const origin = "https://127.0.0.1:3443";
async function login(page: Page, kind = "MANAGER") {
  await page.context().addCookies([{ name: "__Host-altvia_session", value: process.env[`ALTVIA_E2E_WORK_${kind}_SESSION`]!, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const me = await page.request.get("/api/v1/auth/me"); expect(me.status()).toBe(200);
  return await me.json() as { id: string; csrf_token: string };
}
const headers = (csrf: string, version = 1) => ({ Origin: origin, "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID(), "If-Match": `"${version}"` });
async function capture(page: Page, name: string) {
  const root = fileURLToPath(new URL("../../../.impeccable/review/work-external/", import.meta.url)); await mkdir(root, { recursive: true });
  await expect(page.getByRole("heading", { name: name === "create" ? "Nova tarefa" : "Dados da tarefa", exact: true })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: /^Carregando/ })).toHaveCount(0);
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(element => element.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      await expect(page.locator("html")).toHaveCSS("color-scheme", theme);
      await page.evaluate(() => scrollTo(0, 0));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: `${root}/${name}-${size}-${theme}.png`, fullPage: true });
    }
  }
}
async function create(page: Page, csrf: string, labels: string[], owner?: string) {
  const response = await page.request.post("/api/v1/work-items", { headers: headers(csrf), data: { project_id: project, title: "Tarefa com apoio externo", priority: "medium", work_type: "one_off", external_participants: labels, owner_id: owner ?? null } });
  expect(response.status()).toBe(201); return `/work-items/${(await response.json()).work_item_id}`;
}

test("@external manager creates edits and clears real external involvement as literal text", async ({ page }) => {
  await login(page); await page.goto(directory);
  await page.getByLabel("Título da nova tarefa", { exact: true }).fill("Entrega com apoio externo");
  const field = page.getByLabel("Envolvidos externos, um por linha", { exact: true });
  await field.fill("Terceiro\nFornecedor <script>texto</script>");
  await capture(page, "create");
  await field.focus(); await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Criar tarefa", exact: true })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Entrega com apoio externo", exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Envolvidos externos", exact: true })).toContainText("Fornecedor <script>texto</script>");
  await expect(page.locator("script").filter({ hasText: /^texto$/ })).toHaveCount(0);
  await page.reload(); await capture(page, "detail");
  await page.getByRole("button", { name: "Editar tarefa", exact: true }).click();
  await field.fill("Fornecedor revisado\nTerceiro"); await capture(page, "edit");
  await page.getByRole("button", { name: "Salvar tarefa", exact: true }).click();
  await expect(page.getByRole("list", { name: "Envolvidos externos", exact: true })).toContainText("Fornecedor revisado");
  await page.getByRole("button", { name: "Editar tarefa", exact: true }).click(); await field.fill("");
  await page.getByRole("button", { name: "Salvar tarefa", exact: true }).click(); await page.reload();
  await expect(page.getByText("Nenhum envolvido externo.", { exact: true })).toBeVisible();
});

for (const committed of [false, true]) test(`@external uncertain create ${committed} retains original external labels through list failure`, async ({ page }) => {
  await login(page); await page.goto(directory);
  await page.getByLabel("Título da nova tarefa", { exact: true }).fill(`Entrega incerta ${committed}`);
  const field = page.getByLabel("Envolvidos externos, um por linha", { exact: true }); await field.fill("Terceiro original");
  let original: object | undefined; let first = true;
  await page.route("**/api/v1/work-items", async route => {
    if (route.request().method() !== "POST") return route.continue();
    const intent = { body: route.request().postData(), key: route.request().headers()["idempotency-key"] };
    if (first) { original = intent; first = false; if (committed) await route.fetch(); await route.abort("failed"); }
    else { expect(intent).toEqual(original); await route.continue(); }
  });
  await page.getByRole("button", { name: "Criar tarefa", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar criação", exact: true })).toBeVisible();
  await page.route("**/api/v1/work-items?*", route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Atualizar tarefas", exact: true }).click();
  await expect(field).toHaveValue("Terceiro original"); await expect(field).toBeDisabled();
  await page.unroute("**/api/v1/work-items?*");
  await page.getByRole("button", { name: "Verificar criação", exact: true }).click();
  await expect(page.getByRole("list", { name: "Envolvidos externos", exact: true })).toContainText("Terceiro original");
});

test("@external stale reviewed editing never overwrites a newer external list", async ({ page }) => {
  const user = await login(page); const path = await create(page, user.csrf_token, ["Terceiro anterior"]);
  await page.goto(path); await page.getByRole("button", { name: "Editar tarefa", exact: true }).click();
  const field = page.getByLabel("Envolvidos externos, um por linha", { exact: true }); await field.fill("Edicao antiga");
  const response = await page.request.patch(`/api/v1${path}`, { headers: headers(user.csrf_token), data: { external_participants: ["Revisado em outra sessao"] } }); expect(response.status()).toBe(200);
  await page.getByRole("button", { name: "Salvar tarefa", exact: true }).click();
  await expect(field).toBeDisabled(); await expect(field).toHaveValue("Edicao antiga"); await capture(page, "recovery");
  await page.getByRole("button", { name: "Recarregar e descartar edição", exact: true }).click();
  await expect(page.getByRole("list", { name: "Envolvidos externos", exact: true })).toContainText("Revisado em outra sessao");
});

test("@external assigned agent and reader see labels without manager controls", async ({ page }) => {
  const agent = await login(page, "AGENT"); const manager = await login(page);
  const path = await create(page, manager.csrf_token, ["Terceiro informado"], agent.id);
  await login(page, "AGENT"); await page.goto(path);
  await expect(page.getByRole("list", { name: "Envolvidos externos", exact: true })).toContainText("Terceiro informado");
  await page.getByRole("button", { name: "Editar tarefa", exact: true }).click();
  await expect(page.getByLabel("Envolvidos externos, um por linha", { exact: true })).toHaveCount(0);
  await page.getByLabel("Título", { exact: true }).fill("Conteudo pelo agente");
  await page.getByRole("button", { name: "Salvar tarefa", exact: true }).click();
  await expect(page.getByRole("list", { name: "Envolvidos externos", exact: true })).toContainText("Terceiro informado");
  await login(page, "READER"); await page.goto(path);
  await expect(page.getByRole("button", { name: "Editar tarefa", exact: true })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Envolvidos externos", exact: true })).toContainText("Terceiro informado");
});

test("@external unrelated title edit preserves exact external Unicode labels", async ({ page }) => {
  const user = await login(page); const labels = ["\uFEFFFornecedor", "Fornecedor"];
  const path = await create(page, user.csrf_token, labels);
  await page.goto(path); await page.getByRole("button", { name: "Editar tarefa", exact: true }).click();
  await page.getByLabel("Título", { exact: true }).fill("Titulo sem alterar envolvidos");
  await page.getByRole("button", { name: "Salvar tarefa", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Titulo sem alterar envolvidos", exact: true })).toBeVisible();
  expect((await (await page.request.get(`/api/v1${path}`)).json()).external_participants).toEqual([...labels].sort((a, b) => a < b ? -1 : a > b ? 1 : 0));
});
