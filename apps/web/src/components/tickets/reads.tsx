"use client";

import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import { type TicketApi, ticketStatuses } from "@/lib/tickets";

export function TicketHistory({ id, api }: { id: string; api: TicketApi }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["ticket-states", id, paging.cursor], queryFn: ({ signal }) => api.states(id, paging.cursor, signal) });
  return <section className="admin-section" aria-labelledby="ticket-history-heading">
    <h2 id="ticket-history-heading">Historico de estados</h2>
    <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar estados</Button>
    {query.isPending ? <LoadingRows label="Carregando estados..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> :
      <ul className="record-list" aria-label="Historico de estados">{query.data.items.map(row => <li className="team-row" key={row.id}>
        <div className="record-text">
          <strong>{row.from_status ? `${ticketStatuses[row.from_status]} para ${ticketStatuses[row.to_status]}` : `Criado como ${ticketStatuses[row.to_status]}`}</strong>
          {row.reason && <p className="work-prose">{row.reason}</p>}
          <span className="record-meta">Autor {row.actor_id} - versao {row.version}</span>
          <time className="record-meta" dateTime={row.occurred_at}>{new Date(row.occurred_at).toLocaleString("pt-BR")}</time>
        </div>
      </li>)}</ul>}
    <Paging paging={paging} next={query.data?.next_cursor} label="mudanças de estado" disabled={query.isFetching} />
  </section>;
}

export function TicketActivity({ id, api }: { id: string; api: TicketApi }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["ticket-activity", id, paging.cursor], queryFn: ({ signal }) => api.activity(id, paging.cursor, signal) });
  const labels: Record<string, string> = { "ticket.created": "Chamado criado", "ticket.updated": "Chamado editado", "ticket.assigned": "Responsavel atribuido", "ticket.status_changed": "Estado alterado" };
  return <section className="admin-section" aria-labelledby="ticket-activity-heading">
    <h2 id="ticket-activity-heading">Atividade do chamado</h2>
    <p className="field-help">Novas atividades podem levar instantes para aparecer.</p>
    <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar atividade</Button>
    {query.isPending ? <LoadingRows label="Carregando atividade..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ?
      <ul className="record-list" aria-label="Atividade do chamado">{query.data.items.map(row => <li className="team-row" key={row.event_id}>
        <div className="record-text"><strong>{labels[row.event_type] ?? "Alteracao registrada"}</strong>
          <span className="record-meta">Autor {row.actor_id} - versao {row.aggregate_version}</span>
          <time className="record-meta" dateTime={row.occurred_at}>{new Date(row.occurred_at).toLocaleString("pt-BR")}</time>
        </div>
      </li>)}</ul> : <p>Nenhuma atividade disponivel nesta pagina.</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="atividades" disabled={query.isFetching} />
  </section>;
}
