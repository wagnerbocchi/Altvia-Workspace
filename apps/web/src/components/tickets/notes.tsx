"use client";

import type { ReactNode } from "react";
import { LinkedAttachments } from "@/components/attachments";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import type { TicketApi } from "@/lib/tickets";

export function TicketNotes({ id, api }: { id: string; api: TicketApi }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["ticket-notes", id, paging.cursor], queryFn: ({ signal }) => api.notes(id, paging.cursor, signal) });
  return <section className="admin-section" aria-labelledby="ticket-notes-heading">
    <h2 id="ticket-notes-heading">Notas internas</h2>
    <p className="field-help">Conteudo privado. Visivel somente a contas com acesso explicito a notas e a este chamado.</p>
    <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar notas</Button>
    {query.isPending ? <LoadingRows label="Carregando notas..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ?
      <ul className="record-list" aria-label="Notas internas">{query.data.items.map(note => <li className="team-row" key={note.id}>
        <div className="record-text">
          <strong>{note.author_name}</strong>
          <time className="record-meta" dateTime={note.created_at}>{new Date(note.created_at).toLocaleString("pt-BR")}</time>
          <p className="work-prose">{note.body_text}</p><LinkedAttachments files={note.attachments} />
        </div>
      </li>)}</ul> : <p>Nenhuma nota interna nesta pagina.</p>}
    <Paging paging={paging} next={query.data?.next_cursor} label="notas" disabled={query.isFetching} />
  </section>;
}

export function TicketNoteForm({ body, disabled, error, change, submit, attachments }: {
  body: string; disabled: boolean; error: string; change: (value: string) => void; submit: () => void; attachments: ReactNode;
}) {
  return <section className="admin-section" aria-labelledby="ticket-compose-heading">
    <h2 id="ticket-compose-heading">Registrar nota interna</h2>
    <p id="ticket-note-help" className="field-help">Somente uso interno. Nao sera enviada ao solicitante. A nota registrada nao pode ser editada ou removida.</p>
    {attachments}
    <form noValidate onSubmit={event => { event.preventDefault(); submit(); }}>
      <fieldset className="work-fields" disabled={disabled}>
        <label htmlFor="ticket-note">Nota interna</label>
        <textarea id="ticket-note" rows={5} value={body} onChange={event => change(event.target.value)} aria-invalid={!!error} aria-describedby="ticket-note-help ticket-note-error" />
        <p id="ticket-note-error" className="field-error" role="alert">{error}</p>
        <Button type="submit">Registrar nota interna</Button>
      </fieldset>
    </form>
  </section>;
}
