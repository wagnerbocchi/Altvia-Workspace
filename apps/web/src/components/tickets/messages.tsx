"use client";

import type { ReactNode } from "react";
import { AttachmentReview, LinkedAttachments } from "@/components/attachments";
import type { AttachmentSummary } from "@/lib/attachments";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, ReadError, usePaging } from "@/components/team-admin/common";
import type { DeliveryChoices, TicketApi, TicketMessage } from "@/lib/tickets";

const deliveryLabels = { draft: "Rascunho - nao enviado", queued: "Na fila de envio", preparing: "Preparando envio", transmitting: "Transmitindo ao servidor de e-mail", accepted: "Aceito pelo servidor de e-mail", failed: "Envio falhou", uncertain: "Resultado do envio incerto" };

function DeliveryStatus({ id, message, api }: { id: string; message: TicketMessage; api: TicketApi }) {
  const query = useQuery({ queryKey: ["ticket-delivery", id, message.id], queryFn: ({ signal }) => api.delivery(id, message.id, signal), enabled: message.delivery_status !== "draft" });
  const status = query.data?.state ?? message.delivery_status;
  const errors: Record<string, string> = { permanent: "O servidor recusou a mensagem.", temporary: "O servidor pediu para aguardar; o sistema fara novas tentativas limitadas.", transport: "A conexao segura nao foi concluida; o sistema fara novas tentativas limitadas.", eligibility_revoked: "A autorizacao ou a elegibilidade mudou antes do envio.", retry_exhausted: "O limite de tentativas foi atingido.", data_unknown: "O resultado no servidor precisa de verificacao administrativa." };
  return <div>
    <span className="record-meta">{deliveryLabels[status]}</span>
    {status === "accepted" && <p className="field-help">O servidor aceitou a mensagem. Isso nao confirma a entrega ao destinatario.</p>}
    {status === "failed" && <p className="field-help">Nao foi possivel concluir este envio. Solicite analise ao administrador; esta resposta nao sera reenviada por esta tela.</p>}
    {status === "uncertain" && <p className="field-help">O servidor pode ter aceitado a mensagem. Nao envie outra copia. Um administrador precisa conferir o resultado.</p>}
    {query.data?.last_error_code && errors[query.data.last_error_code] && <p className="field-help">{errors[query.data.last_error_code]}</p>}
    {query.data && <p className="record-meta">Tentativas: {query.data.attempts}{query.data.accepted_at && ` - Aceite em ${new Date(query.data.accepted_at).toLocaleString("pt-BR")}`}</p>}
    {message.delivery_status !== "draft" && <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar estado do envio</Button>}
    {query.isError && <ReadError retry={() => void query.refetch()}>Nao foi possivel consultar o envio. O ultimo estado conhecido continua exibido; nao crie outra copia.</ReadError>}
  </div>;
}

export type DeliveryReview = { message: TicketMessage; choices: DeliveryChoices; version: number; key: string };
export function TicketDeliveryReview({ review, disabled, confirm, cancel }: { review: DeliveryReview; disabled: boolean; confirm: () => void; cancel: () => void }) {
  return <section className="admin-section" aria-labelledby="ticket-delivery-review-heading">
    <h2 id="ticket-delivery-review-heading" tabIndex={-1}>Revisar envio de resposta</h2>
    <dl className="account-details work-facts"><div><dt>De</dt><dd>{review.choices.sender?.from_email}</dd></div><div><dt>Para</dt><dd>{review.choices.participant?.display_name} - {review.choices.participant?.email}</dd></div></dl>
    <p className="field-help">Destinatario atestado somente para este chamado. Isso nao verifica sua conta ou contato em outros contextos.</p>
    <h3 className="work-subheading">Texto salvo que sera enviado</h3><p className="work-prose">{review.message.body_text}</p>
    <AttachmentReview files={review.message.attachments} />
    <p className="field-help">Confirmar coloca esta resposta na fila de envio. Notas internas nao fazem parte da mensagem.</p>
    <div className="action-row"><Button disabled={disabled} onClick={confirm}>Confirmar envio</Button><Button variant="outline" disabled={disabled} onClick={cancel}>Cancelar revisao de envio</Button></div>
  </section>;
}

