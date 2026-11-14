import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const origin = "https://127.0.0.1:3443";
function env(key: string) {
  const value = process.env["ALTVIA_E2E_AUTOMATION_" + key];
  if (!value) throw Error("Real isolated fixture required: " + key);
  return value;
}
async function login(page: Page, kind = "MANAGER") {
  await page.context().addCookies([{ name: "__Host-altvia_session", value: env(kind + "_SESSION"), url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const response = await page.request.get("/api/v1/auth/me");
  expect(response.status()).toBe(200);
  return (await response.json()).csrf_token as string;
}
const headers = (csrf: string, version: number) => ({ Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${version}"`, "Idempotency-Key": crypto.randomUUID() });
const root = `/api/v1/ticket-queues/`;
async function configuration(page: Page) {
  await page.goto(`/service-desk/queues/${env("QUEUE")}`);
  const panel = page.getByRole("region", { name: "SLA e calendarios", exact: true });
  await expect(panel.getByRole("heading", { name: "SLA e calendarios", exact: true })).toBeVisible();
  await panel.getByLabel("Cliente do SLA", { exact: true }).selectOption(env("CLIENT"));
  await expect(panel.getByRole("button", { name: "Novo calendario", exact: true })).toBeEnabled();
  return panel;
}
async function calendarForm(page: Page, name: string) {
  await page.getByRole("button", { name: "Novo calendario", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Cadastrar calendario", exact: true })).toBeFocused();
  await page.getByLabel("Nome do calendario", { exact: true }).fill(name);
  await page.getByLabel("Fuso IANA do calendario", { exact: true }).fill("UTC");
  await page.getByLabel("Dia da janela 1", { exact: true }).selectOption("0");
  await page.getByLabel("Inicio da janela 1", { exact: true }).fill("00:00");
  await page.getByLabel("Termino da janela 1", { exact: true }).fill("24:00");
  await page.getByLabel("Calendario ativo para novos ciclos", { exact: true }).check();
}
async function capture(page: Page, label: string) {
  const folder = fileURLToPath(new URL("../../../.impeccable/review/ticket-sla/", import.meta.url));
  await mkdir(folder, { recursive: true });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(el => el.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      for (const label of await page.getByRole("list", { name: "Calendarios de SLA", exact: true }).locator(".record-text > strong").all()) {
        const lines = await label.evaluate(el => el.getBoundingClientRect().height / Number.parseFloat(getComputedStyle(el).lineHeight));
        expect(lines, "Calendar names must remain readable beside their actions").toBeLessThanOrEqual(4);
      }
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.evaluate(async () => { scrollTo(0, 0); await new Promise(requestAnimationFrame); });
      await page.screenshot({ path: `${folder}/${label}-${width}-${theme}.png`, fullPage: true });
    }
  }
}
async function confirmed(page: Page) {
  await expect(page.getByText("Configuracao confirmada. Os ciclos existentes preservam suas revisoes.", { exact: true })).toBeVisible();
}
async function createTicket(page: Page, csrf: string) {
  const response = await page.request.post("/api/v1/tickets", { headers: headers(csrf, 1), data: { queue_id: env("QUEUE"), client_id: env("CLIENT"), requester_id: env("REQUESTER"), subject: "SLA synthetic " + crypto.randomUUID(), priority: "critical" } });
  expect(response.status()).toBe(201);
  return (await response.json()).ticket_id as string;
}
async function transition(page: Page, target: "open" | "resolved") {
  await page.getByLabel("Proximo estado", { exact: true }).selectOption(target);
  await page.getByLabel("Motivo", { exact: true }).fill("Synthetic SLA lifecycle");
  await page.getByRole("button", { name: "Alterar estado", exact: true }).click();
  await expect(page.locator(".admin-intro")).toContainText(target === "open" ? "Aberto" : "Resolvido");
}

test("@sla configure frozen revisions, activate deliberately and read real worker cycles", async ({ page }) => {
  test.setTimeout(240_000);
  const csrf = await login(page);
  const panel = await configuration(page);
  const name = "Calendario <b>literal</b> " + crypto.randomUUID();
  await calendarForm(page, name);
  await expect(page.getByLabel("Nome do calendario", { exact: true })).toHaveValue(name);
  await capture(page, "calendar-form");
  for (let i = 2; i <= 7; i++) {
    await page.getByRole("button", { name: "Adicionar janela semanal", exact: true }).click();
    await page.getByLabel(`Dia da janela ${i}`, { exact: true }).selectOption(String(i - 1));
    await page.getByLabel(`Inicio da janela ${i}`, { exact: true }).fill("00:00");
    await page.getByLabel(`Termino da janela ${i}`, { exact: true }).fill("24:00");
  }
  await page.getByRole("button", { name: "Adicionar feriado", exact: true }).click();
  await page.getByLabel("Data sem atendimento 1", { exact: true }).fill("2026-12-25");
  await page.getByLabel("Descricao opcional da data 1", { exact: true }).fill("Data sintetica de teste");
  await page.getByRole("button", { name: "Cadastrar calendario revisado", exact: true }).click();
  await confirmed(page);
  const calendars = await (await page.request.get(`${root}${env("QUEUE")}/business-calendars?client_id=${env("CLIENT")}`)).json();
  const calendar = calendars.items.find((row: { name: string }) => row.name === name);
  expect(calendar).toBeTruthy();
  const original = await (await page.request.get(`${root}${env("QUEUE")}/business-calendars/${calendar.id}`)).json();
  expect(original.windows).toHaveLength(7); expect(original.holidays).toHaveLength(1);
  await page.getByRole("button", { name: "Nova politica de SLA", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Cadastrar politica de SLA", exact: true })).toBeFocused();
  await page.getByLabel("Nome da politica", { exact: true }).fill("SLA sintetico geral");
  await page.getByLabel("Calendario da politica", { exact: true }).selectOption(calendar.id);
  await page.getByRole("button", { name: "Usar esta revisao do calendario", exact: true }).click();
  await page.getByLabel("Meta de primeira resposta (minutos uteis)", { exact: true }).fill("60");
  await page.getByLabel("Meta de resolucao (minutos uteis)", { exact: true }).fill("240");
  await page.getByLabel("Aproximacao do limite (minutos uteis)", { exact: true }).fill("10");
  await page.getByLabel("Aguardando cliente", { exact: true }).check();
  await capture(page, "policy-form");
  await page.getByRole("button", { name: "Cadastrar politica desativada", exact: true }).click();
  await expect(panel.getByText("Politica desativada", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: `Editar calendario ${name}`, exact: true }).click();
  await page.getByLabel("Nome do calendario", { exact: true }).fill("Nome posterior do calendario");
  await page.getByRole("button", { name: "Salvar revisao do calendario", exact: true }).click();
  await confirmed(page);
  await panel.getByRole("button", { name: "Revisar ativacao do SLA", exact: true }).click();
  const review = page.getByRole("region", { name: "Ativar politica de SLA?", exact: true });
  await expect(review.getByRole("heading", { name: "Ativar politica de SLA?", exact: true })).toBeFocused();
  await expect(review).toContainText(name);
  await expect(review).not.toContainText("Nome posterior do calendario");
  await capture(page, "activation-review");
  await review.getByRole("button", { name: "Cancelar revisao do SLA", exact: true }).click();
  await expect(panel.getByRole("button", { name: "Revisar ativacao do SLA", exact: true })).toBeFocused();
  await panel.getByRole("button", { name: "Revisar ativacao do SLA", exact: true }).click();
  await review.getByRole("button", { name: "Confirmar ativacao do SLA", exact: true }).click();
  await expect(panel.getByText("Politica ativada", { exact: true })).toBeVisible();
  const ticket = await createTicket(page, csrf);
  await page.goto(`/service-desk/tickets/${ticket}`);
  const outcomes = page.getByRole("region", { name: "SLA do chamado", exact: true });
  await expect(outcomes).toBeVisible();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/tickets/${ticket}/sla`)).json()).current.state, { timeout: 30_000 }).toBe("ready");
  await outcomes.getByRole("button", { name: "Atualizar SLA", exact: true }).click();
  await expect(outcomes.getByText("Em andamento", { exact: true })).toHaveCount(2);
  await expect(outcomes).toContainText(name);
  await capture(page, "running-outcomes");
  await transition(page, "open");
  await transition(page, "resolved");
  await expect.poll(async () => (await (await page.request.get(`/api/v1/tickets/${ticket}/sla`)).json()).current.first_response.status, { timeout: 45_000 }).toBe("unfulfilled");
  await outcomes.getByRole("button", { name: "Atualizar SLA", exact: true }).click();
  await expect(outcomes.getByText("Nao cumprido", { exact: true })).toBeVisible();
  await expect(outcomes.getByText("Cumprido", { exact: true })).toBeVisible();
  const queuePath = `${root}${env("QUEUE")}`;
  const queue = await (await page.request.get(queuePath)).json();
  expect((await page.request.patch(queuePath, { headers: headers(csrf, queue.version), data: { allow_reopen: true } })).status()).toBe(200);
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await transition(page, "open");
  await outcomes.getByRole("button", { name: "Atualizar SLA", exact: true }).click();
  await expect(outcomes.getByRole("heading", { name: "Ciclo atual 2", exact: true })).toBeVisible();
  await expect(outcomes.getByRole("heading", { name: "Ciclo anterior 1", exact: true })).toBeVisible();
  await capture(page, "reopened-history");
});

test("@sla uncertain calendar create retains original intent and newer revision", async ({ page }) => {
  const csrf = await login(page);
  let createdId: string | undefined;
  const panel = await configuration(page);
  const attempts: { body: string | null; key: string | undefined; version: string | undefined }[] = [];
  await page.route(`**${root}${env("QUEUE")}/business-calendars`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    const request = route.request();
    attempts.push({ body: request.postData(), key: request.headers()["idempotency-key"], version: request.headers()["if-match"] });
    const response = await route.fetch();
    if (attempts.length === 1) { expect(response.status()).toBe(201); createdId = (await response.json()).calendar_id; }
    await route.fulfill(attempts.length === 1 ? { status: 503, contentType: "application/problem+json", body: JSON.stringify({ code: "synthetic_lost_response" }) } : { response });
  });
  await calendarForm(page, "Recuperacao " + crypto.randomUUID());
  await page.getByRole("button", { name: "Cadastrar calendario revisado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar configuracao de SLA", exact: true })).toBeVisible();
  await expect(panel.getByLabel("Cliente do SLA", { exact: true })).toBeDisabled();
  expect(createdId).toBeTruthy();
  const detailPath = `${root}${env("QUEUE")}/business-calendars/${createdId}`;
  const before = await (await page.request.get(detailPath)).json();
  const changed = await page.request.patch(detailPath, { headers: { ...headers(csrf, before.version), "If-Match-Queue": `"${before.queue_version}"` }, data: { name: "Nome revisado depois do aceite" } });
  expect(changed.status()).toBe(200);
  await page.getByRole("button", { name: "Verificar configuracao de SLA", exact: true }).click();
  await confirmed(page);
  expect(attempts).toHaveLength(2); expect(attempts[1]).toEqual(attempts[0]);
  const after = await (await page.request.get(detailPath)).json();
  expect(after.version).toBe(2); expect(after.name).toBe("Nome revisado depois do aceite");
});

test("@sla acknowledged create retries only its read confirmation", async ({ page }) => {
  await login(page);
  await configuration(page);
  let posts = 0, failed = false;
  await page.route(`**${root}${env("QUEUE")}/business-calendars**`, async route => {
    if (route.request().method() === "POST") { posts++; return route.continue(); }
    const path = new URL(route.request().url()).pathname;
    if (!failed && posts && path !== `${root}${env("QUEUE")}/business-calendars`) {
      failed = true;
      return route.fulfill({ status: 503, contentType: "application/problem+json", body: JSON.stringify({ code: "synthetic_read_failure" }) });
    }
    return route.continue();
  });
  await calendarForm(page, "Confirmacao de leitura " + crypto.randomUUID());
  await page.getByRole("button", { name: "Cadastrar calendario revisado", exact: true }).click();
  await expect(page.getByRole("button", { name: "Confirmar dados do SLA", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Confirmar dados do SLA", exact: true }).click();
  await confirmed(page); expect(posts).toBe(1); expect(failed).toBe(true);
});



test("@sla delayed configuration read cannot restart queries after identity replacement", async ({ page }) => {
  test.setTimeout(60_000);
  await login(page);
  const panel = await configuration(page);
  const path = `${root}${env("QUEUE")}/business-calendars`;
  let collections = 0;
  page.on("request", request => { if (new URL(request.url()).pathname === path && request.method() === "GET") collections++; });
  let release!: () => void, waiting!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const entered = new Promise<void>(resolve => { waiting = resolve; });
  await page.route(`**${path}`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    const response = await route.fetch();
    waiting(); await gate; await route.fulfill({ response });
  });
  try {
    await calendarForm(page, "Private identity boundary " + crypto.randomUUID());
    await page.getByRole("button", { name: "Cadastrar calendario revisado", exact: true }).click();
    await entered;
    await login(page, "AGENT");
    await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
    await expect(panel).toHaveCount(0);
    const before = collections;
    release(); await page.waitForLoadState("networkidle");
    expect(collections).toBe(before);
    await expect(page.getByText("Configuracao confirmada. Os ciclos existentes preservam suas revisoes.", { exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => Object.keys(sessionStorage))).toEqual([]);
  } finally { release(); await page.unrouteAll({ behavior: "wait" }); }
});

test("@sla parent ticket read failure owns recovery without a second SLA retry", async ({ page }) => {
  const csrf = await login(page);
  const ticket = await createTicket(page, csrf);
  await page.goto(`/service-desk/tickets/${ticket}`);
  await expect(page.getByRole("region", { name: "SLA do chamado", exact: true })).toBeVisible();
  let failed = false;
  await page.route(`**/api/v1/tickets/${ticket}`, async route => {
    failed = true;
    await route.fulfill({ status: 503, contentType: "application/problem+json", body: JSON.stringify({ code: "database_unavailable" }) });
  });
  await page.getByRole("button", { name: "Atualizar chamado", exact: true }).click();
  await expect(page.getByRole("region", { name: "SLA do chamado", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Atualizar SLA", exact: true })).toHaveCount(0);
  expect(failed).toBe(true);
  await page.unrouteAll();
});

test("@sla real TLS SMTP acceptance fulfills the visible response goal", async ({ page }) => {
  test.setTimeout(90_000);
  const repo = fileURLToPath(new URL("../../../", import.meta.url));
  const python = resolve(repo, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  execFileSync(python, ["scripts/browser_sla_fixture.py"], { cwd: repo, env: process.env, stdio: "pipe" });
  await page.context().addCookies([{ name: "__Host-altvia_session", value: process.env.ALTVIA_E2E_NOTE_AUTHOR_SESSION!, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const created = await page.request.post("/api/v1/tickets", { headers: headers(me.csrf_token, 1), data: { queue_id: process.env.ALTVIA_E2E_NOTE_QUEUE_ID, client_id: process.env.ALTVIA_E2E_TICKET_CLIENT_ID, requester_id: process.env.ALTVIA_E2E_TICKET_REQUESTER_ID, subject: "Delivery synthetic SLA " + crypto.randomUUID(), priority: "medium" } });
  expect(created.status()).toBe(201);
  const ticket = (await created.json()).ticket_id;
  expect((await page.request.post(`/api/v1/tickets/${ticket}/messages`, { headers: headers(me.csrf_token, 1), data: { body_text: "E2E-SMTP-SLA-ACCEPTED Public response" } })).status()).toBe(201);
  execFileSync(python, ["scripts/browser_delivery_fixture.py", ticket], { cwd: repo, env: process.env, stdio: "pipe" });
  await page.goto(`/service-desk/tickets/${ticket}`);
  await page.getByRole("button", { name: "Revisar envio", exact: true }).click();
  await page.getByRole("region", { name: "Revisar envio de resposta", exact: true }).getByRole("button", { name: "Confirmar envio", exact: true }).click();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/tickets/${ticket}/sla`)).json()).current.first_response.status, { timeout: 45_000 }).toBe("fulfilled");
  const outcomes = page.getByRole("region", { name: "SLA do chamado", exact: true });
  await outcomes.getByRole("button", { name: "Atualizar SLA", exact: true }).click();
  await expect(outcomes.getByText("Cumprido", { exact: true })).toBeVisible();
  await expect(outcomes).toContainText("Synthetic SMTP browser SLA");
  const conversation = page.getByRole("region", { name: "Conversa", exact: true });
  await expect(conversation.getByText("Aceito pelo servidor de e-mail", { exact: true })).toBeVisible();
  await expect(conversation.getByText("Na fila de envio", { exact: true })).toHaveCount(0);
  await capture(page, "accepted-response");
});

test("@sla invalid timezone is actionable and duplicate selectors retain the original policy", async ({ page }) => {
  const csrf = await login(page);
  await configuration(page);
  const name = "Erro corrigivel " + crypto.randomUUID();
  await calendarForm(page, name);
  await page.getByLabel("Fuso IANA do calendario", { exact: true }).fill("Etc/Unknown_Altvia_Zone");
  await page.getByRole("button", { name: "Cadastrar calendario revisado", exact: true }).click();
  await expect(page.getByRole("region", { name: "SLA e calendarios", exact: true }).getByRole("alert")).toContainText("Confira o nome IANA");
  await page.getByLabel("Fuso IANA do calendario", { exact: true }).fill("UTC");
  await page.getByRole("button", { name: "Cadastrar calendario revisado", exact: true }).click();
  await confirmed(page);
  const collection = `${root}${env("QUEUE")}/business-calendars?client_id=${env("CLIENT")}`;
  const calendar = (await (await page.request.get(collection)).json()).items.find((row: { name: string }) => row.name === name);
  await page.getByRole("button", { name: "Nova politica de SLA", exact: true }).click();
  await page.getByLabel("Nome da politica", { exact: true }).fill("Duplicata nao permitida");
  await page.getByLabel("Calendario da politica", { exact: true }).selectOption(calendar.id);
  await page.getByRole("button", { name: "Usar esta revisao do calendario", exact: true }).click();
  await page.getByLabel("Meta de primeira resposta (minutos uteis)", { exact: true }).fill("1");
  await page.getByLabel("Meta de resolucao (minutos uteis)", { exact: true }).fill("2");
  await page.getByLabel("Aproximacao do limite (minutos uteis)", { exact: true }).fill("0");
  await page.getByRole("button", { name: "Cadastrar politica desativada", exact: true }).click();
  await expect(page.getByRole("region", { name: "SLA e calendarios", exact: true }).getByRole("alert")).toContainText("Ja existe uma politica");
  await expect(page.getByLabel("Cliente do SLA", { exact: true })).toBeDisabled();
  const policies = await (await page.request.get(`${root}${env("QUEUE")}/sla-policies?client_id=${env("CLIENT")}`)).json();
  expect(policies.items).toHaveLength(1); expect(policies.items[0].name).toBe("SLA sintetico geral");
  expect(policies.items[0].enabled).toBe(true);
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(200);
  expect(csrf).toBeTruthy();
});

test("@sla concurrent queue version rejects create and requires explicit reload", async ({ page }) => {
  const csrf = await login(page);
  await configuration(page);
  let posts = 0;
  const queuePath = `${root}${env("QUEUE")}`;
  await page.route(`**${queuePath}/business-calendars`, async route => {
    if (route.request().method() !== "POST") return route.continue();
    posts++;
    const current = await (await page.request.get(queuePath)).json();
    expect((await page.request.patch(queuePath, { headers: headers(csrf, current.version), data: { name: "Alteracao concorrente de teste" } })).status()).toBe(200);
    const response = await route.fetch();
    expect(response.status()).toBe(409);
    await route.fulfill({ response });
  });
  const name = "Conflito nao gravado " + crypto.randomUUID();
  await calendarForm(page, name);
  await page.getByRole("button", { name: "Cadastrar calendario revisado", exact: true }).click();
  await expect(page.getByRole("region", { name: "SLA e calendarios", exact: true }).getByRole("alert")).toContainText("Os dados foram alterados");
  await expect(page.getByLabel("Cliente do SLA", { exact: true })).toBeDisabled();
  await page.getByRole("button", { name: /Recarregar e descartar/ }).click();
  await expect(page.getByRole("button", { name: "Novo calendario", exact: true })).toBeFocused();
  expect(posts).toBe(1);
  const list = await (await page.request.get(`${queuePath}/business-calendars?client_id=${env("CLIENT")}`)).json();
  expect(list.items.some((row: { name: string }) => row.name === name)).toBe(false);
});

test("@sla archived parents preserve deliberate policy deactivation", async ({ page }) => {
  const csrf = await login(page);
  const queuePath = `${root}${env("QUEUE")}`;
  let queue = await (await page.request.get(queuePath)).json();
  const createdCalendar = await page.request.post(`${queuePath}/business-calendars`, { headers: headers(csrf, queue.version), data: { client_id: env("CLIENT"), name: "Synthetic archive calendar", timezone: "UTC", active: true, windows: [{ weekday: 0, start_minute: 0, end_minute: 1440 }], holidays: [] } });
  expect(createdCalendar.status()).toBe(201);
  queue = await (await page.request.get(queuePath)).json();
  const createdPolicy = await page.request.post(`${queuePath}/sla-policies`, { headers: headers(csrf, queue.version), data: { client_id: env("CLIENT"), name: "Synthetic archived SLA", priority: "high", calendar_id: (await createdCalendar.json()).calendar_id, calendar_version: 1, first_response_minutes: 60, resolution_minutes: 240, approach_minutes: 0, pause_states: [] } });
  expect(createdPolicy.status()).toBe(201);
  const path = `${queuePath}/sla-policies/${(await createdPolicy.json()).policy_id}`;
  const policy = await (await page.request.get(path)).json();
  expect((await page.request.patch(path, { headers: { ...headers(csrf, policy.version), "If-Match-Queue": `"${policy.queue_version}"` }, data: { enabled: true } })).status()).toBe(200);
  queue = await (await page.request.get(queuePath)).json();
  expect((await page.request.patch(queuePath, { headers: headers(csrf, queue.version), data: { active: false } })).status()).toBe(200);
  try {
    await page.goto(`/service-desk/queues/${env("QUEUE")}`);
    const panel = page.getByRole("region", { name: "SLA e calendarios", exact: true });
    await panel.getByLabel("Cliente do SLA", { exact: true }).selectOption(env("CLIENT"));
    await expect(panel.getByRole("button", { name: "Novo calendario", exact: true })).toBeDisabled();
    const row = panel.getByRole("listitem").filter({ has: page.getByRole("heading", { name: "Synthetic archived SLA", exact: true }) });
    const disable = row.getByRole("button", { name: "Revisar desativacao do SLA", exact: true });
    await expect(disable).toBeEnabled();
    await disable.click();
    await page.getByRole("button", { name: "Confirmar desativacao do SLA", exact: true }).click();
    await expect(row.getByText("Politica desativada", { exact: true })).toBeVisible();
    expect((await (await page.request.get(path)).json()).enabled).toBe(false);
  } finally {
    queue = await (await page.request.get(queuePath)).json();
    expect((await page.request.patch(queuePath, { headers: headers(csrf, queue.version), data: { active: true } })).status()).toBe(200);
  }
});
