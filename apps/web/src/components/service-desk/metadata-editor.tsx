"use client";

import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { useTeamWrite, writeError } from "@/components/team-admin/common";
import type { QueuePatch } from "@/lib/ticket-queues";

// Python str.strip preserves U+FEFF and includes four ASCII separators.
const stripName = (value: string) => value.replace(/^[\p{White_Space}\u001c-\u001f]+|[\p{White_Space}\u001c-\u001f]+$/gu, "");
export const queueNameSchema = z.object({
  name: z.string().transform(stripName).refine(
    value => Array.from(value).length >= 1 && Array.from(value).length <= 150 && !/[\0\r\n]/.test(value),
    "Use um nome de 1 a 150 caracteres em uma linha.",
  ),
});

type WriteState = Pick<ReturnType<typeof useTeamWrite>, "error" | "uncertain" | "pending" | "locked" | "reloading" | "reloadFailed" | "verify" | "reconcile">;
export function WriteFeedback({ write, reload, creation = false }: {
  write: WriteState; reload: () => Promise<void>; creation?: boolean;
}) {
  return <>
    {write.error && <div className="read-error">
      <p role="alert">{writeError(write.error)}</p>
      {creation && write.uncertain ? <Button variant="outline" disabled={write.pending} onClick={write.verify}>Verificar cadastro</Button>
        : write.locked && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(reload)}>Recarregar e descartar edicao</Button>}
    </div>}
    {write.reloadFailed && <p role="alert" className="error-message">Nao foi possivel atualizar. A edicao continua bloqueada.</p>}
  </>;
}

type Metadata = { id: string; name: string; active: boolean; version: number };
export function MetadataEditor({ record, kind, session, writable, disabled = false, update, refresh }: {
  record: Metadata; kind: "fila" | "categoria"; session: WorkspaceSession; writable: boolean;
  disabled?: boolean;
  update: (body: QueuePatch, version: number) => Promise<Metadata>; refresh: () => Promise<void>;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const confirmation = useRef<HTMLHeadingElement>(null);
  const form = useForm<{ name: string }>({ resolver: zodResolver(queueNameSchema), defaultValues: { name: record.name } });
  const focus = () => requestAnimationFrame(() => document.getElementById(`rename-${record.id}`)?.focus());
  const write = useTeamWrite(session, ({ version, body }: { version: number; body: QueuePatch }) => update(body, version), () => {
    setEditing(null); setConfirm(null); setNotice("Alteracao confirmada.");
    void refresh().catch(() => { /* The owning read renders recovery independently. */ });
    focus();
  });
  const locked = write.locked || disabled;
  useEffect(() => { if (confirm !== null) confirmation.current?.focus(); }, [confirm]);
  const reload = async () => {
    await refresh();
    if (session.isCurrent()) { setEditing(null); setConfirm(null); setNotice(""); focus(); }
  };
  return <>
    {notice && <p role="status" className="read-notice">{notice}</p>}
    {editing !== null ? <form noValidate className="inline-form" onSubmit={form.handleSubmit(value => write.submit({ body: { name: value.name }, version: editing }))}>
      <div className="form-grow">
        <label htmlFor={`name-${record.id}`}>Nome da {kind}</label>
        <input id={`name-${record.id}`} {...form.register("name")} maxLength={300} disabled={locked} aria-invalid={!!form.formState.errors.name} aria-describedby={`error-${record.id}`} />
        <p id={`error-${record.id}`} className="field-error">{form.formState.errors.name?.message}</p>
      </div>
      <Button type="submit" disabled={locked || !writable}>Salvar nome</Button>
      <Button type="button" variant="outline" disabled={write.locked} onClick={() => { setEditing(null); focus(); }}>Cancelar edicao</Button>
    </form> : writable && <div className="action-row add-member-action">
      <Button id={`rename-${record.id}`} variant="outline" disabled={locked || confirm !== null} onClick={() => { form.reset({ name: record.name }); setEditing(record.version); setNotice(""); }}>Renomear {kind}</Button>
      <Button id={`state-${record.id}`} variant="outline" disabled={locked || confirm !== null} onClick={() => {
        setNotice("");
        if (record.active) setConfirm(record.version);
        else write.submit({ body: { active: true }, version: record.version });
      }}>{record.active ? "Arquivar" : "Restaurar"} {kind}</Button>
    </div>}
    {confirm !== null && <div className="confirmation" role="group" aria-labelledby={`confirm-${record.id}`}>
      <h3 id={`confirm-${record.id}`} ref={confirmation} tabIndex={-1}>Arquivar {record.name}?</h3>
      <p>O cadastro e seu historico serao preservados. Voce podera restaura-lo depois.</p>
      <div className="action-row">
        <Button disabled={locked || !writable} onClick={() => write.submit({ body: { active: false }, version: confirm })}>Confirmar arquivamento</Button>
        <Button variant="outline" disabled={write.locked} onClick={() => { setConfirm(null); focus(); }}>Cancelar</Button>
      </div>
    </div>}
    <WriteFeedback write={write} reload={reload} />
  </>;
}
