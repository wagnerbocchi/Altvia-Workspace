import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

// Separate capture run: synthetic identities only, no browser traces or filled credentials.
test("@account-captures directory confirmation and uncertain-result states", async ({ page, context }) => {
  const shots = fileURLToPath(new URL("../../../.impeccable/review/accounts/", import.meta.url));
  await mkdir(shots, { recursive: true });
  await context.addCookies([{ name: "__Host-altvia_session", value: process.env.ALTVIA_E2E_ADMIN_SESSION!,
    domain: "127.0.0.1", path: "/", secure: true, httpOnly: true, sameSite: "Lax" }]);
  const identity = await page.request.get("/api/v1/auth/me");
  expect(identity.status()).toBe(200);
  const me = await identity.json();
  await page.goto("/admin/users");
  await expect(page.getByLabel("Nome da nova conta")).toBeVisible();
  await expect(page.locator(".account-form-grid .field").first()).toHaveCSS("margin-bottom", "0px");
  for (const theme of ["light", "dark"]) {
    await page.evaluate(value => localStorage.setItem("theme", value), theme); await page.reload();
    await expect(page.getByRole("list", { name: "Contas cadastradas" })).toBeVisible();
    for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
      await page.setViewportSize({ width, height: 1000 });
      await page.screenshot({ path: `${shots}/directory-${size}-${theme}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
  }
  await page.goto(`/admin/users/${me.id}`);
  await page.getByRole("button", { name: "Revogar administração", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Revogar administração?", exact: true })).toBeFocused();
  await page.screenshot({ path: `${shots}/confirmation-mobile-dark.png`, fullPage: true });
  await page.getByRole("button", { name: "Cancelar", exact: true }).click();
  await expect(page.getByRole("button", { name: "Revogar administração", exact: true })).toBeFocused();
  await page.goto("/admin/users");
  await page.route("**/api/v1/users", async route => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fetch(); await route.abort("failed");
  });
  await page.getByLabel("Nome da nova conta").fill("Conta com resposta não confirmada");
  await page.getByLabel("E-mail da nova conta").fill(`capture-${crypto.randomUUID()}@example.invalid`);
  await page.getByLabel("Senha inicial").fill("Synthetic capture credential 2026!");
  await page.getByRole("button", { name: "Criar conta", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar resultado" })).toBeVisible();
  await expect(page.getByLabel("Senha inicial")).toHaveValue("");
  await page.screenshot({ path: `${shots}/uncertain-mobile-dark.png`, fullPage: true });
});
