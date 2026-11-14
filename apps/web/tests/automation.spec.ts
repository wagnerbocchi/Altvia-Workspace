import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const origin = "https://127.0.0.1:3443";
const env = (key: string) => {
  const value = process.env["ALTVIA_E2E_AUTOMATION_" + key];
  if (!value) throw Error("Real isolated automation fixture required: " + key);
  return value;
};
async function login(page: Page, kind = "MANAGER") {
  await page.context().addCookies([{ name: "__Host-altvia_session", value: env(kind + "_SESSION"),
    url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const response = await page.request.get("/api/v1/auth/me");
  expect(response.status()).toBe(200);
  return (await response.json()).csrf_token as string;
}
async function createTicket(page: Page, csrf: string) {
  const response = await page.request.post("/api/v1/tickets", {
    headers: { Origin: origin, "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID() },
    data: { queue_id: env("QUEUE"), client_id: env("CLIENT"), requester_id: env("REQUESTER"),
      subject: "Texto privado de chamado " + crypto.randomUUID(), description: "Nao copiar esta descricao privada.",
      priority: "critical", assignee_id: env("AGENT_ID") },
  });
  expect(response.status()).toBe(201);
  return (await response.json()).ticket_id as string;
}
async function defaultProject(page: Page, csrf: string, project: string | null) {
  const path = `/api/v1/clients/${env("CLIENT")}`;
  const current = await (await page.request.get(path)).json();
  const response = await page.request.patch(path, {
    headers: { Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${current.version}"` },
    data: { default_project_id: project },
  });
  expect(response.status()).toBe(200);
}
async function enableRule(page: Page, csrf: string, enabled = true) {
  const path = `/api/v1/ticket-queues/${env("QUEUE")}/automation-rules`;
  let list = await (await page.request.get(`${path}?client_id=${env("CLIENT")}`)).json();
  if (!list.items.length) {
    const queue = await (await page.request.get(`/api/v1/ticket-queues/${env("QUEUE")}`)).json();
    const created = await page.request.post(path, {
      headers: { Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${queue.version}"`, "Idempotency-Key": crypto.randomUUID() },
      data: { client_id: env("CLIENT"), title: "Recuperacao de atribuicao", priority: "medium", ticket_statuses: ["new", "open"] },
    });
    expect(created.status()).toBe(201);
    list = await (await page.request.get(`${path}?client_id=${env("CLIENT")}`)).json();
  }
  const row = list.items[0];
  const changed = await page.request.patch(`${path}/${row.id}`, {
    headers: { Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${row.version}"`, "If-Match-Queue": `"${row.queue_version}"`, "Idempotency-Key": crypto.randomUUID() },
    data: { enabled },
  });
  expect(changed.status()).toBe(200);
}
async function capture(page: Page, label: string) {
  const root = fileURLToPath(new URL("../../../.impeccable/review/assignment-automation/", import.meta.url));
  await mkdir(root, { recursive: true });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      if (await page.locator("html").evaluate(el => el.classList.contains("dark")) !== (theme === "dark")) await page.getByRole("button", { name: "Alternar tema claro e escuro", exact: true }).click();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({ path: `${root}/${label}-${width}-${theme}.png`, fullPage: true });
    }
  }
}

test("@automation configure and execute one real scoped assignment rule", async ({ page, browser }) => {
  test.setTimeout(120_000);
  const csrf = await login(page);
  const queue = env("QUEUE");
  const title = "Tarefa automatica <b>literal</b> " + crypto.randomUUID();
  await page.goto(`/service-desk/queues/${queue}`);
  await expect(page.getByRole("heading", { name: "Automacoes de atribuicao", exact: true })).toBeVisible();
  await page.getByLabel("Cliente da automacao", { exact: true }).selectOption(env("CLIENT"));
  await page.getByLabel("Titulo da tarefa gerada", { exact: true }).fill(title);
  await page.getByLabel("Prioridade da tarefa gerada", { exact: true }).selectOption("high");
  await capture(page, "form");
  await page.getByRole("button", { name: "Cadastrar regra desativada", exact: true }).click();
  await expect(page.getByText("Regra desativada", { exact: true })).toBeVisible();
  const old = await createTicket(page, csrf);
  const empty = await page.request.get(`/api/v1/tickets/${old}/automation-executions`);
  expect((await empty.json()).items).toEqual([]);
  await page.getByRole("button", { name: "Revisar ativacao", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ativar regra?", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Confirmar ativacao", exact: true }).click();
  await expect(page.getByText("Regra ativada", { exact: true })).toBeVisible();
  await capture(page, "rule");
  const id = await createTicket(page, csrf);
  let run: { id: string; state: string; effect: { work_item_id: string } };
  await expect.poll(async () => {
    const response = await page.request.get(`/api/v1/tickets/${id}/automation-executions`);
    expect(response.status()).toBe(200);
    run = (await response.json()).items[0];
    return run?.state;
  }, { timeout: 20_000 }).toBe("succeeded");
  const workId = run!.effect.work_item_id;
  const task = await (await page.request.get(`/api/v1/work-items/${workId}`)).json();
  expect(task.title).toBe(title); expect(task.description).toBe(""); expect(task.priority).toBe("high");
  expect(task.status).toBe("todo"); expect(task.due).toBeNull(); expect(task.owner_id).toBe(env("AGENT_ID"));
  await page.goto(`/service-desk/tickets/${id}`);
  const panel = page.getByRole("region", { name: "Automacoes do chamado", exact: true });
  await expect(panel.getByText("Concluida", { exact: true })).toBeVisible();
  await expect(panel.getByRole("link", { name: "Abrir tarefa gerada", exact: true })).toHaveAttribute("href", `/work-items/${workId}`);
  await capture(page, "execution");
  await page.goto(`/work-items/${workId}`);
  await expect.poll(async () => {
    const response = await page.request.get(`/api/v1/work-items/${workId}/activity`);
    return (await response.json()).items.some((row: { actor_kind: string }) => row.actor_kind === "automation");
  }).toBe(true);
  await page.getByRole("button", { name: "Atualizar atividade", exact: true }).click();
  await expect(page.getByText("Tarefa criada por automacao", { exact: true })).toBeVisible();
  await expect(page.getByText("Automacao autorizada por:", { exact: false }).first()).toBeVisible();
  const context = await browser.newContext({ baseURL: origin, ignoreHTTPSErrors: true });
  try {
    const workOnly = await context.newPage();
    await login(workOnly, "WORK_ONLY");
    expect((await workOnly.request.get(`/api/v1/tickets/${id}`)).status()).toBe(404);
    const activity = await workOnly.request.get(`/api/v1/work-items/${workId}/activity`);
    const text = await activity.text();
    expect(text).not.toContain(id); expect(text).not.toContain(run!.id);
    expect(JSON.parse(text).items).toHaveLength(1);
    await workOnly.goto(`/work-items/${workId}`);
    await expect(workOnly.getByText("Tarefa criada por automacao", { exact: true })).toBeVisible();
    await expect(workOnly.getByText("Autor: null", { exact: true })).toHaveCount(0);
  } finally { await context.close(); }
  await page.goto(`/service-desk/queues/${queue}`);
  await page.getByLabel("Cliente da automacao", { exact: true }).selectOption(env("CLIENT"));
  await page.getByRole("button", { name: "Revisar desativacao", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar desativacao", exact: true }).click();
  await expect(page.getByText("Regra desativada", { exact: true })).toBeVisible();
});

test("@automation recovery retains its original reviewed intent after a lost receipt", async ({ page }) => {
  test.setTimeout(90_000);
  const csrf = await login(page);
  await enableRule(page, csrf);
  await defaultProject(page, csrf, null);
  const id = await createTicket(page, csrf);
  await expect.poll(async () => {
    const response = await page.request.get(`/api/v1/tickets/${id}/automation-executions`);
    return (await response.json()).items[0]?.state;
  }, { timeout: 20_000 }).toBe("triage");
  await page.goto(`/service-desk/tickets/${id}`);
  const panel = page.getByRole("region", { name: "Automacoes do chamado", exact: true });
  await expect(panel.getByText("Requer revisao", { exact: true })).toBeVisible();
  await defaultProject(page, csrf, env("PROJECT"));
  await panel.getByRole("button", { name: "Revisar nova tentativa", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Repetir esta execucao?", exact: true })).toBeFocused();
  await capture(page, "recovery");
  const requests: { key: string | undefined; version: string | undefined; body: string | null }[] = [];
  await page.route(`**/api/v1/tickets/${id}/automation-executions/*/retry`, async route => {
    const headers = route.request().headers();
    requests.push({ key: headers["idempotency-key"], version: headers["if-match"], body: route.request().postData() });
    const response = await route.fetch();
    if (requests.length === 1) { expect(response.status()).toBe(202); await route.abort("failed"); }
    else { expect(response.status()).toBe(200); await route.fulfill({ response }); }
  });
  await panel.getByRole("button", { name: "Confirmar nova tentativa", exact: true }).click();
  await panel.getByRole("button", { name: "Verificar nova tentativa", exact: true }).click();
  await expect(panel.getByText("Reagendamento registrado. Atualize para acompanhar o processamento.", { exact: true })).toBeVisible();
  expect(requests).toHaveLength(2); expect(requests[0]).toEqual(requests[1]); expect(requests[0].key).toBeTruthy();
  await page.unrouteAll();
  await expect.poll(async () => {
    const response = await page.request.get(`/api/v1/tickets/${id}/automation-executions`);
    return (await response.json()).items[0]?.state;
  }, { timeout: 20_000 }).toBe("succeeded");
  await panel.getByRole("button", { name: "Atualizar automacoes", exact: true }).click();
  await expect(panel.getByText("Concluida", { exact: true })).toBeVisible();
  const links = await (await page.request.get(`/api/v1/tickets/${id}/work-items`)).json();
  expect(links.items).toHaveLength(1);
});

test("@automation uncertain rule edit preserves both versions and a later disable", async ({ page }) => {
  test.setTimeout(60_000);
  const csrf = await login(page);
  await enableRule(page, csrf);
  const root = `/api/v1/ticket-queues/${env("QUEUE")}/automation-rules`;
  const row = (await (await page.request.get(`${root}?client_id=${env("CLIENT")}`)).json()).items[0];
  await page.goto(`/service-desk/queues/${env("QUEUE")}`);
  await page.getByLabel("Cliente da automacao", { exact: true }).selectOption(env("CLIENT"));
  await page.getByRole("button", { name: "Editar regra", exact: true }).click();
  const title = "Revisao preservada " + crypto.randomUUID();
  await page.getByLabel("Titulo da tarefa gerada", { exact: true }).fill(title);
  const requests: { key: string | undefined; rule: string | undefined; queue: string | undefined; body: string | null }[] = [];
  await page.route(`**${root}/${row.id}`, async route => {
    if (route.request().method() !== "PATCH") return route.continue();
    const headers = route.request().headers();
    requests.push({ key: headers["idempotency-key"], rule: headers["if-match"], queue: headers["if-match-queue"], body: route.request().postData() });
    const result = await route.fetch();
    expect(result.status()).toBe(200);
    if (requests.length === 1) {
      const current = await (await page.request.get(`${root}/${row.id}`)).json();
      const disabled = await page.request.patch(`${root}/${row.id}`, {
        headers: { Origin: origin, "X-CSRF-Token": csrf, "If-Match": `"${current.version}"`, "If-Match-Queue": `"${current.queue_version}"`, "Idempotency-Key": crypto.randomUUID() }, data: { enabled: false },
      });
      expect(disabled.status()).toBe(200);
      await route.abort("failed");
    } else await route.fulfill({ response: result });
  });
  await page.getByRole("button", { name: "Salvar regra revisada", exact: true }).click();
  await expect(page.getByLabel("Cliente da automacao", { exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Verificar regra", exact: true }).click();
  await expect(page.getByText("Regra desativada", { exact: true })).toBeVisible();
  await expect(page.getByText(title, { exact: true })).toBeVisible();
  await expect(page.getByLabel("Cliente da automacao", { exact: true })).toBeEnabled();
  expect(requests).toHaveLength(2); expect(requests[0]).toEqual(requests[1]);
  expect(requests[0].rule).toBe(`"${row.version}"`); expect(requests[0].queue).toBe(`"${row.queue_version}"`);
  await page.unrouteAll();
});

test("@automation delayed read cannot restart private queries after identity replacement", async ({ page }) => {
  test.setTimeout(60_000);
  const csrf = await login(page);
  await enableRule(page, csrf);
  const root = `/api/v1/ticket-queues/${env("QUEUE")}/automation-rules`;
  const row = (await (await page.request.get(`${root}?client_id=${env("CLIENT")}`)).json()).items[0];
  let collections = 0;
  page.on("request", request => { if (new URL(request.url()).pathname === root && request.method() === "GET") collections++; });
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let waiting!: () => void;
  const entered = new Promise<void>(resolve => { waiting = resolve; });
  await page.route(`**${root}/${row.id}`, async route => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    waiting(); await gate; await route.fulfill({ response });
  });
  try {
    await page.goto(`/service-desk/queues/${env("QUEUE")}`);
    await page.getByLabel("Cliente da automacao", { exact: true }).selectOption(env("CLIENT"));
    await page.getByRole("button", { name: "Revisar desativacao", exact: true }).click();
    await page.getByRole("button", { name: "Confirmar desativacao", exact: true }).click();
    await entered;
    await login(page, "AGENT");
    await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
    await expect(page.getByRole("heading", { name: "Automacoes de atribuicao", exact: true })).toHaveCount(0);
    const before = collections;
    release();
    await page.waitForLoadState("networkidle");
    expect(collections).toBe(before);
    await expect(page.getByText("Regra confirmada. Consulte o estado atual abaixo.", { exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => Object.keys(sessionStorage))).toEqual([]);
  } finally { release(); await page.unrouteAll({ behavior: "wait" }); }
});

test("@automation acknowledged write recovers a failed read without resending the mutation", async ({ page }) => {
  test.setTimeout(60_000);
  const csrf = await login(page);
  await enableRule(page, csrf);
  const root = `/api/v1/ticket-queues/${env("QUEUE")}/automation-rules`;
  const row = (await (await page.request.get(`${root}?client_id=${env("CLIENT")}`)).json()).items[0];
  await page.goto(`/service-desk/queues/${env("QUEUE")}`);
  await page.getByLabel("Cliente da automacao", { exact: true }).selectOption(env("CLIENT"));
  await page.getByRole("button", { name: "Editar regra", exact: true }).click();
  await page.getByLabel("Titulo da tarefa gerada", { exact: true }).fill("Leitura confirmada " + crypto.randomUUID());
  let patches = 0, failed = false;
  await page.route(`**${root}/${row.id}`, async route => {
    if (route.request().method() === "PATCH") {
      patches++; const response = await route.fetch(); expect(response.status()).toBe(200);
      await route.fulfill({ response }); return;
    }
    if (route.request().method() === "GET" && patches && !failed) {
      failed = true;
      await route.fulfill({ status: 503, contentType: "application/problem+json", body: JSON.stringify({ code: "database_unavailable", status: 503, title: "Synthetic read failure" }) });
      return;
    }
    await route.continue();
  });
  await page.getByRole("button", { name: "Salvar regra revisada", exact: true }).click();
  await expect(page.getByText("Operacao registrada. A confirmacao esta pendente.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Confirmar dados da regra", exact: true }).click();
  await expect(page.getByText("Regra confirmada. Consulte o estado atual abaixo.", { exact: true })).toBeVisible();
  expect(patches).toBe(1); expect(failed).toBe(true);
  await page.unrouteAll();
});

test("@automation platform configuration alone offers no customer rule form", async ({ page }) => {
  const token = process.env.ALTVIA_E2E_ADMIN_SESSION;
  if (!token) throw Error("Real isolated platform configuration session required");
  await page.context().addCookies([{ name: "__Host-altvia_session", value: token, url: origin,
    secure: true, httpOnly: true, sameSite: "Lax" }]);
  await page.goto(`/service-desk/queues/${env("QUEUE")}`);
  const panel = page.getByRole("region", { name: "Automacoes de atribuicao", exact: true });
  await expect(panel.getByText("Nenhum cliente sob sua gestao disponivel nesta pagina.", { exact: true })).toBeVisible();
  await expect(panel.getByRole("option")).toHaveCount(1);
  await expect(panel.getByLabel("Titulo da tarefa gerada", { exact: true })).toHaveCount(0);
});

for (const enabled of [true, false]) test(`@automation keyboard cancellation restores rule openers enabled=${enabled}`, async ({ page }) => {
  const csrf = await login(page);
  await enableRule(page, csrf, enabled);
  await page.goto(`/service-desk/queues/${env("QUEUE")}`);
  await page.getByLabel("Cliente da automacao", { exact: true }).selectOption(env("CLIENT"));
  const panel = page.getByRole("region", { name: "Automacoes de atribuicao", exact: true });
  const opener = panel.getByRole("button", { name: enabled ? "Revisar desativacao" : "Revisar ativacao", exact: true });
  await opener.focus(); await page.keyboard.press("Enter");
  await expect(panel.getByRole("heading", { name: enabled ? "Desativar regra?" : "Ativar regra?", exact: true })).toBeFocused();
  await panel.getByRole("button", { name: "Cancelar revisao", exact: true }).click();
  await expect(opener).toBeFocused();
  await page.keyboard.press("Tab");
  const edit = panel.getByRole("button", { name: "Editar regra", exact: true });
  await expect(edit).toBeFocused(); await page.keyboard.press("Enter");
  await expect(panel.getByLabel("Titulo da tarefa gerada", { exact: true })).toBeFocused();
  await panel.getByRole("button", { name: "Cancelar edicao", exact: true }).click();
  await expect(edit).toBeFocused(); await page.keyboard.press("Tab");
  await expect(page.getByLabel("Cliente do SLA", { exact: true })).toBeFocused();
});

test("@automation adopts existing in-progress work without changing its executor or lifecycle", async ({ page }) => {
  test.setTimeout(60_000);
  const csrf = await login(page);
  await enableRule(page, csrf);
  const manager = await (await page.request.get("/api/v1/auth/me")).json();
  const headers = { Origin: origin, "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID() };
  const source = await page.request.post("/api/v1/tickets", { headers, data: {
    queue_id: env("QUEUE"), client_id: env("CLIENT"), requester_id: env("REQUESTER"),
    subject: "Adocao de trabalho " + crypto.randomUUID(), priority: "critical",
  } });
  expect(source.status()).toBe(201);
  const id = (await source.json()).ticket_id as string;
  const manual = await page.request.post("/api/v1/work-items", { headers: { ...headers, "Idempotency-Key": crypto.randomUUID() }, data: {
    project_id: env("PROJECT"), title: "Trabalho manual preservado " + crypto.randomUUID(),
    description: "Contexto manual independente.", work_type: "one_off", priority: "low", owner_id: manager.id,
  } });
  expect(manual.status()).toBe(201);
  const workId = (await manual.json()).work_item_id as string;
  const transition = await page.request.post(`/api/v1/work-items/${workId}/transitions`, { headers: {
    ...headers, "Idempotency-Key": crypto.randomUUID(), "If-Match": '"1"',
  }, data: { target_status: "in_progress" } });
  expect(transition.status()).toBe(200);
  const linked = await page.request.post(`/api/v1/tickets/${id}/work-items`, { headers: {
    ...headers, "Idempotency-Key": crypto.randomUUID(), "If-Match": '"1"', "If-Match-Work-Item": '"2"',
  }, data: { work_item_id: workId } });
  expect(linked.status()).toBe(201);
  const before = await (await page.request.get(`/api/v1/work-items/${workId}`)).json();
  const collection = `/api/v1/work-items?project_id=${env("PROJECT")}&limit=100`;
  const count = (await (await page.request.get(collection)).json()).items.length;
  const assigned = await page.request.patch(`/api/v1/tickets/${id}`, { headers: { ...headers, "If-Match": '"2"' }, data: { assignee_id: env("AGENT_ID") } });
  expect(assigned.status()).toBe(200);
  await expect.poll(async () => {
    const runs = await (await page.request.get(`/api/v1/tickets/${id}/automation-executions`)).json();
    return runs.items[0]?.state;
  }, { timeout: 20_000 }).toBe("succeeded");
  const run = (await (await page.request.get(`/api/v1/tickets/${id}/automation-executions`)).json()).items[0];
  expect(run.effect).toEqual({ work_item_id: workId, project_id: env("PROJECT"), mode: "adopted" });
  expect(await (await page.request.get(`/api/v1/work-items/${workId}`)).json()).toEqual(before);
  const after = await (await page.request.get(collection)).json();
  expect(after.items).toHaveLength(count); expect(after.next_cursor).toBeNull();
  await page.goto(`/service-desk/tickets/${id}`);
  const panel = page.getByRole("region", { name: "Automacoes do chamado", exact: true });
  await expect(panel.getByRole("link", { name: "Abrir tarefa existente", exact: true })).toHaveAttribute("href", `/work-items/${workId}`);
  await panel.getByRole("link", { name: "Abrir tarefa existente", exact: true }).click();
  await expect(page.getByRole("heading", { name: before.title, exact: true })).toBeVisible();
  await expect(page.getByText("Tarefa criada por automacao", { exact: true })).toHaveCount(0);
});
