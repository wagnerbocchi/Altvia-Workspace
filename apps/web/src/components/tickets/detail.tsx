"use client";

import Link from "next/link";
import { TicketWorkLinks } from "@/components/ticket-work/links";
import { AssignmentRuns } from "@/components/automation/runs";
import { AttachmentPicker } from "@/components/attachments";
import { sameAttachments, type AttachmentSummary } from "@/lib/attachments";
import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, ReadError, useTeamWrite } from "@/components/team-admin/common";
import type { QueueApi } from "@/lib/ticket-queues";
import { ApiError, isResourceForbidden } from "@/lib/http";
import { type TicketApi, type TicketPatch, type TicketRecord, type TicketTransition, ticketPriorities, ticketStatuses } from "@/lib/tickets";
import { TicketForm } from "./form";
import { TicketFeedback } from "./feedback";
import { TicketActivity, TicketHistory } from "./reads";
import { TicketNoteForm, TicketNotes } from "./notes";
import { type DeliveryReview, TicketDeliveryReview, TicketMessageForm, TicketMessages } from "./messages";

type Intent = { kind: "edit"; body: TicketPatch; version: number }
  | { kind: "claim"; version: number; key: string }
  | { kind: "transition"; body: TicketTransition; version: number; key: string }
  | { kind: "note"; body: { body_text: string; attachment_ids?: string[] }; files: AttachmentSummary[]; version: number; key: string }
  | { kind: "delivery"; review: DeliveryReview; version: number; key: string }
  | { kind: "message"; body: { body_text: string; attachment_ids?: string[] }; files: AttachmentSummary[]; version: number; key: string };

