"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { Choice } from "@/components/project-workspace/picker";
import type { QueueApi } from "@/lib/ticket-queues";
import { type TicketApi, type TicketCreate, type TicketPatch, type TicketRecord, ticketPriorities } from "@/lib/tickets";
import { TicketPicker } from "./picker";

export type TicketReferences = { requester: string; category: string; assignee: string };
export function TicketForm({ api, queues, queue, client, manage, actor, initial, disabled, submit, cancel }: {
  api: TicketApi; queues: QueueApi; queue: string; client: string; manage: boolean; actor: { id: string; display_name: string };
  initial?: TicketRecord; disabled: boolean;
  submit: (body: TicketCreate | TicketPatch, references: TicketReferences) => void; cancel: () => void;
}) {
  const [subject, setSubject] = useState(initial?.subject ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [priority, setPriority] = useState<TicketRecord["priority"]>(initial?.priority ?? "medium");
  const [requester, setRequester] = useState<Choice | null>(initial ? { id: initial.requester_id, label: `${initial.requester_name} - ${initial.requester_email}` } : null);
  const [category, setCategory] = useState<Choice | null>(initial?.category_id ? { id: initial.category_id, label: initial.category_name! } : null);
  const [assignee, setAssignee] = useState<Choice | null>(initial?.assignee_id ? { id: initial.assignee_id, label: initial.assignee_name! } : null);
  const [error, setError] = useState("");
  const references = { requester: requester?.label ?? "", category: category?.label ?? "Sem categoria", assignee: assignee?.label ?? "Sem responsavel" };
  const review = () => {
    setError("");
    const title = subject.trim();
    if (!title || Array.from(title).length > 300 || /[\0\r\n]/.test(title) || /\0/.test(description) || Array.from(description).length > 20000) {
      setError("Use assunto de 1 a 300 caracteres em uma linha e descricao de ate 20000 caracteres."); return;
    }
    if (!requester && (!initial || manage)) { setError("Escolha o solicitante deste cliente."); return; }
    if (!initial) {
      submit({ queue_id: queue, client_id: client, requester_id: requester!.id, subject: title, description, priority, category_id: category?.id ?? null, assignee_id: assignee?.id ?? null }, references);
      return;
    }
    const candidates: TicketPatch = { subject: title, description, priority, category_id: category?.id ?? null,
      ...(manage ? { requester_id: requester!.id, assignee_id: assignee?.id ?? null } : {}) };
    const changes = Object.fromEntries(Object.entries(candidates).filter(([key, value]) => initial[key as keyof TicketRecord] !== value)) as TicketPatch;
    if (!Object.keys(changes).length) { setError("Nenhuma alteracao para salvar."); return; }
    submit(changes, references);
  };
  return <form noValidate onSubmit={event => { event.preventDefault(); review(); }}>
    <fieldset className="work-fields" disabled={disabled}>
      <div className="account-form-grid">
        <div className="form-grow"><label htmlFor="ticket-subject">Assunto</label>
          <input id="ticket-subject" value={subject} maxLength={600} onChange={event => setSubject(event.target.value)} required />
        </div>
        <div><label htmlFor="ticket-priority">Prioridade</label>
          <select id="ticket-priority" value={priority} onChange={event => setPriority(event.target.value as typeof priority)}>
            {Object.entries(ticketPriorities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        {(!initial || manage) && <TicketPicker id="ticket-requester" label="Solicitante" scope={`requesters:${queue}:${client}`} value={requester} onChange={setRequester} disabled={disabled}
          load={async (cursor, signal) => { const page = await api.requesters(queue, client, cursor, signal); return { ...page, items: page.items.map(row => ({ id: row.id, label: `${row.display_name} - ${row.email}` })) }; }} />}
        <TicketPicker id="ticket-category" label="Categoria" scope={`categories:${queue}`} value={category} onChange={setCategory} disabled={disabled} empty="Sem categoria"
          load={async (cursor, signal) => { const page = await queues.categories(queue, cursor, signal); return { ...page, items: page.items.filter(row => row.active).map(row => ({ id: row.id, label: row.name })) }; }} />
        {manage && <TicketPicker id="ticket-assignee" label="Responsavel" scope={`assignees:${queue}:${client}`} value={assignee} onChange={setAssignee} disabled={disabled} empty="Sem responsavel"
          load={async (cursor, signal) => { const page = await api.assignees(queue, client, cursor, signal); return { ...page, items: page.items.map(row => ({ id: row.id, label: row.display_name })) }; }} />}
      </div>
      {!initial && !manage && <label className="work-checkbox"><input type="checkbox" checked={assignee?.id === actor.id} onChange={event => setAssignee(event.target.checked ? { id: actor.id, label: actor.display_name } : null)} />Atribuir a mim</label>}
      <p className="field-help">Solicitante com identidade nao verificada.</p>
      <div className="field"><label htmlFor="ticket-description">Descricao</label>
        <textarea id="ticket-description" rows={6} maxLength={40000} value={description} onChange={event => setDescription(event.target.value)} />
      </div>
      {error && <p role="alert" className="field-error">{error}</p>}
      <div className="action-row">
        <Button type="submit">{initial ? "Salvar chamado" : "Revisar chamado"}</Button>
        <Button type="button" variant="outline" onClick={cancel}>{initial ? "Cancelar edicao" : "Limpar formulario"}</Button>
      </div>
    </fieldset>
  </form>;
}
