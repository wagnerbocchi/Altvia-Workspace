"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging, useTeamWrite } from "@/components/team-admin/common";
import { WriteRecovery } from "@/components/work-items/recovery";
import type { WorkspaceSession } from "@/components/workspace-session";
import { createAutomationApi, type AssignmentRule, type RuleCreate, type RulePatch } from "@/lib/automation";
import { createClientApi, type ClientRecord } from "@/lib/clients";
import { createQueueApi, type QueueRecord } from "@/lib/ticket-queues";
import { ApiError } from "@/lib/http";
import { workPriorities } from "@/lib/work-items";
import { ticketStatuses } from "@/lib/tickets";

const states = ["new", "open", "pending_customer", "pending_third_party", "resolved"] as const;
const fields = z.object({ title: z.string().trim().min(1, "Informe o titulo da tarefa.").max(300),
  priority: z.enum(["low", "medium", "high", "critical"]),
  ticket_statuses: z.array(z.enum(states)).min(1, "Selecione ao menos um estado.") });
type Fields = z.infer<typeof fields>;
type Intent = { kind: "create"; body: RuleCreate; queueVersion: number; key: string }
  | { kind: "patch"; id: string; body: RulePatch; ruleVersion: number; queueVersion: number; key: string };

function RuleForm({ initial, disabled, submit, cancel }: { initial?: AssignmentRule; disabled: boolean;
  submit: (body: Fields) => void; cancel?: () => void }) {
  const form = useForm<Fields>({ resolver: zodResolver(fields), defaultValues: initial ? {
    title: initial.title, priority: initial.priority, ticket_statuses: initial.ticket_statuses,
  } : { title: "", priority: "medium", ticket_statuses: ["new", "open"] } });
  return <form className="team-form" noValidate onSubmit={form.handleSubmit(submit)}>
    <div className="field"><label htmlFor="automation-title">Titulo da tarefa gerada</label><input id="automation-title" maxLength={300} disabled={disabled} {...form.register("title")} aria-invalid={!!form.formState.errors.title} aria-describedby="automation-title-error" /><p id="automation-title-error" className="field-error">{form.formState.errors.title?.message}</p></div>
    <div className="field"><label htmlFor="automation-priority">Prioridade da tarefa gerada</label><select id="automation-priority" disabled={disabled} {...form.register("priority")}>{Object.entries(workPriorities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
    <fieldset className="work-fields" disabled={disabled}><legend>Executar quando o chamado estiver em</legend>{states.map(value => <label className="work-checkbox" key={value}><input type="checkbox" value={value} {...form.register("ticket_statuses")} />{ticketStatuses[value]}</label>)}{form.formState.errors.ticket_statuses && <p role="alert" className="field-error">{form.formState.errors.ticket_statuses.message}</p>}</fieldset>
    <div className="action-row"><Button type="submit" disabled={disabled}>{initial ? "Salvar regra revisada" : "Cadastrar regra desativada"}</Button>{cancel && <Button type="button" variant="outline" disabled={disabled} onClick={cancel}>Cancelar edicao</Button>}</div>
  </form>;
}

function RuleScope({ queue, client, session, onBusyChange }: { queue: QueueRecord; client: ClientRecord; session: WorkspaceSession; onBusyChange: (busy: boolean) => void }) {
  const api = createAutomationApi(session.user.csrf_token, session.onAuthError);
  const queues = createQueueApi(session.user.csrf_token, session.onAuthError);
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ["automation-rules", queue.id, client.id], queryFn: ({ signal }) => api.rules(queue.id, client.id, null, signal) });
  const denied = query.error instanceof ApiError && [403, 404].includes(query.error.status);
  const rule = denied ? undefined : query.data?.items[0];
  const [editor, setEditor] = useState<AssignmentRule | null>(null);
  const [review, setReview] = useState<AssignmentRule | null>(null);
  const reviewOpener = useRef<HTMLButtonElement | null>(null);
  const editOpener = useRef<HTMLButtonElement | null>(null);
  const [notice, setNotice] = useState("");
  const receipt = useRef<{ key: string; ruleId: string } | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const preparing = useRef(false);
  const [preparingRead, setPreparingRead] = useState(false);
  const refresh = async () => {
    if (!session.isCurrent()) return;
    await cache.cancelQueries({ queryKey: ["automation-rules", queue.id, client.id] });
    if (!session.isCurrent()) return;
    const fresh = await query.refetch({ throwOnError: true });
    if (!session.isCurrent()) return fresh;
    await cache.invalidateQueries({ queryKey: ["ticket-queue", queue.id] });
    return fresh;
  };
  const write = useTeamWrite(session, async (intent: Intent) => {
    if (!session.isCurrent()) return;
    if (!receipt.current) {
      const result = intent.kind === "create" ? await api.create(queue.id, intent.body, intent.queueVersion, intent.key)
        : await api.patch(queue.id, intent.id, intent.body, intent.ruleVersion, intent.queueVersion, intent.key);
      if (!session.isCurrent()) return;
      if (result.queue_id !== queue.id || result.client_id !== client.id || (intent.kind === "patch" && result.rule_id !== intent.id)) throw Error("Rule scope not confirmed");
      receipt.current = { key: intent.key, ruleId: result.rule_id }; setAcknowledged(true);
    }
    if (receipt.current.key !== intent.key) throw Error("Original rule intent required");
    await api.rule(queue.id, receipt.current.ruleId);
    if (!session.isCurrent()) return;
    await refresh();
  }, () => {
    receipt.current = null; setAcknowledged(false); setEditor(null); setReview(null);
    setNotice("Regra confirmada. Consulte o estado atual abaixo.");
    requestAnimationFrame(() => { if (session.isCurrent()) document.getElementById("automation-scope-heading")?.focus(); });
  });
  const active = queue.active && queue.team_active && client.active;
  useEffect(() => {
    if (session.isCurrent() && (review || editor)) document.getElementById(editor ? "automation-title" : "automation-review-heading")?.focus();
  }, [review, editor, session]);
  useEffect(() => { onBusyChange(write.locked || preparingRead); return () => onBusyChange(false); }, [onBusyChange, write.locked, preparingRead]);
  const locked = write.locked || preparingRead || query.isFetching || query.isError;
  const patch = (snapshot: AssignmentRule, body: RulePatch) => write.submit({ kind: "patch", id: snapshot.id, body,
    ruleVersion: snapshot.version, queueVersion: snapshot.queue_version, key: crypto.randomUUID() });
  return <div>
    <h3 id="automation-scope-heading" className="work-subheading" tabIndex={-1}>{denied ? "Configuracao indisponivel" : client.name}</h3>
    <p className="field-help">Atribuir um chamado pode criar uma tarefa no projeto padrao atual do cliente, com o mesmo responsavel. Textos privados, estados e prazos nao sao copiados.</p>
    <Button variant="outline" disabled={write.locked || query.isFetching} onClick={() => void refresh().catch(() => { /* Read state owns recovery. */ })}>Atualizar regra</Button>
    {query.isPending && <LoadingRows label="Carregando regra..." />}
    {query.isError && <ReadError retry={() => void refresh().catch(() => { /* Read state owns recovery. */ })}>{denied ? "A configuracao desta fila e cliente nao esta disponivel para sua conta." : undefined}</ReadError>}
    {!denied && rule && <>
      <p><span className="record-status" data-state={rule.enabled ? "active" : "inactive"}>{rule.enabled ? "Regra ativada" : "Regra desativada"}</span></p>
      <dl className="account-details work-facts"><div><dt>Tarefa gerada</dt><dd>{rule.title}</dd></div><div><dt>Prioridade</dt><dd>{workPriorities[rule.priority]}</dd></div><div><dt>Estados elegiveis</dt><dd>{rule.ticket_statuses.map(value => ticketStatuses[value]).join(", ")}</dd></div></dl>
      <div className="action-row add-member-action"><Button disabled={locked || (!rule.enabled && !active)} onClick={event => { reviewOpener.current = event.currentTarget; setEditor(null); setReview(rule); }}>{rule.enabled ? "Revisar desativacao" : "Revisar ativacao"}</Button><Button variant="outline" disabled={locked || !active} onClick={event => { editOpener.current = event.currentTarget; setReview(null); setEditor(rule); }}>Editar regra</Button></div>
      {review && <section className="confirmation" aria-labelledby="automation-review-heading"><h4 id="automation-review-heading" tabIndex={-1}>{review.enabled ? "Desativar regra?" : "Ativar regra?"}</h4><p>{review.enabled ? "Execucoes antigas ainda sem efeito serao canceladas, mesmo se a regra for reativada. Tarefas existentes permanecem." : "Novas atribuicoes elegiveis poderao criar ou vincular uma tarefa. Atribuicoes anteriores nao serao buscadas."}</p><p>Tarefa: {review.title}. Prioridade: {workPriorities[review.priority]}. Estados: {review.ticket_statuses.map(value => ticketStatuses[value]).join(", ")}.</p><div className="action-row"><Button disabled={locked} onClick={() => patch(review, { enabled: !review.enabled })}>{review.enabled ? "Confirmar desativacao" : "Confirmar ativacao"}</Button><Button variant="outline" disabled={write.locked} onClick={() => { setReview(null); requestAnimationFrame(() => { if (session.isCurrent()) reviewOpener.current?.focus(); }); }}>Cancelar revisao</Button></div></section>}
      {editor && <RuleForm key={editor.id + editor.version} initial={editor} disabled={locked || !active} submit={body => patch(editor, body)} cancel={() => { setEditor(null); requestAnimationFrame(() => { if (session.isCurrent()) editOpener.current?.focus(); }); }} />}
    </>}
    {!denied && (!rule || write.current?.kind === "create") && <><p>A nova regra comeca desativada. Revise os campos antes de cadastrar.</p><RuleForm disabled={write.locked || preparingRead || !active || query.isPending || query.isError} submit={async body => {
      if (preparing.current || write.locked || !session.isCurrent()) return;
      preparing.current = true; setPreparingRead(true);
      setNotice("");
      try {
        const current = await queues.get(queue.id);
        if (session.isCurrent()) write.submit({ kind: "create", body: { ...body, client_id: client.id }, queueVersion: current.version, key: crypto.randomUUID() });
      } catch { if (session.isCurrent()) setNotice("Nao foi possivel conferir a fila. Atualize antes de cadastrar."); }
      finally { preparing.current = false; if (session.isCurrent()) setPreparingRead(false); }
    }} /></>}
    {acknowledged ? <div className="read-notice"><p role="status">Operacao registrada. A confirmacao esta pendente.</p><Button variant="outline" disabled={write.pending} onClick={write.verify}>Confirmar dados da regra</Button></div> : <WriteRecovery write={write} reload={async () => { await refresh(); setEditor(null); setReview(null); }} verifyLabel="Verificar regra" />}
    {notice && !denied && <p role="status" className="read-notice">{notice}</p>}
  </div>;
}

