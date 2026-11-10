"use client";

import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import { type WorkApi, type WorkFilters, type WorkRecord, dueLabel, workPriorities, workStatuses } from "@/lib/work-items";

type Values = {
  q: string; status: NonNullable<WorkFilters["status"]> | "";
  priority: NonNullable<WorkFilters["priority"]> | "";
  work_type: NonNullable<WorkFilters["work_type"]> | "";
  involvement: "" | "owner" | "involved" | "unassigned";
  due_presence: NonNullable<WorkFilters["due_presence"]> | "";
};
const initial: Values = { q: "", status: "", priority: "", work_type: "", involvement: "", due_presence: "" };
export function TaskFilters({ actor, onApply, personal = false }: { actor: string; onApply: (filters: WorkFilters) => void; personal?: boolean }) {
  const { register, handleSubmit, reset } = useForm<Values>({ defaultValues: initial });
  return <form className="task-filters" aria-label="Filtros de tarefas" onSubmit={handleSubmit(values => {
    onApply({ q: values.q.trim(), status: values.status || undefined, priority: values.priority || undefined,
      work_type: values.work_type || undefined, due_presence: values.due_presence || undefined,
      owner_id: values.involvement === "owner" ? actor : undefined,
      involved_user_id: values.involvement === "involved" ? actor : undefined,
      unassigned: values.involvement === "unassigned" || undefined });
  })}>
    <div className="field task-search"><label htmlFor="task-search">Buscar tarefas</label><input id="task-search" type="search" maxLength={200} {...register("q")} aria-describedby="task-search-help" /><p id="task-search-help" className="field-help">Busca por palavras no título e na descrição. Use aspas para uma frase.</p></div>
    <details className="task-filter-details"><summary>Filtros adicionais</summary><div className="task-filter-options">
    <div className="field"><label htmlFor="task-filter-status">Estado da tarefa</label><select id="task-filter-status" {...register("status")}><option value="">Todos os estados</option>{Object.entries(workStatuses).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></div>
    <div className="field"><label htmlFor="task-filter-priority">Prioridade da tarefa</label><select id="task-filter-priority" {...register("priority")}><option value="">Todas as prioridades</option>{Object.entries(workPriorities).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></div>
    <div className="field"><label htmlFor="task-filter-type">Tipo de tarefa</label><select id="task-filter-type" {...register("work_type")}><option value="">Todos os tipos</option><option value="one_off">Pontual</option><option value="ongoing">Contínua</option></select></div>
    {!personal && <div className="field"><label htmlFor="task-filter-involvement">Vínculo comigo</label><select id="task-filter-involvement" {...register("involvement")}><option value="">Qualquer vínculo</option><option value="owner">Sou responsável</option><option value="involved">Sou responsável ou envolvido</option><option value="unassigned">Sem responsável</option></select></div>}
    <div className="field"><label htmlFor="task-filter-due">Prazo da tarefa</label><select id="task-filter-due" {...register("due_presence")}><option value="">Com ou sem prazo</option><option value="dated">Com prazo</option><option value="undated">Sem prazo</option></select></div>
    </div></details>
    <div className="action-row task-filter-actions"><Button type="submit">Aplicar filtros</Button><Button type="button" variant="outline" onClick={() => { reset(initial); onApply({}); }}>Limpar filtros</Button></div>
  </form>;
}

function WorkRows({ rows, label }: { rows: WorkRecord[]; label: string }) {
  return <ul className="record-list" aria-label={label}>{rows.map(row => <li className="team-row" key={row.id}><div className="record-text"><Link className="text-link" href={`/work-items/${encodeURIComponent(row.id)}`}>{row.title}</Link><span className="record-meta">{workStatuses[row.status]} · Prioridade {workPriorities[row.priority].toLocaleLowerCase("pt-BR")}{row.parent_id ? " · Subtarefa" : ""}</span><span className="record-meta">{row.owner_name ?? "Sem responsável"} · {dueLabel(row)}</span>{row.work_type === "ongoing" && <span className="record-meta">Trabalho contínuo</span>}</div></li>)}</ul>;
}
function ProjectResults({ project, api, filters, status, refresh }: { project: string; api: WorkApi; filters: WorkFilters; status?: NonNullable<WorkFilters["status"]>; refresh: () => void }) {
  const paging = usePaging();
  const applied = status ? { ...filters, status } : filters;
  const query = useQuery({ queryKey: ["work-items", project, "discovery", applied, paging.cursor], queryFn: ({ signal }) => api.list(project, paging.cursor, signal, applied) });
  const heading = status ? workStatuses[status] : "Tarefas do projeto";
  return <section className={status ? "task-column" : "task-list-results"} aria-labelledby={`task-results-${status ?? "list"}`}>
    {status && <h3 id={`task-results-${status}`}>{heading}</h3>}
    {!status && <h3 id="task-results-list" className="sr-only">{heading}</h3>}
    <Button variant="outline" disabled={query.isFetching} onClick={() => { paging.reset(); refresh(); }}>Atualizar tarefas</Button>
    {query.isPending ? <LoadingRows label={`Carregando ${heading.toLocaleLowerCase("pt-BR")}...`} /> : query.isError ? <ReadError retry={refresh} /> : query.data.items.length ? <WorkRows rows={query.data.items} label={status ? `Tarefas: ${heading}` : heading} /> : <p>{status ? "Nenhuma tarefa nesta coluna." : "Nenhuma tarefa corresponde aos filtros."}</p>}
    {!query.isError && <Paging paging={paging} next={query.data?.next_cursor} label="tarefas" disabled={query.isFetching} />}
  </section>;
}
export function ProjectDiscovery({ project, api, actor, refresh }: { project: string; api: WorkApi; actor: string; refresh: () => void }) {
  const [filters, setFilters] = useState<WorkFilters>({});
  const [view, setView] = useState<"list" | "board">("list");
  const statuses = filters.status ? [filters.status] : Object.keys(workStatuses) as NonNullable<WorkFilters["status"]>[];
  return <section className="admin-section" aria-labelledby="work-directory-heading"><h2 id="work-directory-heading">Tarefas do projeto</h2>
    <TaskFilters actor={actor} onApply={setFilters} />
    <div className="action-row task-views" role="group" aria-label="Visualização de tarefas"><Button variant="outline" aria-pressed={view === "list"} onClick={() => setView("list")}>Lista</Button><Button variant="outline" aria-pressed={view === "board"} onClick={() => setView("board")}>Quadro</Button></div>
    <p className="field-help">Resultados dos filtros aplicados. Abra uma tarefa para consultar ou alterar seu estado.</p>
    {view === "list" ? <ProjectResults key={`list:${JSON.stringify(filters)}`} project={project} api={api} filters={filters} refresh={refresh} /> : <div className="task-board" key={JSON.stringify(filters)}>{statuses.map(status => <ProjectResults key={status} status={status} project={project} api={api} filters={filters} refresh={refresh} />)}</div>}
  </section>;
}

function PersonalResults({ api, filters }: { api: WorkApi; filters: WorkFilters }) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["my-work", filters, paging.cursor], queryFn: ({ signal }) => api.mine(paging.cursor, signal, filters) });
  return <section aria-labelledby="personal-results-heading"><h2 id="personal-results-heading">Minhas tarefas</h2>
    <Button variant="outline" disabled={query.isFetching} onClick={() => { paging.reset(); void query.refetch(); }}>Atualizar tarefas</Button>
    {query.isPending ? <LoadingRows label="Carregando minhas tarefas..." /> : query.isError ? <ReadError retry={() => void query.refetch()} /> : query.data.items.length ? <ul className="record-list" aria-label="Minhas tarefas">{query.data.items.map(row => <li className="team-row" key={row.id}><div className="record-text"><Link className="text-link" href={`/work-items/${encodeURIComponent(row.id)}`}>{row.title}</Link><span className="record-meta">{workStatuses[row.status]} · Prioridade {workPriorities[row.priority].toLocaleLowerCase("pt-BR")}{row.work_type === "ongoing" ? " · Trabalho contínuo" : ""}</span><span className="record-meta">{dueLabel(row)}</span><Link className="text-link record-meta" href={`/projects/${encodeURIComponent(row.project_id)}`}>{row.project_name}</Link></div></li>)}</ul> : <p>Nenhuma tarefa sua corresponde aos filtros. Tarefas em que você é responsável ou envolvido aparecem aqui quando o projeto está liberado para sua conta.</p>}
    {!query.isError && <Paging paging={paging} next={query.data?.next_cursor} label="tarefas" disabled={query.isFetching} />}
  </section>;
}
export function PersonalWork({ api, actor }: { api: WorkApi; actor: string }) {
  const [filters, setFilters] = useState<WorkFilters>({});
  return <div className="admin-workspace task-discovery-workspace"><div className="action-row"><Link className="text-link" href="/">Minha conta</Link><Link className="text-link" href="/projects">Projetos</Link></div>
    <h1 id="my-work-heading" tabIndex={-1}>Meu trabalho</h1><p className="admin-intro">Tarefas em que você é responsável ou envolvido, sem duplicação. Inclui todos os estados até você aplicar um filtro. Tickets serão incluídos em uma próxima entrega.</p>
    <div className="admin-plane"><section className="admin-section"><TaskFilters actor={actor} onApply={setFilters} personal /><PersonalResults key={JSON.stringify(filters)} api={api} filters={filters} /></section></div>
  </div>;
}
