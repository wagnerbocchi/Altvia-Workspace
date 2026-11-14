"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging, useTeamWrite } from "@/components/team-admin/common";
import { WriteRecovery } from "@/components/work-items/recovery";
import type { WorkspaceSession } from "@/components/workspace-session";
import { isResourceForbidden } from "@/lib/http";
import { createTicketApi, ticketStatuses, type TicketRecord } from "@/lib/tickets";
import { createWorkApi, workStatuses, workPriorities, type WorkRecord } from "@/lib/work-items";
import { createTicketWorkApi, type LinkIntent, type LinkFilters } from "@/lib/ticket-work";

type Parent = {
  session: WorkspaceSession;
  parentLocked: boolean;
  parentAvailable: boolean;
  onBusyChange: (busy: boolean) => void;
};
type Review = { intent: LinkIntent; ticket: TicketRecord; work: WorkRecord };
const sameIntent = (a: LinkIntent, b: LinkIntent) => a.key === b.key && a.operation === b.operation
  && a.ticketId === b.ticketId && a.workItemId === b.workItemId
  && a.ticketVersion === b.ticketVersion && a.workItemVersion === b.workItemVersion;

// Only relationship intent and paired authoritative reads live here. Native
// useTeamWrite continues to own submission, uncertain replay and reconciliation.
function useLinkWrite({ session, parentLocked, onBusyChange }: Parent) {
  const cache = useQueryClient();
  const api = createTicketWorkApi(session.user.csrf_token, session.onAuthError);
  const tickets = createTicketApi(session.user.csrf_token, session.onAuthError);
  const work = createWorkApi(session.user.csrf_token, session.onAuthError);
  const [review, setReview] = useState<Review | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [readFailed, setReadFailed] = useState(false);
  const [acknowledged, setAcknowledged] = useState<LinkIntent | null>(null);
  const [notice, setNotice] = useState("");
  const focus = (id: string) => requestAnimationFrame(() => { if (session.isCurrent()) document.getElementById(id)?.focus(); });
  useEffect(() => {
    if (review && session.isCurrent()) document.getElementById("ticket-work-review-heading")?.focus();
  }, [review, session]);
  const details = async (ticketId: string, workItemId: string) => {
    // Cancel older in-flight reads so a pre-write reply cannot confirm a write.
    await Promise.all([
      cache.cancelQueries({ queryKey: ["ticket", ticketId], exact: true }),
      cache.cancelQueries({ queryKey: ["work-item", workItemId], exact: true }),
    ]);
    const [ticket, task] = await Promise.all([
      cache.fetchQuery({ queryKey: ["ticket", ticketId], queryFn: ({ signal }) => tickets.get(ticketId, signal), staleTime: 0 }),
      cache.fetchQuery({ queryKey: ["work-item", workItemId], queryFn: ({ signal }) => work.get(workItemId, signal), staleTime: 0 }),
    ]);
    return { ticket, work: task };
  };
  const refresh = async (intent: LinkIntent) => {
    await details(intent.ticketId, intent.workItemId);
    if (!session.isCurrent()) return;
    await Promise.all([
      cache.cancelQueries({ queryKey: ["ticket-work", intent.ticketId] }),
      cache.cancelQueries({ queryKey: ["work-tickets", intent.workItemId] }),
    ]);
    await Promise.all([
      cache.fetchQuery({ queryKey: ["ticket-work", intent.ticketId, null], queryFn: ({ signal }) => api.work(intent.ticketId, null, signal), staleTime: 0 }),
      cache.fetchQuery({ queryKey: ["work-tickets", intent.workItemId, null], queryFn: ({ signal }) => api.tickets(intent.workItemId, null, signal), staleTime: 0 }),
      cache.refetchQueries({ queryKey: ["ticket-work", intent.ticketId], type: "active" }, { throwOnError: true, cancelRefetch: false }),
      cache.refetchQueries({ queryKey: ["work-tickets", intent.workItemId], type: "active" }, { throwOnError: true, cancelRefetch: false }),
    ]);
    if (!session.isCurrent()) return;
    await Promise.all([
      ["ticket-activity", intent.ticketId], ["work-activity", intent.workItemId],
      ["ticket-work-choices", intent.ticketId], ["tickets"], ["work-items"],
    ].map(queryKey => cache.invalidateQueries({ queryKey })));
  };
  const confirmed = () => {
    if (!session.isCurrent()) return;
    setAcknowledged(null); setReview(null); setReadFailed(false);
    setNotice("Registros atualizados. Consulte os vinculos atuais abaixo.");
    focus("ticket-work-heading");
  };
  const perform = async (intent: LinkIntent): Promise<void> => {
    if (!session.isCurrent()) return;
    if (acknowledged && !sameIntent(acknowledged, intent)) throw Error("Acknowledged pair still awaiting reads");
    if (!acknowledged) {
      if (intent.operation === "link") {
        const receipt = await api.link(intent);
        if (receipt.ticket_id !== intent.ticketId || receipt.work_item_id !== intent.workItemId) throw Error("Link receipt not confirmed");
      } else await api.unlink(intent);
      if (!session.isCurrent()) return;
      setAcknowledged(intent);
    }
    await refresh(intent);
  };
  const write = useTeamWrite(session, perform, confirmed);
  const busy = reviewing || review !== null || write.locked || acknowledged !== null;
  useEffect(() => { onBusyChange(busy); }, [busy, onBusyChange]);
  useEffect(() => () => onBusyChange(false), [onBusyChange]);
  const start = async (operation: LinkIntent["operation"], ticketId: string, workItemId: string) => {
    if (busy || parentLocked || !session.isCurrent()) return;
    setReviewing(true); setReadFailed(false); setNotice("");
    try {
      const fresh = await details(ticketId, workItemId);
      if (!session.isCurrent()) return;
      if (!fresh.ticket.can_update || !fresh.work.can_update || !fresh.work.project_writable) {
        setReadFailed(true); return;
      }
      setReview({ ...fresh, intent: Object.freeze({ operation, ticketId, workItemId,
        ticketVersion: fresh.ticket.version, workItemVersion: fresh.work.version, key: crypto.randomUUID() }) });
    } catch { if (session.isCurrent()) setReadFailed(true); }
    finally { if (session.isCurrent()) setReviewing(false); }
  };
  const reload = async () => {
    const intent = acknowledged ?? write.current ?? review?.intent;
    if (intent) await refresh(intent);
    if (session.isCurrent()) { setReview(null); setReadFailed(false); setNotice(""); focus("ticket-work-heading"); }
  };
  return { api, write, review, busy, reviewing, readFailed, acknowledged, notice, start,
    cancel: () => { setReview(null); focus("ticket-work-heading"); }, reload,
    retryReads: () => void write.reconcile(async () => { if (acknowledged) { await refresh(acknowledged); confirmed(); } }),
  };
}

