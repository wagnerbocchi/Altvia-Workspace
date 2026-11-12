import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const folder = resolve(root, ".impeccable/review/workspace-redesign");
const origin = "https://127.0.0.1:3443";
const env = (key: string) => process.env[`ALTVIA_E2E_${key}`]!;
async function session(page: Page, key: string) {
  await page.context().clearCookies();
  await page.context().addCookies([{ name: "__Host-altvia_session", value: env(key + "_SESSION"), url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const me = await page.request.get("/api/v1/auth/me"); expect(me.status()).toBe(200); return me.json();
}
async function create(page: Page, path: string, data: object) {
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const response = await page.request.post(`/api/v1${path}`, { data, headers: {
    Origin: origin, "X-CSRF-Token": me.csrf_token, "Idempotency-Key": crypto.randomUUID(),
  } });
  expect(response.status()).toBe(201); return response.json();
}

// Opt in with ALTVIA_REDESIGN_CAPTURE=1 and pass workspace-captures.spec.ts to
// node apps/web/scripts/browser-test.mjs on a fresh guarded disposable database. These are real
// persisted synthetic records, never runtime demo rows or customer data.
test("@redesign-capture all existing routes and representative states", async ({ page }) => {
  test.setTimeout(600_000);
  await mkdir(folder, { recursive: true });
  const coverage: object[] = [];
  async function capture(name: string, path: string, axe = false, action?: () => Promise<void>) {
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: /^Carregando|^Verificando|^Confirmando/ })).toHaveCount(0);
    if (action) await action();
    const files: string[] = [];
    for (const width of [1440, 390]) for (const theme of ["light", "dark"]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(value => { document.documentElement.classList.toggle("dark", value === "dark"); document.documentElement.classList.toggle("light", value === "light"); (document.activeElement as HTMLElement)?.blur(); scrollTo(0, 0); }, theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (axe) expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      const filename = `${name}-${width}-${theme}.png`; files.push(filename);
      await page.screenshot({ path: resolve(folder, filename), fullPage: true });
    }
    await page.setViewportSize({ width: 320, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    coverage.push({ name, path, heading: await page.locator("main h1").textContent(), files, overflow320: "passed", axe });
    await writeFile(resolve(folder, "coverage.json"), JSON.stringify(coverage, null, 2));
  }
  await capture("login", "/", true);
  const user = await session(page, "WORK_MANAGER");
  const project = env("WORK_PROJECT_ID");
  const titles = ["Revisar acessos da equipe de atendimento", "Validar restauracao do ambiente de homologacao", "Documentar a rotina de verificacao dos backups", "Acompanhar atualizacao da rede e confirmar conectividade nas unidades", "Conferir inventario de equipamentos"];
  let task = "";
  for (const [index, title] of titles.entries()) {
    const result = await create(page, "/work-items", { project_id: project, title, description: "Registro sintetico para verificacao visual do workspace.", priority: index % 2 ? "medium" : "high", work_type: "one_off", owner_id: user.id, assignee_ids: [user.id] });
    task ||= result.work_item_id;
  }
  await capture("account", "/", true);
  await capture("my-work", "/my-work", true);
  await capture("work-detail", `/work-items/${task}`);
  await capture("projects", "/projects");
  await capture("project-detail", `/projects/${project}`);
  await capture("project-members", `/projects/${project}/members`);
  await capture("project-work", `/projects/${project}/work`);
  await capture("project-board", `/projects/${project}/work`, true, async () => { await page.getByRole("button", { name: "Quadro", exact: true }).click(); await expect(page.getByRole("region", { name: "Quadro de tarefas com rolagem" })).toBeVisible(); });
  const milestone = await create(page, `/projects/${project}/milestones`, { title: "Validacao operacional", due: { precision: "date", date: "2026-11-20", timezone: "America/Sao_Paulo" } });
  await capture("milestones", `/projects/${project}/milestones`);
  await capture("milestone-detail", `/projects/${project}/milestones/${milestone.milestone_id}`);
  await capture("areas", "/operational-areas");
  await capture("queues", "/service-desk/queues");
  await capture("queue-detail", `/service-desk/queues/${env("QUEUE_ID")}`);
  await capture("queue-members", `/service-desk/queues/${env("QUEUE_ID")}/members`);
  await session(page, "CONTACT_MANAGER");
  const client = env("CONTACT_CLIENT_ID");
  const contact = await create(page, `/clients/${client}/contacts`, { display_name: "Marina - Operacoes", email: `marina-${crypto.randomUUID()}@example.invalid` });
  await capture("clients", "/clients");
  await capture("client-detail", `/clients/${client}`);
  await capture("contacts", `/clients/${client}/contacts`);
  await capture("contact-detail", `/clients/${client}/contacts/${contact.contact_id}`);
  await session(page, "TICKET_MANAGER");
  let ticket = "";
  for (const [index, subject] of ["Acesso ao sistema de atendimento", "Conexao intermitente na unidade administrativa", "Solicitacao de revisao das permissoes de uma pasta compartilhada", "Impressora da recepcao indisponivel", "Orientacao para configurar o correio no novo equipamento"].entries()) {
    const result = await create(page, "/tickets", { queue_id: env("TICKET_QUEUE_ID"), client_id: env("TICKET_CLIENT_ID"), requester_id: env("TICKET_REQUESTER_ID"), subject, priority: index % 2 ? "medium" : "high" });
    ticket ||= result.ticket_id;
  }
  await capture("tickets", "/service-desk/tickets", true);
  await capture("ticket-new", "/service-desk/tickets/new");
  await capture("ticket-detail", `/service-desk/tickets/${ticket}`);
  await session(page, "NOTE_AUTHOR");
  const incoming = JSON.parse(execFileSync(resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"), ["scripts/browser_incoming_fixture.py"], { cwd: root, env: process.env, input: JSON.stringify({ subject: "Confirmacao da janela de manutencao", body: "Mensagem sintetica para revisao visual.\nPodemos confirmar a janela de manutencao combinada para sexta-feira?" }), encoding: "utf8" }));
  await capture("mail-cases", "/service-desk/mail-cases");
  await capture("mail-detail", `/service-desk/mail-cases/${incoming.case_id}`);
  await page.context().clearCookies();
  const login = await page.request.post("/api/v1/auth/sessions", { data: { email: env("ADMIN_EMAIL"), password: env("ADMIN_PASSWORD") }, headers: { Origin: origin } });
  expect(login.status()).toBe(201); const admin = (await login.json()).user;
  const team = await create(page, "/teams", { name: "Operacoes - verificacao visual" });
  await capture("teams", "/admin/teams");
  await capture("team-detail", `/admin/teams/${team.id}`);
  await capture("users", "/admin/users");
  await capture("user-detail", `/admin/users/${admin.id}`);
  await session(page, "WORK_READER");
  await capture("empty-work", "/my-work", false, async () => { await expect(page.getByText("Nenhuma tarefa sua corresponde aos filtros.", { exact: false })).toBeVisible(); });
  await session(page, "WORK_MANAGER");
  await page.route("**/api/v1/my-work?**", route => route.abort());
  await capture("work-error", "/my-work", false, async () => { await expect(page.locator(".workspace-content").getByRole("alert")).toContainText("Não foi possível carregar os dados"); });
  await page.unroute("**/api/v1/my-work?**");
  await page.goto("/my-work"); await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => { document.documentElement.classList.add("dark"); document.documentElement.classList.remove("light"); });
  await page.getByRole("button", { name: "Navegacao principal", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Navegacao principal" }).getByRole("link", { name: "Meu trabalho", exact: true })).toBeFocused();
  await page.screenshot({ path: resolve(folder, "navigation-focus-390-dark.png"), fullPage: true });
});
