// Actual packaged frontend/HTTPS identity proof. Synthetic task stack only.
import { strict as assert } from "node:assert";
import { execFileSync } from "node:child_process";
import { createHash, X509Certificate } from "node:crypto";
import { readFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

if (process.env.ALTVIA_ALLOW_CONTAINER_TEST !== "1") throw Error("Explicit container-test opt-in required");
const [engine, project, directory] = process.argv.slice(2);
assert.ok(["docker", "podman"].includes(engine));
assert.match(project, /^altvia-test-[a-f0-9]{10}$/);
const root = fileURLToPath(new URL("../", import.meta.url));
const work = resolve(directory);
assert.equal(work, resolve(root, ".superpowers/container-tests", project));
let input = "";
for await (const chunk of process.stdin) {
  input += chunk;
  if (input.length > 8192) throw Error("Test input too large");
}
const { origin, email, password } = JSON.parse(input);
const url = new URL(origin);
assert.equal(url.hostname, "workspace.altvia.test");
assert.equal(url.protocol, "https:");
assert.ok(url.port && !url.username && !url.password && url.pathname === "/");
const cert = new X509Certificate(await readFile(resolve(work, "secrets/tls_cert")));
const pin = createHash("sha256").update(cert.publicKey.export({ type: "spki", format: "der" })).digest("base64");
const webRequire = createRequire(new URL("../apps/web/package.json", import.meta.url));
const { chromium, expect } = webRequire("@playwright/test");
const axeModule = webRequire("@axe-core/playwright");
const AxeBuilder = axeModule.default ?? axeModule;
const screenshots = resolve(work, "screenshots");
await mkdir(screenshots, { recursive: true });
let browser;
try {
  browser = await chromium.launch({ args: [
    `--ignore-certificate-errors-spki-list=${pin}`,
    "--host-resolver-rules=MAP workspace.altvia.test 127.0.0.1",
  ] });
  const context = await browser.newContext({ baseURL: origin, ignoreHTTPSErrors: false,
    viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const document = await page.goto("/");
  assert.equal(document.status(), 200);
  const headers = document.headers();
  assert.ok(headers["content-security-policy"].includes("'nonce-"));
  assert.ok(headers["content-security-policy"].includes("frame-ancestors 'none'"));
  assert.ok(!headers["content-security-policy"].includes("'unsafe-eval'"));
  assert.ok(headers["cache-control"].includes("no-store"));
  await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeVisible();
  // Rendering/axe checks share the same captures, with no filled credentials.
  for (const [name, width, height] of [["desktop", 1440, 900], ["mobile", 390, 844]]) {
    await page.setViewportSize({ width, height });
    for (const theme of ["light", "dark"]) {
      await page.evaluate(theme => localStorage.setItem("theme", theme), theme);
      await page.reload();
      await expect(page.locator("html")).toHaveClass(theme);
      await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeVisible();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.deepEqual((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations, []);
      await page.screenshot({ path: resolve(screenshots, `${name}-${theme}.png`), fullPage: true });
    }
  }
  await page.getByLabel("E-mail", { exact: true }).fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Minha conta" })).toBeFocused();
  await expect(page.getByText(email, { exact: true })).toBeVisible();
  const cookie = (await context.cookies()).find(item => item.name === "__Host-altvia_session");
  assert.ok(cookie?.secure && cookie.httpOnly && cookie.sameSite === "Lax");
  assert.deepEqual(Object.keys(await page.evaluate(() => ({ ...localStorage }))), ["theme"]);
  // APIRequestContext has a separate Node DNS/TLS transport. These probes must
  // use the browser's pinned certificate, reserved host mapping and cookies.
  const publicDocument = await page.evaluate(async () => (await fetch("/")).text());
  assert.ok(!publicDocument.includes(email), "SSR serialized an authenticated identity");
  // Browser JS supplies its real Origin and cannot forge another origin. The
  // existing strict-CA Python probe separately verifies foreign-Origin denial.
  assert.equal(await page.evaluate(async () => (await fetch("/api/v1/auth/sessions/current", {
    method: "DELETE",
  })).status), 403);
  assert.equal(await page.evaluate(async () => (await fetch("/_next/image?url=%2Ffavicon.ico&w=64&q=75")).status), 404);
  execFileSync(engine, ["compose", "-f", "infra/compose.yaml", "-p", project, "up", "-d",
    "--no-deps", "--no-build", "--force-recreate", "--wait", "--wait-timeout", "90", "web"],
  { cwd: root, env: process.env, stdio: "pipe" });
  // The edge's dynamic DNS may still hold the old web address for five seconds.
  let recovered = false;
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      const response = await page.goto("/");
      if (response.status() === 200) { recovered = true; break; }
    } catch { /* bounded startup/DNS recovery */ }
    await delay(500);
  }
  assert.ok(recovered, "Packaged frontend did not recover");
  await expect(page.getByText(email, { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Minha conta" })).toBeVisible();
  assert.deepEqual((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations, []);
  await page.screenshot({ path: resolve(screenshots, "account-mobile.png"), fullPage: true });
  await page.getByRole("link", { name: "Administrar equipes" }).click();
  const teamName = `Equipe ${project}`;
  await page.getByLabel("Nome da nova equipe").fill(teamName);
  await page.getByRole("button", { name: "Criar equipe", exact: true }).click();
  await expect(page.getByRole("heading", { name: teamName, exact: true })).toBeVisible();
  await page.getByRole("radio", { name: /reader@example.test/ }).check();
  await page.getByRole("button", { name: "Adicionar participante", exact: true }).click();
  await expect(page.getByRole("list", { name: "Participantes da equipe" })).toContainText("Container Reader");
  await page.reload();
  await expect(page.getByRole("list", { name: "Participantes da equipe" })).toContainText("Container Reader");
  await page.getByRole("button", { name: "Arquivar equipe", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar arquivamento" }).click();
  await expect(page.getByText("Equipe arquivada", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Adicionar participante", exact: true })).toBeDisabled();
  await page.screenshot({ path: resolve(screenshots, "team-mobile.png"), fullPage: true });
  assert.deepEqual((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations, []);
  await page.getByRole("button", { name: "Restaurar equipe", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar restauração" }).click();
  await expect(page.getByText("Equipe ativa", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Remover Container Reader da equipe" }).click();
  await page.getByRole("button", { name: "Confirmar remoção" }).click();
  await expect(page.getByText("Nenhum participante nesta equipe.", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Voltar às equipes" }).click();
  await expect(page.getByRole("link", { name: teamName, exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Voltar à minha conta" }).click();
  await page.getByRole("link", { name: "Administrar contas" }).click();
  const accountName = `Conta ${project}`;
  await page.getByLabel("Nome da nova conta").fill(accountName);
  await page.getByLabel("E-mail da nova conta").fill(`${project}@example.invalid`);
  await page.getByLabel("Senha inicial").fill(password);
  await page.getByRole("button", { name: "Criar conta", exact: true }).click();
  await expect(page.getByRole("heading", { name: accountName, exact: true })).toBeVisible();
  await page.getByLabel("Nova senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Redefinir senha", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar nova senha", exact: true }).click();
  await expect(page.getByLabel("Nova senha", { exact: true })).toHaveValue("");
  await page.getByRole("button", { name: "Desativar conta", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar desativação", exact: true }).click();
  await expect(page.getByText("Conta desativada", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Conta desativada", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Ativar conta", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar ativação", exact: true }).click();
  await expect(page.getByText("Conta ativa", { exact: true })).toBeVisible();
  await page.screenshot({ path: resolve(screenshots, "admin-account-mobile.png"), fullPage: true });
  assert.deepEqual((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations, []);
  await page.getByRole("link", { name: "Voltar às contas" }).click();
  await page.getByRole("link", { name: "Voltar à minha conta" }).click();
  await page.getByRole("link", { name: "Clientes", exact: true }).click();
  const ownId = await page.evaluate(async () => (await (await fetch("/api/v1/auth/me")).json()).id);
  const clientName = `Cliente ${project}`;
  await page.getByLabel("Nome do cliente", { exact: true }).fill(clientName);
  await page.getByLabel("Gestor inicial", { exact: true }).selectOption(ownId);
  await page.getByRole("button", { name: "Cadastrar cliente", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeVisible();
  await page.getByLabel("E-mail", { exact: true }).fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.getByRole("link", { name: clientName, exact: true }).click();
  await page.getByRole("button", { name: "Arquivar cliente", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar arquivamento", exact: true }).click();
  await expect(page.getByText("Cliente arquivado", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Cliente arquivado", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Restaurar cliente", exact: true }).click();
  await expect(page.getByText("Cliente ativo", { exact: true })).toBeVisible();
  for (let attempt = 0; attempt < 60; attempt++) {
    await page.getByRole("button", { name: "Atualizar histórico", exact: true }).click();
    const present = await page.getByText("Cliente cadastrado", { exact: true }).count();
    if (present) break;
    await delay(250);
  }
  await expect(page.getByText("Cliente cadastrado", { exact: true })).toBeVisible();
  await page.screenshot({ path: resolve(screenshots, "client-mobile.png"), fullPage: true });
  assert.deepEqual((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations, []);
  await page.getByRole("link", { name: "Voltar aos clientes", exact: true }).click();
  await page.getByRole("link", { name: "Voltar à minha conta" }).click();
  await page.getByRole("button", { name: "Sair da conta" }).click();
  await expect(page.getByRole("status")).toHaveText("Você saiu da conta com segurança.");
  await expect(page.getByRole("heading", { name: "Acesse seu workspace" })).toBeFocused();
  assert.equal(await page.evaluate(async () => (await fetch("/api/v1/auth/me")).status), 401);
  assert.equal((await context.cookies()).some(item => item.name === "__Host-altvia_session"), false);
  assert.deepEqual(errors, []);
  await context.close();
  console.log("Packaged browser login/HTTPS/CSP/CSRF/recreation/teams/roster/accounts/clients/logout/themes/axe proof passed.");
} catch (error) {
  // Playwright locator diagnostics can include fill arguments. Never publish them.
  console.error(String(error).replaceAll(password, "[REDACTED]"));
  process.exitCode = 1;
} finally {
  await browser?.close();
}
