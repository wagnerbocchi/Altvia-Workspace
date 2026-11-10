"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, Paging, ReadError, usePaging, useTeamWrite, writeError } from "@/components/team-admin/common";
import type { MilestoneCreate, MilestonePatch, MilestoneRecord, ProjectApi } from "@/lib/projects";
import { dueLabel } from "@/lib/work-items";
import { ApiError } from "@/lib/http";
import { MilestoneForm } from "./milestone-form";
const states = { planned: "Marco planejado", done: "Marco concluido", cancelled: "Marco cancelado" };
const failure = (error: unknown) => error instanceof ApiError && error.code === "project_inactive" ? "Projeto, equipe ou cliente arquivado. Restaure a referencia antes de alterar este marco." : writeError(error);

export function MilestoneDirectory({ id, api, session }: { id: string; api: ProjectApi; session: WorkspaceSession }) {
  const router = useRouter(); const cache = useQueryClient();
  const parent = useQuery({ queryKey: ["project", id], queryFn: ({ signal }) => api.get(id, signal) });
  const paging = usePaging();
  const query = useQuery({ queryKey: ["project-milestones", id, paging.cursor], queryFn: ({ signal }) => api.milestones(id, paging.cursor, signal) });
  const [creating, setCreating] = useState(false);
  const write = useTeamWrite(session, (value: MilestoneCreate & { key: string }) => { const { key, ...body } = value; return api.createMilestone(id, body, key); }, receipt => {
    for (const key of [["project", id], ["projects"], ["project-activity", id], ["project-milestones", id]]) void cache.invalidateQueries({ queryKey: key });
    router.push(`/projects/${id}/milestones/${receipt.milestone_id}`);
  });
  const refresh = async () => { await Promise.all([parent.refetch({ throwOnError: true }), query.refetch({ throwOnError: true })]); };
  const allowed = parent.isSuccess && parent.data.can_manage;
  const blocked = !allowed || !query.isSuccess || !query.data.project_writable || parent.isFetching || query.isFetching || write.locked;
  return <div className="admin-workspace milestone-workspace"><Link className="text-link" href={`/projects/${id}`}>Voltar ao projeto</Link>
    <h1 id="milestones-heading" tabIndex={-1}>Marcos do projeto</h1><p className="admin-intro">Registre entregas e acompanhe seus estados. Marcos e tarefas mantem ciclos independentes.</p>
    {parent.isPending ? <LoadingRows label="Carregando projeto..." /> : parent.isError ? <ReadError retry={() => void refresh().catch(() => {})}>Este projeto nao esta disponivel para sua conta.</ReadError> : <p>{parent.data.name}</p>}
    <div className="admin-plane"><section className="admin-section" aria-labelledby="milestone-list-heading"><h2 id="milestone-list-heading">Entregas planejadas</h2>
      <Button variant="outline" disabled={parent.isFetching || query.isFetching} onClick={() => void refresh().catch(() => {})}>Atualizar marcos</Button>
      {query.isPending ? <LoadingRows label="Carregando marcos..." /> : query.isError ? <ReadError retry={() => void refresh().catch(() => {})} /> : !parent.isSuccess ? null : query.data.items.length ? <ul className="record-list" aria-label="Marcos do projeto">{query.data.items.map(row => <li className="member-row" key={row.id}><div className="record-text"><Link className="text-link" href={`/projects/${id}/milestones/${row.id}`}>{row.title}</Link><span className="record-meta">{dueLabel(row)}</span></div><span className="record-status">{states[row.state]}</span></li>)}</ul> : <p>Nenhum marco nesta pagina.</p>}
      <Paging paging={paging} next={query.data?.next_cursor} label="marcos" disabled={query.isFetching} />
    </section><section className="admin-section" aria-labelledby="milestone-create-heading"><h2 id="milestone-create-heading">Cadastro de marco</h2>
      {parent.isSuccess && !allowed && <p>Acesso somente para consulta.</p>}
      {query.isSuccess && !query.data.project_writable && <p>Projeto, equipe ou cliente arquivado. Novos marcos e alteracoes estao bloqueados.</p>}
      {creating ? <MilestoneForm disabled={blocked} cancelDisabled={write.locked} onSubmit={value => { if (!blocked && value.title) write.submit({ ...value, title: value.title, key: crypto.randomUUID() }); }} cancel={() => { setCreating(false); requestAnimationFrame(() => document.getElementById("new-milestone")?.focus()); }} /> : allowed && <Button id="new-milestone" disabled={blocked} onClick={() => setCreating(true)}>Novo marco</Button>}
      {write.error && <div className="read-error"><p role="alert">{failure(write.error)}</p>{write.uncertain ? <Button variant="outline" disabled={write.pending || write.reloading} onClick={write.verify}>Verificar cadastro do marco</Button> : write.locked && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(refresh)}>Recarregar para revisar cadastro</Button>}</div>}
      {write.reloadFailed && <p role="alert">Nao foi possivel atualizar. O cadastro original continua bloqueado.</p>}
    </section></div>
  </div>;
}

