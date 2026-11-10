"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, type UseFormReturn } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, nameSchema, usePaging, useTeamWrite, writeError } from "@/components/team-admin/common";
import type { WorkspaceSession } from "@/components/workspace-session";
import type { ClientApi, ContactCreate } from "@/lib/clients";

// ADR-0022's bounded ASCII dot-atom policy; the API remains authoritative.
const atom = "[a-z0-9!#$%&'*+/=?^_`{|}~-]+";
const label = "[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?";
const mailbox = new RegExp(`^${atom}(?:\\.${atom})*@${label}(?:\\.${label})+$`, "i");
const emailSchema = z.string().refine(value => /^[\x20-\x7e]*$/.test(value), "Use um endereco de e-mail sem acentos ou caracteres especiais de outros alfabetos.")
  .trim().max(254, "Use um e-mail de ate 254 caracteres.")
  .refine(value => mailbox.test(value) && value.split("@")[0].length <= 64, "Informe um e-mail valido.");
const schema = z.object({ display_name: nameSchema.shape.name, email: emailSchema });
type Fields = z.infer<typeof schema>;
const explanation = "Contatos sao pessoas externas deste cliente. O cadastro nao cria uma conta nem concede acesso. O e-mail permanece nao verificado.";
function ContactFields({ form, disabled }: { form: UseFormReturn<Fields>; disabled: boolean }) {
  useLayoutEffect(() => { form.setFocus("display_name"); }, [form]);
  return <div className="account-form-grid">
    <div><label htmlFor="contact-name">Nome do contato</label><input id="contact-name" maxLength={300} {...form.register("display_name")} disabled={disabled} aria-invalid={!!form.formState.errors.display_name} aria-describedby="contact-name-error" />
      <p id="contact-name-error" className="field-error">{form.formState.errors.display_name?.message}</p></div>
    <div><label htmlFor="contact-email">E-mail do contato</label><input id="contact-email" type="email" autoCapitalize="none" maxLength={254} {...form.register("email")} disabled={disabled} aria-invalid={!!form.formState.errors.email} aria-describedby="contact-email-error" />
      <p id="contact-email-error" className="field-error">{form.formState.errors.email?.message}</p></div>
  </div>;
}