export function TicketMessages({ id, api, canAdd, blocked, review, pendingDelivery, recoveryBusy, recoveryAvailable, recoverDelivery }: {
  id: string; api: TicketApi; canAdd: boolean; blocked: boolean; review: (message: TicketMessage, choices: DeliveryChoices) => void;
  pendingDelivery: { messageId: string; acknowledged: boolean } | null; recoveryBusy: boolean; recoveryAvailable: boolean; recoverDelivery: () => void;
}) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["ticket-conversation", id, paging.cursor], queryFn: ({ signal }) => api.conversation(id, paging.cursor, signal) });
  const choices = useQuery({ queryKey: ["ticket-delivery-choices", id], queryFn: ({ signal }) => api.deliveryChoices(id, signal) });
  return <section className="admin-section" aria-labelledby="ticket-messages-heading">
    <h2 id="ticket-messages-heading">Conversa</h2>
    <p className="field-help">Mensagens recebidas e respostas publicas, em ordem de registro no chamado. Salvar um rascunho nao envia e-mail. Cada envio exige revisao e confirmacao.</p>
    {choices.isError && <ReadError retry={() => void choices.refetch()}>Nao foi possivel consultar as opcoes de envio.</ReadError>}
    {choices.data && (!choices.data.can_send || !choices.data.sender || !choices.data.participant) && <p className="field-help">{!canAdd ? "Sua conta pode consultar respostas, mas nao enviar neste chamado." : !choices.data.sender ? "O envio precisa de um remetente configurado pelo administrador para esta fila." : !choices.data.participant ? "O solicitante precisa de uma atestacao valida para este chamado antes do envio. Consulte o administrador." : "O envio nao esta disponivel nas condicoes atuais do chamado."}</p>}
    {!canAdd && <p className="field-help">Rascunhos podem ser salvos pelo responsavel ou gestor, com cliente, equipe e fila ativos e chamado aberto para alteracoes.</p>}
    <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar conversa</Button>
    {query.isPending ? <LoadingRows label="Carregando conversa..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ?
      <ol className="record-list" aria-label="Conversa do chamado">{query.data.items.map(item => item.kind === "incoming" ? <li className="team-row" key={item.id}><div className="record-text"><strong>Recebida de {item.contact_name}</strong><span className="record-meta">{item.email_snapshot}</span><time className="record-meta" dateTime={item.received_at}>{new Date(item.received_at).toLocaleString("pt-BR")}</time><p className="field-help">Identidade atestada somente para esta mensagem; o contato e a conta nao estao globalmente verificados.</p>{item.invalidation_warning && <p className="read-notice">A atestacao desta mensagem foi revogada ou entrou em conflito. O registro historico foi preservado; consulte o administrador.</p>}<h3 className="work-subheading">{item.subject || "(Sem assunto recebido)"}</h3><div className="incoming-text" role="region" aria-label={`Texto recebido de ${item.contact_name}`} tabIndex={0}><p className="work-prose">{item.body_text}</p></div></div></li> : <OutboundMessage key={item.message.id} message={item.message} id={id} api={api} canAdd={canAdd} choices={choices} blocked={blocked} review={review} pendingDelivery={pendingDelivery} recoveryBusy={recoveryBusy} recoveryAvailable={recoveryAvailable} recoverDelivery={recoverDelivery} />)}</ol> : <p>Nenhuma mensagem nesta pagina.</p>}
    <nav className="paging" aria-label="Paginas da conversa">
      <Button type="button" variant="outline" disabled={query.isFetching || paging.index === 0} onClick={paging.previous}>Mensagens anteriores</Button>
      <span>Pagina {paging.index + 1}</span>
      <Button type="button" variant="outline" disabled={query.isFetching || !query.data?.next_cursor} onClick={() => query.data?.next_cursor && paging.next(query.data.next_cursor)}>Proximas mensagens</Button>
    </nav>
  </section>;
}

