"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { WorkspaceSession } from "@/components/workspace-session";
import { Button } from "@/components/ui/button";
import { LoadingRows, ReadError, nameSchema, useTeamWrite, writeError } from "@/components/team-admin/common";
import { ApiError } from "@/lib/http";
import type { ClientApi } from "@/lib/clients";
import { ClientHistory } from "./history";

type Intent = { version: number } & ({ name: string } | { active: boolean });

export function ClientDetail({ id, api, session }: { id: string; api: ClientApi; session: WorkspaceSession }) {
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ["client", id], queryFn: ({ signal }) => api.get(id, signal) });
  const client = query.data;
  const [editing, setEditing] = useState(false);
  const [editVersion, setEditVersion] = useState(1);
  const [confirmVersion, setConfirmVersion] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const confirmHeading = useRef<HTMLHeadingElement>(null);
  const form = useForm<{ name: string }>({ resolver: zodResolver(nameSchema), defaultValues: { name: "" } });
  const write = useTeamWrite(session, (intent: Intent) => {
    const { version, ...body } = intent; return api.update(id, body, version);
  }, result => {
    cache.setQueryData(["client", id], result); void cache.invalidateQueries({ queryKey: ["clients"] });
    setEditing(false); setConfirmVersion(null); setNotice("Alteração confirmada.");
    requestAnimationFrame(() => document.getElementById("client-heading")?.focus());
  });
  useEffect(() => { if (confirmVersion !== null) confirmHeading.current?.focus(); }, [confirmVersion]);
  const reload = async () => {
    await query.refetch({ throwOnError: true });
    if (session.isCurrent()) { setEditing(false); setConfirmVersion(null); setNotice(""); }
  };
  const blocked = write.locked || query.isFetching || query.isError;
  return <div className="admin-workspace">
    <Link className="text-link" href="/clients">Voltar aos clientes</Link>
    {query.isPending ? <LoadingRows label="Carregando cliente..." /> : query.isError ? <>
      <h1 id="client-heading" tabIndex={-1}>Cliente indisponível</h1>
      <ReadError retry={() => void query.refetch()}>{query.error instanceof ApiError && query.error.status === 404 ? "Este cliente não está disponível para sua conta." : undefined}</ReadError>
    </> : client && <>
      <h1 id="client-heading" tabIndex={-1}>{client.name}</h1>
      <p className="admin-intro">{client.active ? "Cliente ativo" : "Cliente arquivado"}</p>
      {notice && <p role="status" className="read-notice">{notice}</p>}
      {write.error && <div className="read-error"><p role="alert">{writeError(write.error)}</p>
        <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(reload)}>Recarregar e descartar edição</Button></div>}
      {write.reloadFailed && <p role="alert" className="error-message">Não foi possível atualizar os dados. A edição continua bloqueada.</p>}
      <div className="admin-plane">
        <section className="admin-section" aria-labelledby="client-settings-heading">
          <h2 id="client-settings-heading">Dados do cliente</h2>
          {!client.can_manage ? <p>Acesso somente para consulta.</p> : editing ? <form noValidate className="inline-form" onSubmit={form.handleSubmit(value => write.submit({ name: value.name, version: editVersion }))}>
            <div className="form-grow"><label htmlFor="client-name">Nome do cliente</label>
              <input id="client-name" maxLength={300} {...form.register("name")} disabled={write.locked} aria-invalid={!!form.formState.errors.name} aria-describedby="client-name-error" />
              <p id="client-name-error" className="field-error">{form.formState.errors.name?.message}</p></div>
            <Button type="submit" disabled={blocked}>Salvar nome</Button>
            <Button variant="outline" type="button" disabled={write.locked} onClick={() => { setEditing(false); requestAnimationFrame(() => document.getElementById("rename-client")?.focus()); }}>Cancelar edição</Button>
          </form> : <div className="action-row">
            <Button id="rename-client" variant="outline" disabled={blocked || confirmVersion !== null} onClick={() => { form.reset({ name: client.name }); setEditVersion(client.version); setEditing(true); setNotice(""); }}>Renomear cliente</Button>
            <Button id="client-state" variant="outline" disabled={blocked || confirmVersion !== null} onClick={() => {
              setNotice(""); if (client.active) setConfirmVersion(client.version); else write.submit({ active: true, version: client.version });
            }}>{client.active ? "Arquivar cliente" : "Restaurar cliente"}</Button>
          </div>}
          {confirmVersion !== null && <div className="confirmation" role="group" aria-labelledby="archive-client-heading">
            <h3 id="archive-client-heading" ref={confirmHeading} tabIndex={-1}>Arquivar este cliente?</h3>
            <p>O cliente {client.name} continuará no histórico e poderá ser restaurado.</p>
            <div className="action-row"><Button disabled={blocked} onClick={() => write.submit({ active: false, version: confirmVersion })}>Confirmar arquivamento</Button>
              <Button variant="outline" disabled={write.locked} onClick={() => { setConfirmVersion(null); requestAnimationFrame(() => document.getElementById("client-state")?.focus()); }}>Cancelar</Button></div>
          </div>}
        </section>
        <ClientHistory id={id} api={api} />
      </div>
    </>}
  </div>;
}
