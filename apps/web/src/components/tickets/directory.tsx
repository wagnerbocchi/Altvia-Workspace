"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import { type TicketApi, type TicketFilters, ticketPriorities, ticketStatuses } from "@/lib/tickets";

export function TicketDirectory({ api, actor }: { api: TicketApi; actor: string }) {
  const paging = usePaging();
  const [filters, setFilters] = useState<TicketFilters>({});
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [assignment, setAssignment] = useState("");
  const [queue, setQueue] = useState("");
  const [client, setClient] = useState<{ id: string; name: string } | null>(null);
  const [queueCursor, setQueueCursor] = useState<string | null>(null);
  const queues = useQuery({ queryKey: ["ticket-inbox-queues", queueCursor], queryFn: ({ signal }) => api.queues(queueCursor, signal) });
  const authority = useQuery({ queryKey: ["ticket-create-authority"], queryFn: ({ signal }) => api.queues(null, signal) });
  const query = useQuery({ queryKey: ["tickets", filters, paging.cursor], queryFn: ({ signal }) => api.list(filters, paging.cursor, signal) });
  return <div className="admin-workspace ticket-workspace">
    <Link className="text-link" href="/">Voltar a minha conta</Link>
    <h1 id="tickets-heading" tabIndex={-1}>Chamados</h1>
    <div className="action-row">
      {authority.data?.can_create && <Button asChild><Link href="/service-desk/tickets/new">Novo chamado</Link></Button>}
      <Link className="text-link" href="/service-desk/mail-cases">Mensagens recebidas</Link>
      <Link className="text-link" href="/service-desk/queues">Filas de atendimento</Link>
    </div>
    <div className="admin-plane">
      <section className="admin-section" aria-labelledby="ticket-filters-heading">
        <h2 id="ticket-filters-heading">Filtrar chamados</h2>
        <form className="ticket-filters" onSubmit={event => {
          event.preventDefault(); paging.reset();
          setFilters({ q: search.trim(), status: status as TicketFilters["status"], priority: priority as TicketFilters["priority"], queue_id: queue || undefined,
            client_id: client?.id, assignee_id: assignment === "mine" ? actor : undefined, unassigned: assignment === "unassigned" });
        }}>
          <div className="account-form-grid">
            <div><label htmlFor="ticket-search">Busca nos chamados</label><input id="ticket-search" type="search" value={search} maxLength={200} onChange={event => setSearch(event.target.value)} /></div>
            <div><label htmlFor="ticket-status-filter">Estado</label><select id="ticket-status-filter" value={status} onChange={event => setStatus(event.target.value)}>
              <option value="">Todos os estados</option>{Object.entries(ticketStatuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></div>
            <div><label htmlFor="ticket-priority-filter">Prioridade</label><select id="ticket-priority-filter" value={priority} onChange={event => setPriority(event.target.value)}>
              <option value="">Todas as prioridades</option>{Object.entries(ticketPriorities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></div>
          </div>
          <details className="ticket-filter-extra"><summary>Mais filtros de chamados</summary>
          <div className="account-form-grid">
            <div><label htmlFor="ticket-assignment-filter">Atribuicao</label><select id="ticket-assignment-filter" value={assignment} onChange={event => setAssignment(event.target.value)}>
              <option value="">Todos os responsaveis</option><option value="mine">Atribuidos a mim</option><option value="unassigned">Sem responsavel</option>
            </select></div>
            <div><label htmlFor="ticket-queue-filter">Fila</label><select id="ticket-queue-filter" value={queue} disabled={queues.isPending || queues.isError} onChange={event => setQueue(event.target.value)}>
              <option value="">Todas as filas</option>{queues.data?.items.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
              {queue && !queues.data?.items.some(row => row.id === queue) && <option value={queue}>Fila selecionada</option>}
            </select>
              {queues.isError && <ReadError retry={() => void queues.refetch()} />}
              <div className="action-row"><Button type="button" variant="outline" disabled={!queueCursor || queues.isFetching} onClick={() => setQueueCursor(null)}>Primeiras filas</Button>
                <Button type="button" variant="outline" disabled={!queues.data?.next_cursor || queues.isFetching} onClick={() => setQueueCursor(queues.data!.next_cursor)}>Proximas filas</Button></div>
            </div>
          </div>
          </details>
          {client && <p>Cliente selecionado {client.name} <Button type="button" variant="outline" onClick={() => setClient(null)}>Remover filtro de cliente</Button></p>}
          <Button type="submit" className="work-transition-action" disabled={query.isFetching}>Aplicar filtros</Button>
        </form>
      </section>
      <section className="admin-section" aria-labelledby="ticket-list-heading">
        <h2 id="ticket-list-heading">Chamados disponiveis</h2>
        <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar chamados</Button>
        {query.isPending ? <LoadingRows label="Carregando chamados..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ?
          <ul className="record-list" aria-label="Chamados disponiveis">{query.data.items.map(row => <li className="team-row" key={row.id}>
            <div className="record-text">
              <Link className="text-link" href={`/service-desk/tickets/${encodeURIComponent(row.id)}`}>{row.number} - {row.subject}</Link>
              <span className="record-meta">{row.queue_name} - {ticketPriorities[row.priority]}</span>
              <span className="record-meta">{row.assignee_name ?? "Sem responsavel"}</span>
              <Button variant="ghost" aria-label={`Filtrar por ${row.client_name}`} onClick={() => { setClient({ id: row.client_id, name: row.client_name }); setFilters(current => ({ ...current, client_id: row.client_id })); paging.reset(); }}>{row.client_name}</Button>
            </div><span className="record-status" data-state={row.status}>{ticketStatuses[row.status]}</span>
          </li>)}</ul> : <p>Nenhum chamado disponivel nesta pagina com estes filtros.</p>}
        <Paging paging={paging} next={query.data?.next_cursor} label="chamados" disabled={query.isFetching} />
      </section>
    </div>
  </div>;
}
