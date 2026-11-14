import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const origin = "https://127.0.0.1:3443";
const clientId = process.env.ALTVIA_E2E_CONTACT_CLIENT_ID!;
const path = `/clients/${clientId}`;
const shots = fileURLToPath(new URL("../../../.impeccable/review/contacts/", import.meta.url));
async function login(page: Page, kind = "MANAGER") {
  const token = process.env[`ALTVIA_E2E_CONTACT_${kind}_SESSION`];
  if (!token) throw Error("Guarded contact session fixture required");
  await page.context().addCookies([{ name: "__Host-altvia_session", value: token, url: origin, secure: true, httpOnly: true, sameSite: "Lax" }]);
  const response = await page.request.get("/api/v1/auth/me");
  expect(response.status()).toBe(200);
  return (await response.json()).csrf_token as string;
}
const headers = (csrf: string, version?: number) => ({ Origin: origin, "X-CSRF-Token": csrf, "Idempotency-Key": crypto.randomUUID(), ...(version ? { "If-Match": `"${version}"` } : {}) });
async function capture(page: Page, name: string) {
  await mkdir(shots, { recursive: true });
  for (const [size, width] of [["desktop", 1440], ["mobile", 390]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      await page.evaluate(value => { document.documentElement.classList.toggle("dark", value === "dark"); scrollTo(0, 0); }, theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: `${shots}/${name}-${size}-${theme}.png`, fullPage: true });
    }
  }
}

