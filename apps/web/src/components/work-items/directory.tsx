"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, Paging, ReadError, usePaging, useTeamWrite } from "@/components/team-admin/common";
import { type WorkApi, type WorkCreate, dueLabel, workPriorities, workStatuses } from "@/lib/work-items";
import { createProjectApi } from "@/lib/projects";
import { WorkForm } from "./form";
import { WriteRecovery } from "./recovery";

function Creation({ project, api, session, manage, writable }: { project: string; api: WorkApi; session: WorkspaceSession; manage: boolean; writable: boolean }) {
  const router = useRouter(), cache = useQueryClient();
  const write = useTeamWrite(session, ({ key, ...body }: WorkCreate & { key: string }) => api.create(body, key), result => {
    void cache.invalidateQueries({ queryKey: ["work-items", project] });
    router.push(`/work-items/${encodeURIComponent(result.work_item_id)}`);
  });
  return <section className="admin-section" aria-labelledby="new-work-heading"><h2 id="new-work-heading">Nova tarefa</h2>
    <WorkForm api={api} project={project} actor={session.user} manage={manage} locked={write.locked || !writable}
      onSubmit={body => write.submit({ ...body, project_id: project, key: crypto.randomUUID() } as WorkCreate & { key: string })} />
    <WriteRecovery write={write} verifyLabel="Verificar criação" reload={async () => { await Promise.all(["work-items", "work-candidates"].map(key => cache.refetchQueries({ queryKey: [key, project], type: "active" }, { throwOnError: true }))); }} />
  </section>;
}
export function WorkDirectory({ project, api, session }: { project: string; api: WorkApi; session: WorkspaceSession }) {
  const paging = usePaging();
  const projectApi = createProjectApi(session.user.csrf_token, session.onAuthError);
  const record = useQuery({ queryKey: ["project", project], queryFn: ({ signal }) => projectApi.get(project, signal) });
  // Observe creation authority while the independently paged list recovers.
  const authority = useQuery({ queryKey: ["work-items", project, null], queryFn: ({ signal }) => api.list(project, null, signal) });
  const query = useQuery({ queryKey: ["work-items", project, paging.cursor], queryFn: ({ signal }) => api.list(project, paging.cursor, signal) });
  const mayCreate = authority.data?.can_create && query.data?.can_create !== false;
  return <div className="admin-workspace"><Link className="text-link" href={`/projects/${encodeURIComponent(project)}`}>Voltar ao projeto</Link>
    <h1 id="work-list-heading" tabIndex={-1}>Tarefas</h1>
    <p className="admin-intro">{record.data?.name ?? "Trabalho do projeto"}. Responsáveis e envolvidos mantêm as permissões deste projeto.</p>
    {authority.data?.project_writable === false && <p className="notice">O projeto, seu cliente ou sua equipe foi arquivado. As tarefas continuam disponíveis para consulta.</p>}
    <div className="admin-plane">{mayCreate && <Creation project={project} api={api} session={session} manage={authority.data!.can_manage} writable={authority.data!.project_writable && query.data?.project_writable !== false} />}
      <section className="admin-section" aria-labelledby="work-directory-heading"><h2 id="work-directory-heading">Tarefas do projeto</h2>
        <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar tarefas</Button>
        {query.isPending ? <LoadingRows label="Carregando tarefas..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ?
          <ul className="record-list" aria-label="Tarefas do projeto">{query.data.items.map(row => <li className="team-row" key={row.id}><div className="record-text"><Link className="text-link" href={`/work-items/${encodeURIComponent(row.id)}`}>{row.title}</Link><span className="record-meta">{workStatuses[row.status]} · Prioridade {workPriorities[row.priority].toLocaleLowerCase("pt-BR")}{row.parent_id ? " · Subtarefa" : ""}</span><span className="record-meta">{row.owner_name ?? "Sem responsável"} · {dueLabel(row)}</span></div></li>)}</ul> : <p>Nenhuma tarefa nesta página.</p>}
        <Paging paging={paging} next={query.data?.next_cursor} label="tarefas" disabled={query.isFetching} />
      </section>
    </div>
  </div>;
}