export function AssignmentRules({ queue, session }: { queue: QueueRecord; session: WorkspaceSession }) {
  const api = createClientApi(session.user.csrf_token, session.onAuthError);
  const paging = usePaging();
  const query = useQuery({ queryKey: ["automation-client-choices", paging.cursor], queryFn: ({ signal }) => api.list(paging.cursor, signal) });
  const [selected, setSelected] = useState<ClientRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const choices = query.data?.items.filter(row => row.can_manage) ?? [];
  return <section className="admin-section" aria-labelledby="automation-heading"><h2 id="automation-heading">Automacoes de atribuicao</h2>
    <p className="field-help">Selecione um cliente sob sua gestao. A configuracao tambem exige gestao operacional e administrativa desta fila.</p>
    <label htmlFor="automation-client">Cliente da automacao</label><select id="automation-client" value={selected?.id ?? ""} disabled={busy || query.isFetching} onChange={event => setSelected(choices.find(row => row.id === event.target.value) ?? null)}><option value="">Selecione um cliente</option>{selected && !choices.some(row => row.id === selected.id) && <option value={selected.id}>{selected.name}</option>}{choices.map(row => <option key={row.id} value={row.id}>{row.name}{row.active ? "" : " (arquivado)"}</option>)}</select>
    {query.isPending && <LoadingRows label="Carregando clientes para automacao..." />}{query.isError && <ReadError retry={() => void query.refetch()} />}
    {query.isSuccess && !choices.length && <p>Nenhum cliente sob sua gestao disponivel nesta pagina.</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="clientes" disabled={busy || query.isFetching} />
    {selected && <RuleScope key={selected.id} queue={queue} client={selected} session={session} onBusyChange={setBusy} />}
  </section>;
}
