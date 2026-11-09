"use client";

import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { LogOut, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { IdentityBoundary, useWorkspaceSession } from "@/components/workspace-session";
import { ApiError, logout } from "@/lib/auth";

function Account() {
  const { user, onLogout, onRefresh } = useWorkspaceSession();
  const mutation = useMutation({ mutationFn: () => logout(user.csrf_token), onSuccess: onLogout,
    onError(error) { if (error instanceof ApiError && error.status === 403) onRefresh(); } });
  return <section className="working-surface" aria-labelledby="account-heading">
    <h1 id="account-heading" tabIndex={-1}>Minha conta</h1>
    <p className="intro">Você está conectado ao Altvia Workspace.</p>
    <dl className="account-details">
      <div><dt>Nome</dt><dd>{user.display_name}</dd></div>
      <div><dt>E-mail</dt><dd>{user.email}</dd></div>
    </dl>
    {user.capabilities.includes("identity.manage") && <div className="account-admin-link">
      <Button variant="outline" asChild><Link href="/admin/teams">Administrar equipes</Link></Button>
      <Button variant="outline" asChild><Link href="/admin/users">Administrar contas</Link></Button>
    </div>}
    <div className="session-actions">
      {mutation.isError && <p className="error-message" role="alert">Não foi possível sair. Sua sessão pode continuar ativa. Tente novamente.</p>}
      <Button variant="outline" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
        {mutation.isPending ? <LoaderCircle size={18} className="spinner" aria-hidden="true" /> : <LogOut size={18} aria-hidden="true" />}
        {mutation.isPending ? "Saindo..." : "Sair da conta"}
      </Button>
    </div>
  </section>;
}

export function IdentityScreen() {
  return <IdentityBoundary location="Minha conta" headingId="account-heading"><Account /></IdentityBoundary>;
}
