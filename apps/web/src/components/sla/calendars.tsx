"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import type { Calendar, CalendarCreate } from "@/lib/sla";

export const weekdays = ["Segunda-feira", "Terca-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sabado", "Domingo"];
const time = z.string().regex(/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/, "Use HH:MM, entre 00:00 e 23:59.");
const fields = z.object({ name: z.string().trim().min(1, "Informe o nome.").max(160), timezone: z.string().trim().min(1, "Informe o fuso IANA.").max(100).regex(/^[A-Za-z0-9_+/-]+$/, "Confira o nome IANA do fuso.").refine(value => value.split("/").every(part => part.length > 0), "Confira o nome IANA do fuso."), active: z.boolean(),
  windows: z.array(z.object({ weekday: z.string().regex(/^[0-6]$/, "Escolha o dia."), start: time, end: z.string().regex(/^(?:(?:[01][0-9]|2[0-3]):[0-5][0-9]|24:00)$/, "Use HH:MM, ate 24:00.") })).min(1, "Adicione ao menos uma janela.").max(28),
  holidays: z.array(z.object({ date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Informe a data."), label: z.string().trim().max(160) })).max(1000),
}).superRefine((value, context) => {
  value.windows.forEach((window, i) => {
    if (window.end <= window.start) context.addIssue({ code: "custom", path: ["windows", i, "end"], message: "O termino deve ser depois do inicio." });
    if (value.windows.some((other, j) => j < i && other.weekday === window.weekday && other.start < window.end && window.start < other.end)) context.addIssue({ code: "custom", path: ["windows", i, "weekday"], message: "Esta janela sobrepoe outra no mesmo dia." });
  });
  value.holidays.forEach((holiday, i) => {
    if (value.holidays.some((other, j) => j < i && other.date === holiday.date)) context.addIssue({ code: "custom", path: ["holidays", i, "date"], message: "Esta data ja foi adicionada." });
  });
});
type Fields = z.infer<typeof fields>;
export function minute(value: string) { const [hour, minutes] = value.split(":").map(Number); return hour * 60 + minutes; }
export function clock(value: number) { return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`; }

export function CalendarForm({ initial, disabled, submit, cancel }: { initial?: Calendar; disabled: boolean; submit: (body: Omit<CalendarCreate, "client_id">) => void; cancel: () => void }) {
  const form = useForm<Fields>({ resolver: zodResolver(fields), defaultValues: initial ? { name: initial.name, timezone: initial.timezone, active: initial.active,
    windows: initial.windows.map(row => ({ weekday: String(row.weekday), start: clock(row.start_minute), end: clock(row.end_minute) })),
    holidays: initial.holidays.map(row => ({ date: row.date, label: row.label ?? "" })),
  } : { name: "", timezone: "", active: false, windows: [{ weekday: "", start: "", end: "" }], holidays: [] } });
  const windows = useFieldArray({ control: form.control, name: "windows" });
  const holidays = useFieldArray({ control: form.control, name: "holidays" });
  return <form className="team-form" noValidate onSubmit={form.handleSubmit(body => submit({ name: body.name, timezone: body.timezone, active: body.active,
    windows: body.windows.map(row => ({ weekday: Number(row.weekday), start_minute: minute(row.start), end_minute: minute(row.end) })),
    holidays: body.holidays.map(row => ({ date: row.date, ...(row.label ? { label: row.label } : {}) })),
  }))}>
    <h4 id="sla-calendar-form-heading" className="work-subheading sla-subheading" tabIndex={-1}>{initial ? "Editar calendario" : "Cadastrar calendario"}</h4>
    <p className="field-help">Informe os horarios reais de atendimento. Edicoes criam outra revisao; ciclos ja iniciados preservam seu calendario capturado.</p>
    <div className="work-facts"><div className="field"><label htmlFor="sla-calendar-name">Nome do calendario</label><input id="sla-calendar-name" maxLength={160} disabled={disabled} {...form.register("name")} aria-invalid={!!form.formState.errors.name} aria-describedby="sla-calendar-name-error" /><p id="sla-calendar-name-error" className="field-error">{form.formState.errors.name?.message}</p></div>
      <div className="field"><label htmlFor="sla-calendar-timezone">Fuso IANA do calendario</label><input id="sla-calendar-timezone" disabled={disabled} {...form.register("timezone")} aria-invalid={!!form.formState.errors.timezone} aria-describedby="sla-calendar-timezone-help sla-calendar-timezone-error" /><p id="sla-calendar-timezone-help" className="field-help">Use o nome IANA adotado pela operacao. O servidor verifica o fuso informado.</p><p id="sla-calendar-timezone-error" className="field-error">{form.formState.errors.timezone?.message}</p></div></div>
    <fieldset className="work-fields" disabled={disabled}><legend>Janelas semanais de atendimento</legend><p className="field-help">Horarios locais em HH:MM. O termino admite 24:00. Divida horarios que cruzam a meia-noite em dois dias.</p>
      {windows.fields.map((row, i) => <div className="sla-window" key={row.id}><div className="work-facts">
        <div className="field"><label htmlFor={`sla-day-${i}`}>Dia da janela {i + 1}</label><select id={`sla-day-${i}`} {...form.register(`windows.${i}.weekday`)} aria-invalid={!!form.formState.errors.windows?.[i]?.weekday} aria-describedby={`sla-day-${i}-error`}><option value="">Escolha o dia</option>{weekdays.map((day, n) => <option key={day} value={n}>{day}</option>)}</select><p id={`sla-day-${i}-error`} className="field-error">{form.formState.errors.windows?.[i]?.weekday?.message}</p></div>
        <div className="field"><label htmlFor={`sla-start-${i}`}>Inicio da janela {i + 1}</label><input id={`sla-start-${i}`} maxLength={5} inputMode="numeric" {...form.register(`windows.${i}.start`)} aria-invalid={!!form.formState.errors.windows?.[i]?.start} aria-describedby={`sla-start-${i}-error`} /><p id={`sla-start-${i}-error`} className="field-error">{form.formState.errors.windows?.[i]?.start?.message}</p></div>
        <div className="field"><label htmlFor={`sla-end-${i}`}>Termino da janela {i + 1}</label><input id={`sla-end-${i}`} maxLength={5} inputMode="numeric" {...form.register(`windows.${i}.end`)} aria-invalid={!!form.formState.errors.windows?.[i]?.end} aria-describedby={`sla-end-${i}-error`} /><p id={`sla-end-${i}-error`} className="field-error">{form.formState.errors.windows?.[i]?.end?.message}</p></div></div>
        <Button type="button" variant="outline" onClick={() => windows.remove(i)}>Remover janela {i + 1}</Button></div>)}
      {form.formState.errors.windows?.message && <p role="alert" className="field-error">{form.formState.errors.windows.message}</p>}
      <Button type="button" variant="outline" disabled={windows.fields.length >= 28} onClick={() => windows.append({ weekday: "", start: "", end: "" })}>Adicionar janela semanal</Button>
    </fieldset>
    <fieldset className="work-fields work-description" disabled={disabled}><legend>Feriados e dias sem atendimento</legend>
      {!holidays.fields.length && <p>Nenhum feriado informado. Adicione apenas as datas aprovadas pela operacao.</p>}
      {holidays.fields.map((row, i) => <div className="sla-window" key={row.id}><div className="work-facts"><div className="field"><label htmlFor={`sla-holiday-${i}`}>Data sem atendimento {i + 1}</label><input id={`sla-holiday-${i}`} type="date" min="2000-01-01" max="2099-12-31" {...form.register(`holidays.${i}.date`)} aria-invalid={!!form.formState.errors.holidays?.[i]?.date} aria-describedby={`sla-holiday-${i}-error`} /><p id={`sla-holiday-${i}-error`} className="field-error">{form.formState.errors.holidays?.[i]?.date?.message}</p></div><div className="field"><label htmlFor={`sla-holiday-name-${i}`}>Descricao opcional da data {i + 1}</label><input id={`sla-holiday-name-${i}`} maxLength={160} {...form.register(`holidays.${i}.label`)} /></div></div><Button type="button" variant="outline" onClick={() => holidays.remove(i)}>Remover data {i + 1}</Button></div>)}
      <Button type="button" variant="outline" disabled={holidays.fields.length >= 1000} onClick={() => holidays.append({ date: "", label: "" })}>Adicionar feriado</Button>
    </fieldset>
    <label className="work-checkbox"><input type="checkbox" disabled={disabled} {...form.register("active")} />Calendario ativo para novos ciclos</label>
    <p className="field-help">Desativar um calendario pode impedir novas aberturas ou reaberturas enquanto uma politica ativada o selecionar. Revise as politicas antes de desativar.</p>
    <div className="action-row"><Button type="submit" disabled={disabled}>{initial ? "Salvar revisao do calendario" : "Cadastrar calendario revisado"}</Button><Button type="button" variant="outline" disabled={disabled} onClick={cancel}>Cancelar calendario</Button></div>
  </form>;
}