test("@contacts real contact lifecycle and explicit same-client default persist", async ({ page }) => {
  await login(page);
  await page.goto(path);
  await expect(page.getByRole("link", { name: "Contatos do cliente", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Contatos do cliente", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Contatos", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Novo contato", exact: true }).click();
  const name = `Pessoa externa ${crypto.randomUUID().slice(0, 8)}`;
  const email = `person-${crypto.randomUUID()}@example.test`;
  await page.getByLabel("Nome do contato", { exact: true }).fill(name);
  await page.getByLabel("E-mail do contato", { exact: true }).fill(email.toUpperCase());
  await page.getByRole("button", { name: "Cadastrar contato", exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  const detailPath = new URL(page.url()).pathname;
  await expect(page.getByText(email, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Editar contato", exact: true }).click();
  await page.getByLabel("Nome do contato", { exact: true }).fill(name + " revisada");
  await page.getByRole("button", { name: "Salvar contato", exact: true }).click();
  await expect(page.getByRole("heading", { name: name + " revisada", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Arquivar contato", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Arquivar este contato?", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "Confirmar arquivamento", exact: true }).click();
  await expect(page.getByText("Contato arquivado", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Restaurar contato", exact: true }).click();
  await expect(page.getByText("Contato ativo", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Contato ativo", { exact: true })).toBeVisible();
  await capture(page, "detail");
  await page.getByRole("link", { name: "Voltar aos contatos", exact: true }).click();
  await expect(page.getByRole("link", { name: name + " revisada", exact: true })).toBeVisible();
  await capture(page, "directory");
  await page.getByRole("link", { name: "Voltar ao cliente", exact: true }).click();
  await page.getByRole("button", { name: "Alterar projeto padrao", exact: true }).click();
  const projects = (await (await page.request.get(`/api/v1/projects?client_id=${clientId}&limit=100`)).json()).items;
  const wanted = projects.at(-1);
  const select = page.getByRole("combobox", { name: "Projeto padrao", exact: true });
  for (let n = 0; n < 3 && !await select.locator(`option[value="${wanted.id}"]`).count(); n++) {
    await page.getByRole("navigation", { name: "Páginas de projetos" }).getByRole("button", { name: "Próximos projetos", exact: true }).click();
    await expect(page.getByText("Carregando projetos...", { exact: true })).toBeHidden();
  }
  await select.selectOption(wanted.id);
  await page.getByRole("button", { name: "Salvar projeto padrao", exact: true }).click();
  await expect(page.getByRole("link", { name: wanted.name, exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("link", { name: wanted.name, exact: true })).toBeVisible();
  await capture(page, "default-project");
  await page.getByRole("button", { name: "Limpar projeto padrao", exact: true }).click();
  await expect(page.getByText("Nenhum projeto padrao definido.", { exact: true })).toBeVisible();
  expect((await (await page.request.get(`/api/v1${path}`)).json()).default_project_id).toBeNull();
  await page.goto(detailPath);
  await expect(page.getByRole("heading", { name: name + " revisada", exact: true })).toBeVisible();
});

test("@contacts lost create reply retains original body and key through refresh", async ({ page }) => {
  await login(page);
  await page.goto(`${path}/contacts`);
  await page.getByRole("button", { name: "Novo contato", exact: true }).click();
  await page.getByLabel("Nome do contato", { exact: true }).fill("Cadastro incerto");
  const email = `uncertain-${crypto.randomUUID()}@example.test`;
  await page.getByLabel("E-mail do contato", { exact: true }).fill(email);
  await expect(page.getByLabel("Nome do contato", { exact: true })).toHaveValue("Cadastro incerto");
  await expect(page.getByLabel("E-mail do contato", { exact: true })).toHaveValue(email);
  const attempts: { key?: string; body: string | null }[] = [];
  await page.route(`**/api/v1${path}/contacts`, async route => {
    if (route.request().method() !== "POST") { await route.continue(); return; }
    attempts.push({ key: route.request().headers()["idempotency-key"], body: route.request().postData() });
    const response = await route.fetch();
    if (attempts.length === 1) await route.abort(); else await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Cadastrar contato", exact: true }).click();
  await expect(page.getByRole("button", { name: "Verificar cadastro do contato", exact: true })).toBeVisible();
  await expect(page.getByLabel("E-mail do contato", { exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Atualizar contatos", exact: true }).click();
  await page.getByRole("button", { name: "Verificar cadastro do contato", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Cadastro incerto", exact: true })).toBeVisible();
  expect(attempts).toHaveLength(2);
  expect(attempts[0]).toEqual(attempts[1]);
  expect((await (await page.request.get(`/api/v1${path}/contacts?limit=100`)).json()).items.filter((item: { email_normalized: string }) => item.email_normalized === email)).toHaveLength(1);
});

test("@contacts opening contact fields focuses immediately without a pending timer stealing typed email", async ({ page }) => {
  await login(page);
  await page.goto(`${path}/contacts`);
  const trigger = page.getByRole("button", { name: "Novo contato", exact: true });
  await trigger.focus();
  const now = new Date();
  await page.clock.install({ time: now });
  await page.clock.pauseAt(now);
  await page.keyboard.press("Enter");
  const name = page.getByLabel("Nome do contato", { exact: true });
  const email = page.getByLabel("E-mail do contato", { exact: true });
  await expect(name).toBeFocused();
  await page.keyboard.type("Foco preservado");
  await page.keyboard.press("Tab");
  await expect(email).toBeFocused();
  await page.clock.runFor(1);
  await expect(email).toBeFocused();
  await page.keyboard.type("focus@example.test");
  await expect(name).toHaveValue("Foco preservado");
  await expect(email).toHaveValue("focus@example.test");
  await page.clock.resume();
});

test("@contacts stale contact and default edits require deliberate reload", async ({ page }) => {
  const csrf = await login(page);
  const receipt = await page.request.post(`/api/v1${path}/contacts`, { data: { display_name: "Conflito controlado", email: `conflict-${crypto.randomUUID()}@example.test` }, headers: headers(csrf) });
  expect(receipt.status()).toBe(201);
  const contactPath = `${path}/contacts/${(await receipt.json()).contact_id}`;
  await page.goto(contactPath);
  await page.getByRole("button", { name: "Editar contato", exact: true }).click();
  await page.getByLabel("Nome do contato", { exact: true }).fill("Edicao antiga");
  expect((await page.request.patch(`/api/v1${contactPath}`, { data: { display_name: "Edicao concorrente" }, headers: headers(csrf, 1) })).status()).toBe(200);
  await page.getByRole("button", { name: "Salvar contato", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Recarregue" })).toBeVisible();
  await page.getByRole("button", { name: "Recarregar e descartar edicao", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Edicao concorrente", exact: true })).toBeVisible();
  await page.goto(path);
  await page.getByRole("button", { name: "Alterar projeto padrao", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Projeto padrao", exact: true }).locator("option")).not.toHaveCount(1);
  const option = page.getByRole("combobox", { name: "Projeto padrao", exact: true }).locator("option").nth(1);
  await page.getByRole("combobox", { name: "Projeto padrao", exact: true }).selectOption((await option.getAttribute("value"))!);
  expect((await page.request.post(`/api/v1${path}/contacts`, { data: { display_name: "Avanca versao", email: `version-${crypto.randomUUID()}@example.test` }, headers: headers(csrf) })).status()).toBe(201);
  await page.getByRole("button", { name: "Salvar projeto padrao", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Recarregue" })).toBeVisible();
  expect((await (await page.request.get(`/api/v1${path}`)).json()).default_project_id).toBeNull();
});

test("@contacts viewer reads and hidden account cannot see customer contacts", async ({ page }) => {
  await login(page, "VIEWER");
  await page.goto(`${path}/contacts`);
  await expect(page.getByRole("heading", { name: "Contatos", exact: true })).toBeVisible();
  await expect(page.getByText("Acesso somente para consulta.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Novo contato", exact: true })).toHaveCount(0);
  await capture(page, "readonly");
  await page.context().clearCookies();
  await login(page, "HIDDEN");
  await page.goto(`${path}/contacts`);
  await expect(page.getByText("Este cliente nao esta disponivel para sua conta.", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Pessoa externa/ })).toHaveCount(0);
});

test("@contacts @contact-review contact detail identifies the owning client", async ({ page }) => {
  const csrf = await login(page);
  const created = await page.request.post(`/api/v1${path}/contacts`, { data: { display_name: "Contexto do cliente", email: `context-${crypto.randomUUID()}@example.test` }, headers: headers(csrf) });
  expect(created.status()).toBe(201);
  await page.goto(`${path}/contacts/${(await created.json()).contact_id}`);
  await expect(page.getByRole("heading", { name: "Contexto do cliente", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Cliente de contatos - Validacao", exact: true })).toBeVisible();
});

test("@contacts @contact-review default editor opening and cancellation preserve keyboard focus", async ({ page }) => {
  await login(page);
  await page.goto(path);
  const trigger = page.getByRole("button", { name: "Alterar projeto padrao", exact: true });
  for (const width of [1440, 390]) for (const theme of ["light", "dark"]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(value => document.documentElement.classList.toggle("dark", value === "dark"), theme);
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("combobox", { name: "Projeto padrao", exact: true })).toBeFocused();
    await mkdir(shots, { recursive: true });
    await page.screenshot({ path: `${shots}/default-editor-${width}-${theme}.png`, fullPage: true });
    await page.getByRole("button", { name: "Cancelar selecao", exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(trigger).toBeFocused();
  }
});

test("@contacts @contact-source supported dot-atom mailboxes can be created in browser", async ({ page }) => {
  await login(page);
  for (const local of ["a/b", "a!b"]) {
    await page.goto(`${path}/contacts`);
    await page.getByRole("button", { name: "Novo contato", exact: true }).click();
    const name = `Mailbox ${local}`;
    const email = `${local}-${crypto.randomUUID()}@example.test`;
    await page.getByLabel("Nome do contato", { exact: true }).fill(name);
    await page.getByLabel("E-mail do contato", { exact: true }).fill(email);
    await page.getByRole("button", { name: "Cadastrar contato", exact: true }).click();
    await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
    await expect(page.getByText(email, { exact: true })).toBeVisible();
  }
});

test("@contacts @contact-source API-supported mailbox remains editable without email change", async ({ page }) => {
  const csrf = await login(page);
  for (const local of ["a/b", "a!b"]) {
    const email = `${local}-${crypto.randomUUID()}@example.test`;
    const created = await page.request.post(`/api/v1${path}/contacts`, { data: { display_name: "Mailbox existente", email }, headers: headers(csrf) });
    expect(created.status()).toBe(201);
    await page.goto(`${path}/contacts/${(await created.json()).contact_id}`);
    await page.getByRole("button", { name: "Editar contato", exact: true }).click();
    await page.getByLabel("Nome do contato", { exact: true }).fill("Mailbox revisada");
    await page.getByRole("button", { name: "Salvar contato", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Mailbox revisada", exact: true })).toBeVisible();
    await expect(page.getByText(email, { exact: true })).toBeVisible();
  }
});
