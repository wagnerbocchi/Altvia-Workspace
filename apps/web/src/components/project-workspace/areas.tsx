"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, Paging, ReadError, nameSchema, usePaging, useTeamWrite, writeError } from "@/components/team-admin/common";
import type { AreaRecord, ProjectApi } from "@/lib/projects";

function AreaRow({ area, api, session, refresh }: { area: AreaRecord; api: ProjectApi; session: WorkspaceSession; refresh: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [snapshot, setSnapshot] = useState(1);
  const [confirm, setConfirm] = useState<number | null>(null);
  const confirmHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (confirm !== null) confirmHeading.current?.focus(); }, [confirm]);
  const form = useForm<{ name: string }>({ resolver: zodResolver(nameSchema), defaultValues: { name: "" } });
  const write = useTeamWrite(session, ({ version, ...body }: { version: number; name?: string; active?: boolean }) => api.updateArea(area.id, body, version), () => {
    setEditing(false); setConfirm(null); void refresh().catch(() => { /* The list renders its read failure independently. */ });
    requestAnimationFrame(() => document.getElementById(`area-${area.id}`)?.focus());
  });
  const reload = async () => { await refresh(); if (session.isCurrent()) { setEditing(false); setConfirm(null); } };
  return <li className="admin-section">
    <h3 id={`area-${area.id}`} tabIndex={-1}>{area.name}</h3>
    <p className="field-help">{area.active ? "Área ativa" : "Área arquivada"}</p>
    {session.user.capabilities.includes("identity.manage") && <>
      {editing ? <form className="inline-form" noValidate onSubmit={form.handleSubmit(value => write.submit({ name: value.name, version: snapshot }))}>
        <div className="form-grow"><label htmlFor={`area-name-${area.id}`}>Nome da área</label><input id={`area-name-${area.id}`} {...form.register("name")} maxLength={300} disabled={write.locked} aria-invalid={!!form.formState.errors.name} aria-describedby={`area-error-${area.id}`} />
          <p id={`area-error-${area.id}`} className="field-error">{form.formState.errors.name?.message}</p></div>
        <Button type="submit" disabled={write.locked}>Salvar nome</Button>
        <Button variant="outline" type="button" disabled={write.locked} onClick={() => setEditing(false)}>Cancelar edição</Button>
      </form> : <div className="action-row">
        <Button variant="outline" disabled={write.locked || confirm !== null} onClick={() => { setSnapshot(area.version); form.reset({ name: area.name }); setEditing(true); }}>Renomear área</Button>
        <Button id={`area-state-${area.id}`} variant="outline" disabled={write.locked || confirm !== null} onClick={() => area.active ? setConfirm(area.version) : write.submit({ active: true, version: area.version })}>{area.active ? "Arquivar área" : "Restaurar área"}</Button>
      </div>}
      {confirm !== null && <div className="confirmation" role="group" aria-labelledby={`area-confirm-${area.id}`}><h4 id={`area-confirm-${area.id}`} ref={confirmHeading} tabIndex={-1}>Arquivar {area.name}?</h4><p>Projetos já classificados manterão essa referência.</p><div className="action-row">
        <Button disabled={write.locked} onClick={() => write.submit({ active: false, version: confirm })}>Confirmar arquivamento</Button>
        <Button variant="outline" disabled={write.locked} onClick={() => { setConfirm(null); requestAnimationFrame(() => document.getElementById(`area-state-${area.id}`)?.focus()); }}>Cancelar</Button></div></div>}
    </>}
    {write.error && <div className="read-error"><p role="alert">{writeError(write.error)}</p><Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(reload)}>Recarregar e descartar edição</Button></div>}
    {write.reloadFailed && <p role="alert" className="error-message">Não foi possível atualizar. A edição continua bloqueada.</p>}
  </li>;
}

export function Areas({ api, session }: { api: ProjectApi; session: WorkspaceSession }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["operational-areas", paging.cursor], queryFn: ({ signal }) => api.areas(paging.cursor, signal) });
  const form = useForm<{ name: string }>({ resolver: zodResolver(nameSchema), defaultValues: { name: "" } });
  const [notice, setNotice] = useState("");
  const refresh = async () => { await query.refetch({ throwOnError: true }); };
  const write = useTeamWrite(session, (intent: { name: string; key: string }) => api.createArea(intent.name, intent.key), () => { form.reset(); setNotice("Área cadastrada."); paging.reset(); void query.refetch(); });
  return <div className="admin-workspace"><Link className="text-link" href="/projects">Voltar aos projetos</Link>
    <h1 id="areas-heading" tabIndex={-1}>Áreas operacionais</h1>
    <p className="admin-intro">Classifique projetos por área. Essa classificação não concede acesso a clientes ou projetos.</p>
    <div className="admin-plane">
      {session.user.capabilities.includes("identity.manage") && <section className="admin-section" aria-labelledby="new-area-heading"><h2 id="new-area-heading">Nova área</h2>
        <form noValidate className="inline-form" onSubmit={form.handleSubmit(value => { setNotice(""); write.submit({ name: value.name, key: crypto.randomUUID() }); })}>
          <div className="form-grow"><label htmlFor="new-area-name">Nome da nova área</label><input id="new-area-name" maxLength={300} {...form.register("name")} disabled={write.locked} aria-invalid={!!form.formState.errors.name} aria-describedby="area-create-error" /><p id="area-create-error" className="field-error">{form.formState.errors.name?.message}</p></div>
          <Button type="submit" disabled={write.locked}>{write.pending ? "Cadastrando..." : "Cadastrar área"}</Button>
        </form>
        {notice && <p role="status" className="read-notice">{notice}</p>}
        {write.error && <div className="read-error"><p role="alert">{writeError(write.error)}</p>{write.uncertain ? <Button variant="outline" disabled={write.pending} onClick={write.verify}>Verificar cadastro</Button>
          : write.locked && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(refresh)}>Recarregar áreas</Button>}</div>}
        {write.reloadFailed && <p role="alert" className="error-message">Não foi possível atualizar. O cadastro continua bloqueado.</p>}
      </section>}
      <section className="admin-section" aria-labelledby="area-list-heading"><h2 id="area-list-heading">Áreas cadastradas</h2>
        {query.isPending ? <LoadingRows label="Carregando áreas..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ?
          <ul className="record-list" aria-label="Áreas cadastradas">{query.data.items.map(area => <AreaRow key={area.id} area={area} api={api} session={session} refresh={refresh} />)}</ul> : <p>Nenhuma área nesta página.</p>}
        <Paging paging={paging} next={query.data?.next_cursor} label="áreas" disabled={query.isFetching} />
      </section>
    </div>
  </div>;
}
