"use client";

import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import { pageQuery } from "@/lib/admin-http";
import { createAdminTransport } from "@/lib/admin-http";
import type { components } from "@/lib/api.generated";
import type { WorkspaceSession } from "@/components/workspace-session";

const actions: Record<string, string> = {
  "identity.session_created": "Sessão iniciada", "identity.session_revoked": "Sessão encerrada",
  "identity.admin_bootstrapped": "Administração inicial configurada", "identity.user_created": "Conta criada",
  "identity.user_enabled": "Conta ativada", "identity.user_disabled": "Conta desativada",
  "identity.password_reset": "Senha redefinida", "identity.admin_granted": "Administração concedida",
  "identity.admin_revoked": "Administração revogada", "identity.team_role_granted": "Acesso à equipe concedido",
  "identity.team_role_revoked": "Acesso à equipe revogado", "identity.team_created": "Equipe criada",
  "identity.team_updated": "Equipe atualizada", "identity.team_member_added": "Participante adicionado",
  "identity.team_member_removed": "Participante removido",
};

export function IdentityActivity({ session }: { session: WorkspaceSession }) {
  const paging = usePaging();
  const { request } = createAdminTransport(session.user.csrf_token, session.onAuthError);
  const query = useQuery({ queryKey: ["identity-activity", paging.cursor], queryFn: async ({ signal }) =>
    (await request(`/identity-activity${pageQuery(paging.cursor)}`, { signal })).json() as Promise<components["schemas"]["ActivityPage"]> });
  return <section className="admin-section" aria-labelledby="identity-activity-heading">
    <h2 id="identity-activity-heading">Histórico administrativo</h2>
    <p className="field-help">Alterações de contas, equipes e acessos, da mais recente à mais antiga. Os horários seguem o seu dispositivo.</p>
    <Button variant="outline" disabled={query.isFetching} onClick={() => { paging.reset(); void query.refetch(); }}>Atualizar histórico</Button>
    {query.isPending ? <LoadingRows label="Carregando histórico..." />
      : query.isError ? <ReadError retry={() => void query.refetch()} />
        : query.data.items.length ? <ul className="record-list" aria-label="Histórico administrativo">
          {query.data.items.map(item => <li className="team-row" key={item.event_id}>
            <div className="record-text"><strong>{actions[item.event_type] ?? "Atividade de identidade"}</strong>
              <span className="record-meta">{item.resource_type === "team" ? "Equipe" : "Identidade"}: {item.resource_id}</span>
              <span className="record-meta">{item.actor_kind === "management_command" ? "Comando administrativo" : `Autor: ${item.actor_id}`}</span>
              <span className="record-meta">Correlação: {item.correlation_id}</span></div>
            <time className="record-status" dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString("pt-BR")}</time>
          </li>)}
        </ul> : <p>{paging.index ? "Nenhuma atividade nesta página. Volte à página anterior." : "Nenhuma atividade disponível. Atualize em instantes."}</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="atividades" disabled={query.isFetching} />
  </section>;
}
