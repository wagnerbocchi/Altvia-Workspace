"use client";

import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import type { ProjectApi } from "@/lib/projects";

export function ProjectMembers({ id, api }: { id: string; api: ProjectApi }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["project-members", id, paging.cursor], queryFn: ({ signal }) => api.members(id, paging.cursor, signal) });
  const roles: Record<string, string> = { project_manager: "Gestor do projeto", viewer: "Consulta", agent: "Colaborador" };
  return <section className="admin-section" aria-labelledby="project-members-heading"><h2 id="project-members-heading">Participantes do projeto</h2>
    {query.isPending ? <LoadingRows label="Carregando participantes..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ? <ul className="record-list" aria-label="Participantes do projeto">{query.data.items.map(row => <li className="team-row" key={row.id}><div className="record-text"><strong>{row.display_name}</strong><span className="record-meta">{roles[row.role_name] ?? "Acesso do projeto"}</span></div><span className="record-status" data-state={row.active ? "active" : "inactive"}>{row.active ? "Conta ativa" : "Conta desativada"}</span></li>)}</ul> : <p>Nenhum participante nesta página.</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="participantes do projeto" disabled={query.isFetching} />
  </section>;
}
export function ProjectHistory({ id, api }: { id: string; api: ProjectApi }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["project-activity", id, paging.cursor], queryFn: ({ signal }) => api.activity(id, paging.cursor, signal) });
  const labels: Record<string, string> = { "project.created": "Projeto cadastrado", "project.updated": "Projeto atualizado", "project.access_changed": "Acesso ao projeto alterado", "project.milestone_created": "Marco cadastrado", "project.milestone_updated": "Marco atualizado" };
  return <section className="admin-section" aria-labelledby="project-history-heading"><h2 id="project-history-heading">Histórico do projeto</h2>
    <p className="field-help">Alterações deste projeto, da mais recente à mais antiga. Os horários seguem o seu dispositivo.</p>
    <Button variant="outline" disabled={query.isFetching} onClick={() => { paging.reset(); void query.refetch(); }}>Atualizar histórico</Button>
    {query.isPending ? <LoadingRows label="Carregando histórico..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ? <ul className="record-list" aria-label="Histórico do projeto">{query.data.items.map(row => <li className="team-row" key={row.event_id}><div className="record-text"><strong>{labels[row.event_type] ?? "Atividade do projeto"}</strong><span className="record-meta">{row.actor_kind === "management_command" ? "Comando administrativo" : `Autor: ${row.actor_id}`}</span><span className="record-meta">Correlação: {row.correlation_id}</span></div><time className="record-status" dateTime={row.occurred_at}>{new Date(row.occurred_at).toLocaleString("pt-BR")}</time></li>)}</ul> : <p>Nenhuma atividade disponível. Atualize em instantes.</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="atividades" disabled={query.isFetching} />
  </section>;
}
