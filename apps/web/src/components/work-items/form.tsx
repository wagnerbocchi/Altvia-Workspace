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

const schema = z.object({
  title: z.string().trim().refine(value => Array.from(value).length >= 1 && Array.from(value).length <= 300, "Use um título de 1 a 300 caracteres."),
  description: z.string().max(20000, "Use até 20.000 caracteres."),
  priority: z.enum(["low", "medium", "high", "critical"]),
  work_type: z.enum(["one_off", "ongoing"]),
  estimate: z.string().refine(value => !value || (/^\d+$/.test(value) && Number(value) <= 2147483647), "Informe minutos inteiros não negativos."),
});
type Values = z.infer<typeof schema>;
type Fields = Omit<WorkCreate, "project_id">;
function localInstant(instant?: string) {
  if (!instant) return "";
  const date = new Date(instant);
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}T${String(date.getHours()).padStart(2,"0")}:${String(date.getMinutes()).padStart(2,"0")}`;
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
  const [error, setError] = useState("");
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: {
    title: initial?.title ?? "", description: initial?.description ?? "", priority: initial?.priority ?? "medium",
    work_type: initial?.work_type ?? "one_off", estimate: initial?.estimated_minutes?.toString() ?? "",
  } });
  const submit = (values: Values) => {
    setError("");
    let due: WorkCreate["due"] = null;
    if (precision === "date") {
      if (!day || !zone.trim()) { setError("Informe a data limite e o fuso horário."); return; }
      due = { precision: "date", date: day, timezone: zone.trim() };
    } else if (precision === "instant") {
      const date = new Date(instant);
      if (!instant || !Number.isFinite(date.valueOf()) || localInstant(date.toISOString()) !== instant) { setError("Informe uma data e hora válida no fuso do seu dispositivo."); return; }
      due = { precision: "instant", instant: date.toISOString() };
    }
    const fields: Fields = { title: values.title, description: values.description, priority: values.priority, work_type: values.work_type,
      due, estimated_minutes: values.estimate ? Number(values.estimate) : null,
      ...(manage ? { owner_id: owner?.id ?? null, parent_id: parent?.id ?? null, assignee_ids: assignees.map(row => row.id) }
        : create ? { owner_id: actor.id } : {}),
    };
    if (create) { onSubmit(fields); return; }
    const body: WorkPatch = {};
    for (const key of ["title", "description", "priority", "due", "estimated_minutes", ...(manage ? ["owner_id", "parent_id", "assignee_ids"] as const : [])] as const) {
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
        <div><label htmlFor="work-due">Prazo</label><select id="work-due" value={precision} onChange={event => setPrecision(event.target.value as typeof precision)}><option value="none">Sem prazo</option><option value="date">Data</option><option value="instant">Data e hora exatas</option></select></div>
        {precision === "date" && <><div><label htmlFor="work-day">Data limite</label><input id="work-day" type="date" value={day} onChange={event => setDay(event.target.value)} /></div><div><label htmlFor="work-zone">Fuso do prazo</label><input id="work-zone" value={zone} maxLength={100} onChange={event => setZone(event.target.value)} /><p className="field-help">O prazo inclui todo o dia neste fuso, por exemplo America/Sao_Paulo.</p></div></>}
        {precision === "instant" && <div><label htmlFor="work-instant">Data e hora limite</label><input id="work-instant" type="datetime-local" value={instant} onChange={event => setInstant(event.target.value)} /><p className="field-help">Fuso do dispositivo: {Intl.DateTimeFormat().resolvedOptions().timeZone}.</p></div>}
        <div><label htmlFor="work-estimate">Estimativa em minutos</label><input id="work-estimate" type="number" min={0} max={2147483647} step={1} {...form.register("estimate")} aria-invalid={!!form.formState.errors.estimate} aria-describedby="work-estimate-error" /><p id="work-estimate-error" className="field-error">{form.formState.errors.estimate?.message}</p></div>
      </div>
      <div className="field work-description"><label htmlFor="work-description">Descrição</label><textarea id="work-description" maxLength={20000} rows={5} {...form.register("description")} /></div>
      {manage && <div className="work-participants"><h3>Envolvidos</h3><p className="field-help">Envolvimento não concede acesso ao projeto. Selecione até 50 colaboradores autorizados.</p>
        <RecordPicker id="work-participant" label="Adicionar envolvido" value={person} onChange={setPerson} choices={choices.filter(row => !assignees.some(selected => selected.id === row.id))} paging={peoplePaging} next={people.data?.next_cursor} pending={people.isPending} failed={people.isError} retry={() => void people.refetch()} disabled={locked || assignees.length >= 50} />
        <Button type="button" variant="outline" disabled={locked || !person || assignees.length >= 50} onClick={() => { if (person) setAssignees([...assignees, person]); setPerson(null); }}>Incluir envolvido</Button>
        <ul className="record-list" aria-label="Envolvidos selecionados">{assignees.map(row => <li className="team-row" key={row.id}><span className="record-text">{row.label}</span><Button type="button" variant="outline" onClick={() => setAssignees(assignees.filter(selected => selected.id !== row.id))}>Remover {row.label}</Button></li>)}</ul>
      </div>}
      {!manage && create && <p className="field-help">Você será responsável por esta tarefa. O gestor pode ajustar os envolvidos e a tarefa principal.</p>}
      {error && <p role="alert" className="field-error">{error}</p>}
      <div className="action-row"><Button type="submit">{create ? "Criar tarefa" : "Salvar tarefa"}</Button>{cancel && <Button type="button" variant="outline" onClick={cancel}>Cancelar edição</Button>}</div>
    </fieldset>
  </form>;
}
