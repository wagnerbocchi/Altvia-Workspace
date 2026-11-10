"use client";

import { IdentityBoundary, useWorkspaceSession } from "@/components/workspace-session";
import { createWorkApi } from "@/lib/work-items";
import { WorkDirectory } from "./directory";
import { WorkDetail } from "./detail";

function Content({ project, id }: { project?: string; id?: string }) {
  const session = useWorkspaceSession();
  const api = createWorkApi(session.user.csrf_token, session.onAuthError);
  return project ? <WorkDirectory key={project} project={project} api={api} session={session} /> : <WorkDetail key={id} id={id!} api={api} session={session} />;
}
export function WorkDirectoryScreen({ project }: { project: string }) { return <IdentityBoundary location="Tarefas" headingId="work-list-heading" wide><Content project={project} /></IdentityBoundary>; }
export function WorkDetailScreen({ id }: { id: string }) { return <IdentityBoundary location="Tarefas" headingId="work-heading" wide><Content id={id} /></IdentityBoundary>; }