function LinkReview({ state, locked, available }: { state: ReturnType<typeof useLinkWrite>; locked: boolean; available: boolean }) {
  const { write, review, acknowledged } = state;
  return <>
    {acknowledged ? <div className="read-error">
      <p role="status">Operacao registrada. A confirmacao dos dados esta pendente.</p>
      <Button variant="outline" disabled={write.pending || write.reloading} onClick={state.retryReads}>Atualizar registros vinculados</Button>
      {write.reloadFailed && <p role="alert">Nao foi possivel atualizar. Novas alteracoes continuam bloqueadas.</p>}
    </div> : <>
      <WriteRecovery write={write} reload={state.reload} verifyLabel="Verificar vinculo" />
      {isResourceForbidden(write.error) && write.current && <Button variant="outline" disabled={write.pending || write.reloading} onClick={write.verify}>Verificar vinculo</Button>}
      {available && review && <section className="confirmation" aria-labelledby="ticket-work-review-heading">
        <h3 id="ticket-work-review-heading" tabIndex={-1}>{review.intent.operation === "link" ? "Revisar vinculacao" : "Revisar desvinculacao"}</h3>
        <dl className="account-details work-facts">
          <div><dt>Chamado</dt><dd>{review.ticket.number} - {review.ticket.subject}</dd></div>
          <div><dt>Estado do chamado</dt><dd>{ticketStatuses[review.ticket.status]}</dd></div>
          <div><dt>Tarefa</dt><dd>{review.work.title}</dd></div>
          <div><dt>Estado da tarefa</dt><dd>{workStatuses[review.work.status]}</dd></div>
        </dl>
        <p>{review.intent.operation === "link" ? "Vincular estes registros do mesmo cliente?" : "Remover somente este vinculo?"} Estados, responsaveis e prazos permanecem independentes.</p>
        <div className="action-row">
          <Button disabled={locked || write.locked} onClick={() => write.submit(review.intent)}>{review.intent.operation === "link" ? "Confirmar vinculacao" : "Confirmar desvinculacao"}</Button>
          <Button variant="outline" disabled={write.locked || locked} onClick={state.cancel}>Cancelar revisao</Button>
        </div>
      </section>}
    </>}
    {state.reviewing && <LoadingRows label="Conferindo chamado e tarefa..." />}
    {state.readFailed && <p role="alert" className="read-error">Nao foi possivel revisar os dois registros. Atualize a lista e confira seu acesso antes de selecionar novamente.</p>}
    {state.notice && available && <p role="status" className="read-notice">{state.notice}</p>}
    {!available && <p role="alert" className="read-error">Os dados do registro nao estao disponiveis. Atualize antes de consultar os vinculos.</p>}
  </>;
}

