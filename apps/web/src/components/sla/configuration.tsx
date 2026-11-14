"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging, useTeamWrite } from "@/components/team-admin/common";
import { WriteRecovery } from "@/components/work-items/recovery";
import type { WorkspaceSession } from "@/components/workspace-session";
import { createClientApi, type ClientRecord } from "@/lib/clients";
import { createQueueApi, type QueueRecord } from "@/lib/ticket-queues";
import { ApiError } from "@/lib/http";
import { createSlaApi, type Calendar, type CalendarCreate, type CalendarPatch, type Policy, type PolicyCreate, type PolicyPatch } from "@/lib/sla";
import { CalendarForm } from "./calendars";
import { CalendarFacts, PolicyFacts, PolicyForm, type PolicyBody } from "./policies";

type Editor = { kind: "calendar"; initial?: Calendar } | { kind: "policy"; initial?: Policy };
type Intent = { kind: "calendar-create"; body: CalendarCreate; queueVersion: number; key: string }
  | { kind: "calendar-patch"; id: string; body: CalendarPatch; version: number; queueVersion: number; key: string }
  | { kind: "policy-create"; body: PolicyCreate; queueVersion: number; key: string }
  | { kind: "policy-patch"; id: string; body: PolicyPatch; version: number; queueVersion: number; key: string };

