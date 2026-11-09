"use client";

import Link from "next/link";
import { IdentityBoundary, useWorkspaceSession } from "@/components/workspace-session";
import { createTeamApi } from "@/lib/teams";
import { createAccountApi } from "@/lib/users";
import { AccountDirectory } from "./directory";
import { AccountDetail } from "./detail";

function Content({ id }: { id?: string }) {
  const session = useWorkspaceSession();
  if (!session.user.capabilities.includes("identity.manage")) return <section className="working-surface access-surface">
    <h1 id={id ? "user-heading" : "users-heading"} tabIndex={-1}>Acesso restrito</h1>
    <p className="intro">Sua conta não tem permissão para administrar contas e acessos.</p>
    <Link className="text-link" href="/">Voltar à minha conta</Link></section>;
  const api = createAccountApi(session.user.csrf_token, session.onAuthError);
  const teams = createTeamApi(session.user.csrf_token, session.onAuthError);
  return id ? <AccountDetail key={id} id={id} api={api} teams={teams} session={session} />
    : <AccountDirectory api={api} teams={teams} session={session} />;
}
export function AccountDirectoryScreen() {
  return <IdentityBoundary location="Contas" headingId="users-heading" wide><Content /></IdentityBoundary>;
}
export function AccountDetailScreen({ id }: { id: string }) {
  return <IdentityBoundary location="Contas" headingId="user-heading" wide><Content id={id} /></IdentityBoundary>;
}
