"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { useTeamWrite } from "@/components/team-admin/common";
import type { QueueApi, QueueRecord } from "@/lib/ticket-queues";
import { WriteFeedback } from "./metadata-editor";

type Policy = Pick<QueueRecord, "allow_manual_close" | "allow_reopen" | "version">;
export function QueueWorkflow({ row, api, session, disabled, refresh }: {
  row: QueueRecord; api: QueueApi; session: WorkspaceSession; disabled: boolean; refresh: () => Promise<void>;
}) {
  const [editing, setEditing] = useState<Policy | null>(null);
  const [notice, setNotice] = useState("");
  const write = useTeamWrite(session, (intent: Policy) => api.update(row.id, { allow_manual_close: intent.allow_manual_close, allow_reopen: intent.allow_reopen }, intent.version), () => {
    setEditing(null); setNotice("Fluxo atualizado.");
    void refresh().catch(() => { /* Parent read owns recovery. */ });
  });
  const reload = async () => { await refresh(); if (session.isCurrent()) setEditing(null); };
  return <section className="admin-section" aria-labelledby="queue-workflow-heading">
    <h2 id="queue-workflow-heading">Fluxo dos chamados</h2>
    {notice && <p role="status" className="read-notice">{notice}</p>}
    {editing ? <form onSubmit={event => { event.preventDefault(); write.submit(editing); }}>
      <fieldset className="work-fields" disabled={disabled || write.locked}>
        <label className="work-checkbox"><input type="checkbox" checked={editing.allow_manual_close} onChange={event => setEditing({ ...editing, allow_manual_close: event.target.checked })} />Permitir fechamento manual</label>
        <label className="work-checkbox"><input type="checkbox" checked={editing.allow_reopen} onChange={event => setEditing({ ...editing, allow_reopen: event.target.checked })} />Permitir reabertura</label>
        <div className="action-row"><Button type="submit">Salvar fluxo</Button><Button type="button" variant="outline" onClick={() => setEditing(null)}>Cancelar fluxo</Button></div>
      </fieldset>
    </form> : <>
      <dl className="account-details"><div><dt>Fechamento manual</dt><dd>{row.allow_manual_close ? "Permitido ao gestor da fila" : "Desabilitado"}</dd></div>
        <div><dt>Reabertura</dt><dd>{row.allow_reopen ? "Permitida conforme papel e atribuicao" : "Desabilitada"}</dd></div></dl>
      {row.can_manage && row.team_active && <Button variant="outline" disabled={disabled || write.locked} onClick={() => { setNotice(""); setEditing({ version: row.version, allow_manual_close: row.allow_manual_close, allow_reopen: row.allow_reopen }); }}>Editar fluxo</Button>}
    </>}
    <WriteFeedback write={write} reload={reload} />
  </section>;
}
