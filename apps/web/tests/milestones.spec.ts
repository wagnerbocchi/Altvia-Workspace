import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const origin = "https://127.0.0.1:3443";
const project = process.env.ALTVIA_E2E_MILESTONE_PROJECT_ID!;
const path = `/projects/${project}/milestones`;
const api = `/api/v1/projects/${project}/milestones`;
async function login(page: Page, kind = "MANAGER") {
  await page.context().addCookies([{ name: "__Host-altvia_session", value: process.env[`ALTVIA_E2E_MILESTONE_${kind}_SESSION`]!, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const response = await page.request.get("/api/v1/auth/me"); expect(response.status()).toBe(200);
  return (await response.json()).csrf_token as string;
}
const headers = (csrf: string, version?: number) => ({ Origin: origin, "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID(), ...(version ? { "If-Match": `"${version}"` } : {}) });
async function capture(page: Page, name: string) {
  const dir = fileURLToPath(new URL("../../../.impeccable/review/milestones/", import.meta.url)); await mkdir(dir, { recursive: true });
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    if (width === 1440) {
      expect((await page.locator(".admin-workspace").boundingBox())!.width).toBeGreaterThanOrEqual(800);
    }
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(element => element.classList.contains("dark")) !== (theme === "dark")) {
        await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      }
      await expect(page.locator("html")).toHaveCSS("color-scheme", theme);
      await page.evaluate(() => scrollTo(0, 0));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: `${dir}/${name}-${size}-${theme}.png`, fullPage: true });
    }
  }
}
test("@milestones real milestone deadline completion cancel reopen and persistence", async ({ page }) => {
  await login(page); await page.goto(`/projects/${project}`);
  await page.getByRole("link", { name: "Marcos do projeto", exact: true }).click();
  await expect(page.getByRole("button", { name: "Marcos anteriores", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Proximos marcos", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Novo marco", exact: true }).click();
  const title = `Entrega ${crypto.randomUUID().slice(0, 8)}`;
  await page.getByLabel("Titulo do marco", { exact: true }).fill(title);
  await page.getByLabel("Prazo do marco", { exact: true }).selectOption("date");
  await page.getByLabel("Data limite", { exact: true }).fill("2026-11-20");
  await page.getByLabel("Fuso do prazo", { exact: true }).fill("America/Sao_Paulo");
  await page.getByRole("button", { name: "Cadastrar marco", exact: true }).click();
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  await expect(page.getByText("20/11/2026 (America/Sao_Paulo)", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Concluir marco", exact: true }).click();
  await expect(page.getByText("Marco concluido", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Reabrir marco", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Reabrir este marco?", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Confirmar reabertura", exact: true }).click();
  await page.getByRole("button", { name: "Cancelar marco", exact: true }).click();
  await capture(page, "confirmation");
  await page.getByRole("button", { name: "Confirmar cancelamento", exact: true }).click();
  await page.reload(); await expect(page.getByText("Marco cancelado", { exact: true })).toBeVisible();
  await capture(page, "detail");
  await page.getByRole("link", { name: "Voltar aos marcos", exact: true }).click();
  await expect(page.getByRole("link", { name: title, exact: true })).toBeVisible(); await capture(page, "directory");
});
for (const committed of [false, true]) test(`@milestones uncertain create ${committed} preserves original intent after parent failure`, async ({ page }) => {
  await login(page); await page.goto(path); await page.getByRole("button", { name: "Novo marco", exact: true }).click();
  const title = `Incerto ${crypto.randomUUID().slice(0, 8)}`; await page.getByLabel("Titulo do marco", { exact: true }).fill(title);
  let first = true; let original: object | undefined;
  await page.route(`**${api}`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    const value = { body: route.request().postData(), key: route.request().headers()["idempotency-key"] };
    if (first) { first = false; original = value; if (committed) await route.fetch(); await route.abort("failed"); }
    else { expect(value).toEqual(original); await route.continue(); }
  });
  await page.getByRole("button", { name: "Cadastrar marco", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar cadastro do marco", exact: true })).toBeVisible();
  await page.route(`**/api/v1/projects/${project}`, route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Atualizar marcos", exact: true }).click();
  await expect(page.getByLabel("Titulo do marco", { exact: true })).toHaveValue(title);
  await expect(page.getByRole("button", { name: "Cadastrar marco", exact: true })).toBeDisabled();
  await page.unroute(`**/api/v1/projects/${project}`);
  await page.getByRole("button", { name: "Verificar cadastro do marco", exact: true }).click();
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
});
test("@milestones stale editing keeps reviewed version and exact instant until explicit reload", async ({ page }) => {
  const csrf = await login(page);
  const response = await page.request.post(api, { data: { title: "Marco exato", due: { precision: "instant", instant: "2026-11-10T12:34:56.123456Z" } }, headers: headers(csrf) }); expect(response.status()).toBe(201);
  const identifier = (await response.json()).milestone_id;
  await page.goto(`${path}/${identifier}`); await page.getByRole("button", { name: "Editar marco", exact: true }).click();
  await page.getByLabel("Titulo do marco", { exact: true }).fill("Titulo alterado"); await capture(page, "edit");
  await page.getByRole("button", { name: "Salvar marco", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Titulo alterado", exact: true })).toBeVisible();
  const current = await (await page.request.get(`${api}/${identifier}`)).json(); expect(current.due.instant).toBe("2026-11-10T12:34:56.123456Z");
  await page.getByRole("button", { name: "Editar marco", exact: true }).click(); await page.getByLabel("Titulo do marco", { exact: true }).fill("Edicao antiga");
  expect((await page.request.patch(`${api}/${identifier}`, { data: { title: "Alterado em outra sessao" }, headers: headers(csrf, current.version) })).status()).toBe(200);
  await page.getByRole("button", { name: "Salvar marco", exact: true }).click(); await expect(page.getByRole("button", { name: "Salvar marco", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Alterado em outra sessao", exact: true })).toBeVisible();
});
test("@milestones viewer only reads and hidden account sees no milestone", async ({ page }) => {
  const csrf = await login(page); const response = await page.request.post(api, { data: { title: "Marco visivel" }, headers: headers(csrf) }); expect(response.status()).toBe(201);
  const id = (await response.json()).milestone_id;
  await login(page, "READER"); await page.goto(`${path}/${id}`);
  await expect(page.getByText("Acesso somente para consulta.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Editar marco", exact: true })).toHaveCount(0);
  await login(page, "HIDDEN"); await page.reload();
  await expect(page.getByText("Este marco nao esta disponivel para sua conta.", { exact: true })).toBeVisible();
  await expect(page.getByText("Marco visivel", { exact: true })).toHaveCount(0);
});
