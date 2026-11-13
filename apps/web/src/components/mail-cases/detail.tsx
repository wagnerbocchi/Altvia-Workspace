"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { IncomingAttachments } from "@/components/attachments";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, ReadError, useTeamWrite, writeError } from "@/components/team-admin/common";
import { ApiError, isResourceForbidden } from "@/lib/http";
import { caseStates, type MailCase, type MailCaseApi, type PromotionReceipt } from "@/lib/mail-cases";
import type { TicketApi } from "@/lib/tickets";
import type { QueueApi } from "@/lib/ticket-queues";
import { MailPromotionForm, type PromotionReview } from "./form";

function ReceivedText({ row }: { row: MailCase }) {
  return <>
    <dl className="account-details work-facts"><div><dt>Cliente</dt><dd>{row.client_name}</dd></div><div><dt>Fila</dt><dd>{row.queue_name}</dd></div><div><dt>Remetente desta mensagem</dt><dd>{row.contact_name} - {row.email_snapshot}</dd></div><div><dt>Recebida em</dt><dd><time dateTime={row.received_at}>{new Date(row.received_at).toLocaleString("pt-BR")}</time></dd></div></dl>
    <p className="field-help">Identidade atestada pelo administrador somente para esta mensagem. Isso nao verifica globalmente o contato ou uma conta.</p>
    {(row.state === "revoked" || row.state === "collision") && <p className="read-notice">A atestacao desta mensagem foi revogada ou entrou em conflito. O texto historico permanece disponivel; consulte o administrador antes de qualquer nova acao.</p>}
    <h3 className="work-subheading">Assunto original recebido</h3><p className="work-prose">{row.subject || "(Sem assunto recebido)"}</p>
    <h3 className="work-subheading" id="received-text-heading">Texto recebido</h3><div className="incoming-text" role="region" aria-labelledby="received-text-heading" tabIndex={0}><p className="work-prose">{row.body_text}</p></div>
  </>;
}

function ConfirmedReceipt({ receipt, api, tickets, session }: { receipt: PromotionReceipt; api: MailCaseApi; tickets: TicketApi; session: WorkspaceSession }) {
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ["mail-case-receipt", receipt.case_id, receipt.ticket_id, receipt.incoming_message_id], queryFn: async () => {
    const row = await api.get(receipt.case_id);
    const ticket = await tickets.get(receipt.ticket_id);
    const incoming = await tickets.incoming(receipt.ticket_id, receipt.incoming_message_id);
    if (row.state === "ready" || row.promotion_receipt?.incoming_message_id !== receipt.incoming_message_id || row.promotion_receipt.ticket_id !== receipt.ticket_id || incoming.id !== receipt.incoming_message_id || incoming.case_id !== row.id || incoming.ticket_id !== ticket.id || incoming.ticket_version > ticket.version || incoming.body_text !== row.body_text || incoming.subject !== row.subject || incoming.email_snapshot !== row.email_snapshot) throw Error("Incoming receipt not confirmed");
    if (session.isCurrent()) {
      cache.setQueryData(["mail-case", row.id], row);
      await Promise.all([cache.invalidateQueries({ queryKey: ["mail-cases"] }), cache.invalidateQueries({ queryKey: ["tickets"] }), cache.invalidateQueries({ queryKey: ["ticket-conversation", ticket.id] }), cache.invalidateQueries({ queryKey: ["ticket", ticket.id] })]);
    }
    return true;
  } });
  return <section className="admin-section" aria-labelledby="mail-receipt-heading"><h2 id="mail-receipt-heading">Resultado da inclusao</h2>
    {query.isPending ? <LoadingRows label="Confirmando mensagem no chamado..." /> : query.isError ? <ReadError retry={() => void query.refetch()}>A inclusao foi registrada, mas ainda nao foi possivel ler o chamado e a mensagem confirmada. Tente consultar novamente; nao crie outra copia.</ReadError> : <p role="status" className="read-notice">Mensagem confirmada na conversa. <Link className="text-link" href={`/service-desk/tickets/${encodeURIComponent(receipt.ticket_id)}`}>Abrir chamado confirmado</Link></p>}
  </section>;
}

