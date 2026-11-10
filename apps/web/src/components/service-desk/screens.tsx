"use client";

import { IdentityBoundary, useWorkspaceSession } from "@/components/workspace-session";
import { createQueueApi } from "@/lib/ticket-queues";
import { QueueDirectory } from "./directory";
import { QueueDetail } from "./detail";

function Content({ id }: { id?: string }) {
  const session = useWorkspaceSession();
  const api = createQueueApi(session.user.csrf_token, session.onAuthError);
  return id ? <QueueDetail key={id} id={id} api={api} session={session} /> : <QueueDirectory api={api} session={session} />;
}

export function QueuesScreen({ id }: { id?: string }) {
  return <IdentityBoundary location="Service Desk" headingId={id ? "queue-heading" : "queues-heading"} wide><Content id={id} /></IdentityBoundary>;
}
