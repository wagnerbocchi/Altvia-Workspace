"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import type { WorkspaceSession } from "@/components/workspace-session";
import { createQueueApi } from "@/lib/ticket-queues";
import { createSlaApi, type Calendar, type CalendarSummary, type Policy, type PolicyCreate, type PolicyCalendar } from "@/lib/sla";
import { workPriorities } from "@/lib/work-items";
import { ticketStatuses } from "@/lib/tickets";
import { clock, weekdays } from "./calendars";

const positive = z.string().regex(/^[1-9][0-9]*$/, "Informe minutos inteiros positivos.").refine(value => Number(value) <= 525600, "Use ate 525600 minutos.");
const fields = z.object({ name: z.string().trim().min(1, "Informe o nome.").max(160), category_id: z.string(), priority: z.enum(["", "low", "medium", "high", "critical"]), first_response: positive, resolution: positive,
  approach: z.string().regex(/^(0|[1-9][0-9]*)$/, "Informe minutos inteiros, incluindo zero.").refine(value => Number(value) <= 525600, "Use ate 525600 minutos."),
  pauses: z.array(z.enum(["pending_customer", "pending_third_party"])),
});
type Fields = z.infer<typeof fields>;
export type PolicyBody = Omit<PolicyCreate, "client_id">;

export function CalendarFacts({ row }: { row: Calendar | PolicyCalendar }) {
  return <div><p><strong>{row.name}</strong> - revisao {row.version} - {row.timezone}{"active" in row ? ` - ${row.active ? "Ativo" : "Desativado"}` : ""}</p>
    <ul>{row.windows.map((window, index) => <li key={index}>{weekdays[window.weekday]}: {clock(window.start_minute)} a {clock(window.end_minute)}</li>)}</ul>
    <p>{row.holidays.length ? `${row.holidays.length} datas sem atendimento nesta revisao.` : "Nenhum feriado nesta revisao."}</p>
    {row.holidays.length > 0 && <details><summary>Ver datas sem atendimento</summary><ul>{row.holidays.map(holiday => <li key={holiday.date}>{holiday.date}{holiday.label ? ` - ${holiday.label}` : ""}</li>)}</ul></details>}
  </div>;
}
export function PolicyFacts({ row, categoryName }: { row: Policy; categoryName?: string }) {
  return <dl className="account-details work-facts"><div><dt>Seletor</dt><dd>{row.category_id ? categoryName ?? "Categoria especifica" : "Todas as categorias"} / {row.priority ? workPriorities[row.priority] : "Todas as prioridades"}</dd></div>
    <div><dt>Primeira resposta</dt><dd>{row.first_response_minutes} min uteis</dd></div><div><dt>Resolucao</dt><dd>{row.resolution_minutes} min uteis</dd></div><div><dt>Aviso de aproximacao</dt><dd>{row.approach_minutes} min uteis restantes</dd></div><div><dt>Pausas</dt><dd>{row.pause_states.length ? row.pause_states.map(state => ticketStatuses[state]).join(", ") : "Nenhuma pausa"}</dd></div><div><dt>Calendario selecionado</dt><dd>Revisao {row.calendar_version}</dd></div></dl>;
}

