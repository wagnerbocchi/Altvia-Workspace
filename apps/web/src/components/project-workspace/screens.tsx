"use client";

import { IdentityBoundary, useWorkspaceSession } from "@/components/workspace-session";
import { createProjectApi } from "@/lib/projects";
import { ProjectDirectory } from "./directory";
import { ProjectDetail } from "./detail";
import { Areas } from "./areas";
import { ProjectMemberDirectory } from "./members";
import { MilestoneDirectory, MilestoneDetail } from "./milestones";

function Content({ id, areas, members, milestones, milestoneId }: { id?: string; areas?: boolean; members?: boolean; milestones?: boolean; milestoneId?: string }) {
  const session = useWorkspaceSession();
  const api = createProjectApi(session.user.csrf_token, session.onAuthError);
  if (areas) return <Areas api={api} session={session} />;
  if (members && id) return <ProjectMemberDirectory id={id} api={api} session={session} />;
  if (id && milestoneId) return <MilestoneDetail key={milestoneId} id={id} milestoneId={milestoneId} api={api} session={session} />;
  if (milestones && id) return <MilestoneDirectory id={id} api={api} session={session} />;
  return id ? <ProjectDetail key={id} id={id} api={api} session={session} /> : <ProjectDirectory api={api} session={session} />;
}
export function ProjectDirectoryScreen() { return <IdentityBoundary location="Projetos" headingId="projects-heading" wide><Content /></IdentityBoundary>; }
export function ProjectDetailScreen({ id }: { id: string }) { return <IdentityBoundary location="Projetos" headingId="project-heading" wide><Content id={id} /></IdentityBoundary>; }
export function AreasScreen() { return <IdentityBoundary location="Áreas operacionais" headingId="areas-heading" wide><Content areas /></IdentityBoundary>; }
export function ProjectMembersScreen({ id }: { id: string }) { return <IdentityBoundary location="Projetos" headingId="members-heading" wide><Content id={id} members /></IdentityBoundary>; }
export function MilestonesScreen({ id, milestoneId }: { id: string; milestoneId?: string }) { return <IdentityBoundary location="Projetos" headingId={milestoneId ? "milestone-heading" : "milestones-heading"} wide><Content id={id} milestones milestoneId={milestoneId} /></IdentityBoundary>; }
