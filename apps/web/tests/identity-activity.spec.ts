import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const origin = "https://127.0.0.1:3443";
const shots = fileURLToPath(new URL("../../../.impeccable/review/activity/", import.meta.url));

test("@activity real persisted administrative history has bounded pages and safe read recovery", async ({ page }) => {
  const login = await page.request.post("/api/v1/auth/sessions", { data: {
    email: process.env.ALTVIA_E2E_ADMIN_EMAIL!, password: process.env.ALTVIA_E2E_ADMIN_PASSWORD!,
  }, headers: { Origin: origin } });
  expect(login.status()).toBe(201);
  await page.goto("/admin/users");
  await expect(page.getByRole("heading", { name: "Histórico administrativo", exact: true })).toBeVisible();
  const csrf = (await login.json()).csrf_token;
  for (let i = 0; i < 12; i++) {
    expect((await page.request.post("/api/v1/teams", { data: { name: `Historico ${i}` }, headers: {
      Origin: origin, "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID(),
    } })).status()).toBe(201);
  }
  await expect.poll(async () => (await (await page.request.get("/api/v1/identity-activity?limit=100")).json()).items.length).toBeGreaterThanOrEqual(12);
  await page.getByRole("button", { name: "Atualizar histórico", exact: true }).click();
  const history = page.getByRole("list", { name: "Histórico administrativo" });
  await expect(history.getByRole("listitem")).toHaveCount(10);
  await page.getByRole("button", { name: "Próximas atividades", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Páginas de atividades" })).toContainText("Página 2");
  await expect(history.getByRole("listitem").first()).toBeVisible();
  await page.getByRole("button", { name: "Atividades anteriores", exact: true }).click();
  await page.route("**/api/v1/identity-activity?*", route => route.abort());
  await page.getByRole("button", { name: "Atualizar histórico", exact: true }).click();
  await expect(page.getByRole("button", { name: "Tentar carregar novamente", exact: true })).toBeVisible();
  await page.unroute("**/api/v1/identity-activity?*");
  await page.getByRole("button", { name: "Tentar carregar novamente", exact: true }).click();
  await expect(history.getByRole("listitem")).toHaveCount(10);
  await mkdir(shots, { recursive: true });
  for (const theme of ["light", "dark"]) {
    await page.evaluate(value => localStorage.setItem("theme", value), theme); await page.reload();
    await expect(history.getByRole("listitem")).toHaveCount(10);
    await expect(page.getByText("Carregando contas...", { exact: true })).toBeHidden();
    for (const [name, width] of [["desktop", 1440], ["mobile", 390]] as const) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: `${shots}/${name}-${theme}.png`, fullPage: true });
      const region = await page.getByRole("region", { name: "Histórico administrativo" }).boundingBox();
      expect(region).not.toBeNull();
      await page.screenshot({ path: `${shots}/${name}-${theme}-history.png`, fullPage: true, clip: region! });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    }
  }
});
