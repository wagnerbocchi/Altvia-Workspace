import { test, expect } from "@playwright/test";

test.beforeEach(async ({ context }) => {
  await context.addCookies([{ name: "__Host-altvia_session", value: process.env.ALTVIA_E2E_WORK_MANAGER_SESSION!,
    domain: "127.0.0.1", path: "/", secure: true, httpOnly: true, sameSite: "Lax" }]);
});

test("workspace navigation follows real routes and capability visibility", async ({ page }) => {
  await page.goto("/my-work");
  const navigation = page.getByRole("navigation", { name: "Navegacao principal" });
  await expect(navigation.getByRole("link", { name: "Meu trabalho", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(navigation.getByRole("link", { name: "Administrar contas" })).toHaveCount(0);
  await navigation.getByRole("link", { name: "Projetos", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Projetos", exact: true })).toBeVisible();
  await expect(navigation.getByRole("link", { name: "Projetos", exact: true })).toHaveAttribute("aria-current", "page");
  await page.goto(`/projects/${process.env.ALTVIA_E2E_WORK_PROJECT_ID}/work`);
  await expect(navigation.getByRole("link", { name: "Projetos", exact: true })).toHaveAttribute("aria-current", "page");
});

test("mobile navigation expands with keyboard and Escape restores its trigger", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/my-work");
  const toggle = page.getByRole("button", { name: "Navegacao principal", exact: true });
  const navigation = page.getByRole("navigation", { name: "Navegacao principal" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(navigation).toBeHidden();
  await toggle.focus(); await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(navigation.getByRole("link", { name: "Meu trabalho", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(toggle).toBeFocused(); await expect(navigation).toBeHidden();
  await toggle.click();
  await navigation.getByRole("link", { name: "Clientes", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Clientes", exact: true })).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
});

test("private navigation disappears during identity failure and after logout", async ({ page }) => {
  await page.goto("/");
  const navigation = page.getByRole("navigation", { name: "Navegacao principal" });
  await expect(navigation).toBeVisible();
  await page.route("**/api/v1/auth/me", route => route.abort());
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await expect(page.getByRole("heading", { name: "Conexão indisponível" })).toBeVisible();
  await expect(navigation).toBeHidden();
  await expect(page.locator(".location")).not.toContainText("Minha conta");
  await page.unroute("**/api/v1/auth/me");
  await page.getByRole("button", { name: "Tentar novamente" }).click();
  await expect(navigation).toBeVisible();
  await page.getByRole("button", { name: "Sair da conta" }).click();
  await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeVisible();
  await expect(navigation).toHaveCount(0);
});

test("administrative links use the existing identity capability", async ({ page, context }) => {
  await context.clearCookies();
  const login = await page.request.post("/api/v1/auth/sessions", { data: {
    email: process.env.ALTVIA_E2E_ADMIN_EMAIL!, password: process.env.ALTVIA_E2E_ADMIN_PASSWORD!,
  }, headers: { Origin: "https://127.0.0.1:3443" } });
  expect(login.status()).toBe(201);
  await page.goto("/admin/users");
  const navigation = page.getByRole("navigation", { name: "Navegacao principal" });
  await expect(navigation.getByRole("link", { name: "Administrar contas" })).toHaveAttribute("aria-current", "page");
  await expect(navigation.getByRole("link", { name: "Administrar equipes" })).toBeVisible();
});
