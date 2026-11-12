"use client";

import { IdentityBoundary, useWorkspaceSession } from "@/components/workspace-session";
import { createMailCaseApi } from "@/lib/mail-cases";
import { createTicketApi } from "@/lib/tickets";
import { createQueueApi } from "@/lib/ticket-queues";
import { MailCaseDirectory } from "./directory";
import { MailCaseDetail } from "./detail";

function Content({ id }: { id?: string }) {
  const session = useWorkspaceSession();
  const api = createMailCaseApi(session.user.csrf_token, session.onAuthError);
  return id ? <MailCaseDetail key={id} id={id} api={api} tickets={createTicketApi(session.user.csrf_token, session.onAuthError)} queues={createQueueApi(session.user.csrf_token, session.onAuthError)} session={session} /> : <MailCaseDirectory api={api} />;
}
export function MailCasesScreen({ id }: { id?: string }) {
  return <IdentityBoundary location="Service Desk" headingId={id ? "mail-case-heading" : "mail-cases-heading"} wide><Content id={id} /></IdentityBoundary>;
}
