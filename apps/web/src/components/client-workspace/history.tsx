"use client";

import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import type { ClientApi } from "@/lib/clients";

const actions: Record<string, string> = { "client.created": "Cliente cadastrado", "client.updated": "Cadastro atualizado", "client.access_changed": "Acesso ao cliente alterado", "client.contact_created": "Contato cadastrado", "client.contact_updated": "Contato atualizado" };

export function ClientHistory({ id, api }: { id: string; api: ClientApi }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["client-activity", id, paging.cursor], queryFn: ({ signal }) => api.activity(id, paging.cursor, signal) });
  return <section className="admin-section" aria-labelledby="client-history-heading">
    <h2 id="client-history-heading">Histórico do cliente</h2>
    <p className="field-help">Alterações deste cliente, da mais recente à mais antiga. Os horários seguem o seu dispositivo.</p>
    <Button variant="outline" disabled={query.isFetching} onClick={() => { paging.reset(); void query.refetch(); }}>Atualizar histórico</Button>
    {query.isPending ? <LoadingRows label="Carregando histórico..." /> : query.isError ? <ReadError retry={() => void query.refetch()} />
      : query.data.items.length ? <ul className="record-list" aria-label="Histórico do cliente">{query.data.items.map(item => <li className="team-row" key={item.event_id}>
        <div className="record-text"><strong>{actions[item.event_type] ?? "Atividade do cliente"}</strong>
          <span className="record-meta">{item.actor_kind === "management_command" ? "Comando administrativo" : `Autor: ${item.actor_id}`}</span>
          {item.details.manager_user_id && <span className="record-meta">Gestor inicial: {item.details.manager_user_id}</span>}
          {item.details.member_user_id && <span className="record-meta">Conta com acesso alterado: {item.details.member_user_id}</span>}
          <span className="record-meta">Correlação: {item.correlation_id}</span></div>
        <time className="record-status" dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString("pt-BR")}</time></li>)}</ul>
        : <p>Nenhuma atividade disponível. Atualize em instantes.</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="atividades" disabled={query.isFetching} />
  </section>;
}
