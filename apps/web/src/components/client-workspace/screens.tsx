"use client";

import { IdentityBoundary, useWorkspaceSession } from "@/components/workspace-session";
import { createClientApi } from "@/lib/clients";
import { ClientDirectory } from "./directory";
import { ClientDetail } from "./detail";
import { ContactDirectory, ContactDetail } from "./contacts";

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

function Contacts({ id, contactId }: { id: string; contactId?: string }) {
  const session = useWorkspaceSession();
  const api = createClientApi(session.user.csrf_token, session.onAuthError);
  return contactId ? <ContactDetail key={`${id}:${contactId}`} id={id} contactId={contactId} api={api} session={session} /> : <ContactDirectory key={id} id={id} api={api} session={session} />;
}
export function ContactScreen({ id, contactId }: { id: string; contactId?: string }) {
  return <IdentityBoundary location="Contatos" headingId={contactId ? "contact-heading" : "contacts-heading"} wide><Contacts id={id} contactId={contactId} /></IdentityBoundary>;
}
