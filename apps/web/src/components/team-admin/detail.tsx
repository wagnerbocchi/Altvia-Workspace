"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@/lib/http";
import type { TeamApi } from "@/lib/teams";
import type { WorkspaceSession } from "@/components/workspace-session";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, nameSchema, usePaging, useTeamWrite, writeError } from "./common";

type Intent = { version: number } & (
  { kind: "rename"; name: string } | { kind: "state"; active: boolean }
  | { kind: "add"; userId: string; key: string } | { kind: "remove"; userId: string }
);
type Confirmation = { title: string; description: string; label: string; intent: Intent; trigger: HTMLElement };

export function TeamDetail({ id, api, session }: { id: string; api: TeamApi; session: WorkspaceSession }) {
  const client = useQueryClient();
  const membersPaging = usePaging();
  const usersPaging = usePaging();
  const [selected, setSelected] = useState("");
  const [editing, setEditing] = useState(false);
  const [editVersion, setEditVersion] = useState(1);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [notice, setNotice] = useState("");
  const confirmHeading = useRef<HTMLHeadingElement>(null);
  const form = useForm<{ name: string }>({ resolver: zodResolver(nameSchema), defaultValues: { name: "" } });
  const teamQuery = useQuery({ queryKey: ["team", id], queryFn: ({ signal }) => api.get(id, signal) });
  const team = teamQuery.data;
  const rosterQuery = useQuery({ queryKey: ["members", id, team?.version, membersPaging.cursor],
    queryFn: ({ signal }) => api.members(id, membersPaging.cursor, signal), enabled: !!team });
  const usersQuery = useQuery({ queryKey: ["users", usersPaging.cursor], queryFn: ({ signal }) => api.users(usersPaging.cursor, signal) });
  const ready = !!team && !teamQuery.isError && !rosterQuery.isError && !teamQuery.isFetching
    && !rosterQuery.isFetching && rosterQuery.data?.version === team.version;
  const selectedUser = usersQuery.data?.items.find(row => row.id === selected);
  const visibleMembers = new Set(rosterQuery.data?.page.items.map(row => row.user_id));
  const write = useTeamWrite(session, async (intent: Intent) => {
    if (intent.kind === "rename") await api.update(id, { name: intent.name }, intent.version);
    else if (intent.kind === "state") await api.update(id, { active: intent.active }, intent.version);
    else if (intent.kind === "add") await api.add(id, intent.userId, intent.version, intent.key);
    else await api.remove(id, intent.userId, intent.version);
  }, () => {
    setEditing(false); setConfirmation(null); setSelected(""); membersPaging.reset();
    setNotice("Solicitação confirmada. Os dados atuais estão sendo carregados.");
    void client.invalidateQueries({ queryKey: ["team", id] });
    void client.invalidateQueries({ queryKey: ["members", id] });
    document.getElementById("team-heading")?.focus();
  });
  useEffect(() => { if (confirmation) confirmHeading.current?.focus(); }, [confirmation]);
  useEffect(() => { if (editing) form.setFocus("name"); }, [editing, form]);
  const hidden = teamQuery.error instanceof ApiError && [401, 403, 404].includes(teamQuery.error.status);
  async function reloadSnapshot() {
    const fresh = await api.get(id);
    const roster = await api.members(id, membersPaging.cursor);
    await usersQuery.refetch({ throwOnError: true });
    if (fresh.version !== roster.version) throw new ApiError(409, undefined, "version_conflict");
    if (!session.isCurrent()) return;
    client.setQueryData(["team", id], fresh);
    client.setQueryData(["members", id, fresh.version, membersPaging.cursor], roster);
    if (editing) { form.reset({ name: fresh.name }); setEditVersion(fresh.version); }
    setSelected(""); setConfirmation(null); setNotice("Dados recarregados. Confira o estado atual antes de alterar.");
  }
  function cancelConfirmation() {
    const target = confirmation?.trigger;
    setConfirmation(null);
    if (target?.isConnected) target.focus(); else document.getElementById("team-heading")?.focus();
  }
  return <div className="admin-workspace">
    <Link className="text-link" href="/admin/teams">Voltar às equipes</Link>
    <h1 id="team-heading" tabIndex={-1} className="record-heading">{!hidden && team ? team.name : "Equipe"}</h1>
    {teamQuery.isPending ? <LoadingRows label="Carregando equipe..." />
      : teamQuery.isError && !hidden && !team ? <ReadError retry={() => void teamQuery.refetch()} />
      : hidden || !team ? <div className="admin-plane admin-section"><p role="alert">Equipe não encontrada ou acesso indisponível.</p></div>
        : <>
          <p className="admin-intro"><span>{team.active ? "Equipe ativa" : "Equipe arquivada"}</span>
            <span className="record-meta">Identificador: {team.id}</span></p>
          {notice && <p className="notice" role="status">{notice}</p>}
          {(teamQuery.isError || rosterQuery.isError || (rosterQuery.data && rosterQuery.data.version !== team.version)) && <ReadError
            retry={() => void write.reconcile(reloadSnapshot, write.uncertain && write.current?.kind === "add")}>
            Não foi possível confirmar os dados atuais. Recarregue antes de alterar.</ReadError>}
          {write.error && <div className="error-message"><p role="alert">{writeError(write.error)}</p>
            {write.uncertain && write.current?.kind === "add"
              ? <Button variant="outline" disabled={write.pending || write.reloading} onClick={write.verify}>Verificar resultado</Button>
              : write.locked && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(reloadSnapshot)}>
                {editing ? "Recarregar e descartar edição" : "Recarregar dados"}
              </Button>}
          </div>}
          {write.reloadFailed && <p className="error-message" role="alert">Não foi possível atualizar os dados. As alterações continuam bloqueadas.</p>}
          {write.pending && <p role="status">Salvando solicitação...</p>}
          <div className="admin-plane">
            <section className="admin-section" aria-labelledby="team-settings-heading">
              <h2 id="team-settings-heading">Dados da equipe</h2>
              {editing ? <form noValidate className="inline-form" onSubmit={form.handleSubmit(value => write.submit({ kind: "rename", name: value.name, version: editVersion }))}>
                <div className="form-grow"><label htmlFor="team-name">Nome da equipe</label>
                  <input id="team-name" maxLength={300} {...form.register("name")} disabled={write.locked}
                    aria-invalid={!!form.formState.errors.name} aria-describedby="team-name-error" />
                  <p id="team-name-error" className="field-error">{form.formState.errors.name?.message}</p>
                </div><Button type="submit" disabled={!ready || write.locked}>Salvar nome</Button>
                <Button variant="outline" type="button" disabled={write.locked} onClick={() => {
                  setEditing(false); requestAnimationFrame(() => document.getElementById("rename-team")?.focus());
                }}>Cancelar edição</Button>
              </form> : <div className="action-row">
                <Button id="rename-team" variant="outline" disabled={!ready || write.locked || !!confirmation} onClick={() => {
                  form.reset({ name: team.name }); setEditVersion(team.version); setEditing(true);
                }}>Renomear equipe</Button>
                <Button variant="outline" disabled={!ready || write.locked || !!confirmation} onClick={event => {
                  setConfirmation({ title: team.active ? "Arquivar esta equipe?" : "Restaurar esta equipe?",
                    description: team.active ? `A equipe ${team.name} manterá seu histórico e participantes, mas não receberá novas inclusões.` : `A equipe ${team.name} voltará a receber participantes.`,
                    label: team.active ? "Confirmar arquivamento" : "Confirmar restauração",
                    intent: { kind: "state", active: !team.active, version: team.version }, trigger: event.currentTarget });
                }}>{team.active ? "Arquivar equipe" : "Restaurar equipe"}</Button>
              </div>}
              {confirmation && <section className="confirmation" role="group" aria-labelledby="confirmation-heading">
                <h3 id="confirmation-heading" ref={confirmHeading} tabIndex={-1}>{confirmation.title}</h3><p>{confirmation.description}</p>
                <div className="action-row"><Button variant="outline" disabled={write.locked} onClick={cancelConfirmation}>Cancelar confirmação</Button>
                  <Button disabled={!ready || write.locked} onClick={() => write.submit(confirmation.intent)}>{confirmation.label}</Button></div>
              </section>}
            </section>
            <div className="roster-columns admin-section">
              <section aria-labelledby="roster-heading"><h2 id="roster-heading">Participantes</h2>
                {rosterQuery.isPending ? <LoadingRows label="Carregando participantes..." />
                  : rosterQuery.isError ? <ReadError retry={() => void rosterQuery.refetch()} />
                    : rosterQuery.data?.page.items.length ? <ul className="record-list" aria-label="Participantes da equipe">
                      {rosterQuery.data.page.items.map(member => <li key={member.user_id} className="member-row">
                        <div className="record-text"><strong>{member.display_name}</strong>
                          <span className="record-meta">{member.account_active ? "Conta ativa" : "Conta inativa"}</span>
                          <span className="record-meta">Identificador: {member.user_id}</span></div>
                        <Button variant="outline" disabled={!ready || write.locked || !!confirmation || editing}
                          aria-label={`Remover ${member.display_name} da equipe`} onClick={event => setConfirmation({
                            title: "Remover participante?", description: `${member.display_name} será removido desta equipe. Os acessos a conteúdo não serão alterados por esta ação.`,
                            label: "Confirmar remoção", intent: { kind: "remove", userId: member.user_id, version: team.version }, trigger: event.currentTarget,
                          })}>Remover</Button>
                      </li>)}
                    </ul> : <p>{membersPaging.index ? "Nenhum participante nesta página." : "Nenhum participante nesta equipe."}</p>}
                <Paging paging={membersPaging} next={rosterQuery.data?.page.next_cursor} label="participantes" disabled={write.locked || rosterQuery.isFetching || !!confirmation} />
              </section>
              <section aria-labelledby="add-member-heading"><h2 id="add-member-heading">Adicionar participante</h2>
                <p className="field-help">Escolha uma conta existente e ativa. Participar da equipe não concede acesso a clientes ou projetos.</p>
                {usersQuery.isPending ? <LoadingRows label="Carregando contas..." />
                  : usersQuery.isError ? <ReadError retry={() => void usersQuery.refetch()} />
                    : <fieldset disabled={!team.active || write.locked || !!confirmation || editing} className="account-picker">
                      <legend>Conta para adicionar</legend>
                      {usersQuery.data.items.map(user => <label className="account-option" key={user.id}>
                        <input type="radio" name="member-account" value={user.id} checked={selected === user.id}
                          disabled={!user.active || visibleMembers.has(user.id)} onChange={() => setSelected(user.id)} />
                        <span className="record-text"><strong>{user.display_name}</strong><span className="record-meta">{user.email}</span>
                          <span className="record-meta">{!user.active ? "Conta inativa" : visibleMembers.has(user.id) ? "Já está na equipe" : "Conta ativa"}</span></span>
                      </label>)}
                    </fieldset>}
                <Paging paging={usersPaging} next={usersQuery.data?.next_cursor} label="contas" disabled={write.locked || usersQuery.isFetching || !!confirmation} />
                <Button className="add-member-action" disabled={!ready || !team.active || write.locked || !selectedUser?.active || visibleMembers.has(selected) || usersQuery.isError || !!confirmation || editing}
                  onClick={() => write.submit({ kind: "add", userId: selected, version: team.version, key: crypto.randomUUID() })}>Adicionar participante</Button>
              </section>
            </div>
          </div>
        </>}
  </div>;
}
