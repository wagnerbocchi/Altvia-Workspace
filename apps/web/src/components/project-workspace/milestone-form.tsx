"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import type { MilestoneCreate, MilestonePatch, MilestoneRecord } from "@/lib/projects";

const schema = z.object({ title: z.string().trim().refine(value => Array.from(value).length >= 1 && Array.from(value).length <= 300, "Use um titulo de 1 a 300 caracteres.") });
export function MilestoneForm({ initial, disabled, cancelDisabled, onSubmit, cancel }: {
  initial?: MilestoneRecord; disabled: boolean; cancelDisabled: boolean;
  onSubmit: (value: MilestoneCreate | MilestonePatch) => void; cancel: () => void;
}) {
  const original = initial?.due ?? null;
  const initialInstant = original?.precision === "instant" ? new Date(original.instant).toISOString().slice(0, 23) : "";
  const [precision, setPrecision] = useState<"none" | "date" | "instant">(original?.precision ?? "none");
  const [day, setDay] = useState(original?.precision === "date" ? original.date : "");
  const [zone, setZone] = useState(original?.precision === "date" ? original.timezone : Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [instant, setInstant] = useState(initialInstant);
  const [error, setError] = useState("");
  const form = useForm<{ title: string }>({ resolver: zodResolver(schema), defaultValues: { title: initial?.title ?? "" } });
  const submit = (values: { title: string }) => {
    setError(""); let due: MilestoneCreate["due"] = null;
    if (precision === "date") {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || !zone.trim()) { setError("Informe a data e o fuso do prazo."); return; }
      due = { precision: "date", date: day, timezone: zone.trim() };
    } else if (precision === "instant") {
      const parsed = new Date(`${instant}Z`);
      if (!instant || !Number.isFinite(parsed.valueOf()) || !parsed.toISOString().startsWith(instant)) { setError("Informe uma data e hora UTC valida, com ate milissegundos."); return; }
      due = original?.precision === "instant" && instant === initialInstant ? original : { precision: "instant", instant: parsed.toISOString() };
    }
    if (!initial) { onSubmit({ title: values.title, due }); return; }
    const patch: MilestonePatch = {};
    if (values.title !== initial.title) patch.title = values.title;
    if (JSON.stringify(due) !== JSON.stringify(original)) patch.due = due;
    if (!Object.keys(patch).length) { setError("Nenhuma alteracao para salvar."); return; }
    onSubmit(patch);
  };
  return <form noValidate onSubmit={form.handleSubmit(submit)}>
    <fieldset className="work-fields" disabled={disabled}>
      <div className="account-form-grid">
        <div><label htmlFor="milestone-title">Titulo do marco</label><input id="milestone-title" autoFocus maxLength={600} {...form.register("title")} aria-invalid={!!form.formState.errors.title} aria-describedby="milestone-title-error" /><p id="milestone-title-error" className="field-error">{form.formState.errors.title?.message}</p></div>
        <div><label htmlFor="milestone-due">Prazo do marco</label><select id="milestone-due" value={precision} onChange={event => setPrecision(event.target.value as typeof precision)}><option value="none">Sem prazo</option><option value="date">Data</option><option value="instant">Data e hora exatas</option></select></div>
        {precision === "date" && <><div><label htmlFor="milestone-day">Data limite</label><input id="milestone-day" type="date" value={day} onChange={event => setDay(event.target.value)} /></div><div><label htmlFor="milestone-zone">Fuso do prazo</label><input id="milestone-zone" maxLength={100} value={zone} onChange={event => setZone(event.target.value)} /><p className="field-help">O prazo inclui todo o dia no fuso informado.</p></div></>}
        {precision === "instant" && <div><label htmlFor="milestone-instant">Data e hora limite em UTC</label><input id="milestone-instant" type="datetime-local" step="any" value={instant} onChange={event => setInstant(event.target.value)} /><p className="field-help">Entrada em UTC, com ate milissegundos. Um instante existente permanece exato quando o horario nao e alterado.</p></div>}
      </div>
      {error && <p role="alert" className="field-error">{error}</p>}
      <div className="action-row add-member-action"><Button type="submit">{initial ? "Salvar marco" : "Cadastrar marco"}</Button></div>
    </fieldset>
    <div className="action-row add-member-action"><Button variant="outline" type="button" disabled={cancelDisabled} onClick={cancel}>Cancelar edicao</Button></div>
  </form>;
}
