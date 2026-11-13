import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { loginWork } from "./work-session";

const project = process.env.ALTVIA_E2E_WORK_PROJECT_ID!;
const origin = "https://127.0.0.1:3443";
const shots = fileURLToPath(new URL("../../../.impeccable/review/work-items/", import.meta.url));
async function login(page: Page, kind = "MANAGER") {
  return loginWork(page, kind);
}
async function headers(page: Page, version = 1) {
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  return { Origin: origin, "X-CSRF-Token": me.csrf_token, "Idempotency-Key": crypto.randomUUID(), "If-Match": `"${version}"` };
}
async function capture(page: Page, prefix: string) {
  await mkdir(shots, { recursive: true });
  await expect(page.getByRole("status").filter({hasText:/^Carregando/})).toHaveCount(0);
  const measurements=[];
  for (const [device, width] of [["desktop",1440],["mobile",390]] as const) {
    await page.setViewportSize({width,height:1000});
    for (const theme of ["light","dark"]) {
      await page.evaluate(value=>document.documentElement.classList.toggle("dark",value==="dark"),theme);
      await page.evaluate(()=>scrollTo(0,0));
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()).violations).toEqual([]);
      measurements.push(await page.evaluate(()=>Object.fromEntries(["main", ".admin-workspace", ".admin-plane", ".admin-section", "h1"].map(selector=>{const el=document.querySelector(selector)!; const css=getComputedStyle(el); return [selector,{width:el.getBoundingClientRect().width,display:css.display,padding:css.padding,fontSize:css.fontSize,className:el.className}];}))));
      await page.screenshot({path:`${shots}/${prefix}-${device}-${theme}.png`,fullPage:true});
    }
  }
  await writeFile(`${shots}/${prefix}-layout.json`,JSON.stringify(measurements,null,2));
}
async function stateCapture(page: Page, name: string) {
  await expect(page.getByRole("status").filter({hasText:/^Carregando/})).toHaveCount(0);
  await mkdir(shots,{recursive:true});await page.setViewportSize({width:390,height:1000});
  await page.evaluate(()=>{document.documentElement.classList.remove("dark");scrollTo(0,0);});
  await page.screenshot({path:`${shots}/${name}-mobile-light.png`,fullPage:true});
}