export function MailCaseDetail({ id, api, tickets, queues, session }: { id: string; api: MailCaseApi; tickets: TicketApi; queues: QueueApi; session: WorkspaceSession }) {
  const query = useQuery({ queryKey: ["mail-case", id], queryFn: ({ signal }) => api.get(id, signal) });
  const row = query.error instanceof ApiError && query.error.status === 404 ? undefined : query.data;
  const [review, setReview] = useState<PromotionReview | null>(null);
  const [ack, setAck] = useState<PromotionReceipt | null>(null);
  const write = useTeamWrite(session, (intent: PromotionReview) => api.promote(id, intent.body, intent.row.version, intent.key), receipt => { setAck(receipt); void query.refetch(); });
  const reload = async () => { await query.refetch({ throwOnError: true }); if (session.isCurrent()) setReview(null); };
  const blocked = write.locked || ack !== null || query.isFetching || query.isError;
  const displayed = query.error instanceof ApiError && query.error.status === 404 ? undefined : review?.row ?? row;
  const receipt = ack ?? (!write.current && !review ? row?.promotion_receipt : null);
  return <div className="admin-workspace ticket-workspace">
    <Link className="text-link" href="/service-desk/mail-cases">Voltar as mensagens recebidas</Link>
    <h1 id="mail-case-heading" tabIndex={-1}>Mensagem recebida</h1>
    {query.isPending && <LoadingRows label="Carregando mensagem recebida..." />}
    {query.isError && <ReadError retry={() => void query.refetch()}>{query.error instanceof ApiError && query.error.status === 404 ? "Esta mensagem nao esta disponivel para sua conta. Volte a lista para consultar mensagens no seu acesso atual." : undefined}</ReadError>}
    {row && <><p className="admin-intro">{caseStates[row.state]}</p><Button variant="outline" disabled={write.pending || query.isFetching} onClick={() => void query.refetch()}>Atualizar mensagem</Button></>}
    {write.error && <div className="read-error"><p role="alert">{isResourceForbidden(write.error) ? "Seu acesso mudou. A solicitacao original foi preservada. Verifique o resultado com o mesmo pedido apos recuperar o acesso." : writeError(write.error)}</p><div className="action-row">{(write.uncertain || isResourceForbidden(write.error)) && <Button variant="outline" disabled={write.pending || write.reloading} onClick={write.verify}>Verificar inclusao original</Button>}{write.locked && !write.uncertain && <Button variant="outline" disabled={write.pending || write.reloading} onClick={() => void write.reconcile(reload)}>Recarregar e descartar revisao</Button>}</div></div>}
    {write.reloadFailed && <p role="alert" className="error-message">Nao foi possivel atualizar. A solicitacao original continua preservada.</p>}
    <div className="admin-plane">{displayed && <section className="admin-section" aria-labelledby="mail-original-heading"><h2 id="mail-original-heading">Mensagem original e contexto</h2><ReceivedText row={displayed} /></section>}
      <IncomingAttachments files={row?.files} caseId={id} blocked={query.isFetching || query.isError} refresh={() => query.refetch({ throwOnError: true })} />
      {displayed && (receipt ? <ConfirmedReceipt receipt={receipt} api={api} tickets={tickets} session={session} /> : review ? <section className="admin-section" aria-labelledby="mail-review-heading"><h2 id="mail-review-heading" tabIndex={-1}>Revisar inclusao da mensagem</h2><ul>{review.labels.map((label, index) => <li key={index}>{label}</li>)}</ul><p className="field-help">Incluiremos exatamente a mensagem original acima. Nenhum e-mail sera enviado. A atestacao de destinatario para um envio posterior e uma etapa administrativa separada.</p><div className="action-row"><Button disabled={blocked} onClick={() => write.submit(review)}>{review.body.action === "create" ? "Confirmar criacao" : "Confirmar inclusao"}</Button><Button variant="outline" disabled={blocked} onClick={() => setReview(null)}>Voltar a revisao</Button></div></section> : row && (row.can_create || row.can_append) ? <MailPromotionForm key={row.version} row={row} api={tickets} queues={queues} actor={session.user} disabled={blocked} submit={value => { setReview(value); requestAnimationFrame(() => document.getElementById("mail-review-heading")?.focus()); }} /> : <section className="admin-section"><h2>Consulta da mensagem</h2><p>{row?.state === "ready" ? "Nao ha acao disponivel para sua conta nas condicoes atuais. Consulte o responsavel ou gestor desta fila para revisar a mensagem; atualize apos uma mudanca de acesso ou elegibilidade." : "Esta mensagem nao permite nova inclusao. Consulte o administrador para revisar a atestacao ou o conflito; o historico ja registrado e preservado."}</p></section>)}
    </div>
  </div>;
}
