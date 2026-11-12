"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, ReadError, usePaging } from "@/components/team-admin/common";
import { caseStates, type MailCase, type MailCaseApi } from "@/lib/mail-cases";

export function MailCaseDirectory({ api }: { api: MailCaseApi }) {
  const [state, setState] = useState<MailCase["state"] | "">("ready");
  const paging = usePaging();
  const query = useQuery({ queryKey: ["mail-cases", state, paging.cursor], queryFn: ({ signal }) => api.list(state, paging.cursor, signal) });
  return <div className="admin-workspace ticket-workspace">
    <Link className="text-link" href="/service-desk/tickets">Voltar aos chamados</Link>
    <h1 id="mail-cases-heading" tabIndex={-1}>Mensagens recebidas</h1>
    <p className="admin-intro">Mensagens publicadas apos atestacao individual pelo administrador, dentro do seu acesso a clientes e filas. Receber uma mensagem nao cria um chamado nem envia resposta.</p>
    <div className="admin-plane"><section className="admin-section" aria-labelledby="mail-list-heading">
      <div className="inline-form mail-case-toolbar"><div className="field"><label htmlFor="mail-state">Situacao</label><select id="mail-state" value={state} onChange={event => { setState(event.target.value as typeof state); paging.reset(); }}><option value="">Todas as situacoes</option>{Object.entries(caseStates).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div><Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar mensagens</Button></div>
      <h2 id="mail-list-heading">Mensagens disponiveis</h2>
      {query.isPending ? <LoadingRows label="Carregando mensagens recebidas..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ? <ul className="record-list" aria-label="Mensagens recebidas">{query.data.items.map(row => <li className="team-row" key={row.id}><div className="record-text"><Link className="text-link" href={`/service-desk/mail-cases/${encodeURIComponent(row.id)}`}>{row.subject || "Mensagem sem assunto"}</Link><span className="record-meta">{row.contact_name} - {row.client_name} - {row.queue_name}</span><span className="record-meta">{caseStates[row.state]} - Recebida em {new Date(row.received_at).toLocaleString("pt-BR")}</span></div></li>)}</ul> : <p>Nenhuma mensagem disponivel nesta situacao. Escolha outra situacao ou atualize apos o administrador publicar uma mensagem atestada para seu cliente e fila.</p>}
      <nav className="paging" aria-label="Paginas de mensagens recebidas"><Button variant="outline" disabled={query.isFetching || paging.index === 0} onClick={paging.previous}>Mensagens anteriores</Button><span>Pagina {paging.index + 1}</span><Button variant="outline" disabled={query.isFetching || !query.data?.next_cursor} onClick={() => query.data?.next_cursor && paging.next(query.data.next_cursor)}>Proximas mensagens</Button></nav>
    </section></div>
  </div>;
}