function Scope({ queue, client, session, available, onBusyChange }: { queue: QueueRecord; client: ClientRecord; session: WorkspaceSession; available: boolean; onBusyChange: (busy: boolean) => void }) {
  const cache = useQueryClient();
  const api = createSlaApi(session.user.csrf_token, session.onAuthError);
  const queues = createQueueApi(session.user.csrf_token, session.onAuthError);
  const calendarPaging = usePaging(), policyPaging = usePaging();
  const calendars = useQuery({ queryKey: ["sla-calendars", queue.id, client.id, calendarPaging.cursor], queryFn: ({ signal }) => api.calendars(queue.id, client.id, calendarPaging.cursor, signal), enabled: available });
  const policies = useQuery({ queryKey: ["sla-policies", queue.id, client.id, policyPaging.cursor], queryFn: ({ signal }) => api.policies(queue.id, client.id, policyPaging.cursor, signal), enabled: available });
  const [editor, setEditor] = useState<Editor | null>(null);
  const [review, setReview] = useState<Policy | null>(null);
  const [viewed, setViewed] = useState<Calendar | null>(null);
  const [preparing, setPreparing] = useState(false);
  const preparingRef = useRef(false);
  const opener = useRef<HTMLButtonElement | null>(null);
  const restoreOpener = useRef(false);
  const [notice, setNotice] = useState("");
  const [readFailed, setReadFailed] = useState(false);
  const receipt = useRef<{ key: string; id: string; kind: "calendar" | "policy" } | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const category = useQuery({ queryKey: ["sla-reviewed-category", queue.id, review?.category_id], queryFn: ({ signal }) => queues.category(queue.id, review!.category_id!, signal), enabled: available && !!review?.category_id });
  const reviewedCalendar = useQuery({ queryKey: ["sla-policy-calendar", queue.id, review?.id, review?.version], queryFn: ({ signal }) => api.policyCalendar(queue.id, review!.id, signal), enabled: available && !!review });
  const refresh = async () => {
    if (!session.isCurrent()) return;
    await Promise.all([cache.cancelQueries({ queryKey: ["sla-calendars", queue.id, client.id] }), cache.cancelQueries({ queryKey: ["sla-policies", queue.id, client.id] })]);
    if (!session.isCurrent()) return;
    await Promise.all([calendars.refetch({ throwOnError: true }), policies.refetch({ throwOnError: true })]);
    if (session.isCurrent()) await cache.invalidateQueries({ queryKey: ["ticket-queue", queue.id] });
  };
  const write = useTeamWrite(session, async (intent: Intent) => {
    if (!session.isCurrent()) return;
    if (!receipt.current) {
      if (intent.kind === "calendar-create" || intent.kind === "calendar-patch") {
        const result = intent.kind === "calendar-create" ? await api.createCalendar(queue.id, intent.body, intent.queueVersion, intent.key) : await api.patchCalendar(queue.id, intent.id, intent.body, intent.version, intent.queueVersion, intent.key);
        if (!session.isCurrent()) return;
        if (result.queue_id !== queue.id || result.client_id !== client.id || (intent.kind === "calendar-patch" && result.calendar_id !== intent.id)) throw Error("Calendar receipt scope not confirmed");
        receipt.current = { key: intent.key, id: result.calendar_id, kind: "calendar" };
      } else {
        const result = intent.kind === "policy-create" ? await api.createPolicy(queue.id, intent.body, intent.queueVersion, intent.key) : await api.patchPolicy(queue.id, intent.id, intent.body, intent.version, intent.queueVersion, intent.key);
        if (!session.isCurrent()) return;
        if (result.queue_id !== queue.id || result.client_id !== client.id || (intent.kind === "policy-patch" && result.policy_id !== intent.id)) throw Error("Policy receipt scope not confirmed");
        receipt.current = { key: intent.key, id: result.policy_id, kind: "policy" };
      }
      setAcknowledged(true);
    }
    if (receipt.current.key !== intent.key) throw Error("Original SLA intent required");
    if (receipt.current.kind === "calendar") await api.calendar(queue.id, receipt.current.id);
    else await api.policy(queue.id, receipt.current.id);
    if (session.isCurrent()) await refresh();
  }, () => {
    receipt.current = null; setAcknowledged(false); setEditor(null); setReview(null); setViewed(null); setReadFailed(false);
    setNotice("Configuracao confirmada. Os ciclos existentes preservam suas revisoes.");
    requestAnimationFrame(() => { if (session.isCurrent()) document.getElementById("sla-scope-heading")?.focus(); });
  });
  const busy = write.locked || preparing || editor !== null || review !== null;
  useEffect(() => { onBusyChange(busy); return () => onBusyChange(false); }, [busy, onBusyChange]);
  useEffect(() => {
    if (session.isCurrent() && (editor || review || viewed)) document.getElementById(editor ? `sla-${editor.kind}-form-heading` : review ? "sla-policy-review-heading" : "sla-calendar-view-heading")?.focus();
  }, [editor, review, viewed, session]);
  const denied = [calendars.error, policies.error].some(error => error instanceof ApiError && [403, 404].includes(error.status));
  const locked = write.locked || preparing || !available || calendars.isError || policies.isError || calendars.isFetching || policies.isFetching;
  const active = queue.active && queue.team_active && client.active;
  useEffect(() => {
    if (restoreOpener.current && !locked && !busy && session.isCurrent()) {
      restoreOpener.current = false;
      const target = opener.current;
      if (target?.isConnected && !target.disabled) target.focus();
      else document.getElementById("sla-scope-heading")?.focus();
    }
  }, [locked, busy, editor, review, viewed, session]);
  const cancel = () => { restoreOpener.current = true; setEditor(null); setReview(null); setViewed(null); setReadFailed(false); };
  const open = async (event: React.MouseEvent<HTMLButtonElement>, kind: "calendar" | "policy", id?: string, readOnly = false) => {
    if (preparingRef.current || busy || !session.isCurrent()) return;
    opener.current = event.currentTarget;
    setViewed(null);
    if (!id) { setEditor({ kind }); return; }
    preparingRef.current = true; setPreparing(true); onBusyChange(true); setReadFailed(false);
    try {
      if (kind === "calendar") { const row = await api.calendar(queue.id, id); if (session.isCurrent()) { if (readOnly) setViewed(row); else setEditor({ kind, initial: row }); } }
      else { const row = await api.policy(queue.id, id); if (session.isCurrent()) setEditor({ kind, initial: row }); }
    } catch { if (session.isCurrent()) setReadFailed(true); }
    finally { preparingRef.current = false; if (session.isCurrent()) setPreparing(false); }
  };
  const submitCreate = async (kind: "calendar" | "policy", body: CalendarCreate | PolicyCreate) => {
    if (preparingRef.current || write.locked || !session.isCurrent()) return;
    preparingRef.current = true; setPreparing(true); onBusyChange(true); setReadFailed(false);
    try {
      const fresh = await queues.get(queue.id);
      if (session.isCurrent()) {
        const key = crypto.randomUUID();
        if (kind === "calendar") write.submit({ kind: "calendar-create", body: body as CalendarCreate, queueVersion: fresh.version, key });
        else write.submit({ kind: "policy-create", body: body as PolicyCreate, queueVersion: fresh.version, key });
      }
    } catch { if (session.isCurrent()) setReadFailed(true); }
    finally { preparingRef.current = false; if (session.isCurrent()) setPreparing(false); }
  };
  const saveCalendar = (body: Omit<CalendarCreate, "client_id">) => {
    if (editor?.kind !== "calendar") return;
    if (editor.initial) write.submit({ kind: "calendar-patch", id: editor.initial.id, body, version: editor.initial.version, queueVersion: editor.initial.queue_version, key: crypto.randomUUID() });
    else void submitCreate("calendar", { ...body, client_id: client.id });
  };
  const savePolicy = (body: PolicyBody) => {
    if (editor?.kind !== "policy") return;
    if (editor.initial) {
      const patch: PolicyPatch = { name: body.name, calendar_id: body.calendar_id,
        calendar_version: body.calendar_version, first_response_minutes: body.first_response_minutes,
        resolution_minutes: body.resolution_minutes, approach_minutes: body.approach_minutes,
        pause_states: body.pause_states };
      write.submit({ kind: "policy-patch", id: editor.initial.id, body: patch, version: editor.initial.version, queueVersion: editor.initial.queue_version, key: crypto.randomUUID() });
    } else void submitCreate("policy", { ...body, client_id: client.id });
  };
  if (!available) return null;
  return <div><h3 id="sla-scope-heading" className="work-subheading sla-subheading" tabIndex={-1}>{denied ? "Configuracao de SLA indisponivel" : client.name}</h3>
    {calendars.isPending || policies.isPending ? <LoadingRows label="Carregando configuracao de SLA..." /> : null}
    {(calendars.isError || policies.isError) && <ReadError retry={() => void refresh().catch(() => { /* Query state owns read recovery. */ })}>{denied ? "A configuracao desta fila e cliente nao esta disponivel para sua conta." : undefined}</ReadError>}
    {readFailed && <div className="read-error"><p role="alert">Nao foi possivel conferir o registro. Atualize os dados antes de continuar.</p><Button variant="outline" disabled={write.locked || preparing} onClick={() => void refresh().then(() => setReadFailed(false)).catch(() => { /* Existing failure remains visible. */ })}>Atualizar configuracao de SLA</Button></div>}
    {!denied && <>
      <div className="action-row work-description"><Button variant="outline" disabled={locked || busy || !active} onClick={event => void open(event, "calendar")}>Novo calendario</Button><Button disabled={locked || busy || !active} onClick={event => void open(event, "policy")}>Nova politica de SLA</Button><Button variant="outline" disabled={locked || busy} onClick={() => void refresh().catch(() => { /* Query state owns recovery. */ })}>Atualizar configuracao</Button></div>
      {editor?.kind === "calendar" && <CalendarForm key={editor.initial?.id ?? "new-calendar"} initial={editor.initial} disabled={locked || !active} submit={saveCalendar} cancel={cancel} />}
      {editor?.kind === "policy" && <PolicyForm key={editor.initial?.id ?? "new-policy"} initial={editor.initial} queueId={queue.id} session={session} calendars={calendars.data?.items ?? []} calendarPaging={calendarPaging} nextCalendar={calendars.data?.next_cursor} disabled={locked || !active} submit={savePolicy} cancel={cancel} />}
      {review && <section className="confirmation" aria-labelledby="sla-policy-review-heading"><h4 className="sla-subheading" id="sla-policy-review-heading" tabIndex={-1}>{review.enabled ? "Desativar politica de SLA?" : "Ativar politica de SLA?"}</h4><p><strong>{review.name}</strong></p><PolicyFacts row={review} categoryName={category.data?.name} />
        {reviewedCalendar.isPending && <LoadingRows label="Conferindo calendario capturado..." />}
        {reviewedCalendar.isError && <ReadError retry={() => void reviewedCalendar.refetch()} />}
        {!reviewedCalendar.isError && reviewedCalendar.data && <><h5 className="sla-subheading">Calendario capturado pela politica</h5><CalendarFacts row={reviewedCalendar.data} />
          {!reviewedCalendar.data.calendar_active && <p className="field-help">O calendario esta desativado atualmente. Reative-o ou revise a politica antes de ativar.</p>}
          {reviewedCalendar.data.policy_version !== review.version && <p className="read-notice">A politica mudou desde a revisao. Cancele e atualize os dados.</p>}</>}
        {review.category_id && category.isPending && <LoadingRows label="Conferindo categoria da politica..." />}{review.category_id && category.isError && <ReadError retry={() => void category.refetch()} />}
        <p>Esta decisao vale apenas para novos chamados ou reaberturas. Os ciclos ja iniciados preservam suas metas e revisoes. Nenhum chamado antigo sera recalculado por esta alteracao.</p>
        <div className="action-row"><Button disabled={locked || !reviewedCalendar.data || reviewedCalendar.isError || reviewedCalendar.isFetching || reviewedCalendar.data.policy_version !== review.version || (!review.enabled && (!active || !reviewedCalendar.data.calendar_active || (!!review.category_id && (!category.data?.active || category.isError || category.isFetching))))} onClick={() => write.submit({ kind: "policy-patch", id: review.id, body: { enabled: !review.enabled }, version: review.version, queueVersion: review.queue_version, key: crypto.randomUUID() })}>{review.enabled ? "Confirmar desativacao do SLA" : "Confirmar ativacao do SLA"}</Button><Button variant="outline" disabled={write.locked} onClick={cancel}>Cancelar revisao do SLA</Button></div>
      </section>}
      {viewed && !editor && <section aria-labelledby="sla-calendar-view-heading"><h4 className="sla-subheading" id="sla-calendar-view-heading" tabIndex={-1}>Calendario consultado</h4><CalendarFacts row={viewed} /><Button variant="outline" onClick={cancel}>Fechar calendario consultado</Button></section>}
      <h4 className="work-subheading sla-subheading">Calendarios deste cliente e fila</h4>
      {!calendars.isError && calendars.data?.items.length === 0 && <p>Nenhum calendario cadastrado neste escopo.</p>}
      {!calendars.isError && <ul className="record-list" aria-label="Calendarios de SLA">{calendars.data?.items.map(row => <li className="team-row sla-calendar-row" key={row.id}><div className="record-text"><strong>{row.name}</strong><span className="record-meta">{row.timezone} - revisao {row.version} - {row.active ? "Ativo" : "Desativado"}</span></div><div className="action-row"><Button variant="outline" disabled={locked || busy} onClick={event => void open(event, "calendar", row.id, true)}>Consultar calendario {row.name}</Button><Button variant="outline" disabled={locked || busy || !active || !row.can_edit} onClick={event => void open(event, "calendar", row.id)}>Editar calendario {row.name}</Button></div></li>)}</ul>}
      <Paging paging={calendarPaging} next={calendars.data?.next_cursor} label="calendarios de SLA" disabled={locked || busy} />
      <h4 className="work-subheading sla-subheading">Politicas deste cliente e fila</h4><p className="field-help">Preferencia: categoria e prioridade; categoria; prioridade; politica geral. Referencias desativadas em uma politica selecionada impedem novos ciclos ate revisao.</p>
      {!policies.isError && policies.data?.items.length === 0 && <p>Nenhuma politica cadastrada neste escopo.</p>}
      {!policies.isError && <ul className="record-list" aria-label="Politicas de SLA">{policies.data?.items.map(row => <li className="sla-policy-row" key={row.id}><h5 className="work-subheading sla-subheading">{row.name}</h5><p><span className="record-status" data-state={row.enabled ? "active" : "inactive"}>{row.enabled ? "Politica ativada" : "Politica desativada"}</span><span className="record-meta">Revisao {row.version}</span></p><PolicyFacts row={row} /><div className="action-row"><Button disabled={locked || busy || (!row.enabled && (!row.can_edit || !active))} onClick={event => { opener.current = event.currentTarget; setReview(row); }}>{row.enabled ? "Revisar desativacao do SLA" : "Revisar ativacao do SLA"}</Button><Button variant="outline" disabled={locked || busy || !active || !row.can_edit} onClick={event => void open(event, "policy", row.id)}>Editar politica {row.name}</Button></div></li>)}</ul>}
      <Paging paging={policyPaging} next={policies.data?.next_cursor} label="politicas de SLA" disabled={locked || busy} />
    </>}
    {acknowledged ? <div className="read-notice"><p role="status">Operacao registrada. Falta confirmar os dados atuais.</p><Button variant="outline" disabled={write.pending} onClick={write.verify}>Confirmar dados do SLA</Button></div> : <WriteRecovery write={write} reload={async () => { await refresh(); cancel(); }} verifyLabel="Verificar configuracao de SLA" />}
    {notice && !denied && <p role="status" className="read-notice">{notice}</p>}
  </div>;
}