function OutboundMessage({ message, id, api, canAdd, choices, blocked, review, pendingDelivery, recoveryBusy, recoveryAvailable, recoverDelivery }: {
  message: TicketMessage; id: string; api: TicketApi; canAdd: boolean; choices: ReturnType<typeof useQuery<DeliveryChoices>>; blocked: boolean; review: (message: TicketMessage, choices: DeliveryChoices) => void; pendingDelivery: { messageId: string; acknowledged: boolean } | null; recoveryBusy: boolean; recoveryAvailable: boolean; recoverDelivery: () => void;
}) {
  return <li className="team-row" key={message.id}>
        <div className="record-text">
          <strong>{message.author_name}</strong>
          {pendingDelivery?.messageId === message.id ? <div role="status">
            <span className="record-meta">{pendingDelivery.acknowledged ? "Solicitacao registrada; estado do envio aguardando confirmacao." : "Solicitacao sem resultado confirmado; estado do envio aguardando verificacao."}</span>
            <p className="field-help">Nao crie outra copia. Recupere o resultado desta solicitacao antes de continuar.</p>
            {recoveryAvailable && <Button variant="outline" disabled={recoveryBusy} onClick={recoverDelivery}>{pendingDelivery.acknowledged ? "Confirmar estado deste envio" : "Recuperar resultado deste envio"}</Button>}
          </div> : <DeliveryStatus id={id} message={message} api={api} />}
          <time className="record-meta" dateTime={message.created_at}>{new Date(message.created_at).toLocaleString("pt-BR")}</time>
          <p className="work-prose">{message.body_text}</p><LinkedAttachments files={message.attachments} />
          {message.delivery_status === "draft" && pendingDelivery?.messageId !== message.id && canAdd && choices.data?.can_send && choices.data.sender && choices.data.participant && <Button variant="outline" disabled={blocked || choices.isFetching || choices.isError} onClick={() => review(message, choices.data!)}>Revisar envio</Button>}
        </div>
      </li>;
}

export function TicketMessageForm({ body, reviewed, disabled, error, change, review, cancel, submit, attachments, reviewedFiles }: {
  body: string; reviewed: string | null; disabled: boolean; error: string; change: (body: string) => void; attachments: ReactNode; reviewedFiles: readonly AttachmentSummary[];
  review: () => void; cancel: () => void; submit: () => void;
}) {
  return <section className="admin-section" aria-labelledby="ticket-message-compose-heading">
    <h2 id="ticket-message-compose-heading">Preparar resposta</h2>
    <p id="ticket-message-help" className="field-help">Salve um rascunho de resposta, separado das notas internas. Nao sera enviado. Depois de salvo, nao pode ser editado ou removido.</p>
    {attachments}
    {reviewed !== null ? <div role="group" aria-labelledby="ticket-message-review-heading">
      <h3 id="ticket-message-review-heading" className="work-subheading" tabIndex={-1}>Revisar rascunho de resposta</h3>
      <p className="field-help">Rascunho - nao enviado. Confira o texto antes de salvar.</p>
      <p className="work-prose">{reviewed}</p><AttachmentReview files={reviewedFiles} />
      <div className="action-row">
        <Button disabled={disabled} onClick={submit}>Salvar rascunho</Button>
        <Button variant="outline" disabled={disabled} onClick={cancel}>Voltar ao texto</Button>
      </div>
    </div> : <form noValidate onSubmit={event => { event.preventDefault(); review(); }}>
      <fieldset className="work-fields" disabled={disabled}>
        <label htmlFor="ticket-message">Texto da resposta</label>
        <textarea id="ticket-message" rows={5} value={body} onChange={event => change(event.target.value)} aria-invalid={!!error} aria-describedby="ticket-message-help ticket-message-error" />
        <p id="ticket-message-error" className="field-error" role="alert">{error}</p>
        <Button type="submit">Revisar rascunho</Button>
      </fieldset>
    </form>}
  </section>;
}
