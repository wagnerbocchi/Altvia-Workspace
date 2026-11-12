"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, ReadError } from "@/components/team-admin/common";
import { TicketPicker } from "@/components/tickets/picker";
import type { Choice } from "@/components/project-workspace/picker";
import type { MailCase, Promotion } from "@/lib/mail-cases";
import type { QueueApi } from "@/lib/ticket-queues";
import { ticketPriorities, ticketStatuses, type TicketApi, type TicketRecord } from "@/lib/tickets";

export type PromotionReview = { row: MailCase; body: Promotion; labels: string[]; key: string };
export function MailPromotionForm({ row, api, queues, actor, disabled, submit }: {
  row: MailCase; api: TicketApi; queues: QueueApi; actor: { id: string; display_name: string }; disabled: boolean; submit: (review: PromotionReview) => void;
}) {
  const [subject, setSubject] = useState(row.subject);
  const [priority, setPriority] = useState<TicketRecord["priority"]>("medium");
  const [category, setCategory] = useState<Choice | null>(null);
  const [assignee, setAssignee] = useState<Choice | null>(null);
  const [reopen, setReopen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const authority = useQuery({ queryKey: ["mail-case-creation-authority", row.queue_id], enabled: row.can_create, queryFn: async ({ signal }) => {
    let cursor: string | null = null;
    do {
      const page = await api.queues(cursor, signal);
      const queue = page.items.find(item => item.id === row.queue_id);
      if (queue) return queue;
      cursor = page.next_cursor;
    } while (cursor && !signal.aborted);
    throw Error("Queue authority unavailable");
  } });
  const review = () => {
    setError("");
    let body: Promotion;
    let labels: string[];
    if (row.can_create) {
      const title = subject.trim();
      if (!title || Array.from(title).length > 300 || /[\0\r\n]/.test(title)) { setError("Revise o assunto do novo chamado: use de 1 a 300 caracteres em uma linha. O assunto recebido sera preservado integralmente."); return; }
      if (!authority.data?.can_create) return;
      body = { action: "create", subject: title, priority, category_id: category?.id ?? null, assignee_id: assignee?.id ?? null };
      labels = ["Novo chamado", title, `Prioridade: ${ticketPriorities[priority]}`, `Categoria: ${category?.label ?? "Sem categoria"}`, `Responsavel: ${assignee?.label ?? "Sem responsavel"}`];
    } else {
      if (!row.can_append || !row.candidate_ticket_id || !row.candidate_ticket_version) return;
      if (row.candidate_ticket_status === "closed" && !reopen) { setError("Escolha reabrir este chamado e informe o motivo para incluir a mensagem."); return; }
      if (reopen && (!reason.trim() || Array.from(reason.trim()).length > 2000)) { setError("Informe o motivo da reabertura, com ate 2000 caracteres."); return; }
      body = { action: "append", ticket_id: row.candidate_ticket_id, ticket_version: row.candidate_ticket_version, reopen, reopen_reason: reopen ? reason.trim() : null };
      labels = [`Chamado ${row.candidate_ticket_number}`, reopen ? "Reabrir e incluir mensagem" : "Incluir mensagem sem mudar o estado", ...(reopen ? [`Motivo: ${reason.trim()}`] : [])];
    }
    submit({ row, body, labels, key: crypto.randomUUID() });
  };
  return <section className="admin-section" aria-labelledby="mail-action-heading">
    <h2 id="mail-action-heading">{row.can_create ? "Criar chamado a partir da mensagem" : "Incluir no chamado relacionado"}</h2>
    <p className="field-help">O texto e o assunto recebidos permanecem integrais na conversa. Esta operacao nao envia e-mail.</p>
    {row.can_create && authority.isPending && <LoadingRows label="Carregando autoridade de criacao..." />}
    {row.can_create && authority.isError && <ReadError retry={() => void authority.refetch()}>Nao foi possivel consultar as opcoes desta fila. Atualize antes de revisar.</ReadError>}
    <form noValidate onSubmit={event => { event.preventDefault(); review(); }}><fieldset className="work-fields" disabled={disabled || (row.can_create && (!authority.data?.can_create || authority.isFetching || authority.isError))}>
      {row.can_create ? <>
        <div className="account-form-grid"><div className="form-grow"><label htmlFor="incoming-ticket-subject">Assunto do novo chamado</label><input id="incoming-ticket-subject" value={subject} onChange={event => setSubject(event.target.value)} aria-describedby="incoming-subject-help" /><p id="incoming-subject-help" className="field-help">Escolha deliberadamente um assunto de ate 300 caracteres. O assunto original aparece acima.</p></div>
          <div><label htmlFor="incoming-priority">Prioridade</label><select id="incoming-priority" value={priority} onChange={event => setPriority(event.target.value as typeof priority)}>{Object.entries(ticketPriorities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
          <TicketPicker id="incoming-category" label="Categoria" scope={`categories:${row.queue_id}`} value={category} onChange={setCategory} disabled={disabled} empty="Sem categoria" load={async (cursor, signal) => { const page = await queues.categories(row.queue_id, cursor, signal); return { ...page, items: page.items.filter(item => item.active).map(item => ({ id: item.id, label: item.name })) }; }} />
          {authority.data?.can_assign && <TicketPicker id="incoming-assignee" label="Responsavel" scope={`assignees:${row.queue_id}:${row.client_id}`} value={assignee} onChange={setAssignee} disabled={disabled} empty="Sem responsavel" load={async (cursor, signal) => { const page = await api.assignees(row.queue_id, row.client_id, cursor, signal); return { ...page, items: page.items.map(item => ({ id: item.id, label: item.display_name })) }; }} />}
        </div>
        {authority.data && !authority.data.can_assign && <label className="work-checkbox"><input type="checkbox" checked={assignee?.id === actor.id} onChange={event => setAssignee(event.target.checked ? { id: actor.id, label: actor.display_name } : null)} />Atribuir a mim</label>}
      </> : <>
        <p>Chamado {row.candidate_ticket_number} - {row.candidate_ticket_status && ticketStatuses[row.candidate_ticket_status]}</p>
        {row.candidate_can_reopen && <><label className="work-checkbox"><input type="checkbox" checked={reopen} onChange={event => setReopen(event.target.checked)} />Reabrir chamado ao incluir esta mensagem</label>{reopen && <div className="field"><label htmlFor="incoming-reopen-reason">Motivo da reabertura</label><textarea id="incoming-reopen-reason" value={reason} rows={3} onChange={event => setReason(event.target.value)} maxLength={4000} /></div>}</>}
      </>}
      {error && <p role="alert" className="field-error">{error}</p>}
      <Button type="submit">{row.can_create ? "Revisar criacao" : "Revisar inclusao"}</Button>
    </fieldset></form>
  </section>;
}