export function ContactDirectory({ id, api, session }: { id: string; api: ClientApi; session: WorkspaceSession }) {
  const cache = useQueryClient();
  const router = useRouter();
  const parent = useQuery({ queryKey: ["client", id], queryFn: ({ signal }) => api.get(id, signal) });
  const paging = usePaging();
  const query = useQuery({ queryKey: ["client-contacts", id, paging.cursor], queryFn: ({ signal }) => api.contacts(id, paging.cursor, signal) });
  const [creating, setCreating] = useState(false);
  const form = useForm<Fields>({ resolver: zodResolver(schema), defaultValues: { display_name: "", email: "" } });
  const write = useTeamWrite(session, (intent: ContactCreate & { key: string }) => {
    const { key, ...body } = intent; return api.createContact(id, body, key);
  }, receipt => {
    void cache.invalidateQueries({ queryKey: ["client", id] });
    void cache.invalidateQueries({ queryKey: ["client-activity", id] });
    void cache.invalidateQueries({ queryKey: ["client-contacts", id] });
    void cache.invalidateQueries({ queryKey: ["clients"] });
    router.push(`/clients/${id}/contacts/${receipt.contact_id}`);
  });
  const refresh = async () => { await Promise.all([parent.refetch({ throwOnError: true }), query.refetch({ throwOnError: true })]); };
  const allowed = parent.isSuccess && parent.data.can_manage && parent.data.active;
  const blocked = !allowed || parent.isFetching || write.locked;
  return <div className="admin-workspace">
    <Link className="text-link" href={`/clients/${id}`}>Voltar ao cliente</Link>
    <h1 id="contacts-heading" tabIndex={-1}>Contatos</h1>
    <p className="admin-intro">{explanation}</p>
    {parent.isPending ? <LoadingRows label="Carregando cliente..." /> : parent.isError ? <ReadError retry={() => void parent.refetch()}>Este cliente nao esta disponivel para sua conta.</ReadError> : <p>{parent.data.name}{!parent.data.active && " - Cliente arquivado"}</p>}
    <div className="admin-plane">
      <section className="admin-section" aria-labelledby="contact-list-heading">
        <h2 id="contact-list-heading">Contatos do cliente</h2>
        <Button variant="outline" disabled={query.isFetching || parent.isFetching} onClick={() => void refresh().catch(() => {})}>Atualizar contatos</Button>
        {query.isPending ? <LoadingRows label="Carregando contatos..." /> : query.isError ? <ReadError retry={() => void refresh().catch(() => {})} /> : query.data.items.length ? <ul className="record-list" aria-label="Contatos do cliente">{query.data.items.map(row => <li className="team-row" key={row.id}>
          <div className="record-text"><Link className="text-link" href={`/clients/${id}/contacts/${row.id}`}>{row.display_name}</Link><span className="record-meta">{row.email_normalized}</span></div>
          <span className="record-status">{row.active ? "Contato ativo" : "Contato arquivado"}</span>
        </li>)}</ul> : <p>Nenhum contato cadastrado.</p>}
        <Paging paging={paging} next={query.data?.next_cursor} label="contatos" disabled={query.isFetching} />
      </section>
      <section className="admin-section" aria-labelledby="new-contact-heading">
        <h2 id="new-contact-heading">Cadastro de contato</h2>
        {parent.isSuccess && !parent.data.can_manage && <p>Acesso somente para consulta.</p>}
        {parent.isSuccess && !parent.data.active && <p>Restaure o cliente para cadastrar ou alterar contatos.</p>}
        {!creating ? allowed && <Button id="new-contact" onClick={() => setCreating(true)}>Novo contato</Button> : <form noValidate onSubmit={form.handleSubmit(value => { if (!blocked) write.submit({ ...value, key: crypto.randomUUID() }); })}>
          <ContactFields form={form} disabled={blocked} />
          <div className="action-row"><Button type="submit" disabled={blocked}>{write.pending ? "Cadastrando..." : "Cadastrar contato"}</Button>
            <Button type="button" variant="outline" disabled={write.locked} onClick={() => { setCreating(false); form.reset(); requestAnimationFrame(() => document.getElementById("new-contact")?.focus()); }}>Cancelar cadastro</Button></div>
        </form>}
        {write.error && <div className="read-error"><p role="alert">{writeError(write.error)}</p>
          {write.uncertain ? <Button variant="outline" disabled={write.pending || write.reloading} onClick={write.verify}>Verificar cadastro do contato</Button> : write.locked && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(refresh)}>Recarregar para revisar cadastro</Button>}</div>}
        {write.reloadFailed && <p role="alert">Nao foi possivel atualizar. O cadastro anterior continua bloqueado.</p>}
      </section>
    </div>
  </div>;
}

