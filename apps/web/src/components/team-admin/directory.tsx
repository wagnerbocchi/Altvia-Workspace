"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { TeamApi } from "@/lib/teams";
import type { WorkspaceSession } from "@/components/workspace-session";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, nameSchema, usePaging, useTeamWrite, writeError } from "./common";

export function TeamDirectory({ api, session }: { api: TeamApi; session: WorkspaceSession }) {
  const router = useRouter();
  const paging = usePaging();
  const query = useQuery({ queryKey: ["teams", paging.cursor], queryFn: ({ signal }) => api.list(paging.cursor, signal) });
  const form = useForm<{ name: string }>({ resolver: zodResolver(nameSchema), defaultValues: { name: "" } });
  const write = useTeamWrite(session, (intent: { name: string; key: string }) => api.create(intent.name, intent.key),
    result => router.push(`/admin/teams/${encodeURIComponent(result.id)}`));
  return <div className="admin-workspace">
    <Link className="text-link" href="/">Voltar à minha conta</Link>
    <h1 id="teams-heading" tabIndex={-1}>Equipes</h1>
    <p className="admin-intro">Organize equipes e participantes. Os acessos a clientes e projetos são definidos separadamente.</p>
    <div className="admin-plane">
      <section className="admin-section" aria-labelledby="new-team-heading">
        <h2 id="new-team-heading">Nova equipe</h2>
        <form className="inline-form" noValidate onSubmit={form.handleSubmit(value => write.submit({ name: value.name, key: crypto.randomUUID() }))}>
          <div className="form-grow"><label htmlFor="new-team-name">Nome da nova equipe</label>
            <input id="new-team-name" maxLength={300} {...form.register("name")} disabled={write.locked}
              aria-invalid={!!form.formState.errors.name} aria-describedby="new-team-help" />
            <p id="new-team-help" className={form.formState.errors.name ? "field-error" : "field-help"}>
              {form.formState.errors.name?.message ?? "Até 150 caracteres. Nomes iguais não representam a mesma equipe."}
            </p>
          </div><Button type="submit" disabled={write.locked || !query.data || query.isError}>
            {write.pending ? "Criando..." : "Criar equipe"}
          </Button>
        </form>
        {write.error && <div className="error-message"><p role="alert">{writeError(write.error)}</p>
          {write.uncertain ? <Button variant="outline" disabled={write.pending} onClick={write.verify}>Verificar resultado</Button>
            : write.locked && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(async () => {
              await query.refetch({ throwOnError: true });
            })}>Recarregar dados</Button>}
        </div>}
        {write.reloadFailed && <p className="error-message" role="alert">Não foi possível atualizar os dados. A solicitação anterior continua bloqueada.</p>}
      </section>
      <section className="admin-section" aria-labelledby="team-list-heading">
        <h2 id="team-list-heading">Equipes cadastradas</h2>
        {query.isPending ? <LoadingRows label="Carregando equipes..." />
          : query.isError ? <ReadError retry={() => void query.refetch()} />
            : query.data.items.length ? <ul className="record-list" aria-label="Equipes cadastradas">
              {query.data.items.map(team => <li key={team.id} className="team-row">
                <div className="record-text"><Link className="team-link" href={`/admin/teams/${team.id}`}>{team.name}</Link>
                  <span className="record-meta">Identificador: {team.id}</span></div>
                <span className="record-status" data-state={team.active ? "active" : "inactive"}>{team.active ? "Ativa" : "Arquivada"}</span>
              </li>)}
            </ul> : <p>{paging.index ? "Nenhuma equipe nesta página. Volte à página anterior." : "Nenhuma equipe cadastrada. Crie a primeira equipe para organizar participantes."}</p>}
        <Paging paging={paging} next={query.data?.next_cursor} label="equipes" disabled={query.isFetching || write.locked} />
      </section>
    </div>
  </div>;
}
