"use client";

import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, ReadError, usePaging } from "@/components/team-admin/common";
import type { TicketApi } from "@/lib/tickets";

export function TicketMessages({ id, api, canAdd }: { id: string; api: TicketApi; canAdd: boolean }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["ticket-messages", id, paging.cursor], queryFn: ({ signal }) => api.messages(id, paging.cursor, signal) });
  return <section className="admin-section" aria-labelledby="ticket-messages-heading">
    <h2 id="ticket-messages-heading">Respostas</h2>
    <p className="field-help">Rascunhos compartilhados com quem tem acesso a este chamado. Nenhuma resposta foi enviada ao solicitante.</p>
    {!canAdd && <p className="field-help">Rascunhos podem ser salvos pelo responsavel ou gestor, com cliente, equipe e fila ativos e chamado aberto para alteracoes.</p>}
    <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar respostas</Button>
    {query.isPending ? <LoadingRows label="Carregando respostas..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ?
      <ol className="record-list" aria-label="Rascunhos de resposta">{query.data.items.map(message => <li className="team-row" key={message.id}>
        <div className="record-text">
          <strong>{message.author_name}</strong>
          <span className="record-meta">Rascunho - nao enviado</span>
          <time className="record-meta" dateTime={message.created_at}>{new Date(message.created_at).toLocaleString("pt-BR")}</time>
          <p className="work-prose">{message.body_text}</p>
        </div>
      </li>)}</ol> : <p>Nenhum rascunho de resposta nesta pagina.</p>}
    <nav className="paging" aria-label="Paginas de respostas">
      <Button type="button" variant="outline" disabled={query.isFetching || paging.index === 0} onClick={paging.previous}>Respostas anteriores</Button>
      <span>Pagina {paging.index + 1}</span>
      <Button type="button" variant="outline" disabled={query.isFetching || !query.data?.next_cursor} onClick={() => query.data?.next_cursor && paging.next(query.data.next_cursor)}>Proximas respostas</Button>
    </nav>
  </section>;
}

export function TicketMessageForm({ body, reviewed, disabled, error, change, review, cancel, submit }: {
  body: string; reviewed: string | null; disabled: boolean; error: string; change: (body: string) => void;
  review: () => void; cancel: () => void; submit: () => void;
}) {
  return <section className="admin-section" aria-labelledby="ticket-message-compose-heading">
    <h2 id="ticket-message-compose-heading">Preparar resposta</h2>
    <p id="ticket-message-help" className="field-help">Salve um rascunho de resposta, separado das notas internas. Nao sera enviado. Depois de salvo, nao pode ser editado ou removido.</p>
    {reviewed !== null ? <div role="group" aria-labelledby="ticket-message-review-heading">
      <h3 id="ticket-message-review-heading" className="work-subheading" tabIndex={-1}>Revisar rascunho de resposta</h3>
      <p className="field-help">Rascunho - nao enviado. Confira o texto antes de salvar.</p>
      <p className="work-prose">{reviewed}</p>
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
