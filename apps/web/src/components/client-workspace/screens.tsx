"use client";

import { IdentityBoundary, useWorkspaceSession } from "@/components/workspace-session";
import { createClientApi } from "@/lib/clients";
import { ClientDirectory } from "./directory";
import { ClientDetail } from "./detail";

function Content({ id }: { id?: string }) {
  const session = useWorkspaceSession();
  const api = createClientApi(session.user.csrf_token, session.onAuthError);
  return id ? <ClientDetail key={id} id={id} api={api} session={session} /> : <ClientDirectory api={api} session={session} />;
}
export function ClientDirectoryScreen() {
  return <IdentityBoundary location="Clientes" headingId="clients-heading" wide><Content /></IdentityBoundary>;
}
export function ClientDetailScreen({ id }: { id: string }) {
  return <IdentityBoundary location="Clientes" headingId="client-heading" wide><Content id={id} /></IdentityBoundary>;
}
