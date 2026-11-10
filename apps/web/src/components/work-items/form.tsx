"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { RecordPicker, type Choice } from "@/components/project-workspace/picker";
import { usePaging } from "@/components/team-admin/common";
import { type WorkApi, type WorkCreate, type WorkPatch, type WorkRecord, workPriorities } from "@/lib/work-items";

// Match Python str.strip; ECMAScript trim would discard meaningful U+FEFF.
const externalLabels = (value: string) => value.split(/\r\n|\r|\n/).map(label => label.replace(/^[\p{White_Space}\u001c-\u001f]+|[\p{White_Space}\u001c-\u001f]+$/gu, "")).filter(Boolean);
const schema = z.object({
  title: z.string().trim().refine(value => Array.from(value).length >= 1 && Array.from(value).length <= 300, "Use um título de 1 a 300 caracteres."),
  description: z.string().max(20000, "Use até 20.000 caracteres."),
  priority: z.enum(["low", "medium", "high", "critical"]),
  work_type: z.enum(["one_off", "ongoing"]),
  estimate: z.string().refine(value => !value || (/^\d+$/.test(value) && Number(value) <= 2147483647), "Informe minutos inteiros não negativos."),
  external_labels: z.string().superRefine((value, context) => {
    const labels = externalLabels(value);
    const message = labels.length > 50 ? "Use no maximo 50 nomes externos."
      : labels.some(label => Array.from(label).length > 150 || label.includes("\0")) ? "Use nomes de 1 a 150 caracteres, sem caractere nulo."
      : new Set(labels).size !== labels.length ? "Remova os nomes externos repetidos." : null;
    if (message) context.addIssue({ code: "custom", message });
  }),
});
type Values = z.infer<typeof schema>;
type Fields = Omit<WorkCreate, "project_id">;
function localInstant(instant?: string, mode: "device" | "utc" = "device") {
  if (!instant) return "";
  const date = new Date(instant);
  const parts = mode === "utc" ? [date.getUTCFullYear(), date.getUTCMonth()+1, date.getUTCDate(), date.getUTCHours(), date.getUTCMinutes(), date.getUTCSeconds(), date.getUTCMilliseconds()] : [date.getFullYear(), date.getMonth()+1, date.getDate(), date.getHours(), date.getMinutes(), date.getSeconds(), date.getMilliseconds()];
  const [year, month, day, hour, minute, second, milliseconds] = parts;
  const tail = second || milliseconds ? `:${String(second).padStart(2,"0")}${milliseconds ? `.${String(milliseconds).padStart(3,"0").replace(/0+$/,"")}` : ""}` : "";
  return `${String(year).padStart(4,"0")}-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}T${String(hour).padStart(2,"0")}:${String(minute).padStart(2,"0")}${tail}`;
}
function instantKey(value: string) {
  const fraction = value.match(/\.(\d+)(?:Z|[+-]\d{2}:\d{2})$/)?.[1] ?? "";
  return `${new Date(value).valueOf()}:${fraction.padEnd(6,"0").slice(3)}`;
}
function localOffset(date: Date) {
  const clock = new Date(0);
  clock.setUTCFullYear(date.getFullYear(), date.getMonth(), date.getDate());
  clock.setUTCHours(date.getHours(), date.getMinutes(), date.getSeconds(), date.getMilliseconds());
  return clock.valueOf() - date.valueOf();
}
function ambiguousClock(date: Date, value: string) {
  const offset = localOffset(date);
  for (let hour = -48; hour <= 48; hour++) {
    const otherOffset = localOffset(new Date(date.valueOf() + hour * 3600000));
    const alternate = new Date(date.valueOf() + offset - otherOffset);
    if (alternate.valueOf() !== date.valueOf() && localInstant(alternate.toISOString()) === value) return true;
  }
  return false;
}
export function WorkForm({ api, project, initial, manage, actor, locked, onSubmit, cancel }: {
  api: WorkApi; project: string; initial?: WorkRecord; manage: boolean; actor: { id: string; display_name: string };
  locked: boolean; onSubmit: (body: Fields | WorkPatch) => void; cancel?: () => void;
}) {
  const create = !initial;
  const peoplePaging = usePaging(), parentsPaging = usePaging();
  const people = useQuery({ queryKey: ["work-candidates", project, peoplePaging.cursor], queryFn: ({ signal }) => api.candidates(project, peoplePaging.cursor, signal), enabled: manage });
  const parents = useQuery({ queryKey: ["work-items", project, parentsPaging.cursor], queryFn: ({ signal }) => api.list(project, parentsPaging.cursor, signal), enabled: manage });
  const [owner, setOwner] = useState<Choice | null>(initial?.owner_id ? { id: initial.owner_id, label: initial.owner_name ?? "Responsável atual" } : null);
  const [parent, setParent] = useState<Choice | null>(initial?.parent_id ? { id: initial.parent_id, label: "Tarefa principal atual" } : null);
  const [assignees, setAssignees] = useState<Choice[]>(initial?.assignees.map(row => ({ id: row.id, label: row.display_name })) ?? []);
  const [person, setPerson] = useState<Choice | null>(null);
  const [precision, setPrecision] = useState<"none" | "date" | "instant">(initial?.due?.precision ?? "none");
  const [day, setDay] = useState(initial?.due?.precision === "date" ? initial.due.date : "");
  const [zone, setZone] = useState(initial?.due?.precision === "date" ? initial.due.timezone : "America/Sao_Paulo");
  const [instant, setInstant] = useState(localInstant(initial?.due?.precision === "instant" ? initial.due.instant : undefined));
  const [instantMode, setInstantMode] = useState<"device" | "utc">("device");
  const [deadlineChanged, setDeadlineChanged] = useState(false);
  const [error, setError] = useState("");
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: {
    title: initial?.title ?? "", description: initial?.description ?? "", priority: initial?.priority ?? "medium",
    work_type: initial?.work_type ?? "one_off", estimate: initial?.estimated_minutes?.toString() ?? "",
    external_labels: (initial?.external_participants ?? []).join("\n"),
  } });
  const submit = (values: Values) => {
    setError("");
    let due: WorkCreate["due"] = initial?.due ?? null;
    if ((create || deadlineChanged) && precision === "none") due = null;
    if ((create || deadlineChanged) && precision === "date") {
      if (!day || !zone.trim()) { setError("Informe a data limite e o fuso horário."); return; }
      due = { precision: "date", date: day, timezone: zone.trim() };
    } else if ((create || deadlineChanged) && precision === "instant") {
      const date = new Date(instantMode === "utc" ? `${instant}Z` : instant);
      if (!instant || !Number.isFinite(date.valueOf()) || localInstant(date.toISOString(), instantMode) !== instant) { setError("Informe uma data e hora válida no fuso escolhido, com até milissegundos."); return; }
      if (instantMode === "device" && ambiguousClock(date, instant)) { setError("Esse horário ocorre duas vezes no fuso do dispositivo. Informe a hora em UTC para escolher o instante exato."); return; }
      due = { precision: "instant", instant: date.toISOString() };
      if (initial?.due?.precision === "instant" && instantKey(initial.due.instant) === instantKey(due.instant)) due = initial.due;
    }
    const fields: Fields = { title: values.title, description: values.description, priority: values.priority, work_type: values.work_type,
      due, estimated_minutes: values.estimate ? Number(values.estimate) : null,
      ...(manage ? { owner_id: owner?.id ?? null, parent_id: parent?.id ?? null, assignee_ids: assignees.map(row => row.id), external_participants: externalLabels(values.external_labels) }
        : create ? { owner_id: actor.id } : {}),
    };
    if (create) { onSubmit(fields); return; }
    const body: WorkPatch = {};
    for (const key of ["title", "description", "priority", "due", "estimated_minutes", ...(manage ? ["owner_id", "parent_id", "assignee_ids", "external_participants"] as const : [])] as const) {
      if (key === "external_participants") {
        const labels = fields.external_participants ?? [], previous = initial.external_participants ?? [];
        if (labels.length !== previous.length || labels.some(label => !previous.includes(label))) body.external_participants = labels;
        continue;
      }
      if (JSON.stringify(fields[key]) !== JSON.stringify(initial[key])) Object.assign(body, { [key]: fields[key] });
    }
    if (!Object.keys(body).length) { setError("Nenhuma alteração para salvar."); return; }
    onSubmit(body);
  };
  const choices = people.data?.items.map(row => ({ id: row.id, label: row.display_name })) ?? [];
  return <form noValidate onSubmit={form.handleSubmit(submit)}>
    <fieldset className="work-fields" disabled={locked}>
      <div className="account-form-grid">
        <div><label htmlFor={create ? "new-work-title" : "work-title"}>{create ? "Título da nova tarefa" : "Título"}</label><input id={create ? "new-work-title" : "work-title"} {...form.register("title")} maxLength={600} aria-invalid={!!form.formState.errors.title} aria-describedby="work-title-error" /><p id="work-title-error" className="field-error">{form.formState.errors.title?.message}</p></div>
        <div><label htmlFor="work-priority">Prioridade</label><select id="work-priority" {...form.register("priority")}>{Object.entries(workPriorities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        {create && <div><label htmlFor="work-type">Tipo de trabalho</label><select id="work-type" {...form.register("work_type")}><option value="one_off">Pontual</option><option value="ongoing">Contínuo</option></select><p className="field-help">Trabalho contínuo inicia em andamento e exige encerramento explícito, sem gerar recorrências.</p></div>}
        {manage && <RecordPicker id="work-owner" label="Responsável" value={owner} onChange={setOwner} choices={choices} paging={peoplePaging} next={people.data?.next_cursor} pending={people.isPending} failed={people.isError} retry={() => void people.refetch()} disabled={locked} empty="Sem responsável" />}
        {manage && <RecordPicker id="work-parent" label="Tarefa principal" value={parent} onChange={setParent} choices={parents.data?.items.filter(row => row.id !== initial?.id).map(row => ({ id: row.id, label: row.title })) ?? []} paging={parentsPaging} next={parents.data?.next_cursor} pending={parents.isPending} failed={parents.isError} retry={() => void parents.refetch()} disabled={locked} empty="Sem tarefa principal" />}
        <div><label htmlFor="work-due">Prazo</label><select id="work-due" value={precision} onChange={event => { setDeadlineChanged(true); setPrecision(event.target.value as typeof precision); }}><option value="none">Sem prazo</option><option value="date">Data</option><option value="instant">Data e hora exatas</option></select></div>
        {precision === "date" && <><div><label htmlFor="work-day">Data limite</label><input id="work-day" type="date" value={day} onChange={event => { setDeadlineChanged(true); setDay(event.target.value); }} /></div><div><label htmlFor="work-zone">Fuso do prazo</label><input id="work-zone" value={zone} maxLength={100} onChange={event => { setDeadlineChanged(true); setZone(event.target.value); }} /><p className="field-help">O prazo inclui todo o dia neste fuso, por exemplo America/Sao_Paulo.</p></div></>}
        {precision === "instant" && <><div><label htmlFor="work-instant-mode">Fuso da hora limite</label><select id="work-instant-mode" value={instantMode} onChange={event => { setDeadlineChanged(true); setInstantMode(event.target.value as typeof instantMode); }}><option value="device">Dispositivo ({Intl.DateTimeFormat().resolvedOptions().timeZone})</option><option value="utc">UTC</option></select></div><div><label htmlFor="work-instant">Data e hora limite</label><input id="work-instant" type="datetime-local" step="any" value={instant} onChange={event => { setDeadlineChanged(true); setInstant(event.target.value); }} /><p className="field-help">O horário digitado será interpretado no fuso escolhido, com precisão de milissegundos.</p></div></>}
        <div><label htmlFor="work-estimate">Estimativa em minutos</label><input id="work-estimate" type="number" min={0} max={2147483647} step={1} {...form.register("estimate")} aria-invalid={!!form.formState.errors.estimate} aria-describedby="work-estimate-error" /><p id="work-estimate-error" className="field-error">{form.formState.errors.estimate?.message}</p></div>
      </div>
      <div className="field work-description"><label htmlFor="work-description">Descrição</label><textarea id="work-description" maxLength={20000} rows={5} {...form.register("description")} /></div>
      {manage && <div className="work-participants"><h3>Envolvidos</h3><p className="field-help">Envolvimento não concede acesso ao projeto. Selecione até 50 colaboradores autorizados.</p>
        <RecordPicker id="work-participant" label="Adicionar envolvido" value={person} onChange={setPerson} choices={choices.filter(row => !assignees.some(selected => selected.id === row.id))} paging={peoplePaging} next={people.data?.next_cursor} pending={people.isPending} failed={people.isError} retry={() => void people.refetch()} disabled={locked || assignees.length >= 50} />
        <Button type="button" variant="outline" disabled={locked || !person || assignees.length >= 50} onClick={() => { if (person) setAssignees([...assignees, person]); setPerson(null); }}>Incluir envolvido</Button>
        <ul className="record-list" aria-label="Envolvidos selecionados">{assignees.map(row => <li className="team-row" key={row.id}><span className="record-text">{row.label}</span><Button type="button" variant="outline" onClick={() => setAssignees(assignees.filter(selected => selected.id !== row.id))}>Remover {row.label}</Button></li>)}</ul>
      </div>}
      {manage && <div className="field work-participants"><label htmlFor="work-external">Envolvidos externos, um por linha</label>
        <p id="work-external-help" className="field-help">Ate 50 nomes, com no maximo 150 caracteres por nome. Nomes informados nao criam contas, nao enviam mensagens e nao concedem acesso.</p>
        <textarea id="work-external" rows={4} maxLength={20000} {...form.register("external_labels")} aria-invalid={!!form.formState.errors.external_labels} aria-describedby="work-external-help work-external-error" />
        <p id="work-external-error" className="field-error" role={form.formState.errors.external_labels ? "alert" : undefined}>{form.formState.errors.external_labels?.message}</p>
      </div>}
      {!manage && create && <p className="field-help">Você será responsável por esta tarefa. O gestor pode ajustar os envolvidos e a tarefa principal.</p>}
      {error && <p role="alert" className="field-error">{error}</p>}
      <div className="action-row"><Button type="submit">{create ? "Criar tarefa" : "Salvar tarefa"}</Button>{cancel && <Button type="button" variant="outline" onClick={cancel}>Cancelar edição</Button>}</div>
    </fieldset>
  </form>;
}
