"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import type { ClientApi, ClientCreate } from "@/lib/clients";
import { createTeamApi } from "@/lib/teams";
import { LoadingRows, Paging, ReadError, nameSchema, usePaging, useTeamWrite, writeError } from "@/components/team-admin/common";

function ClientProvisioning({ api, session }: { api: ClientApi; session: WorkspaceSession }) {
  const peoplePaging = usePaging();
  const users = createTeamApi(session.user.csrf_token, session.onAuthError);
  const people = useQuery({ queryKey: ["client-manager-candidates", peoplePaging.cursor], queryFn: ({ signal }) => users.users(peoplePaging.cursor, signal) });
  const [selected, setSelected] = useState<{ id: string; label: string } | null>(null);
  const [managerError, setManagerError] = useState("");
  const [notice, setNotice] = useState("");
  const form = useForm<{ name: string }>({ resolver: zodResolver(nameSchema), defaultValues: { name: "" } });
  const write = useTeamWrite(session, (intent: ClientCreate & { key: string }) => {
    const { key, ...body } = intent; return api.create(body, key);
  }, receipt => {
    form.reset(); setSelected(null);
    setNotice("Cliente cadastrado para o gestor escolhido. Ele precisará entrar novamente para usar o novo acesso.");
    if (receipt.manager_user_id === session.user.id) session.onRefresh();
  });
  const choices = [{ id: session.user.id, label: `${session.user.display_name} (você)` },
    ...(people.data?.items.filter(person => person.active && person.id !== session.user.id).map(person => ({ id: person.id, label: `${person.display_name} - ${person.email}` })) ?? [])];
  if (selected && !choices.some(person => person.id === selected.id)) choices.push(selected);
  return <section className="admin-section" aria-labelledby="new-client-heading">
    <h2 id="new-client-heading">Novo cliente</h2>
    <p className="field-help">Escolha quem poderá gerenciar este cliente. Cadastrar não dá acesso automático à sua conta.</p>
    <form noValidate onSubmit={form.handleSubmit(value => {
      if (!selected) { setManagerError("Escolha o gestor inicial."); return; }
      setNotice(""); write.submit({ name: value.name, manager_user_id: selected.id, key: crypto.randomUUID() });
    })}>
      <div className="account-form-grid">
        <div><label htmlFor="new-client-name">Nome do cliente</label>
          <input id="new-client-name" maxLength={300} {...form.register("name")} disabled={write.locked} aria-invalid={!!form.formState.errors.name} aria-describedby="client-name-error" />
          <p id="client-name-error" className="field-error">{form.formState.errors.name?.message}</p></div>
        <div><label htmlFor="initial-manager">Gestor inicial</label>
          <select id="initial-manager" value={selected?.id ?? ""} disabled={write.locked} aria-invalid={!!managerError} aria-describedby="initial-manager-help" onChange={event => {
            setSelected(choices.find(person => person.id === event.target.value) ?? null); setManagerError("");
          }}><option value="">Escolha uma pessoa</option>{choices.map(person => <option value={person.id} key={person.id}>{person.label}</option>)}</select>
          <p id="initial-manager-help" className={managerError ? "field-error" : "field-help"}>{managerError || "O gestor terá acesso de gestão. Se escolher você, sua sessão será encerrada após o cadastro."}</p></div>
      </div>
      {people.isPending ? <p role="status">Carregando gestores...</p> : people.isError ? <ReadError retry={() => void people.refetch()}>Não foi possível carregar outras pessoas. Tente novamente para escolher outro gestor.</ReadError>
        : <Paging paging={peoplePaging} next={people.data.next_cursor} label="contas" disabled={people.isFetching || write.locked} />}
      <Button className="client-create-action" type="submit" disabled={write.locked}>{write.pending ? "Cadastrando..." : "Cadastrar cliente"}</Button>
    </form>
    {notice && <p role="status" className="read-notice">{notice}</p>}
    {write.error && <div className="error-message"><p role="alert">{writeError(write.error)}</p>
      {write.uncertain ? <Button variant="outline" disabled={write.pending} onClick={write.verify}>Verificar cadastro</Button>
        : write.locked && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(async () => { await people.refetch({ throwOnError: true }); })}>Recarregar gestores</Button>}</div>}
    {write.reloadFailed && <p className="error-message" role="alert">Não foi possível atualizar. O cadastro anterior continua bloqueado.</p>}
  </section>;
}

export function ClientDirectory({ api, session }: { api: ClientApi; session: WorkspaceSession }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["clients", paging.cursor], queryFn: ({ signal }) => api.list(paging.cursor, signal) });
  return <div className="admin-workspace">
    <Link className="text-link" href="/">Voltar à minha conta</Link>
    <h1 id="clients-heading" tabIndex={-1}>Clientes</h1>
    <p className="admin-intro">Consulte os clientes liberados para sua conta. O acesso a cada cliente é definido explicitamente.</p>
    <div className="admin-plane">
      {session.user.capabilities.includes("identity.manage") && <ClientProvisioning api={api} session={session} />}
      <section className="admin-section" aria-labelledby="client-list-heading">
        <h2 id="client-list-heading">Clientes disponíveis</h2>
        {query.isPending ? <LoadingRows label="Carregando clientes..." /> : query.isError ? <ReadError retry={() => void query.refetch()} />
          : query.data.items.length ? <ul className="record-list" aria-label="Clientes disponíveis">{query.data.items.map(client => <li className="team-row" key={client.id}>
            <div className="record-text"><Link className="text-link" href={`/clients/${encodeURIComponent(client.id)}`}>{client.name}</Link>
              <span className="record-meta">{client.can_manage ? "Gestão do cliente" : "Somente consulta"}</span></div>
            <span className="record-status">{client.active ? "Ativo" : "Arquivado"}</span></li>)}</ul>
            : <p>{paging.index ? "Nenhum cliente nesta página. Volte à página anterior." : "Nenhum cliente disponível para sua conta."}</p>}
        <Paging paging={paging} next={query.data?.next_cursor} label="clientes" disabled={query.isFetching} />
      </section>
    </div>
  </div>;
}
