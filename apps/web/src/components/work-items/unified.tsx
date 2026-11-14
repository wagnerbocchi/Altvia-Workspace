"use client";

import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import { ticketStatuses } from "@/lib/tickets";
import { dueLabel, workPriorities, workStatuses } from "@/lib/work-items";
import type { UnifiedWorkApi, UnifiedWorkFilters, UnifiedWorkPage } from "@/lib/unified-work";

type Values = {
  q: string; kind: NonNullable<UnifiedWorkFilters["kind"]>;
  priority: NonNullable<UnifiedWorkFilters["priority"]> | "";
  work_status: NonNullable<UnifiedWorkFilters["work_status"]> | "";
  ticket_status: NonNullable<UnifiedWorkFilters["ticket_status"]> | "";
};
const initial: Values = { q: "", kind: "all", priority: "", work_status: "", ticket_status: "" };
function UnifiedFilters({ apply }: { apply: (filters: UnifiedWorkFilters) => void }) {
  const { register, reset, handleSubmit } = useForm<Values>({ defaultValues: initial });
  return <form className="task-filters unified-filters" aria-label="Filtros do meu trabalho" onSubmit={handleSubmit(values => apply({
    q: values.q.trim(), kind: values.kind, priority: values.priority || undefined,
    work_status: values.work_status || undefined, ticket_status: values.ticket_status || undefined,
  }))}>
    <div className="field task-search"><label htmlFor="personal-search">Buscar no meu trabalho</label><input id="personal-search" type="search" maxLength={200} {...register("q")} aria-describedby="personal-search-help" /><p className="field-help" id="personal-search-help">Busca por palavras no título e na descrição de tarefas e chamados.</p></div>
    <div className="field"><label htmlFor="personal-kind">Registros</label><select id="personal-kind" {...register("kind")}><option value="all">Tarefas e chamados</option><option value="work_item">Tarefas com seus chamados</option><option value="ticket">Chamados atribuídos a mim</option></select></div>
    <details className="task-filter-details"><summary>Filtros adicionais</summary><div className="task-filter-options">
      <div className="field"><label htmlFor="personal-priority">Prioridade</label><select id="personal-priority" {...register("priority")}><option value="">Todas as prioridades</option>{Object.entries(workPriorities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
      <div className="field"><label htmlFor="personal-work-status">Estado da tarefa</label><select id="personal-work-status" {...register("work_status")}><option value="">Todos os estados</option>{Object.entries(workStatuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
      <div className="field"><label htmlFor="personal-ticket-status">Estado do chamado</label><select id="personal-ticket-status" {...register("ticket_status")}><option value="">Todos os estados</option>{Object.entries(ticketStatuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
    </div></details>
    <div className="action-row task-filter-actions"><Button type="submit">Aplicar filtros</Button><Button type="button" variant="outline" onClick={() => { reset(initial); apply({}); }}>Limpar filtros</Button></div>
  </form>;
}

function UnifiedRows({ items }: { items: UnifiedWorkPage["items"] }) {
  return <ul className="record-list work-records" aria-label="Fila unificada">{items.map(row => <li className="team-row work-row" key={`${row.kind}:${row.id}`}>
    {row.kind === "work_item" ? <>
      <div className="record-text"><Link className="text-link" href={`/work-items/${encodeURIComponent(row.id)}`}>{row.title}</Link>
        <span className="record-meta">Tarefa · <Link className="text-link" href={`/projects/${encodeURIComponent(row.project_id)}`}>{row.project_name}</Link>{row.work_type === "ongoing" ? " · Trabalho contínuo" : ""}</span>
        {!!row.linked_tickets.length && <div className="unified-origins" role="group" aria-label="Chamados representados nesta tarefa">{row.linked_tickets.map(ticket => <div key={ticket.id} className="record-meta">
          <Link className="text-link" href={`/service-desk/tickets/${encodeURIComponent(ticket.id)}`}>Chamado #{ticket.number} · {ticket.subject}</Link><span className="record-meta">Estado do chamado: {ticketStatuses[ticket.status]}</span>
        </div>)}</div>}
        {row.has_more_linked_tickets && <Link className="text-link record-meta" href={`/work-items/${encodeURIComponent(row.id)}`}>Consultar demais chamados vinculados</Link>}
      </div>
      <div className="record-cell"><span className="record-status" data-state={row.status}>{workStatuses[row.status]}</span><span className="record-meta">Prioridade da tarefa: {workPriorities[row.priority]}</span></div>
      <div className="record-cell">{dueLabel(row)}</div>
    </> : <>
      <div className="record-text"><Link className="text-link" href={`/service-desk/tickets/${encodeURIComponent(row.id)}`}>{row.subject}</Link><span className="record-meta">Chamado #{row.number}</span></div>
      <div className="record-cell"><span className="record-status" data-state={row.status}>{ticketStatuses[row.status]}</span><span className="record-meta">Prioridade do chamado: {workPriorities[row.priority]}</span></div>
      <div className="record-cell">Fila: {row.queue_name}</div>
    </>}
  </li>)}</ul>;
}

function UnifiedResults({ api, filters }: { api: UnifiedWorkApi; filters: UnifiedWorkFilters }) {
  const paging = usePaging();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["my-work-unified", filters, paging.cursor], queryFn: ({ signal }) => api.list(paging.cursor, signal, filters) });
  return <section aria-labelledby="unified-results-heading"><div className="section-heading"><h2 id="unified-results-heading">Fila unificada</h2>
    <Button variant="outline" disabled={query.isFetching} onClick={() => { paging.reset(); void client.invalidateQueries({ queryKey: ["my-work-unified"] }); }}>Atualizar fila</Button></div>
    <p className="field-help">Tarefas em que você é responsável ou envolvido e chamados atribuídos a você. Chamados vinculados a uma tarefa desta fila aparecem nela, sem outra linha. Os estados permanecem independentes.</p>
    {query.isPending ? <LoadingRows label="Carregando meu trabalho..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ? <UnifiedRows items={query.data.items} /> : <p>Nenhum registro corresponde aos filtros.</p>}
    {!query.isError && <Paging paging={paging} next={query.data?.next_cursor} label="registros" disabled={query.isFetching} />}
  </section>;
}

export function UnifiedPersonalWork({ api }: { api: UnifiedWorkApi }) {
  const [filters, setFilters] = useState<UnifiedWorkFilters>({});
  return <section className="admin-section"><UnifiedFilters apply={setFilters} /><UnifiedResults key={JSON.stringify(filters)} api={api} filters={filters} /></section>;
}
