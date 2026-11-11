"use client";

import Link from "next/link";
import { useIsMutating, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import type { QueueApi } from "@/lib/ticket-queues";
import { ApiError } from "@/lib/http";
import { MetadataEditor } from "./metadata-editor";
import { QueueCategories } from "./categories";

const actions: Record<string, string> = {
  "ticket_queue.access_changed": "Acesso a fila alterado",
  "ticket_queue.created": "Fila cadastrada",
  "ticket_queue.updated": "Fila atualizada",
  "ticket_queue.category_created": "Categoria cadastrada",
  "ticket_queue.category_updated": "Categoria atualizada",
};

function QueueHistory({ id, api }: { id: string; api: QueueApi }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["queue-activity", id, paging.cursor], queryFn: ({ signal }) => api.activity(id, paging.cursor, signal) });
  return <section className="admin-section" aria-labelledby="queue-history-heading">
    <h2 id="queue-history-heading">Historico da fila</h2>
    <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar historico</Button>
    {query.isPending ? <LoadingRows label="Carregando historico..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ?
      <ul className="record-list" aria-label="Historico da fila">{query.data.items.map(row => <li className="team-row" key={row.event_id}>
        <div className="record-text"><strong>{actions[row.event_type] ?? "Atividade da fila"}</strong>
          <span className="record-meta">Autor {row.actor_id}</span>
          <span className="record-meta">Versao {row.aggregate_version}</span>
        </div><time className="record-status" dateTime={row.occurred_at}>{new Date(row.occurred_at).toLocaleString("pt-BR")}</time>
      </li>)}</ul> : <p>Nenhuma atividade disponivel. Atualize em instantes.</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="atividades" disabled={query.isFetching} />
  </section>;
}

export function QueueDetail({ id, api, session }: { id: string; api: QueueApi; session: WorkspaceSession }) {
  const cache = useQueryClient();
  const mutating = useIsMutating();
  const query = useQuery({ queryKey: ["ticket-queue", id], queryFn: ({ signal }) => api.get(id, signal) });
  const queue = query.data;
  const refresh = async () => {
    await query.refetch({ throwOnError: true });
    await Promise.all([
      cache.invalidateQueries({ queryKey: ["ticket-queues"] }),
      cache.invalidateQueries({ queryKey: ["queue-activity", id] }),
    ]);
  };
  return <div className="admin-workspace">
    <Link className="text-link" href="/service-desk/queues">Voltar as filas</Link>
    {query.isPending && <LoadingRows label="Carregando fila..." />}
    {query.isError && !queue && <h1 id="queue-heading" tabIndex={-1}>Fila indisponivel</h1>}
    {query.isError && <ReadError retry={() => void query.refetch()}>{query.error instanceof ApiError && query.error.status === 404 ? "Esta fila nao esta disponivel para sua conta." : undefined}</ReadError>}
    {queue && <>
      <h1 id="queue-heading" tabIndex={-1}>{queue.name}</h1>
      <p className="admin-intro">{queue.active ? "Fila ativa" : "Fila arquivada"}</p>
      <Link className="text-link" href={`/service-desk/queues/${encodeURIComponent(id)}/members`}>Administrar membros</Link>
      <div className="admin-plane">
        <section className="admin-section" aria-labelledby="queue-data-heading">
          <h2 id="queue-data-heading">Dados da fila</h2>
          <dl className="account-details"><div><dt>Equipe</dt><dd>{queue.team_name}</dd></div></dl>
          {!queue.team_active && <p className="field-help">Equipe arquivada. Os cadastros estao disponiveis para consulta.</p>}
          {!queue.can_manage && <p className="field-help">Acesso somente para consulta.</p>}
          <MetadataEditor record={queue} kind="fila" session={session} writable={queue.can_manage && queue.team_active}
            disabled={query.isFetching || query.isError || mutating > 0}
            update={(body, version) => api.update(id, body, version)} refresh={refresh} />
        </section>
        <QueueCategories id={id} api={api} session={session} writable={queue.can_manage && queue.team_active && queue.active} refresh={refresh} />
        <QueueHistory id={id} api={api} />
      </div>
    </>}
  </div>;
}