export function PolicyForm({ initial, queueId, session, calendars, calendarPaging, nextCalendar, disabled, submit, cancel }: {
  initial?: Policy; queueId: string; session: WorkspaceSession; calendars: CalendarSummary[];
  calendarPaging: ReturnType<typeof usePaging>; nextCalendar?: string | null;
  disabled: boolean; submit: (body: PolicyBody) => void; cancel: () => void;
}) {
  const api = createSlaApi(session.user.csrf_token, session.onAuthError);
  const queues = createQueueApi(session.user.csrf_token, session.onAuthError);
  const categoriesPaging = usePaging();
  const categories = useQuery({ queryKey: ["sla-categories", queueId, categoriesPaging.cursor], queryFn: ({ signal }) => queues.categories(queueId, categoriesPaging.cursor, signal) });
  const [selected, setSelected] = useState("");
  const [reviewed, setReviewed] = useState<{ id: string; version: number; name?: string } | null>(initial ? { id: initial.calendar_id, version: initial.calendar_version } : null);
  const [calendarError, setCalendarError] = useState("");
  const calendar = useQuery({ queryKey: ["sla-calendar", queueId, selected], queryFn: ({ signal }) => api.calendar(queueId, selected, signal), enabled: !!selected });
  const form = useForm<Fields>({ resolver: zodResolver(fields), defaultValues: initial ? { name: initial.name, category_id: initial.category_id ?? "", priority: initial.priority ?? "", first_response: String(initial.first_response_minutes), resolution: String(initial.resolution_minutes), approach: String(initial.approach_minutes), pauses: initial.pause_states } : { name: "", category_id: "", priority: "", first_response: "", resolution: "", approach: "", pauses: [] } });
  const save = (body: Fields) => {
    if (!reviewed) { setCalendarError("Revise e selecione uma revisao do calendario."); document.getElementById("sla-policy-calendar")?.focus(); return; }
    submit({ name: body.name, calendar_id: reviewed.id, calendar_version: reviewed.version, category_id: body.category_id || null, priority: body.priority || null, first_response_minutes: Number(body.first_response), resolution_minutes: Number(body.resolution), approach_minutes: Number(body.approach), pause_states: body.pauses });
  };
  return <form className="team-form" noValidate onSubmit={form.handleSubmit(save)}><h4 id="sla-policy-form-heading" className="work-subheading sla-subheading" tabIndex={-1}>{initial ? "Editar politica de SLA" : "Cadastrar politica de SLA"}</h4>
    <div className="field"><label htmlFor="sla-policy-name">Nome da politica</label><input id="sla-policy-name" maxLength={160} disabled={disabled} {...form.register("name")} aria-invalid={!!form.formState.errors.name} aria-describedby="sla-policy-name-error" /><p id="sla-policy-name-error" className="field-error">{form.formState.errors.name?.message}</p></div>
    <fieldset className="work-fields" disabled={disabled || !!initial}><legend>Seletores da politica</legend><p className="field-help">A selecao segue esta ordem: categoria e prioridade; categoria; prioridade; politica geral. Os seletores nao mudam depois do cadastro.</p>
      <div className="work-facts"><div className="field"><label htmlFor="sla-policy-category">Categoria da politica</label><select id="sla-policy-category" {...form.register("category_id")} disabled={disabled || !!initial || categories.isFetching || categories.isError}><option value="">Todas as categorias</option>{initial?.category_id && !categories.data?.items.some(row => row.id === initial.category_id) && <option value={initial.category_id}>Categoria atualmente selecionada</option>}{categories.data?.items.filter(row => row.active || row.id === initial?.category_id).map(row => <option key={row.id} value={row.id}>{row.name}{row.active ? "" : " (arquivada)"}</option>)}</select></div><div className="field"><label htmlFor="sla-policy-priority">Prioridade da politica</label><select id="sla-policy-priority" {...form.register("priority")}><option value="">Todas as prioridades</option>{Object.entries(workPriorities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div></div>
      {!initial && <Paging paging={categoriesPaging} next={categories.data?.next_cursor} label="categorias" disabled={disabled || categories.isFetching} />}
    </fieldset>
    {categories.isError && !initial && <ReadError retry={() => void categories.refetch()} />}
    <fieldset className="work-fields work-description" disabled={disabled}><legend>Calendario e revisao</legend>
      {reviewed && <p className="read-notice">Revisao selecionada: {reviewed.name ?? "calendario atual"}, revisao {reviewed.version}. Essa selecao e preservada ate voce escolher outra.</p>}
      <label htmlFor="sla-policy-calendar">Calendario da politica</label><select id="sla-policy-calendar" value={selected} onChange={event => { setSelected(event.target.value); setCalendarError(""); }}><option value="">Escolha um calendario para revisar</option>{selected && !calendars.some(row => row.id === selected) && <option value={selected}>Calendario em revisao</option>}{calendars.map(row => <option key={row.id} value={row.id}>{row.name}{row.active ? "" : " (desativado)"}</option>)}</select>
      <Paging paging={calendarPaging} next={nextCalendar} label="calendarios de SLA" disabled={disabled} />
      {selected && calendar.isPending && <LoadingRows label="Carregando revisao do calendario..." />}
      {selected && calendar.isError && <ReadError retry={() => void calendar.refetch()} />}
      {selected && !calendar.isError && calendar.data && <><CalendarFacts row={calendar.data} /><Button type="button" variant="outline" disabled={disabled || calendar.isFetching || !calendar.data.active} onClick={() => { const row = calendar.data!; setReviewed({ id: row.id, version: row.version, name: row.name }); setCalendarError(""); }}>Usar esta revisao do calendario</Button></>}
      {calendarError && <p role="alert" className="field-error">{calendarError}</p>}
    </fieldset>
    <div className="work-facts work-description">{([ ["first_response", "Meta de primeira resposta"], ["resolution", "Meta de resolucao"], ["approach", "Aproximacao do limite"] ] as const).map(([key, label]) => <div className="field" key={key}><label htmlFor={`sla-${key}`}>{label} (minutos uteis)</label><input id={`sla-${key}`} type="number" min={key === "approach" ? 0 : 1} max={525600} step={1} disabled={disabled} {...form.register(key)} aria-invalid={!!form.formState.errors[key]} aria-describedby={`sla-${key}-error`} /><p id={`sla-${key}-error`} className="field-error">{form.formState.errors[key]?.message}</p></div>)}</div>
    <fieldset className="work-fields" disabled={disabled}><legend>Estados que pausam os dois relogios</legend>{(["pending_customer", "pending_third_party"] as const).map(state => <label className="work-checkbox" key={state}><input type="checkbox" value={state} {...form.register("pauses")} />{ticketStatuses[state]}</label>)}<p className="field-help">Sem selecao, nenhum estado de pendencia pausa o SLA. Revise essa escolha antes de ativar.</p></fieldset>
    <div className="action-row"><Button type="submit" disabled={disabled || (!initial && categories.isError)}>{initial ? "Salvar revisao da politica" : "Cadastrar politica desativada"}</Button><Button type="button" variant="outline" disabled={disabled} onClick={cancel}>Cancelar politica</Button></div>
  </form>;
}
