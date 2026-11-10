"use client";

import Link from "next/link";
import { useLayoutEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging, useTeamWrite, writeError } from "@/components/team-admin/common";
import type { WorkspaceSession } from "@/components/workspace-session";
import type { ClientApi, ClientRecord } from "@/lib/clients";
import { createProjectApi } from "@/lib/projects";

export function DefaultProject({ client, api, session }: { client: ClientRecord; api: ClientApi; session: WorkspaceSession }) {
  const cache = useQueryClient();
  const projects = createProjectApi(session.user.csrf_token, session.onAuthError);
  const paging = usePaging();
  const [editing, setEditing] = useState(false);
  const [version, setVersion] = useState(client.version);
  const [selected, setSelected] = useState<{ id: string; name: string } | null>(null);
  const [notice, setNotice] = useState("");
  const selector = useRef<HTMLSelectElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const focusSelection = useRef(false);
  const restoreTrigger = useRef(false);
  const current = useQuery({ queryKey: ["project", client.default_project_id], queryFn: ({ signal }) => projects.get(client.default_project_id!, signal), enabled: !!client.default_project_id });
  const choices = useQuery({ queryKey: ["client-default-projects", client.id, paging.cursor], queryFn: ({ signal }) => projects.forClient(client.id, paging.cursor, signal), enabled: editing });
  useLayoutEffect(() => {
    if (editing && focusSelection.current && !choices.isPending && !choices.isFetching && !choices.isError) {
      selector.current?.focus(); focusSelection.current = false;
    }
    if (!editing && restoreTrigger.current) { trigger.current?.focus(); restoreTrigger.current = false; }
  }, [editing, choices.isPending, choices.isFetching, choices.isError]);
  const write = useTeamWrite(session, (intent: { default_project_id: string | null; version: number }) => api.update(client.id, { default_project_id: intent.default_project_id }, intent.version), result => {
    cache.setQueryData(["client", client.id], result); void cache.invalidateQueries({ queryKey: ["clients"] }); void cache.invalidateQueries({ queryKey: ["client-activity", client.id] });
    setEditing(false); setNotice("Projeto padrao atualizado."); requestAnimationFrame(() => document.getElementById("default-project-heading")?.focus());
  });
  const reload = async () => {
    const fresh = await api.get(client.id); if (!session.isCurrent()) return;
    cache.setQueryData(["client", client.id], fresh); await choices.refetch({ throwOnError: true });
    setEditing(false); setSelected(null); setNotice("");
  };
  const options = choices.data?.items.filter(project => project.active) ?? [];
  const retained = selected && !options.some(project => project.id === selected.id) ? selected : null;
  return <section className="admin-section" aria-labelledby="default-project-heading">
    <h2 id="default-project-heading" tabIndex={-1}>Projeto padrao</h2>
    <p className="field-help">Referencia para futuras tarefas de atendimento. A selecao nao cria tickets nem concede acesso. Projetos arquivados precisam ser revistos antes do uso.</p>
    {!client.default_project_id ? <p>Nenhum projeto padrao definido.</p> : current.isPending ? <LoadingRows label="Carregando projeto padrao..." /> : current.isError ? <ReadError retry={() => void current.refetch()}>Nao foi possivel carregar o projeto padrao. A configuracao foi preservada.</ReadError> : <p><Link className="text-link" href={`/projects/${current.data.id}`}>{current.data.name}</Link>{!current.data.active && " - Projeto arquivado"}</p>}
    {client.can_manage && (editing ? <form onSubmit={event => { event.preventDefault(); if (selected && !choices.isFetching && !choices.isError && !write.locked) write.submit({ default_project_id: selected.id, version }); }}>
      <label htmlFor="default-project">Projeto padrao</label><select id="default-project" ref={selector} value={selected?.id ?? ""} disabled={write.locked || choices.isFetching || choices.isError} onChange={event => { const choice = options.find(project => project.id === event.target.value); setSelected(choice ? { id: choice.id, name: choice.name } : null); }}>
        <option value="">Escolha um projeto ativo deste cliente</option>{options.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}{retained && <option value={retained.id}>{retained.name}</option>}
      </select>
      {choices.isPending ? <LoadingRows label="Carregando projetos..." /> : choices.isError ? <ReadError retry={() => void choices.refetch()} /> : <Paging paging={paging} next={choices.data.next_cursor} label="projetos" disabled={choices.isFetching || write.locked} />}
      <div className="action-row"><Button type="submit" disabled={write.locked || !selected || choices.isFetching || choices.isError}>Salvar projeto padrao</Button><Button type="button" variant="outline" disabled={write.locked} onClick={() => { focusSelection.current = false; restoreTrigger.current = true; setEditing(false); setSelected(null); }}>Cancelar selecao</Button></div>
    </form> : <div className="action-row">
      <Button ref={trigger} variant="outline" disabled={write.locked || !client.active} onClick={() => { focusSelection.current = true; setVersion(client.version); setSelected(null); paging.reset(); setEditing(true); setNotice(""); }}>Alterar projeto padrao</Button>
      {client.default_project_id && <Button variant="outline" disabled={write.locked} onClick={() => write.submit({ default_project_id: null, version: client.version })}>Limpar projeto padrao</Button>}
    </div>)}
    {notice && <p role="status" className="read-notice">{notice}</p>}
    {write.error && <div className="read-error"><p role="alert">{writeError(write.error)}</p><Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(reload)}>Recarregar projeto padrao</Button></div>}
    {write.reloadFailed && <p role="alert">Nao foi possivel atualizar. A selecao continua bloqueada.</p>}
  </section>;
}
