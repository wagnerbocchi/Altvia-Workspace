"use client";

import { LinkedAttachments } from "@/components/attachments";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import { type WorkApi, workStatuses } from "@/lib/work-items";

export function Comments({ id, api }: { id: string; api: WorkApi }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["work-comments", id, paging.cursor], queryFn: ({ signal }) => api.comments(id, paging.cursor, signal) });
  return <><h3>Comentários registrados</h3><Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar comentários</Button>
    {query.isPending ? <LoadingRows label="Carregando comentários..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ? <ul className="record-list" aria-label="Comentários internos">{query.data.items.map(row => <li className="team-row" key={row.id}><div className="record-text"><p className="work-prose">{row.body}</p><LinkedAttachments files={row.attachments} /><span className="record-meta">Autor: {row.author_id}</span><time className="record-meta" dateTime={row.created_at}>{new Date(row.created_at).toLocaleString("pt-BR")}</time></div></li>)}</ul> : <p>Nenhum comentário nesta página.</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="comentários" disabled={query.isFetching} />
  </>;
}
export function StateHistory({ id, api }: { id: string; api: WorkApi }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["work-states", id, paging.cursor], queryFn: ({ signal }) => api.states(id, paging.cursor, signal) });
  return <section className="admin-section" aria-labelledby="work-states-heading"><h2 id="work-states-heading">Histórico de estados</h2>
    {query.isPending ? <LoadingRows label="Carregando estados..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ? <ul className="record-list" aria-label="Histórico de estados">{query.data.items.map(row => <li className="team-row" key={row.id}><div className="record-text"><strong>{row.from_status ? `${workStatuses[row.from_status]} para ${workStatuses[row.to_status]}` : `Criada: ${workStatuses[row.to_status]}`}</strong>{row.reason && <p className="work-prose">{row.reason}</p>}<span className="record-meta">Autor: {row.actor_id}</span><time className="record-meta" dateTime={row.occurred_at}>{new Date(row.occurred_at).toLocaleString("pt-BR")}</time></div></li>)}</ul> : <p>Nenhuma mudança nesta página.</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="mudanças de estado" disabled={query.isFetching} />
  </section>;
}
export function WorkActivity({ id, api }: { id: string; api: WorkApi }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["work-activity", id, paging.cursor], queryFn: ({ signal }) => api.activity(id, paging.cursor, signal) });
  const labels: Record<string, string> = { "work_item.created": "Tarefa criada", "work_item.updated": "Tarefa editada", "work_item.assigned": "Responsáveis alterados", "work_item.blocked": "Bloqueio registrado", "work_item.completed": "Tarefa concluída", "work_item.status_changed": "Estado alterado", "work_item.commented": "Comentário registrado" };
  const fields: Record<string, string> = { title: "Título", description: "Descrição", priority: "Prioridade", due: "Prazo", parent_id: "Tarefa principal", owner_id: "Responsável", assignee_ids: "Envolvidos", external_participants: "Envolvidos externos", estimated_minutes: "Estimativa" };
  return <section className="admin-section" aria-labelledby="work-activity-heading"><h2 id="work-activity-heading">Atividade da tarefa</h2>
    <p className="field-help">Da mais recente à mais antiga. Novas atividades podem levar instantes para aparecer.</p><Button variant="outline" disabled={query.isFetching} onClick={() => { paging.reset(); void query.refetch(); }}>Atualizar atividade</Button>
    {query.isPending ? <LoadingRows label="Carregando atividade..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ? <ul className="record-list" aria-label="Atividade da tarefa">{query.data.items.map(row => <li className="team-row" key={row.event_id}><div className="record-text"><strong>{labels[row.event_type] ?? "Alteração registrada"}</strong><span className="record-meta">{row.actor_kind === "management_command" ? "Comando administrativo" : `Autor: ${row.actor_id}`}</span>{row.details.changed_fields && <span className="record-meta">Campos alterados: {row.details.changed_fields.split(",").map(field => fields[field] ?? "Outro campo").join(", ")}</span>}<time className="record-meta" dateTime={row.occurred_at}>{new Date(row.occurred_at).toLocaleString("pt-BR")}</time></div></li>)}</ul> : <p>Nenhuma atividade nesta página. Atualize em instantes.</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="atividades" disabled={query.isFetching} />
  </section>;
}
