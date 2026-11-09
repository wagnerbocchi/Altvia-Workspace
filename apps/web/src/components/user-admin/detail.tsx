"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { WorkspaceSession } from "@/components/workspace-session";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import { ApiError } from "@/lib/http";
import type { TeamApi } from "@/lib/teams";
import type { AccountApi, Role, SecurityChange } from "@/lib/users";
import { AccountWriteFeedback, passwordError, useAccountWrite } from "./write";

type PublicChange = Exclude<SecurityChange, { kind: "password" }> | { kind: "password" };
type Confirmation = { change: PublicChange; version: number; title: string; label: string;
  description: string; trigger: HTMLElement };

export function AccountDetail({ id, api, teams, session }: {
  id: string; api: AccountApi; teams: TeamApi; session: WorkspaceSession;
}) {
  const client = useQueryClient();
  const rolePaging = usePaging();
  const teamPaging = usePaging();
  const password = useRef<HTMLInputElement>(null);
  const confirmHeading = useRef<HTMLHeadingElement>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [invalidPassword, setInvalidPassword] = useState("");
  const [selected, setSelected] = useState("");
  const [role, setRole] = useState<Role["role_name"]>("viewer");
  const [notice, setNotice] = useState("");
  const accountQuery = useQuery({ queryKey: ["account", id], queryFn: ({ signal }) => api.get(id, signal) });
  const account = accountQuery.data;
  const roleQuery = useQuery({ queryKey: ["account-roles", id, account?.version, rolePaging.cursor],
    queryFn: ({ signal }) => api.roles(id, rolePaging.cursor, signal), enabled: !!account });
  const teamQuery = useQuery({ queryKey: ["teams", teamPaging.cursor], queryFn: ({ signal }) => teams.list(teamPaging.cursor, signal) });
  const selectedTeam = teamQuery.data?.items.find(team => team.id === selected);
  const ready = !!account && !accountQuery.isError && !accountQuery.isFetching
    && !roleQuery.isError && !roleQuery.isFetching && roleQuery.data?.version === account.version;
  const write = useAccountWrite(session, (intent: { change: SecurityChange; version: number; key: string }) =>
    api.change(id, intent.change, intent.version, intent.key), () => {
    setConfirmation(null); setSelected(""); setInvalidPassword(""); rolePaging.reset();
    setNotice("Solicitação confirmada. Os dados atuais estão sendo carregados.");
    void client.invalidateQueries({ queryKey: ["account", id] });
    void client.invalidateQueries({ queryKey: ["account-roles", id] });
    void client.invalidateQueries({ queryKey: ["users"] });
    document.getElementById("user-heading")?.focus();
  });
  useEffect(() => { if (confirmation) confirmHeading.current?.focus(); }, [confirmation]);
  const blocked = !ready || write.locked || !!confirmation;
  const hidden = accountQuery.error instanceof ApiError && [401, 403, 404].includes(accountQuery.error.status);
  async function reloadSnapshot() {
    const fresh = await api.get(id);
    const roles = await api.roles(id, rolePaging.cursor);
    await teamQuery.refetch({ throwOnError: true });
    if (fresh.version !== roles.version) throw new ApiError(409, undefined, "version_conflict");
    if (!session.isCurrent()) return;
    client.setQueryData(["account", id], fresh);
    client.setQueryData(["account-roles", id, fresh.version, rolePaging.cursor], roles);
    setSelected(""); setConfirmation(null); setNotice("Dados recarregados. Confira o estado atual antes de alterar.");
  }
  function confirm(change: PublicChange, title: string, label: string, description: string, trigger: HTMLElement) {
    if (!account || blocked) return;
    setConfirmation({ change, title, label, description, version: account.version, trigger });
  }
  function cancel() {
    const trigger = confirmation?.trigger;
    setConfirmation(null);
    requestAnimationFrame(() => {
      if (!session.isCurrent()) return;
      if (trigger?.isConnected) trigger.focus(); else document.getElementById("user-heading")?.focus();
    });
  }
  return <div className="admin-workspace">
    <Link className="text-link" href="/admin/users">Voltar às contas</Link>
    <h1 id="user-heading" tabIndex={-1}>{!hidden && account ? account.display_name : "Conta"}</h1>
    {accountQuery.isPending ? <LoadingRows label="Carregando conta..." />
      : hidden || (!account && !accountQuery.isError) ? <p role="alert">Conta não encontrada ou acesso indisponível.</p>
        : !account ? <ReadError retry={() => void accountQuery.refetch()} /> : <>
          <p className="admin-intro">{account.email}<span className="record-meta">Identificador: {account.id}</span></p>
          {notice && <p className="notice" role="status">{notice}</p>}
          {(accountQuery.isError || roleQuery.isError || (roleQuery.data && roleQuery.data.version !== account.version)) &&
            <ReadError retry={() => void write.reconcile(reloadSnapshot)}>Não foi possível confirmar os dados atuais. Recarregue antes de alterar.</ReadError>}
          <AccountWriteFeedback write={write} reload={reloadSnapshot} />
          <div className="admin-plane">
            <section className="admin-section" aria-labelledby="account-state-heading">
              <h2 id="account-state-heading">Estado e administração</h2>
              <p>{account.active ? "Conta ativa" : "Conta desativada"}</p>
              <p>{account.platform_admin ? "Administrador da plataforma" : "Sem administração da plataforma"}</p>
              <p className="field-help">A administração permite gerenciar identidades. Os acessos a clientes e projetos são definidos separadamente.</p>
              <div className="action-row">
                <Button variant="outline" disabled={blocked} onClick={event => confirm({ kind: "activation", active: !account.active },
                  account.active ? "Desativar esta conta?" : "Ativar esta conta?",
                  account.active ? "Confirmar desativação" : "Confirmar ativação",
                  account.active ? "A pessoa perderá o acesso e todas as sessões serão encerradas." : "A pessoa poderá entrar com a senha atual. Os acessos existentes serão preservados.", event.currentTarget)}>
                  {account.active ? "Desativar conta" : "Ativar conta"}</Button>
                <Button variant="outline" disabled={blocked || (!account.active && !account.platform_admin)} onClick={event => confirm({ kind: "platform-admin", enabled: !account.platform_admin },
                  account.platform_admin ? "Revogar administração?" : "Conceder administração?",
                  account.platform_admin ? "Confirmar revogação" : "Confirmar concessão",
                  "Esta permissão permite administrar contas, equipes e acessos. Todas as sessões da pessoa serão encerradas.", event.currentTarget)}>
                  {account.platform_admin ? "Revogar administração" : "Conceder administração"}</Button>
              </div>
            </section>
            <section className="admin-section" aria-labelledby="password-heading">
              <h2 id="password-heading">Redefinir senha</h2>
              <form className="inline-form" noValidate onSubmit={event => {
                event.preventDefault(); const error = passwordError(password.current?.value ?? ""); setInvalidPassword(error);
                if (error) { password.current?.focus(); return; }
                confirm({ kind: "password" }, "Redefinir a senha desta conta?", "Confirmar nova senha",
                  "A senha anterior deixará de funcionar e todas as sessões serão encerradas. Informe a nova senha por um canal seguro.",
                  document.getElementById("reset-password")!);
              }}>
                <div className="form-grow"><label htmlFor="account-new-password">Nova senha</label>
                  <input id="account-new-password" ref={password} type="password" autoComplete="new-password" maxLength={2048} disabled={blocked}
                    aria-invalid={!!invalidPassword} aria-describedby="account-password-help" />
                  <p id="account-password-help" className={invalidPassword ? "field-error" : "field-help"}>
                    {invalidPassword || "Pelo menos 14 caracteres; até 1024 bytes."}</p></div>
                <Button id="reset-password" type="submit" disabled={blocked}>Redefinir senha</Button>
              </form>
            </section>
            {confirmation && <section className="admin-section" aria-labelledby="account-confirm-heading">
              <h2 id="account-confirm-heading" ref={confirmHeading} tabIndex={-1}>{confirmation.title}</h2>
              <p>Conta: <strong>{account.display_name}</strong> ({account.email}).</p>
              <p>{confirmation.description}</p>
              {id === session.user.id && <p className="notice">Sua sessão será encerrada. Entre novamente para continuar.</p>}
              <div className="action-row"><Button disabled={write.locked} onClick={() => {
                const change = confirmation.change.kind === "password"
                  ? { kind: "password" as const, password: password.current?.value ?? "" } : confirmation.change;
                write.submit({ change, version: confirmation.version, key: crypto.randomUUID() });
                if (password.current) password.current.value = "";
                setConfirmation(null);
              }}>{confirmation.label}</Button><Button variant="outline" disabled={write.locked} onClick={cancel}>Cancelar</Button></div>
            </section>}
            <section className="admin-section" aria-labelledby="roles-heading">
              <h2 id="roles-heading">Acessos a equipes</h2>
              <p className="field-help">São permissões explícitas de leitura. Adicionar alguém à lista de participantes de uma equipe não concede estes acessos.</p>
              <div className="roster-columns"><section aria-labelledby="granted-roles-heading">
                <h3 id="granted-roles-heading">Acessos concedidos</h3>
                {roleQuery.isPending ? <LoadingRows label="Carregando acessos..." />
                  : roleQuery.isError ? <p role="alert">Não foi possível carregar os acessos. Use a recuperação acima.</p>
                    : roleQuery.data?.page.items.length ? <ul className="record-list" aria-label="Acessos concedidos">
                      {roleQuery.data.page.items.map(binding => <li className="member-row" key={binding.id}>
                        <div className="record-text"><strong>{binding.team_name}</strong><span className="record-meta">{binding.role_name === "viewer" ? "Leitura" : "Gestor operacional (leitura)"} · {binding.team_active ? "Equipe ativa" : "Equipe arquivada"}</span>
                          <span className="record-meta">Equipe: {binding.team_id}</span></div>
                        <Button variant="outline" disabled={blocked} onClick={event => confirm({ kind: "team-roles", team_id: binding.team_id,
                          role_name: binding.role_name, enabled: false }, "Revogar este acesso?", "Confirmar revogação",
                          `Remover ${binding.role_name === "viewer" ? "Leitura" : "Gestor operacional (leitura)"} da equipe ${binding.team_name}. Todas as sessões da pessoa serão encerradas.`, event.currentTarget)}>Revogar acesso</Button>
                      </li>)}
                    </ul> : <p>Nenhum acesso a equipes concedido.</p>}
                <Paging paging={rolePaging} next={roleQuery.data?.page.next_cursor} label="acessos" disabled={write.locked || !!confirmation || roleQuery.isFetching} />
              </section><section aria-labelledby="grant-role-heading">
                <h3 id="grant-role-heading">Conceder acesso</h3>
                {!account.active && <p className="notice">Ative a conta antes de conceder novos acessos.</p>}
                {teamQuery.isPending ? <LoadingRows label="Carregando equipes..." />
                  : teamQuery.isError ? <ReadError retry={() => void teamQuery.refetch()} />
                    : <fieldset className="account-picker" disabled={blocked || !account.active || teamQuery.isFetching}>
                      <legend>Equipe para acesso</legend>
                      {teamQuery.data.items.length ? teamQuery.data.items.map(team => <label className="account-option" key={team.id}>
                        <input type="radio" name="account-team" checked={selected === team.id} disabled={!team.active} onChange={() => setSelected(team.id)} />
                        <span className="record-text">{team.name}<span className="record-meta">{team.active ? "Ativa" : "Arquivada"} · {team.id}</span></span>
                      </label>) : <p>Nenhuma equipe nesta página.</p>}
                    </fieldset>}
                <Paging paging={teamPaging} next={teamQuery.data?.next_cursor} label="equipes" disabled={write.locked || !!confirmation || teamQuery.isFetching} />
                <fieldset className="account-picker role-picker" disabled={blocked || !account.active}>
                  <legend>Permissão de leitura</legend>
                  {(["viewer", "operations_manager"] as const).map(value => <label className="account-option" key={value}>
                    <input type="radio" name="account-role" checked={role === value} onChange={() => setRole(value)} />
                    <span>{value === "viewer" ? "Leitura" : "Gestor operacional (leitura)"}</span>
                  </label>)}
                </fieldset>
                <Button className="add-member-action" disabled={blocked || !account.active || !selectedTeam?.active || teamQuery.isError || teamQuery.isFetching}
                  onClick={event => selectedTeam && confirm({ kind: "team-roles", team_id: selectedTeam.id, role_name: role, enabled: true },
                    "Conceder acesso a esta equipe?", "Confirmar acesso", `Conceder ${role === "viewer" ? "Leitura" : "Gestor operacional (leitura)"} à equipe ${selectedTeam.name}. Todas as sessões da pessoa serão encerradas.`, event.currentTarget)}>Conceder acesso à equipe</Button>
              </section></div>
            </section>
          </div>
        </>}
  </div>;
}