export function TicketDetail({ id, api, queues, session }: { id: string; api: TicketApi; queues: QueueApi; session: WorkspaceSession }) {
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ["ticket", id], queryFn: ({ signal }) => api.get(id, signal) });
  const row = query.error instanceof ApiError && [403, 404].includes(query.error.status) ? undefined : query.data;
  const [editor, setEditor] = useState<TicketRecord | null>(null);
  const [awaiting, setAwaiting] = useState(false);
  const [linksBusy, setLinksBusy] = useState(false);
  const [messageFiles, setMessageFiles] = useState<AttachmentSummary[]>([]), [noteFiles, setNoteFiles] = useState<AttachmentSummary[]>([]);
  const [messageFilesBusy, setMessageFilesBusy] = useState(false), [noteFilesBusy, setNoteFilesBusy] = useState(false);
  const messageBusyChanged = useCallback((busy: boolean) => setMessageFilesBusy(busy), []), noteBusyChanged = useCallback((busy: boolean) => setNoteFilesBusy(busy), []);
  const acknowledgedNote = useRef<{ id: string; body: string; files: AttachmentSummary[] } | null>(null);
  const [noteDraft, setNoteDraft] = useState<{ body: string; version: number } | null>(null);
  const [noteError, setNoteError] = useState("");
  const acknowledgedDelivery = useRef<{ message: string; delivery: string } | null>(null);
  const [deliveryAcknowledged, setDeliveryAcknowledged] = useState(false);
  const [deliveryReview, setDeliveryReview] = useState<DeliveryReview | null>(null);
  const acknowledgedMessage = useRef<{ id: string; body: string; files: AttachmentSummary[] } | null>(null);
  const [messageDraft, setMessageDraft] = useState<{ body: string; version: number } | null>(null);
  const [messageReview, setMessageReview] = useState<{ body: string; version: number; files: AttachmentSummary[] } | null>(null);
  const [messageError, setMessageError] = useState("");
  const [notice, setNotice] = useState("");
  const [target, setTarget] = useState<TicketRecord["status"] | "">("");
  const [reason, setReason] = useState("");
  const [transitionReview, setTransitionReview] = useState<Pick<TicketRecord, "version" | "status" | "allowed_transitions"> | null>(null);
  const [error, setError] = useState("");
  const refresh = async () => {
    const fresh = await query.refetch({ throwOnError: true });
    if (acknowledgedNote.current) {
      const note = await api.note(id, acknowledgedNote.current.id);
      if (!fresh.data || note.ticket_version > fresh.data.version || note.body_text !== acknowledgedNote.current.body || !sameAttachments(note.attachments ?? [], acknowledgedNote.current.files)) throw Error("Note version not confirmed");
      await cache.refetchQueries({ queryKey: ["ticket-notes", id], type: "active" }, { throwOnError: true });
    }
    if (acknowledgedMessage.current) {
      const message = await api.message(id, acknowledgedMessage.current.id);
      if (!fresh.data || message.ticket_version > fresh.data.version || message.body_text !== acknowledgedMessage.current.body || !sameAttachments(message.attachments ?? [], acknowledgedMessage.current.files)) throw Error("Message version not confirmed");
    }
    if (acknowledgedDelivery.current) {
      const receipt = acknowledgedDelivery.current;
      const delivery = await api.delivery(id, receipt.message);
      if (delivery.delivery_id !== receipt.delivery || delivery.message_id !== receipt.message || delivery.ticket_id !== id) throw Error("Delivery receipt not confirmed");
      await cache.invalidateQueries({ queryKey: ["ticket-delivery", id] });
    }
    await cache.refetchQueries({ queryKey: ["ticket-conversation", id], type: "active" }, { throwOnError: true });
    await cache.refetchQueries({ queryKey: ["ticket-delivery-choices", id], type: "active" }, { throwOnError: true });
    if (!session.isCurrent()) return;
    if (acknowledgedDelivery.current) setDeliveryReview(null);
    acknowledgedDelivery.current = null;
    setDeliveryAcknowledged(false);
    acknowledgedNote.current = null;
    acknowledgedMessage.current = null;
    setAwaiting(false);
    if (awaiting) setNotice("Alteracao confirmada.");
    await Promise.all(["tickets", "ticket-states", "ticket-activity"].map(key => cache.invalidateQueries({ queryKey: key === "tickets" ? [key] : [key, id] })));
  };
  const write = useTeamWrite(session, async (intent: Intent) => {
    if (intent.kind === "delivery") return { kind: "delivery" as const, receipt: await api.send(id, intent.review.message.id, { participant_id: intent.review.choices.participant!.participant_id, source_id: intent.review.choices.sender!.source_id, ...(intent.review.message.attachments?.length ? { attachment_ids: intent.review.message.attachments.map(file => file.id) } : {}) }, intent.version, intent.key) };
    if (intent.kind === "edit") return { kind: "edit" as const, row: await api.update(id, intent.body, intent.version) };
    if (intent.kind === "note") return { kind: "note" as const, receipt: await api.addNote(id, intent.body, intent.version, intent.key) };
    if (intent.kind === "message") return { kind: "message" as const, receipt: await api.addMessage(id, intent.body, intent.version, intent.key) };
    if (intent.kind === "claim") await api.claim(id, intent.version, intent.key);
    else await api.transition(id, intent.body, intent.version, intent.key);
    return { kind: "receipt" as const };
  }, (result, intent) => {
    setEditor(null); setTarget(""); setReason(""); setTransitionReview(null); setError("");
    if (result.kind === "edit") cache.setQueryData(["ticket", id], result.row);
    if (result.kind === "note") { acknowledgedNote.current = { id: result.receipt.note_id, body: intent.kind === "note" ? intent.body.body_text : "", files: intent.kind === "note" ? intent.files : [] }; setNoteDraft(null); setNoteFiles([]); setNoteError(""); }
    if (result.kind === "message") { acknowledgedMessage.current = { id: result.receipt.message_id, body: intent.kind === "message" ? intent.body.body_text : "", files: intent.kind === "message" ? intent.files : [] }; setMessageDraft(null); setMessageFiles([]); setMessageReview(null); setMessageError(""); }
    if (result.kind === "delivery") { acknowledgedDelivery.current = { message: result.receipt.message_id, delivery: result.receipt.delivery_id }; setDeliveryAcknowledged(true); }
    setAwaiting(true);
    setNotice(result.kind === "delivery" ? "Solicitacao de envio registrada. Atualize o chamado para consultar o estado confirmado." : result.kind === "message" ? "Rascunho salvo, nao enviado. Atualize o chamado antes de continuar." : result.kind === "note" ? "Nota registrada. Atualize o chamado antes de continuar." : "Operacao confirmada. Atualize o chamado antes de continuar.");
    void refresh().then(() => { if (session.isCurrent()) setNotice("Alteracao confirmada."); }).catch(() => { /* The authoritative read owns recovery. */ });
  });
  const reload = async () => {
    await refresh();
    if (session.isCurrent()) { setEditor(null); setTarget(""); setReason(""); setTransitionReview(null); setNoteDraft(null); setNoteFiles([]); setMessageFiles([]); setNoteError(""); setMessageDraft(null); setMessageReview(null); setDeliveryReview(null); setMessageError(""); setError(""); setNotice(""); }
  };
  const fileBusy = messageFilesBusy || noteFilesBusy;
  const parentLocked = fileBusy || write.locked || awaiting || query.isFetching || query.isError;
  const blocked = linksBusy || parentLocked;
  const reviewed = transitionReview ?? row;
  const startTransition = () => {
    if (row && transitionReview === null) setTransitionReview({ version: row.version, status: row.status, allowed_transitions: [...row.allowed_transitions] });
  };
  const transition = () => {
    if (!reviewed || !target || !reviewed.allowed_transitions.includes(target)) { setError("Escolha o proximo estado."); return; }
    if ((["pending_customer", "pending_third_party", "resolved"].includes(target) || (target === "open" && ["resolved", "closed"].includes(reviewed.status))) && !reason.trim()) {
      setError("Informe o motivo desta mudanca."); return;
    }
    setNotice(""); setError("");
    write.submit({ kind: "transition", body: { target_status: target, reason: reason.trim() || null }, version: reviewed.version, key: crypto.randomUUID() });
  };
  return <div className="admin-workspace ticket-workspace">
    <Link className="text-link" href="/service-desk/tickets">Voltar aos chamados</Link>
    <h1 id="ticket-heading" tabIndex={-1}>{row?.subject ?? "Chamado"}</h1>
    {query.isPending && <LoadingRows label="Carregando chamado..." />}
    {query.isError && <ReadError retry={() => void refresh().catch(() => {})}>{query.error instanceof ApiError && query.error.status === 404 ? "Este chamado nao esta disponivel para sua conta." : undefined}</ReadError>}
    {row && <>
      <p className="admin-intro">Chamado {row.number} - {ticketStatuses[row.status]}</p>
      <Button variant="outline" disabled={query.isFetching || write.pending} onClick={() => void refresh().catch(() => {})}>Atualizar chamado</Button>
      {notice && <p role="status" className="read-notice">{notice}</p>}
      <TicketFeedback write={write} reload={reload} verifyLabel={write.current?.kind === "delivery" ? "Verificar solicitacao de envio" : write.current?.kind === "message" ? "Verificar rascunho" : write.current?.kind === "note" ? "Verificar nota interna" : write.current?.kind === "claim" ? "Verificar atribuicao" : write.current?.kind === "transition" ? "Verificar mudanca de estado" : undefined} />
      <div className="admin-plane">
        <section className="admin-section" aria-labelledby="ticket-data-heading">
          <h2 id="ticket-data-heading">Dados do chamado</h2>
          {editor ? <TicketForm key={editor.version} initial={editor} api={api} queues={queues} queue={row.queue_id} client={row.client_id} manage={row.can_assign} actor={session.user} disabled={blocked || !row.can_update}
            submit={body => { setNotice(""); write.submit({ kind: "edit", body: body as TicketPatch, version: editor.version }); }} cancel={() => { setEditor(null); requestAnimationFrame(() => document.getElementById("edit-ticket")?.focus()); }} /> : <>
            <dl className="account-details work-facts">
              <div><dt>Cliente</dt><dd>{row.client_name}</dd></div><div><dt>Fila</dt><dd>{row.queue_name}</dd></div>
              <div><dt>Solicitante</dt><dd>{row.requester_name} - {row.requester_email}{!row.requester_active && " (arquivado)"}</dd></div>
              <div><dt>Categoria</dt><dd>{row.category_name ?? "Sem categoria"}</dd></div>
              <div><dt>Responsavel</dt><dd>{row.assignee_name ?? "Sem responsavel"}</dd></div>
              <div><dt>Prioridade</dt><dd>{ticketPriorities[row.priority]}</dd></div>
              <div><dt>Criado em</dt><dd><time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString("pt-BR")}</time></dd></div>
              {row.resolved_at && <div><dt>Resolvido em</dt><dd>{new Date(row.resolved_at).toLocaleString("pt-BR")}</dd></div>}
              {row.closed_at && <div><dt>Fechado em</dt><dd>{new Date(row.closed_at).toLocaleString("pt-BR")}</dd></div>}
            </dl>
            <p className="field-help">Solicitante com identidade nao verificada.</p>
            <h3 className="work-subheading">Descricao</h3><p className="work-prose">{row.description || "Sem descricao."}</p>
            <div className="action-row">
              {row.can_update && <Button id="edit-ticket" variant="outline" disabled={blocked} onClick={() => { setEditor(row); setNotice(""); }}>Editar chamado</Button>}
              {row.can_claim && <Button disabled={blocked} onClick={() => { setNotice(""); write.submit({ kind: "claim", version: row.version, key: crypto.randomUUID() }); }}>Assumir chamado</Button>}
            </div>
            {!row.can_update && <p className="field-help">Edicao disponivel ao responsavel ou gestor, com cliente, equipe e fila ativos e chamado aberto para alteracoes.</p>}
          </>}
        </section>
      </div>
    </>}
    {query.data && <TicketWorkLinks ticket={query.data} session={session}
      parentAvailable={!!row && !query.isError}
      parentLocked={parentLocked || editor !== null || transitionReview !== null || messageReview !== null || deliveryReview !== null}
      onBusyChange={setLinksBusy} />}
    {row && <>
      <div className="admin-plane">
        <AssignmentRuns ticketId={id} session={session} available={!query.isError} />
        {reviewed && reviewed.allowed_transitions.length > 0 && <section className="admin-section" aria-labelledby="ticket-transition-heading">
          <h2 id="ticket-transition-heading">Mudar estado</h2>
          <form noValidate onSubmit={event => { event.preventDefault(); transition(); }}>
            <fieldset className="work-fields" disabled={blocked || editor !== null}>
              <div className="account-form-grid">
                <div><label htmlFor="ticket-target">Proximo estado</label>
                  <select id="ticket-target" value={target} onChange={event => { startTransition(); setTarget(event.target.value as typeof target); }}>
                    <option value="">Escolha um estado</option>{reviewed.allowed_transitions.map(value => <option key={value} value={value}>{ticketStatuses[value]}</option>)}
                  </select>
                </div>
                <div><label htmlFor="ticket-reason">Motivo</label><textarea id="ticket-reason" rows={3} maxLength={2000} value={reason} onChange={event => { startTransition(); setReason(event.target.value); }} /></div>
              </div>
              {error && <p role="alert" className="field-error">{error}</p>}
              <Button className="work-transition-action" type="submit">Alterar estado</Button>
            </fieldset>
          </form>
        </section>}
        <TicketMessages id={id} api={api} canAdd={row.can_add_message}
          pendingDelivery={deliveryReview && (write.current?.kind === "delivery" || deliveryAcknowledged) ? { messageId: deliveryReview.message.id, acknowledged: deliveryAcknowledged } : null}
          recoveryAvailable={deliveryAcknowledged || write.uncertain || isResourceForbidden(write.error)}
          recoveryBusy={write.pending || query.isFetching || write.reloading}
          recoverDelivery={() => { if (acknowledgedDelivery.current) void refresh().catch(() => {}); else write.verify(); }}
          blocked={blocked || editor !== null || deliveryReview !== null} review={(message, choices) => {
          if (blocked || !row.can_add_message || deliveryReview) return;
          setDeliveryReview({ message, choices, version: row.version, key: crypto.randomUUID() });
          requestAnimationFrame(() => document.getElementById("ticket-delivery-review-heading")?.focus());
        }} />
        {deliveryReview && <TicketDeliveryReview review={deliveryReview} disabled={blocked || !row.can_add_message} cancel={() => setDeliveryReview(null)} confirm={() => {
          if (blocked || !row.can_add_message) return;
          write.submit({ kind: "delivery", review: deliveryReview, version: deliveryReview.version, key: deliveryReview.key });
        }} />}
        {(row.can_add_message || messageDraft !== null || messageReview !== null || messageFilesBusy) && <TicketMessageForm body={messageDraft?.body ?? ""} reviewed={messageReview?.body ?? null} disabled={blocked || editor !== null || !row.can_add_message} error={messageError} reviewedFiles={messageReview?.files ?? []}
          attachments={<AttachmentPicker scope={{ owner: "ticket", id, purpose: "public" }} version={row.version} selected={messageFiles} change={files => { setMessageFiles(files); setMessageDraft({ body: messageDraft?.body ?? "", version: messageDraft?.version ?? row.version }); }} disabled={linksBusy || write.locked || awaiting || query.isFetching || query.isError || editor !== null || messageReview !== null || noteFilesBusy || !row.can_add_message} busyChanged={messageBusyChanged} />}
          change={body => { setMessageDraft({ body, version: messageDraft?.version ?? row.version }); setMessageError(""); }}
          review={() => {
            if (blocked || !row.can_add_message) return;
            const body = messageDraft?.body.trim() ?? "";
            if (!body || Array.from(body).length > 10000 || body.includes("\u0000")) { setMessageError("Use de 1 a 10000 caracteres, sem caracteres nulos."); return; }
            setMessageReview({ body, version: messageDraft!.version, files: [...messageFiles] }); setMessageError("");
            requestAnimationFrame(() => document.getElementById("ticket-message-review-heading")?.focus());
          }}
          cancel={() => { setMessageReview(null); requestAnimationFrame(() => document.getElementById("ticket-message")?.focus()); }}
          submit={() => {
            if (blocked || !row.can_add_message || !messageReview) return;
            setNotice("");
            write.submit({ kind: "message", body: { body_text: messageReview.body, ...(messageReview.files.length ? { attachment_ids: messageReview.files.map(file => file.id) } : {}) }, files: [...messageReview.files], version: messageReview.version, key: crypto.randomUUID() });
          }} />}
        {!row.can_add_message && !messageDraft && !messageReview && !messageFilesBusy && <AttachmentPicker scope={{ owner: "ticket", id, purpose: "public" }} version={row.version} selected={[]} change={() => {}} disabled busyChanged={messageBusyChanged} />}
        {row.can_read_notes && !row.can_add_note && !noteDraft && !noteFilesBusy && !noteFiles.length && <AttachmentPicker scope={{ owner: "ticket", id, purpose: "note" }} version={row.version} selected={[]} change={() => {}} disabled busyChanged={noteBusyChanged} />}
        {row.can_read_notes && <TicketNotes id={id} api={api} />}
        {(row.can_add_note || noteDraft !== null || noteFilesBusy || noteFiles.length > 0) && <TicketNoteForm body={noteDraft?.body ?? ""} disabled={blocked || editor !== null || !row.can_add_note} error={noteError}
          attachments={<AttachmentPicker scope={{ owner: "ticket", id, purpose: "note" }} version={row.version} selected={noteFiles} change={files => { setNoteFiles(files); setNoteDraft({ body: noteDraft?.body ?? "", version: noteDraft?.version ?? row.version }); }} disabled={linksBusy || write.locked || awaiting || query.isFetching || query.isError || editor !== null || messageFilesBusy || !row.can_add_note} busyChanged={noteBusyChanged} />}
          change={body => { setNoteDraft({ body, version: noteDraft?.version ?? row.version }); setNoteError(""); }}
          submit={() => {
            if (blocked || !row.can_add_note || !noteDraft) { setNoteError("Escreva a nota interna."); return; }
            const body = noteDraft.body.trim();
            if (!body || Array.from(body).length > 10000 || body.includes("\u0000")) { setNoteError("Use de 1 a 10000 caracteres, sem caracteres nulos."); return; }
            setNotice(""); setNoteError("");
            write.submit({ kind: "note", body: { body_text: body, ...(noteFiles.length ? { attachment_ids: noteFiles.map(file => file.id) } : {}) }, files: [...noteFiles], version: noteDraft.version, key: crypto.randomUUID() });
          }} />}
        <TicketHistory id={id} api={api} /><TicketActivity id={id} api={api} />
      </div>
    </>}
  </div>;
}
