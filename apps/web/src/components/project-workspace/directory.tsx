"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, Paging, ReadError, nameSchema, usePaging, useTeamWrite, writeError } from "@/components/team-admin/common";
import { createClientApi } from "@/lib/clients";
import { createTeamApi } from "@/lib/teams";
import type { ProjectApi, ProjectCreate } from "@/lib/projects";
import { RecordPicker, type Choice } from "./picker";

function ProjectProvisioning({ api, session }: { api: ProjectApi; session: WorkspaceSession }) {
  const admin = session.user.capabilities.includes("identity.manage");
  const teamApi = createTeamApi(session.user.csrf_token, session.onAuthError);
  const clientApi = createClientApi(session.user.csrf_token, session.onAuthError);
  const teamsPaging = usePaging(), clientsPaging = usePaging(), areasPaging = usePaging(), peoplePaging = usePaging();
  const teams = useQuery({ queryKey: ["project-team-choices", teamsPaging.cursor], queryFn: ({ signal }) => teamApi.list(teamsPaging.cursor, signal) });
  const clients = useQuery({ queryKey: ["project-client-choices", clientsPaging.cursor], queryFn: ({ signal }) => clientApi.list(clientsPaging.cursor, signal) });
  const areas = useQuery({ queryKey: ["project-area-choices", areasPaging.cursor], queryFn: ({ signal }) => api.areas(areasPaging.cursor, signal) });
  const people = useQuery({ queryKey: ["project-manager-choices", peoplePaging.cursor], queryFn: ({ signal }) => teamApi.users(peoplePaging.cursor, signal), enabled: admin });
  const [kind, setKind] = useState<"internal" | "client">(admin ? "internal" : "client");
  const [team, setTeam] = useState<Choice | null>(null), [client, setClient] = useState<Choice | null>(null), [area, setArea] = useState<Choice | null>(null), [manager, setManager] = useState<Choice | null>(null);
  const [notice, setNotice] = useState(""), [selectionError, setSelectionError] = useState("");
  const form = useForm<{ name: string }>({ resolver: zodResolver(nameSchema), defaultValues: { name: "" } });
  const write = useTeamWrite(session, ({ key, ...body }: ProjectCreate & { key: string }) => api.create(body, key), receipt => {
    form.reset(); setManager(null); setNotice("Projeto cadastrado para o gestor escolhido. Ele precisará entrar novamente para usar o novo acesso.");
    if (receipt.manager_user_id === session.user.id) session.onRefresh();
  });
  const reload = async () => { await Promise.all([teams.refetch({ throwOnError: true }), clients.refetch({ throwOnError: true }), areas.refetch({ throwOnError: true }), ...(admin ? [people.refetch({ throwOnError: true })] : [])]); };
  const common = { disabled: write.locked };
  return <section className="admin-section" aria-labelledby="new-project-heading"><h2 id="new-project-heading">Novo projeto</h2>
    <p className="field-help">Selecione a equipe e o gestor inicial. Projetos de cliente exigem acesso prévio ao cliente; a equipe não concede esse acesso.</p>
    <form noValidate onSubmit={form.handleSubmit(value => {
      if (!team || !manager || (kind === "client" && !client)) { setSelectionError("Escolha a equipe, o gestor e, se aplicável, o cliente."); return; }
      setSelectionError(""); setNotice(""); write.submit({ name: value.name, scope_kind: kind, team_id: team.id, client_id: kind === "client" ? client!.id : null, operational_area_id: area?.id ?? null, manager_user_id: manager.id, key: crypto.randomUUID() });
    })}>
      <div className="account-form-grid">
        <div><label htmlFor="new-project-name">Nome do projeto</label><input id="new-project-name" maxLength={300} {...form.register("name")} disabled={write.locked} aria-invalid={!!form.formState.errors.name} aria-describedby="project-name-error" /><p id="project-name-error" className="field-error">{form.formState.errors.name?.message}</p></div>
        {admin ? <div><label htmlFor="project-scope">Tipo de projeto</label><select id="project-scope" value={kind} disabled={write.locked} onChange={event => setKind(event.target.value as "internal" | "client")}><option value="internal">Interno</option><option value="client">De cliente</option></select><p className="field-help">O cliente e a equipe não poderão ser trocados depois do cadastro.</p></div> : <p className="field-help">Cadastre para um cliente que você gerencia e uma equipe disponível para sua conta.</p>}
        {kind === "client" && <RecordPicker {...common} id="project-client" label="Cliente do projeto" value={client} onChange={setClient} choices={clients.data?.items.filter(row => row.active && (admin || row.can_manage)).map(row => ({ id: row.id, label: row.name })) ?? []} paging={clientsPaging} next={clients.data?.next_cursor} pending={clients.isPending} failed={clients.isError} retry={() => void clients.refetch()} />}
        <RecordPicker {...common} id="project-team" label="Equipe responsável" value={team} onChange={setTeam} choices={teams.data?.items.filter(row => row.active).map(row => ({ id: row.id, label: row.name })) ?? []} paging={teamsPaging} next={teams.data?.next_cursor} pending={teams.isPending} failed={teams.isError} retry={() => void teams.refetch()} />
        <RecordPicker {...common} id="project-area" label="Área do projeto" value={area} onChange={setArea} choices={areas.data?.items.filter(row => row.active).map(row => ({ id: row.id, label: row.name })) ?? []} paging={areasPaging} next={areas.data?.next_cursor} pending={areas.isPending} failed={areas.isError} retry={() => void areas.refetch()} empty="Sem área" />
        <RecordPicker {...common} id="project-manager" label="Gestor inicial" value={manager} onChange={setManager} choices={[{ id: session.user.id, label: `${session.user.display_name} (você)` }, ...(people.data?.items.filter(row => row.active && row.id !== session.user.id).map(row => ({ id: row.id, label: `${row.display_name} - ${row.email}` })) ?? [])]} paging={peoplePaging} next={people.data?.next_cursor} pending={admin && people.isPending} failed={admin && people.isError} retry={() => void people.refetch()} />
      </div>
      <p className="field-help">Escolher você como gestor encerrará sua sessão após o cadastro. Cadastrar para outra pessoa não concede acesso automático à sua conta.</p>
      {selectionError && <p role="alert" className="field-error">{selectionError}</p>}
      <Button type="submit" className="client-create-action" disabled={write.locked}>{write.pending ? "Cadastrando..." : "Cadastrar projeto"}</Button>
    </form>
    {notice && <p role="status" className="read-notice">{notice}</p>}
    {write.error && <div className="read-error"><p role="alert">{writeError(write.error)}</p>{write.uncertain ? <Button variant="outline" disabled={write.pending} onClick={write.verify}>Verificar cadastro</Button> : write.locked && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(reload)}>Recarregar opções</Button>}</div>}
    {write.reloadFailed && <p role="alert" className="error-message">Não foi possível atualizar. O cadastro continua bloqueado.</p>}
  </section>;
}