export function TicketWorkLinks({ ticket, ...parent }: Parent & { ticket: TicketRecord }) {
  const state = useLinkWrite(parent);
  const paging = usePaging(), choicesPaging = usePaging();
  const [choosing, setChoosing] = useState(false);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<LinkFilters>({});
  const query = useQuery({ queryKey: ["ticket-work", ticket.id, paging.cursor], queryFn: ({ signal }) => state.api.work(ticket.id, paging.cursor, signal), enabled: parent.parentAvailable });
  const choices = useQuery({ queryKey: ["ticket-work-choices", ticket.id, filters, choicesPaging.cursor], queryFn: ({ signal }) => state.api.choices(ticket.id, choicesPaging.cursor, filters, signal), enabled: choosing && parent.parentAvailable && !!query.data?.can_link });
  const blocked = parent.parentLocked || state.busy;
  const visible = parent.parentAvailable && !state.acknowledged;
  return <section className="admin-section" aria-labelledby="ticket-work-heading">
    <h2 id="ticket-work-heading" tabIndex={-1}>Tarefas vinculadas</h2>
    <LinkReview state={state} locked={parent.parentLocked || !parent.parentAvailable} available={visible} />
    {visible && <>
      <p className="field-help">Vincule tarefas existentes do mesmo cliente. Cada registro mantem seu estado, responsaveis e prazos.</p>
      <div className="action-row">
        <Button variant="outline" disabled={query.isFetching || state.write.pending} onClick={() => void query.refetch()}>Atualizar tarefas vinculadas</Button>
        {!query.isError && query.data?.can_link && <Button disabled={blocked || query.isFetching} onClick={() => setChoosing(!choosing)}>{choosing ? "Fechar selecao" : "Vincular tarefa"}</Button>}
      </div>
      {query.isPending ? <LoadingRows label="Carregando tarefas vinculadas..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : <>
        {query.data.items.length ? <ul className="record-list" aria-label="Tarefas vinculadas">{query.data.items.map(row => <li className="team-row" key={row.work_item_id}>
          <div className="record-text"><Link className="text-link" href={`/work-items/${encodeURIComponent(row.work_item_id)}`}>{row.title}</Link>
            <span className="record-meta">{row.project_name}</span><span className="record-meta">Estado da tarefa: {workStatuses[row.status]} - Prioridade: {workPriorities[row.priority]}</span></div>
          {row.can_unlink && <Button variant="outline" disabled={blocked || query.isFetching} onClick={() => void state.start("unlink", ticket.id, row.work_item_id)}>Desvincular tarefa</Button>}
        </li>)}</ul> : <p>Nenhuma tarefa vinculada disponivel nesta pagina.</p>}
        {!query.data.can_link && <p className="field-help">Vinculacao indisponivel para este chamado. Consulte seu acesso e o estado dos registros.</p>}
      </>}
      <Paging paging={paging} next={query.data?.next_cursor} label="tarefas" disabled={query.isFetching || state.write.pending} />
      {choosing && query.data?.can_link && !query.isError && <section aria-labelledby="ticket-work-choices-heading">
        <h3 id="ticket-work-choices-heading">Escolher tarefa existente</h3>
        <form className="work-comment-form" onSubmit={event => { event.preventDefault(); if (!blocked) { setFilters(search.trim() ? { q: search.trim() } : {}); choicesPaging.reset(); } }}>
          <label htmlFor="ticket-work-search">Buscar tarefa para vincular</label>
          <input id="ticket-work-search" value={search} maxLength={200} disabled={blocked} onChange={event => setSearch(event.target.value)} />
          <Button variant="outline" type="submit" disabled={blocked}>Buscar tarefas</Button>
        </form>
        {choices.isPending ? <LoadingRows label="Carregando tarefas disponiveis..." /> : choices.isError ? <ReadError retry={() => void choices.refetch()} /> : choices.data?.items.length ? <ul className="record-list" aria-label="Tarefas para vincular">{choices.data.items.map(row => <li className="team-row" key={row.work_item_id}>
          <div className="record-text"><strong>{row.title}</strong><span className="record-meta">{row.project_name}</span><span className="record-meta">Estado da tarefa: {workStatuses[row.status]} - Prioridade: {workPriorities[row.priority]}</span></div>
          <Button variant="outline" disabled={blocked || choices.isFetching || !choices.data?.can_link} onClick={() => void state.start("link", ticket.id, row.work_item_id)}>Revisar vinculo</Button>
        </li>)}</ul> : <p>Nenhuma tarefa elegivel nesta pagina com esta busca.</p>}
        <Paging paging={choicesPaging} next={choices.data?.next_cursor} label="tarefas" disabled={choices.isFetching || state.write.pending} />
      </section>}
    </>}
  </section>;
}