export function MilestoneDetail({ id, milestoneId, api, session }: { id: string; milestoneId: string; api: ProjectApi; session: WorkspaceSession }) {
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ["project-milestone", id, milestoneId], queryFn: ({ signal }) => api.milestone(id, milestoneId, signal) });
  const [edit, setEdit] = useState<MilestoneRecord | null>(null);
  const [confirm, setConfirm] = useState<{ state: "planned" | "cancelled"; version: number } | null>(null);
  const [notice, setNotice] = useState(""); const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (confirm) heading.current?.focus(); }, [confirm]);
  const close = () => { setEdit(null); setConfirm(null); requestAnimationFrame(() => document.getElementById("milestone-heading")?.focus()); };
  const write = useTeamWrite(session, ({ version, ...body }: MilestonePatch & { version: number }) => api.updateMilestone(id, milestoneId, body, version), result => {
    cache.setQueryData(["project-milestone", id, milestoneId], result);
    for (const key of [["project-milestones", id], ["project", id], ["projects"], ["project-activity", id]]) void cache.invalidateQueries({ queryKey: key });
    close(); setNotice("Alteracao confirmada.");
  });
  const refresh = async () => { await query.refetch({ throwOnError: true }); if (session.isCurrent()) { close(); setNotice(""); } };
  const row = query.data;
  const blocked = !query.isSuccess || query.isFetching || !row?.can_manage || !row.project_writable || write.locked;
  return <div className="admin-workspace milestone-workspace"><Link className="text-link" href={`/projects/${id}/milestones`}>Voltar aos marcos</Link>
    <h1 id="milestone-heading" tabIndex={-1}>{query.isSuccess ? row?.title : "Marco indisponivel"}</h1>
    {query.isPending ? <LoadingRows label="Carregando marco..." /> : query.isError ? <ReadError retry={() => void query.refetch()}>Este marco nao esta disponivel para sua conta.</ReadError> : row && <>
      <p className="admin-intro">{states[row.state]}</p><p>{dueLabel(row)}</p>
      {notice && <p role="status" className="read-notice">{notice}</p>}
    </>}
    {write.error && <div className="read-error"><p role="alert">{failure(write.error)}</p><Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(refresh)}>Recarregar e descartar edicao</Button></div>}
    {write.reloadFailed && <p role="alert">Nao foi possivel atualizar. A edicao continua bloqueada.</p>}
    <div className="admin-plane"><section className="admin-section" aria-labelledby="milestone-data-heading"><h2 id="milestone-data-heading">Dados do marco</h2>
      {query.isSuccess && !row?.can_manage && <p>Acesso somente para consulta.</p>}
      {row && !row.project_writable && <p>Projeto, equipe ou cliente arquivado. As alteracoes estao bloqueadas.</p>}
      {edit ? <MilestoneForm key={edit.id + ":" + edit.version} initial={edit} disabled={blocked} cancelDisabled={write.locked} onSubmit={value => { if (!blocked) write.submit({ ...value, version: edit.version }); }} cancel={close} /> : query.isSuccess && row?.can_manage && !confirm && <div className="action-row">
        <Button variant="outline" disabled={blocked} onClick={() => { setEdit({ ...row }); setNotice(""); }}>Editar marco</Button>
        {row.state === "planned" ? <><Button disabled={blocked} onClick={() => write.submit({ state: "done", version: row.version })}>Concluir marco</Button><Button variant="outline" disabled={blocked} onClick={() => setConfirm({ state: "cancelled", version: row.version })}>Cancelar marco</Button></> : <Button variant="outline" disabled={blocked} onClick={() => setConfirm({ state: "planned", version: row.version })}>Reabrir marco</Button>}
      </div>}
      {confirm && <div className="confirmation" role="group" aria-labelledby="milestone-confirm-heading"><h3 id="milestone-confirm-heading" ref={heading} tabIndex={-1}>{confirm.state === "planned" ? "Reabrir este marco?" : "Cancelar este marco?"}</h3><p>O historico sera preservado. As tarefas do projeto permanecem independentes.</p><div className="action-row add-member-action"><Button disabled={blocked} onClick={() => write.submit({ state: confirm.state, version: confirm.version })}>{confirm.state === "planned" ? "Confirmar reabertura" : "Confirmar cancelamento"}</Button><Button variant="outline" disabled={write.locked} onClick={close}>Manter estado atual</Button></div></div>}
    </section></div>
  </div>;
}
