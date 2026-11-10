"use client";

import { Paging, ReadError, usePaging } from "@/components/team-admin/common";

export type Choice = { id: string; label: string };
export function RecordPicker({ id, label, value, choices, onChange, paging, next, pending, failed, retry, disabled, empty = "Escolha uma opção" }: {
  id: string; label: string; value: Choice | null; choices: Choice[]; onChange: (value: Choice | null) => void;
  paging: ReturnType<typeof usePaging>; next?: string | null; pending: boolean; failed: boolean;
  retry: () => void; disabled: boolean; empty?: string;
}) {
  const visible = [...choices];
  if (value && !visible.some(item => item.id === value.id)) visible.push(value);
  return <div>
    <label htmlFor={id}>{label}</label>
    <select id={id} disabled={disabled} value={value?.id ?? ""} onChange={event => onChange(visible.find(item => item.id === event.target.value) ?? null)}>
      <option value="">{empty}</option>{visible.map(item => <option value={item.id} key={item.id}>{item.label}</option>)}
    </select>
    {pending ? <p role="status">Carregando {label.toLocaleLowerCase("pt-BR")}...</p> : failed ? <ReadError retry={retry} />
      : <Paging paging={paging} next={next} label={label.toLocaleLowerCase("pt-BR")} disabled={disabled} />}
  </div>;
}
