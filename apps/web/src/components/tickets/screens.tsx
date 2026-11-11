"use client";

import { IdentityBoundary, useWorkspaceSession } from "@/components/workspace-session";
import { createTicketApi } from "@/lib/tickets";
import { createQueueApi } from "@/lib/ticket-queues";
import { TicketDirectory } from "./directory";
import { NewTicket } from "./new";
import { TicketDetail } from "./detail";

function Content({ id, create }: { id?: string; create?: boolean }) {
  const session = useWorkspaceSession();
  const api = createTicketApi(session.user.csrf_token, session.onAuthError);
  const queues = createQueueApi(session.user.csrf_token, session.onAuthError);
  if (create) return <NewTicket api={api} queues={queues} session={session} />;
  if (id) return <TicketDetail key={id} id={id} api={api} queues={queues} session={session} />;
  return <TicketDirectory api={api} actor={session.user.id} />;
}

export function TicketsScreen({ id, create }: { id?: string; create?: boolean }) {
  return <IdentityBoundary location="Service Desk" headingId={create ? "ticket-new-heading" : id ? "ticket-heading" : "tickets-heading"} wide><Content id={id} create={create} /></IdentityBoundary>;
}
