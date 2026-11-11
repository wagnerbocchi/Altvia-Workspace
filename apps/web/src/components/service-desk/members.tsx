"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, Paging, ReadError, usePaging, useTeamWrite, writeError } from "@/components/team-admin/common";
import type { QueueApi, QueueMember, QueueMemberRole } from "@/lib/ticket-queues";
import { ApiError } from "@/lib/http";

const roles: Record<QueueMemberRole, string> = { viewer: "Consulta", agent: "Agente", operations_manager: "Gestor de atendimento" };
const schema = z.object({
  email: z.string().trim().min(3, "Informe o e-mail da conta.").max(254, "Use ate 254 caracteres.")
    .refine(value => { const parts = value.split("@"); return parts.length === 2 && !!parts[0] && parts[1].includes(".") && !/\s/.test(value); }, "Informe um e-mail valido."),
  role_name: z.enum(["viewer", "agent", "operations_manager"]),
});
type Fields = z.infer<typeof schema>;
type Editor = { member: QueueMember; version: number; remove: boolean };
type Intent = { version: number } & (
  { kind: "add"; email: string; role_name: QueueMemberRole; key: string }
  | { kind: "change"; userId: string; role: QueueMemberRole | null }
);

function RoleOptions() {
  return <>{Object.entries(roles).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</>;
}

export function QueueMemberDirectory({ id, api, session }: { id: string; api: QueueApi; session: WorkspaceSession }) {
  const cache = useQueryClient();
  const parent = useQuery({ queryKey: ["ticket-queue", id], queryFn: ({ signal }) => api.get(id, signal) });
  const paging = usePaging();
  const query = useQuery({ queryKey: ["queue-members", id, paging.cursor], queryFn: ({ signal }) => api.members(id, paging.cursor, signal) });
  const [creating, setCreating] = useState(false), [addVersion, setAddVersion] = useState(1);
  const [reviewedAdd, setReviewedAdd] = useState<Extract<Intent, { kind: "add" }> | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null), [role, setRole] = useState<QueueMemberRole>("viewer");
  const [selfConfirm, setSelfConfirm] = useState(false);
  const [needsReview, setNeedsReview] = useState(false), [notice, setNotice] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const grantHeading = useRef<HTMLHeadingElement>(null);
  const form = useForm<Fields>({ resolver: zodResolver(schema), defaultValues: { email: "", role_name: "agent" } });
  const refresh = async () => { await Promise.all([parent.refetch({ throwOnError: true }), query.refetch({ throwOnError: true })]); };
  const close = () => {
    setCreating(false); setEditor(null); setSelfConfirm(false); setReviewedAdd(null); form.reset();
    requestAnimationFrame(() => document.getElementById("members-heading")?.focus());
  };
  const completeRefresh = async () => {
    await refresh();
    if (session.isCurrent()) { setNeedsReview(false); close(); }
  };
  const write = useTeamWrite(session, async (intent: Intent) => {
    if (intent.kind === "add") return api.addMember(id, { email: intent.email, role_name: intent.role_name }, intent.version, intent.key);
    await api.changeMember(id, intent.userId, intent.role, intent.version);
    return { user_id: intent.userId };
  }, result => {
    setNotice("Solicitacao confirmada. Confira o acesso atual na lista.");
    if (result.user_id === session.user.id) { session.onRefresh(); return; }
    setNeedsReview(true);
    for (const key of [["ticket-queues"], ["queue-activity", id]]) void cache.invalidateQueries({ queryKey: key });
    void completeRefresh().catch(() => {});
  });
  useEffect(() => { if (editor) heading.current?.focus(); }, [editor]);
  useEffect(() => { if (creating) form.setFocus("email"); }, [creating, form]);
  useEffect(() => { if (reviewedAdd) grantHeading.current?.focus(); }, [reviewedAdd]);
  const allowed = parent.isSuccess && parent.data.can_manage;
  const consistent = parent.isSuccess && query.isSuccess && parent.data.version === query.data.queue_version;
  const blocked = !allowed || !consistent || parent.isFetching || query.isFetching || write.locked || needsReview;
  const grantBlocked = blocked || !parent.data?.active || !parent.data?.team_active;
  const editingSelf = editor?.member.id === session.user.id;
  const sessionWarning = "Sua sessao sera encerrada. Sera necessario entrar novamente.";
  const review = async () => { await refresh(); if (session.isCurrent()) { close(); setNeedsReview(false); setNotice(""); } };
  const edit = (member: QueueMember, remove: boolean) => {
    if (blocked) return;
    setCreating(false); setSelfConfirm(false); setNotice("");
    setRole(member.role_name as QueueMemberRole);
    setEditor({ member: { ...member }, version: query.data!.queue_version, remove });
  };
  const submitRole = () => {
    if (!editor || blocked) return;
    if (editingSelf && role !== editor?.member.role_name && !selfConfirm) { setSelfConfirm(true); return; }
    write.submit({ kind: "change", userId: editor.member.id, role, version: editor.version });
  };

  return <div className="admin-workspace">
    <Link className="text-link" href={`/service-desk/queues/${encodeURIComponent(id)}`}>Voltar a fila</Link>
    <h1 id="members-heading" tabIndex={-1}>Membros da fila</h1>
    <p className="admin-intro">Gerencie acessos diretos. Alteracoes encerram as sessoes da conta afetada e preservam o historico.</p>
    {parent.isPending ? <LoadingRows label="Carregando fila..." /> : parent.isError ? <ReadError retry={() => void refresh().catch(() => {})}>{parent.error instanceof ApiError && parent.error.status === 404 ? "Esta fila nao esta disponivel para sua conta." : undefined}</ReadError> : <p>{parent.data.name}{!parent.data.active && " - Fila arquivada"}</p>}
    {notice && <p role="status" className="read-notice">{notice}</p>}
    {needsReview && <div className="read-notice"><p>Atualize os dados para conferir o resultado antes de outra alteracao.</p><Button variant="outline" disabled={query.isFetching || parent.isFetching} onClick={() => void completeRefresh().catch(() => {})}>Conferir acesso atual</Button></div>}
    <div className="admin-plane">
      <section className="admin-section" aria-labelledby="member-list-heading">
        <h2 id="member-list-heading">Acessos diretos</h2>
        <Button variant="outline" disabled={query.isFetching || parent.isFetching || write.pending} onClick={() => void refresh().catch(() => {})}>Atualizar membros</Button>
        {query.isPending ? <LoadingRows label="Carregando membros..." /> : query.isError ? <ReadError retry={() => void refresh().catch(() => {})} /> : !parent.isSuccess ? null : query.data.items.length ? <ul className="record-list" aria-label="Membros da fila">{query.data.items.map(member => <li className="member-row" key={member.id}>
          <div className="record-text"><strong>{member.display_name}{member.id === session.user.id && " (voce)"}</strong><span className="record-meta">{roles[member.role_name as QueueMemberRole] ?? "Acesso da fila"}</span><span className="record-meta">{member.active ? "Conta ativa" : "Conta desativada"}</span></div>
          {allowed && <div className="action-row"><Button variant="outline" disabled={blocked || !!editor || creating || (!parent.data.active || !parent.data.team_active)} onClick={() => edit(member, false)}>Alterar papel</Button><Button variant="outline" disabled={blocked || !!editor || creating} onClick={() => edit(member, true)}>Remover acesso</Button></div>}
        </li>)}</ul> : <p>Nenhum membro nesta pagina.</p>}
        <Paging paging={paging} next={query.data?.next_cursor} label="membros da fila" disabled={query.isFetching || write.locked || !!editor || creating || needsReview} />
        {parent.isSuccess && query.isSuccess && !consistent && <p role="alert">A lista mudou. Atualize os membros antes de alterar um acesso.</p>}
      </section>
      <section className="admin-section" aria-labelledby="member-access-heading">
        <h2 id="member-access-heading">Acesso a fila</h2>
        {parent.isSuccess && !allowed && <p>Acesso somente para consulta.</p>}
        {parent.isSuccess && (!parent.data.active || !parent.data.team_active) && <p>Restaure a fila e a equipe para conceder acesso ou alterar papeis. A remocao continua disponivel.</p>}
        <p className="field-help">Somente contas existentes. O acesso aos clientes e administrado separadamente. O papel Gestor de atendimento tem escopo na fila. A configuracao exige permissao independente.</p>
        {editor ? <div className="confirmation" role="group" aria-labelledby="member-edit-heading">
          <h3 id="member-edit-heading" tabIndex={-1} ref={heading}>{editor.remove ? "Remover acesso direto?" : "Alterar papel na fila"}</h3>
          <p>{editor.member.display_name} - {roles[editor.member.role_name as QueueMemberRole]}</p>
          {editor.remove ? <><p>O historico sera preservado. Permissoes de configuracao e de clientes permanecem independentes.</p>{editingSelf && <p>{sessionWarning}</p>}
            <div className="action-row add-member-action"><Button disabled={blocked} onClick={() => write.submit({ kind: "change", userId: editor.member.id, role: null, version: editor.version })}>Confirmar remocao</Button><Button variant="outline" disabled={write.locked} onClick={close}>Cancelar alteracao</Button></div>
          </> : <>
            <label htmlFor="member-role">Novo papel</label><select id="member-role" value={role} onChange={event => { setRole(event.target.value as QueueMemberRole); setSelfConfirm(false); }} disabled={blocked}><RoleOptions /></select>
            {editingSelf && role !== editor?.member.role_name && <p>{sessionWarning}</p>}
            {selfConfirm && <p role="alert">Confirme a alteracao do seu proprio acesso.</p>}
            <div className="action-row add-member-action"><Button disabled={grantBlocked} onClick={submitRole}>{selfConfirm ? "Confirmar meu novo papel" : "Salvar papel"}</Button><Button variant="outline" disabled={write.locked} onClick={close}>Cancelar alteracao</Button></div>
          </>}
        </div> : creating ? <form noValidate onSubmit={form.handleSubmit(value => { if (!grantBlocked && !reviewedAdd) setReviewedAdd(Object.freeze({ kind: "add", ...value, version: addVersion, key: crypto.randomUUID() })); })}>
          <div><label htmlFor="member-email">E-mail da conta</label><input id="member-email" type="email" autoComplete="off" autoCapitalize="none" spellCheck={false} maxLength={254} {...form.register("email")} disabled={grantBlocked || !!reviewedAdd} aria-invalid={!!form.formState.errors.email} aria-describedby="member-email-help member-email-error" /><p id="member-email-error" className="field-error" role="alert">{form.formState.errors.email?.message}</p></div>
          <p id="member-email-help" className="field-help">Confira o endereco antes de confirmar. Se usar seu proprio e-mail para alterar seu acesso, sera necessario entrar novamente.</p>
          <label htmlFor="member-new-role">Papel na fila</label><select id="member-new-role" {...form.register("role_name")} disabled={grantBlocked || !!reviewedAdd}><RoleOptions /></select>
          {reviewedAdd ? <div className="confirmation" role="group" aria-labelledby="member-grant-heading">
            <h3 id="member-grant-heading" ref={grantHeading} tabIndex={-1}>Confirmar papel na fila?</h3>
            <p>{reviewedAdd.email} - {roles[reviewedAdd.role_name]}</p>
            <p>O papel selecionado substitui qualquer acesso direto ja existente desta conta.</p>
            <p>Se esta for sua conta, sera necessario entrar novamente. A configuracao da fila tem permissao independente.</p>
            <div className="action-row add-member-action"><Button type="button" disabled={grantBlocked} onClick={() => write.submit(reviewedAdd)}>{write.pending ? "Enviando..." : "Conceder acesso"}</Button><Button type="button" variant="outline" disabled={write.locked} onClick={close}>Cancelar cadastro</Button></div>
          </div> : <div className="action-row add-member-action"><Button type="submit" disabled={grantBlocked}>Revisar acesso</Button><Button type="button" variant="outline" disabled={write.locked} onClick={close}>Cancelar cadastro</Button></div>}
        </form> : allowed && <Button id="new-member" disabled={grantBlocked} onClick={() => { setCreating(true); setNotice(""); setAddVersion(query.data!.queue_version); }}>Adicionar membro</Button>}
        {write.error && <div className="read-error"><p role="alert">{write.error instanceof ApiError && write.error.code === "invalid_queue_member" ? "Conta indisponivel para esta fila. Confira o e-mail e se a conta esta ativa." : write.error instanceof ApiError && write.error.code === "version_conflict" ? "Os dados foram alterados em outra sessao. Recarregue para revisar." : writeError(write.error)}</p>
          {write.uncertain && write.current?.kind === "add" ? <Button variant="outline" disabled={write.pending || write.reloading} onClick={write.verify}>Verificar concessao</Button> : write.locked && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(review)}>Recarregar para revisar</Button>}
        </div>}
        {write.reloadFailed && <p role="alert">Nao foi possivel atualizar. A alteracao anterior continua bloqueada.</p>}
      </section>
    </div>
  </div>;
}
