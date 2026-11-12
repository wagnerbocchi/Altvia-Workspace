"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, Paging, ReadError, usePaging, useTeamWrite } from "@/components/team-admin/common";
import { RecordPicker, type Choice } from "@/components/project-workspace/picker";
import type { QueueApi, QueueCreate } from "@/lib/ticket-queues";
import { queueNameSchema, WriteFeedback } from "./metadata-editor";

function QueueCreation({ api, session }: { api: QueueApi; session: WorkspaceSession }) {
  const router = useRouter();
  const paging = usePaging();
  const teams = useQuery({ queryKey: ["queue-teams", paging.cursor], queryFn: ({ signal }) => api.teams(paging.cursor, signal) });
  const [team, setTeam] = useState<Choice | null>(null);
  const [selectionError, setSelectionError] = useState("");
  const form = useForm<{ name: string }>({ resolver: zodResolver(queueNameSchema), defaultValues: { name: "" } });
  const write = useTeamWrite(session, ({ key, ...body }: QueueCreate & { key: string }) => api.create(body, key), receipt => router.push(`/service-desk/queues/${receipt.queue_id}`));
  return <section className="admin-section" aria-labelledby="new-queue-heading">
    <h2 id="new-queue-heading">Nova fila</h2>
    <form noValidate onSubmit={form.handleSubmit(value => {
      if (!team) { setSelectionError("Escolha a equipe da fila."); return; }
      setSelectionError("");
      write.submit({ name: value.name, team_id: team.id, key: crypto.randomUUID() });
    })}>
      <div className="account-form-grid">
        <div>
          <label htmlFor="new-queue-name">Nome da nova fila</label>
          <input id="new-queue-name" maxLength={300} {...form.register("name")} disabled={write.locked} aria-invalid={!!form.formState.errors.name} aria-describedby="queue-name-error" />
          <p id="queue-name-error" className="field-error">{form.formState.errors.name?.message}</p>
        </div>
        <RecordPicker id="queue-team" label="Equipe da fila" value={team} onChange={setTeam}
          choices={teams.data?.items.filter(row => row.active && row.can_manage).map(row => ({ id: row.id, label: row.name })) ?? []}
          paging={paging} next={teams.data?.next_cursor} pending={teams.isPending} failed={teams.isError} retry={() => void teams.refetch()} disabled={write.locked} />
      </div>
      <p className="field-help">A equipe sera mantida no cadastro da fila.</p>
      {selectionError && <p role="alert" className="field-error">{selectionError}</p>}
      <div className="action-row add-member-action"><Button type="submit" disabled={write.locked}>{write.pending ? "Cadastrando..." : "Cadastrar fila"}</Button></div>
    </form>
    <WriteFeedback creation write={write} reload={async () => { await teams.refetch({ throwOnError: true }); }} />
  </section>;
}

export function QueueDirectory({ api, session }: { api: QueueApi; session: WorkspaceSession }) {
  const paging = usePaging();
  const authority = useQuery({ queryKey: ["ticket-queues", null], queryFn: ({ signal }) => api.list(null, signal) });
  const query = useQuery({ queryKey: ["ticket-queues", paging.cursor], queryFn: ({ signal }) => api.list(paging.cursor, signal) });
  const mayCreate = authority.data?.can_create && query.data?.can_create !== false;
  return <div className="admin-workspace">
    <Link className="text-link" href="/">Voltar a minha conta</Link>
    <h1 id="queues-heading" tabIndex={-1}>Filas de atendimento</h1>
    <p className="admin-intro">Organize as filas e categorias de atendimento das equipes disponiveis para sua conta.</p>
    <div className="admin-plane">
      {mayCreate && <QueueCreation api={api} session={session} />}
      <section className="admin-section" aria-labelledby="queue-list-heading">
        <h2 id="queue-list-heading">Filas cadastradas</h2>
        <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar filas</Button>
        {query.isPending ? <LoadingRows label="Carregando filas..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ?
          <ul className="record-list" aria-label="Filas cadastradas">{query.data.items.map(row => <li className="team-row" key={row.id}>
            <div className="record-text"><Link className="text-link" href={`/service-desk/queues/${row.id}`}>{row.name}</Link>
              <span className="record-meta">{row.team_name}</span>
              <span className="record-meta">{row.can_manage ? "Gestao da fila" : "Somente consulta"}</span>
            </div><span className="record-status" data-state={row.active ? "active" : "inactive"}>{row.active ? "Ativa" : "Arquivada"}</span>
          </li>)}</ul> : <p>Nenhuma fila disponivel nesta pagina.</p>}
        <Paging paging={paging} next={query.data?.next_cursor} label="filas" disabled={query.isFetching} />
      </section>
    </div>
  </div>;
}
