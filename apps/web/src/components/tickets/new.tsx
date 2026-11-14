"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLayoutEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, ReadError, usePaging, useTeamWrite } from "@/components/team-admin/common";
import { RecordPicker, type Choice } from "@/components/project-workspace/picker";
import type { QueueApi } from "@/lib/ticket-queues";
import { type TicketApi, type TicketCreate, ticketPriorities } from "@/lib/tickets";
import { TicketForm, type TicketReferences } from "./form";
import { TicketPicker } from "./picker";
import { TicketFeedback } from "./feedback";

type QueueChoice = Choice & { can_assign: boolean };
export function NewTicket({ api, queues, session }: { api: TicketApi; queues: QueueApi; session: WorkspaceSession }) {
  const router = useRouter();
  const paging = usePaging();
  const query = useQuery({ queryKey: ["ticket-queue-choices", paging.cursor], queryFn: ({ signal }) => api.queues(paging.cursor, signal) });
  const [queue, setQueue] = useState<QueueChoice | null>(null);
  const [client, setClient] = useState<Choice | null>(null);
  const [revision, setRevision] = useState(0);
  const [review, setReview] = useState<{ body: TicketCreate; references: TicketReferences } | null>(null);
  useLayoutEffect(() => {
    // Finish initial review focus before the user can choose another control.
    if (review) document.getElementById("ticket-review-heading")?.focus();
  }, [review]);
  const [created, setCreated] = useState<string | null>(null);
  const write = useTeamWrite(session, (intent: { body: TicketCreate; key: string }) => api.create(intent.body, intent.key), receipt => {
    setCreated(receipt.ticket_id);
    router.push(`/service-desk/tickets/${receipt.ticket_id}`);
  });
  const options = query.data?.items.filter(row => row.can_create).map(row => ({ id: row.id, label: row.name, can_assign: row.can_assign })) ?? [];
  const reload = async () => { await query.refetch({ throwOnError: true }); };
  const blocked = write.locked || created !== null || query.isFetching || query.isError;
  return <div className="admin-workspace ticket-workspace">
    <Link className="text-link" href="/service-desk/tickets">Voltar aos chamados</Link>
    <h1 id="ticket-new-heading" tabIndex={-1}>Novo chamado</h1>
    <Button variant="outline" disabled={query.isFetching || write.pending} onClick={() => void query.refetch()}>Atualizar opcoes</Button>
    {query.isPending && <LoadingRows label="Carregando filas..." />}
    {query.isError && <ReadError retry={() => void query.refetch()} />}
    <TicketFeedback write={write} reload={reload} verifyLabel="Verificar criacao" />
    {created && <p role="status" className="read-notice">Chamado criado. <Link className="text-link" href={`/service-desk/tickets/${created}`}>Abrir chamado criado</Link></p>}
    {query.data?.can_create === false && !review && <p>Seu acesso atual permite somente consultar chamados.</p>}
    {(query.data?.can_create || review) && <div className="admin-plane">
      <section className="admin-section" aria-labelledby="ticket-scope-heading" hidden={review !== null}>
        <h2 id="ticket-scope-heading">Fila e cliente</h2>
        <div className="account-form-grid">
          <div><RecordPicker id="ticket-queue" label="Fila do chamado" value={queue} choices={options} paging={paging} next={query.data?.next_cursor}
            pending={query.isPending} failed={query.isError} retry={() => void query.refetch()} disabled={blocked}
            onChange={value => { setQueue(options.find(row => row.id === value?.id) ?? null); setClient(null); }} />
          </div>
          {queue && <TicketPicker key={queue.id} id="ticket-client" label="Cliente do chamado" scope={`clients:${queue.id}`} value={client} onChange={setClient} disabled={blocked}
            load={async (cursor, signal) => { const page = await api.clients(queue.id, cursor, signal); return { ...page, items: page.items.map(row => ({ id: row.id, label: row.name })) }; }} />}
        </div>
      </section>
      {queue && client && <section className="admin-section" aria-labelledby="ticket-fields-heading" hidden={review !== null}>
        <h2 id="ticket-fields-heading">Dados do chamado</h2>
        <TicketForm key={`${queue.id}:${client.id}:${revision}`} api={api} queues={queues} queue={queue.id} client={client.id} manage={queue.can_assign} actor={session.user} disabled={blocked}
          submit={(body, references) => { setReview({ body: body as TicketCreate, references }); }}
          cancel={() => setRevision(value => value + 1)} />
      </section>}
      {review && <section className="admin-section" aria-labelledby="ticket-review-heading">
        <h2 id="ticket-review-heading" tabIndex={-1}>Revisar chamado</h2>
        <dl className="account-details work-facts">
          <div><dt>Fila</dt><dd>{queue?.label}</dd></div><div><dt>Cliente</dt><dd>{client?.label}</dd></div>
          <div><dt>Solicitante</dt><dd>{review.references.requester}<p className="field-help">Solicitante com identidade nao verificada.</p></dd></div>
          <div><dt>Categoria</dt><dd>{review.references.category}</dd></div><div><dt>Responsavel</dt><dd>{review.references.assignee}</dd></div>
          <div><dt>Prioridade</dt><dd>{ticketPriorities[review.body.priority]}</dd></div>
          <div><dt>Assunto</dt><dd>{review.body.subject}</dd></div>
        </dl>
        <p className="work-prose">{review.body.description || "Sem descricao."}</p>
        <div className="action-row">
          <Button disabled={blocked} onClick={() => write.submit({ body: review.body, key: crypto.randomUUID() })}>Criar chamado</Button>
          <Button variant="outline" disabled={write.locked || created !== null} onClick={() => setReview(null)}>Voltar a edicao</Button>
        </div>
      </section>}
    </div>}
  </div>;
}