export function SlaConfiguration({ queue, session, available }: { queue: QueueRecord; session: WorkspaceSession; available: boolean }) {
  const api = createClientApi(session.user.csrf_token, session.onAuthError);
  const paging = usePaging();
  const query = useQuery({ queryKey: ["sla-client-choices", paging.cursor], queryFn: ({ signal }) => api.list(paging.cursor, signal), enabled: available });
  const [selected, setSelected] = useState<ClientRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const busyChanged = useCallback((value: boolean) => setBusy(value), []);
  const choices = query.data?.items.filter(row => row.can_manage) ?? [];
  if (!available) return null;
  return <section className="admin-section" aria-labelledby="sla-configuration-heading"><h2 id="sla-configuration-heading">SLA e calendarios</h2><p className="field-help">Selecione um cliente sob sua gestao. Calendarios e politicas pertencem a esta fila e cliente. A selecao nao altera permissoes nem configura horarios automaticamente.</p>
    <label htmlFor="sla-client">Cliente do SLA</label><select id="sla-client" value={selected?.id ?? ""} disabled={busy || query.isFetching || query.isError} onChange={event => setSelected(choices.find(row => row.id === event.target.value) ?? null)}><option value="">Selecione um cliente</option>{selected && !choices.some(row => row.id === selected.id) && <option value={selected.id}>{selected.name}</option>}{choices.map(row => <option key={row.id} value={row.id}>{row.name}{row.active ? "" : " (arquivado)"}</option>)}</select>
    {query.isPending && <LoadingRows label="Carregando clientes para SLA..." />}{query.isError && <ReadError retry={() => void query.refetch()} />}
    {query.isSuccess && !choices.length && <p>Nenhum cliente sob sua gestao nesta pagina.</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="clientes" disabled={busy || query.isFetching} />
    {selected && <Scope key={selected.id} queue={queue} client={selected} session={session} available={!query.isError && !query.isPending} onBusyChange={busyChanged} />}
  </section>;
}
