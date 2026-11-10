"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { WorkspaceSession } from "@/components/workspace-session";
import { ReadError, useTeamWrite } from "@/components/team-admin/common";
import { type WorkApi, type WorkCreate } from "@/lib/work-items";
import { createProjectApi } from "@/lib/projects";
import { WorkForm } from "./form";
import { WriteRecovery } from "./recovery";
import { ProjectDiscovery } from "./discovery";

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
  const cache = useQueryClient();
  const projectApi = createProjectApi(session.user.csrf_token, session.onAuthError);
  const record = useQuery({ queryKey: ["project", project], queryFn: ({ signal }) => projectApi.get(project, signal) });
  // Observe creation authority while the independently paged list recovers.
  const authority = useQuery({ queryKey: ["work-items", project, null], queryFn: ({ signal }) => api.list(project, null, signal) });
  const mayCreate = authority.data?.can_create;
  const refresh = () => { void cache.invalidateQueries({ queryKey: ["work-items", project] }); };
  return <div className="admin-workspace task-discovery-workspace"><div className="action-row"><Link className="text-link" href={`/projects/${encodeURIComponent(project)}`}>Voltar ao projeto</Link><Link className="text-link" href="/my-work">Meu trabalho</Link></div>
    <h1 id="work-list-heading" tabIndex={-1}>Tarefas</h1>
    <p className="admin-intro">{record.data?.name ?? "Trabalho do projeto"}. Responsáveis e envolvidos mantêm as permissões deste projeto.</p>
    {authority.data?.project_writable === false && <p className="notice">O projeto, seu cliente ou sua equipe foi arquivado. As tarefas continuam disponíveis para consulta.</p>}
    <div className="admin-plane"><ProjectDiscovery project={project} api={api} actor={session.user.id} refresh={refresh} />
      {authority.isError && <section className="admin-section" aria-label="Criação de tarefas"><ReadError retry={refresh}>Não foi possível verificar se você pode criar tarefas neste projeto. Tente carregar novamente.</ReadError></section>}
      {mayCreate && <Creation project={project} api={api} session={session} manage={authority.data!.can_manage} writable={authority.data!.project_writable && !authority.isError} />}
    </div>
  </div>;
}