export function ProjectDirectory({ api, session }: { api: ProjectApi; session: WorkspaceSession }) {
  const paging = usePaging();
  // Keep authority observed across independent list cursors. On page one this
  // shares the same query/cache and request; session ownership stays unchanged.
  const authority = useQuery({ queryKey: ["projects", null], queryFn: ({ signal }) => api.list(null, signal) });
  const query = useQuery({ queryKey: ["projects", paging.cursor], queryFn: ({ signal }) => api.list(paging.cursor, signal) });
  const mayCreate = authority.data?.can_create && query.data?.can_create !== false;
  return <div className="admin-workspace"><Link className="text-link" href="/">Voltar à minha conta</Link>
    <h1 id="projects-heading" tabIndex={-1}>Projetos</h1><p className="admin-intro">Acompanhe os projetos liberados para sua conta. Projetos internos têm acesso próprio; projetos de cliente mantêm as permissões desse cliente.</p>
    <p><Link className="text-link" href="/operational-areas">Áreas operacionais</Link></p>
    <div className="admin-plane">
      <section className="admin-section" aria-labelledby="project-list-heading"><h2 id="project-list-heading">Projetos disponíveis</h2>
        <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar projetos</Button>
        {query.isPending ? <LoadingRows label="Carregando projetos..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ?
          <ul className="record-list" aria-label="Projetos disponíveis">{query.data.items.map(row => <li className="team-row" key={row.id}><div className="record-text"><Link className="text-link" href={`/projects/${encodeURIComponent(row.id)}`}>{row.name}</Link><span className="record-meta">{row.scope_kind === "internal" ? "Interno" : "De cliente"} · {row.can_manage ? "Gestão do projeto" : "Somente consulta"}</span></div><span className="record-status" data-state={row.active ? "active" : "inactive"}>{row.active ? "Ativo" : "Arquivado"}</span></li>)}</ul> : <p>Nenhum projeto disponível nesta página.</p>}
        <Paging paging={paging} next={query.data?.next_cursor} label="projetos" disabled={query.isFetching} />
      </section>
      {mayCreate && <ProjectProvisioning api={api} session={session} />}
    </div>
  </div>;
}
