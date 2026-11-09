"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import type { WorkspaceSession } from "@/components/workspace-session";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import type { TeamApi } from "@/lib/teams";
import type { AccountApi, AccountCreate } from "@/lib/users";
import { AccountWriteFeedback, passwordError, useAccountWrite } from "./write";

const schema = z.object({ display_name: z.string().trim().refine(value =>
  Array.from(value).length >= 1 && Array.from(value).length <= 150, "Use um nome de 1 a 150 caracteres."),
  email: z.string().trim().max(254).pipe(z.email("Informe um e-mail válido.")) });

export function AccountDirectory({ api, teams, session }: { api: AccountApi; teams: TeamApi; session: WorkspaceSession }) {
  const router = useRouter();
  const paging = usePaging();
  const password = useRef<HTMLInputElement>(null);
  const [invalidPassword, setInvalidPassword] = useState("");
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { email: "", display_name: "" } });
  const query = useQuery({ queryKey: ["users", paging.cursor], queryFn: ({ signal }) => teams.users(paging.cursor, signal) });
  const write = useAccountWrite(session, (intent: AccountCreate & { key: string }) => {
    const { key, ...body } = intent; return api.create(body, key);
  }, result => router.push(`/admin/users/${encodeURIComponent(result.id)}`));
  return <div className="admin-workspace">
    <div className="action-row"><Link className="text-link" href="/">Voltar à minha conta</Link>
      <Link className="text-link" href="/admin/teams">Administrar equipes</Link></div>
    <h1 id="users-heading" tabIndex={-1}>Contas</h1>
    <p className="admin-intro">Crie contas e gerencie o acesso de cada pessoa. Novas contas começam sem permissões administrativas ou acesso a equipes.</p>
    <div className="admin-plane"><section className="admin-section" aria-labelledby="new-account-heading">
      <h2 id="new-account-heading">Nova conta</h2>
      <form noValidate onSubmit={event => void form.handleSubmit(value => {
        const secret = password.current?.value ?? "";
        const error = passwordError(secret); setInvalidPassword(error);
        if (error) { password.current?.focus(); return; }
        write.submit({ ...value, password: secret, key: crypto.randomUUID() });
        if (password.current) password.current.value = "";
      })(event)}>
        <div className="account-form-grid">
          <div className="field"><label htmlFor="new-account-name">Nome da nova conta</label>
            <input id="new-account-name" maxLength={300} autoComplete="off" {...form.register("display_name")} disabled={write.locked}
              aria-invalid={!!form.formState.errors.display_name} aria-describedby="new-account-name-error" />
            <p id="new-account-name-error" className="field-error">{form.formState.errors.display_name?.message}</p></div>
          <div className="field"><label htmlFor="new-account-email">E-mail da nova conta</label>
            <input id="new-account-email" type="email" maxLength={254} autoComplete="off" autoCapitalize="none" spellCheck={false}
              {...form.register("email")} disabled={write.locked} aria-invalid={!!form.formState.errors.email} aria-describedby="new-account-email-error" />
            <p id="new-account-email-error" className="field-error">{form.formState.errors.email?.message}</p></div>
          <div className="field"><label htmlFor="new-account-password">Senha inicial</label>
            <input id="new-account-password" type="password" autoComplete="new-password" ref={password} disabled={write.locked}
              maxLength={2048} aria-invalid={!!invalidPassword} aria-describedby="new-account-password-help" />
            <p id="new-account-password-help" className={invalidPassword ? "field-error" : "field-help"}>
              {invalidPassword || "Pelo menos 14 caracteres; até 1024 bytes. Informe a senha à pessoa por um canal seguro."}</p></div>
        </div>
        <Button type="submit" disabled={write.locked || !query.data || query.isError}>Criar conta</Button>
      </form>
      <AccountWriteFeedback write={write} reload={async () => { await query.refetch({ throwOnError: true }); }} />
    </section><section className="admin-section" aria-labelledby="account-list-heading">
      <h2 id="account-list-heading">Contas cadastradas</h2>
      {query.isPending ? <LoadingRows label="Carregando contas..." />
        : query.isError ? <ReadError retry={() => void query.refetch()} />
          : query.data.items.length ? <ul className="record-list" aria-label="Contas cadastradas">
            {query.data.items.map(account => <li className="team-row" key={account.id}><div className="record-text">
              <Link className="team-link" href={`/admin/users/${account.id}`}>{account.display_name}</Link>
              <span className="record-meta">{account.email}</span></div><span className="record-status">{account.active ? "Ativa" : "Desativada"}</span></li>)}
          </ul> : <p>{paging.index ? "Nenhuma conta nesta página. Volte à página anterior." : "Nenhuma conta cadastrada."}</p>}
      <Paging paging={paging} next={query.data?.next_cursor} label="contas" disabled={write.locked || query.isFetching} />
    </section></div>
  </div>;
}
