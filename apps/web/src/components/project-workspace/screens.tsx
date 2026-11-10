"use client";

import { IdentityBoundary, useWorkspaceSession } from "@/components/workspace-session";
import { createProjectApi } from "@/lib/projects";
import { ProjectDirectory } from "./directory";
import { ProjectDetail } from "./detail";
import { Areas } from "./areas";

function Content({ id, areas }: { id?: string; areas?: boolean }) {
  const session = useWorkspaceSession();
  const api = createProjectApi(session.user.csrf_token, session.onAuthError);
  if (areas) return <Areas api={api} session={session} />;
  return id ? <ProjectDetail key={id} id={id} api={api} session={session} /> : <ProjectDirectory api={api} session={session} />;
}
export function ProjectDirectoryScreen() { return <IdentityBoundary location="Projetos" headingId="projects-heading" wide><Content /></IdentityBoundary>; }
export function ProjectDetailScreen({ id }: { id: string }) { return <IdentityBoundary location="Projetos" headingId="project-heading" wide><Content id={id} /></IdentityBoundary>; }
export function AreasScreen() { return <IdentityBoundary location="Áreas operacionais" headingId="areas-heading" wide><Content areas /></IdentityBoundary>; }
