"use client";

import Link from "next/link";
import { WorkTicketLinks } from "@/components/ticket-work/links";
import { AttachmentPicker } from "@/components/attachments";
import { sameAttachments, type AttachmentSummary } from "@/lib/attachments";
import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, ReadError, useTeamWrite } from "@/components/team-admin/common";
import { ApiError } from "@/lib/http";
import { type WorkApi, type WorkRecord, type WorkPatch, type WorkTransition, dueLabel, workPriorities, workStatuses } from "@/lib/work-items";
import { WorkForm } from "./form";
import { WriteRecovery } from "./recovery";
import { Comments, StateHistory, WorkActivity } from "./reads";

type Intent = { kind: "edit"; body: WorkPatch; version: number }
  | { kind: "transition"; body: WorkTransition; version: number; key: string }
  | { kind: "comment"; body: string; files: AttachmentSummary[]; version: number; key: string };
const transitions: Record<string, WorkTransition["target_status"][]> = { todo: ["in_progress","blocked","cancelled"], in_progress: ["blocked","done","cancelled"], blocked: ["todo","in_progress","cancelled"], done: ["in_progress"], cancelled: ["todo"] };
export function WorkDetail({ id, api, session }: { id: string; api: WorkApi; session: WorkspaceSession }) {
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ["work-item", id], queryFn: ({ signal }) => api.get(id, signal) });
  const row = query.data;
  const parentDenied = query.error instanceof ApiError && [403, 404].includes(query.error.status);
  const parent = useQuery({ queryKey: ["work-item", row?.parent_id], queryFn: ({ signal }) => api.get(row!.parent_id!, signal), enabled: !!row?.parent_id });
  const [editor, setEditor] = useState<WorkRecord | null>(null), [notice, setNotice] = useState("");
  const [linksBusy, setLinksBusy] = useState(false);
  const [target, setTarget] = useState<WorkTransition["target_status"] | "">("");
  const [reason, setReason] = useState(""), [end, setEnd] = useState(false), [body, setBody] = useState("");
  const [files, setFiles] = useState<AttachmentSummary[]>([]), [filesBusy, setFilesBusy] = useState(false);
  const busyChanged = useCallback((busy: boolean) => setFilesBusy(busy), []);
  const [commentVersion, setCommentVersion] = useState<number | null>(null);
  const [formError, setFormError] = useState("");
  const write = useTeamWrite(session, async (intent: Intent) => {
    if (intent.kind === "edit") return { kind: "edit" as const, row: await api.update(id, intent.body, intent.version) };
    if (intent.kind === "transition") return { kind: "transition" as const, row: await api.transition(id, intent.body, intent.version, intent.key) };
    const comment = await api.comment(id, intent.body, intent.version, intent.key, intent.files.map(file => file.id));
    if (comment.work_item_id !== id || comment.body !== intent.body || !sameAttachments(comment.attachments ?? [], intent.files)) throw Error("Comment receipt not confirmed");
    return { kind: "comment" as const, comment };
  }, result => {
    if (result.kind !== "comment") cache.setQueryData<WorkRecord>(["work-item", id], current => !current || current.version <= result.row.version ? result.row : current);
    if (result.kind === "edit") { setEditor(null); requestAnimationFrame(() => document.getElementById("work-heading")?.focus()); }
    if (result.kind === "transition") { setTarget(""); setReason(""); setEnd(false); }
    if (result.kind === "comment") { setBody(""); setFiles([]); setCommentVersion(null); }
    setNotice(result.kind === "comment" ? "Comentário registrado." : "Alteração confirmada.");
    void Promise.all([
      cache.invalidateQueries({ queryKey: ["work-item", id] }),
      cache.invalidateQueries({ queryKey: ["work-items", row?.project_id] }),
      ...["work-comments", "work-states", "work-activity"].map(key => cache.invalidateQueries({ queryKey: [key, id] })),
    ]);
  });
  const reload = async () => {
    await query.refetch({ throwOnError: true });
    await cache.refetchQueries({ queryKey: ["work-candidates", row?.project_id], type: "active" }, { throwOnError: true });
    if (session.isCurrent()) { setEditor(null); setBody(""); setFiles([]); setCommentVersion(null); setNotice(""); setFormError(""); }
  };
  const parentLocked = filesBusy || write.locked || query.isFetching || query.isError || row?.project_writable === false;
  const blocked = linksBusy || parentLocked;
  const available = row ? transitions[row.status].filter(value => row.status !== "cancelled" || row.can_manage || value !== "todo") : [];
  const selected = available.includes(target as WorkTransition["target_status"]) ? target : "";
  if (!row) return <div className="admin-workspace"><Link className="text-link" href="/projects">Voltar aos projetos</Link><h1 id="work-heading" tabIndex={-1}>Tarefa</h1>{query.isPending ? <LoadingRows label="Carregando tarefa..." /> : <ReadError retry={() => void query.refetch()} />}</div>;
  return <div className="admin-workspace"><Link className="text-link" href={parentDenied ? "/projects" : `/projects/${encodeURIComponent(row.project_id)}/work`}>Voltar às tarefas</Link>
    <h1 id="work-heading" tabIndex={-1}>{parentDenied ? "Tarefa" : row.title}</h1>{!parentDenied && <p className="admin-intro">{workStatuses[row.status]} · {row.work_type === "ongoing" ? "Trabalho contínuo" : "Trabalho pontual"}</p>}
    {query.isError && <ReadError retry={() => void query.refetch()} />}
    {!parentDenied && notice && <p className="read-notice" role="status">{notice}</p>}
    {!parentDenied && !row.project_writable && <p className="notice">O projeto, seu cliente ou sua equipe foi arquivado. Novas alterações estão bloqueadas.</p>}
    <WriteRecovery write={write} reload={reload} verifyLabel={write.current?.kind === "comment" ? "Verificar comentário" : write.current?.kind === "transition" ? "Verificar mudança de estado" : undefined} />
    <div className="admin-plane">{!parentDenied && <section className="admin-section" aria-labelledby="work-data-heading"><h2 id="work-data-heading">Dados da tarefa</h2>
      {editor ? <WorkForm key={editor.version} api={api} project={row.project_id} initial={editor} manage={row.can_manage} actor={session.user} locked={blocked} onSubmit={value => { setNotice(""); write.submit({ kind: "edit", body: value as WorkPatch, version: editor.version }); }} cancel={() => { setEditor(null); requestAnimationFrame(() => document.getElementById("edit-work")?.focus()); }} /> : <>
        <dl className="account-details work-facts"><div><dt>Responsável</dt><dd>{row.owner_name ?? "Sem responsável"}</dd></div><div><dt>Envolvidos</dt><dd>{row.assignees.length ? row.assignees.map(person => person.display_name).join(", ") : "Nenhum envolvido"}</dd></div><div><dt>Prioridade</dt><dd>{workPriorities[row.priority]}</dd></div><div><dt>Prazo</dt><dd>{dueLabel(row)}</dd></div><div><dt>Estimativa</dt><dd>{row.estimated_minutes === null ? "Não informada" : `${row.estimated_minutes} minutos`}</dd></div></dl>
        {row.parent_id && <p>Tarefa principal: {parent.data ? <Link className="text-link" href={`/work-items/${encodeURIComponent(row.parent_id)}`}>{parent.data.title}</Link> : parent.isError ? <Button variant="outline" onClick={() => void parent.refetch()}>Carregar tarefa principal</Button> : "Carregando..."}</p>}
        <h3 className="work-subheading">Envolvidos externos</h3><p className="field-help">Nomes informados, sem verificacao de identidade. Nao concedem acesso ao projeto.</p>
        {row.external_participants?.length ? <ul className="record-list" aria-label="Envolvidos externos">{row.external_participants.map(label => <li className="record-text" key={label}>{label}</li>)}</ul> : <p>Nenhum envolvido externo.</p>}
        <h3 className="work-subheading">Descrição</h3><p className="work-prose">{row.description || "Sem descrição."}</p>
        {row.blocked_reason && <><h3 className="work-subheading">Motivo do bloqueio</h3><p className="work-prose">{row.blocked_reason}</p></>}
        {row.can_update ? <Button id="edit-work" variant="outline" disabled={blocked} onClick={() => { setEditor(row); setNotice(""); }}>Editar tarefa</Button> : <p>Acesso de consulta a esta tarefa.</p>}
      </>}
    </section>}
    <WorkTicketLinks work={row} session={session} parentAvailable={!query.isError}
      parentLocked={parentLocked || editor !== null} onBusyChange={setLinksBusy} />
    {!parentDenied && <>
    {row.can_update && available.length > 0 && <section className="admin-section" aria-labelledby="work-transition-heading"><h2 id="work-transition-heading">Mudar estado</h2>
      <form noValidate onSubmit={event => { event.preventDefault(); setFormError(""); if (!selected) { setFormError("Escolha o próximo estado."); return; } if ((selected === "blocked" || row.status === "done" || row.status === "cancelled" || (selected === "done" && row.work_type === "ongoing")) && !reason.trim()) { setFormError("Informe o motivo desta mudança."); return; } if (selected === "done" && row.work_type === "ongoing" && !end) { setFormError("Confirme o encerramento da operação contínua."); return; } setNotice(""); write.submit({ kind: "transition", body: { target_status: selected, reason: reason.trim() || null, end_operation: end }, version: row.version, key: crypto.randomUUID() }); }}>
        <fieldset className="work-fields" disabled={blocked || editor !== null}><div className="account-form-grid"><div><label htmlFor="work-target">Próximo estado</label><select id="work-target" value={selected} onChange={event => setTarget(event.target.value as typeof target)}><option value="">Escolha um estado</option>{available.map(value => <option key={value} value={value}>{workStatuses[value]}</option>)}</select></div><div><label htmlFor="work-reason">Motivo</label><textarea id="work-reason" value={reason} maxLength={2000} rows={3} onChange={event => setReason(event.target.value)} /></div></div>
          {row.work_type === "ongoing" && selected === "done" && <label className="work-checkbox"><input type="checkbox" checked={end} onChange={event => setEnd(event.target.checked)} />Confirmo o encerramento desta operação contínua</label>}
          {formError && <p className="field-error" role="alert">{formError}</p>}<Button type="submit" className="work-transition-action">Alterar estado</Button>
        </fieldset>
      </form>
    </section>}
    <section className="admin-section" aria-labelledby="work-comments-heading"><h2 id="work-comments-heading">Comentários internos</h2><p className="field-help">Visíveis a quem tem acesso ao projeto. Não enviam e-mail nem mensagem ao cliente.</p>
      <AttachmentPicker scope={{ owner: "work_item", id, purpose: "work" }} version={row.version} selected={files} change={next => { setFiles(next); setCommentVersion(commentVersion ?? row.version); }} disabled={linksBusy || write.locked || query.isFetching || query.isError || !row.can_comment || editor !== null} busyChanged={busyChanged} />
      {row.can_comment && <form className="work-comment-form" onSubmit={event => { event.preventDefault(); if (body.trim()) { setNotice(""); write.submit({ kind: "comment", body: body.trim(), files: [...files], version: commentVersion ?? row.version, key: crypto.randomUUID() }); } }}><label htmlFor="work-comment">Comentário interno</label><textarea id="work-comment" value={body} maxLength={10000} rows={4} disabled={blocked || editor !== null} onChange={event => { setBody(event.target.value); setCommentVersion(commentVersion ?? row.version); }} /><Button type="submit" disabled={blocked || editor !== null || !body.trim()}>Registrar comentário</Button></form>}
      <Comments id={id} api={api} />
    </section><StateHistory id={id} api={api} /><WorkActivity id={id} api={api} /></>}
    </div>
  </div>;
}