test("@work real task/subtask/deadline/state/comments persist", async ({page})=>{
  await login(page);
  await page.goto(`/projects/${project}`);
  await page.getByRole("link",{name:"Tarefas do projeto",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Tarefas",exact:true})).toBeVisible();
  await page.getByLabel("Título da nova tarefa",{exact:true}).fill("Preparar entrega persistida");
  await page.getByLabel("Responsável",{exact:true}).selectOption({label:"Gestor de tarefas"});
  await page.getByLabel("Prazo",{exact:true}).selectOption("date");
  await page.getByLabel("Data limite",{exact:true}).fill("2026-11-20");
  await page.getByRole("button",{name:"Criar tarefa",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Preparar entrega persistida",exact:true})).toBeVisible();
  const path = new URL(page.url()).pathname;
  await page.getByRole("button",{name:"Editar tarefa",exact:true}).click();
  await page.getByLabel("Descrição",{exact:true}).fill("Evidência <script>sem HTML executável</script>");
  await page.getByRole("button",{name:"Salvar tarefa",exact:true}).click();
  await expect(page.getByText("Evidência <script>sem HTML executável</script>",{exact:true})).toBeVisible();
  await page.getByLabel("Próximo estado",{exact:true}).selectOption("in_progress");
  await page.getByRole("button",{name:"Alterar estado",exact:true}).click();
  await expect(page.locator(".admin-intro")).toContainText("Em andamento");
  await page.getByLabel("Próximo estado",{exact:true}).selectOption("blocked");
  await page.getByLabel("Motivo",{exact:true}).fill("Aguardando terceiro autorizado");
  await page.getByRole("button",{name:"Alterar estado",exact:true}).click();
  await expect(page.getByText("Aguardando terceiro autorizado",{exact:true}).first()).toBeVisible();
  await page.getByLabel("Comentário interno",{exact:true}).fill("Contato registrado sem envio externo.");
  await page.getByRole("button",{name:"Registrar comentário",exact:true}).click();
  await expect(page.getByText("Contato registrado sem envio externo.",{exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByText("Contato registrado sem envio externo.",{exact:true})).toBeVisible();
  await capture(page,"detail");
  await page.getByRole("link",{name:"Voltar às tarefas",exact:true}).click();
  await page.getByLabel("Título da nova tarefa",{exact:true}).fill("Subtarefa real");
  const parentPicker = page.getByLabel("Tarefa principal",{exact:true});
  const parentPages = page.getByRole("navigation",{name:"Páginas de tarefa principal",exact:true});
  let parentPage = 1;
  while (await parentPicker.getByRole("option",{name:"Preparar entrega persistida",exact:true}).count() === 0) {
    await expect(parentPages.getByRole("button",{name:"Próximas tarefas",exact:true})).toBeEnabled();
    await parentPages.getByRole("button",{name:"Próximas tarefas",exact:true}).click();
    await expect(parentPages).toContainText(`Página ${++parentPage}`);
  }
  await page.getByLabel("Tarefa principal",{exact:true}).selectOption({label:"Preparar entrega persistida"});
  await page.getByRole("button",{name:"Criar tarefa",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Subtarefa real",exact:true})).toBeVisible();
  await expect(page.getByRole("link",{name:"Preparar entrega persistida",exact:true})).toBeVisible();
  await page.goto(path);
  await expect(page.locator(".admin-intro")).toContainText("Bloqueada");
  await page.getByRole("link",{name:"Voltar às tarefas",exact:true}).click();
  await expect(page.getByLabel("Responsável",{exact:true}).locator("option")).not.toHaveCount(1);
  await capture(page,"directory");
});

test("@work uncertain comment and version conflict retain original intent",async({page})=>{
  await login(page);
  const response=await page.request.post("/api/v1/work-items",{data:{project_id:project,title:"Conflito e comentário",priority:"medium",work_type:"one_off"},headers:await headers(page)});
  expect(response.status()).toBe(201);
  const id=(await response.json()).work_item_id;
  await page.goto(`/work-items/${id}`);
  const intents:{key?:string,body:string|null}[]=[];
  let first=true;
  await page.route(`**/api/v1/work-items/${id}/comments`,async route=>{
    if(route.request().method()!=="POST")return route.continue();
    intents.push({key:route.request().headers()["idempotency-key"],body:route.request().postData()});
    const saved=await route.fetch();expect(saved.status()).toBe(first?201:200);
    if(first){first=false;await route.abort();}else await route.fulfill({response:saved});
  });
  await page.getByLabel("Comentário interno",{exact:true}).fill("Efeito único");
  await page.getByRole("button",{name:"Registrar comentário",exact:true}).click();
  await expect(page.getByRole("button",{name:"Verificar comentário",exact:true})).toBeVisible();
  await stateCapture(page,"uncertain");
  await page.getByRole("button",{name:"Verificar comentário",exact:true}).click();
  // A list refresh can reveal committed history while protected replay is still
  // pending. Only the acknowledged write may clear the retained composer.
  await expect(page.getByLabel("Comentário interno",{exact:true})).toHaveValue("");
  await expect(page.getByRole("list",{name:"Comentários internos",exact:true}).getByText("Efeito único",{exact:true})).toBeVisible();
  expect(intents).toHaveLength(2);expect(intents[1]).toEqual(intents[0]);
  const transitions:{key?:string,version?:string,body:string|null}[]=[];
  let lostTransition=true;
  await page.route(`**/api/v1/work-items/${id}/transitions`,async route=>{
    transitions.push({key:route.request().headers()["idempotency-key"],version:route.request().headers()["if-match"],body:route.request().postData()});
    const saved=await route.fetch();expect(saved.status()).toBe(200);
    if(lostTransition){lostTransition=false;await route.abort();}else await route.fulfill({response:saved});
  });
  await page.getByLabel("Próximo estado",{exact:true}).selectOption("in_progress");
  await page.getByRole("button",{name:"Alterar estado",exact:true}).click();
  await expect(page.getByRole("button",{name:"Verificar mudança de estado",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Verificar mudança de estado",exact:true}).click();
  await expect(page.locator(".admin-intro")).toContainText("Em andamento");
  expect(transitions).toHaveLength(2);expect(transitions[1]).toEqual(transitions[0]);
  await page.getByRole("button",{name:"Editar tarefa",exact:true}).click();
  await page.getByLabel("Título",{exact:true}).fill("Edição local");
  const current=await (await page.request.get(`/api/v1/work-items/${id}`)).json();
  expect((await page.request.patch(`/api/v1/work-items/${id}`,{data:{title:"Outra sessão"},headers:await headers(page,current.version)})).status()).toBe(200);
  await page.getByRole("button",{name:"Salvar tarefa",exact:true}).click();
  await expect(page.getByRole("alert").filter({hasText:"Os dados foram alterados em outra sessão"})).toBeVisible();
  await expect(page.getByLabel("Título",{exact:true})).toHaveValue("Edição local");
  await expect(page.getByRole("button",{name:"Salvar tarefa",exact:true})).toBeDisabled();
  await stateCapture(page,"conflict");
  await page.getByRole("button",{name:"Recarregar e descartar edição",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Outra sessão",exact:true})).toBeVisible();
});

test("@work reader stays readonly and agent creates own work",async({page})=>{
  await login(page,"READER");await page.goto(`/projects/${project}/work`);
  await expect(page.getByRole("heading",{name:"Tarefas",exact:true})).toBeVisible();
  await expect(page.locator(".admin-intro")).toContainText("Projeto de tarefas");
  await expect(page.getByRole("status").filter({hasText:/^Carregando/})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Criar tarefa",exact:true})).toHaveCount(0);
  await stateCapture(page,"reader");
  await login(page,"AGENT");await page.reload();
  await page.getByLabel("Título da nova tarefa",{exact:true}).fill("Execução do agente");
  await page.getByRole("button",{name:"Criar tarefa",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Execução do agente",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Editar tarefa",exact:true}).click();
  await expect(page.getByLabel("Responsável",{exact:true})).toHaveCount(0);
  await page.getByLabel("Título",{exact:true}).fill("Execução própria revisada");
  await page.getByRole("button",{name:"Salvar tarefa",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Execução própria revisada",exact:true})).toBeVisible();
});

test("@work uncertain creation survives independent directory pagination", async ({page})=>{
  await login(page);
  for(let n=0;n<11;n++){
    expect((await page.request.post("/api/v1/work-items",{data:{project_id:project,title:`Página ${n}`,priority:"low",work_type:"one_off"},headers:await headers(page)})).status()).toBe(201);
  }
  await page.goto(`/projects/${project}/work`);
  await page.getByLabel("Título da nova tarefa",{exact:true}).fill("Criação com resposta perdida");
  const intents:{key?:string,body:string|null}[]=[];let first=true;
  await page.route("**/api/v1/work-items",async route=>{
    if(route.request().method()!=="POST")return route.continue();
    intents.push({key:route.request().headers()["idempotency-key"],body:route.request().postData()});
    const response=await route.fetch();expect(response.status()).toBe(first?201:200);
    if(first){first=false;await route.abort();}else await route.fulfill({response});
  });
  await page.getByRole("button",{name:"Criar tarefa",exact:true}).click();
  await expect(page.getByRole("button",{name:"Verificar criação",exact:true})).toBeVisible();
  const directory=page.getByRole("region",{name:"Tarefas do projeto",exact:true});
  await directory.getByRole("button",{name:"Próximas tarefas",exact:true}).click();
  await expect(page.getByRole("button",{name:"Verificar criação",exact:true})).toBeVisible();
  await expect(page.getByLabel("Título da nova tarefa",{exact:true})).toBeDisabled();
  await page.getByRole("button",{name:"Verificar criação",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Criação com resposta perdida",exact:true})).toBeVisible();
  expect(intents).toHaveLength(2);expect(intents[1]).toEqual(intents[0]);
});