type Intent = { version: number } & (Fields | { active: boolean });
export function ContactDetail({ id, contactId, api, session }: { id: string; contactId: string; api: ClientApi; session: WorkspaceSession }) {
  const cache = useQueryClient();
  const parent = useQuery({ queryKey: ["client", id], queryFn: ({ signal }) => api.get(id, signal) });
  const query = useQuery({ queryKey: ["client-contact", id, contactId], queryFn: ({ signal }) => api.contact(id, contactId, signal) });
  const row = query.data;
  const [editing, setEditing] = useState(false);
  const [version, setVersion] = useState(1);
  const [confirm, setConfirm] = useState<number | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [notice, setNotice] = useState("");
  const form = useForm<Fields>({ resolver: zodResolver(schema), defaultValues: { display_name: "", email: "" } });
  const write = useTeamWrite(session, (intent: Intent) => { const { version, ...body } = intent; return api.updateContact(id, contactId, body, version); }, result => {
    cache.setQueryData(["client-contact", id, contactId], result);
    for (const key of [["client", id], ["clients"], ["client-contacts", id], ["client-activity", id]]) void cache.invalidateQueries({ queryKey: key });
    setEditing(false); setConfirm(null); setNotice("Alteracao confirmada.");
    requestAnimationFrame(() => document.getElementById("contact-heading")?.focus());
  });
  useEffect(() => { if (confirm !== null) heading.current?.focus(); }, [confirm]);
  const refresh = async () => { await Promise.all([query.refetch({ throwOnError: true }), parent.refetch({ throwOnError: true })]); if (session.isCurrent()) { setEditing(false); setConfirm(null); setNotice(""); } };
  const allowed = parent.isSuccess && parent.data.can_manage && parent.data.active;
  const blocked = !allowed || parent.isFetching || query.isFetching || query.isError || write.locked;
  return <div className="admin-workspace">
    <Link className="text-link" href={`/clients/${id}/contacts`}>Voltar aos contatos</Link>
    {query.isPending ? <LoadingRows label="Carregando contato..." /> : query.isError ? <><h1 id="contact-heading" tabIndex={-1}>Contato indisponivel</h1><ReadError retry={() => void query.refetch()} /></> : row && <>
      <h1 id="contact-heading" tabIndex={-1}>{row.display_name}</h1>
      {parent.isSuccess && <p>Cliente: <Link className="text-link" href={`/clients/${id}`}>{parent.data.name}</Link></p>}
      <p className="admin-intro">{explanation}</p>
      {notice && <p role="status" className="read-notice">{notice}</p>}
      <div className="admin-plane"><section className="admin-section" aria-labelledby="contact-data-heading">
        <h2 id="contact-data-heading">Dados do contato</h2>
        <p>{row.email_normalized}</p><p>{row.active ? "Contato ativo" : "Contato arquivado"}</p><p className="field-help">E-mail nao verificado</p>
        {parent.isPending ? <LoadingRows label="Verificando acesso..." /> : parent.isError ? <ReadError retry={() => void parent.refetch()}>Nao foi possivel verificar o acesso ao cliente.</ReadError> : !parent.data.can_manage ? <p>Acesso somente para consulta.</p> : !parent.data.active ? <p>Restaure o cliente para alterar contatos.</p> : editing ? <form noValidate onSubmit={form.handleSubmit(value => { if (!blocked) write.submit({ ...value, version }); })}>
          <ContactFields form={form} disabled={write.locked} /><div className="action-row"><Button type="submit" disabled={blocked}>Salvar contato</Button><Button type="button" variant="outline" disabled={write.locked} onClick={() => { setEditing(false); requestAnimationFrame(() => document.getElementById("edit-contact")?.focus()); }}>Cancelar edicao</Button></div>
        </form> : <div className="action-row">
          <Button id="edit-contact" variant="outline" disabled={blocked || confirm !== null} onClick={() => { form.reset({ display_name: row.display_name, email: row.email_normalized }); setVersion(row.version); setEditing(true); setNotice(""); }}>Editar contato</Button>
          <Button id="contact-state" variant="outline" disabled={blocked || confirm !== null} onClick={() => { if (row.active) setConfirm(row.version); else write.submit({ active: true, version: row.version }); }}>{row.active ? "Arquivar contato" : "Restaurar contato"}</Button>
        </div>}
        {confirm !== null && <div className="confirmation" role="group" aria-labelledby="archive-contact-heading"><h3 id="archive-contact-heading" ref={heading} tabIndex={-1}>Arquivar este contato?</h3><p>O cadastro sera preservado e podera ser restaurado.</p><div className="action-row"><Button disabled={blocked} onClick={() => write.submit({ active: false, version: confirm })}>Confirmar arquivamento</Button><Button variant="outline" disabled={write.locked} onClick={() => { setConfirm(null); requestAnimationFrame(() => document.getElementById("contact-state")?.focus()); }}>Cancelar</Button></div></div>}
      </section></div>
    </>}
    {write.error && <div className="read-error"><p role="alert">{writeError(write.error)}</p><Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(refresh)}>Recarregar e descartar edicao</Button></div>}
    {write.reloadFailed && <p role="alert">Nao foi possivel atualizar. A edicao continua bloqueada.</p>}
  </div>;
}