export function WorkTicketLinks({ work, ...parent }: Parent & { work: WorkRecord }) {
  const state = useLinkWrite(parent);
  const paging = usePaging();
  const query = useQuery({ queryKey: ["work-tickets", work.id, paging.cursor], queryFn: ({ signal }) => state.api.tickets(work.id, paging.cursor, signal), enabled: parent.parentAvailable });
  const blocked = parent.parentLocked || state.busy;
  return <section className="admin-section" aria-labelledby="ticket-work-heading">
    <h2 id="ticket-work-heading" tabIndex={-1}>Chamados vinculados</h2>
    <LinkReview state={state} locked={parent.parentLocked || !parent.parentAvailable} available={parent.parentAvailable && !state.acknowledged} />
    {parent.parentAvailable && !state.acknowledged && <>
      <p className="field-help">Para vincular esta tarefa, abra um chamado do mesmo cliente e escolha Vincular tarefa. Os estados permanecem independentes.</p>
      <Link className="text-link" href="/service-desk/tickets">Consultar chamados</Link>
      <div className="action-row"><Button variant="outline" disabled={query.isFetching || state.write.pending} onClick={() => void query.refetch()}>Atualizar chamados vinculados</Button></div>
      {query.isPending ? <LoadingRows label="Carregando chamados vinculados..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ? <ul className="record-list" aria-label="Chamados vinculados">{query.data.items.map(row => <li className="team-row" key={row.ticket_id}>
        <div className="record-text"><Link className="text-link" href={`/service-desk/tickets/${encodeURIComponent(row.ticket_id)}`}>{row.number} - {row.subject}</Link>
          <span className="record-meta">Estado do chamado: {ticketStatuses[row.status]}</span></div>
        {row.can_unlink && <Button variant="outline" disabled={blocked || query.isFetching} onClick={() => void state.start("unlink", row.ticket_id, work.id)}>Desvincular chamado</Button>}
      </li>)}</ul> : <p>Nenhum chamado vinculado disponivel nesta pagina.</p>}
      <Paging paging={paging} next={query.data?.next_cursor} label="chamados" disabled={query.isFetching || state.write.pending} />
    </>}
  </section>;
}
