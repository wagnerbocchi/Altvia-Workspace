import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { mkdir } from "node:fs/promises";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const email = process.env.ALTVIA_E2E_EMAIL!;
const password = process.env.ALTVIA_E2E_PASSWORD!;
if (!email || !password) throw Error("Run the guarded browser-test harness");

async function enter(page: Page) {
  await page.goto("/");
  await page.getByLabel("E-mail", { exact: true }).fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Minha conta" })).toBeVisible();
}

test("keyboard validation, password reveal and generic invalid credentials", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByText("Informe um e-mail válido.")).toBeVisible();
  await expect(page.getByLabel("E-mail", { exact: true })).toBeFocused();
  await page.getByLabel("E-mail", { exact: true }).fill(email);
  await page.getByLabel("Senha", { exact: true }).fill("intentionally-wrong-password");
  await page.getByRole("button", { name: "Mostrar senha" }).click();
  await expect(page.getByLabel("Senha", { exact: true })).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Ocultar senha" }).click();
  await page.getByLabel("Senha", { exact: true }).press("Enter");
  await expect(page.getByRole("alert").filter({ hasText: "E-mail ou senha incorretos" })).toBeVisible();
  await expect(page.getByLabel("Senha", { exact: true })).toHaveValue("");
  await page.screenshot({ path: `${root}/.impeccable/review/error-desktop.png`, fullPage: true });
});

test("real secure login persists across reload and logout revokes the session", async ({ page, context }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await enter(page);
  await expect(page.getByText(email, { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Minha conta" })).toBeFocused();
  const cookie = (await context.cookies()).find(item => item.name === "__Host-altvia_session")!;
  expect(cookie.secure && cookie.httpOnly).toBe(true);
  expect(cookie.sameSite).toBe("Lax");
  await expect(page.evaluate(() => ({ ...localStorage }))).resolves.toEqual({});
  await page.reload();
  await expect(page.getByText(email, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sair da conta" }).click();
  await expect(page.getByRole("status")).toHaveText("Você saiu da conta com segurança.");
  await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeFocused();
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);
  expect((await context.cookies()).some(item => item.name === "__Host-altvia_session")).toBe(false);
  expect(errors).toEqual([]);
});

test("expired server session returns to login on visibility revalidation", async ({ page }) => {
  await enter(page);
  execFileSync(process.platform === "win32" ? "uv.exe" : "uv", ["run", "python", "scripts/browser_fixture.py"], {
    cwd: root, env: { ...process.env, ALTVIA_E2E_EXPIRE: "1" }, stdio: "pipe",
  });
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Sua sessão terminou. Entre novamente.");
});

test("network failure retries and failed logout never claims success", async ({ page }) => {
  await page.route("**/api/v1/auth/me", route => route.abort());
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Conexão indisponível" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Conexão indisponível" })).toBeFocused();
  await page.screenshot({ path: `${root}/.impeccable/review/offline-desktop.png`, fullPage: true });
  await page.unroute("**/api/v1/auth/me");
  await page.getByRole("button", { name: "Tentar novamente" }).click();
  await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeFocused();
  await enter(page);
  await page.route("**/api/v1/auth/me", route => route.abort());
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await expect(page.getByRole("heading", { name: "Conexão indisponível" })).toBeFocused();
  await page.unroute("**/api/v1/auth/me");
  await page.getByRole("button", { name: "Tentar novamente" }).click();
  await expect(page.getByRole("heading", { name: "Minha conta" })).toBeFocused();
  await page.route("**/api/v1/auth/sessions/current", route => route.abort());
  await page.getByRole("button", { name: "Sair da conta" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Sua sessão pode continuar ativa" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Minha conta" })).toBeVisible();
  await page.unroute("**/api/v1/auth/sessions/current");
  await page.getByRole("button", { name: "Sair da conta" }).click();
  await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeVisible();
});

test("real gateway preserves Origin and CSRF checks and restrictive document policy", async ({ page }) => {
  const document = await page.goto("/");
  const csp = document!.headers()["content-security-policy"];
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toContain("'nonce-");
  expect(csp).not.toContain("'unsafe-eval'");
  expect(document!.headers()["cache-control"]).toContain("no-store");
  expect((await page.request.get("/_next/image?url=%2Ffavicon.ico&w=64&q=75")).status()).toBe(404);
  expect((await page.request.post("/api/v1/auth/sessions", { data: { email, password },
    headers: { Origin: "https://foreign.invalid" } })).status()).toBe(403);
  await enter(page);
  expect((await page.request.delete("/api/v1/auth/sessions/current", {
    headers: { Origin: "https://127.0.0.1:3443" },
  })).status()).toBe(403);
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(200);
});

test("pending login prevents duplicates and rate-limit recovery stays actionable", async ({ page }) => {
  await page.goto("/");
  let finish!: () => void;
  const gate = new Promise<void>(resolve => { finish = resolve; });
  await page.route("**/api/v1/auth/sessions", async route => {
    await gate;
    await route.fulfill({ status: 429, headers: { "Retry-After": "120" }, body: "{}" });
  });
  await page.getByLabel("E-mail", { exact: true }).fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("button", { name: "Entrando..." })).toBeDisabled();
  finish();
  await expect(page.getByRole("alert").filter({ hasText: "Aguarde 120 segundos" })).toBeVisible();
});

test("desktop and mobile light/dark render, accessibility and theme persistence", async ({ page }) => {
  const screenshots = fileURLToPath(new URL("../../../.impeccable/review/", import.meta.url));
  await mkdir(screenshots, { recursive: true });
  for (const [name, width, height] of [["desktop", 1440, 900], ["mobile", 390, 844]] as const) {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeVisible();
    for (const theme of ["light", "dark"]) {
      await page.evaluate(theme => { localStorage.setItem("theme", theme); }, theme);
      await page.reload();
      await expect(page.locator("html")).toHaveClass(theme);
      await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(axe.violations).toEqual([]);
      await page.screenshot({ path: resolvePath(screenshots, `${name}${theme === "dark" ? "-dark" : ""}.png`), fullPage: true });
    }
  }
  await page.getByRole("button", { name: "Alternar tema claro e escuro" }).click();
  await expect(page.locator("html")).toHaveClass("light");
  await page.reload();
  await expect(page.locator("html")).toHaveClass("light");
  await enter(page);
  await page.screenshot({ path: resolvePath(screenshots, "account-mobile.png"), fullPage: true });
  await expect(page.getByRole("heading", { name: "Minha conta" })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
});

function resolvePath(directory: string, name: string) { return `${directory}/${name}`; }
