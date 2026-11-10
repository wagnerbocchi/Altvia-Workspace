"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, ReadError, nameSchema, usePaging, useTeamWrite, writeError } from "@/components/team-admin/common";
import type { ProjectApi, ProjectPatch } from "@/lib/projects";
import { ApiError } from "@/lib/http";
import { RecordPicker, type Choice } from "./picker";
import { ProjectHistory, ProjectMembers } from "./reads";

export function ProjectDetail({ id, api, session }: { id: string; api: ProjectApi; session: WorkspaceSession }) {
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ["project", id], queryFn: ({ signal }) => api.get(id, signal) });
  const project = query.data;
  const [editor, setEditor] = useState<"name" | "area" | null>(null), [editVersion, setEditVersion] = useState(1);
  const [confirmation, setConfirmation] = useState<number | null>(null), [notice, setNotice] = useState("");
  const [area, setArea] = useState<Choice | null>(null);
  const areaPaging = usePaging();
  const areas = useQuery({ queryKey: ["project-area-choices", areaPaging.cursor], queryFn: ({ signal }) => api.areas(areaPaging.cursor, signal), enabled: editor === "area" });
  const confirmHeading = useRef<HTMLHeadingElement>(null);
  const form = useForm<{ name: string }>({ resolver: zodResolver(nameSchema), defaultValues: { name: "" } });
  const write = useTeamWrite(session, ({ version, ...body }: ProjectPatch & { version: number }) => api.update(id, body, version), result => {
    cache.setQueryData(["project", id], result); void cache.invalidateQueries({ queryKey: ["projects"] });
    setEditor(null); setConfirmation(null); setNotice("Alteração confirmada.");
    requestAnimationFrame(() => document.getElementById("project-heading")?.focus());
  });
  useEffect(() => { if (confirmation !== null) confirmHeading.current?.focus(); }, [confirmation]);
  const reload = async () => { await query.refetch({ throwOnError: true }); if (session.isCurrent()) { setEditor(null); setConfirmation(null); setNotice(""); } };
  const cancel = () => { setEditor(null); requestAnimationFrame(() => document.getElementById("rename-project")?.focus()); };
  const blocked = write.locked || query.isFetching || query.isError;
  return <div className="admin-workspace"><Link className="text-link" href="/projects">Voltar aos projetos</Link>
    {query.isPending ? <LoadingRows label="Carregando projeto..." /> : query.isError ? <><h1 id="project-heading" tabIndex={-1}>Projeto indisponível</h1><ReadError retry={() => void query.refetch()}>{query.error instanceof ApiError && query.error.status === 404 ? "Este projeto não está disponível para sua conta." : undefined}</ReadError></> : project && <>
      <h1 id="project-heading" tabIndex={-1}>{project.name}</h1><p className="admin-intro">{project.active ? "Projeto ativo" : "Projeto arquivado"}</p>
      {notice && <p role="status" className="read-notice">{notice}</p>}
      {write.error && <div className="read-error"><p role="alert">{writeError(write.error)}</p><Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(reload)}>Recarregar e descartar edição</Button></div>}
      {write.reloadFailed && <p role="alert" className="error-message">Não foi possível atualizar. A edição continua bloqueada.</p>}
      <div className="admin-plane"><section className="admin-section" aria-labelledby="project-data-heading"><h2 id="project-data-heading">Dados do projeto</h2>
        <div className="record-text"><span>{project.scope_kind === "internal" ? "Projeto interno" : "Projeto de cliente"}</span>
          {project.client_id && <span className="record-meta">Cliente: {project.client_id}</span>}
          <span className="record-meta">Equipe: {project.team_id}</span><span className="record-meta">{project.operational_area_id ? `Área: ${project.operational_area_name}` : "Sem área operacional"}</span></div>
        {!project.can_manage ? <p>Acesso somente para consulta.</p> : editor === "name" ? <form noValidate className="inline-form" onSubmit={form.handleSubmit(value => write.submit({ name: value.name, version: editVersion }))}>
          <div className="form-grow"><label htmlFor="project-name">Nome do projeto</label><input id="project-name" {...form.register("name")} maxLength={300} disabled={write.locked} aria-invalid={!!form.formState.errors.name} aria-describedby="rename-project-error" /><p id="rename-project-error" className="field-error">{form.formState.errors.name?.message}</p></div>
          <Button type="submit" disabled={blocked}>Salvar nome</Button><Button variant="outline" type="button" disabled={write.locked} onClick={cancel}>Cancelar edição</Button>
        </form> : editor === "area" ? <div className="confirmation">
          <RecordPicker id="edit-project-area" label="Área do projeto" empty="Sem área" value={area} onChange={setArea} choices={areas.data?.items.filter(row => row.active).map(row => ({ id: row.id, label: row.name })) ?? []} paging={areaPaging} next={areas.data?.next_cursor} pending={areas.isPending} failed={areas.isError} retry={() => void areas.refetch()} disabled={write.locked} />
          <div className="action-row"><Button disabled={blocked} onClick={() => write.submit({ operational_area_id: area?.id ?? null, version: editVersion })}>Salvar área</Button><Button variant="outline" disabled={write.locked} onClick={cancel}>Cancelar edição</Button></div>
        </div> : <div className="action-row client-create-action">
          <Button id="rename-project" variant="outline" disabled={blocked || confirmation !== null} onClick={() => { form.reset({ name: project.name }); setEditVersion(project.version); setEditor("name"); setNotice(""); }}>Renomear projeto</Button>
          <Button variant="outline" disabled={blocked || confirmation !== null} onClick={() => { setEditVersion(project.version); setArea(project.operational_area_id ? { id: project.operational_area_id, label: project.operational_area_name ?? "Área atual" } : null); setEditor("area"); setNotice(""); }}>Alterar área</Button>
          <Button id="project-state" variant="outline" disabled={blocked || confirmation !== null} onClick={() => { setNotice(""); if (project.active) setConfirmation(project.version); else write.submit({ active: true, version: project.version }); }}>{project.active ? "Arquivar projeto" : "Restaurar projeto"}</Button>
        </div>}
        {confirmation !== null && <div className="confirmation" role="group" aria-labelledby="archive-project-heading"><h3 id="archive-project-heading" tabIndex={-1} ref={confirmHeading}>Arquivar este projeto?</h3><p>O projeto {project.name} continuará no histórico e poderá ser restaurado.</p><div className="action-row"><Button disabled={blocked} onClick={() => write.submit({ active: false, version: confirmation })}>Confirmar arquivamento</Button><Button variant="outline" disabled={write.locked} onClick={() => { setConfirmation(null); requestAnimationFrame(() => document.getElementById("project-state")?.focus()); }}>Cancelar</Button></div></div>}
      </section><ProjectMembers id={id} api={api} /><ProjectHistory id={id} api={api} /></div>
    </>}
  </div>;
}
